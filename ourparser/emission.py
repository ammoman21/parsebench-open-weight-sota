"""
Patched markdown *emission* for the KDL-Frontier-Parser-nano ParseBench pipeline.

WHAT THIS FILE IS
-----------------
ParseBench is LlamaIndex's document-parsing benchmark. `KDL-Frontier-Parser-nano` is
the open-weight pipeline whose published row we reproduced (72.65 overall against a
published 76.36). Its vendored implementation lives at
`parsebench/src/parse_bench/inference/providers/parse/kdl_frontier_nano.py` (cited
below as `K:<line>`) and **is not modified by us**. This module re-implements the small
part of that pipeline that turns already-recognised page elements into a markdown
string, with a fixed, explicitly-configured set of changes.

Everything here is a pure function of the element list. No network, no randomness, no
wall-clock dependence: the same elements always produce the same markdown.

PLAIN-LANGUAGE GLOSSARY (terms used below, defined once)
-------------------------------------------------------
* **element** — one detected region of a page, as a dict with `category` (e.g. `Title`,
  `Text`, `Table`), `bbox` (its bounding box as `[x1, y1, x2, y2]` in 0..1 page
  fractions), `content` (the recognised text), `layout_order` and `page_number`.
* **layout stage** — the model's first pass, which emits one raw label plus a bounding
  box per region. Raw labels are lowercase/underscored (`title`, `list_item`,
  `page_number`, ...) and are translated to the pipeline's own category names by
  `K.NATIVE_LAYOUT_CATEGORY_MAP` (`K:545-572`).
* **Semantic Formatting** — one of the benchmark's five scored dimensions: "was the
  meaningful markup (bold, headings, superscript, LaTeX, code fences) preserved?".
* **`title_hierarchy_percent`** — a Semantic-Formatting rule that requires, for each
  parent/child pair of expected headings, that the parent appear earlier in the
  document *and* at a shallower heading depth (`# ` is shallower than `## `).
* **run-in label** — a bold lead-in at the start of a paragraph, as in
  "**AGENCY:** Department of Transport". The label is bold in the source PDF; the
  pipeline emits it as plain text.

THE FOUR CHANGES, AND WHY EACH IS A DEFECT FIX RATHER THAN SCORE-CHASING
-----------------------------------------------------------------------
(a) `SECTION_HEADER_MAP_FIX` — add `"section_header": "Section-header"` to the layout
    label map. `K.NATIVE_LAYOUT_CATEGORY_MAP` (`K:545-572`) has no `section_header`
    key, and an unrecognised label falls through `_canonicalize_category` (`K:242-246`)
    to `Text`, because the canonical spelling is hyphenated (`Section-header`) while
    every key in that map is underscored. `Section-header` is therefore the only
    category that would ever emit `## ` (`K:2931-2933`) and it is never produced —
    0 occurrences across all 2,078 stored run artifacts. The `##` branch is dead code.
    IMPORTANT MEASUREMENT CAVEAT: the stored artifacts persist only the *canonical*
    category, never the model's raw label, so this fix cannot be measured by replay —
    see `parsebench/scripts/genuine_set_measure.py` and the report.

(b) `BBOX_HEADING_LEVELS` — derive a heading depth for each `Title` element from the
    height of its bounding box, so that headings are not all `# `. The pipeline does no
    hierarchy inference at all; the geometry it needs is already in its own layout
    output. Without this, every heading is depth 1 and the "parent shallower than
    child" half of `title_hierarchy_percent` is unsatisfiable by construction.

(c) `BOLD_RUN_IN_LABELS` — wrap a leading `Label:` run in `**...**`. These runs are
    bold in the source documents and the pipeline drops the markup entirely.

(d) `RELAXED_TITLE_GATE` — `K._is_titleish` (`K:2489-2508`) decides whether a
    standalone line is promoted to a `# ` heading. It vetoes any line ending in
    `.!?:;,` and any line matching `^.{1,40}:\\s`. Both vetoes reject genuine headings
    ("1. Scope of Works:", "Notes:"). This change drops those two vetoes only, keeps
    every other guard including the leading-capital / capitalisation-ratio requirement,
    and lowers the risk of sweeping in body text by capping promoted lines at 20 words
    (the shipped cap is 12; an earlier exploration used 30, which we rejected as loose).

Two further changes are implemented here but are **NOT part of the submitted set**;
they exist so the "aggressive" comparison in the writeup is measured with the same code
rather than inherited from an earlier exploration:

  * `SHORT_TEXT_HEADINGS` — promote a short single-line `Text` element to `# `.
  * `LIST_ITEM_HEADINGS`  — emit `List-item` elements as `## ` instead of `- `.

Both raise the score by making non-headings look like headings, which the benchmark's
bold check credits (an annotated run counted as bold if it appears anywhere on a
`#`-heading line, since headings render bold). This pipeline emits no inline bold
markup of its own, so that route is the only way it earns bold credit at all, and
promoting non-headings harvests that credit without detecting any bold. That is a
property of the scorer, not of the parser, which is why these two are disclosed rather
than submitted.

FAITHFULNESS OF THE PORTS
-------------------------
`assemble_markdown`, `title_promote` and `postprocess_markdown` below are ports of
`K._nano_assemble_markdown` (`K:2959-3012`), `K.title_promote` (`K:2511-2543`) and
`K.postprocess_markdown` (`K:2567-2585`) with one injected seam each. Ports drift, so
`parsebench/scripts/genuine_set_measure.py` asserts on every stored document that
running them with the *vendored* seam reproduces the vendored functions byte for byte.
If that assertion ever fails, the port has drifted and the measurement is void.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

# The vendored pipeline is imported, never edited. `PARSEBENCH_SRC` may be set to point
# at a checkout in another location.
_DEFAULT_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "parsebench", "src"
)
_SRC = os.environ.get("PARSEBENCH_SRC", _DEFAULT_SRC)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from parse_bench.inference.providers.parse import kdl_frontier_nano as K  # noqa: E402

# --------------------------------------------------------------------------------------
# (a) layout label map fix
# --------------------------------------------------------------------------------------
# One added key. `Section-header` is the pipeline's own canonical name (`K:102`) and the
# only category its formatter renders as `## ` (`K:2931-2933`).
PATCHED_NATIVE_LAYOUT_CATEGORY_MAP: Dict[str, str] = {
    **K.NATIVE_LAYOUT_CATEGORY_MAP,
    "section_header": "Section-header",
}


# --------------------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class EmissionConfig:
    """
    Which emission changes are active. Frozen so a configuration cannot be mutated
    half-way through a run.

    :param section_header_map_fix: change (a). Affects live inference only; it cannot be
        exercised by replay because stored artifacts do not persist the model's raw
        layout label.
    :param bbox_heading_levels: change (b). `None` disables it; otherwise the maximum
        heading depth to assign (4 = `#` .. `####`).
    :param bold_run_in_labels: change (c).
    :param relaxed_title_gate_max_words: change (d). `None` keeps the shipped gate;
        otherwise drop the terminal-punctuation and label-value vetoes and cap promoted
        lines at this many words.
    :param short_text_heading_max_words: NOT SUBMITTED. Promote a single-line `Text`
        element of at most this many words to `# `.
    :param list_item_headings: NOT SUBMITTED. Emit `List-item` as `## `.
    """

    section_header_map_fix: bool = False
    bbox_heading_levels: int | None = None
    bold_run_in_labels: bool = False
    relaxed_title_gate_max_words: int | None = None
    short_text_heading_max_words: int | None = None
    list_item_headings: bool = False


#: The vendored pipeline's behaviour, for paired baselines.
BASELINE = EmissionConfig()

#: Submitted set without the borderline gate relaxation: changes (a) + (b) + (c).
GENUINE_ABC = EmissionConfig(
    section_header_map_fix=True,
    bbox_heading_levels=4,
    bold_run_in_labels=True,
)

#: Submitted set with the borderline gate relaxation: changes (a) + (b) + (c) + (d).
GENUINE_ABCD = EmissionConfig(
    section_header_map_fix=True,
    bbox_heading_levels=4,
    bold_run_in_labels=True,
    relaxed_title_gate_max_words=20,
)


def aggressive(base: EmissionConfig) -> EmissionConfig:
    """
    Disclosed-but-not-submitted set: `base` plus the two category promotions.

    12 words is the pipeline's own "aggressive" heading word cap (`K:2483`), reused here
    so the threshold is not a number we chose.
    """
    return EmissionConfig(
        section_header_map_fix=base.section_header_map_fix,
        bbox_heading_levels=base.bbox_heading_levels,
        bold_run_in_labels=base.bold_run_in_labels,
        relaxed_title_gate_max_words=base.relaxed_title_gate_max_words,
        short_text_heading_max_words=12,
        list_item_headings=True,
    )


# --------------------------------------------------------------------------------------
# (b) heading depth from bounding-box height
# --------------------------------------------------------------------------------------
def heading_levels_by_bbox(
    elements: List[Dict[str, Any]], max_level: int = 4
) -> Dict[int, int]:
    """
    Assign a heading depth 1..`max_level` to every `Title` element of one document.

    Taller bounding box = more prominent heading = shallower depth. Depths come from the
    *rank* of the distinct rounded box heights within the document, not from absolute
    sizes, so the result does not depend on page size or render DPI. Ties share a depth.

    Deterministic and side-effect free: returns `{index in elements -> depth}` rather
    than writing to the element dicts, which keeps the elements bit-identical and so
    keeps the benchmark's Visual Grounding dimension (built from element `category`,
    `bbox` and `content` at `K:3287-3296`) provably untouched.
    """
    heights: List[Tuple[int, float]] = []
    for i, el in enumerate(elements):
        if el.get("category") != "Title":
            continue
        bb = el.get("bbox")
        if not bb or len(bb) < 4:
            continue
        heights.append((i, abs(float(bb[3]) - float(bb[1]))))
    if not heights:
        return {}
    distinct = sorted({round(h, 4) for _, h in heights}, reverse=True)
    rank = {h: min(r + 1, max_level) for r, h in enumerate(distinct)}
    return {i: rank[round(h, 4)] for i, h in heights}


# --------------------------------------------------------------------------------------
# element -> markdown
# --------------------------------------------------------------------------------------
def format_element(el: Dict[str, Any], cfg: EmissionConfig, level: int | None) -> str:
    """
    Render one element, delegating everything we do not change to the vendored formatter.

    Only three branches differ from `K._nano_format_element` (`K:2926-2957`):
      * a `Title` element with an assigned depth gets that many `#` characters;
      * (not submitted) a short single-line `Text` element becomes `# `;
      * (not submitted) a `List-item` element becomes `## ` instead of `- `.

    :param level: heading depth from `heading_levels_by_bbox`, or None.
    """
    category = el.get("category", "Text")

    if category == "Title" and level:
        body = K._preserve_inline_markup(
            K._strip_leading_heading_marker(el.get("content") or "")
        )
        return f"{'#' * int(level)} {body}"

    if category == "Text" and cfg.short_text_heading_max_words is not None:
        content = K._preserve_inline_markup(
            K._strip_leading_heading_marker((el.get("content") or "").strip())
        )
        if (
            content
            and "\n" not in content
            and len(content.split()) <= cfg.short_text_heading_max_words
        ):
            return f"# {content}"

    if category == "List-item" and cfg.list_item_headings:
        content = K._preserve_inline_markup(
            K._strip_leading_heading_marker((el.get("content") or "").strip())
        )
        if not content:
            return ""
        return "\n".join(f"## {ln.strip()}" for ln in content.split("\n") if ln.strip())

    return K._nano_format_element(el)


def assemble_markdown(
    elements: List[Dict[str, Any]],
    format_fn: Callable[[Dict[str, Any], int | None], str],
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Port of `K._nano_assemble_markdown` (`K:2959-3012`) with the per-element formatter
    injected, so our `format_element` can be used without editing the vendored file.

    Behaviour copied verbatim: sort by (page, layout_order); drop elements with an
    invalid page number; group runs of contiguous same-page `List-item` elements into a
    single block; drop empty blocks; insert `---\\n\\n**Page N**` separators between
    pages of the whole-document string only.

    `format_fn` receives `(element, heading_depth_or_None)`.

    :return: (whole-document markdown, per-page markdown records)
    """
    levels = _levels_for(elements, format_fn)

    valid = [
        (i, e)
        for i, e in sorted(
            enumerate(elements),
            key=lambda p: (p[1].get("page_number", 1), p[1].get("layout_order", 0)),
        )
        if isinstance(e.get("page_number"), int)
        and not isinstance(e.get("page_number"), bool)
        and e.get("page_number", 0) >= 1
    ]

    blocks: List[Tuple[int, str]] = []
    index = 0
    while index < len(valid):
        idx, el = valid[index]
        page = el["page_number"]
        if el.get("category") == "List-item":
            items = []
            while (
                index < len(valid)
                and valid[index][1].get("category") == "List-item"
                and valid[index][1]["page_number"] == page
            ):
                j, item = valid[index]
                formatted = format_fn(item, levels.get(j))
                if formatted:
                    items.append(formatted)
                index += 1
            content = "\n".join(items).strip()
        else:
            content = format_fn(el, levels.get(idx)).strip()
            index += 1
        if content:
            blocks.append((page, content))

    md_parts: List[str] = []
    current_page: int | None = None
    for page, content in blocks:
        if current_page is not None and page != current_page:
            md_parts.append(f"---\n\n**Page {page}**")
        md_parts.append(content)
        current_page = page

    pages_md: Dict[int, List[str]] = {}
    for page, content in blocks:
        pages_md.setdefault(page, []).append(content)
    markdown_pages = [
        {"page_number": page, "content": "\n\n".join(parts)}
        for page, parts in sorted(pages_md.items())
    ]
    return "\n\n".join(md_parts), markdown_pages


