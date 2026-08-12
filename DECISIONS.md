# Decision log — the effort to top a benchmark

Written 2026-08-11. Every decision, why it was made, and what it cost. Companion to `STATUS.md`
(current state), `TRACKS.md` (plan), `PARSEBENCH_PLAN.md` (target rationale).

---

## Phase 1 — Understanding the landscape (Aug 7)

**D1. Research the model/benchmark landscape with parallel web-research agents rather than answering
from memory.** *Why:* assistant knowledge ends Jan 2026 and the field turns over in weeks. Produced
the frontier picture (Claude Opus 5, GPT-5.6 Sol, Gemini 3.1 Pro; open-weight within ~6 points of
closed) and the benchmark map.

**D2. Treat a private eval suite, not a model, as the venture's durable asset.** *Why:* every static
public benchmark is assumed contaminated; underwriting needs calibration against your own realized
loss data, which nobody can copy. This conclusion held up all week and is why the benchmark work is
framed as a credibility artifact rather than the product.

## Phase 2 — Choosing a target (the expensive part)

**D3. Reject INS-ActBench (actuarial, Fudan).** *Why:* the repo ships eval code but **no dataset** —
3 commits, 0 releases, no data files, and a HuggingFace staffer's request to host the data sat
unanswered for two weeks. You cannot run what you cannot download. *Cost of not checking earlier:* I
had already written an 8-week and then a 2-week attack plan against it.

**D4. Reject weather/catastrophe benchmarks.** *Why:* months of work, a different discipline
(geospatial ML, ERA5-scale data engineering), and near-zero skill transfer from LLM post-training.

**D5. Reject building our own benchmark.** *Why:* Amol wants to top a known board, not found one. An
orphan benchmark with three stars is weak signal.

**D6. Reject every insurance-specific board.** *Why:* a verified survey found none has downloadable
data + a live leaderboard + an open submission path simultaneously. InsureBench never launched
("Scores pending, opening 2026", placeholder chart). SnorkelUnderwrite is archived with all 33
entries self-run by Snorkel. ActuBench is saturated (six-way tie at 0.98) with no submission
endpoint. AEPC-QA is copyright-locked. INSEva has been "public soon" for 11 months. Vals AI has no
insurance vertical at all.

**D7. Target BFCL v4 (Berkeley Function-Calling Leaderboard) first.** *Why:* public data, public
board, pull-request submission, real headroom, and on-thesis — tool calling is the substrate an
underwriting agent runs on.

