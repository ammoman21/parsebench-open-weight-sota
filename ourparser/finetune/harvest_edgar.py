#!/usr/bin/env python
"""
Harvest real SEC EDGAR filings into training pairs for the formatting fine-tune.

EDGAR (Electronic Data Gathering, Analysis, and Retrieval) is the SEC's public
filing repository. Filings are HTML, so ground-truth inline styling (bold,
strikethrough, superscript, subscript) is derivable exactly from the DOM
(Document Object Model — the parsed HTML tree), not annotated by hand. This
gives us real-document typography with exact labels — the residual failure mode
of the synthetic pipeline (ourparser/finetune/generate_data.py) was precisely
real-document texture: short bold risk labels, ALL-CAPS headers, dense layouts.

PIPELINE
  1. Fetch recent 10-K (annual report) and 10-Q (quarterly report) primary HTML
     documents for insurance-sector companies (SIC codes 6311/6321/6331/6411 —
     Standard Industrial Classification, the SEC's sector coding), via the
     data.sec.gov submissions API. Fair-access compliance: User-Agent with a
     contact string, hard rate limit below 5 requests/second, and every
     response cached under edgar_cache/ so re-runs hit the network zero times.
  2. Extract self-contained region-sized fragments (a paragraph, a
     heading+paragraph pair, a short definition item — a few hundred px tall
     when rendered). Tables are skipped entirely (see report for why).
  3. For each fragment derive (a) target markdown using ONLY the spellings the
     ParseBench scorer accepts (execution-verified in
     reports/parsebench_scoring_spec.md): **bold**, ~~strike~~,
     <sup>text</sup>, <sub>text</sub>; italic/underline deliberately map to
     plain text because they score in no category; and (b) a rendering HTML
     snippet with original inline tags intact but stripped of
     classes/ids/scripts/links (visual styling only).
  4. Render fragments to PNG region crops with the same batch mechanism as the
     synthetic pipeline: Chrome headless --print-to-pdf, one CSS page per
     fragment, PyMuPDF rasterisation at 150 DPI, tight crop to ink.
  5. Emit data.jsonl rows with the production-byte-identical prompt
     "\nText Recognition:\n" and ~25% no-styling negatives (negatives teach
     restraint; the v2 synthetic probe failed by marking indiscriminately).
  6. Mandatory quality gates, printed at the end of every run:
     (a) zero blank renders — every PNG's difference-from-white bounding box
         must be non-None (the synthetic pipeline once shipped blank CJK
         renders; every image is re-opened and checked);
     (b) for 10 random styled samples, every **span** in the target is
         independently located inside a bold-styled element of the fragment's
         rendering HTML — printed side by side;
     (c) near-duplicate fragments are removed (filings share boilerplate);
     (d) marker counts and styled/negative split.

Deterministic given --seed (project convention): all sampling uses one seeded
random.Random; network responses are cached so content is stable across runs.

Run with:  parsebench/.venv/bin/python ourparser/finetune/harvest_edgar.py
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import fitz  # PyMuPDF — PDF rasteriser
import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[2]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CACHE = ROOT / "edgar_cache"

# SEC fair-access rules (https://www.sec.gov/os/accessing-edgar-data):
# identify yourself in the User-Agent and stay below 10 req/s; we cap at 4/s.
USER_AGENT = "research contact shaurya@florin.inc"
MIN_REQUEST_INTERVAL = 0.25  # seconds -> 4 requests/second, under the 5/s brief

# Insurance-sector issuers (SIC 6311 life, 6321 accident/health, 6331
# property/casualty, 6411 brokers). CIK = Central Index Key, the SEC company id.
DEFAULT_TICKERS = ["TRV", "ALL", "PGR", "CB", "AIG",
                   "HIG", "AFL", "CINF", "WRB", "AIZ"]

PROMPT = "\nText Recognition:\n"  # byte-identical to production (FINETUNE_PLAN.md)

# ------------------------------------------------------------------ fetch ----

_last_request_time = 0.0


def _rate_limited_get(url: str) -> bytes:
    """GET with fair-access UA and a hard inter-request delay."""
    global _last_request_time
    wait = MIN_REQUEST_INTERVAL - (time.time() - _last_request_time)
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT,
                                      "Accept-Encoding": "gzip, deflate"},
                        timeout=60)
    _last_request_time = time.time()
    resp.raise_for_status()
    return resp.content


def cached_get(url: str) -> bytes:
    """Every URL is fetched at most once ever; bytes live in edgar_cache/."""
    CACHE.mkdir(exist_ok=True)
    tail = re.sub(r"[^A-Za-z0-9._-]", "_", url.rsplit("/", 1)[-1])[:80]
    path = CACHE / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}_{tail}"
    if path.exists():
        return path.read_bytes()
    data = _rate_limited_get(url)
    path.write_bytes(data)
    return data


def resolve_ciks(tickers: list[str]) -> dict[str, int]:
    """Ticker -> CIK via the SEC's official mapping file."""
    table = json.loads(cached_get("https://www.sec.gov/files/company_tickers.json"))
    want = {t.upper() for t in tickers}
    out = {v["ticker"]: int(v["cik_str"]) for v in table.values()
           if v["ticker"] in want}
    missing = want - set(out)
    if missing:
        raise SystemExit(f"tickers not found in SEC mapping: {sorted(missing)}")
    return out


