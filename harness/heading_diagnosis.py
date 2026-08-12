"""
Deliverable 2: diagnose heading emission for `kdl_frontier_nano`.

CONTEXT. The pipeline never emits inline bold markup (`**`, `<b>`), so every point of
`is_bold` credit arrives through the *heading arm* of the bold matcher
(`rules_formatting.py:201-204`):

    ^[ \\t]*#{1,6}[ \\t]+[^\\n]*?QUERY[^\\n]*?[ \\t]*(?:#+[ \\t]*)?$

i.e. "a markdown heading line that contains the annotated text counts as bold".
Semantic Formatting is therefore in practice a function of *which lines get a `#`*.

WHAT THIS SCRIPT MEASURES.
  1. How many `#` heading lines we emit, at what levels, and where they came from
     (element-level `Title`/`Section-header` markers vs the document-level
     `title_promote` pass).
  2. For every failing `is_bold` and `is_title` rule, why the annotated text is not on
     a heading line. Reasons, in the order they are tested:

       missing            the text is not in the markdown at all (recognition or
                          layout failure — no emission change can help)
       inline_merged      the text is inside a longer line together with other text,
                          so the line is not a candidate for heading promotion
       in_table           the text only appears inside an HTML `<table>` block
       standalone_gated   the text IS its own standalone line but `_is_titleish`
                          rejected the line; sub-broken down by which gate fired
       standalone_other   its own standalone line, `_is_titleish` accepts it, yet no
                          heading — e.g. inside a fenced code region, or a
                          `**Page N**` marker, or a `>`-blockquote line
       already_heading    the line IS a heading but the rule still failed (a matcher
                          subtlety, e.g. the text spans two lines of a multi-line
                          heading element)

  3. The element-category picture: which layout categories host the annotated bold /
     title text, since only `Title` and `Section-header` get a `#` at emission time
     (`kdl_frontier_nano.py:2931-2933`).

Everything is read from stored artifacts. No inference.

Run:  ../.venv/bin/python scripts/heading_diagnosis.py
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys

import semfmt_lib as L

sys.path.insert(0, os.path.join(L.PB_ROOT, "src"))
from parse_bench.evaluation.metrics.parse.rules_formatting import (  # noqa: E402
    FormattingRule,
    _make_markup_tolerant,
)
from parse_bench.inference.providers.parse import kdl_frontier_nano as K  # noqa: E402

HEADING_RE = re.compile(r"^[ \t]*(#{1,6})[ \t]+")
TABLE_BLOCK_RE = re.compile(r"<table\b.*?</table>", re.S)


def norm_loose(s: str) -> str:
    """Case/whitespace-insensitive key for locating rule text inside a line."""
    return re.sub(r"\s+", " ", s).strip().lower()


def titleish_reason(line: str) -> str:
    """
    Which `_is_titleish` gate rejects `line` under the shipped "aggressive" variant?

    Mirrors `_is_titleish` (kdl_frontier_nano.py:2489-2508) branch for branch, with
    params `_TITLE_VARIANTS["aggressive"] = (max_words=12, caps_ratio=0.60,
    require_all_caps=False)` (`:2481`). Returns "accept" if the gate passes.
    """
    max_words, caps_ratio, require_all_caps = K._TITLE_VARIANTS["aggressive"]
    s = line.strip()
    if not s:
        return "empty"
    if K._HEADING_RE.match(s):
        return "looks_like_heading"
    if K._LIST_RE.match(s) or K._NUMLIST_RE.match(s):
        return "looks_like_list"
    if K._TABLEROW_RE.match(s):
        return "looks_like_table_row"
    if len(s.split()) > max_words:
        return f"too_many_words(>{max_words})"
    if s.endswith(K._TERMINAL_PUNCT):
        return "ends_with_terminal_punct"
    if K._LABELVALUE_RE.match(s):
        return "label_value_pattern"
    letters = K._LETTER_RE.findall(s)
    if not letters:
        return "no_ascii_letters"
    caps_frac = len(K._UPPER_RE.findall(s)) / len(letters)
    first_alpha = next((c for c in s if c.isalpha()), "")
    if require_all_caps:
        return "accept" if caps_frac >= caps_ratio else "caps_ratio"
    if first_alpha.isupper() or caps_frac > caps_ratio:
        return "accept"
    return "leading_capital_gate"  # lower-case initial AND caps ratio <= 0.60


def is_standalone(lines: list[str], i: int) -> bool:
    """`title_promote`'s standalone test (kdl_frontier_nano.py:2524-2527)."""
    n = len(lines)
    above_blank = i == 0 or lines[i - 1].strip() == ""
    below_blank = i + 1 >= n or lines[i + 1].strip() == ""
    return above_blank and below_blank


