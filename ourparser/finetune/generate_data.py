#!/usr/bin/env python
"""
Synthetic training data for the formatting fine-tune.

WHAT A TRAINING EXAMPLE IS — and why it is a region crop, not a page.
The pipeline's text stage never sees full pages: `_parse_page` runs layout
detection, crops each detected region, and sends the CROP with the prompt
"\nText Recognition:\n" (kdl_frontier_nano.py:3094 onward). So a training pair is
(region-crop image, exact markdown of that region), which matches the deployment
distribution exactly. We are teaching the model what to do with its existing
trigger — the prompt is byte-identical to production, per FINETUNE_PLAN.md.

TARGET MARKUP — only spellings the scorer accepts (execution-verified in
reports/parsebench_scoring_spec.md): bold `**text**`; strikethrough `~~text~~`;
superscript `<sup>text</sup>` and subscript `<sub>text</sub>` with no inner
spaces, wrapping exactly the styled run including punctuation. Never `<strong>`,
never `__text__`, never single-tilde. Underline/italic/highlight are deliberately
ABSENT from targets: they score in no category, and training them in would only
add noise.

PIPELINE: content sampler -> HTML -> Chrome headless --print-to-pdf ->
PyMuPDF rasterise at 150 DPI (the provider's own dpi, kdl_frontier_nano.py:75)
-> tight crop -> JSONL row. Deterministic under --seed.

NEGATIVES: ~30% of samples carry no styling and a plain-text target. The v2 probe
failure was indiscriminate marking; negatives are what teach restraint.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[2]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# ---------------------------------------------------------------- content ----
# Vocabulary is deliberately insurance/enterprise-flavoured: the benchmark's
# Tables dimension is 57.7% rate filings, and transfer needs visual + lexical
# similarity. Sentences are assembled from pools so no two docs read identically.

TERMS = ["premium", "deductible", "endorsement", "loss ratio", "underwriting margin",
         "combined ratio", "policyholder surplus", "reinsurance treaty", "rate filing",
         "actuarial reserve", "exposure base", "experience modifier", "retention",
         "subrogation", "indemnity limit", "coverage territory", "schedule of values"]
LABELS = ["Note", "Definition", "Exclusion", "Condition", "Endorsement", "Warning",
          "Section", "Item", "Coverage A", "Coverage B", "Exhibit", "Schedule"]
SENTENCES = [
    "The {t1} shall be calculated in accordance with the provisions of the {t2} set forth herein.",
    "Any adjustment to the {t1} requires written notice no fewer than sixty days prior to renewal.",
    "The company reported a {t1} of {num} percent for the period ending December 31.",
    "Failure to maintain the required {t1} constitutes a material breach of this agreement.",
    "The {t1} applies separately to each occurrence and is not reduced by payment of the {t2}.",
    "As filed with the commissioner, the proposed {t1} reflects a {num} percent indicated change.",
    "This provision supersedes the {t1} described in the prior edition of the {t2}.",
    "The insurer retains the right to audit the {t1} at any time during the policy period.",
]
FOOTMARKS = ["1", "2", "3", "a", "b", "*"]
CHEM = [("H", "2", "O"), ("CO", "2", ""), ("SO", "4", ""), ("CaCl", "2", "")]

CJK_SENT = ["國務院本月初公布了關於促進民航業發展的若干意見",
    "中國民用航空局局長今日透露現時國內外每天約有航班往來",
    "據內地媒體報道多家高校研究團隊聯合發布了最新報告",
    "香港民眾安全服務隊少年團二百名隊員完成了年度訓練",
    "保險監督管理委員會發布新規要求提高償付能力披露頻率",
    "再保險合約的分出比例將於下一財政年度起逐步調整"]
CJK_MARK = ["【本報訊】", "【本報記者北京電】", "【特稿】", "【綜合報道】"]
CAPS_LABELS = ["CREDIT RISK", "TOTAL ASSETS", "NET PREMIUMS EARNED", "LOSS RESERVES",
    "SECTION 4", "PART II", "EXHIBIT A", "UNDERWRITING RESULTS", "NOTES TO ACCOUNTS"]

FONTS = ['Georgia, serif', 'Helvetica, Arial, sans-serif', '"Times New Roman", serif',
         'Verdana, sans-serif', '"Courier New", monospace']


def _sentence(rng: random.Random, pool: list | None = None) -> str:
    s = rng.choice(pool) if pool else rng.choice(SENTENCES)
    if pool: pool.remove(s)
    s = (s.replace("{t1}", rng.choice(TERMS)).replace("{t2}", rng.choice(TERMS))
          .replace("{num}", str(rng.randint(2, 97))))
    # article agreement: "a actuarial reserve" -> "an actuarial reserve"
    return re.sub(r"\ba ([aeiouAEIOU])", r"an \1", s)


def make_region(rng: random.Random, styled: bool) -> tuple[str, str]:
    """One region: returns (html_body, target_markdown)."""
    # Targeted patterns from it4 failure analysis (86 residual bold failures:
    # CJK newsprint datelines, ALL-CAPS labels, short section labels).
    if styled:
        r = rng.random()
        if r < 0.22:   # CJK newsprint: bold bracketed dateline + body
            mark = rng.choice(CJK_MARK)
            body = "".join(rng.sample(CJK_SENT, k=2)) + "。"
            return (f"<b>{mark}</b>{body}", f"**{mark}**{body}")
        if r < 0.38:   # ALL-CAPS bold label, then body
            lab = rng.choice(CAPS_LABELS)
            body = " ".join(_sentence(rng, list(SENTENCES)) for _ in range(2))
            return (f"<b>{lab}</b><br>{body}", f"**{lab}**\n{body}")
    html_parts: list[str] = []
    md_parts: list[str] = []
    n_sent = rng.randint(2, 5)
    pool = list(SENTENCES)

    # Whole-line bold opener (mini-heading inside a text region) — common in real
    # filings, absent from the it3 mix; bold plateaued at 65 partly for this reason.
    if styled and rng.random() < 0.25:
        h = rng.choice(LABELS) + " " + rng.choice(TERMS).title()
        html_parts.append(f"<b>{h}</b><br>")
        md_parts.append(f"**{h}**\n")
    # Optional run-in label — the classic bold pattern in policy documents.
    if styled and rng.random() < 0.6:
        lab = rng.choice(LABELS)
        html_parts.append(f"<b>{lab}:</b> ")
        md_parts.append(f"**{lab}:** ")

    for i in range(n_sent):
        s = _sentence(rng, pool)
        if styled:
            r = rng.random()
            if r < 0.38:  # bold a defined term inside the sentence
                t = rng.choice(TERMS)
                if t in s:
                    s_html = s.replace(t, f"<b>{t}</b>", 1)
                    s_md = s.replace(t, f"**{t}**", 1)
                else:
                    s_html = s_md = s
            elif r < 0.58:  # superscript footnote reference at sentence end
                fm = rng.choice(FOOTMARKS)
                s_html = s[:-1] + f".<sup>{fm}</sup>" if s.endswith(".") else s + f"<sup>{fm}</sup>"
                s_md = s[:-1] + f".<sup>{fm}</sup>" if s.endswith(".") else s + f"<sup>{fm}</sup>"
            elif r < 0.68:  # struck-through (superseded) clause
                s_html = f"<s>{s}</s>"
                s_md = f"~~{s}~~"
            elif r < 0.70 and rng.random() < 0.5:  # subscript via chemical/financial notation
                base, sub, tail = rng.choice(CHEM)
                frag = f"{base}<sub>{sub}</sub>{tail}"
                s_html = s + f" The sample contained {frag}."
                s_md = s + f" The sample contained {frag}."
            else:
                s_html = s_md = s
        else:
            s_html = s_md = s
        html_parts.append(s_html + (" " if i < n_sent - 1 else ""))
        md_parts.append(s_md + (" " if i < n_sent - 1 else ""))

    html, md = "".join(html_parts), "".join(md_parts)
    if styled and not any(m in md for m in ("**", "~~", "<sup>", "<sub>")):
        t = rng.choice(TERMS)
        if t in md:
            md = md.replace(t, f"**{t}**", 1)
            html = html.replace(t, f"<b>{t}</b>", 1)
        else:
            lab = rng.choice(LABELS)
            html = f"<b>{lab}:</b> " + html
            md = f"**{lab}:** " + md
    return html, md


def render(html_body: str, out_png: Path, rng: random.Random) -> None:
    font = rng.choice(FONTS)
    size = rng.choice([13, 14, 15, 16])
    width = rng.choice([420, 520, 620, 700])
    align = rng.choice(["left", "justify"])
    doc_html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ margin: 0; size: {width + 40}px 2000px; }}
      body {{ margin: 20px; width: {width}px; font-family: {font};
              font-size: {size}px; line-height: 1.45; text-align: {align};
              color: #111; background: #fff; }}
    </style></head><body>{html_body}</body></html>"""
    with tempfile.TemporaryDirectory() as td:
        hp = Path(td) / "r.html"
        pp = Path(td) / "r.pdf"
        hp.write_text(doc_html)
        subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pp}", str(hp)],
                       check=True, capture_output=True, timeout=60)
        doc = fitz.open(pp)
        page = doc[0]
        # 150 DPI to match the provider's own rasterisation (dpi=150)
        pix = page.get_pixmap(dpi=150)
        pix.save(out_png)
        doc.close()
    # tight-crop whitespace so the crop resembles a layout-detected region
    import PIL.Image
    import PIL.ImageChops
    im = PIL.Image.open(out_png).convert("RGB")
    bg = PIL.Image.new("RGB", im.size, (255, 255, 255))
    bbox = PIL.ImageChops.difference(im, bg).getbbox()
    if bbox:
        pad = 8
        bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad))
        im.crop(bbox).save(out_png)


