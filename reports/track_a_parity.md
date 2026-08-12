# Track A — parity gate

**Purpose.** Prove our harness reproduces a published BFCL score. Until this passes,
every downstream number in the sprint is meaningless (`TRACK_A_HANDOFF.md` §5.2).

**Status as of 2026-08-11: PARTIAL — not yet passed, not failed.** One category
deviates far outside the noise band. See the verdict section.

## Reference data and how it was obtained

Parity model: **`Qwen3-14B (FC)`** — the same model we are baselining, chosen so the
baseline sweep doubles as the parity check at no extra GPU cost.

The public leaderboard renders its table client-side, so the HTML contains no scores.
The page's `index_main.js` fetches `./data_<dataset>.csv`; those CSVs were fetched
directly and **only the two `Qwen3-14B` rows were extracted** from each, per the
agreed limit on reading published scores. Retrieved 2026-08-11 from
`https://gorilla.cs.berkeley.edu/data_{overall,non_live,live,multi_turn,agentic}.csv`.

Published `Qwen3-14B (FC)`, rank 43, overall **41.03%**, Apache-2.0, org Qwen.

## Comparison — our sweep run 1 vs published

Our settings: vLLM, `--tool-call-parser hermes`, `--max-num-seqs 32`, temperature
0.001, harness commit `6ea5797`. The published run's settings are **not disclosed**,
which is the entire reason this project reports matched settings.

| Category | Ours (run 1) | Published | Delta | Within noise? |
|---|---:|---:|---:|---|
| simple_python | 95.75% | 95.25% | +0.50 | yes |
| simple_java | 61.00% | 63.00% | −2.00 | yes (2 of 100 items) |
| simple_javascript | 66.00% | 66.00% | 0.00 | exact match |
| multiple | 96.50% | 93.00% | +3.50 | marginal |
| parallel | 93.50% | 80.00% | **+13.50** | **NO** |
| parallel_multiple | 90.00% | 92.00% | −2.00 | yes |
| irrelevance | 82.08% | 85.83% | −3.75 | marginal |
| live_simple | 84.50% | 85.66% | −1.16 | yes |

Measured single-turn run-to-run variance is 0.38 percentage points (three runs of
`simple_python`), so "within noise" here means roughly ±1–2 points allowing for the
smaller item counts; `simple_javascript` has only 50 items, where one item is 2 points.

## The `parallel` discrepancy — UNEXPLAINED

We score **13.5 points higher** than published on `parallel`. A parity deviation in
our favour is not automatically good news: it can equally mean our evaluation is too
lenient.

### Ruled out: leniency on our side

Checked directly against the raw outputs. Among the 187 items scored correct, the
number of `<tool_call>` blocks the model emitted tracks the ground-truth requirement
almost exactly:

| Calls emitted | Items scored correct | Ground truth requires |
|---:|---:|---:|
| 2 | 105 | 109 |
| 3 | 47 | 52 |
| 4 | 32 | 36 |
| 6 | 1 | 1 |
| 8 | 2 | 2 |

Items are not passing by emitting a single call where several were required. The
checker is doing real work and 93.50% is a genuine score.

### Ruled out: vLLM tool-call parser

An earlier draft of this file blamed a server-side tool-call parser difference. **That
explanation is wrong and has been removed.** `QwenFCHandler` renders its own prompt
(tools embedded in `<tools>` XML tags) and calls `client.completions.create` — the raw
completions endpoint — then extracts `<tool_call>` blocks from the returned text
itself. It never sends a `tools=` parameter. vLLM's `--tool-call-parser` and
`--enable-auto-tool-choice` apply only to `/v1/chat/completions` with `tools`, so **they
are never invoked on BFCL's path for this model.** Whatever the published run used for
those flags is irrelevant, and so is ours.

This has a second consequence worth stating plainly: correcting
`qwen3_coder` to `hermes` on the instance did **not** affect any score in this report.
It was correct hygiene and matters for chat-completions work, but the sweep would
almost certainly have produced the same numbers without it. The `--max-num-seqs 8 → 32`
change did buy real throughput.

### Still open

Candidate explanations, none verified:

- **Thinking mode.** Qwen3 emits `<think>` blocks and the handler's chat template has
  an `enable_thinking` branch. The Amazon brittleness paper (arXiv 2606.00135) attributes
  2–5% to how thinking history is handled. Whether the published run enabled it is not
  disclosed.
- **Harness version skew.** Our checkout is pinned at `6ea5797` (March 2026); the
  leaderboard was refreshed July 2026. The upstream changelog has no entries after
  October 2025, so this is not evidenced, merely not excluded.
- **Undisclosed sampling settings** in the published run.

The prompt-flavor run (`Qwen/Qwen3-14B`, no `-FC`) is still worth doing as the next
discriminating experiment, but it no longer tests a parser hypothesis — it tests
whether the FC-vs-Prompt gap reproduces in our harness at all.

## Verdict

**Not yet passed.** Two conditions from the handoff remain unmet:

1. **Three independent runs.** Only run 1 exists. The gate is defined across 3 runs.
2. **`parallel` is outside any plausible noise band** at +13.5 points and is
   unexplained until the prompt-flavor test discriminates between the two hypotheses.

Five of eight categories compared so far reproduce within noise, and
`simple_javascript` matches exactly — so the harness is very unlikely to be broken in
a general way. The problem, if there is one, is specific to parallel call handling.

**Do not treat the baselines as validated until this resolves.** Per the handoff, the
other tracks are gated on this outcome.

## Next actions

1. Finish sweep runs 2 and 3 for `Qwen/Qwen3-14B-FC`.
2. Run the prompt flavor `Qwen/Qwen3-14B` and compare the FC-vs-Prompt gap on
   `parallel` against the published gap. This is the discriminating test.
3. If the parser hypothesis holds, the writeup should report it as a finding: the
   published FC number for this model appears to understate the model because of a
   settings choice, which is a concrete instance of the arXiv 2606.00135 thesis that
   settings move BFCL scores more than training does.
4. `web_search_base` / `web_search_no_snippet` cannot be compared at all until a
   SerpAPI key exists. Published FC values for reference: 8.00% and 12.00%.

---

# RESOLVED 2026-08-11 — the `parallel` discrepancy is an artifact of the published run

**Verified, not inferred.** Method: fetched the per-item failure records that the results
repository publishes alongside each score, at
`BFCL-Result/2025-12-16/score/qwen3-14b-FC/non_live/BFCL_v4_parallel_score.json`.
Each score file's first line is the accuracy summary; subsequent lines are one JSON record per
failed item, including `error`, `error_type`, `model_result_raw`, and `possible_answer`.

## Root cause

Of the 40 published `parallel` failures, **34 share one error**:
`"Invalid syntax. Failed to decode AST. 'str' object has no attribute 'keys'"`, with
`error_type: ast_decoder:decoder_failed`. Inspecting `model_result_raw` for those items shows
the model never answered at all:

```
"model_result_raw": "Error during inference: The read operation timed out"
```

The published run's inference calls timed out. The scorer then attempted to parse that literal
error string as a function call, failed, and recorded the item as a **wrong answer**. These are
dropped requests counted as model errors.

## Scale, and it is specific to this run

Counting items whose failure record contains an inference error, across all 19 scored categories
(4,641 items per model):

| Published run | Inference-error items | Rate | Worst category |
|---|---:|---:|---|
| `glm-4.6-FC` | 1 | 0.0% | — |
| `claude-opus-4-5-20251101-FC` | 5 | 0.1% | web_search_no_snippet 4% |
| `Qwen_Qwen3-8B-FC` | 31 | 0.7% | multi_turn_long_context 14% |
| `Salesforce_Llama-xLAM-2-8b-fc-r` | 49 | 1.1% | web_search_no_snippet 34% |
| **`qwen3-14b-FC` (our base)** | **240** | **5.2%** | **web_search_base 50%** |

Per-category timeout rates for `qwen3-14b-FC`: parallel 16.5%, multi_turn_base 24.0%,
multi_turn_long_context 20.5%, multi_turn_miss_func 18.0%, web_search_base 50.0%,
web_search_no_snippet 16.0%, multi_turn_miss_param 4.0%, multiple 2.5%, live_multiple 0.3%.
All other categories: zero.

