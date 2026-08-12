"""
Measure the SUBMITTED ("genuine") patch set and the DISCLOSED ("aggressive") set for the
`KDL-Frontier-Parser-nano` ParseBench pipeline, by replay, with no GPU.

WHAT THIS SCRIPT IS FOR
-----------------------
`PREREGISTRATION.md` §3 fixes the submitted patch set in advance:
  (a) add the missing `section_header` key to the layout label map;
  (b) derive heading depth from the `Title` element's bounding-box height;
  (c) bold run-in `Label:` prefixes;
  (d) OPTIONAL, borderline — relax the heading gate `_is_titleish` by dropping only its
      terminal-punctuation and label-value vetoes, with a 20-word cap. Dropped if its
      contribution is negative or within +/-0.05 Overall.
§4 fixes the disclosed-but-not-submitted set: short single-line `Text` promoted to `# `
and `List-item` promoted to `## `, on top of the submitted set.

Every number below is produced by REPLAY: markdown is re-derived from stored run
artifacts under `output/kdl_frontier_nano/`, then re-scored with the benchmark's own rule
classes. No inference is run.

The patched emission being measured is the code that ships, `ourparser/emission.py`,
driven through the production entry point of the provider subclass
(`ourparser.provider.PatchedNanoEngine.rebuild_markdown`) in section 5. There is no
separate "patch" implementation.

TERMS, IN PLAIN LANGUAGE
------------------------
* **replay** — re-derive markdown from stored per-element model output, then re-score it
  with the benchmark's own rule classes. The only measurement route without a GPU.
* **element sub-corpus** — the 319 of 476 scored `text_formatting` documents whose
  markdown can be re-assembled from stored elements *byte-identically* to what shipped.
  The other 157 contain `Picture`/`Chart` elements whose `picture_path` the artifact does
  not persist, so their markdown cannot be reconstructed exactly. Changes that act before
  the final markdown exists can only be measured here.
* **transfer** — a change measured on the 319-document sub-corpus is reported against the
  full-corpus baseline by adding its sub-corpus delta. `reports/formatting_gap_closure.md`
  §1.2 measured the error in doing so at 0.16-0.84 Semantic-Formatting points, i.e.
  0.03-0.17 Overall points, with the sub-corpus slightly *under*-stating gains.
* **Overall** — the unweighted mean of the benchmark's five dimensions, so 1
  Semantic-Formatting point moves Overall by 0.2 points.
* **Semantic Formatting / Content Faithfulness / Charts / Tables / Visual Grounding** —
  the five dimensions: preserved markup; text correctness and ordering; chart data-point
  extraction; table structure; and whether each detected region's box and text line up.

Run (from `parsebench/`, with that checkout's own virtual environment — the top-level
`bfcl-sprint/.venv` lacks `rapidfuzz` and cannot import the benchmark):

    ./.venv/bin/python scripts/genuine_set_measure.py            # sections 1,2,3,5,6
    ./.venv/bin/python scripts/genuine_set_measure.py --collateral   # + section 4

Deterministic: no randomness, no wall-clock dependence, no network.
"""

from __future__ import annotations

import collections
import json
import os
import sys
from typing import Any, Callable, Dict, List, Tuple

import semfmt_lib as L
import semfmt_measure as M
import semfmt_patches as P

sys.path.insert(0, os.path.join(L.PB_ROOT, "src"))
# `ourparser` lives one level above the parsebench checkout; it is our code, deliberately
# kept outside the pinned upstream tree.
sys.path.insert(0, os.path.dirname(L.PB_ROOT))

from ourparser import emission as E  # noqa: E402
from ourparser.provider import PatchedNanoEngine  # noqa: E402
from parse_bench.inference.providers.parse import kdl_frontier_nano as K  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "_genuine_set_measure.json")

