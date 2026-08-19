# Add florin-parser-nano (fine-tune of KDL-Frontier-Parser-nano): provider, pipeline, leaderboard entry

## Environment disclosure — read this first

All numbers in this PR were measured in **our** evaluation environment, and our environment
does not fully reproduce the current #1 open-weight row. Running the in-repo
`kdl_frontier_nano` pipeline unmodified against the public KDL weights, we measure
**Overall 72.65** where the leaderboard publishes **76.36**. Three dimensions reproduce to
within 0.3 points (Tables +0.20, Charts +0.28, Content Faithfulness −0.01); two do not
(Semantic Formatting −14.39, Visual Grounding −4.65). The full parity analysis is in our
reproduction repo:
[`reports/insurance_subset_scores.md` §4](https://github.com/ammoman21/parsebench-open-weight-sota/blob/main/reports/insurance_subset_scores.md)
("Parity against the published leaderboard — three of five dimensions reproduce, two do not").

Because of that, the honest comparison for this entry is **same-environment,
head-to-head**: 72.65 → 76.95/76.89 (**+4.30 / +4.24** over the base pipeline measured
identically). The cross-environment comparison against the published 76.36 (+0.56 on our
mean) carries the caveat above. **We welcome and expect the maintainers to re-run this
pipeline in their own environment and to use those numbers for the leaderboard if they
differ from ours.**

## What this entry is

[`florin-inc/florin-parser-nano`](https://huggingface.co/florin-inc/florin-parser-nano) is a
LoRA fine-tune (low-rank adaptation — small trainable adapter matrices on top of frozen
base weights; here merged back into the checkpoint, with the adapter also published) of
[`KDLAI/KDL-Frontier-Parser-nano`](https://huggingface.co/KDLAI/KDL-Frontier-Parser-nano)
(KoreaDeep, 1.2B parameters, Qwen2-VL architecture). Full attribution to KoreaDeep for the
base model and the pipeline design. Weights are AGPL-3.0, inherited from the base model,
and are public (merged checkpoint + adapter + model card + `.eval_results/parsebench.yaml`).

The fine-tune teaches the model to emit inline formatting — `**bold**`,
`~~strikethrough~~`, `<sup>`/`<sub>` — during text recognition, with the production prompt
unchanged. Training data: 6,678 region-crop→markdown pairs (real SEC EDGAR filing
fragments with bold ground truth derived from the filing HTML, synthetic rendered
fragments for strikethrough/super/subscript, and no-styling negatives). Details and the
full training loop are in the reproduction repo linked below.

The inference pipeline is the repo's own `kdl_frontier_nano` provider, inherited
unchanged — same layout stage, same crop/bucket step, same four recognition passes, same
retry/error handling, same serve command shape — plus four fixes in the markdown
*emission* step (element list → markdown string), implemented in the new provider module
and documented in its docstring:

1. map the `section_header` layout label to `Section-header` (currently unmapped, so `## `
   headings are unreachable);
2. derive heading depth 1–4 from each Title's bounding-box height rank (currently every
   heading is `# `);
3. bold paragraph-leading `Label:` runs (bold in source documents, dropped by the current
   emission);
4. relax the standalone-heading gate by dropping two vetoes that reject genuine headings
   like "Notes:", with a 20-word cap.

The `pages` payload (category / bounding box / text per element) is left exactly as the
inherited pipeline produced it, so the Visual Grounding dimension is computed from
unmodified pipeline output. The provider does not modify `kdl_frontier_nano.py`; it
subclasses its provider and engine and scopes the two module-attribute rebindings the
vendored file requires (details in the module docstring).

## Scores (full corpus, 2,078 documents, 100% success, both runs)

Two independent full runs; leaderboard row uses the mean.

| Dimension | Run 1 | Run 2 | Mean (submitted) |
|---|---:|---:|---:|
| Tables | 86.14 | 86.05 | 86.10 |
| Charts | 65.39 | 65.27 | 65.33 |
| Content Faithfulness | 87.35 | 87.33 | 87.34 |
| Semantic Formatting | 71.71 | 71.66 | 71.69 |
| Visual Grounding | 74.15 | 74.14 | 74.15 |
| **Overall** | **76.95** | **76.89** | **76.92** |

Run-to-run variance: |Δ| = 0.06 Overall, max per-dimension |Δ| = 0.12. Scoring used the
repo's default configuration (rule-based judge; `LLAMACLOUD_BENCH_LLM_NORMALIZATION`
unset, i.e. off). Cost_Per_Page is left blank, matching the other self-hosted
"VLM - Open Weight" rows.

Against the inclusion criteria: weights are public on Hugging Face; a full run finishes in
under an hour of inference on one H100 (well inside single-digit hours); no framework
changes are required — the provider follows the existing `kdl_frontier_nano` conventions
and is driven by `parse-bench run florin_parser_nano`.

## Reproduction

Serve (identical to the base model, only the checkpoint and served name differ):

```bash
vllm serve florin-inc/florin-parser-nano \
  --served-model-name florin-parser-nano \
  --max-model-len 8192 --gpu-memory-utilization 0.85 \
  --max-num-seqs 24 --trust-remote-code \
  --limit-mm-per-prompt '{"image":1}'
```

Run:

```bash
FLORIN_NANO_ENDPOINT_URL=http://localhost:8000/v1 \
uv run parse-bench run florin_parser_nano
```

Everything else — training loop, data generators, EDGAR harvester, per-iteration logs, the
parity analysis, and the emission-change measurements (including a
disclosed-but-not-submitted more aggressive emission variant we deliberately excluded from
this PR) — is at:
https://github.com/ammoman21/parsebench-open-weight-sota

`.eval_results/parsebench.yaml` on the Hugging Face model repo records the same numbers.

## Files changed

- `src/parse_bench/inference/providers/parse/florin_parser_nano.py` — new provider
  (subclasses `kdl_frontier_nano`; emission fixes included in the module; exact serve
  command in the docstring)
- `src/parse_bench/inference/providers/parse/__init__.py` — module list entry
- `src/parse_bench/inference/pipelines/parse.py` — `florin_parser_nano` pipeline spec
- `docs/pipelines.md` — self-hosted pipeline entry
- `.env.example` — `FLORIN_NANO_ENDPOINT_URL`
- `leaderboard.csv` — one row (category `VLM - Open Weight`)
- `README.md` — top-10 table refresh (hand-applied to keep the diff minimal;
  byte-identical to `scripts/update_readme.py` output except that script reformats the
  pre-existing Pulse Ultra 2 cost cell `15¢` → `15.00¢`)

Verification we ran before submitting: the in-repo emission port was replayed against all
2,077 element-bearing stored documents from our full runs and produces byte-identical
markdown to the code that generated the submitted scores; provider import, registration,
config-error path, and binding restore are exercised the same way.
