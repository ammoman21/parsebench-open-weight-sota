# Sprint status ledger

**Purpose:** the single source of truth across sessions and agents. Any session working on this
sprint reads this file first and updates it when state changes. Chat context does not carry
between terminals; this file does.

Last updated: 2026-08-10 (orchestrator session)

---

## Objective
Score at or above the top of the Berkeley Function-Calling Leaderboard (BFCL) v4 under matched
evaluation settings, using a post-trained small open-weight model. See `TRACK_B_CONTRACT.md`
for the dataset spec and `CLAUDE.md` for the rules every agent obeys.

## Track status

| Track | What it is | State | Blocked on |
|---|---|---|---|
| A | Eval harness + baselines + parity gate | Pipeline live (Mac → SSH tunnel → vLLM on H100). Smoke test `simple_python` **95.42% ± 0.38pp** over 3 runs. **`parallel` discrepancy RESOLVED 2026-08-11 — our harness is correct.** The published `qwen3-14b-FC` run has **240 of 4,641 items (5.2%) that never received a model response** (`"Error during inference: The read operation timed out"`), scored as wrong answers; 16.5% of `parallel` items. Timeout-corrected published parallel = 95.8% vs our 93.50%. Comparison runs: opus 0.1%, glm-4.6 0.0%, Qwen3-8B 0.7%, xLAM-2-8b 1.1%. Full evidence in `reports/track_a_parity.md`. Remaining: sweep runs 2–3. | SerpAPI key (blocks 2 of 23 categories) |
| B | Synthetic dataset factory (9 components, 4 waves) | Contract v0.2 drafted, awaiting Amol's approval to freeze | Amol's go |
| C | Training (supervised fine-tune, then reinforcement learning) | Not started; configs writable before GPU exists | Track A parity gate, Track B dataset |
| D | Credibility & release (prereg, matched-settings matrix, writeup) | Not started; prereg draftable now | nothing |

## Done so far
- `gorilla/` upstream checkout pinned; BFCL harness installed in `.venv` (Python 3.12) and CLI verified.
- Benchmark structure read directly from its data files: 23 test categories confirmed; record
  shapes, answer-key conventions (multiple acceptable values per argument), multi-turn
  answer-as-list-of-call-lists, and `_load_scenario` environment interface all documented in
  the contract §3.
- Confirmed the harness can point at an external model server via `--skip-server-setup` plus
  `LOCAL_SERVER_ENDPOINT` / `LOCAL_SERVER_PORT`, and that it applies chat templates itself
  (which is what makes matched-settings evaluation auditable).
- `CLAUDE.md` (agent rules) and `TRACK_B_CONTRACT.md` (dataset spec, v0.2) written.

## Open external dependencies (Amol's hands)
- [ ] **SerpAPI key** (~$75 tier) — two `web_search_*` categories cannot run without it. Goes in `.env` as `SERPAPI_API_KEY`.
- [ ] **GCP**: confirm credit type (trial credits cannot be used for GPUs; startup-program credits can), then GPU quota request. `gcloud auth login` must be run by Amol.
- [ ] **Together AI credits**: confirm scope (do they cover GPU clusters, or only serverless + fine-tuning?) and whether fine-tuned weights are downloadable.
- [ ] **Chrome extension** for browser control, if console work is wanted (currently not connected).

## Decisions made (do not relitigate without an amendment)
- Target is BFCL v4, chosen over INS-ActBench (dataset not downloadable) and weather
  benchmarks (months, wrong discipline).
- Adversarial generator/solver loop is **out of scope** for this sprint; replaced by
  difficulty-band filtering + adversarial augmentation on gold-preserving axes (contract §6.3, §6.4).
- Teacher model must be MIT/Apache-licensed (DeepSeek/Qwen). Never OpenAI or Anthropic outputs.
- Claims are made under matched evaluation settings with 3 seeds and reported variance, because
  the Amazon brittleness paper (arXiv 2606.00135) showed settings move scores 6–15%.