#: The measured configurations, in report order.
CONFIGS: Dict[str, E.EmissionConfig] = {
    "baseline (vendored emission)": E.BASELINE,
    "GENUINE a+b+c": E.GENUINE_ABC,
    "GENUINE a+b+c+d": E.GENUINE_ABCD,
    "AGGRESSIVE on a+b+c": E.aggressive(E.GENUINE_ABC),
    "AGGRESSIVE on a+b+c+d": E.aggressive(E.GENUINE_ABCD),
}


# ======================================================================================
# 1. drift test — are our ports faithful?
# ======================================================================================
def drift_test() -> Dict[str, Any]:
    """
    Prove `ourparser.emission`'s ports reproduce the vendored functions exactly.

    `assemble_markdown`, `title_promote` and `postprocess_markdown` in
    `ourparser/emission.py` are ports of vendored functions with one injected seam each.
    A port can drift from its original. So: over EVERY stored artifact, run our ports
    with the *vendored* seam and require byte-identical output, both for the
    whole-document markdown and for every per-page record. Also require our
    `bold_run_in_labels` to equal the function the earlier exploration measured
    (`scripts/semfmt_patches.bold_labels`), so change (c) is provably the same rule.

    A single mismatch invalidates every number in this report.
    """
    arts = L.artifact_index()
    n = mism_md = mism_pages = mism_label = 0
    examples: List[str] = []
    for stem in sorted(arts):
        raw = L.load_raw(arts[stem])
        els = L.elements_of(raw)
        n += 1

        want_md, want_pages = K._nano_assemble_markdown(els)
        want_md = K.postprocess_markdown(want_md)
        want_pages = [
            {"page_number": p["page_number"], "content": K.postprocess_markdown(p["content"])}
            for p in want_pages
        ]
        got_md, got_pages = E.build_markdown_vendored(els)
        if got_md != want_md:
            mism_md += 1
            if len(examples) < 5:
                examples.append(f"markdown differs: {stem}")
        if got_pages != want_pages:
            mism_pages += 1
            if len(examples) < 5:
                examples.append(f"page markdown differs: {stem}")

        shipped = raw.get("markdown") or ""
        if E.bold_run_in_labels(shipped) != P.bold_labels(shipped):
            mism_label += 1
            if len(examples) < 5:
                examples.append(f"bold_run_in_labels differs: {stem}")

    ok = mism_md == 0 and mism_pages == 0 and mism_label == 0
    print("1. PORT DRIFT TEST (our ports, vendored seam, vs the vendored functions)")
    print(f"   artifacts compared                          : {n}")
    print(f"   whole-document markdown mismatches          : {mism_md}")
    print(f"   per-page markdown mismatches                : {mism_pages}")
    print(f"   bold_run_in_labels vs prior bold_labels     : {mism_label} mismatches")
    print(f"   PORTS FAITHFUL: {ok}")
    for ex in examples:
        print(f"     ! {ex}")
    return {
        "n": n,
        "mismatch_markdown": mism_md,
        "mismatch_pages": mism_pages,
        "mismatch_bold_labels": mism_label,
        "ok": ok,
    }


# ======================================================================================
# 2. Semantic Formatting by replay
# ======================================================================================
def score_elements(
    elem_corpus: List[Tuple[str, List[dict], List[dict]]],
    build: Callable[[List[dict]], str],
) -> Dict[str, Any]:
    """Score one emission path over the element sub-corpus."""
    vals: List[float] = []
    tacc: Dict[str, List[float]] = collections.defaultdict(list)
    cacc: Dict[str, List[float]] = collections.defaultdict(list)
    for _stem, els, rows in elem_corpus:
        md = build(els)
        semfmt, cats, per_type = L.score_from_rule_scores(L.run_rules(md, rows))
        if semfmt is not None:
            vals.append(semfmt)
        for t, v in per_type.items():
            tacc[t].append(v)
        for c, v in cats.items():
            cacc[c].append(v)
    return {
        "semfmt": L.aggregate(vals),
        "n": len(vals),
        "per_type": {t: L.aggregate(v) for t, v in sorted(tacc.items())},
        "cats": {c: L.aggregate(v) for c, v in sorted(cacc.items())},
    }


