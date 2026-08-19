# Thank you for KDL-Frontier-Parser-nano — an attributed fine-tune, and two findings from a week inside your pipeline

We spent the last week reproducing and studying KDL-Frontier-Parser-nano as the top open-weight entry on ParseBench (LlamaIndex's document-parsing benchmark: ~2,079 pages scored by deterministic rules across five dimensions). First, the thanks: this is a remarkable 1.2B-parameter model. Its localization is the strongest sub-metric in its own evaluation, and everything we did below rests on capabilities that were already in your weights.

**Attribution notice.** We have published a fine-tune of your model: [florin-inc/florin-parser-nano](https://huggingface.co/florin-inc/florin-parser-nano) — a LoRA adapter (low-rank adaptation: your 1.2B weights stay frozen; ~24M correction parameters are trained on the language layers) that teaches the model to emit inline formatting during text recognition, with your production prompt byte-identical. It is released under AGPL-3.0, inherited from your license, with full attribution to KoreaDeep for the base model and pipeline design; adapter, merged weights, training code and data generators are all public.

While studying the pipeline we measured two things that seem more useful to you than to anyone else, so here they are.

## 1. Page-header over-prediction

On ParseBench's 500-page Visual Grounding corpus, the pipeline predicts `Page-header` **1,282 times against 531 in the ground truth — 2.4x over-prediction** — and it is the weakest scored class by a wide margin: **F1 0.36** (precision 0.372, recall 0.393), versus 0.59–0.80 for every other scored class. Since both precision and recall are near-chance, this looks like a systematic disagreement between the model's `header` label and the benchmark's `Page-header` convention rather than a marginal calibration issue; the only source of that class is the single map entry `"header": "Page-header"` (`kdl_frontier_nano.py:554`), so it may be cheap to investigate.

Honest caveat on size: `Page-header` is only **3.25% of the benchmark's grounding rules** (531 of 16,325), so fixing it moves the headline modestly. We flag it because it is the largest per-class quality gap we found, not because it is a large scoreboard lever.

## 2. The formatting prompt gap — and what closing it is worth

The model's complete instruction set is five bare strings (`kdl_frontier_nano.py:2596-2604` — `"\nText Recognition:\n"` and four siblings); no prompt anywhere asks for formatting. The measurable consequence: **zero inline markers — no bold, strikethrough, superscript or subscript — across 23,802 output elements from 1,196 documents**, on a benchmark whose Semantic Formatting dimension scores exactly those markers. And **63.3% of the failed bold checks are text merged inside longer lines**, which no post-processing can ever reach — only generation can.

The model itself is not the limitation.[^1] Our fine-tune adds only that behavior — same prompt, same pipeline, vision layers frozen — and in our environment, head-to-head on the full corpus with identical serving and scoring, it moves the pipeline from **72.65 to 76.95 overall (+4.30)**, with Semantic Formatting going from 52.42 to 71.71. (For calibration: we could not reproduce your published 76.36 in our environment — we measure your unmodified pipeline at 72.65, three dimensions matching within 0.3 — so we quote the same-environment delta as the meaningful number.) We read that gain as a statement about your base model: the capability was there; it was never asked. The weights are yours to take, fold in, or ignore — AGPL-3.0, attributed.

One more small thing we noticed on the way, in case it saves you a code read.[^2]

Happy to share any of our measurement records, training data generators, or per-iteration logs: https://github.com/ammoman21/parsebench-open-weight-sota. Thanks again for putting a model this strong in the open.

[^1]: We tried prompting first and measured it four ways before training anything. The model emits markup on request (1,729 markers under an explicit-instruction prompt) but marks the wrong spans, and its bold accuracy degrades **monotonically with any perturbation of the production prompt** — control 60.59, one added sentence 58.96, a superscript-only request 56.94, explicit rules and examples 55.24. The model is keyed very tightly to its training prompt, which is why the fine-tune keeps that prompt byte-identical.

[^2]: `NATIVE_LAYOUT_CATEGORY_MAP` (`kdl_frontier_nano.py:545-572`) has no `section_header` key, so the `Section-header` category is never produced — 0 occurrences across all 2,078 artifacts in our runs — and the `## ` branch of `_nano_format_element` (`:2932`) is unreachable. Every heading therefore emits as `h1`, which makes 12.9% of the benchmark's title-hierarchy constraints structurally unsatisfiable for the pipeline. A map entry plus any level inference (bounding-box height works) recovers it.
