#!/bin/bash
# Chain: wait for datagen -> convert -> upload -> launch it1 detached -> poll to completion.
set -uo pipefail
cd "$(dirname "$0")"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15 -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 52850 root@93.91.156.108"

echo "[chain] waiting for 2000 rendered images..."
while [ "$(ls finetune_data_2k/images 2>/dev/null | wc -l | tr -d ' ')" -lt 2000 ] || [ ! -s finetune_data_2k/data.jsonl ]; do sleep 30; done
echo "[chain] datagen complete: $(date)"

./parsebench/.venv/bin/python ourparser/finetune/to_llamafactory.py finetune_data_2k /workspace/data

echo "[chain] uploading data to box..."
rsync -aq -e "ssh -o BatchMode=yes -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 52850" \
  finetune_data_2k/ root@93.91.156.108:/workspace/data/
$SSH "grep -q dataset_dir /workspace/configs/it1.yaml || sed -i 's|dataset: kdl_formatting|dataset: kdl_formatting\ndataset_dir: /workspace/data|' /workspace/configs/it1.yaml; echo config-ok"

echo "[chain] waiting for box_setup to finish (ftenv + LLaMA-Factory)..."
while ! $SSH "test -x /workspace/ftenv/bin/llamafactory-cli" 2>/dev/null; do sleep 30; done

echo "[chain] launching it1 training detached: $(date)"
$SSH "setsid nohup bash /workspace/train_and_merge.sh it1 > /workspace/ft_out_it1_outer.log 2>&1 & echo launched"

echo "[chain] polling STATUS until READY or failure..."
while true; do
  ST=$($SSH "cat /workspace/ft_out/it1/STATUS 2>/dev/null" 2>/dev/null | tail -1)
  echo "[chain] $(date '+%H:%M') status=$ST"
  case "$ST" in
    READY|TRAIN_FAILED|MERGE_FAILED|SERVE_TIMEOUT) break ;;
  esac
  sleep 120
done
echo "[chain] final status: $ST at $(date)"
mkdir -p ft_logs && rsync -aq -e "ssh -o BatchMode=yes -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 52850" \
  root@93.91.156.108:/workspace/ft_out/it1/run.log ft_logs/it1_run.log 2>/dev/null || true
tail -5 ft_logs/it1_run.log 2>/dev/null
