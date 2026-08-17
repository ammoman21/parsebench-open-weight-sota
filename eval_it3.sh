#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15 -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 52850 root@93.91.156.108"
echo "[eval] waiting for training DONE..."
while ! $SSH "grep -q '^DONE' /workspace/ft_out/it3/train.log" 2>/dev/null; do
  if $SSH "grep -q '^ABORT' /workspace/ft_out/it3/train.log" 2>/dev/null; then echo "[eval] TRAIN ABORTED"; exit 1; fi
  sleep 60
done
echo "[eval] merging + serving merged model..."
$SSH "source /workspace/ftenv/bin/activate && python /workspace/merge_minimal.py it3 && \
  sed -i '/^VLLM_MODEL=/d;/^MODEL_NAME=/d' /etc/environment && \
  printf 'VLLM_MODEL=\"/workspace/merged/it3\"\nMODEL_NAME=\"/workspace/merged/it3\"\n' >> /etc/environment && \
  supervisorctl start vllm"
for i in $(seq 1 40); do sleep 10; curl -s -m 4 http://127.0.0.1:18000/v1/models 2>/dev/null | grep -q '"id"' && break; done
echo "[eval] serving; running probes"
export PATH="$HOME/.local/bin:$PATH" KDL_NANO_ENDPOINT_URL=http://127.0.0.1:18000/v1 LLAMACLOUD_BENCH_LLM_NORMALIZATION=off
./parsebench/.venv/bin/python ourparser/probe/run_probe.py v0_control 2>&1 | tail -14 | tee -a LOOP_LOG.md
PROBE_GROUP=text_content PROBE_DATA="$(pwd)/parsebench/data_probe_text_content" \
  ./parsebench/.venv/bin/python ourparser/probe/run_probe.py v0_control 2>&1 | grep -E "scored docs|content_faithfulness|avg_rule_pass_rate" | tee -a LOOP_LOG.md
echo "[eval] complete $(date)"