def recent_filings(cik: int, forms: tuple[str, ...] = ("10-K", "10-Q"),
                   per_form: int = 1) -> list[dict]:
    """Most recent primary HTML document per requested form type."""
    sub = json.loads(cached_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    rec = sub["filings"]["recent"]
    picked: list[dict] = []
    counts = {f: 0 for f in forms}
    for form, acc, doc, date in zip(rec["form"], rec["accessionNumber"],
                                    rec["primaryDocument"], rec["filingDate"]):
        if form in counts and counts[form] < per_form and doc.endswith((".htm", ".html")):
            counts[form] += 1
            acc_nodash = acc.replace("-", "")
            picked.append({
                "form": form, "date": date, "cik": cik,
                "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}",
            })
        if all(c >= per_form for c in counts.values()):
            break
    return picked


# ------------------------------------------------- styling model of the DOM ----

# Tags that directly set a styling flag. Italic/underline are tracked so we can
# keep them in the rendering HTML, but they never produce a markdown marker.
TAG_FLAGS = {"b": "bold", "strong": "bold",
             "s": "strike", "strike": "strike", "del": "strike",
             "sup": "sup", "sub": "sub",
             "i": "italic", "em": "italic", "u": "underline", "ins": "underline",
             # headings render bold by default in Chrome; an explicit
             # font-weight:normal style overrides this (applied after tag name)
             "h1": "bold", "h2": "bold", "h3": "bold",
             "h4": "bold", "h5": "bold", "h6": "bold"}

BLOCK_TAGS = {"p", "div", "li", "dt", "dd", "center", "blockquote",
              "h1", "h2", "h3", "h4", "h5", "h6"}

# Attributes kept in rendering HTML: only the filtered style attribute.
# Visual CSS properties retained (colors deliberately dropped — some filings
# use white-on-color header text, which without its background would render
# blank and trip gate (a)).
KEEP_STYLE_PROPS = {"font-weight", "font-style", "font-size", "font-family",
                    "text-decoration", "text-decoration-line", "text-transform",
                    "vertical-align", "text-align", "letter-spacing",
                    "line-height", "text-indent",
                    # hanging-indent bullets: EDGAR marks list items as
                    # padding-left + negative text-indent + a padded span;
                    # dropping the paddings while keeping text-indent clipped
                    # the bullet glyph off the page edge (found in first run)
                    "padding-left", "margin-left"}
KEEP_TAGS = {"p", "div", "span", "font", "b", "strong", "i", "em", "u", "ins",
             "s", "strike", "del", "sup", "sub", "br", "small", "big",
             "h1", "h2", "h3", "h4", "h5", "h6", "li", "dt", "dd"}


def parse_style(style: str | None) -> dict[str, str]:
    props: dict[str, str] = {}
    for part in (style or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            props[k.strip().lower()] = v.replace("!important", "").strip().lower()
    return props


def is_hidden(tag: Tag) -> bool:
    """display:none content (inline-XBRL hidden facts etc.) must appear in
    neither the target nor the render — Chrome would not show it."""
    return (tag.name == "ix:hidden"
            or parse_style(tag.get("style")).get("display") == "none")


def apply_node_style(tag: Tag, flags: dict[str, bool]) -> dict[str, bool]:
    """New flag dict after entering `tag` (tag name + inline style)."""
    f = dict(flags)
    name = tag.name.lower()
    if name in TAG_FLAGS:
        f[TAG_FLAGS[name]] = True
    props = parse_style(tag.get("style"))
    fw = props.get("font-weight")
    if fw:
        if fw in ("bold", "bolder") or (fw.rstrip("0123456789") == "" and int(fw) >= 600):
            f["bold"] = True
        elif fw in ("normal", "lighter") or fw.isdigit():
            f["bold"] = False
    deco = props.get("text-decoration", "") + " " + props.get("text-decoration-line", "")
    if "line-through" in deco:
        f["strike"] = True
    if "underline" in deco:
        f["underline"] = True
    va = props.get("vertical-align", "")
    if va.startswith("super"):
        f["sup"] = True
    elif va.startswith("sub"):
        f["sub"] = True
    fs = props.get("font-style")
    if fs in ("italic", "oblique"):
        f["italic"] = True
    elif fs == "normal":
        f["italic"] = False
    return f


BASE_FLAGS = {"bold": False, "strike": False, "sup": False, "sub": False,
              "italic": False, "underline": False}


def inherited_flags(elem: Tag) -> dict[str, bool]:
    """Styling inherited from ancestors (a whole-bold <p> must count as bold)."""
    chain = []
    node = elem
    while isinstance(node, Tag) and node.name not in ("body", "html", "[document]"):
        chain.append(node)
        node = node.parent
    flags = dict(BASE_FLAGS)
    for tag in reversed(chain[1:]):  # ancestors only; elem itself applied by walker
        flags = apply_node_style(tag, flags)
    return flags


def collect_runs(node, flags: dict[str, bool], runs: list[tuple[str, tuple]]) -> None:
    """Flatten a fragment into (text, (bold, strike, sup, sub)) runs.

    Whitespace inside text nodes is collapsed (HTML rendering collapses it
    too, so the target must match what the image shows). <br> becomes a
    literal newline run.
    """
    if isinstance(node, Comment):
        return
    if isinstance(node, NavigableString):
        text = str(node).replace("\xa0", " ").replace("​", "").replace("\xad", "")
        text = re.sub(r"\s+", " ", text)
        if text:
            runs.append((text, (flags["bold"], flags["strike"],
                                flags["sup"], flags["sub"])))
        return
    if not isinstance(node, Tag):
        return
    if node.name in ("script", "style", "table", "img") or is_hidden(node):
        return
    if node.name == "br":
        runs.append(("\n", (False, False, False, False)))
        return
    child_flags = apply_node_style(node, flags)
    # A left-padded inline element mid-fragment renders as a visible gap
    # (EDGAR bullet spacing); the target must show it as a space or the label
    # would read "•a downgrade" against an image showing "• a downgrade".
    pad = parse_style(node.get("style")).get("padding-left", "")
    m = re.match(r"([\d.]+)\s*(px|pt)", pad)
    if m and float(m.group(1)) >= 3 and runs and not runs[-1][0].endswith((" ", "\n")):
        runs.append((" ", runs[-1][1]))
    for child in node.children:
        collect_runs(child, child_flags, runs)


def runs_to_markdown(runs: list[tuple[str, tuple]]) -> tuple[str, bool]:
    """Emit target markdown. Returns (markdown, has_any_marker_styling).

    Marker precedence when styles overlap on one run: sup > sub > strike >
    bold — one marker per run, matching the synthetic pipeline, which never
    nests markers. Whitespace at run edges is moved OUTSIDE the marker: the
    scorer's regexes want the marker hugging the styled text
    (reports/parsebench_scoring_spec.md — "no inner spaces").
    """
    merged: list[tuple[str, tuple]] = []
    for text, st in runs:
        if merged and merged[-1][1] == st:
            merged[-1] = (merged[-1][0] + text, st)
        else:
            merged.append((text, st))

    out: list[str] = []
    has_marker = False
    for text, (bold, strike, sup, sub) in merged:
        core = text.strip()
        styled = any((bold, strike, sup, sub)) and re.search(r"[A-Za-z0-9]", core)
        if not styled:
            out.append(text)
            continue
        has_marker = True
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        if sup:
            piece = f"<sup>{core}</sup>"
        elif sub:
            piece = f"<sub>{core}</sub>"
        elif strike:
            piece = f"~~{core}~~"
        else:
            piece = f"**{core}**"
        out.append(lead + piece + trail)
    md = "".join(out)
    md = re.sub(r"[ \t]+", " ", md)
    md = re.sub(r" *\n+ *", "\n", md).strip()
    return md, has_marker


# ------------------------------------------------ fragment extraction ----

BOILERPLATE = re.compile(
    r"(UNITED STATES\s+SECURITIES AND EXCHANGE COMMISSION|Washington,?\s*D\.?C\.?\s*20549"
    r"|^Table of Contents$|Commission File Number|pursuant to Section 1[35]"
    r"|Securities Exchange Act of 1934|I\.?R\.?S\.?\s*Employer|Check the appropriate box"
    r"|Indicate by check mark|has duly caused this report|antifraud provisions"
    r"|incorporated by reference|^Exhibit\s+\d|^Item\s+\d+[A-Z]?\.?$|^PART [IVX]+$"
    r"|^\(?Unaudited\)?$|^\$? ?[\d,.()%]+$|shares outstanding as of)",
    re.IGNORECASE)


def is_boilerplate(text: str) -> bool:
    if BOILERPLATE.search(text):
        return True
    alpha = sum(c.isalpha() for c in text)
    return alpha < 0.45 * max(len(text), 1)  # numeric/punct-dominated rows


def clean_for_render(node: Tag) -> str:
    """Rendering HTML: original inline tags, no classes/ids/scripts/links,
    inline style filtered to visual properties, oversized fonts capped so a
    fragment never overflows its CSS page in the batch renderer."""
    node = copy.copy(node)

    def filter_attrs(tag: Tag) -> None:
        style = parse_style(tag.get("style"))
        kept = {k: v for k, v in style.items() if k in KEEP_STYLE_PROPS}
        # vertical-align top/text-top/bottom/middle raise or lower text in a
        # sup-like way the target does not model; keep only true super/sub.
        va = kept.get("vertical-align", "")
        if va and not (va.startswith("super") or va.startswith("sub")
                       or va == "baseline"):
            del kept["vertical-align"]
        fs = kept.get("font-size", "")
        m = re.match(r"([\d.]+)\s*(px|pt)", fs)
        if m and float(m.group(1)) > (30 if m.group(2) == "px" else 22):
            kept["font-size"] = "22pt"  # cap: a fragment must fit one CSS page
        tag.attrs = {}
        if kept:
            tag["style"] = ";".join(f"{k}:{v}" for k, v in kept.items())

    def walk(tag: Tag) -> None:
        for child in list(tag.children):
            if isinstance(child, Comment):
                child.extract()
            elif isinstance(child, Tag):
                if (child.name in ("script", "style", "img", "table", "head", "link")
                        or is_hidden(child)):
                    child.extract()
                    continue
                walk(child)
                if child.name == "a" or child.name not in KEEP_TAGS:
                    child.unwrap()  # keep children (text), drop the tag
                    continue
                filter_attrs(child)
    walk(node)
    filter_attrs(node)  # the fragment root's own class/id/style too
    html = node.decode()
    return re.sub(r"\s+", " ", html).strip()


def leaf_blocks(soup: BeautifulSoup) -> list[Tag]:
    """Block elements with no nested blocks/tables — the region candidates."""
    out = []
    for elem in soup.find_all(BLOCK_TAGS):
        if elem.find_parent("table") is not None:
            continue
        if elem.find(list(BLOCK_TAGS | {"table"})) is not None:
            continue
        if is_hidden(elem) or any(is_hidden(a) for a in elem.find_parents(True)):
            continue
        out.append(elem)
    return out


def extract_fragments(html: bytes, source_url: str) -> list[dict]:
    """All acceptable fragments from one filing, in document order."""
    soup = BeautifulSoup(html, "lxml")
    blocks = leaf_blocks(soup)
    fragments: list[dict] = []
    consumed: set[int] = set()

    def build(elems: list[Tag]) -> dict | None:
        runs: list[tuple[str, tuple]] = []
        rendered: list[str] = []
        for j, e in enumerate(elems):
            if j:
                runs.append(("\n", (False, False, False, False)))
            inh = inherited_flags(e)
            collect_runs(e, apply_node_style(e, inh), runs)
            # Styling inherited from ancestors OUTSIDE the fragment must be
            # baked back in, or the target would claim styling the image
            # doesn't show (e.g. a <p> inside a bold wrapper div).
            piece = clean_for_render(e)
            for flag, tag in (("bold", "b"), ("strike", "s"),
                              ("italic", "i"), ("underline", "u")):
                if inh[flag]:
                    piece = f"<{tag}>{piece}</{tag}>"
            rendered.append(piece)
        md, has_marker = runs_to_markdown(runs)
        if "****" in md or "~~~~" in md:
            return None  # marker adjacency artifact; drop rather than repair
        return {"target": md, "render_html": "<br/>".join(rendered),
                "styled": has_marker, "source_url": source_url}

    for i, elem in enumerate(blocks):
        if id(elem) in consumed:
            continue
        text = re.sub(r"\s+", " ", elem.get_text()).strip()
        if not text or is_boilerplate(text):
            continue
        # Short header-like block: try to pair with the next content block —
        # the "bold risk label + definition" texture the fine-tune needs.
        if len(text) < 70:
            f0 = apply_node_style(elem, inherited_flags(elem))
            header_like = f0["bold"] or (text.upper() == text and len(text) > 5)
            if header_like and i + 1 < len(blocks):
                nxt = blocks[i + 1]
                ntext = re.sub(r"\s+", " ", nxt.get_text()).strip()
                if 40 <= len(ntext) <= 700 and not is_boilerplate(ntext):
                    frag = build([elem, nxt])
                    if frag and 60 <= len(frag["target"]) <= 900:
                        consumed.update({id(elem), id(nxt)})
                        fragments.append(frag)
                        continue
            if len(text) < 60:
                continue  # standalone short block: too small for a region
        if len(text) > 850:
            continue  # would risk overflowing one CSS page when rendered
        frag = build([elem])
        if frag and 60 <= len(frag["target"]) <= 900:
            fragments.append(frag)
    return fragments


# ------------------------------------------------------------- dedupe ----

def _shingles(text: str) -> frozenset:
    words = re.sub(r"\d", "0", text.lower()).split()
    return frozenset(tuple(words[i:i + 4]) for i in range(max(len(words) - 3, 1)))


def dedupe(frags: list[dict], threshold: float = 0.6) -> tuple[list[dict], int]:
    """Drop exact and near duplicates (Jaccard over word 4-grams). Filings
    share huge amounts of boilerplate; this gate is load-bearing."""
    kept: list[dict] = []
    kept_shingles: list[frozenset] = []
    seen_exact: set[str] = set()
    dropped = 0
    for f in frags:
        norm = re.sub(r"[\W\d]+", "", f["target"].lower())
        if norm in seen_exact:
            dropped += 1
            continue
        sh = _shingles(f["target"])
        dup = False
        for other in kept_shingles:
            inter = len(sh & other)
            if inter and inter / len(sh | other) >= threshold:
                dup = True
                break
        if dup:
            dropped += 1
            continue
        seen_exact.add(norm)
        kept.append(f)
        kept_shingles.append(sh)
    return kept, dropped


# ------------------------------------------------------------- rendering ----
# Copied from ourparser/finetune/generate_data.py:222-258 (render_batch) per
# task instruction — that file is a live training dependency and must not be
# imported or edited. One Chrome call renders a whole batch, one CSS page per
# region, rasterised at 150 DPI (the production pipeline's own DPI) and
# tight-cropped to ink.

FONTS = ['Georgia, serif', 'Helvetica, Arial, sans-serif',
         '"Times New Roman", serif', 'Verdana, sans-serif']


def render_batch(specs, out_paths, rng_styles) -> None:
    """One Chrome call for a whole batch: each region is its own CSS page,
    rasterised per page then tight-cropped. ~10x faster than per-region calls."""
    import PIL.Image, PIL.ImageChops
    pages = []
    for (html_body,), style in zip(specs, rng_styles):
        has_cjk = any('一' <= ch <= '鿿' for ch in html_body)
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
        # Stricter than the original's >=: any fragment tall enough to spill
        # onto a second CSS page would silently misalign every later
        # page<->fragment pair, corrupting labels. Fragment length caps in
        # extract_fragments make overflow impossible in practice; assert it.
        assert doc.page_count == len(out_paths), \
            f"page/fragment misalignment: {doc.page_count} pages, {len(out_paths)} regions"
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


# ------------------------------------------------------------ quality gates ----

def gate_blank_renders(image_paths: list[Path]) -> int:
    """Gate (a): EVERY image must have a non-None difference-from-white bbox."""
    import PIL.Image, PIL.ImageChops
    blanks = 0
    for p in image_paths:
        im = PIL.Image.open(p).convert("RGB")
        bg = PIL.Image.new("RGB", im.size, (255, 255, 255))
        if PIL.ImageChops.difference(im, bg).getbbox() is None:
            blanks += 1
            print(f"  BLANK RENDER: {p}")
    return blanks


def bold_texts_in_html(render_html: str) -> list[str]:
    """Independent locator for gate (b): texts inside bold-styled elements of
    the rendering HTML, found by direct DOM inspection (b/strong tags or
    font-weight style), NOT by reusing the target-derivation walker."""
    soup = BeautifulSoup(render_html, "lxml")
    found = []
    for tag in soup.find_all(True):
        name = tag.name.lower()
        fw = parse_style(tag.get("style")).get("font-weight", "")
        is_bold = (name in ("b", "strong", "h1", "h2", "h3", "h4", "h5", "h6")
                   or fw in ("bold", "bolder")
                   or (fw.isdigit() and int(fw) >= 600))
        if is_bold:
            found.append(re.sub(r"\s+", " ", tag.get_text()).strip())
    return found


def gate_bold_spans(rows: list[dict], frags: list[dict], rng: random.Random) -> int:
    """Gate (b): for 10 random styled samples, every **span** in the target
    must appear as text under a bold tag/style in the fragment HTML."""
    styled_idx = [i for i, r in enumerate(rows) if "**" in r["target"]]
    picks = rng.sample(styled_idx, min(10, len(styled_idx)))
    failures = 0
    for i in picks:
        spans = re.findall(r"\*\*(.+?)\*\*", rows[i]["target"])
        bolds = bold_texts_in_html(frags[i]["render_html"])
        # squashed comparison also covers adjacent bold tags the run-merger
        # fused into one **span** (whitespace lives outside the tags)
        squash = re.sub(r"\s", "", "".join(bolds))
        ok = all(any(s in b for b in bolds) or re.sub(r"\s", "", s) in squash
                 for s in spans)
        failures += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {rows[i]['image']}")
        print(f"    target : {rows[i]['target'][:160]!r}")
        print(f"    **spans: {spans}")
        print(f"    html-bold texts: {[b[:80] for b in bolds]}")
    return failures


# ------------------------------------------------------------------- main ----

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--n", type=int, default=300, help="target fragment count")
    ap.add_argument("--neg-frac", type=float, default=0.25,
                    help="share of no-styling negatives")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "edgar_data_sample"))
    ap.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    ap.add_argument("--per-filing-cap", type=int, default=40,
                    help="max fragments taken from any one filing (diversity)")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)

    # --- fetch ---------------------------------------------------------
    ciks = resolve_ciks(args.tickers.split(","))
    filings: list[dict] = []
    for ticker in sorted(ciks):
        for f in recent_filings(ciks[ticker]):
            f["ticker"] = ticker
            filings.append(f)
    print(f"filings selected: {len(filings)} "
          f"({sum(f['form'] == '10-K' for f in filings)} 10-K, "
          f"{sum(f['form'] == '10-Q' for f in filings)} 10-Q)")

    # --- extract + dedupe ------------------------------------------------
    all_frags: list[dict] = []
    yield_report: list[tuple[str, int, int]] = []
    for f in filings:
        html = cached_get(f["url"])
        frags = extract_fragments(html, f["url"])
        frags, dropped = dedupe(frags)          # within-filing dedupe
        rng.shuffle(frags)
        # pre-cap negatives only (they are abundant); styled fragments are the
        # scarce resource and all survive to global selection
        neg = [x for x in frags if not x["styled"]][: args.per_filing_cap * 3]
        frags = [x for x in frags if x["styled"]] + neg
        yield_report.append((f"{f['ticker']} {f['form']} {f['date']}",
                             len(frags), dropped))
        all_frags.extend(frags)
    all_frags, cross_dropped = dedupe(all_frags)  # cross-filing boilerplate
    print("\nfragment yield per filing (post within-filing dedupe):")
    for name, n_kept, n_dropped in yield_report:
        print(f"  {name}: {n_kept} kept, {n_dropped} near-dup dropped")
    print(f"cross-filing near-dups dropped: {cross_dropped}")

    # --- select: ~25% negatives, per-filing cap, deterministic ----------
    styled_pool = [f for f in all_frags if f["styled"]]
    neg_pool = [f for f in all_frags if not f["styled"]]
    rng.shuffle(styled_pool)
    rng.shuffle(neg_pool)

    def capped(pool: list[dict], k: int) -> list[dict]:
        per_src: dict[str, int] = {}
        picked = []
        for f in pool:
            if per_src.get(f["source_url"], 0) >= args.per_filing_cap:
                continue
            per_src[f["source_url"]] = per_src.get(f["source_url"], 0) + 1
            picked.append(f)
            if len(picked) == k:
                break
        return picked

    n_neg = round(args.n * args.neg_frac)
    chosen = capped(styled_pool, args.n - n_neg) + capped(neg_pool, n_neg)
    rng.shuffle(chosen)
    print(f"\nselected {len(chosen)} fragments "
          f"(styled pool {len(styled_pool)}, negative pool {len(neg_pool)})")

    # --- render ----------------------------------------------------------
    rows: list[dict] = []
    image_paths: list[Path] = []
    for start in range(0, len(chosen), 100):
        batch = chosen[start:start + 100]
        specs, paths, styles = [], [], []
        for j, frag in enumerate(batch):
            png = out / "images" / f"region_{start + j:05d}.png"
            specs.append((frag["render_html"],))
            paths.append(png)
            styles.append((rng.choice(FONTS), rng.choice([13, 14, 15, 16]),
                           rng.choice([420, 520, 620, 700]),
                           rng.choice(["left", "justify"])))
        render_batch(specs, paths, styles)
        image_paths.extend(paths)
    for j, frag in enumerate(chosen):
        rows.append({
            "image": str((out / "images" / f"region_{j:05d}.png").relative_to(out)),
            "prompt": PROMPT,
            "target": frag["target"],
            "source_url": frag["source_url"],
            "styled": frag["styled"],
        })

    (out / "data.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    # Sidecar with the rendering HTML per row — lets gates be re-run and
    # failures inspected without refetching filings. Not part of data.jsonl.
    (out / "fragments.jsonl").write_text(
        "\n".join(json.dumps({"image": r["image"], "render_html": f["render_html"]},
                             ensure_ascii=False)
                  for r, f in zip(rows, chosen)) + "\n")

    # --- gates ------------------------------------------------------------
    print("\n=== QUALITY GATES ===")
    print("(a) blank-render check over EVERY image:")
    blanks = gate_blank_renders(image_paths)
    print(f"  blank renders: {blanks} / {len(image_paths)} "
          f"-> {'PASS' if blanks == 0 else 'FAIL'}")

    print("(b) bold-span provenance, 10 random styled samples:")
    span_failures = gate_bold_spans(rows, chosen, random.Random(args.seed + 1))
    print(f"  bold-span failures: {span_failures} / 10 "
          f"-> {'PASS' if span_failures == 0 else 'FAIL'}")

    n_styled = sum(r["styled"] for r in rows)
    print(f"(c) dedupe: within-filing drops "
          f"{sum(d for _, _, d in yield_report)}, cross-filing drops {cross_dropped}")
    import collections
    marks = collections.Counter()
    for r in rows:
        marks["**"] += r["target"].count("**") // 2
        marks["~~"] += r["target"].count("~~") // 2
        marks["<sup>"] += r["target"].count("<sup>")
        marks["<sub>"] += r["target"].count("<sub>")
    print(f"(d) styled: {n_styled}  negatives: {len(rows) - n_styled} "
          f"({(len(rows) - n_styled) * 100 // max(len(rows), 1)}%)")
    print(f"    marker occurrences in targets: {dict(marks)}")
    print(f"\nwrote {len(rows)} rows -> {out / 'data.jsonl'}")
    if blanks or span_failures:
        raise SystemExit("QUALITY GATE FAILURE — see output above")


if __name__ == "__main__":
    main()
