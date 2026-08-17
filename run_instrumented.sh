#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
export KDL_NANO_ENDPOINT_URL=http://127.0.0.1:18000/v1
export LLAMACLOUD_BENCH_LLM_NORMALIZATION=off
export PARSEBENCH_LABEL_CAPTURE="$(pwd)/runs/labels"
cd parsebench
echo "=== [$(date)] instrumented run: kdl_frontier_nano_patched ==="
uv run python ../ourparser/run_patched.py run kdl_frontier_nano_patched --max_concurrent 8 2>&1 | tail -40
echo "=== [$(date)] DONE ==="
