"""
Deliverables 3-5: measure every candidate patch by replay, individually and stacked,
and check collateral damage on the other four leaderboard dimensions.

CORPORA
  * markdown-level patches  -> all 476 scored `text_formatting` documents. The
    unpatched baseline reproduces our shipped 52.42 exactly (see
    `scripts/semfmt_validate.py`), so these deltas transfer to the leaderboard number
    one-for-one.
  * provider-level patches  -> the 319 documents whose markdown can be re-assembled
    byte-identically from stored per-element output. Baseline on that sub-corpus is
    reported alongside so the delta is read on its own footing; the sub-corpus delta is
    also rescaled to the full corpus by the share of scored documents it covers, and
    both numbers are shown.

COLLATERAL DAMAGE
  Only two of the five dimensions can move at all:
    - Content Faithfulness (`text_content` split, 506 docs, metric
      `content_faithfulness`) — measured properly by re-running the real
      `text_content` rules over patched markdown, not by a proxy.
    - Charts (`chart` split, 568 docs, metric `rule_pass_rate` over
      `chart_data_point` rules) — measured the same way.
  Tables (`table` split, `grits_trm_composite`) is table-structure only; every patch
  here skips lines inside `<table>…</table>` and lines beginning with `|`, so this
  script asserts byte-identity of extracted table blocks rather than recomputing GriTS.
  Visual Grounding (`layout` split, `layout_element_rule_pass_rate`) is computed from
  per-element bounding boxes and per-element `content` (`kdl_frontier_nano.py:3290-3296`
  builds `LayoutItemIR.md` from `e["content"]`, not from the assembled markdown), so no
  patch measured here can reach it. Both claims are checked, not assumed.

Run:  ../.venv/bin/python scripts/semfmt_measure.py            # SemFmt only (fast)
      ../.venv/bin/python scripts/semfmt_measure.py --collateral   # + other dimensions
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys
from typing import Any, Callable

import semfmt_lib as L
import semfmt_patches as P

sys.path.insert(0, os.path.join(L.PB_ROOT, "src"))
from parse_bench.inference.providers.parse import kdl_frontier_nano as K  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = L.PUBLISHED["Semantic_Formatting"] / 100.0


# ---------------------------------------------------------------------------
def measure_provider_patch(
    ctx_factory: Callable[[], Any] | None,
    elem_corpus: list[tuple[str, list[dict], list[dict]]],
) -> dict[str, Any]:
    """Re-assemble markdown under a provider patch, then score it."""
    vals: list[float] = []
    type_acc: dict[str, list[float]] = collections.defaultdict(list)
    per_doc: dict[str, float] = {}
    ctx = ctx_factory() if ctx_factory else None

    def body() -> None:
        for stem, els, rows in elem_corpus:
            md = L.assemble(els)
            per_rule = L.run_rules(md, rows)
            semfmt, _cats, per_type = L.score_from_rule_scores(per_rule)
            if semfmt is not None:
                vals.append(semfmt)
                per_doc[stem] = semfmt
            for t, v in per_type.items():
                type_acc[t].append(v)

    if ctx is None:
        body()
    else:
        with ctx:
            body()
    return {
        "semfmt": L.aggregate(vals),
        "n": len(vals),
        "per_type": {t: L.aggregate(v) for t, v in sorted(type_acc.items())},
        "docs": per_doc,
    }


def provider_markdown(
    ctx_factory: Callable[[], Any] | None, stems: list[str]
) -> dict[str, str]:
    """Re-assembled markdown for `stems` under a provider patch (for collateral checks)."""
    arts = L.artifact_index()
    out: dict[str, str] = {}
    ctx = ctx_factory() if ctx_factory else None

    def body() -> None:
        for stem in stems:
            path = arts.get(stem)
            if not path:
                continue
            out[stem] = L.assemble(L.elements_of(L.load_raw(path)))

    if ctx is None:
        body()
    else:
        with ctx:
            body()
    return out


# ---------------------------------------------------------------------------
def load_split(split: str, keep_types: set[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    """
    Rules of another split (`text_content`, `chart`), grouped by document stem.

    `keep_types` filters to just the rule types that feed the dimension being checked.
    `text_content.jsonl` holds 141,322 rules, but Content Faithfulness reads only the
    eight `*_percent` / `extra_content` correctness types plus `order`
    (`evaluators/parse.py:356-372, 475-495`) — about 16,600 rules. Dropping the rest
    (105k `missing_specific_word`, 19k `missing_specific_sentence`) is exact, not an
    approximation: those types are in no Content-Faithfulness category.
    """
    rules = L.load_rules(os.path.join(L.PB_ROOT, "data", f"{split}.jsonl"))
    if keep_types is None:
        return rules
    return {
        stem: kept
        for stem, rows in rules.items()
        if (kept := [r for r in rows if r["type"] in keep_types])
    }


CF_TYPES = set(L.CORRECTNESS_TYPES) | set(L.ORDER_TYPES)
SPLIT_TYPES = {"text_content": CF_TYPES, "chart": {"chart_data_point"}}


TABLE_BLOCK_RE = re.compile(r"<table\b.*?</table>", re.S)
PIPE_ROW_RE = re.compile(r"^\s*\|.*$", re.M)


def table_signature(md: str) -> tuple:
    """Everything a table metric could read: HTML table blocks plus pipe-table rows."""
    return (tuple(TABLE_BLOCK_RE.findall(md)), tuple(PIPE_ROW_RE.findall(md)))


def _split_score(split: str, md_by_stem: dict[str, str],
                 rules: dict[str, list[dict[str, Any]]]) -> tuple[float, int]:
    """Aggregate the dimension metric of `split` over `md_by_stem`."""
    vals: list[float] = []
    for stem, md in md_by_stem.items():
        rows = rules.get(stem)
        if not rows:
            continue
        scored = L.run_rules(md, rows)
        if split == "text_content":
            v = L.faithfulness_from_rule_scores(scored)
        else:  # chart -> plain rule_pass_rate over chart_data_point rules
            v = (sum(s for _, s in scored) / len(scored)) if scored else None
        if v is not None:
            vals.append(v)
    return L.aggregate(vals), len(vals)


_BASE_CACHE: dict[tuple[str, int], tuple[float, int]] = {}


def collateral(
    patch_md: Callable[[str], str] | None,
    provider_ctx: Callable[[], Any] | None,
    baseline_md: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """
    Content Faithfulness, Charts, and table/VG invariance for one patch.

    `baseline_md` is {split: {stem: unpatched markdown}} — for markdown-level patches
    this is the shipped markdown; for provider-level patches it is the re-assembled
    baseline, so the comparison is paired. Baseline scores are memoised per
    `baseline_md` identity, since many patches share the same one.
    """
    res: dict[str, Any] = {}
    for split, metric in (("text_content", "cf"), ("chart", "charts")):
        rules = load_split(split, SPLIT_TYPES[split])
        base_md = baseline_md[split]
        key = (split, id(base_md))
        if key not in _BASE_CACHE:
            _BASE_CACHE[key] = _split_score(split, base_md, rules)
        base_val, n = _BASE_CACHE[key]

        if provider_ctx is not None:
            patched_md = provider_markdown(provider_ctx, sorted(base_md))
        else:
            patched_md = {s: (patch_md(m) if patch_md else m) for s, m in base_md.items()}
        patched_val, _ = _split_score(split, patched_md, rules)

        res[metric] = {
            "baseline": base_val,
            "patched": patched_val,
            "delta_pts": 100 * (patched_val - base_val),
            "n": n,
        }

    # Table / Visual-Grounding invariance, over every document in every split.
    changed_tables = 0
    checked = 0
    all_md = {s: m for split_md in baseline_md.values() for s, m in split_md.items()}
    if provider_ctx is not None:
        patched_all = provider_markdown(provider_ctx, sorted(all_md))
    else:
        patched_all = {s: (patch_md(m) if patch_md else m) for s, m in all_md.items()}
    for stem, md in all_md.items():
        checked += 1
        if table_signature(md) != table_signature(patched_all.get(stem, md)):
            changed_tables += 1
    res["tables_changed_docs"] = changed_tables
    res["tables_checked_docs"] = checked
    return res


# ---------------------------------------------------------------------------
def main() -> None:
    want_collateral = "--collateral" in sys.argv

    md_corpus = list(L.iter_markdown_corpus())
    elem_corpus = list(L.iter_element_corpus(require_byte_exact=True))
    elem_stems = {s for s, _, _ in elem_corpus}

    print(f"markdown corpus : {len(md_corpus)} docs (all scored text_formatting docs)")
    print(f"element  corpus : {len(elem_corpus)} docs (byte-exact re-assembly only)")

    md_base = L.measure_markdown_patch(None, md_corpus)
    print(f"\nBASELINE (full 476)                                  SemFmt={md_base['semfmt'] * 100:6.2f}")
    print(f"  per-type: { {t: round(v, 4) for t, v in md_base['per_type'].items()} }")
    el_base = measure_provider_patch(None, elem_corpus)
    print(f"BASELINE (element sub-corpus, {el_base['n']} scored docs)     "
          f"SemFmt={el_base['semfmt'] * 100:6.2f}")
    # Fraction of the full corpus's scored documents the sub-corpus covers, used to
    # rescale sub-corpus deltas into a full-corpus estimate.
    cover = len([s for s in md_base["docs"] if s in elem_stems]) / len(md_base["docs"])
    print(f"  sub-corpus covers {cover:.1%} of scored documents; sub-corpus deltas are also")
    print(f"  shown rescaled by that fraction as a full-corpus estimate.\n")

    results: dict[str, Any] = {
        "baseline_full": md_base["semfmt"],
        "baseline_elem": el_base["semfmt"],
        "coverage": cover,
        "md_patches": {},
        "provider_patches": {},
        "stacks": {},
        "collateral": {},
    }

    print("=" * 108)
    print("MARKDOWN-LEVEL PATCHES  (full 476-doc corpus; deltas land directly on the board)")
    print("=" * 108)
    print(f"{'patch':<48s} {'SemFmt':>7s} {'dSemFmt':>8s} {'dOvr':>6s} | "
          f"{'bold':>6s} {'title':>6s} {'hier':>6s}")
    for name, fn in P.MD_PATCHES.items():
        r = L.measure_markdown_patch(fn, md_corpus)
        d = 100 * (r["semfmt"] - md_base["semfmt"])
        pt = r["per_type"]
        print(f"{name:<48s} {r['semfmt'] * 100:7.2f} {d:+8.2f} {d / 5:+6.2f} | "
              f"{pt.get('is_bold', 0):6.3f} {pt.get('is_title', 0):6.3f} "
              f"{pt.get('title_hierarchy_percent', 0):6.3f}")
        results["md_patches"][name] = {"semfmt": r["semfmt"], "d_semfmt": d,
                                      "d_overall": d / 5, "per_type": pt}

    print()
    print("=" * 108)
    print("PROVIDER-LEVEL PATCHES  (319-doc byte-exact sub-corpus)")
    print("=" * 108)
    print(f"{'patch':<48s} {'SemFmt':>7s} {'dSemFmt':>8s} {'dOvr':>6s} {'dOvr*cov':>9s} | "
          f"{'bold':>6s} {'title':>6s} {'hier':>6s}")
    for name, ctxf in P.PROVIDER_PATCHES.items():
        r = measure_provider_patch(ctxf, elem_corpus)
        d = 100 * (r["semfmt"] - el_base["semfmt"])
        pt = r["per_type"]
        print(f"{name:<48s} {r['semfmt'] * 100:7.2f} {d:+8.2f} {d / 5:+6.2f} {d * cover / 5:+9.2f} | "
              f"{pt.get('is_bold', 0):6.3f} {pt.get('is_title', 0):6.3f} "
              f"{pt.get('title_hierarchy_percent', 0):6.3f}")
        results["provider_patches"][name] = {"semfmt": r["semfmt"], "d_semfmt_sub": d,
                                            "d_overall_sub": d / 5,
                                            "d_overall_rescaled": d * cover / 5,
                                            "per_type": pt}

    # ---- stacked combinations, measured not assumed ----
    print()
    print("=" * 108)
    print("STACKED COMBINATIONS  (measured, not summed — these levers overlap)")
    print("=" * 108)
    stacks: list[tuple[str, Callable[[], Any] | None, Callable[[str], str] | None]] = [
        ("T5 + G  (relaxed titles + E + F)", P.PROVIDER_PATCHES["T5 titleish: drop caps+punct+label, 30 words"],
         P.compose(P.bold_labels, P.bold_standalone)),
        ("T5 + G2 (relaxed titles + E + F2)", P.PROVIDER_PATCHES["T5 titleish: drop caps+punct+label, 30 words"],
         P.compose(P.bold_labels, P.bold_own_line)),
        ("T5 + C2 + G2 (titles + short-Text head + bold)",
         None, None),  # filled below with a composed provider ctx
        # MAXBOLD alone on the element sub-corpus, so T5's marginal contribution on top
        # of it can be read against a like-for-like reference.
        ("MAXBOLD alone (element sub-corpus reference)", lambda: __import__("contextlib").nullcontext(),
         P.bold_all_lines),
        ("T5 + MAXBOLD", P.PROVIDER_PATCHES["T5 titleish: drop caps+punct+label, 30 words"], P.bold_all_lines),
        ("T5 + C2 + C3 + MAXBOLD", None, None),  # filled below
        ("G2 + MAXBOLD-ordering check", None, P.compose(P.bold_labels, P.bold_own_line, P.bold_all_lines)),
    ]

    # A composed provider patch needs both swaps live at once; build it explicitly.
    import contextlib

    def t5_plus_c2() -> Any:
        stack = contextlib.ExitStack()
        stack.enter_context(P.PROVIDER_PATCHES["T5 titleish: drop caps+punct+label, 30 words"]())
        stack.enter_context(P.PROVIDER_PATCHES["C2 short single-line Text -> '# '"]())
        return stack

    def t5_c2_c3() -> Any:
        stack = contextlib.ExitStack()
        stack.enter_context(P.PROVIDER_PATCHES["T5 titleish: drop caps+punct+label, 30 words"]())
        stack.enter_context(P.PROVIDER_PATCHES["C2 short single-line Text -> '# '"]())
        stack.enter_context(P.PROVIDER_PATCHES["C3 List-item -> '## ' instead of '- '"]())
        return stack

    stacks[2] = ("T5 + C2 + G2 (titles + short-Text head + bold)", t5_plus_c2,
                 P.compose(P.bold_labels, P.bold_own_line))
    stacks[5] = ("T5 + C2 + C3 + MAXBOLD", t5_c2_c3, P.bold_all_lines)

    print(f"{'stack':<48s} {'SemFmt':>7s} {'dSemFmt':>8s} {'dOvr':>6s} | "
          f"{'bold':>6s} {'title':>6s} {'hier':>6s}   corpus")
    for name, ctxf, mdfn in stacks:
        if ctxf is None:
            r = L.measure_markdown_patch(mdfn, md_corpus)
            base = md_base["semfmt"]
            tag = "full 476"
        else:
            # provider patch first (it runs earlier in the pipeline), then md patch
            vals: list[float] = []
            type_acc: dict[str, list[float]] = collections.defaultdict(list)
            with ctxf():
                for stem, els, rows in elem_corpus:
                    md = L.assemble(els)
                    if mdfn:
                        md = mdfn(md)
                    s, _c, pt = L.score_from_rule_scores(L.run_rules(md, rows))
                    if s is not None:
                        vals.append(s)
                    for t, v in pt.items():
                        type_acc[t].append(v)
            r = {"semfmt": L.aggregate(vals),
                 "per_type": {t: L.aggregate(v) for t, v in type_acc.items()}}
            base = el_base["semfmt"]
            tag = f"elem {len(elem_corpus)}"
        d = 100 * (r["semfmt"] - base)
        pt = r["per_type"]
        print(f"{name:<48s} {r['semfmt'] * 100:7.2f} {d:+8.2f} {d / 5:+6.2f} | "
              f"{pt.get('is_bold', 0):6.3f} {pt.get('is_title', 0):6.3f} "
              f"{pt.get('title_hierarchy_percent', 0):6.3f}   {tag}")
        results["stacks"][name] = {"semfmt": r["semfmt"], "d_semfmt": d, "d_overall": d / 5,
                                  "corpus": tag, "per_type": pt}

    # ---- collateral damage ----
    if want_collateral:
        print()
        print("=" * 108)
        print("COLLATERAL DAMAGE ON THE OTHER DIMENSIONS")
        print("=" * 108)
        arts = L.artifact_index()
        baseline_md: dict[str, dict[str, str]] = {}
        for split in ("text_content", "chart"):
            rules = load_split(split)
            baseline_md[split] = {}
            for stem in rules:
                path = arts.get(stem)
                if path:
                    baseline_md[split][stem] = L.load_raw(path).get("markdown") or ""
        print(f"  text_content docs with artifacts: {len(baseline_md['text_content'])}")
        print(f"  chart        docs with artifacts: {len(baseline_md['chart'])}")

        # Validate the collateral baselines against the shipped per-split reports
        # before trusting any delta computed from them.
        zero = collateral(None, None, baseline_md)
        print(f"  CF     baseline replay = {zero['cf']['baseline'] * 100:.2f}   "
              f"shipped = {L.OURS['Content_Faithfulness']:.2f}  "
              f"(n={zero['cf']['n']})")
        print(f"  Charts baseline replay = {zero['charts']['baseline'] * 100:.2f}   "
              f"shipped = {L.OURS['Charts']:.2f}  (n={zero['charts']['n']})")
        results["collateral_baseline_check"] = zero
        print()

        to_check: list[tuple[str, Callable[[str], str] | None, Callable[[], Any] | None]] = [
            ("E  bold run-in 'Label:' prefixes", P.bold_labels, None),
            ("F  bold short standalone lines", P.bold_standalone, None),
            ("F2 bold short own-lines", P.bold_own_line, None),
            ("G2 = E + F2", P.compose(P.bold_labels, P.bold_own_line), None),
            ("MAXBOLD bold every non-table line", P.bold_all_lines, None),
            ("HEADALL '# ' every non-table line", P.head_all_lines, None),
            ("T5 relaxed _is_titleish", None,
             P.PROVIDER_PATCHES["T5 titleish: drop caps+punct+label, 30 words"]),
            ("C2 short single-line Text -> '# '", None,
             P.PROVIDER_PATCHES["C2 short single-line Text -> '# '"]),
        ]
        print(f"{'patch':<40s} {'CF base':>8s} {'CF new':>8s} {'dCF':>7s} | "
              f"{'Ch base':>8s} {'Ch new':>8s} {'dCh':>7s} | tables changed")
        # For a provider patch the baseline must also be re-assembled from stored
        # elements, so the comparison is paired rather than shipped-vs-replayed.
        # Built once and reused, so its baseline score is memoised.
        replay_md: dict[str, dict[str, str]] = {
            split: provider_markdown(None, sorted(baseline_md[split]))
            for split in ("text_content", "chart")
        }
        for name, mdfn, ctxf in to_check:
            bl = replay_md if ctxf is not None else baseline_md
            c = collateral(mdfn, ctxf, bl)
            print(f"{name:<40s} {c['cf']['baseline'] * 100:8.2f} {c['cf']['patched'] * 100:8.2f} "
                  f"{c['cf']['delta_pts']:+7.2f} | "
                  f"{c['charts']['baseline'] * 100:8.2f} {c['charts']['patched'] * 100:8.2f} "
                  f"{c['charts']['delta_pts']:+7.2f} | "
                  f"{c['tables_changed_docs']}/{c['tables_checked_docs']}")
            results["collateral"][name] = c

    json.dump(results, open(os.path.join(HERE, "_semfmt_measure.json"), "w"), indent=1,
              default=lambda o: None)
    print("\nwrote scripts/_semfmt_measure.json")


if __name__ == "__main__":
    main()
