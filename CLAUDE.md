# bfcl-sprint — project instructions (read by every agent, every session)

## Communication
- Define every acronym and term of art in plain language on first use, in every report and
  every code comment. No unexplained shorthand — not even common ML ones (SFT, RL, LoRA,
  AST, MoE). If a term is load-bearing for a decision, its meaning appears in the same message.
- Assume a strong general software engineer who does NOT know machine-learning training
  vocabulary, benchmark names, or insurance vocabulary.

## What this project is
We are manufacturing a synthetic training dataset of tool-calling examples, then
post-training a small open-weight model on it, to score at or above the top of the
Berkeley Function-Calling Leaderboard (BFCL) v4 under matched evaluation settings.

"Tool calling" (a.k.a. function calling): the model is shown machine-readable descriptions
of tools it has never seen and must emit a correctly-named call with correctly-typed
arguments, sometimes across a multi-step conversation where each call's result affects
the next.

The reference benchmark lives at `gorilla/berkeley-function-call-leaderboard/`.
The dataset we build lives at `datagen/`. Read `TRACK_B_CONTRACT.md` before writing any code.

## Hard prohibitions (violating any of these invalidates the whole result)

1. **Never copy, paraphrase, or derive training content from BFCL's data files.**
   `gorilla/berkeley-function-call-leaderboard/bfcl_eval/data/**` may be read ONLY by
   `datagen/decontam/` (the overlap checker) and only to extract identifiers for
   exclusion. No generator, prompt, or dataset row may contain a BFCL function name,
   description, question, or environment class.
2. **Never use OpenAI or Anthropic model outputs as training data ("teacher" data).**
   Their terms prohibit using outputs to train other models. The only permitted teacher is
   an MIT/Apache-licensed open model accessed via API (DeepSeek V4, Qwen). Record the
   teacher model and license in every generated row's provenance field.
3. **Never evaluate on, tune against, or inspect scores from the real benchmark during
   development.** Checkpoint selection uses our own held-out dev split only. Full benchmark
   runs are budgeted, pre-registered events.
4. **Never invent results.** If a check did not run or a test failed, say so plainly with
   the output. Partial work honestly reported beats a clean-looking summary.
5. **Do not modify anything inside `gorilla/`.** It is a pinned upstream checkout, our
   evaluation instrument. Configuration goes in our own files.

## Conventions
- Python 3.12 via the repo venv: `bfcl-sprint/.venv/bin/python`. Run tests with
  `.venv/bin/pytest`.
- Every module is deterministic given an explicit `seed` argument. No unseeded randomness,
  no wall-clock dependence — reruns must reproduce byte-identical output.
- Every generator writes JSON Lines (one JSON object per line) validated against the
  record schema in `datagen/schema.py` before being written.
- Type hints on public functions. Comments explain constraints, not narration.
- Small, focused modules; one component per file as laid out in the contract.

## Definition of done for any assigned task
1. The module exposes exactly the interface named in `TRACK_B_CONTRACT.md`.
2. `.venv/bin/pytest` passes for its test file.
3. Its acceptance criteria in the contract are met, each demonstrated by a command whose
   real output is quoted in the final report.
4. Determinism verified: same seed twice → identical output.
5. The report states what was NOT done or is uncertain.