def builder(cfg: E.EmissionConfig) -> Callable[[List[dict]], str]:
    def build(els: List[dict]) -> str:
        return E.build_markdown(els, cfg)[0]

    return build


def semfmt_section(
    elem_corpus: List[Tuple[str, List[dict], List[dict]]],
    md_corpus: List[Tuple[str, str, List[dict]]],
) -> Dict[str, Any]:
    print("\n2. SEMANTIC FORMATTING BY REPLAY")
    full_base = L.measure_markdown_patch(None, md_corpus)
    print(f"   full corpus baseline        (n={full_base['n']}) SemFmt="
          f"{full_base['semfmt'] * 100:6.2f}   <- our shipped 52.42")
    results: Dict[str, Any] = {"full_baseline": full_base["semfmt"]}

    base = score_elements(elem_corpus, builder(E.BASELINE))
    print(f"   element sub-corpus baseline (n={base['n']}) SemFmt="
          f"{base['semfmt'] * 100:6.2f}   <- prior harness 54.26")
    results["elem_baseline"] = base["semfmt"]

    print(f"\n   {'configuration':<28s} {'SemFmt':>7s} {'dSemFmt':>8s} {'dOverall':>9s} | "
          f"{'is_bold':>7s} {'is_title':>8s} {'hier':>6s}")
    for name, cfg in CONFIGS.items():
        if name.startswith("baseline"):
            r = base
        else:
            r = score_elements(elem_corpus, builder(cfg))
        d = 100 * (r["semfmt"] - base["semfmt"])
        pt = r["per_type"]
        print(f"   {name:<28s} {r['semfmt'] * 100:7.2f} {d:+8.2f} {d / 5:+9.2f} | "
              f"{pt.get('is_bold', 0):7.3f} {pt.get('is_title', 0):8.3f} "
              f"{pt.get('title_hierarchy_percent', 0):6.3f}")
        results[name] = {"semfmt_sub": r["semfmt"], "d_semfmt_sub": d,
                         "per_type": pt, "cats": r["cats"], "n": r["n"]}

    # Change (c) is a pure function of the final markdown, so it can also be measured on
    # all 476 documents with no transfer caveat. Reported as a cross-check on transfer.
    c_only = L.measure_markdown_patch(E.bold_run_in_labels, md_corpus)
    dc_full = 100 * (c_only["semfmt"] - full_base["semfmt"])
    c_sub = score_elements(
        elem_corpus,
        lambda els: E.bold_run_in_labels(E.build_markdown(els, E.BASELINE)[0]),
    )
    dc_sub = 100 * (c_sub["semfmt"] - base["semfmt"])
    print(f"\n   change (c) alone, full 476 docs : SemFmt={c_only['semfmt'] * 100:6.2f}  "
          f"dSemFmt={dc_full:+.2f}  dOverall={dc_full / 5:+.2f}")
    print(f"   change (c) alone, sub-corpus    : SemFmt={c_sub['semfmt'] * 100:6.2f}  "
          f"dSemFmt={dc_sub:+.2f}   -> transfer disagreement "
          f"{abs(dc_sub - dc_full):.2f} SemFmt pts")
    results["c_only_full"] = {"semfmt": c_only["semfmt"], "d_semfmt": dc_full}
    results["c_only_sub"] = {"semfmt": c_sub["semfmt"], "d_semfmt": dc_sub}

    # Marginal contribution of the borderline change (d), which is the number the
    # preregistration's drop rule is evaluated against.
    d_marginal = (results["GENUINE a+b+c+d"]["d_semfmt_sub"]
                  - results["GENUINE a+b+c"]["d_semfmt_sub"])
    print(f"\n   marginal contribution of (d) on top of (a)+(b)+(c): "
          f"{d_marginal:+.2f} SemFmt = {d_marginal / 5:+.3f} Overall")
    results["d_marginal_semfmt"] = d_marginal
    return results