**D8. Abandon BFCL as the headline.** *Why, two reasons:* the board is frozen at Dec 2025 with **no
2026 frontier models on it** (no Fable 5, Opus 5, GPT-5.6 — the #1 is a nine-month-old Opus 4.5), and
the only category with a reachable gap was `simple_java`, one point behind a five-way tie. That claim
is five qualifiers deep and decided by 1–3 items out of 100 — not marketable, which Amol said
directly and correctly.

**D9. Target ParseBench (LlamaIndex, document parsing).** *Why:* the only option clearing all three
bars at once — a live current board (85 entries), genuinely self-serve submission (a pull request
adding `.eval_results/parsebench.yaml` to **your own** model repo, no gatekeeper), and deterministic
rule-based scoring with no LLM judge, so runs are cheap. Plus small specialists already lead it, and
**197 filenames / 384 documents of its corpus are insurance** — SERFF rate filings (the US System for
Electronic Rate and Form Filing), catastrophe loss models, P&C industry reports.

## Phase 3 — Methodology (the decisions that make the number defensible)

**D10. Matched evaluation settings, 3 runs, reported variance.** *Why:* an ICML 2026 paper by an
Amazon team (arXiv 2606.00135) showed BFCL scores move 6–15% from settings alone — system prompt,
multi-turn template, thinking-history retention, run-to-run noise — and every model on that board is
evaluated under its own settings. Being the team that reports variance is the differentiated position.

**D11. Parity gate as a hard kill gate before any training spend.** *Why:* if the harness cannot
reproduce a published score, every number it produces afterwards is meaningless. This decision paid
for itself repeatedly.

**D12. Measure improvements against our own reproduced baseline, never published rows.** *Why:* the
BFCL contamination finding (below) proved published rows contain artifacts. Claiming credit against
them would inflate our result by someone else's infrastructure failures.

**D13. Preregister the target and the fallback claim before the final run.** *Why:* it is what stops
a result reading as goalpost-moving.

**D14. Claim discipline: "#1 open-weight", never "#1 overall".** *Why:* LlamaIndex owns both the
benchmark and the leading entry (LlamaParse Agentic, 84.88). Saying so plainly is what makes the rest
credible.

## Phase 4 — Infrastructure

**D15. Rent Vast.ai on-demand H100 SXM 80GB — not 40GB, not interruptible.** *Why:* 80GB avoids
quantizing (which would confound a matched-settings comparison), leaves VRAM for the concurrency that
determines wall-clock, and fits larger candidate models. On-demand because a marketplace host dying
mid-run is a real probability.

**D16. Point GCP credits at a future training node, not at Track A.** *Why:* Google's trial credits
**cannot** buy GPUs at all, and GPU quota on a new project is zero and takes days to raise — useless
for same-day work. Track A cost $40–80 in cash instead.

**D17. Reject Hyperbolic.** *Why:* its price has risen above the market median (~$3.19/hr H100 vs
$2.29–3.12 median) and it is a multi-tenant marketplace — wrong quadrant.

**D18. Connect over an SSH tunnel, not the public port.** *Why:* Vast fronts every exposed port with
a Caddy proxy requiring HTTP Basic auth, while the harness's client can only send a Bearer token, and
the upstream checkout must not be patched. The tunnel also keeps the endpoint off the open internet.

**D19. Install a self-destruct watchdog **on the instance**.** *Why:* Amol's API key lacks the
two-factor privilege to manage instances, but each instance ships its own privileged key at
`/root/.vast_api_key`. The watchdog polls vLLM's monotonic request counter and destroys the box after
N idle minutes — which triggers correctly whether the run finishes, the Mac sleeps, the tunnel drops,
or the run crashes at 3am.

**D20. Destroy rather than stop.** *Why:* a stopped instance still bills for its 200GB disk; results
are written locally as the run progresses; weights re-download in ~4 minutes on a fast host.

**D21. Run the full 2,079-file corpus for parity, not the test slice.** *Why:* the 3-file slices
proved wildly unrepresentative — KDL's formatting read 32.24 on the slice versus 52.42 on the full
corpus.

## Phase 5 — Diagnosis

**D22. Read per-item failure records instead of trusting aggregate scores.** *Why:* this single habit
produced every real finding of the week. It is the same instinct as underwriting: audit the stated
number.

**D23. Run a second pipeline (Chandra-ocr-2) to test whether the parity gap was systematic.** *Why:*
the only way to separate "our bug" from "their environment". Answer: **not systematic** — Chandra
reproduced its published Charts score exactly and its formatting within 3.17, while KDL was 14.39 off.

**D24. Attack only Charts and Semantic Formatting.** *Why:* open-weight models have already reached
parity on the other three dimensions (gaps of 0.22, 0.01 and 2.30) — changes there risk regression
for no upside. The entire open-vs-closed gap is Charts (25.72) and Semantic Formatting (15.94).

**D25. License is not a selection criterion.** *Why:* Amol confirmed this workstream is
publication-only, never production. KDL's model is AGPL-3.0, which would be disqualifying for a
served product and is irrelevant here.

---

## The findings that came out of it

1. **BFCL's published leaderboard scores requests that never reached the model as wrong answers.**
   Our base model's published run lost **240 of 4,641 items (5.2%)** to `"Error during inference: The
   read operation timed out"`, which the scorer tried to parse as a function call. Four of the top 30
   models exceed 2%; Gemini-3-Pro-Preview (FC) loses 4.6%, and its 4.4-point deficit against its own
   Prompt-mode row is substantially an artifact. Corrected, our base model's multi-turn average rises
   from 34.75 to 41.68 and one category moves 15.8 points.
2. **A BFCL Java scoring defect:** correct Java (`new String[]{"a","b"}`) is scored wrong because the
   checker keeps escaped quotes when parsing array literals. 27 of 100 items fail for all four top
   models, capping the whole field at 67%.
3. **ParseBench's Tables dimension is 57.7% insurance** (290 of 503 files), and the leader scores
   **3.73 points worse** on insurance tables than on the rest — so insurance table extraction is both
   the biggest lever on that dimension and the work closest to the product.
4. **The ParseBench leader emits zero inline formatting markup** — no bold, underline, strikethrough,
   superscript or subscript across 23,802 elements — because its entire prompt set is five bare
   strings that never ask for any. Its formatting score comes solely through the heading arm of the
   bold matcher.
5. **Chart scoring defaults to an LLM judge** (Claude Haiku) unless an env var disables it,
   contradicting the README's claim of purely deterministic evaluation.

## Where the effort actually stands

| | Ours | Published | Gap |
|---|---:|---:|---:|
| Tables | 85.76 | 85.56 | +0.20 |
| Charts | 63.69 | 63.41 | +0.28 |
| Content Faithfulness | 87.18 | 87.19 | −0.01 |
| Semantic Formatting | 52.42 | 66.81 | **−14.39** |
| Visual Grounding | 74.19 | 78.84 | −4.65 |
| **Overall** | **72.65** | **76.36** | **−3.71** |

**The honest problem:** topping the board needs >76.36, and our reproduction of the leader is 72.65.
So 3.71 points must be recovered *before* any improvement counts, and the best measured patch is
+0.98. Either the missing 3.71 is found (an agent is measuring this now, GPU-free), or the claim
becomes "beats our reproduction of the leader" — which is contested, not clean.

## Mistakes made and corrected (the pattern worth remembering)

Called out by Amol directly: I was repeatedly confident and wrong where the ground truth was cheaply
checkable. Specifically — claimed the vLLM tool-call parser was the top risk (it is never invoked on
BFCL's path for that model); gave "50–60% odds" of topping BFCL from a half-remembered figure (real
gap: 36 points); called the formatting deficit a post-processing gap (it is a prompt gap); called
superscript the prize (naive wrapping corrupts Content Faithfulness); headlined underline as the gap
(underline is not a scored sub-type at all); compared Visual Grounding on the wrong metric (mAP
instead of the benchmark's own element pass rate); never defined "KDL" (KoreaDeepLearning) despite an
explicit instruction; and did not check the base model's license until asked.

Nine verification rules now live in `~/.claude/CLAUDE.md` as a result, and the correction pattern is
recorded in project memory.

## Total spend

Roughly **$4 of GPU** across two full 2,079-file corpus runs on rented H100s, plus web research.
Both boxes released themselves. No training has been run yet.