def _levels_for(
    elements: List[Dict[str, Any]],
    format_fn: Callable[[Dict[str, Any], int | None], str],
) -> Dict[int, int]:
    """Heading depths for `assemble_markdown`, or none when levels are disabled."""
    cfg = getattr(format_fn, "emission_config", None)
    if cfg is None or cfg.bbox_heading_levels is None:
        return {}
    return heading_levels_by_bbox(elements, cfg.bbox_heading_levels)


def formatter_for(cfg: EmissionConfig) -> Callable[[Dict[str, Any], int | None], str]:
    """Bind a configuration to a `(element, level) -> markdown` callable."""

    def fmt(el: Dict[str, Any], level: int | None) -> str:
        return format_element(el, cfg, level)

    fmt.emission_config = cfg  # type: ignore[attr-defined]
    return fmt


#: The vendored formatter, wrapped to the injected signature. Used by the drift test to
#: prove `assemble_markdown` is a faithful port, and as the baseline in paired
#: comparisons.
def vendored_formatter(el: Dict[str, Any], level: int | None) -> str:
    return K._nano_format_element(el)


# --------------------------------------------------------------------------------------
# (d) relaxed heading gate
# --------------------------------------------------------------------------------------
def is_titleish_relaxed(
    text: str,
    max_words: int,
    caps_ratio: float,
    require_all_caps: bool,
    *,
    word_cap: int = 20,
) -> bool:
    """
    Replacement for `K._is_titleish` (`K:2489-2508`) with exactly two vetoes removed.

    Kept, unchanged from the vendored gate: refuse a line that is already a heading, a
    bullet, a numbered item or a table row; refuse a line with no ASCII letters; and
    require either a leading capital letter or a capitalisation ratio above
    `caps_ratio`.

    Removed: the "ends with `.!?:;,`" veto (`K:2496-2497`) and the
    "`^.{1,40}:\\s` looks like a label/value pair" veto (`K:2498-2499`). Both reject
    genuine headings such as "Notes:" or "3. Scope of works:".

    Replaced: the shipped 12-word cap becomes `word_cap` (20). Raising the cap admits
    longer headings; leaving it unbounded would sweep in body sentences, which is what
    the terminal-punctuation veto had been standing in for.

    The `max_words` argument is accepted and deliberately ignored so the signature
    matches the vendored gate, which `title_promote` calls positionally.
    """
    s = text.strip()
    if not s:
        return False
    if (
        K._HEADING_RE.match(s)
        or K._LIST_RE.match(s)
        or K._NUMLIST_RE.match(s)
        or K._TABLEROW_RE.match(s)
    ):
        return False
    if len(s.split()) > word_cap:
        return False
    letters = K._LETTER_RE.findall(s)
    if not letters:
        return False
    caps_frac = len(K._UPPER_RE.findall(s)) / len(letters)
    if require_all_caps:
        return caps_frac >= caps_ratio
    first_alpha = next((c for c in s if c.isalpha()), "")
    return first_alpha.isupper() or caps_frac > caps_ratio


