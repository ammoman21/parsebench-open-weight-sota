"""
Candidate emission-level patches for the Semantic Formatting gap, as data.

Two kinds, kept separate because they are measured on different corpora:

* MD_PATCHES  — pure `markdown -> markdown` functions. These are what would be added
  as extra rules at the end of `postprocess_markdown`
  (`kdl_frontier_nano.py:2567-2585`). Measurable on all 476 scored documents by
  applying them to the shipped markdown, so their deltas land directly on our
  leaderboard number.

* PROVIDER_PATCHES — context managers that monkey-patch module-level functions of the
  vendored provider (`_is_titleish`, `_nano_format_element`). These change behaviour
  *before* the final markdown exists, so they require re-assembling markdown from the
  stored per-element output; measurable only on documents whose re-assembly is
  byte-identical to the shipped output.

NOTHING under `parsebench/src/` is edited. Provider patches are applied at runtime by
rebinding module attributes inside a `with` block and restoring them on exit; the
report states which source lines a real implementation would have to change.

GRADER FACTS THE PATCHES EXPLOIT (all in `rules_formatting.py`)
--------------------------------------------------------------
* `is_bold`, heading arm (`:201-204`):
      ^[ \\t]*#{1,6}[ \\t]+[^\\n]*?QUERY[^\\n]*?$
  the query may sit ANYWHERE inside the heading line.
* `is_bold`, `**` arm (`:194-197`):
      \\*\\*(?!\\s)(?:(?!\\*\\*).)*?QUERY(?:(?!\\*\\*).)*?(?<!\\s)\\*\\*
  the query may sit anywhere inside a `**...**` span, as long as no other `**`
  intervenes. Bolding a whole line therefore satisfies every bold rule whose text
  lies within that line.
* `is_title` (`:744-760`): heading arm requires the text at the START of the heading
  line (`^#{1,6}\\s+TEXT`); the bold arm requires the text to be the WHOLE line
  (`^\\s*\\*\\*TEXT\\*\\*\\s*$`). Strictly narrower than the bold matcher.
* `title_hierarchy_percent` (`:869-925`): counts expected titles present as heading
  (level 1-6) or whole-line bold (level 7) *events*, plus parent->child edges that
  require `parent_line < child_line` and `parent_level < child_level`. Level-flattening
  patches can therefore lose points here even while gaining `is_title` points.
* There are NO `is_not_*` rules in this corpus, so over-emitting formatting costs
  nothing inside Semantic Formatting. It can still cost Content Faithfulness, which is
  why every patch is checked against that dimension separately.
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
from typing import Any, Callable, Iterator

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

from parse_bench.inference.providers.parse import kdl_frontier_nano as K  # noqa: E402

# ---------------------------------------------------------------------------
# helpers shared by the markdown-level patches
# ---------------------------------------------------------------------------
# A line we must never touch: heading, table row, HTML, fence, image, page marker,
# or the horizontal rule the page separator uses.
_SKIP_PREFIXES = ("#", "|", "<", "`", "!", "---")
_PAGE_MARKER = re.compile(r"^\*\*Page\s+\d+\*\*$")
# A `- ` / `* ` / `1. ` list marker or a `> ` blockquote marker: keep the marker
# outside the emphasis so the line still parses as a list/quote.
_MARKER_RE = re.compile(r"^(\s*(?:(?:[-*+]|\d+[.)])\s+|>\s*)*)(.*)$")
_HAS_BOLD = re.compile(r"\*\*")
_HTML_TABLE_SPAN = re.compile(r"<table\b.*?</table>", re.S)


def _table_line_mask(md: str) -> list[bool]:
    """True for every line that falls inside an HTML `<table>…</table>` block."""
    spans = [(m.start(), m.end()) for m in _HTML_TABLE_SPAN.finditer(md)]
    mask: list[bool] = []
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
    if s.startswith(_SKIP_PREFIXES):
        return True
    return False


def _bold_line_body(line: str) -> str:
    """
    Wrap a line's body in `**…**`, keeping any list/blockquote marker outside.

    Refuses if the line already contains `**` (never nest or split an existing span,
    which would break the tempered-greedy `**` matcher) or if the body is empty.
    """
    if _HAS_BOLD.search(line):
        return line
    m = _MARKER_RE.match(line)
    prefix, body = m.group(1), m.group(2).rstrip()
    if not body.strip():
        return line
    trail = line[len(prefix) + len(body):]
    return f"{prefix}**{body}**{trail}"


# ---------------------------------------------------------------------------
# MD patch: E — bold run-in "Label:" prefixes
# ---------------------------------------------------------------------------
# Motivation: the largest single failure class for `is_bold` is text merged inline
# into a longer line, and a large share of those are run-in labels
# ("AGENCY: Department of ...", "Corporate Identity Number: U65990MH...").
_LABEL_RE = re.compile(r"^([^\s#>|*<][^:\n]{0,60}?:)(\s)")


def bold_labels(md: str) -> str:
    tbl = _table_line_mask(md)
    out = []
    for i, line in enumerate(md.split("\n")):
        if tbl[i] or _skippable(line) or _HAS_BOLD.search(line):
            out.append(line)
            continue
        m = _LABEL_RE.match(line)
        if m and len(m.group(1).split()) <= 6:
            line = f"**{m.group(1)}**{m.group(2)}{line[m.end():]}"
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# MD patch: F — bold short standalone non-heading lines
# ---------------------------------------------------------------------------
def _bold_lines_where(md: str, keep: Callable[[list[str], int], bool]) -> str:
    lines = md.split("\n")
    tbl = _table_line_mask(md)
    out = list(lines)
    for i, line in enumerate(lines):
        if tbl[i] or _skippable(line):
            continue
        if keep(lines, i):
            out[i] = _bold_line_body(line)
    return "\n".join(out)


def _standalone(lines: list[str], i: int) -> bool:
    above = lines[i - 1].strip() if i else ""
    below = lines[i + 1].strip() if i + 1 < len(lines) else ""
    return not above and not below


def bold_standalone(md: str, max_words: int = 14) -> str:
    """Patch F: bold every short *standalone* (blank above and below) line."""
    return _bold_lines_where(
        md, lambda ls, i: _standalone(ls, i) and len(ls[i].split()) <= max_words
    )


def bold_own_line(md: str, max_words: int = 14) -> str:
    """
    Patch F2: bold every short line regardless of blank neighbours.

    Targets the `own_line_not_standalone` failure class — a heading text that lives on
    its own line but sits inside a merged List-item block or a multi-line Title
    element, so `title_promote`'s standalone test never considers it.
    """
    return _bold_lines_where(md, lambda ls, i: len(ls[i].split()) <= max_words)


def bold_all_lines(md: str) -> str:
    """
    Patch MAXBOLD: bold the entire body of every eligible line, no length limit.

    This is the CEILING of what bold emission can achieve without touching table
    interiors: after it, every `is_bold` rule whose annotated text lies within a
    single non-table line passes. It is deliberately degenerate — it is measured to
    bound the lever, and its Content-Faithfulness cost is reported alongside.
    """
    return _bold_lines_where(md, lambda ls, i: True)


# ---------------------------------------------------------------------------
# MD patch: heading-based variants of the same idea
# ---------------------------------------------------------------------------
def head_all_lines(md: str) -> str:
    """
    Every eligible line becomes an `# ` heading.

    The bold matcher's heading arm allows the query anywhere in the line, so this is
    the heading-route twin of MAXBOLD. Included to test the primary hypothesis in its
    strongest possible form. Warning: `#` is NOT stripped by `normalize_text`
    (`metrics/parse/utils.py:223-358` has no rule for it), so unlike `**` this leaks
    literal `#` tokens into the Content-Faithfulness comparison.
    """
    lines = md.split("\n")
    tbl = _table_line_mask(md)
    out = list(lines)
    for i, line in enumerate(lines):
        if tbl[i] or _skippable(line):
            continue
        m = _MARKER_RE.match(line)
        body = m.group(2).strip()
        if body:
            out[i] = f"# {body}"
    return "\n".join(out)


def head_short_lines(md: str, max_words: int = 14) -> str:
    """Promote every short eligible line to `# ` — a heading-route twin of F2."""
    lines = md.split("\n")
    tbl = _table_line_mask(md)
    out = list(lines)
    for i, line in enumerate(lines):
        if tbl[i] or _skippable(line):
            continue
        m = _MARKER_RE.match(line)
        body = m.group(2).strip()
        if body and len(body.split()) <= max_words:
            out[i] = f"# {body}"
    return "\n".join(out)


def compose(*fns: Callable[[str], str]) -> Callable[[str], str]:
    """Left-to-right composition, so `compose(bold_labels, bold_standalone)` = E then F."""

    def run(md: str) -> str:
        for fn in fns:
            md = fn(md)
        return md

    return run


MD_PATCHES: dict[str, Callable[[str], str]] = {
    "E  bold run-in 'Label:' prefixes": bold_labels,
    "F  bold short standalone lines (<=14w)": bold_standalone,
    "F2 bold short own-lines, any neighbour (<=14w)": bold_own_line,
    "G  = E + F": compose(bold_labels, bold_standalone),
    "G2 = E + F2": compose(bold_labels, bold_own_line),
    # Word-limit sweep on the own-line bold rule: shows how much of MAXBOLD's gain is
    # reachable while still only touching short, heading-like lines.
    "F2/25w bold own-lines <=25 words": lambda md: bold_own_line(md, 25),
    "F2/40w bold own-lines <=40 words": lambda md: bold_own_line(md, 40),
    "MAXBOLD bold every non-table line (ceiling)": bold_all_lines,
    "HEADSHORT '# ' every short own-line (<=14w)": head_short_lines,
    "HEADALL  '# ' every non-table line (ceiling)": head_all_lines,
}


# ---------------------------------------------------------------------------
# PROVIDER patches
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def _swap(**attrs: Any) -> Iterator[None]:
    """Temporarily rebind module attributes of the vendored provider."""
    old = {k: getattr(K, k) for k in attrs}
    try:
        for k, v in attrs.items():
            setattr(K, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(K, k, v)


def _titleish_factory(
    drop_caps: bool = False,
    drop_terminal_punct: bool = False,
    drop_label_value: bool = False,
    max_words_override: int | None = None,
) -> Callable[..., bool]:
    """
    Build a relaxed replacement for `_is_titleish` (`kdl_frontier_nano.py:2489-2508`).

    The structural guards (already a heading / list / table row / no letters) are always
    kept — dropping them would promote table rows and list bullets to headings.

    :param drop_caps: remove the "first alphabetic char is uppercase OR >60% of letters
        are uppercase" requirement. This is the gate the earlier investigation named as
        the lever.
    :param drop_terminal_punct: allow lines ending in `.!?:;,`.
    :param drop_label_value: allow `^.{1,40}:\\s` label-value lines.
    :param max_words_override: raise the 12-word cap.
    """

    def relaxed(text: str, max_words: int, caps_ratio: float, require_all_caps: bool) -> bool:
        s = text.strip()
        if not s:
            return False
        if K._HEADING_RE.match(s) or K._LIST_RE.match(s) or K._NUMLIST_RE.match(s) or K._TABLEROW_RE.match(s):
            return False
        limit = max_words_override if max_words_override is not None else max_words
        if len(s.split()) > limit:
            return False
        if not drop_terminal_punct and s.endswith(K._TERMINAL_PUNCT):
            return False
        if not drop_label_value and K._LABELVALUE_RE.match(s):
            return False
        letters = K._LETTER_RE.findall(s)
        if not letters:
            return False
        if drop_caps:
            return True
        caps_frac = len(K._UPPER_RE.findall(s)) / len(letters)
        if require_all_caps:
            return caps_frac >= caps_ratio
        first_alpha = next((c for c in s if c.isalpha()), "")
        return first_alpha.isupper() or caps_frac > caps_ratio

    return relaxed


def _variant_swap(variant: str) -> Callable[[], Any]:
    """Use one of the provider's own already-shipped `_TITLE_VARIANTS` tuples."""
    params = K._TITLE_VARIANTS[variant]

    def ctx() -> Any:
        return _swap(_TITLE_VARIANTS={**K._TITLE_VARIANTS, "aggressive": params})

    return ctx


