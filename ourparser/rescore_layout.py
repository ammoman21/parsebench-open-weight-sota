#!/usr/bin/env python
"""
Re-run ONLY the Visual Grounding (layout) evaluation of a completed
kdl_frontier_nano_patched run, from the inference outputs already on disk.
No GPU, no inference, no benchmark source edits.

THE BUG THIS WORKS AROUND (verified by stepping through, not assumed)
---------------------------------------------------------------------
Layout evaluation converts each saved parse result into the layout evaluator's
input format via a per-provider "layout adapter", looked up by provider name:

1. `resolve_layout_provider_name` maps the result's pipeline name to a provider
   name via the pipeline registry
   (src/parse_bench/evaluation/layout_adapters/registry.py:57-63). For our runs
   that resolves to "kdl_frontier_nano_patched" (registered by
   `ourparser/provider.py`).
2. `create_layout_adapter` then looks that key up in the adapter registry — a
   module-level list `_LAYOUT_ADAPTER_REGISTRY`
   (src/parse_bench/evaluation/layout_adapters/registry.py:22). Only the key
   "kdl_frontier_nano" is registered
   (src/parse_bench/evaluation/layout_adapters/adapters.py:2876), so the lookup
   finds nothing — and instead of raising, it silently falls back to the
   "__default__" adapter (registry.py:74-83).
3. Because no exception is raised, the shape-based fallback matcher in
   `create_layout_adapter_for_result` (registry.py:92-96, the `except
   ValueError` that would have tried each adapter's `matches()`) is never
   reached. The default adapter requires an already-converted LayoutOutput and
   raises "Inference output is not LayoutOutput and no provider adapter
   matched." (adapters.py:73). Result: 436/500 layout pages scored as failures
   in the it5 full run purely from the name mismatch.

THE FIX
-------
Register the benchmark's own `KdlFrontierNanoLayoutAdapter` class under the
patched pipeline's provider key, using only the public
`register_layout_adapter` decorator — the same public-registration seam
`ourparser/provider.py` uses for the pipeline itself. Step 2 above then finds
an exact key match and the correct adapter is used everywhere.

WHY REGISTRATION MUST HAPPEN AT MODULE TOP LEVEL
------------------------------------------------
The evaluation runner fans work out to child processes
(`ProcessPoolExecutor`, src/parse_bench/evaluation/runner.py:1019). On macOS
those children start fresh ("spawn") and re-import this script as the
`__mp_main__` module — top-level statements run again in every child, so both
the pipeline registration (import of `ourparser.provider`) and the adapter
alias below are present in the workers too. Code under the
`if __name__ == "__main__"` guard does NOT run in children.

USAGE (from the parsebench directory, its own venv)
---------------------------------------------------
    .venv/bin/python ../ourparser/rescore_layout.py \
        [--output-root output/it5_full/kdl_frontier_nano_patched] \
        [--data-dir data]

Writes reports only into <output-root>/layout/ (the same files the original
evaluation wrote there); every other dimension's reports are untouched.
Deterministic: no randomness, no network, reads only saved outputs.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.environ.get("PARSEBENCH_SRC", os.path.join(_ROOT, "parsebench", "src"))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Registers the "kdl_frontier_nano_patched" (and "..._aggressive") pipelines so the
# provider name resolves — in this process and in every spawn-restarted worker.
import ourparser.provider  # noqa: E402,F401

from parse_bench.evaluation.layout_adapters.adapters import (  # noqa: E402
    KdlFrontierNanoLayoutAdapter,
)
from parse_bench.evaluation.layout_adapters.registry import (  # noqa: E402
    list_layout_adapters,
    register_layout_adapter,
)


def _register_adapter_aliases() -> None:
    """Alias the stock kdl_frontier_nano layout adapter to our pipeline names.

    Idempotent: `register_layout_adapter` raises on a duplicate key, so skip keys
    that are already present (each process only imports this module once, but the
    guard makes re-imports harmless).
    """
    existing = set(list_layout_adapters())
    for key in (ourparser.provider.PATCHED_PIPELINE, ourparser.provider.AGGRESSIVE_PIPELINE):
        if key not in existing:
            # Same priority the stock "kdl_frontier_nano" registration uses
            # (adapters.py:2876); priority only breaks ties among identical keys.
            register_layout_adapter(key, priority=90)(KdlFrontierNanoLayoutAdapter)


_register_adapter_aliases()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--output-root",
        default="output/it5_full/kdl_frontier_nano_patched",
        help="Run directory containing the per-dimension subdirectories (default: the it5 full run)",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Benchmark test-case directory (default: data)",
    )
    args = parser.parse_args(argv)

    from pathlib import Path

    from parse_bench.evaluation.cli import EvaluationCLI

    output_root = Path(args.output_root)
    report_dir = output_root / "layout"
    if not report_dir.is_dir():
        print(f"Error: {report_dir} does not exist", file=sys.stderr)
        return 1

    # Sanity: confirm the alias is visible before spending minutes evaluating.
    keys = list_layout_adapters()
    assert ourparser.provider.PATCHED_PIPELINE in keys, keys
    print(f"Layout adapter registered for: {ourparser.provider.PATCHED_PIPELINE}")

    # Exactly the invocation the end-to-end runner used for the 'layout' group
    # (src/parse_bench/pipeline/cli.py:331-339): results discovered under the run
    # root, test cases filtered to the layout group, reports written ONLY into
    # <run root>/layout/.
    return EvaluationCLI().run(
        output_dir=output_root,
        test_cases_dir=args.data_dir,
        group="layout",
        report_dir=str(report_dir),
        force=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
