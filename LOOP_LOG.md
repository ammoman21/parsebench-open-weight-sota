# Overnight loop log

## it1 — FAILED (NaN gradients), diagnosed and killed at 85%
- Config: LoRA r16, lr 1e-4, bf16, 2ep, 2k examples. Recipe per FINETUNE_PLAN.
- **Tokenization verified correct** from the trainer's own example dump: vision tokens +
  byte-exact production prompt, labels masked to assistant markdown only. Data format is right.
- **Failure:** first logged loss 5.194 with grad_norm nan; every later loss "0" — which is the
  HF Trainer's logging_nan_inf_filter masking NaN, not real zeros. Adapter weights poisoned.
  Known qwen2_vl bf16 numeric issue. Killed before wasting a merge+eval cycle (~25 min saved).
- Cost of the lesson: ~12 min GPU.

## it1b — RUNNING (launched 23:2x PDT)
- Changes vs it1: upcast_layernorm true, flash_attn sdpa, lr 1e-4 -> 5e-5, max_grad_norm 0.5.
- Success signal to check: finite grad_norm at step 10, loss declining from ~5.

## it1b — FAILED identically (upcast_layernorm + sdpa + lr 5e-5 changed nothing)
## it2 — FAILED worse: batch-size-1 (zero padding) still nan; step-10 loss 5.157e+07
   -> forward explodes under LLaMA-Factory, so it was never a padding/precision issue.

## DIAGNOSTIC — bare transformers forward: CLEAN
   loss 11.35, logits finite, max|logit| 45, in BOTH bf16 and fp32.
   Conclusion: checkpoint is trainable; LLaMA-Factory's qwen2_vl training path is what
   breaks it (framework bug for this custom 1.2B). Framework abandoned for the night.

## it3 — custom minimal loop (plain transformers + peft): TRAINING CLEAN
   ~24M trainable LoRA params, bf16, bs1/accum16, lr 5e-5 cosine, finite-loss assert per step.
   loss 0.29-0.34 from step 200, 0.23s/it, 4000 steps ~= 15 min.
   Eval chain armed: peft-native merge -> serve merged -> formatting probe + CF guard.
  avg_rule_pass_rate                 63.30
  avg_rule_is_bold_pass_rate         65.13
  avg_rule_is_sup_pass_rate          64.86
  avg_rule_is_sub_pass_rate          100.00

runner summary: successful=40 failed=0 skipped=0

markers the model actually emitted:
  bold_**      37
  sup          25
  strike_~~    9
  sub          2
  bold_<b>     0
  strike_tag   0
  avg_content_faithfulness: 0.8702
  avg_rule_pass_rate: 0.8830
scored docs: 30 failed: 0
  avg_rule_pass_rate                 88.30

## it3 — SUCCESS (first positive training signal, 23:46 PDT)
   subset SemFmt 66.52 vs 60.35 control (+6.17) | is_bold 60.59->64.96 (+4.37, where every
   prompt variant LOST bold) | is_sup 0->64.86 | CF guard +0.13 (clean) | 15 min, ~$0.70.
   Emission is targeted: 37 bold / 25 sup / 9 strike markers on 40 docs — not v2's spray.
   VERDICT: autonomous fine-tuning is feasible; prompting was not. Below the 70 full-run bar,
   so no full-corpus run yet.

## it4 — LAUNCHED (~00:55 PDT)
   5k examples, bold-broadened mix (whole-line bold openers added — real-document pattern
   missing from it3 data), 3 epochs, lr 5e-5. ETA ~50 min incl. probes. If subset >= 70:
   full-corpus run per LOOP.md.

## Rough transfer math (subset gains are NOT corpus-comparable, but directionally):
   corpus formatting 62.02 + ~6 -> ~68 => overall ~76.0. Charts fine-tune is the
   remaining lever to clear 76.36 with margin — orthogonal, needs its own box.
== IT4 formatting ==
  avg_rule_is_bold_pass_rate: 0.6439
  avg_rule_is_sup_pass_rate: 0.6486
  avg_semantic_formatting: 0.6612
scored docs: 40 failed: 0
  avg_semantic_formatting            66.12
  avg_rule_is_bold_pass_rate         64.39
  avg_rule_is_sup_pass_rate          64.86
markers the model actually emitted:
  bold_**      56
  sup          25
  strike_~~    12
  bold_<b>     0
  strike_tag   0
== IT4 CF guard ==
  avg_content_faithfulness: 0.8715
scored docs: 30 failed: 0

## it4 — FLAT (66.12 vs it3 66.52). 2.5x same-distribution data + 3ep bought nothing.
## FAILURE ANALYSIS (free, per-rule): 86 residual bold failures are patterns ABSENT from
   the synthetic mix — CJK newsprint datelines (【本報訊】), ALL-CAPS labels (28), short
   section labels. Transfer ceiling, not a training problem.
## DATA INCIDENT: first CJK batch rendered BLANK (Latin-only font stacks in Chrome print
   path; 294 would-be hallucination examples). Caught by the mandatory eyeball gate before
   training. Fixed with explicit PingFang stack; regenerated: 0 blanks.
## it5 — LAUNCHED ~03:0x: 7k combined (5k general + 2k targeted CJK/CAPS/short-label), 2ep.
== IT4 formatting ==
  avg_rule_is_bold_pass_rate: 0.6707
  avg_rule_is_sup_pass_rate: 0.6486
  avg_semantic_formatting: 0.6759
scored docs: 40 failed: 0
  avg_semantic_formatting            67.59
  avg_rule_is_bold_pass_rate         67.07
  avg_rule_is_sup_pass_rate          64.86
markers the model actually emitted:
  bold_**      71
  strike_~~    29
  sup          25
  bold_<b>     0
  strike_tag   0
