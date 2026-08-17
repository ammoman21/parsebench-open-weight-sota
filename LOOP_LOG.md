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
