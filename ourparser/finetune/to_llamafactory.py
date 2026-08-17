#!/usr/bin/env python
"""
Convert our data.jsonl to LLaMA-Factory's sharegpt-multimodal format.

Fidelity note: production sends a chat message whose content is [image, text
"\nText Recognition:\n"]. LLaMA-Factory renders "<image>" followed by the text
through the qwen2_vl template, which produces the same token sequence: vision
tokens, then the prompt text. The assistant turn is the exact target markdown.
Also emits dataset_info.json so the dataset registers as `kdl_formatting`.
"""
import json, sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else "finetune_data_2k")
# image paths must be valid ON THE TRAINING BOX, not on this Mac
BOX_PREFIX = sys.argv[2] if len(sys.argv) > 2 else "/workspace/data"
rows = [json.loads(l) for l in (src / "data.jsonl").open()]
out = []
for r in rows:
    out.append({
        "messages": [
            {"role": "user", "content": "<image>" + r["prompt"]},
            {"role": "assistant", "content": r["target"]},
        ],
        "images": [f"{BOX_PREFIX}/{r['image']}"],
    })
(src / "llamafactory.json").write_text(json.dumps(out, ensure_ascii=False, indent=0))
(src / "dataset_info.json").write_text(json.dumps({
    "kdl_formatting": {
        "file_name": "llamafactory.json",
        "formatting": "sharegpt",
        "columns": {"messages": "messages", "images": "images"},
        "tags": {"role_tag": "role", "content_tag": "content",
                 "user_tag": "user", "assistant_tag": "assistant"},
    }
}, indent=1))
styled = sum(1 for r in rows if r["styled"])
print(f"converted {len(out)} examples ({styled} styled, {len(rows)-styled} negative) -> {src}/llamafactory.json")
