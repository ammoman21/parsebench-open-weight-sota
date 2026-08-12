# Track A handoff — evaluation harness, baselines, parity gate

**For a fresh Claude Code session.** Start it in `~/forecasting_networks/bfcl-sprint/` so
`CLAUDE.md` (the rules) loads automatically. Read `STATUS.md` for cross-track state. Written
2026-08-10 by the orchestrator session, which is concurrently running Track B (dataset build).

---

## 0. Read first
- `CLAUDE.md` — hard rules. The relevant ones here: never tune against or inspect real
  benchmark scores outside a pre-registered run; never modify anything under `gorilla/`;
  never invent results; define every acronym in plain language in reports.
- `STATUS.md` — what's done across all four tracks, and the decisions already settled.
- `TRACK_B_CONTRACT.md` — only needed for context on what the training data will look like.

## 1. What Track A is for

Produce trustworthy baseline numbers on the Berkeley Function-Calling Leaderboard (BFCL) v4,
under evaluation settings we control and disclose. Two purposes:

1. **The parity gate** — prove our harness reproduces a published score. Until this passes,
   every downstream number in the sprint is meaningless. This is the sprint's kill gate.
2. **Per-category baseline gaps** — which of the 23 categories the base model is weakest at.
   This is the one input Track B needs from Track A (it tunes the dataset mix at assembly time,
   contract §6.3 "failure-driven top-up").

Context for why settings discipline matters: an ICML 2026 paper by an Amazon team
(arXiv 2606.00135) showed BFCL scores move **6–8% from the multi-turn template choice, 2–5%
from whether the model's thinking history is retained, up to ~3% from run-to-run variance, and
a system-prompt edit can produce a gain larger than reinforcement-learning training does.**
Every model on the public leaderboard is evaluated under its own settings, so bare score
comparisons are near-meaningless. Our differentiator is that ours will be matched and measured.

## 2. Environment (already built and verified)

```
~/forecasting_networks/bfcl-sprint/
  .venv/                  Python 3.12 (system default 3.14 is too new for the pinned numpy)
  gorilla/                pinned upstream checkout — DO NOT MODIFY
    berkeley-function-call-leaderboard/    the harness, installed editable into .venv
  CLAUDE.md  STATUS.md  TRACK_B_CONTRACT.md  TRACK_A_HANDOFF.md
```

Verified already: the CLI works (`.venv/bin/bfcl --help`); 23 test categories are listed by
`.venv/bin/bfcl test-categories`; handlers exist for `Qwen/Qwen3-14B-FC` (native
function-calling flavor) and `Qwen/Qwen3-14B` (prompt-parsing flavor); **the harness has no
vLLM dependency of its own** — it talks to a model server over HTTP using the `openai` client,
so everything runs from the Mac. One undeclared dependency (`soundfile`) was already patched in.

There is no Qwen3.5 handler — only Qwen3. Serving a model without a handler is a dead end.

## 3. The rented machine (booked 2026-08-10)

Vast.ai machine **#36444807**, 1× H100 SXM 80GB, Washington US, $3/hr, on-demand.
Specs that matter: 2,892 GB/s memory bandwidth, 1,449 GB disk, 2,620 Mbps down, CUDA 13.0,
99.86% reliability.

Template configuration used:
- Image `vastai/vllm:v0.27.0-cuda-13.0`, launch mode `jupyter` (gives a browser terminal)
- Disk 200 GB, **no local volume** (a 32 GB volume at `/workspace` would have starved the
  model download — `VLLM_ARGS` sends weights to `/workspace/models`)
- `VLLM_MODEL=Qwen/Qwen3-14B`
- `VLLM_ARGS=--max-num-seqs 32 --max-model-len 32000 --enable-auto-tool-choice
  --tool-call-parser hermes --reasoning-parser qwen3 --download-dir /workspace/models
  --host 0.0.0.0 --port 8000 --api-key sprint-key`

Why those args are what they are: `--host 0.0.0.0` because the template's default
`127.0.0.1` binds inside the container only and the Mac cannot reach it; `--api-key` because
the port is internet-exposed and an open GPU endpoint gets abused; `--max-num-seqs 32` (up
from 8) because eval wall-clock is dominated by how many benchmark items run concurrently.

