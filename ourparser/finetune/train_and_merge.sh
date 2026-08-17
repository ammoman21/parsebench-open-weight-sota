#!/bin/bash
# One training iteration on the box: train LoRA -> merge -> serve merged model.
# Usage: bash /workspace/train_and_merge.sh <iteration_name>
# Runs detached-safe: writes progress to /workspace/ft_out/<it>/run.log and a
# status file the Mac polls, so a dropped SSH session cannot kill training.
set -uo pipefail
IT="${1:?iteration name}"
cd /workspace
source ftenv/bin/activate
mkdir -p ft_out/$IT
STATUS=/workspace/ft_out/$IT/STATUS
echo "TRAINING" > $STATUS

# vLLM must be down: it holds 0.85 of VRAM and training needs the GPU.
supervisorctl stop vllm >/dev/null 2>&1 || true
pkill -9 -f "VLLM::EngineCore" 2>/dev/null || true; sleep 5

cd LLaMA-Factory
llamafactory-cli train /workspace/configs/$IT.yaml \
  > /workspace/ft_out/$IT/run.log 2>&1 || { echo "TRAIN_FAILED" > $STATUS; exit 1; }

echo "MERGING" > $STATUS
cat > /tmp/merge_$IT.yaml <<MEOF
model_name_or_path: KDLAI/KDL-Frontier-Parser-nano
adapter_name_or_path: /workspace/ft_out/$IT
template: qwen2_vl
finetuning_type: lora
trust_remote_code: true
export_dir: /workspace/merged/$IT
export_size: 4
export_legacy_format: false
MEOF
llamafactory-cli export /tmp/merge_$IT.yaml \
  >> /workspace/ft_out/$IT/run.log 2>&1 || { echo "MERGE_FAILED" > $STATUS; exit 1; }

echo "SERVING" > $STATUS
# Serve the merged weights under the SAME served-model-name so the Mac-side
# evaluation pipeline needs no changes at all.
sed -i '/^VLLM_MODEL=/d;/^MODEL_NAME=/d' /etc/environment
printf 'VLLM_MODEL="/workspace/merged/%s"\nMODEL_NAME="/workspace/merged/%s"\n' "$IT" "$IT" >> /etc/environment
supervisorctl start vllm >/dev/null 2>&1
for i in $(seq 1 40); do
  sleep 10
  curl -s -m 4 http://127.0.0.1:18000/v1/models 2>/dev/null | grep -q '"id"' && { echo "READY" > $STATUS; exit 0; }
done
echo "SERVE_TIMEOUT" > $STATUS; exit 1