TitleGate = Callable[[str, int, float, bool], bool]


def title_promote(md: str, gate: TitleGate, variant: str = "aggressive") -> str:
    """
    Port of `K.title_promote` (`K:2511-2543`) with the accept/reject gate injected.

    Verbatim behaviour: skip fenced code blocks; consider only lines that are
    "standalone" (blank line, or document edge, both above and below); never promote the
    `**Page N**` separator; unwrap a `> ` blockquote and promote its inner text if the
    gate accepts it.
    """
    if not md:
        return md
    max_words, caps_ratio, require_all_caps = K._TITLE_VARIANTS[variant]
    do_promote = variant != "deblockquote_only"

    lines = md.split("\n")
    n = len(lines)
    out = list(lines)
    in_fence = False
    for i, raw in enumerate(lines):
        if K._FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        above = lines[i - 1] if i > 0 else ""
        below = lines[i + 1] if i + 1 < n else ""
        standalone = (i == 0 or above.strip() == "") and (i + 1 >= n or below.strip() == "")
        if not standalone:
            continue
        if K._PAGE_MARKER_RE.match(raw.strip()):
            continue
        bq = K._BLOCKQUOTE_RE.match(raw)
        if bq:
            inner = bq.group(1)
            if gate(inner, max_words, caps_ratio, require_all_caps):
                out[i] = ("# " + inner.strip()) if do_promote else inner.strip()
            continue
        if do_promote and gate(raw, max_words, caps_ratio, require_all_caps):
            out[i] = "# " + raw.strip()
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# (c) bold run-in `Label:` prefixes
# --------------------------------------------------------------------------------------
# A line whose first token run is a short label ending in a colon, followed by
# whitespace and then the value. Deliberately narrow: at most 60 characters and at most
# 6 words in the label, no colon inside it, and the line may not begin with a markdown
# structural character.
_LABEL_RE = re.compile(r"^([^\s#>|*<][^:\n]{0,60}?:)(\s)")
_HAS_BOLD = re.compile(r"\*\*")
_HTML_TABLE_SPAN = re.compile(r"<table\b.*?</table>", re.S)
_PAGE_MARKER = re.compile(r"^\*\*Page\s+\d+\*\*$")
#: Lines we never touch: heading, pipe-table row, HTML, code fence, image, page rule.
_SKIP_PREFIXES = ("#", "|", "<", "`", "!", "---")


