#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15 -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 52850 root@93.91.156.108"
while [ "$(ls finetune_data_5k/images 2>/dev/null | wc -l | tr -d ' ')" -lt 5000 ] || [ ! -s finetune_data_5k/data.jsonl ]; do sleep 20; done
./parsebench/.venv/bin/python ourparser/finetune/to_llamafactory.py finetune_data_5k /workspace/data5k
rsync -aq -e "ssh -o BatchMode=yes -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 52850" finetune_data_5k/ root@93.91.156.108:/workspace/data5k/
scp -q -o BatchMode=yes -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -P 52850 ourparser/finetune/train_minimal.py root@93.91.156.108:/workspace/
echo "[it5] waiting for DONE (~45 min for 14k steps)..."
while ! $SSH "grep -q '^DONE' /workspace/ft_out/it5/train.log" 2>/dev/null; do
  $SSH "grep -q '^ABORT' /workspace/ft_out/it5/train.log" 2>/dev/null && { echo "[it5] ABORTED"; exit 1; }
  sleep 90
done
echo "[it5] merge + serve"
$SSH "source /workspace/ftenv/bin/activate && python /workspace/merge_minimal.py it5 && sed -i '/^VLLM_MODEL=/d;/^MODEL_NAME=/d' /etc/environment && printf 'VLLM_MODEL=\"/workspace/merged/it5\"\nMODEL_NAME=\"/workspace/merged/it5\"\n' >> /etc/environment && supervisorctl restart vllm"
for i in $(seq 1 40); do sleep 10; curl -s -m 4 http://127.0.0.1:18000/v1/models 2>/dev/null | grep -q '"id"' && break; done
export PATH="$HOME/.local/bin:$PATH" KDL_NANO_ENDPOINT_URL=http://127.0.0.1:18000/v1 LLAMACLOUD_BENCH_LLM_NORMALIZATION=off
echo "== IT4 formatting ==" >> LOOP_LOG.md
./parsebench/.venv/bin/python ourparser/probe/run_probe.py v0_control 2>&1 | grep -E "avg_semantic|is_bold|is_sup|is_strikeout|scored docs|markers|bold_|sup |strike" | tee -a LOOP_LOG.md
echo "== IT4 CF guard ==" >> LOOP_LOG.md
PROBE_GROUP=text_content PROBE_DATA="$(pwd)/parsebench/data_probe_text_content" ./parsebench/.venv/bin/python ourparser/probe/run_probe.py v0_control 2>&1 | grep -E "avg_content|scored docs" | tee -a LOOP_LOG.md
echo "[it5] complete $(date)"
