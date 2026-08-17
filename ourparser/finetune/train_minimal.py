#!/usr/bin/env python
"""
Minimal SFT loop for KDL-Frontier-Parser-nano. Exists because three LLaMA-Factory
configs produced NaN/exploding losses while a bare transformers forward with the
same processor is clean (loss 11.35, logits finite, bf16 and fp32) — so the
smallest trustworthy system is a loop we control entirely.

Fidelity: input = processor(chat_template(image + production prompt) + target),
labels masked to the target tokens only, computed by tokenizing the prompt-only
rendering and masking its length. Byte-identical production prompt.

Safety: asserts a finite loss EVERY step and aborts loudly on the first
non-finite value (no silent zero-logging); grad-clip 1.0; LoRA on language
attention+MLP only; vision tower and projector frozen by parameter filter.
"""
import json, math, os, random, sys, time
import torch
from pathlib import Path
from PIL import Image
from peft import LoraConfig, get_peft_model
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

DATA = Path(os.environ.get("DATA_DIR", "/workspace/data"))
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/ft_out/it3")
EPOCHS = float(os.environ.get("EPOCHS", "2"))
LR = float(os.environ.get("LR", "5e-5"))
DTYPE = torch.float32 if os.environ.get("FP32") else torch.bfloat16
ACCUM = int(os.environ.get("ACCUM", "16"))
M = "KDLAI/KDL-Frontier-Parser-nano"

OUT.mkdir(parents=True, exist_ok=True)
log = open(OUT / "train.log", "a")
def say(*a):
    print(*a, flush=True); print(*a, file=log, flush=True)

proc = AutoProcessor.from_pretrained(M, trust_remote_code=True)
model = Qwen2VLForConditionalGeneration.from_pretrained(M, torch_dtype=DTYPE, trust_remote_code=True).cuda()
model.gradient_checkpointing_disable()
# Freeze everything visual; LoRA the language stack only.
lcfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                  target_modules=[n for n in ["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"]],
                  task_type="CAUSAL_LM")
model = get_peft_model(model, lcfg)
for n, p in model.named_parameters():
    if "visual" in n or "merger" in n:
        p.requires_grad_(False)
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
say(f"trainable params: {trainable/1e6:.1f}M | dtype={DTYPE} lr={LR} epochs={EPOCHS} accum={ACCUM}")

rows = [json.loads(l) for l in (DATA / "data.jsonl").open()]
rng = random.Random(0); rng.shuffle(rows)

def encode(row):
    img = Image.open(DATA / row["image"]).convert("RGB")
    msgs = [{"role":"user","content":[{"type":"image"},{"type":"text","text":row["prompt"]}]}]
    prefix = proc.apply_chat_template(msgs, add_generation_prompt=True)
    full = prefix + row["target"] + "<|im_end|>"
    enc = proc(text=[full], images=[img], return_tensors="pt")
    pre = proc(text=[prefix], images=[img], return_tensors="pt")
    labels = enc.input_ids.clone()
    labels[:, :pre.input_ids.shape[1]] = -100
    enc["labels"] = labels
    return {k: v.cuda() for k, v in enc.items()}

opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR, weight_decay=0.0)
steps_total = int(len(rows) * EPOCHS)
warmup = max(10, steps_total // 33)
sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, s / warmup) * (0.5 * (1 + math.cos(math.pi * min(1.0, s / steps_total)))))

model.train(); t0 = time.time(); running = []
for step in range(steps_total):
    row = rows[step % len(rows)]
    out = model(**encode(row))
    loss = out.loss
    if not torch.isfinite(loss):
        say(f"ABORT step {step}: non-finite loss {loss.item()} on {row['image']}"); sys.exit(2)
    (loss / ACCUM).backward()
    running.append(loss.item())
    if (step + 1) % ACCUM == 0:
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step(); sched.step(); opt.zero_grad(set_to_none=True)
    if (step + 1) % 100 == 0:
        say(f"step {step+1}/{steps_total} loss={sum(running)/len(running):.4f} "
            f"lr={sched.get_last_lr()[0]:.2e} {(time.time()-t0)/(step+1):.2f}s/it")
        running = []
model.save_pretrained(OUT / "adapter")
say("DONE: adapter saved")
