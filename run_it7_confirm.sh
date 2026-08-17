#!/bin/bash
export PATH="$HOME/.local/bin:$PATH" KDL_NANO_ENDPOINT_URL=http://127.0.0.1:18000/v1 LLAMACLOUD_BENCH_LLM_NORMALIZATION=off
cd "$(dirname "$0")/parsebench"
echo "=== [$(date)] CALIBRATION full run: it7 weights + patched pipeline ==="
uv run python ../ourparser/run_patched.py run kdl_frontier_nano_patched \
  --output_dir output/it7_confirm --force True --max_concurrent 8 2>&1 | tail -25
echo "=== [$(date)] DONE ==="