# ======================================================================================
# 3. sensitivity checks
# ======================================================================================
def sensitivity(elem_corpus: List[Tuple[str, List[dict], List[dict]]],
                base_semfmt: float) -> Dict[str, Any]:
    """
    Two dials that had to be chosen, reported so the choice is auditable.

    * the maximum heading depth for change (b) — kept at 4, the value the earlier
      exploration used, so it is not a value picked after seeing this result;
    * whether change (d) also drops the leading-capital gate — the preregistration says
      it does not, and this shows what that decision costs.
    """
    print("\n3. SENSITIVITY (reported, not used to pick the headline)")
    out: Dict[str, Any] = {}
    for ml in (2, 3, 4, 6):
        cfg = E.EmissionConfig(section_header_map_fix=True, bbox_heading_levels=ml,
                               bold_run_in_labels=True)
        r = score_elements(elem_corpus, builder(cfg))
        d = 100 * (r["semfmt"] - base_semfmt)
        print(f"   (a)+(b max depth={ml})+(c)              SemFmt={r['semfmt'] * 100:6.2f}  "
              f"dSemFmt={d:+6.2f}  hier={r['per_type'].get('title_hierarchy_percent', 0):.3f}")
        out[f"max_level_{ml}"] = {"semfmt": r["semfmt"], "d_semfmt": d}

    for cap in (12, 20, 30):
        cfg = E.EmissionConfig(section_header_map_fix=True, bbox_heading_levels=4,
                               bold_run_in_labels=True, relaxed_title_gate_max_words=cap)
        r = score_elements(elem_corpus, builder(cfg))
        d = 100 * (r["semfmt"] - base_semfmt)
        print(f"   (a)+(b)+(c)+(d word cap={cap})          SemFmt={r['semfmt'] * 100:6.2f}  "
              f"dSemFmt={d:+6.2f}")
        out[f"gate_cap_{cap}"] = {"semfmt": r["semfmt"], "d_semfmt": d}
    return out


# ======================================================================================
# 4. collateral on the other four dimensions
# ======================================================================================
SPLITS = ("text_content", "chart")


def assemble_split(cfg: E.EmissionConfig, stems: List[str]) -> Dict[str, str]:
    arts = L.artifact_index()
    out: Dict[str, str] = {}
    for stem in stems:
        path = arts.get(stem)
        if not path:
            continue
        out[stem] = E.build_markdown(L.elements_of(L.load_raw(path)), cfg)[0]
    return out