- **REVISED TARGET (2026-08-11), based on the official `data_overall.csv` for the 2025-12-16
  snapshot.** Topping the overall leaderboard is NOT the goal and is not achievable at 14B:
  #1 is Claude-Opus-4-5 (FC) at 77.47%; our base `Qwen3-14B (FC)` is 41.03% (rank 43/108).
  The gap lives almost entirely in three agentic categories — Web Search 10.00%, Memory 19.57%,
  Multi-Turn 34.75% — versus Opus at 84.50 / 73.76 / 68.38. Decisive evidence: purpose-built
  function-calling specialists don't top this board either. `xLAM-2-32b` is the best specialist
  at 54.66% overall (rank 18) and `xLAM-2-70b` reaches only 53.07%, despite the latter holding
  the **best multi-turn score on the entire board (77.38%)** — its Web Search (15.00%) and
  Memory (14.41%) sink the aggregate. Specialization buys multi-turn; it does not buy the broad
  knowledge and multi-hop retrieval that web search and memory require.
  **AMENDED 2026-08-11 — the baseline numbers in the paragraph above are contaminated.** The
  published `qwen3-14b-FC` run dropped 5.2% of all items to inference timeouts and scored them as
  wrong answers. Corrected baselines (correct ÷ items actually attempted): multi_turn_base 51.3%
  (not 39.00), long_context 40.9% (not 32.50), miss_func 41.5% (not 34.00), web_search_base 16.0%
  (not 8.00), parallel 95.8% (not 80.00). Multi-turn average ≈42.2%, not 34.75%. The gap to first
  place is therefore ~30 points, not 36 (the leader's run is clean at 0.1%). **All improvement
  claims must be measured against our own clean baseline, never the published rows** — otherwise
  ~7.5 points of "our" multi-turn gain would actually be someone else's dropped requests.
  Claims we pursue instead, in priority order:
  1. **Multi-turn state of the art, or beating Claude Opus 4.5 (68.38%) on multi-turn.**
     Demonstrated feasible: `xLAM-2-8b-fc-r` scores 70.00% multi-turn at *8B*. Our base is 34.75%.
  2. **Best commercially-licensed model under ~20B overall.** xLAM and ToolACE are cc-by-nc
     (non-commercial); the Apache-2.0 bar under 20B is `BitAgent-Bounty-8B` at 46.23%.
  3. **Lowest format-sensitivity delta on the board.** The leaderboard now reports this column;
     `Qwen3-14B (Prompt)` swings **14.0 points**. Training robustness (contract §6.2, B7) targets
     a number nobody else optimizes, and it is the property an autonomous agent actually needs.

## Dated notes

### 2026-08-11 — Track A: pipeline live, smoke test passed
- Vast instance `47425997` (machine 36444807) serving `Qwen/Qwen3-14B` on 1x H100 80GB.
- **The instance did not boot with the arguments the handoff specified.** It came up on the
  template's defaults: `--tool-call-parser qwen3_coder` (not `hermes`) and `--max-num-seqs 8`
  (not 32). Both were corrected before any real run.
- **CORRECTION — the tool-call parser does not affect BFCL scores for this model.** An earlier
  version of this note claimed the `qwen3_coder` default was the silent score-killer that
  `TRACK_A_HANDOFF.md` §6 warns about. That is wrong, and the handoff's §6 is misleading on this
  point. `QwenFCHandler` renders its own prompt (tools inside `<tools>` XML tags) and calls
  `client.completions.create` — the **raw completions endpoint** — then extracts `<tool_call>`
  blocks from the returned text itself. It never sends a `tools=` parameter. vLLM's
  `--tool-call-parser` and `--enable-auto-tool-choice` apply only to `/v1/chat/completions` with
  `tools`, so they are **never invoked on BFCL's path for this model**. Verified at
  `bfcl_eval/model_handler/local_inference/qwen_fc.py` and `base_oss_handler.py:317`
  (`# We use the OpenAI Completions API`). The `--max-num-seqs 8 → 32` change did buy real
  throughput; the parser change bought nothing measurable here. It still matters for any
  chat-completions work, and for `-FC` handlers that do send `tools=` (e.g. `falcon_fc`).
- **`supervisorctl restart vllm` is not trustworthy on this image.** It reported success but
  orphaned the running engine, which kept serving the old arguments while holding the port and
  72 GB of GPU. The replacement died with `Address already in use`; supervisor showed `EXITED`
  while the stale server answered health checks with HTTP 200. Always verify a restart by
  reading `/proc/<pid>/cmdline` and confirming GPU memory hit 0 between stop and start.
- **The public port is unusable by the harness.** Vast fronts every exposed port with a Caddy
  proxy requiring HTTP Basic auth; the harness's OpenAI client can only send a Bearer token.
  We connect over an SSH tunnel to the container's `127.0.0.1:18000` instead (`open_tunnel.sh`).
  This also keeps the model endpoint off the open internet.
- **No seed flag exists** in `bfcl generate` — only `--temperature` (default 0.001). "3 seeds"
  must therefore be reported as 3 independent runs measuring batching-induced variance, not as
  seeded replication. This needs to be stated plainly in the writeup.
- Results are written to `bfcl_runs/` via `BFCL_PROJECT_ROOT`; by default the harness would
  write them **inside `gorilla/`**, violating rule 5.
- Smoke test: `simple_python` = **95.00%**, above the 80–90% expected band.

## How to coordinate
- **Files, not chat.** `CLAUDE.md` (auto-loaded), `TRACK_B_CONTRACT.md` (spec), this file (state).
- Any new terminal session: start it in `bfcl-sprint/`, and it picks up the rules automatically.
- Update the tables above when a gate passes or a blocker clears. Append, don't rewrite history.

### 2026-08-11 — Insurance benchmark survey: no toppable target exists

Verified survey of every insurance/underwriting/actuarial LLM benchmark. **None is toppable**, and
not because they're hard — the sparse ones have no submission mechanism and the live ones are
saturated *and* closed:

| Benchmark | Data public? | Live board? | Leader | External submissions? |
|---|---|---|---|---|
| INS-ActBench (Fudan) | **No** — repo has 3 commits, 0 releases, no data files; HF request from HuggingFace staff open 2wks unanswered | No | — | No |
| InsureBench | No | **No** — "Scores pending, opening 2026", placeholder chart | — | Unknown (email only) |
| SnorkelUnderwrite | Traces only (380 + 1,800, Apache-2.0); **environment not released** | **Archived** | GPT-5.4 91% | No — all 33 entries Snorkel's own runs |
| ActuBench MCQ | Yes — incl. answers via undocumented `/api/items.csv` | Yes, 54 entries | **6-way tie 0.98** | No endpoint |
| ActuBench Judge | Yes | Yes, 53 entries | opus-4-7 0.89 | No endpoint |
| INSEva (Ant Group) | No — "public soon" for 11 months | No | — | No |
| INS-MMBench | Yes (1.5GB) | No | — | vision benchmark, no board |
| ActuarialMathBench | Yes (MIT, 750 SOA items) | No | 3 models | known data errors in FAM-L |
| AEPC-QA | **No** — copyright-restricted | No | o3 78.68% | No |
| Vals AI | n/a | Yes | — | **no insurance vertical at all** |

**The opening found instead: Agents' Last Exam (UC Berkeley RDI × Snorkel), arXiv 2606.05405.**
938 stars, repo updated 2026-08-11, Apache-2.0 code / CC BY 4.0 data, real "Top Submissions"
leaderboard (36+ entries), **top score only 30.6% pass** — huge headroom. Tasks are mapped to
O*NET/SOC occupational codes; 300+ experts from 44 institutions. **Verified: zero insurance tasks.**
`tasks/published_tasks.json` has no matches for insur/underwrit/actuar/claim/premium, and all 23
`tasks/business_finance/` entries are options pricing, Basel, equity research, PE, SEC filings,
tax — no insurance. Submissions accepted via a verifiability decision tree, with **monetary awards
for high-impact contributions**.

Funding leads: **Snorkel Open Benchmarks Grants** ($3M, rolling, no deadline,
benchmarks.snorkel.ai/apply — credits/compute/engineering not cash; first cohort all coding/agent,
zero insurance). **CAS AI Working Group RFP**, up to **$40,000 cash** for "Adapting LLMs for
Specialized P&C Actuarial Reasoning" — **deadline passed April 27 2026**, worth asking about a
second round (esmith@casact.org, hdavis@casact.org).

### 2026-08-11 — TARGET CHANGED to ParseBench; GPU box repurposed

**Decision:** BFCL is no longer the headline target. Reason: `simple_java` (the only category with a
reachable gap — ours 66.00 vs a five-way tie at 67.00) is five qualifiers deep and decided by 1–3
items out of 100, i.e. not a marketable claim. The board is also frozen at 2025-12 with no 2026
frontier models on it (no Fable 5, no Opus 5, no GPT-5.6). **BFCL work is retained only as the
timeout-contamination finding**, which needs no further GPU.

**New target: `ParseBench` (LlamaIndex).** See `PARSEBENCH_PLAN.md`. Live board, 85 entries,
self-serve submission (a PR adding `.eval_results/parsebench.yaml` to your own model repo),
deterministic rule-based scoring with no LLM judge, and **197 of 2,113 corpus files are insurance**
(California/Texas/Interstate SERFF rate filings, catastrophe loss modeling, P&C industry reports).
Number to beat for #1 open-weight: **76.36** (`KDL-Frontier-Parser-nano`). Anthropic Fable 5 is on
this board at 70.78, so topping open-weight also beats Fable 5, Gemini 3 Flash (75.05) and Reducto.

**Box repurposed (instance 47425997).** Now serving `KDLAI/KDL-Frontier-Parser-nano` — the current
open-weight leader — instead of `Qwen/Qwen3-14B`.
- **The BFCL config is backed up at `/etc/environment.bfcl.bak` on the instance.** To restore BFCL,
  copy it back over `/etc/environment` and restart `vllm`.
- Per the image's own agent guide (`/etc/vast-agents-guide.md`), a runtime model change requires
  setting **both** `VLLM_MODEL` and `MODEL_NAME` in `/etc/environment`; the boot-time linking
  between them does not re-run on `supervisorctl restart`. JSON-valued flags go in
  `/etc/vllm-args.conf`, not `VLLM_ARGS`.

**Three operational findings worth keeping:**
1. **The orphaned-engine mystery from the earlier note is solved.** `supervisorctl stop vllm`
   leaves a separate process named **`VLLM::EngineCore`** holding all GPU memory, and its command
   line contains no `vllm serve` string — so `pkill -f "vllm serve"` misses it. Reliable teardown:
   `for p in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader); do kill -9 $p; done`.
   GPU went 77 GB → 0 in 4 seconds once targeted correctly.
2. **Pipeline naming trap in ParseBench:** `mineru2605pro_vllm` is *not* OpenAI-compatible despite
   the name — it POSTs `{"image_base64": ...}` to a custom `/predict` endpoint returning
   `{markdown, blocks, ...}`, which needs MinerU's own wrapper server. The genuinely
   OpenAI-compatible parse providers are `kdl_frontier_nano`, `infinity_parser2`, `chandra2`,
   `paddleocr`, `qwen3_5`, `gemma4`, `dots_ocr`, `granite_vision`, `nemotron_omni`.
3. **Both MinerU and KDL cap at `max_position_embeddings=8192`** — a larger `--max-model-len` is
   rejected outright at startup with a pydantic `ValidationError`.

**Big break:** `src/parse_bench/inference/providers/parse/kdl_frontier_nano.py` **ships the
leader's entire pipeline vendored into the repo**, with exact serve flags in its docstring —
*"a 2-stage multi-region pipeline (layout detection → per-region crop → per-category recognition)
against ONE vLLM OpenAI-compatible endpoint serving the public 1.2B weights, followed by
deterministic rule-based post-processing."* The state of the art is readable, runnable, and
modifiable rather than something to reverse-engineer.

**Test-slice results (3 files/dimension) for the leader, confirming where the headroom is:**
Content Faithfulness 0.958 · Table 0.631 GriTS · Layout 0.431 mAP · **Charts 0.500** ·
**Semantic Formatting 0.322, with underline 0.00 and strikethrough 0.00.** Even the best
open-weight model on the board drops those markers entirely — a post-processing gap, not a vision
one. Board-level headroom confirms it: open-weight is already at parity on Content Faithfulness
(gap 0.22), Visual Grounding (0.01) and Tables (2.30), and the whole open-vs-closed gap sits in
**Charts (25.72)** and **Semantic Formatting (15.94)**.

**In flight:** full ~2,000-page parity run of `kdl_frontier_nano` against the published 76.36.
Script `parsebench/run_parity.sh`, log `parsebench/parity_run.log`. Local setup: repo at
`bfcl-sprint/parsebench/`, `uv` installed, deps synced, `pdf2image` added, tunnel unchanged on
`127.0.0.1:18000`.

### 2026-08-11 — CONSTRAINT: publication only, not production

Amol: benchmark work is **for publishing a SOTA result only; nothing goes to prod.** Therefore
**license is not a selection criterion** for this workstream. `KDLAI/KDL-Frontier-Parser-nano`
is **AGPL-3.0** (KDL = KoreaDeepLearning, a Korean AI company) — fine under this constraint, though
it would be disqualifying for a served product. Same for cc-by-nc entries like xLAM/ToolACE.
Pick the strongest base, full stop.
