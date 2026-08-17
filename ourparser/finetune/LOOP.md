# Overnight loop protocol

**Budget guard: hard $50 GPU ceiling for the night (~18h at $2.63/hr).** A time-based
self-destruct replaces the idle watchdog — training makes vLLM idle, so the idle
watchdog would kill the box mid-run. The box destroys itself at deadline regardless
of what I am doing; all checkpoints and logs sync to the Mac after every iteration.

## One iteration
1. stop vllm -> train LoRA (ftenv, ~1-2h for 2k×2ep on 1.2B)
2. merge adapter -> /workspace/merged/itN
3. point VLLM_MODEL at merged dir -> start vllm
4. Mac: text_formatting probe subset (primary, ~2 min) + text_content collateral
   subset (guard, ~2 min)
5. rsync checkpoints+logs to Mac; log scores to LOOP_LOG.md; decide next config

## Decision tree (diagnosis -> next config)
- markers absent or rare        -> +1 epoch, or LR 2e-4, or styled fraction up
- markers everywhere, score down (v2-in-weights) -> negatives 30->45%, LR down 2x
- right markers, wrong spans    -> data realism: fonts/weights subtlety, harder negatives
  (bold-adjacent plain text), span-tightness examples
- text_content collateral < -0.3 -> rank 16->8, LR down 2x, add plain-transcription volume
- bold up but title credit down -> add heading-bearing regions so Title behaviour is anchored
- two consecutive iterations flat -> stop; write up "not feasible at this budget" honestly

## Success/stop criteria
- SUCCESS: subset SemFmt ≥ 70 with CF collateral ≥ -0.3 -> full-corpus run (~$3) to confirm
  -> if full run ≥ 76.4 overall: publish weights, claim per PREREGISTRATION tiers
- STOP: budget guard, or 4 iterations without a subset improvement over 60.35 control