## 4. Connect and smoke-test

```bash
cd ~/forecasting_networks/bfcl-sprint
# from the Vast instance card: public IP + the EXTERNAL port mapped to internal 8000
curl http://<IP>:<EXT_PORT>/v1/models -H "Authorization: Bearer sprint-key"
```
Expect a JSON list containing `Qwen/Qwen3-14B`. Hanging → host bind wrong. 401 → api-key wrong.

```bash
export LOCAL_SERVER_ENDPOINT=<IP>
export LOCAL_SERVER_PORT=<EXT_PORT>
./.venv/bin/bfcl generate --model Qwen/Qwen3-14B-FC \
  --test-category simple_python --skip-server-setup --num-threads 8
./.venv/bin/bfcl evaluate --model Qwen/Qwen3-14B-FC --test-category simple_python
```
Expect roughly 80–90%. **A near-zero score here almost certainly means the tool-call parser is
wrong, not that the model is bad** — see §6.

## 4b. Pre-flight checks (do these before any real run)

> **CORRECTION 2026-08-11 — this section was wrong about the parser being the top risk.**
> Verified by the Track A session: `QwenFCHandler` renders its own prompt (tools inside `<tools>`
> XML tags), calls the **raw `/v1/completions` endpoint**, and extracts `<tool_call>` blocks from
> the returned text itself. It never sends a `tools=` parameter. vLLM's `--tool-call-parser` and
> `--enable-auto-tool-choice` only apply to `/v1/chat/completions` requests carrying `tools`, so
> **they are never invoked on BFCL's path for this model.** See `bfcl_eval/model_handler/
> local_inference/qwen_fc.py` and `base_oss_handler.py:317`. The check below is still a useful
> 30-second sanity test of the server, and the parser still matters for `-FC` handlers that do
> send `tools=` (e.g. `falcon_fc`) and for any chat-completions work — but it is not the
> score-killer this section claimed. The real unresolved risk is the `parallel` category
> discrepancy in `reports/track_a_parity.md`.

**(i) Parser check — 30 seconds, ~$0.001.** Ask the server directly and read the raw output:

```bash
curl -s http://<IP>:<EXT_PORT>/v1/chat/completions \
  -H "Authorization: Bearer sprint-key" -H "Content-Type: application/json" -d '{
  "model":"Qwen/Qwen3-14B",
  "messages":[{"role":"user","content":"What is the area of a triangle with base 10 and height 5?"}],
  "tools":[{"type":"function","function":{"name":"calculate_triangle_area",
    "description":"Calculate the area of a triangle given its base and height.",
    "parameters":{"type":"object","properties":{
      "base":{"type":"integer","description":"The base."},
      "height":{"type":"integer","description":"The height."}},
      "required":["base","height"]}}}]}' | python3 -m json.tool