def collateral_section() -> Dict[str, Any]:
    """
    Content Faithfulness and Charts re-measured with the benchmark's real rules, plus
    byte-identity checks for Tables and Visual Grounding.

    Baselines are PAIRED: the comparison markdown is also re-assembled from stored
    elements, so the delta isolates the patch instead of mixing in the reconstruction
    difference of the 157 documents that do not rebuild byte-exactly. Only the delta is
    meaningful; the absolute re-assembled baseline differs slightly from the shipped one.
    """
    print("\n4. COLLATERAL — Content Faithfulness, Charts, Tables, Visual Grounding")
    arts = L.artifact_index()
    split_rules = {s: M.load_split(s, M.SPLIT_TYPES[s]) for s in SPLITS}
    stems = {s: sorted(x for x in split_rules[s] if x in arts) for s in SPLITS}

    print("   shipped-markdown reference (the values on our leaderboard row):")
    for s in SPLITS:
        md = {x: (L.load_raw(arts[x]).get("markdown") or "") for x in stems[s]}
        v, n = M._split_score(s, md, split_rules[s])
        print(f"     {s:14s} {v * 100:7.4f}  (n={n})")

    base_md = {s: assemble_split(E.BASELINE, stems[s]) for s in SPLITS}
    base_val: Dict[str, float] = {}
    print("   re-assembled paired baseline:")
    for s in SPLITS:
        v, n = M._split_score(s, base_md[s], split_rules[s])
        base_val[s] = v
        print(f"     {s:14s} {v * 100:7.4f}  (n={n})")

    out: Dict[str, Any] = {"paired_baseline": {s: base_val[s] for s in SPLITS}}
    for name, cfg in CONFIGS.items():
        if name.startswith("baseline"):
            continue
        print(f"   {name}")
        row: Dict[str, Any] = {}
        tables_changed = 0
        checked = 0
        for s in SPLITS:
            patched = assemble_split(cfg, stems[s])
            v, n = M._split_score(s, patched, split_rules[s])
            d = 100 * (v - base_val[s])
            label = "Content Faithfulness" if s == "text_content" else "Charts"
            print(f"     {label:22s} {base_val[s] * 100:7.2f} -> {v * 100:7.2f}   "
                  f"delta {d:+6.2f} pts  (Overall {d / 5:+5.2f})")
            row[s] = {"baseline": base_val[s], "patched": v, "delta_pts": d, "n": n}
            for stem, md in base_md[s].items():
                checked += 1
                if M.table_signature(md) != M.table_signature(patched.get(stem, md)):
                    tables_changed += 1
        print(f"     Tables: documents with any change to an HTML <table> block or a "
              f"pipe-table row: {tables_changed}/{checked}")
        row["tables_changed"] = tables_changed
        row["tables_checked"] = checked
        out[name] = row

    # Visual Grounding: built from each element's (category, bbox, content) at
    # kdl_frontier_nano.py:3287-3296, never from the markdown. Our emission code takes
    # the element list as read-only, so assert the triples are untouched after a build.
    print("   Visual Grounding invariance (element (category, bbox, content) triples)")
    probe = sorted(arts)[:400]
    changed = 0
    for stem in probe:
        els = L.elements_of(L.load_raw(arts[stem]))
        before = [(e.get("category"), tuple(e.get("bbox") or ()), e.get("content")) for e in els]
        for cfg in CONFIGS.values():
            E.build_markdown(els, cfg)
        after = [(e.get("category"), tuple(e.get("bbox") or ()), e.get("content")) for e in els]
        if before != after:
            changed += 1
    print(f"     documents probed: {len(probe)}   with any change: {changed}")
    out["vg_probe"] = {"documents": len(probe), "changed": changed}
    return out


