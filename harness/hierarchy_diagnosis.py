"""
Sub-diagnosis: decompose `title_hierarchy_percent` failures, and test heading-LEVEL
assignment as a separate lever from heading *presence*.

WHY. The heading census found that our run emits 3,780 `# ` (level-1) heading lines and
essentially nothing else: `Section-header` — the only category that would produce `## `
(`kdl_frontier_nano.py:2931-2933`) — is never produced, because
`NATIVE_LAYOUT_CATEGORY_MAP` (`:545-572`) has no `section_header` entry at all; the only
heading-ish raw label is `"title" -> "Title"`. Verified empirically: 0 `Section-header`
elements across all 2,078 stored artifacts.

`title_hierarchy_percent` (`rules_formatting.py:869-925`) scores two things:
  * presence  — each expected title must appear as a heading or whole-line-bold event;
  * edges     — for each parent->child pair, `parent_line < child_line` AND (for
                nesting edges) `parent_level < child_level`.
With every heading at level 1, `parent_level < child_level` is FALSE for every nesting
edge, so that half of the score is structurally unreachable. This script measures how
much of the metric that costs, and whether a deterministic level-assignment heuristic
recovers it.

The heuristic uses information we already have and did not use: the *bounding-box
height* of the `Title` element, available in the stored artifact
(`e["bbox"]`). Bigger box -> more prominent heading -> shallower level. Levels are
assigned per document by ranking the distinct rounded heights of `Title` elements.

Run:  ../.venv/bin/python scripts/hierarchy_diagnosis.py
"""

from __future__ import annotations

import collections
import json
import os
import sys
from typing import Any

import semfmt_lib as L

sys.path.insert(0, os.path.join(L.PB_ROOT, "src"))
from parse_bench.evaluation.metrics.parse.rules_formatting import (  # noqa: E402
    TitleHierarchyPercentRule,
    _extract_title_events,
)
from parse_bench.inference.providers.parse import kdl_frontier_nano as K  # noqa: E402


def decompose(md: str, rule_payload: dict[str, Any]) -> dict[str, int]:
    """Count satisfied/failed constraints of one `title_hierarchy_percent` rule."""
    rule = TitleHierarchyPercentRule(rule_payload)
    events = _extract_title_events(md)
    first_pos: dict[str, int] = {}
    first_level: dict[str, int] = {}
    for idx, level, title in events:
        if title not in first_pos:
            first_pos[title] = idx
            first_level[title] = level

    expected, edges = rule._collect_constraints(rule.title_hierarchy)
    c = collections.Counter()
    for t in expected:
        c["title_present" if t in first_pos else "title_missing"] += 1
    for parent, child, deeper in edges:
        if parent not in first_pos or child not in first_pos:
            c["edge_missing_endpoint"] += 1
            continue
        order_ok = first_pos[parent] < first_pos[child]
        depth_ok = first_level[parent] < first_level[child] if deeper else True
        if order_ok and depth_ok:
            c["edge_ok"] += 1
        elif not order_ok and not depth_ok:
            c["edge_fail_order_and_level"] += 1
        elif not order_ok:
            c["edge_fail_order_only"] += 1
        else:
            c["edge_fail_level_only"] += 1
    return dict(c)


def level_by_bbox(els: list[dict[str, Any]], max_level: int = 4) -> dict[int, int]:
    """
    Assign a heading level 1..max_level to each `Title` element by bbox height rank.

    :return: {id(element index) -> level}. Taller box = shallower (smaller) level.
    """
    heights: list[tuple[int, float]] = []
    for i, el in enumerate(els):
        if el.get("category") != "Title":
            continue
        bb = el.get("bbox")
        if not bb or len(bb) < 4:
            continue
        h = abs(float(bb[3]) - float(bb[1]))
        heights.append((i, h))
    if not heights:
        return {}
    # Rank the distinct rounded heights, tallest first.
    distinct = sorted({round(h, 4) for _, h in heights}, reverse=True)
    rank = {h: min(r + 1, max_level) for r, h in enumerate(distinct)}
    return {i: rank[round(h, 4)] for i, h in heights}