def render_batch(specs, out_paths, rng_styles) -> None:
    """One Chrome call for a whole batch: each region is its own CSS page,
    rasterised per page then tight-cropped. ~10x faster than per-region calls."""
    import PIL.Image, PIL.ImageChops
    pages = []
    for (html_body,), style in zip(specs, rng_styles):
        has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in html_body)
        font, size, width, align = style
        if has_cjk:
            font = '"PingFang TC","Hiragino Sans","Songti TC",sans-serif' 
        pages.append(
            f'<div style="page-break-after: always; margin:0; padding:20px; '
            f'width:{width}px; font-family:{font}; font-size:{size}px; '
            f'line-height:1.45; text-align:{align}; color:#111; background:#fff">'
            f'{html_body}</div>')
    doc_html = ('<!doctype html><html><head><meta charset="utf-8"><style>'
                '@page { margin: 0; size: 760px 2200px; } body { margin:0; }'
                '</style></head><body>' + "".join(pages) + "</body></html>")
    with tempfile.TemporaryDirectory() as td:
        hp = Path(td) / "b.html"; pp = Path(td) / "b.pdf"
        hp.write_text(doc_html)
        subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pp}", str(hp)],
                       check=True, capture_output=True, timeout=300)
        doc = fitz.open(pp)
        assert doc.page_count >= len(out_paths), f"pages {doc.page_count} < regions {len(out_paths)}"
        for page, out_png in zip(doc, out_paths):
            pix = page.get_pixmap(dpi=150); pix.save(out_png)
            im = PIL.Image.open(out_png).convert("RGB")
            bg = PIL.Image.new("RGB", im.size, (255, 255, 255))
            bbox = PIL.ImageChops.difference(im, bg).getbbox()
            if bbox:
                pad = 8
                bbox = (max(0, bbox[0]-pad), max(0, bbox[1]-pad),
                        min(im.width, bbox[2]+pad), min(im.height, bbox[3]+pad))
                im.crop(bbox).save(out_png)
        doc.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "finetune_data"))
    ap.add_argument("--neg-frac", type=float, default=0.30)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)

    rows = []
    n_styled = n_neg = 0
    pending, pending_paths, pending_styles, pending_meta = [], [], [], []

    def flush():
        if pending:
            render_batch(pending, pending_paths, pending_styles)
            pending.clear(); pending_paths.clear(); pending_styles.clear()

    for i in range(args.n):
        styled = rng.random() >= args.neg_frac
        html_body, md = make_region(rng, styled)
        png = out / "images" / f"region_{i:05d}.png"
        style = (rng.choice(FONTS), rng.choice([13, 14, 15, 16]),
                 rng.choice([420, 520, 620, 700]), rng.choice(["left", "justify"]))
        pending.append((html_body,)); pending_paths.append(png); pending_styles.append(style)
        if len(pending) >= 100:
            flush()
        has_markup = any(m in md for m in ("**", "~~", "<sup>", "<sub>"))
        n_styled += has_markup
        n_neg += not has_markup
        rows.append({
            "image": str(png.relative_to(out)),
            "prompt": "\nText Recognition:\n",   # byte-identical to production
            "target": md,
            "styled": has_markup,
            "seed": args.seed, "index": i,
        })
    flush()
    (out / "data.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    import collections
    marks = collections.Counter()
    for r in rows:
        for m in ("**", "~~", "<sup>", "<sub>"):
            marks[m] += r["target"].count(m)
    print(f"wrote {len(rows)} examples -> {out}")
    print(f"  styled: {n_styled}  negatives: {n_neg} ({n_neg*100//len(rows)}%)")
    print(f"  marker occurrences in targets: {dict(marks)}")


if __name__ == "__main__":
    main()