def find_lines(lines: list[str], needle_norm: str) -> list[int]:
    """Indices of lines whose loose-normalised form contains `needle_norm`."""
    return [i for i, ln in enumerate(lines) if needle_norm and needle_norm in norm_loose(ln)]


def classify(md: str, text: str, rule_passed: bool) -> tuple[str, str]:
    """
    :return: (reason, detail) explaining why `text` is/is not on a heading line.
    """
    lines = md.split("\n")
    needle = norm_loose(text)
    hits = find_lines(lines, needle)

    if not hits:
        # Second chance: the matcher is markup-tolerant, so try its own regex on the
        # whole document before declaring the text absent.
        pat = re.compile(_make_markup_tolerant(re.escape(text)), re.IGNORECASE | re.DOTALL)
        if not pat.search(md):
            return "missing", ""
        return "present_multiline", "spans a line break"

    # Which of the hosting lines are headings?
    heading_hits = [i for i in hits if HEADING_RE.match(lines[i])]
    if heading_hits:
        return ("already_heading", f"h{len(HEADING_RE.match(lines[heading_hits[0]]).group(1))}")

    # Inside a table block only?
    table_spans = [(m.start(), m.end()) for m in TABLE_BLOCK_RE.finditer(md)]
    if table_spans:
        offsets = []
        pos = 0
        for ln in lines:
            offsets.append(pos)
            pos += len(ln) + 1
        in_tbl = all(any(a <= offsets[i] < b for a, b in table_spans) for i in hits)
        if in_tbl:
            return "in_table", ""

    # Is the text on a line of its own (i.e. the line is essentially just the text)?
    own_line = [i for i in hits if norm_loose(lines[i]) == needle]
    if not own_line:
        return "inline_merged", norm_loose(lines[hits[0]])[:80]

    # It has its own line. Standalone (blank above and below)?
    standalone = [i for i in own_line if is_standalone(lines, i)]
    if not standalone:
        return "own_line_not_standalone", norm_loose(lines[own_line[0]])[:80]

    i = standalone[0]
    reason = titleish_reason(lines[i])
    if reason == "accept":
        return "standalone_other", lines[i].strip()[:80]
    return "standalone_gated", reason


