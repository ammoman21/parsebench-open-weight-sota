"""
Fidelity check for the no-GPU Semantic Formatting replay harness.

Three questions, answered before any patch is trusted:

  A. Does the re-implemented aggregation reproduce the shipped
     `avg_semantic_formatting` when fed the shipped per-rule results?
     (checks the arithmetic)

  B. Does re-executing the real rule classes against the shipped markdown reproduce
     those same per-rule scores?
     (checks that scoring is reproducible outside the harness — this is what makes a
     patch measurement meaningful)

  C. How many documents can be re-assembled byte-identically from the stored
     per-element model output?
     (bounds the element-level replay corpus)

Run:  ../.venv/bin/python scripts/semfmt_validate.py
"""

from __future__ import annotations

import json
import os
import sys

import semfmt_lib as L


def main() -> int:
    with open(L.FMT_REPORT) as fh:
        report = json.load(fh)
    shipped_semfmt = report["aggregate_metrics"]["avg_semantic_formatting"]
    shipped_types = {
        k[len("avg_rule_") : -len("_pass_rate")]: v
        for k, v in report["aggregate_metrics"].items()
        if k.startswith("avg_rule_") and k.endswith("_pass_rate")
    }

    # ---- A: arithmetic from stored per-rule results ----
    stored = L.stored_rule_scores()
    vals = []
    for stem, per_rule in stored.items():
        s, _, _ = L.score_from_rule_scores(per_rule)
        if s is not None:
            vals.append(s)
    recomputed = L.aggregate(vals)
    print("A. aggregation check (stored per-rule scores -> SemFmt)")
    print(f"   shipped avg_semantic_formatting = {shipped_semfmt:.10f}  (n={len(report['per_example_results'])})")
    print(f"   recomputed                      = {recomputed:.10f}  (n={len(vals)})")
    ok_a = abs(recomputed - shipped_semfmt) < 1e-9
    print(f"   MATCH: {ok_a}\n")

    # ---- B: re-execute rules against shipped markdown ----
    corpus = list(L.iter_markdown_corpus())
    print(f"B. rule re-execution check over {len(corpus)} documents "
          f"(shipped markdown -> real rule classes)")
    base = L.measure_markdown_patch(None, corpus)
    print(f"   replayed SemFmt = {base['semfmt']:.10f}   shipped = {shipped_semfmt:.10f}")
    print(f"   delta = {100 * (base['semfmt'] - shipped_semfmt):+.4f} SemFmt points")
    print("   per-rule-type pass rates (replayed vs shipped):")
    for t in sorted(base["per_type"]):
        sh = shipped_types.get(t)
        mark = "" if sh is None or abs(sh - base["per_type"][t]) < 1e-6 else "   <-- DIFFERS"
        print(f"     {t:28s} replay={base['per_type'][t]:.6f}  shipped="
              f"{'n/a' if sh is None else f'{sh:.6f}'}{mark}")
    print("   category values (replayed):")
    for c, v in base["cats"].items():
        print(f"     {c:32s} {v:.6f}")
    ok_b = abs(base["semfmt"] - shipped_semfmt) < 1e-6
    print(f"   MATCH: {ok_b}\n")

    # ---- C: element-level reconstruction coverage ----
    n_exact = sum(1 for _ in L.iter_element_corpus(require_byte_exact=True))
    n_all = sum(1 for _ in L.iter_element_corpus(require_byte_exact=False))
    print("C. element-replay coverage")
    print(f"   documents with stored elements       : {n_all}")
    print(f"   byte-identical re-assembly           : {n_exact}  "
          f"({100 * n_exact / max(n_all, 1):.1f}%)")

    # Baseline SemFmt restricted to the element-replay corpus, so element-level
    # patch deltas can be read on the same footing as full-corpus ones.
    exact_stems = {stem for stem, _, _ in L.iter_element_corpus(require_byte_exact=True)}
    sub = [(s, m, r) for s, m, r in corpus if s in exact_stems]
    sub_base = L.measure_markdown_patch(None, sub)
    print(f"   baseline SemFmt on that sub-corpus   : {sub_base['semfmt'] * 100:.2f} "
          f"(full corpus {base['semfmt'] * 100:.2f})")

    json.dump(
        {
            "shipped_semfmt": shipped_semfmt,
            "recomputed_from_stored": recomputed,
            "replayed_from_markdown": base["semfmt"],
            "per_type_replay": base["per_type"],
            "cats_replay": base["cats"],
            "n_full": len(corpus),
            "n_element_exact": n_exact,
            "element_subcorpus_semfmt": sub_base["semfmt"],
            "element_subcorpus_stems": sorted(exact_stems),
        },
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_semfmt_validate.json"), "w"),
        indent=1,
    )
    print("\nwrote scripts/_semfmt_validate.json")
    return 0 if (ok_a and ok_b) else 1


if __name__ == "__main__":
    sys.exit(main())
