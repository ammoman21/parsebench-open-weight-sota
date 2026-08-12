#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
export CHANDRA2_SERVER_URL=http://127.0.0.1:18000
cd "$(dirname "$0")"
echo "=== [$(date)] full run: chandra2_vllm (2079 files) ==="
uv run parse-bench run chandra2_vllm --max_concurrent 8 2>&1 | tail -30
echo "=== [$(date)] DONE ==="