## Parity verdict: `parallel` PASSES

Recomputing the published score over items that actually received a response:
**160 correct / 167 attempted = 95.8%.** Our run scored **93.50%** — 2.3 points *below* their
corrected value, comfortably within noise. The +13.5-point "discrepancy" was entirely their
dropped requests. Independent corroboration: every other Qwen3 row on the board scores 92.0–95.5%
on `parallel` (32B FC and Prompt both 93.50%, 8B FC 92.00%, 8B Prompt 94.50%, 14B Prompt 95.50%).
Only the published 14B-FC row at 80.00% is an outlier — in their own data, not ours.

The three hypotheses previously listed as open (thinking mode, harness version skew, undisclosed
sampling) are all **ruled out**; none was the cause.

## Consequence: published baselines for this model are unusable

Corrected baselines for `Qwen3-14B (FC)`, computed as correct ÷ items actually attempted:

| Category | Published | Corrected | Understated by |
|---|---:|---:|---:|
| parallel | 80.00% | 95.8% | 15.8 |
| multiple | 93.00% | 95.4% | 2.4 |
| multi_turn_base | 39.00% | **51.3%** | 12.3 |
| multi_turn_long_context | 32.50% | **40.9%** | 8.4 |
| multi_turn_miss_func | 34.00% | **41.5%** | 7.5 |
| multi_turn_miss_param | 33.50% | 34.9% | 1.4 |
| web_search_base | 8.00% | **16.0%** | 8.0 |
| web_search_no_snippet | 12.00% | 14.3% | 2.3 |

Multi-turn average: reported 34.75% → **corrected ≈42.2%**. Overall 41.03% is likewise
understated, so the previously-stated 36-point gap to first place is overstated (the leader's own
run is clean at 0.1%, so a large gap remains — roughly 30 points).

**Two hard consequences for the sprint:**

1. **Baseline against our own measurements, never the published numbers.** If we trained and then
   reported "multi-turn improved from 34.75%", roughly 7.5 of those points would be someone else's
   infrastructure failure rather than our training. A careful reviewer would find that, and it
   would look precisely like the benchmark inflation this project exists to avoid.
2. **This is a reportable finding in its own right** — and a sharper instance of the arXiv
   2606.00135 thesis. That paper showed *settings* move BFCL scores by 6–15%. This is worse:
   dropped requests scored as wrong answers, moving one model's published multi-turn number by
   ~7.5 points and one category by 15.8. Anyone comparing against published BFCL rows without
   checking per-item error records is comparing partly against timeouts.

## Remaining for the parity gate
Runs 2 and 3 of the sweep (the gate is defined over 3 independent runs). No category remains
unexplained. The prompt-flavor run is no longer a discriminating experiment for this question and
can be demoted to a settings-axis measurement.

---

# Independent verification 2026-08-11 (Track A session)

The RESOLVED section above was written by the orchestrator session. Track A re-derived it
from the source rather than accepting it. **It reproduces exactly.** Method and caveats below.

## Verification of the timeout claim

Fetched the same published per-item score files from
`https://raw.githubusercontent.com/HuanzhiMao/BFCL-Result/main/2025-12-16/score/qwen3-14b-FC/`
(the archive repo is `HuanzhiMao/BFCL-Result`, found via search after the HuggingFace and
`ShishirPatil/BFCL-Result` paths returned 401 and 404 respectively).

Counting items whose failure record contains `"Error during inference"` **anywhere in the
record**: **240 of 4,641 = 5.17%**. This matches the orchestrator's figure exactly, as do the
per-category corrections (multi_turn_base 51.32%, miss_func 41.46%, long_context 40.88%,
web_search_base 16.00%, parallel 95.81%).

**A first attempt at this count got 41 items (0.88%) and was wrong.** It searched only the
top-level `model_result_raw` field. In multi-turn categories that field is a nested list of
per-turn outputs and the error string sits deeper, and `inference_log` holds a copy too. Anyone
re-running this check must search the serialised whole record, not one field.

## Caveat on the correction method — it is an estimate, not a measurement