def main() -> None:
    corpus = list(L.iter_markdown_corpus())
    rules = L.load_rules()

    # ---- 1. decomposition of the shipped run ----
    totals = collections.Counter()
    for stem, md, rows in corpus:
        for row in rows:
            if row["type"] != "title_hierarchy_percent":
                continue
            try:
                totals.update(decompose(md, L.rule_payload(row)))
            except Exception:
                totals["rule_error"] += 1
    grand = sum(totals.values())
    print("1. title_hierarchy_percent constraint decomposition (shipped run, 476 docs)")
    print(f"   total constraints: {grand}")
    for k, v in totals.most_common():
        print(f"     {k:28s} {v:6d}  ({v / grand:6.1%})")
    lvl_only = totals.get("edge_fail_level_only", 0)
    print(f"\n   constraints lost ONLY to the flat level-1 heading structure: {lvl_only}"
          f"  ({lvl_only / grand:.1%} of all constraints)")

    # ---- 2. can a bbox-height heuristic recover them? ----
    print("\n2. bbox-height level assignment, measured by replay")
    elem_corpus = list(L.iter_element_corpus(require_byte_exact=True))
    print(f"   element sub-corpus: {len(elem_corpus)} docs")

    orig_assemble = K._nano_assemble_markdown

    for max_level in (2, 3, 4, 6):
        def make_fmt(ml: int):
            def assemble(els: list[dict[str, Any]]):
                levels = level_by_bbox(els, ml)
                # Tag each Title element with its assigned level, then let the
                # provider's own formatter read it.
                for i, el in enumerate(els):
                    if i in levels:
                        el["_lvl"] = levels[i]
                return orig_assemble(els)

            return assemble

        orig_fmt = K._nano_format_element

        def fmt(el: dict[str, Any]) -> str:
            if el.get("category") == "Title" and el.get("_lvl"):
                prefix = "#" * int(el["_lvl"])
                body = K._preserve_inline_markup(K._strip_leading_heading_marker(el.get("content") or ""))
                return f"{prefix} {body}"
            return orig_fmt(el)

        K._nano_assemble_markdown = make_fmt(max_level)
        K._nano_format_element = fmt
        try:
            vals: list[float] = []
            tacc: dict[str, list[float]] = collections.defaultdict(list)
            for stem, els, rows in elem_corpus:
                md = L.assemble(els)
                s, _c, pt = L.score_from_rule_scores(L.run_rules(md, rows))
                if s is not None:
                    vals.append(s)
                for t, v in pt.items():
                    tacc[t].append(v)
            got = L.aggregate(vals)
            print(f"   max_level={max_level}: SemFmt={got * 100:6.2f}  "
                  f"is_title={L.aggregate(tacc['is_title']):.3f}  "
                  f"hier={L.aggregate(tacc['title_hierarchy_percent']):.3f}  "
                  f"is_bold={L.aggregate(tacc['is_bold']):.3f}")
        finally:
            K._nano_assemble_markdown = orig_assemble
            K._nano_format_element = orig_fmt
            for _s, els, _r in elem_corpus:
                for el in els:
                    el.pop("_lvl", None)

    # baseline on the same corpus for reference
    vals = []
    tacc = collections.defaultdict(list)
    for stem, els, rows in elem_corpus:
        md = L.assemble(els)
        s, _c, pt = L.score_from_rule_scores(L.run_rules(md, rows))
        if s is not None:
            vals.append(s)
        for t, v in pt.items():
            tacc[t].append(v)
    print(f"   BASELINE       : SemFmt={L.aggregate(vals) * 100:6.2f}  "
          f"is_title={L.aggregate(tacc['is_title']):.3f}  "
          f"hier={L.aggregate(tacc['title_hierarchy_percent']):.3f}  "
          f"is_bold={L.aggregate(tacc['is_bold']):.3f}")

    json.dump({"decomposition": dict(totals)},
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "_hierarchy_diagnosis.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
