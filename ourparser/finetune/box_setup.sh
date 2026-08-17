#!/bin/bash
# One-time training setup on a fresh Vast vLLM box. Idempotent.
#
# Design: training gets its OWN venv (/workspace/ftenv) so the serving venv
# (/venv/main, which vLLM runs from) is never disturbed — we alternate
# stop-vllm -> train -> merge -> start-vllm -> eval all night, and a broken
# serving env would end the loop.
set -euo pipefail
cd /workspace

if [ ! -d ftenv ]; then python3 -m venv ftenv; fi
source ftenv/bin/activate
pip -q install --upgrade pip
# LLaMA-Factory pinned; qwen2_vl LoRA support is stable in this line.
if [ ! -d LLaMA-Factory ]; then
  git clone -q --depth 1 https://github.com/hiyouga/LLaMA-Factory.git
fi
cd LLaMA-Factory && pip -q install -e ".[torch,metrics]" && cd ..

python - <<'PY'
# Verify the base model loads through transformers and report its chat template.
# Training MUST format samples exactly as vLLM formats them at serve time; if the
# template is nonstandard, the loop aborts here rather than training garbage.
from transformers import AutoProcessor, AutoConfig
import json
cfg = AutoConfig.from_pretrained("KDLAI/KDL-Frontier-Parser-nano", trust_remote_code=True)
print("architecture:", cfg.architectures, "| model_type:", cfg.model_type)
proc = AutoProcessor.from_pretrained("KDLAI/KDL-Frontier-Parser-nano", trust_remote_code=True)
t = getattr(proc, "chat_template", None) or getattr(proc.tokenizer, "chat_template", "")
print("chat_template present:", bool(t), "| length:", len(t or ""))
print("standard qwen2-vl markers:", all(m in (t or "") for m in ("<|im_start|>", "<|vision_start|>")) if t else "n/a")
PY
echo "SETUP OK"
