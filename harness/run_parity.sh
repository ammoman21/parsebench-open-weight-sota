#!/bin/bash
# Full ParseBench parity run: reproduce KDL-Frontier-Parser-nano's published 76.36
export PATH="$HOME/.local/bin:$PATH"
export KDL_NANO_ENDPOINT_URL=http://127.0.0.1:18000/v1
cd "$(dirname "$0")"
echo "=== [$(date)] downloading full dataset ==="
uv run parse-bench download 2>&1 | tail -5
echo "=== [$(date)] dataset status ==="
uv run parse-bench status 2>&1 | tail -12
echo "=== [$(date)] starting full run: kdl_frontier_nano ==="
uv run parse-bench run kdl_frontier_nano --max_concurrent 8 2>&1 | tail -40
echo "=== [$(date)] DONE ==="
