---
license: agpl-3.0
base_model: KDLAI/KDL-Frontier-Parser-nano
tags: [document-parsing, ocr, parsebench, qwen2_vl, image-text-to-text]
language: [en, zh, hi]
---

# florin-parser-nano (fine-tune of KDL-Frontier-Parser-nano)

A LoRA fine-tune of [KDLAI/KDL-Frontier-Parser-nano](https://huggingface.co/KDLAI/KDL-Frontier-Parser-nano)
(KoreaDeep, 1.2B, Qwen2-VL architecture) that teaches the model to emit inline formatting —
`**bold**`, `~~strikethrough~~`, `<sup>`/`<sub>` — during text recognition, with the production
prompt unchanged. Full attribution to KoreaDeep for the base model and pipeline design.
License is AGPL-3.0, inherited from the base.

## ParseBench results (full corpus, 2,079 documents, all five dimensions measured)

> **Correction, 2026-08-21.** Maintainer review of ParseBench PR #99 found two defects
> in our markdown emission (list markers swallowed into bold spans; a heading gate that
> promoted short sentences ending in `.`). Both were fixed and **both full runs were
> replayed on identical stored model output** with the fixed emission. The table below
> shows the corrected numbers. Prior reported figures: Overall 76.95/76.89, mean 76.92;
> Semantic Formatting 71.71/71.66. Net effect of the correction: Semantic Formatting
> −1.04, Charts −0.14, Content Faithfulness +0.03, Tables and Visual Grounding unchanged.

| Dimension | This model | Base (published) | Base (same environment) |
|---|---:|---:|---:|
| Tables | 86.14 | 85.56 | 85.76 |
| Charts | 65.25 | 63.41 | 63.69 |
| Content Faithfulness | 87.38 | 87.19 | 87.18 |
| Semantic Formatting | **70.66** | 66.81 | 52.42 |
| Visual Grounding | 74.15 | 78.84 | 74.19 |
| **Overall** | **76.72** | **76.36** | **72.65** |

Confirmation-run variance: two independent full runs: 76.72 and 76.66 (|Δ| = 0.06 overall; max per-dimension |Δ| = 0.12). Reported figure: mean 76.69.
Insurance-document subset (384 docs incl. SERFF rate filings, methodology in repo): **77.60**
vs 74.77 for the base pipeline measured identically — measured before the 2026-08-21
emission correction; subset re-measurement pending, expect a small downward revision in
its formatting component.

The honest comparison is the same-environment column: **+4.04 overall** head-to-head
(mean of two runs; run 1 alone is +4.07). The published-number comparison (+0.33 on the
mean) crosses evaluation environments and is reported with that caveat. The formatting
score (70.64 mean) exceeds the best open-weight formatting entry on the public board
(69.30).

## Training

- **Data:** 6,678 region-crop→markdown pairs. 2,165 real fragments from SEC EDGAR insurance-carrier
  filings (bold ground truth derived from filing HTML DOM), 3,313 synthetic rendered fragments
  (sole source of strikethrough/superscript/subscript; incl. CJK newsprint and Devanagari
  textures), 1,200 no-styling negatives to teach restraint.
- **Method:** LoRA r16 on language attention+MLP only; vision tower and projector frozen;
  completion-only loss; prompt byte-identical to the production pipeline ("\nText Recognition:\n").
  2 epochs, lr 5e-5, bf16, single H100, ~50 minutes.
- **Why prompting was not enough:** four measured prompt variants all scored at or below control —
  the base model emits markup when asked but marks the wrong spans, and degrades monotonically
  with any prompt perturbation. Details in the linked method note.

## Reproduction

Everything (training loop, data generators, EDGAR harvester, evaluation harness, per-iteration
logs) is at: https://github.com/ammoman21/parsebench-open-weight-sota