# ======================================================================================
# 5. verification through the provider subclass
# ======================================================================================
def verify_via_provider(
    elem_corpus: List[Tuple[str, List[dict], List[dict]]], measured: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Re-measure through `PatchedNanoEngine.rebuild_markdown`, the method live inference
    calls, and require the Semantic Formatting value to match section 2 exactly.

    This is the check that the measured number belongs to the shipped code path and not
    to a measurement-only helper. A mismatch means they are not the same code.
    """
    print("\n5. VERIFICATION THROUGH THE PROVIDER SUBCLASS")
    out: Dict[str, Any] = {}
    ok_all = True
    for name, cfg in CONFIGS.items():
        engine = PatchedNanoEngine(
            "http://unused/v1", "unused", 1, 1.0, config=cfg
        )
        r = score_elements(elem_corpus, lambda els: engine.rebuild_markdown(els)["markdown"])
        want = measured[name]["semfmt_sub"]
        ok = abs(r["semfmt"] - want) < 1e-12
        ok_all = ok_all and ok
        print(f"   {name:<28s} engine SemFmt={r['semfmt'] * 100:.10f}  "
              f"section-2 SemFmt={want * 100:.10f}  MATCH={ok}")
        out[name] = {"engine_semfmt": r["semfmt"], "section2_semfmt": want, "match": ok}
    print(f"   ALL MATCH: {ok_all}")
    out["all_match"] = ok_all
    return out


# ======================================================================================
# 6. projected leaderboard rows
# ======================================================================================
def board(semfmt_pts: float, cf_pts: float, charts_pts: float) -> Dict[str, float]:
    row = dict(L.OURS)
    row["Semantic_Formatting"] = semfmt_pts
    row["Content_Faithfulness"] = cf_pts
    row["Charts"] = charts_pts
    dims = ["Tables", "Charts", "Content_Faithfulness", "Semantic_Formatting", "Visual_Grounding"]
    row["Overall"] = sum(row[d] for d in dims) / 5
    return row


def board_section(semfmt: Dict[str, Any], coll: Dict[str, Any] | None) -> Dict[str, Any]:
    print("\n6. PROJECTED LEADERBOARD ROWS")
    print("   Semantic Formatting = full-corpus baseline 52.42 + the sub-corpus delta;")
    print("   Content Faithfulness and Charts = our shipped values + their measured")
    print("   paired deltas; Tables and Visual Grounding verified unchanged.")
    hdr = (f"   {'row':<28s} {'Tables':>7s} {'Charts':>7s} {'ContFaith':>10s} "
           f"{'SemFmt':>7s} {'VisGrnd':>8s} {'Overall':>8s} {'vs 72.65':>9s} {'vs 76.36':>9s}")
    print(hdr)
    o = L.OURS
    print(f"   {'our run as shipped':<28s} {o['Tables']:7.2f} {o['Charts']:7.2f} "
          f"{o['Content_Faithfulness']:10.2f} {o['Semantic_Formatting']:7.2f} "
          f"{o['Visual_Grounding']:8.2f} {o['Overall']:8.2f} {'—':>9s} "
          f"{o['Overall'] - L.PUBLISHED['Overall']:+9.2f}")
    rows: Dict[str, Any] = {}
    for name in CONFIGS:
        if name.startswith("baseline"):
            continue
        sf = L.OURS["Semantic_Formatting"] + semfmt[name]["d_semfmt_sub"]
        if coll:
            cf = L.OURS["Content_Faithfulness"] + coll[name]["text_content"]["delta_pts"]
            ch = L.OURS["Charts"] + coll[name]["chart"]["delta_pts"]
        else:
            cf, ch = L.OURS["Content_Faithfulness"], L.OURS["Charts"]
        b = board(sf, cf, ch)
        print(f"   {name:<28s} {b['Tables']:7.2f} {b['Charts']:7.2f} "
              f"{b['Content_Faithfulness']:10.2f} {b['Semantic_Formatting']:7.2f} "
              f"{b['Visual_Grounding']:8.2f} {b['Overall']:8.2f} "
              f"{b['Overall'] - o['Overall']:+9.2f} "
              f"{b['Overall'] - L.PUBLISHED['Overall']:+9.2f}")
        rows[name] = b
    p = L.PUBLISHED
    print(f"   {'published KDL row':<28s} {p['Tables']:7.2f} {p['Charts']:7.2f} "
          f"{p['Content_Faithfulness']:10.2f} {p['Semantic_Formatting']:7.2f} "
          f"{p['Visual_Grounding']:8.2f} {p['Overall']:8.2f}")
    return rows


def main() -> None:
    want_collateral = "--collateral" in sys.argv
    md_corpus = list(L.iter_markdown_corpus())
    elem_corpus = list(L.iter_element_corpus(require_byte_exact=True))
    print(f"markdown corpus : {len(md_corpus)} scored text_formatting documents")
    print(f"element corpus  : {len(elem_corpus)} byte-exact re-assembly documents\n")

    results: Dict[str, Any] = {}
    results["drift"] = drift_test()
    if not results["drift"]["ok"]:
        print("\nABORT: the ports have drifted from the vendored functions; every number "
              "below would be measuring something other than the shipped code.")
        json.dump(results, open(OUT_JSON, "w"), indent=1)
        raise SystemExit(1)

    results["semfmt"] = semfmt_section(elem_corpus, md_corpus)
    results["sensitivity"] = sensitivity(elem_corpus, results["semfmt"]["elem_baseline"])
    results["collateral"] = collateral_section() if want_collateral else None
    results["verification"] = verify_via_provider(elem_corpus, results["semfmt"])
    results["board"] = board_section(results["semfmt"], results["collateral"])

    json.dump(results, open(OUT_JSON, "w"), indent=1, default=str)
    print(f"\nwrote {os.path.relpath(OUT_JSON, L.PB_ROOT)}")


if __name__ == "__main__":
    main()