```
- `tool_calls` populated → parser is correct, proceed.
- `tool_calls` null **and** `content` contains `<tool_call>{...}</tool_call>` → the parser isn't
  firing. `hermes` is the right choice (verified: Qwen3-14B's chat template instructs it to emit
  exactly that format, and contains no `function=`/`parameter=` markers, so the template default
  `qwen3_coder` would silently produce zero scores). Check flag spelling, restart, retry.
- `content` shows some *other* notation → match the parser to what you actually observe.
- Nothing works → use the prompt-flavor handler, which parses client-side and ignores this flag.

Iteration is cheap: after first boot the weights are cached on disk, so a vLLM restart is
~1–2 minutes and ~$0.10. Trying every plausible parser costs under $1 and under 15 minutes.

**(ii) Context-length check — the biggest open flag.** `--max-model-len 32000` may be too small.
The padding module `eval_checker/multi_turn_eval/func_source_code/long_context.py` holds
**~47,600 tokens** of filler material; a single `multi_turn_long_context` item uses a subset, but
combined with function docs (up to ~4,400 tokens for `vehicle_control`) plus accumulated
conversation it can approach or exceed 32k. Complication: **Qwen3-14B's native context is 32,768
tokens** — exceeding it requires YaRN rope scaling, which mildly degrades short-context quality
and is therefore a declared settings choice, not a free fix.

Action: run **one** `multi_turn_long_context` item with `--include-input-log`, then measure the
actual prompt token count from the log. Set `--max-model-len` above the observed maximum, and if
that exceeds 32,768, decide explicitly between rope scaling and accepting truncation — and record
the decision in the preregistration.

**(iii) Thinking mode.** Unlike the 4B (which has explicit `qwen3-4b-think-FC` /
`qwen3-4b-nothink-FC` handlers), Qwen3-14B has only one handler pair, so thinking follows the
chat template's default — which for this model is **on**. That is the dominant driver of eval
wall-clock, since every turn generates a reasoning trace before its answer. Keep it on for the
pre-registered runs (it is how the model is designed to be used, and thinking-history retention
was worth 2–5% in arXiv 2606.00135), but consider disabling it for cheap iteration. Either way,
declare it.

## 5. The work, in order

1. **Smoke test** (above) — plumbing only.
2. **Parity gate.** Pick a model already on the public BFCL leaderboard that we can serve or
   call, run it through this harness, and compare to its published score. Pass condition:
   within the run-to-run noise band (≈3% on multi-turn, tighter on single-turn) across 3 runs.
   **If this fails, stop the sprint and report — do not proceed to training.**
3. **Baselines.** `Qwen/Qwen3-14B-FC` across all scored categories, 3 independent runs.
   Then the same for `Qwen/Qwen3-14B` (prompt flavor) — the FC-versus-prompt comparison is
   itself one of the settings axes we report.
4. **Per-category gap table.** Write it to `reports/track_a_baselines.md`: category × mean
   score × standard deviation across runs. This is the artifact Track B consumes.
5. **Optional if time and budget allow:** `Qwen/Qwen3-30B-A3B-Instruct-2507` on the same box
   (it fits in 80 GB) so we know whether the bigger base is worth training instead.

Run **category by category, not one monolithic pass** — cheap insurance against losing hours
if the instance dies mid-run. Results are written client-side on the Mac, so nothing is lost
from the pod itself.

## 6. Known risks, with symptoms

- **Tool-call parser mismatch (highest risk).** `--tool-call-parser` tells vLLM how to turn
  raw model output into structured calls. If it's wrong, calls silently fail to parse: scores
  collapse toward zero while every log looks healthy. `hermes` is the starting choice for
  plain Qwen3; `qwen3_coder` is the template default but is meant for Qwen3-Coder models.
  Escape hatch: the prompt-flavor handler (`Qwen/Qwen3-14B`, no `-FC`) bypasses server-side
  parsing entirely and lets the harness parse text itself.
- **Web-search categories need a paid key.** `web_search_base` and `web_search_no_snippet`
  call SerpAPI (a commercial Google-search API). Set `SERPAPI_API_KEY` in the harness `.env`.
  **Not yet purchased** — those two categories cannot run until it is. Budget ~$75/tier;
  a full 3-run sweep may exceed 5,000 searches.
- **How to vary "seeds" is an open question.** `bfcl generate` defaults to temperature 0.001
  (near-deterministic), and it is not yet confirmed whether a seed flag is exposed. In practice
  what we need to measure is **run-to-run variance**: vLLM's continuous batching makes results
  mildly nondeterministic depending on batch composition, and multi-turn error compounding
  amplifies it. So: three full independent runs, report mean and standard deviation. Determine
  and document the actual mechanism before the pre-registered final runs.
- **Cost discipline.** $3/hr. **Destroy the instance when idle — do not merely stop it**
  (a stopped instance still bills for 200 GB of storage). Weights re-download in ~4 minutes on
  this host, and the template makes boot-to-serving unattended.

## 7. Settings to record for every run (feeds the preregistration in Track D)

Model id, vLLM image tag, handler flavor (`-FC` vs prompt), `--tool-call-parser`,
`--reasoning-parser`, `--max-model-len`, `--max-num-seqs`, `--temperature`, `--num-threads`,
harness git commit hash, date, and per-category scores for each of the 3 runs. Without these
the numbers are not defensible — that is the entire lesson of arXiv 2606.00135.

## 8. Report back
Append findings to `STATUS.md` (Track A row + a dated note) and write the detailed table to
`reports/track_a_baselines.md`. Flag the parity-gate outcome prominently — the other tracks
are gated on it.
