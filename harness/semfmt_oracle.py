"""
Deliverable 1: quantify the Semantic Formatting ceiling with a perfect oracle.

An "oracle" here means: pretend every rule of a chosen type scored 1.0, leave every
other rule at its measured score, then recompute the dimension. It answers "if we
solved this one sub-problem completely, where would Semantic Formatting land?" — an
upper bound on any patch aimed at that sub-problem.

This runs on the SHIPPED per-rule results for all 476 scored documents (not the
replay sub-corpus), so the baseline is exactly the 52.42 on our leaderboard row and
the ceilings are exact for our run — no replay-fidelity caveat.

The decisive test for this investigation: the published KDL-Frontier-Parser-nano row
claims Semantic Formatting 66.81. Our run scored 52.42. Established earlier: the model
emits zero inline formatting markup, so all `is_bold` credit arrives through the bold
matcher's heading arm (`rules_formatting.py:201-204` accepts a `#`-heading line
containing the annotated text). If oracle-perfect `is_bold` alone cannot reach 66.81,
then heading emission cannot be the whole explanation for the 14.39-point gap.

Run:  ../.venv/bin/python scripts/semfmt_oracle.py
"""

from __future__ import annotations

import collections
import json
import os

import semfmt_lib as L

TARGET = L.PUBLISHED["Semantic_Formatting"] / 100.0


def oracle(stored: dict[str, list[tuple[str, float]]], perfect: set[str]) -> tuple[float, dict[str, float]]:
    """Recompute the corpus SemFmt with every rule in `perfect` forced to score 1.0."""
    vals: list[float] = []
    cat_acc: dict[str, list[float]] = collections.defaultdict(list)
    for per_rule in stored.values():
        forced = [(t, 1.0 if t in perfect else s) for t, s in per_rule]
        semfmt, cats, _ = L.score_from_rule_scores(forced)
        if semfmt is not None:
            vals.append(semfmt)
        for c, v in cats.items():
            cat_acc[c].append(v)
    return L.aggregate(vals), {c: L.aggregate(v) for c, v in cat_acc.items()}


def main() -> None:
    stored = L.stored_rule_scores()
    base, base_cats = oracle(stored, set())

    # Rule inventory, so every ceiling can be read against how much mass it covers.
    counts: collections.Counter[str] = collections.Counter()
    docs: dict[str, set[str]] = collections.defaultdict(set)
    for stem, per_rule in stored.items():
        for t, _ in per_rule:
            counts[t] += 1
            docs[t].add(stem)

    print(f"corpus: {len(stored)} documents, baseline SemFmt = {base * 100:.2f} "
          f"(our leaderboard row: {L.OURS['Semantic_Formatting']})")
    print(f"published KDL target SemFmt = {TARGET * 100:.2f}  "
          f"-> gap to close = {(TARGET - base) * 100:.2f} points\n")

    print("rule inventory (scored types in bold):")
    scored = set(L.STYLING_POS) | set(L.TITLE_TYPES) | {"is_latex", "is_code_block"}
    for t, n in counts.most_common():
        tag = "SCORED" if t in scored else "weight 0"
        print(f"  {t:26s} rules={n:5d}  docs={len(docs[t]):4d}  {tag}")
    print()

    print("baseline category values:")
    for c, v in sorted(base_cats.items()):
        print(f"  {c:34s} {v:.4f}")
    print()

    rows: list[tuple[str, set[str]]] = [
        ("is_bold -> 1.0", {"is_bold"}),
        ("is_strikeout -> 1.0", {"is_strikeout"}),
        ("is_sup -> 1.0", {"is_sup"}),
        ("is_sub -> 1.0", {"is_sub"}),
        ("ALL FOUR styling sub-types -> 1.0", set(L.STYLING_POS)),
        ("-- for context, non-styling --", set()),
        ("is_title -> 1.0", {"is_title"}),
        ("title_hierarchy_percent -> 1.0", {"title_hierarchy_percent"}),
        ("both title types -> 1.0", set(L.TITLE_TYPES)),
        ("is_latex -> 1.0", {"is_latex"}),
        ("is_code_block -> 1.0", {"is_code_block"}),
        ("is_underline -> 1.0 (expect exactly 0)", {"is_underline"}),
        ("is_italic -> 1.0 (expect exactly 0)", {"is_italic"}),
        ("EVERYTHING -> 1.0", set(counts)),
    ]

    print(f"{'oracle':<40s} {'SemFmt':>7s} {'dSemFmt':>8s} {'dOverall':>9s}  clears 66.81?")
    results: dict[str, float] = {}
    for name, perfect in rows:
        if not perfect and name.startswith("--"):
            print(f"{name}")
            continue
        val, _ = oracle(stored, perfect)
        results[name] = val
        d = 100 * (val - base)
        clears = "YES" if val >= TARGET else "no"
        print(f"{name:<40s} {val * 100:7.2f} {d:+8.2f} {d / 5:+9.2f}  {clears}")

    print()
    bold_only, _ = oracle(stored, {"is_bold"})
    all_sty, _ = oracle(stored, set(L.STYLING_POS))
    print("VERDICT ON THE HEADING-EMISSION HYPOTHESIS")
    print(f"  oracle-perfect is_bold alone reaches SemFmt {bold_only * 100:.2f}; target {TARGET * 100:.2f}.")
    print(f"  -> heading emission {'CAN' if bold_only >= TARGET else 'CANNOT'} on its own account for the gap.")
    print(f"  oracle-perfect on all four styling sub-types reaches {all_sty * 100:.2f}.")
    print(f"  -> the whole styling sub-score {'CAN' if all_sty >= TARGET else 'CANNOT'} on its own account for the gap.")

    json.dump(
        {"baseline": base, "target": TARGET, "oracles": results,
         "rule_counts": dict(counts), "rule_docs": {k: len(v) for k, v in docs.items()},
         "baseline_cats": base_cats},
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_semfmt_oracle.json"), "w"),
        indent=1,
    )


if __name__ == "__main__":
    main()
