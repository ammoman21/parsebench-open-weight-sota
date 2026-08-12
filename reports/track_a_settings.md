# Track A — recorded evaluation settings

Required by `TRACK_A_HANDOFF.md` §7. Without these the numbers are not defensible.
Every value below was read off the running system, not copied from the plan — the plan
and reality diverged (see "Intended vs actual" below).

Last updated: 2026-08-11 (Track A session)

## Serving stack (as verified live, not as configured)

| Setting | Value | How verified |
|---|---|---|
| Model id | `Qwen/Qwen3-14B` | `/v1/models` response |
| Serving engine | vLLM, image `vastai/vllm:v0.27.0-cuda-13.0` | instance template |
| `--tool-call-parser` | `hermes` | `/proc/<pid>/cmdline` of the live engine |
| `--reasoning-parser` | `qwen3` | same |
| `--max-model-len` | 32000 | same, and `/v1/models` |
| `--max-num-seqs` | 32 | same |
| `--tensor-parallel-size` | 1 | same |
| vLLM API key | none set | unauthenticated `curl` returned HTTP 200 |
| Hardware | 1x NVIDIA H100 80GB HBM3 | `nvidia-smi` |

## Harness

| Setting | Value |
|---|---|
| Harness commit | `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` (working tree clean) |
| Handler flavor | `Qwen/Qwen3-14B-FC` (native function-calling) and `Qwen/Qwen3-14B` (prompt-parsing) |
| `--temperature` | 0.001 (the harness default) |
| `--num-threads` | 16 (client-side concurrency; fixed across all runs so batch composition is comparable) |
| `BFCL_PROJECT_ROOT` | `bfcl-sprint/bfcl_runs` — keeps results out of `gorilla/` |

## Connection topology

The Mac reaches the model through an SSH tunnel, NOT the public port:

    Mac localhost:18000  --ssh port 311-->  container 127.0.0.1:18000 (vLLM)

The instance's public port 31624 maps to container port 8000, which is a **Caddy**
reverse proxy requiring HTTP Basic authentication. The BFCL harness builds its client
as `OpenAI(base_url, api_key)` and can only send a Bearer token, so it cannot satisfy
Caddy. The tunnel bypasses Caddy and additionally keeps the model endpoint off the
open internet.

## Seeds / run-to-run variance

**There is no seed flag.** `bfcl generate --help` exposes `--temperature` and no seed
option; confirmed by inspection. So "3 seeds" cannot mean seeded sampling. What we
measure instead is run-to-run variance: at temperature 0.001 sampling is near-greedy,
but vLLM's continuous batching makes results mildly nondeterministic because floating
point reduction order depends on which requests are batched together, and in
multi-turn categories an early divergence compounds. Three full independent runs;
report mean and standard deviation. This must be stated plainly in the writeup rather
than implying seeded replication.

## Measured run-to-run variance (the answer to the "seeds" question)

Three independent runs of `simple_python`, identical settings, no seed involved:

| Run | Accuracy | Note |
|---|---|---|
| smoke 1 | 95.00% | raw output deleted during run-directory restructuring |
| smoke 2 | 95.50% | raw output deleted during run-directory restructuring |
| sweep run 1 | 95.75% | raw output retained in `bfcl_runs/run1/` |

Mean **95.42%**, standard deviation **0.38 percentage points**, range 0.75pp.

Only the third run's raw output still exists; the first two survive as the figures
above, recorded here so they are not lost, but they cannot be re-derived. Sweep runs 2
and 3 will produce a fully reproducible three-run set.

0.38pp is a **floor**, not a typical value: `simple_python` is single-turn, so there is
no error compounding. Multi-turn categories chain several model calls where an early
divergence changes everything downstream, and the handoff's section 6 expects roughly
3% there. Do not quote the single-turn figure as the benchmark-wide variance.

## Intended vs actual (why this file exists)

The instance did **not** come up with the arguments the handoff specified. The
template's own defaults were in force until corrected:

| Setting | Handoff intended | Actually running at boot |
|---|---|---|
| `--tool-call-parser` | `hermes` | `qwen3_coder` |
| `--max-num-seqs` | 32 | 8 |
| bind address | `0.0.0.0:8000` | `127.0.0.1:18000` |
| `--api-key` | `sprint-key` | none |

The parser row is the dangerous one, and is exactly the failure the handoff's §6 names
as highest risk: `qwen3_coder` targets Qwen3-**Coder** models, and against plain Qwen3
it fails to parse tool calls silently — scores collapse toward zero while every log
looks healthy. Corrected by editing `VLLM_ARGS` in the instance's `/etc/environment`
(backup at `/etc/environment.bak.trackA`) and restarting the service.

**Restarting has a trap worth recording.** `supervisorctl restart vllm` reported
success but orphaned the running engine, which kept serving on the old arguments while
holding port 18000 and 72 GB of GPU memory. The replacement process died with
`OSError: [Errno 98] Address already in use`, supervisor sat in `EXITED`, and the stale
server continued answering health checks with HTTP 200. A naive readiness poll passes
against the wrong configuration. **Verify a restart by reading `/proc/<pid>/cmdline`
for the actual flags and confirming GPU memory dropped to 0 between stop and start —
an HTTP 200 from `/v1/models` proves nothing about which configuration answered.**

## Instance

Vast.ai instance `47425997` on machine `36444807`, $3/hr, Washington US.
Weights cached at `/workspace/models`, so a restart reloads in ~45s rather than
re-downloading. **Destroy when idle — do not merely stop** (a stopped instance still
bills for its 200 GB disk).
