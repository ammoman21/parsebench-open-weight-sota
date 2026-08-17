# Fine-tuning plan — teaching inline formatting judgment

Written 2026-08-17, after the prompt probe closed off the cheaper path.

## What the probe established, and why it dictates the design

Four prompt variants, 40-document subset, all measured:

| Variant | Markers emitted | `is_bold` | `is_sup` | Sem. Fmt |
|---|---:|---:|---:|---:|
| control (byte-exact prompt) | 0 | **60.59** | 0.00 | **60.35** |
| v1 minimal | 43 | 58.96 | 1.01 | 61.06 |
| v4 superscript-only | 27 | 56.94 | 13.13 | 59.85 |
| v2 explicit | 1,729 | 55.24 | 12.12 | 57.63 |

Three facts follow, and each one constrains the training design:

1. **The syntax capability exists.** Asked explicitly, the model emitted 1,318 bold markers where
   it had previously emitted zero across 23,802 elements. We are not teaching it to write `**`.
2. **The judgment does not.** Marker volume rose 40× while the score *fell*. It cannot decide
   *which* spans to mark. **That is the thing to train.**
3. **The model is brittle to prompt perturbation.** `is_bold` degrades monotonically with how much
   the prompt was altered — 60.59 → 58.96 → 56.94 → 55.24 — and v4 damaged it *more* than v1
   despite asking for less and explicitly forbidding other formatting. So degradation tracks
   perturbation, not instruction content.

**Design consequence, and it is the single most important decision here: train with the ORIGINAL
prompt unchanged.** Teach the model to emit correct markup in response to the exact string
`"\nText Recognition:\n"` that it is already keyed to. Do not fight the brittleness — change what
the model does with its existing trigger. Any plan that ships a modified prompt inherits a
3–5 point bold regression before training even starts.

## Where the points are

Bold carries the headroom. An oracle-perfect `is_bold` was measured (by replay, inherited from
`reports/formatting_gap_closure.md`) at Semantic Formatting **74.12** against our 52.42 baseline at
the time — roughly **+12 on the dimension, +2.4 overall**. Our current full-corpus figure is 62.02,
so the remaining oracle headroom is smaller but still the largest available.

And **63.3% of scored bold failures are text merged inline** — the characters are present in the
output but not separable, so no post-processing can reach them. Only the model marking them at
generation time can. That is exactly the training target.

**Honest ceiling.** A fine-tune will not reach oracle. Capturing half the bold headroom is
roughly **+1.2 overall: 74.83 → ~76.0**, which is at the line, not comfortably past it. Superscript
adds a little (0 → 13 was achievable by prompt alone, so training should beat that). Treat
"clears 76.36" as plausible, not expected.

## Training data

**Synthetic, rendered from markup we control.** Generate business-document pages in HTML/CSS —
rate-filing tables, report bodies, financial statements — containing known bold runs, superscript
footnote references, strikethrough amendments. Render to image at the DPI the pipeline uses. The
target markdown is then **exact by construction**, not annotated or inferred.

Why not the alternatives: distilling from a stronger vision model inherits its errors and raises
licensing questions; ParseBench's own annotations are the test set and using them is contamination.

Three requirements that come directly from the probe:
- **Negative examples are mandatory.** Pages with no bold, whose correct output has no markers. The
  v2 failure mode was indiscriminate marking; without negatives the fine-tune reproduces it.
- **Match the corpus visually.** The benchmark is enterprise documents and insurance rate filings.
  Synthetic pages that look like arXiv papers will not transfer.
- **Preserve the rest of the behaviour.** Include examples where the expected output is exactly
  what the model already produces, so the gradient does not pull it away from tables and layout.

Target: ~2,000 examples to start, ~30% negatives.

## Training

- **Base:** `KDLAI/KDL-Frontier-Parser-nano`, Qwen2-VL architecture, 1.2B parameters, AGPL-3.0
  (fine under the publication-only constraint).
- **Method:** LoRA on the language layers; leave the vision tower frozen. Low rank, low learning
  rate — we are nudging a narrow behaviour, not reshaping the model.
- **Framework:** LLaMA-Factory or Unsloth; both support Qwen2-VL LoRA.
- **Hardware:** one H100 is ample for 1.2B. Hours per run, not days.

## Evaluation, and the cost control that makes this affordable

**Iterate on the 40-document subset** (`parsebench/data_probe`, already built): ~2 minutes and
~$0.10 per evaluation via `ourparser/probe/run_probe.py`. Full-corpus runs (~70 min, ~$3.30) only
for a candidate that beats control on the subset.

**Measure all five dimensions every time.** The real risk is catastrophic forgetting — a model
taught to emit markup may degrade on Tables, Content Faithfulness or layout. Preregistration §6
already binds us: any change costing more than 0.3 on those dimensions is dropped regardless of
what it gains.

## Cost and timeline

| Item | Estimate |
|---|---|
| Synthetic data pipeline | ~1 day, no GPU |
| Training runs (~5 × 2–4h) | $30–60 |
| Subset evaluations (~20) | ~$2 |
| Full-corpus runs (3) | ~$10 |
| **Total** | **~$100–200, 3–4 days** |

Cheaper than the $200–600 quoted earlier, because the model is tiny and the subset harness makes
iteration nearly free.

## What changes about the claim

This produces **weights we own**. Publish them to a Hugging Face repo under our org, with
attribution to KoreaDeepLearning for the base, and submit a pipeline pointing at them. The entry
then genuinely is our model, the `.eval_results` file lives on our repo, and "our model tops the
open-weight category" becomes literally true if the number lands.

## First step

Build the synthetic data generator and inspect 50 rendered pages by eye before training anything.
If the pages do not look like the benchmark's corpus, nothing downstream will transfer — and that
check costs nothing.
