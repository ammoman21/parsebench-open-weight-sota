#!/usr/bin/env python
"""Merge the LoRA adapter into base weights with peft directly."""
import sys, torch
from peft import PeftModel
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
it = sys.argv[1]
M = "KDLAI/KDL-Frontier-Parser-nano"
base = Qwen2VLForConditionalGeneration.from_pretrained(M, torch_dtype=torch.bfloat16, trust_remote_code=True)
merged = PeftModel.from_pretrained(base, f"/workspace/ft_out/{it}/adapter").merge_and_unload()
merged.save_pretrained(f"/workspace/merged/{it}")
AutoProcessor.from_pretrained(M, trust_remote_code=True).save_pretrained(f"/workspace/merged/{it}")
print("merged ->", f"/workspace/merged/{it}")