def main() -> None:
    corpus = list(L.iter_markdown_corpus())

    # ---------- 1. heading census ----------
    lvl = collections.Counter()
    docs_with_headings = 0
    total_lines = 0
    for _stem, md, _rows in corpus:
        n_here = 0
        for ln in md.split("\n"):
            total_lines += 1
            m = HEADING_RE.match(ln)
            if m:
                lvl[len(m.group(1))] += 1
                n_here += 1
        if n_here:
            docs_with_headings += 1
    print(f"1. HEADING CENSUS over {len(corpus)} scored documents ({total_lines} lines)")
    print(f"   documents containing at least one '#' heading: {docs_with_headings}/{len(corpus)}")
    for k in sorted(lvl):
        print(f"   level h{k} ('{'#' * k} '): {lvl[k]}")
    print(f"   total heading lines: {sum(lvl.values())}")

    # Provenance: element-level markers vs document-level title_promote.
    elem_corpus = list(L.iter_element_corpus(require_byte_exact=True))
    pre_lvl = collections.Counter()
    post_lvl = collections.Counter()
    cat_counter = collections.Counter()
    multiline_titles = 0
    orphan_heading_lines = 0
    for _stem, els, _rows in elem_corpus:
        for el in els:
            cat_counter[el.get("category", "Text")] += 1
        pre, _ = K._nano_assemble_markdown(els)
        pre = K.header_mark(pre)
        pre = K.quote_fold(pre)
        for ln in pre.split("\n"):
            m = HEADING_RE.match(ln)
            if m:
                pre_lvl[len(m.group(1))] += 1
        post = K.title_promote(pre, variant="aggressive")
        for ln in post.split("\n"):
            m = HEADING_RE.match(ln)
            if m:
                post_lvl[len(m.group(1))] += 1
        for el in els:
            if el.get("category") in ("Title", "Section-header"):
                body = (el.get("content") or "").strip()
                extra = [x for x in body.split("\n")[1:] if x.strip()]
                if extra:
                    multiline_titles += 1
                    orphan_heading_lines += len(extra)
    print(f"\n   provenance, on the {len(elem_corpus)}-doc byte-exact element-replay sub-corpus:")
    print(f"     from element markers (Title -> '# ', Section-header -> '## '): "
          f"{sum(pre_lvl.values())}  {dict(sorted(pre_lvl.items()))}")
    print(f"     after title_promote('aggressive'):                            "
          f"{sum(post_lvl.values())}  {dict(sorted(post_lvl.items()))}")
    print(f"     -> title_promote adds {sum(post_lvl.values()) - sum(pre_lvl.values())} heading lines")
    print(f"     multi-line Title/Section-header elements: {multiline_titles}, "
          f"leaving {orphan_heading_lines} continuation lines with no '#'")
    print(f"\n   element categories in that sub-corpus (only Title/Section-header get a '#'):")
    for c, n in cat_counter.most_common():
        mark = "  <-- gets '#'" if c in ("Title", "Section-header") else ""
        print(f"     {c:16s} {n:6d}{mark}")

    # ---------- 2. why did each bold / title rule fail ----------
    print("\n2. WHY ANNOTATED TEXT IS NOT ON A HEADING LINE")
    out: dict[str, dict] = {}
    for rtype in ("is_bold", "is_title"):
        reasons = collections.Counter()
        gates = collections.Counter()
        n_eval = n_pass = 0
        examples: dict[str, list[str]] = collections.defaultdict(list)
        for stem, md, rows in corpus:
            rows_t = [r for r in rows if r["type"] == rtype]
            if not rows_t:
                continue
            scores = L.run_rules(md, rows_t)
            for row, (_t, score) in zip(rows_t, scores):
                n_eval += 1
                if score >= 1.0:
                    n_pass += 1
                    continue
                text = json.loads(row["rule"])["text"]
                reason, detail = classify(md, text, False)
                reasons[reason] += 1
                if reason == "standalone_gated":
                    gates[detail] += 1
                if len(examples[reason]) < 3:
                    examples[reason].append(f"{stem}: {text[:60]!r} {detail[:60]!r}")
        n_fail = n_eval - n_pass
        print(f"\n   {rtype}: {n_eval} rules, {n_pass} pass ({n_pass / n_eval:.1%}), {n_fail} fail")
        for r, n in reasons.most_common():
            print(f"     {r:26s} {n:5d}  ({n / n_fail:5.1%} of failures)")
            for ex in examples[r][:2]:
                print(f"         e.g. {ex}")
        if gates:
            print(f"     ...of which `_is_titleish` gate that fired:")
            for g, n in gates.most_common():
                print(f"          {g:28s} {n:5d}")
        out[rtype] = {"n_eval": n_eval, "n_pass": n_pass, "reasons": dict(reasons), "gates": dict(gates)}

    json.dump(
        {"heading_levels": dict(lvl), "docs_with_headings": docs_with_headings,
         "pre_promote_levels": dict(pre_lvl), "post_promote_levels": dict(post_lvl),
         "element_categories": dict(cat_counter),
         "multiline_title_elements": multiline_titles,
         "orphan_continuation_lines": orphan_heading_lines,
         "failure_breakdown": out},
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_heading_diagnosis.json"), "w"),
        indent=1,
    )
    print("\nwrote scripts/_heading_diagnosis.json")


if __name__ == "__main__":
    main()
