"""
Offline proof that the two instrumentation hooks DO fire when the vendored
pipeline actually runs a page.

No network: `_nano_chat` (the single HTTP call site,
kdl_frontier_nano.py:2713-2742) is replaced by a stub that returns canned model
responses, so nothing contacts the vLLM endpoint. vLLM = the open-source model
server the pipeline talks to over an OpenAI-compatible HTTP API.
"""
import asyncio, random, sys
sys.path.insert(0, "src")
from PIL import Image
from parse_bench.inference.providers.parse import kdl_frontier_nano as K

LAYOUT = (
    "<|box_start|>100 40 900 80<|box_end|><|ref_start|>header<|ref_end|>"
    "<|box_start|>100 120 900 200<|box_end|><|ref_start|>title<|ref_end|>"
    "<|box_start|>100 240 900 400<|box_end|><|ref_start|>section_header<|ref_end|>"
    "<|box_start|>100 440 900 700<|box_end|><|ref_start|>text<|ref_end|>"
)

calls = {"_category_for_item": 0, "parse_native_layout_tokens": 0}
seen_raw = []

async def fake_chat(client, url, payload, semaphore):
    # payload's text prompt tells us which stage this is
    txt = payload["messages"][0]["content"][-1]["text"]
    return LAYOUT if "Layout Detection" in txt else "some recognised words"

def main():
    orig_cat, orig_tok = K._category_for_item, K.parse_native_layout_tokens

    def wcat(item, metadata):
        calls["_category_for_item"] += 1
        return orig_cat(item, metadata)

    def wtok(content):
        calls["parse_native_layout_tokens"] += 1
        out = orig_tok(content)
        seen_raw.extend((d.get("raw_category"), d.get("category")) for d in out)
        return out

    K._category_for_item, K.parse_native_layout_tokens = wcat, wtok
    K._nano_chat = fake_chat

    rnd = random.Random(0)
    img = Image.new("RGB", (1200, 1600), (255, 255, 255))
    px = img.load()
    for _ in range(200000):                      # noise so is_monochromatic() is False
        px[rnd.randrange(1200), rnd.randrange(1600)] = (rnd.randrange(256),) * 3

    eng = K._NanoEngine("http://127.0.0.1:1/v1", "m", 2, 5.0)
    els = asyncio.run(eng._parse_page(None, asyncio.Semaphore(2), img, 1))

    print("hook calls:", calls)
    print("raw -> category:", seen_raw)
    print("element dict keys:", sorted(els[0].keys()) if els else "NO ELEMENTS")
    print("elements:", [(e["category"], "raw_category" in e) for e in els])

    K._category_for_item, K.parse_native_layout_tokens = orig_cat, orig_tok

main()
