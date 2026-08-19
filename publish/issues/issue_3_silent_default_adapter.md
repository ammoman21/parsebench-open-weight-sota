# create_layout_adapter silently returns the __default__ adapter for unknown provider keys, making the shape-matcher fallback unreachable — new pipelines score ~0 on Visual Grounding

## What

When a layout evaluation runs for a provider key that has no registered adapter, `create_layout_adapter` does not raise — it quietly returns the `__default__` adapter. Because no exception propagates, the shape-based fallback in `create_layout_adapter_for_result` (which asks each registered adapter's `matches()` whether it can handle the output) never gets a chance to run for a *resolvable* provider name. The default adapter then fails per-document with "Inference output is not LayoutOutput and no provider adapter matched", and the pipeline's Visual Grounding collapses toward zero with no registry-level error anywhere.

## Where

`src/parse_bench/evaluation/layout_adapters/registry.py`:

- `:66-88` — `create_layout_adapter`: if `provider_name` matches no registration, execution falls through to the `__default__` lookup (`:74-83`) and returns it. The `ValueError` at `:86` is only reachable when no `__default__` exists — and one always does.
- `:89-109` — `create_layout_adapter_for_result`: the `matches()` fallback loop runs only when `create_layout_adapter(provider_name)` raises `ValueError` (`:92-96`). Given the above, that is dead code for every unknown-but-resolvable provider key.
- Registry store: module-level list `_LAYOUT_ADAPTER_REGISTRY` at `:22`.

## Evidence (how we hit it)

We evaluated a pipeline registered under a new provider key, `kdl_frontier_nano_patched`, whose layout output is byte-compatible with the existing `kdl_frontier_nano` adapter — but that adapter is registered for the key `"kdl_frontier_nano"` only (`layout_adapters/adapters.py:2876`). Result on a full 500-document layout run:

- 436/500 documents errored with `"Worker error: Inference output is not LayoutOutput and no provider adapter matched."`; the dimension reported **11.82**.
- After registering the same adapter class under our key via the public `register_layout_adapter` decorator and re-running evaluation-only from the saved outputs: **500/500 successful, 74.37** — a 62-point swing from a registration detail, with no error pointing at the registry.

The broken evaluation report is preserved in our repo (`ourparser/diag/it5_layout_evaluation_report.broken.json`) alongside the rescoring script.

## Impact

Anyone adding a new pipeline (or renaming a provider) whose outputs would be handled fine by an existing adapter — or by the `matches()` fallback that exists precisely for this case — instead gets a silently near-zero Visual Grounding score. The failure surfaces as hundreds of per-document worker errors rather than one clear "no adapter registered for provider X", so it is easy to misread as a model problem. (We initially did.)

## Suggested fix

Small ordering change, no behaviour loss:

1. In `create_layout_adapter`, when an explicit `provider_name` is given and no registration matches, raise (or signal) instead of falling through to `__default__`; or
2. In `create_layout_adapter_for_result`, try the `matches()` shape fallback *before* resorting to `__default__`.

Either restores the intended chain: explicit key → shape matcher → default. A loud log line when the default adapter is selected for a named provider would also have surfaced this immediately.

## Reproduction

Rescoring script and before/after reports: https://github.com/ammoman21/parsebench-open-weight-sota (see `ourparser/rescore_layout.py` and `ourparser/diag/`).
