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

| Dimension | This model | Base (published) | Base (same environment) |
|---|---:|---:|---:|
| Tables | 86.14 | 85.56 | 85.76 |
| Charts | 65.39 | 63.41 | 63.69 |
| Content Faithfulness | 87.35 | 87.19 | 87.18 |
| Semantic Formatting | **71.71** | 66.81 | 52.42 |
| Visual Grounding | 74.15 | 78.84 | 74.19 |
| **Overall** | **76.95** | **76.36** | **72.65** |

Confirmation-run variance: PENDING_CONFIRMATION_RUN.
Insurance-document subset (384 docs incl. SERFF rate filings, methodology in repo): **77.60**
vs 74.77 for the base pipeline measured identically.

The honest comparison is the same-environment column: **+4.30 overall** head-to-head.
The published-number comparison (+0.59) crosses evaluation environments and is reported
with that caveat. The formatting score exceeds the best open-weight formatting entry on
the public board (69.30).

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