def _table_line_mask(md: str) -> List[bool]:
    """True for each line that lies inside an HTML `<table>...</table>` block."""
    spans = [(m.start(), m.end()) for m in _HTML_TABLE_SPAN.finditer(md)]
    mask: List[bool] = []
    pos = 0
    for line in md.split("\n"):
        mask.append(any(a <= pos < b for a, b in spans))
        pos += len(line) + 1
    return mask


def _skippable(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if _PAGE_MARKER.match(s):
        return True
    return s.startswith(_SKIP_PREFIXES)


def bold_run_in_labels(md: str) -> str:
    """
    Wrap a leading `Label:` run of each paragraph in `**...**`.

    Never touches a line inside a table, a heading, a code fence, an HTML block, or a
    line that already contains `**` (nesting or splitting an existing bold span would
    break both the markdown and the benchmark's bold matcher, which refuses a span with
    another `**` inside it).
    """
    tbl = _table_line_mask(md)
    out: List[str] = []
    for i, line in enumerate(md.split("\n")):
        if tbl[i] or _skippable(line) or _HAS_BOLD.search(line):
            out.append(line)
            continue
        m = _LABEL_RE.match(line)
        if m and len(m.group(1).split()) <= 6:
            line = f"**{m.group(1)}**{m.group(2)}{line[m.end():]}"
        out.append(line)
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# document-level post-processing
# --------------------------------------------------------------------------------------
def postprocess_markdown(md: str, cfg: EmissionConfig, *, title_variant: str = "aggressive") -> str:
    """
    Port of `K.postprocess_markdown` (`K:2567-2585`): `header_mark` -> `quote_fold` ->
    `title_promote`, each wrapped so one failing rule never discards the document, and
    all rules skipped on a runaway document.

    Two seams: `title_promote` uses our gate when change (d) is enabled, and change (c)
    is appended as a final rule. (c) runs last so it sees the promoted headings and
    leaves them alone.
    """
    if not md or K._looks_runaway(md):
        return md
    gate: TitleGate = K._is_titleish
    if cfg.relaxed_title_gate_max_words is not None:
        cap = cfg.relaxed_title_gate_max_words

        def gate(text: str, max_words: int, caps_ratio: float, require_all_caps: bool) -> bool:
            return is_titleish_relaxed(
                text, max_words, caps_ratio, require_all_caps, word_cap=cap
            )

    try:
        md = K.header_mark(md)
    except Exception:  # noqa: BLE001 — never fail a document on a post-processing rule
        pass
    try:
        md = K.quote_fold(md)
        md = title_promote(md, gate, variant=title_variant)
    except Exception:  # noqa: BLE001
        pass
    if cfg.bold_run_in_labels:
        try:
            md = bold_run_in_labels(md)
        except Exception:  # noqa: BLE001
            pass
    return md


def build_markdown(
    elements: List[Dict[str, Any]], cfg: EmissionConfig
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Elements -> (whole-document markdown, per-page markdown records).

    This is the single entry point used by both the live provider
    (`ourparser.provider`) and the no-GPU replay measurement
    (`parsebench/scripts/genuine_set_measure.py`), which is what makes the replay number
    a statement about the shipped code rather than about a throwaway patch.
    """
    fmt = formatter_for(cfg)
    full_md, markdown_pages = assemble_markdown(elements, fmt)
    full_md = postprocess_markdown(full_md, cfg)
    for page in markdown_pages:
        page["content"] = postprocess_markdown(page["content"], cfg)
    return full_md, markdown_pages


def build_markdown_vendored(elements: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Baseline path through *our* ports with the vendored seams — used by the drift test."""
    full_md, markdown_pages = assemble_markdown(elements, vendored_formatter)
    full_md = postprocess_markdown(full_md, BASELINE)
    for page in markdown_pages:
        page["content"] = postprocess_markdown(page["content"], BASELINE)
    return full_md, markdown_pages
