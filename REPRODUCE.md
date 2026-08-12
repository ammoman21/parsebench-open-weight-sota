# Reproducing these results

Everything here is our own work. The two benchmarks it measures are **not vendored** — they are pinned
by commit hash below and cloned fresh, so there is no ambiguity about what was modified and what was
not. **No file inside either upstream checkout was changed.**

## Pinned upstream commits

| What | Repository | Commit |
|---|---|---|
| ParseBench (document parsing) | `run-llama/ParseBench` | `facdaf0257cf06225fc72bf54dfdf497be4a9df3` |
| BFCL harness (function calling) | `ShishirPatil/gorilla` | `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` |

The public ParseBench leaderboard states its own models were evaluated at gorilla commit `f7cf735`;
ours is `6ea5797`. That difference is disclosed in `reports/track_a_parity.md`.

## Setup

```bash
# 1. ParseBench, pinned
git clone https://github.com/run-llama/ParseBench.git parsebench
cd parsebench && git checkout facdaf0257cf06225fc72bf54dfdf497be4a9df3
uv sync && uv pip install pymupdf4llm pdf2image     # pdf2image needs poppler on the host
uv run parse-bench download                          # ~584 MB, 2,079 files
cd ..

# 2. Put our harness and measurement scripts where they expect to run
cp -R harness/. parsebench/scripts/

# 3. Serve the base model on one NVIDIA H100 80GB
vllm serve KDLAI/KDL-Frontier-Parser-nano \
  --served-model-name kdl-frontier-parser-nano \
  --max-model-len 8192 --gpu-memory-utilization 0.85 \
  --max-num-seqs 24 --trust-remote-code \
  --limit-mm-per-prompt '{"image":1}'
```

## Reproduce the baseline (our reproduction of the published leader)

```bash
cd parsebench
KDL_NANO_ENDPOINT_URL=http://127.0.0.1:8000/v1 \
LLAMACLOUD_BENCH_LLM_NORMALIZATION=off \
  uv run parse-bench run kdl_frontier_nano --max_concurrent 8
uv run parse-bench leaderboard      # scores land in output/_leaderboard.html
```

Expected: Tables 85.76 · Charts 63.69 · Content Faithfulness 87.18 · Semantic Formatting 52.42 ·
Visual Grounding 74.19 · **Overall 72.65**. Roughly 35 minutes and ~$2 of rented GPU.

Note this is **3.71 points below** the leader's published 76.36. Three dimensions reproduce within
0.3; two do not. See `reports/track_a_parity.md` — we could not explain the remainder, and a control
model (`Chandra-ocr-2`) reproduced its own published chart score exactly, which establishes that the
scoring is sound and the deficits are per-model rather than a fault in the harness.

## Reproduce the patched result

```bash
cd parsebench
KDL_NANO_ENDPOINT_URL=http://127.0.0.1:8000/v1 \
LLAMACLOUD_BENCH_LLM_NORMALIZATION=off \
  uv run python ../ourparser/run_patched.py --pipeline kdl_frontier_nano_patched
```

Expected: **Overall 74.64** (treat as 74.6 +/- 0.2), a measured **+1.99** over our own baseline. The
`kdl_frontier_nano_aggressive` pipeline reproduces the disclosed-but-not-submitted 75.65. Why the
aggressive set exists and why it is not submitted is in `PREREGISTRATION.md` section 4.

## Reproduce every figure without a GPU

The replay harness rebuilds final markdown byte-identically from saved per-element outputs and scores
it with the benchmark's own rule classes, so emission changes are measurable at zero marginal cost.

```bash
cd parsebench
uv run python scripts/genuine_set_measure.py        # submitted and aggressive sets
uv run python scripts/semfmt_oracle.py              # per-sub-type oracle ceilings
uv run python scripts/heading_diagnosis.py          # why individual bold rules fail
uv run python scripts/insurance_subset_score.py output/kdl_frontier_nano --subset insurance
```

Use `parsebench/.venv/bin/python` (via `uv run`), **not** a top-level `.venv` — the benchmark needs
`rapidfuzz`, which only the project environment has. The `_*.json` files in `harness/` are saved
measurement records, so every figure in `reports/` is re-derivable without re-running anything.

Two fidelity guarantees the scripts enforce, aborting if either fails: our re-implementations
reproduce the vendored functions **byte-for-byte across 2,041 artifacts**, and the patched provider
reproduces the replay measurement to **ten decimal places** through the same method live inference
calls.

## Known limitations

- Provider-level transfer error is unmeasured on 157 of 476 documents, hence the +/-0.2 band.
- The `Section-header` category-map fix ships but **contributes exactly 0 and is unmeasurable by
  replay** — saved artifacts persist only the canonicalised category, so which elements the model
  labelled `section_header` cannot be known without live inference. The defect is real by inspection
  (0 occurrences across 2,078 artifacts; the `##` branch is dead code) but it is excluded from every
  reported number.
- GriTS and the Visual Grounding metric were not re-run under the patches; their inputs were verified
  invariant (0 of 1,074 table documents and 0 of 400 element triples changed).

## What is deliberately absent

- **Upstream checkouts** (`gorilla/`, `parsebench/`) — pinned above, cloned fresh.
- **Benchmark data and run outputs** — 584 MB of corpus and 571 MB of per-page results, regenerable.
  The small measurement records backing the reported figures *are* included.
- **Virtual environments**, caches, logs, and any credential material.

## Layout

```
ourparser/          our patched provider: emission.py, provider.py, run_patched.py
harness/            replay harness, measurement scripts, saved measurement records
reports/            every measurement and diagnosis, with file:line citations
PREREGISTRATION.md  claim, patch set and protocol fixed in advance, plus amendments
DECISIONS.md        every decision and why, including the mistakes
PARSEBENCH_WHITEPAPER.html   the working paper
STATUS.md TRACKS.md live state and plan
```
