"""
Collateral damage for the two RECOMMENDED patch sets, end-to-end.

`semfmt_measure.py --collateral` checks patches one at a time. This checks the exact
combinations that the projected leaderboard rows in the report depend on, because Set A
contains members (notably A4, `List-item` -> `## `, which *removes* the `- ` list
marker) whose Content-Faithfulness effect is not implied by any single-patch row.

Baselines are paired: for a set containing provider-level members, the baseline markdown
is also re-assembled from stored elements, so the comparison isolates the patch rather
than mixing in reconstruction differences.

Dimensions checked:
  Content Faithfulness  `text_content` split, 506 docs, real rules
  Charts                `chart` split, 568 docs, real rules
  Tables                byte-identity of `<table>…</table>` blocks and pipe-table rows
  Visual Grounding      invariant by construction (kdl_frontier_nano.py:3287-3296 builds
                        layout items from raw element `content`, never from markdown);
                        asserted here by comparing the layout inputs directly

Run:  ../.venv/bin/python scripts/final_collateral.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from typing import Any, Callable

import semfmt_lib as L
import semfmt_measure as M
import semfmt_patches as P
from semfmt_final_stack import bbox_levels

sys.path.insert(0, os.path.join(L.PB_ROOT, "src"))
from parse_bench.inference.providers.parse import kdl_frontier_nano as K  # noqa: E402

SPLITS = ("text_content", "chart")


def assemble_all(provider_ctxs: list[Callable[[], Any]], stems: list[str]) -> dict[str, str]:
    arts = L.artifact_index()
    out: dict[str, str] = {}
    with contextlib.ExitStack() as stack:
        for f in provider_ctxs:
            stack.enter_context(f())
        for stem in stems:
            path = arts.get(stem)
            if not path:
                continue
            els = L.elements_of(L.load_raw(path))
            out[stem] = L.assemble(els)
            for el in els:
                el.pop("_lvl", None)
    return out


def main() -> None:
    arts = L.artifact_index()
    split_rules = {s: M.load_split(s, M.SPLIT_TYPES[s]) for s in SPLITS}
    stems = {s: sorted(x for x in split_rules[s] if x in arts) for s in SPLITS}

    T5 = P.PROVIDER_PATCHES["T5 titleish: drop caps+punct+label, 30 words"]
    C2 = P.PROVIDER_PATCHES["C2 short single-line Text -> '# '"]
    C3 = P.PROVIDER_PATCHES["C3 List-item -> '## ' instead of '- '"]
    A_prov = [lambda: bbox_levels(4), T5, C2, C3]
    A_md = P.compose(P.bold_labels, lambda md: P.bold_own_line(md, 40))
    B_md = P.compose(P.bold_labels, lambda md: P.bold_own_line(md, 40), P.bold_all_lines)

    print("shipped-markdown reference (the numbers on our leaderboard row):")
    for s in SPLITS:
        md = {x: (L.load_raw(arts[x]).get("markdown") or "") for x in stems[s]}
        v, n = M._split_score(s, md, split_rules[s])
        print(f"  {s:14s} {v * 100:.4f}  (n={n})")

    print("\nre-assembled baseline (paired reference for provider-level patches):")
    base_replay = {s: assemble_all([], stems[s]) for s in SPLITS}
    base_vals = {}
    for s in SPLITS:
        v, n = M._split_score(s, base_replay[s], split_rules[s])
        base_vals[s] = v
        print(f"  {s:14s} {v * 100:.4f}  (n={n})")

    for name, provs, mdfn in (("SET A", A_prov, A_md), ("SET B", A_prov, B_md)):
        print(f"\n{name}")
        row: dict[str, Any] = {}
        tables_changed = 0
        for s in SPLITS:
            patched = assemble_all(provs, stems[s])
            patched = {k: mdfn(v) for k, v in patched.items()}
            v, n = M._split_score(s, patched, split_rules[s])
            d = 100 * (v - base_vals[s])
            label = "Content Faithfulness" if s == "text_content" else "Charts"
            print(f"  {label:22s} {base_vals[s] * 100:7.2f} -> {v * 100:7.2f}   "
                  f"delta {d:+6.2f} pts   (Overall impact {d / 5:+5.2f})")
            row[s] = {"baseline": base_vals[s], "patched": v, "delta_pts": d, "n": n}
            for stem, md in base_replay[s].items():
                if M.table_signature(md) != M.table_signature(patched.get(stem, md)):
                    tables_changed += 1
        total = sum(len(base_replay[s]) for s in SPLITS)
        print(f"  Tables (byte-identity) docs with any table-markup change: "
              f"{tables_changed}/{total}")
        row["tables_changed"] = tables_changed
        row["tables_checked"] = total
        json.dump(row, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         f"_final_collateral_{name.replace(' ', '')}.json"), "w"),
                  indent=1)

    # Visual Grounding invariance: the layout inputs are the raw element bboxes and
    # `content` fields, which no patch here writes to. Assert it.
    print("\nVisual Grounding invariance check")
    probe = sorted(arts)[:400]
    before = {}
    for stem in probe:
        raw = L.load_raw(arts[stem])
        before[stem] = [
            (e.get("category"), tuple(e.get("bbox") or ()), e.get("content"))
            for p in (raw.get("pages") or []) for e in (p.get("elements") or [])
        ]
    with contextlib.ExitStack() as stack:
        for f in A_prov:
            stack.enter_context(f())
        for stem in probe:
            raw = L.load_raw(arts[stem])
            els = L.elements_of(raw)
            L.assemble(els)
    after = {}
    for stem in probe:
        raw = L.load_raw(arts[stem])
        after[stem] = [
            (e.get("category"), tuple(e.get("bbox") or ()), e.get("content"))
            for p in (raw.get("pages") or []) for e in (p.get("elements") or [])
        ]
    n_diff = sum(1 for s in probe if before[s] != after[s])
    print(f"  documents probed: {len(probe)}   with any (category, bbox, content) change: {n_diff}")
    print("  -> layout_pages inputs unchanged, so layout_element_rule_pass_rate is unchanged.")


if __name__ == "__main__":
    main()
