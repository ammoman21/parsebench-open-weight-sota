#!/bin/bash
# Run one full independent pass over the BFCL categories, one category at a time.
#
# Category-by-category rather than a single monolithic pass: if the rented instance
# dies mid-sweep we lose one category, not hours. Results are written client-side on
# the Mac, so nothing is lost from the pod itself.
#
# Usage:  ./run_sweep.sh <run_number> [model]
#   e.g.  ./run_sweep.sh 1 Qwen/Qwen3-14B-FC
#
# Each run writes to bfcl_runs/run<N>/ so the three independent runs stay isolated
# and can be compared for run-to-run variance (there is no seed flag in the harness;
# variance comes from vLLM's continuous batching, so runs must be kept separate).

set -uo pipefail

RUN="${1:?usage: ./run_sweep.sh <run_number> [model]}"
MODEL="${2:-Qwen/Qwen3-14B-FC}"
ROOT="$HOME/forecasting_networks/bfcl-sprint"

export BFCL_PROJECT_ROOT="$ROOT/bfcl_runs/run${RUN}"
export LOCAL_SERVER_ENDPOINT=localhost
export LOCAL_SERVER_PORT=18000
export REMOTE_OPENAI_API_KEY=EMPTY

mkdir -p "$BFCL_PROJECT_ROOT"
LOG="$ROOT/bfcl_runs/sweep_run${RUN}_$(echo "$MODEL" | tr '/' '_').log"

# The 23 scored categories, cheapest first so the gap table fills in early and a
# mid-sweep failure costs the least. web_search_base and web_search_no_snippet are
# deliberately EXCLUDED: they call SerpAPI (a commercial Google-search API) and the
# key has not been purchased. They must be added once SERPAPI_API_KEY exists.
CATEGORIES=(
  simple_python simple_java simple_javascript
  multiple parallel parallel_multiple irrelevance
  live_simple live_multiple live_parallel live_parallel_multiple
  live_irrelevance live_relevance
  format_sensitivity
  memory_kv memory_vector memory_rec_sum
  multi_turn_base multi_turn_miss_func multi_turn_miss_param multi_turn_long_context
)

echo "=== sweep run ${RUN} | model ${MODEL} | started $(date) ===" | tee -a "$LOG"
echo "EXCLUDED: web_search_base, web_search_no_snippet (no SERPAPI_API_KEY)" | tee -a "$LOG"

for cat in "${CATEGORIES[@]}"; do
  echo "--- ${cat} : generating ---" | tee -a "$LOG"
  START=$(date +%s)
  if ! "$ROOT/.venv/bin/bfcl" generate --model "$MODEL" --test-category "$cat" \
        --skip-server-setup --num-threads 16 >> "$LOG" 2>&1; then
    echo "!!! ${cat} GENERATE FAILED (continuing)" | tee -a "$LOG"
    continue
  fi
  GEN_SECS=$(( $(date +%s) - START ))

  SCORE=$("$ROOT/.venv/bin/bfcl" evaluate --model "$MODEL" --test-category "$cat" 2>&1 \
            | grep -oE "Accuracy: [0-9.]+%" | head -1)
  echo "=== ${cat} | ${SCORE:-NO_SCORE} | generate ${GEN_SECS}s ===" | tee -a "$LOG"
done

echo "=== sweep run ${RUN} finished $(date) ===" | tee -a "$LOG"
grep -E "^=== .* \| Accuracy" "$LOG" | tee -a "$LOG"