Corrected accuracy is `correct_count / (total_count - affected_items)`, i.e. drop the affected
items from the denominator. That assumes the dropped items would have scored at the same rate as
the attempted ones. It is the standard treatment for not-validly-attempted items and it is
certainly better than counting a timeout as a wrong answer, but the corrected figures are
**estimates of what the published run would have scored**, not measured values. Multi-turn is the
most exposed: an item is excluded if *any* single step timed out, even though the other steps ran.

Treat corrected published numbers as approximate context. Our own clean measurements are the
only figures that should carry a claim.

## Our own runs are clean — checked, not assumed

The obvious risk is that our harness has the same defect. It does not:

    0 inference-error items out of 4,064  (0.00%)

across all 19 categories generated so far in `bfcl_runs/run1/`, scanning each result line for
`"Error during inference"` and `"timed out"`. The SSH-tunnel-to-local-vLLM path is not dropping
requests. This check must be re-run for every future sweep before any number is quoted.

## Parity comparison against timeout-corrected published values

| Category | Items | Ours (run 1) | Published raw | Published corrected | Δ vs corrected |
|---|---:|---:|---:|---:|---:|
| simple_python | 400 | 95.75% | 95.25% | 95.25% | +0.50 |
| simple_java | 100 | 61.00% | 63.00% | 63.00% | −2.00 |
| simple_javascript | 50 | 66.00% | 66.00% | 66.00% | 0.00 |
| multiple | 200 | 96.50% | 93.00% | 95.38% | +1.12 |
| parallel | 200 | 93.50% | 80.00% | 95.81% | −2.31 |
| parallel_multiple | 200 | 90.00% | 92.00% | 92.00% | −2.00 |
| irrelevance | 240 | 82.08% | 85.83% | 85.83% | −3.75 |
| live_simple | 258 | 84.50% | 85.66% | 85.66% | −1.16 |
| live_multiple | 1053 | 80.44% | 79.01% | 79.24% | +1.20 |
| live_parallel | 16 | 62.50% | 68.75% | 68.75% | −6.25 |
| live_parallel_multiple | 24 | 79.17% | 70.83% | 70.83% | +8.34 |
| live_irrelevance | 884 | 79.07% | 78.05% | 78.05% | +1.02 |
| live_relevance | 16 | 87.50% | 87.50% | 87.50% | 0.00 |
| memory_kv | 155 | 8.39% | 7.10% | 7.10% | +1.29 |
| memory_vector | 155 | 11.61% | 16.77% | 16.77% | −5.16 |

Once the published run's dropped requests are accounted for, **`parallel` goes from the worst
outlier (+13.50) to −2.31, inside the noise band.** Thirteen of fifteen categories agree within
about 4 points.

The two that do not:

- `live_parallel` (−6.25) and `live_parallel_multiple` (+8.34) have **16 and 24 items**. One item
  is 6.25 and 4.17 points respectively. These are single-item differences and carry no signal.
- **`memory_vector` (−5.16) is the one genuine open gap** — 155 items, so roughly 8 items. Not
  explained by timeouts (the published memory runs have zero). Worth a look before the gate is
  declared passed, though it is a small agentic category.

## Verdict

**Effectively passing on run 1, formally incomplete.** No category remains unexplained except
`memory_vector`, and the harness demonstrably reproduces published values across the size range.
The gate is defined over 3 independent runs, so runs 2 and 3 are still required.

## Also verified: format_sensitivity cannot be run on the FC flavor

`format_sensitivity` returned no score. The harness refuses it by design:

    Warning: Format sensitivity test cases are only supported for prompting (non-FC) models.
    Since Qwen/Qwen3-14B-FC is a FC model based on its config, the format sensitivity test
    cases will be skipped.

This corroborates the leaderboard, which shows Format Sensitivity Max Delta `N/A` for
Qwen3-14B (FC) and `14.0` for Qwen3-14B (Prompt). **Consequence for the sprint's priority claim
#3 (lowest format-sensitivity delta): it can only be baselined and claimed on the prompt flavor.**
That makes the prompt-flavor sweep a requirement, not an optional extra.