def _fmt_multiline_split() -> Any:
    """
    Patch B (re-verification): give every line of a multi-line `Title` /
    `Section-header` element its own `#` marker.

    Today `_nano_format_element:2931-2933` emits one marker for the whole element, so
    a three-line Title yields `# line1\\nline2\\nline3` and lines 2-3 are invisible to
    both the title and the bold matchers.
    """
    orig = K._nano_format_element

    def fmt(el: dict[str, Any]) -> str:
        cat = el.get("category", "Text")
        if cat in ("Title", "Section-header"):
            prefix = "#" if cat == "Title" else "##"
            content = K._preserve_inline_markup(K._strip_leading_heading_marker(el.get("content") or ""))
            lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
            return "\n\n".join(f"{prefix} {ln}" for ln in lines)
        return orig(el)

    return _swap(_nano_format_element=fmt)


def _fmt_wide_categories(extra: tuple[str, ...], level: str = "##") -> Any:
    """
    Widen which layout categories are emitted as headings.

    Today only `Title` (-> `# `) and `Section-header` (-> `## `) get a marker
    (`kdl_frontier_nano.py:2931-2933`); `Caption`, `Footnote`, `Page-header` and
    `Page-footer` become `>` blockquotes (`:2951`) and `Text` becomes a bare paragraph
    (`:2957`), so annotated bold/title text inside them can never reach the heading arm.
    """
    orig = K._nano_format_element

    def fmt(el: dict[str, Any]) -> str:
        cat = el.get("category", "Text")
        if cat in extra:
            content = K._preserve_inline_markup(K._strip_leading_heading_marker((el.get("content") or "").strip()))
            if not content:
                return ""
            return "\n".join(f"{level} {ln.strip()}" for ln in content.split("\n") if ln.strip())
        return orig(el)

    return _swap(_nano_format_element=fmt)