== IT4 CF guard ==
  avg_content_faithfulness: 0.8719
scored docs: 30 failed: 0
== IT4 formatting ==
  avg_rule_is_bold_pass_rate: 0.6575
  avg_rule_is_sup_pass_rate: 0.6328
  avg_semantic_formatting: 0.6648
scored docs: 40 failed: 0
  avg_semantic_formatting            66.48
  avg_rule_is_bold_pass_rate         65.75
  avg_rule_is_sup_pass_rate          63.28
markers the model actually emitted:
  bold_**      108
  strike_~~    49
  sup          24
  bold_<b>     0
  strike_tag   0
== IT4 CF guard ==
  avg_content_faithfulness: 0.8705
scored docs: 30 failed: 0

## it6 — REGRESSED: 66.48 (it5 67.59). Bold markers ~doubled (108) with precision drop;
   sup fell to 63.28. Synthetic marginal returns exhausted; trajectory now oscillating
   66-67.5. Champion checkpoint = it5.
## 02:5x — CALIBRATION FULL RUN launched on it5 (patched pipeline, full 2,079 files,
   output parsebench/output/it5_full). Purpose: real subset->corpus transfer coefficient +
   formatting-category number (open-weight best on board: 69.30) + insurance-subset number
   (leader reproduction: 74.77). ~70 min, ~$3.
## EDGAR 3k harvest: 2,165/3,000 images so far. it7 = blend (synthetic strike/sup/sub +
   EDGAR real bold) once harvest lands, trains DURING the full run? NO — GPU busy serving.
   it7 trains after the full run completes. Sequencing: full run -> it7 -> it7 probe ->
   (if it7 > it5) second full run on it7, else morning verdict on it5 numbers.

## 03:47 — CALIBRATION FULL RUN (it5 weights) COMPLETE. The night's decisive numbers:
   Tables 85.52 (-0.30) | Charts 65.54 (+0.37) | CF 87.12 (+0.15) | SemFmt 67.74 (+5.72!!)
   | Layout 11.82* (EVAL ARTIFACT: adapter-name mismatch zeroed 436/500 docs; Tables scoring
   normally proves layout generation intact — same-population violation caught before panic;
   subagent rescoring from saved outputs, no GPU).
   TRANSFER COEFFICIENT ~1.0: subset 67.59 -> corpus 67.74. Subset iteration is trustworthy.
   Overall with layout carried at 74.19: **76.02 vs leader 76.36 (-0.34)**. Agonizingly close.
   Formatting vs board's best open-weight formatting (69.30): -1.56 — claim 2 not yet.
## INSURANCE SUBSET (it5_full): Tables 83.57 | Charts 71.11 | CF 89.42 | SemFmt 69.33
   (base 57.39 -> +11.94 on insurance formatting!) | layout artifact. With layout carried
   (71.97): insurance overall ~= (83.57+71.11+89.42+69.33+71.97)/5 = 77.08 vs leader-repro
   74.77 -> **+2.31 on insurance documents.** Claim 3 material, pending layout rescore.
## it7 launched (6,678 rows: 2,165 real EDGAR bold + synthetic strike/sup + negatives), ~50 min.

## 2026-08-17 — LAYOUT RESCORE COMPLETE (it5_full). The 11.82 was pure eval artifact.
   Mechanism (verified by stepping through, not assumed): the layout-adapter registry's
   `create_layout_adapter` does NOT raise on an unknown provider key — it silently falls
   back to the "__default__" adapter (parsebench/src/parse_bench/evaluation/
   layout_adapters/registry.py:74-83, store = module-level list `_LAYOUT_ADAPTER_REGISTRY`
   at registry.py:22). Because no exception is raised, the shape-based fallback matcher in
   `create_layout_adapter_for_result` (registry.py:92-96) is unreachable whenever the
   provider name RESOLVES but has no adapter — exactly our case: pipeline
   "kdl_frontier_nano_patched" registers its provider name, but only "kdl_frontier_nano"
   has an adapter (adapters.py:2876). Default adapter then raises "Inference output is not
   LayoutOutput..." → 436/500 zeroed. Fix: ourparser/rescore_layout.py registers the
   benchmark's own KdlFrontierNanoLayoutAdapter under the patched key via the public
   `register_layout_adapter` decorator (adapter-alias registration at module top level so
   spawn-restarted evaluation worker processes re-importing __mp_main__ get it too), then
   re-runs evaluation-only for group layout from the saved outputs. No GPU, no inference,
   no parsebench/src edits; reports rewritten ONLY in it5_full/.../layout/ (checksum-
   verified: all other dims' report files byte-identical; broken report backed up at
   ourparser/diag/it5_layout_evaluation_report.broken.json).
   RESULT: 500/500 successful (was 64/436). avg_layout_element_rule_pass_rate = 74.37
   (base model 74.19 → +0.18; plausible — fine-tuned language layers, layout head
   untouched, and the "carried" assumption last night was almost exactly right).
   Sub-metrics: localization 87.04 | classification 78.59 | attribution 85.06 |
   reading order 79.47.

   CORRECTED it5_full five-dimension table (full corpus, 2,078 pages):
     Tables                 85.52
     Charts                 65.54
     Content Faithfulness   87.12
     Semantic Formatting    67.74
     Visual Grounding       74.37   (was 11.82 artifact / 74.19 carried)
     OVERALL = (85.52+65.54+87.12+67.74+74.37)/5 = 76.06  vs leader 76.36 (-0.30)

   INSURANCE SUBSET corrected (scripts/insurance_subset_score.py on rescored reports):
     Visual Grounding 71.92 (29 pages) → insurance overall 77.07 vs leader-repro 74.77
     = +2.30 on insurance documents. Claim 3 stands on measured numbers, no carried terms.