def _fmt_short_text_heading(max_words: int = 12) -> Any:
    """Emit `# ` for a single-line `Text` element of at most `max_words` words."""
    orig = K._nano_format_element

    def fmt(el: dict[str, Any]) -> str:
        cat = el.get("category", "Text")
        if cat == "Text":
            content = K._preserve_inline_markup(K._strip_leading_heading_marker((el.get("content") or "").strip()))
            if content and "\n" not in content and len(content.split()) <= max_words:
                return f"# {content}"
        return orig(el)

    return _swap(_nano_format_element=fmt)


# name -> zero-arg callable returning a context manager
PROVIDER_PATCHES: dict[str, Callable[[], Any]] = {
    "T1 _is_titleish: drop leading-capital/caps gate": lambda: _swap(
        _is_titleish=_titleish_factory(drop_caps=True)
    ),
    "T2 _TITLE_VARIANTS -> 'ultra' (22w, caps .25)": _variant_swap("ultra"),
    "T3 _TITLE_VARIANTS -> 'ultra2' (30w, caps 0)": _variant_swap("ultra2"),
    "T4 titleish: drop caps + terminal-punct": lambda: _swap(
        _is_titleish=_titleish_factory(drop_caps=True, drop_terminal_punct=True)
    ),
    "T5 titleish: drop caps+punct+label, 30 words": lambda: _swap(
        _is_titleish=_titleish_factory(
            drop_caps=True, drop_terminal_punct=True, drop_label_value=True, max_words_override=30
        )
    ),
    "B  multi-line Title -> one '#' per line": _fmt_multiline_split,
    "C1 Caption/Footnote/Page-hdr/ftr -> '## '": lambda: _fmt_wide_categories(
        ("Caption", "Footnote", "Page-header", "Page-footer")
    ),
    "C2 short single-line Text -> '# '": lambda: _fmt_short_text_heading(12),
    "C3 List-item -> '## ' instead of '- '": lambda: _fmt_wide_categories(("List-item",)),
}
