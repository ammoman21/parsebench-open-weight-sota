"""
Shared, no-GPU replay library for the ParseBench "Semantic Formatting" dimension.

WHY THIS EXISTS
---------------
ParseBench ("Parse Benchmark", LlamaIndex's document-parsing benchmark) scores a
document parser on five dimensions; one of them is *Semantic Formatting* — "did the
parser preserve the meaningful markup (bold, strikethrough, superscript, subscript,
headings, LaTeX, code fences) that a human annotator marked in the source PDF?".

We already ran the vendored `kdl_frontier_nano` pipeline over the whole corpus and
saved, for every document, (a) the final markdown and (b) the per-element model
output that produced it. There is **no GPU available**, so no new inference can be
run. Everything here therefore *replays*: it re-derives markdown from stored output,
optionally applies a candidate patch, and re-scores it with the benchmark's own
rule classes.

Two replay modes, deliberately separated because they have different fidelity:

1. FULL-CORPUS MARKDOWN REPLAY (`iter_markdown_corpus`)
   Reads the stored final markdown for all 476 scored documents. Any patch that is a
   pure function of the final markdown string can be measured here, and the baseline
   reproduces the shipped aggregate *exactly*. This is the high-confidence path.

2. ELEMENT REPLAY (`iter_element_corpus`)
   Re-assembles markdown from the stored per-element model output using the
   provider's own `_nano_assemble_markdown` + `postprocess_markdown`. Needed for
   patches that live *inside* the provider (e.g. changing which element categories
   become `#` headings, or relaxing the `_is_titleish` gate) because those run before
   the final markdown exists. Restricted to documents whose reconstruction is
   byte-identical to the shipped markdown, so patch effects are not confounded with
   reconstruction error.

TERMS USED THROUGHOUT
---------------------
* **rule** — one graded assertion from `data/text_formatting.jsonl`, e.g.
  `{"type": "is_bold", "rule": "{\\"text\\": \\"AGENCY:\\"}"}`. Each is checked against
  the produced markdown by a class in `evaluation/metrics/parse/rules_formatting.py`.
* **score** — a rule returns a float in [0, 1] (most are 0/1; the percent-style rules
  are graduated).
* **per-type average** — mean score of all rules of one type *within one document*.
* **category** — a group of rule types that the evaluator averages together
  (`normalized_text_styling`, `normalized_title_accuracy`, `normalized_latex`,
  `normalized_code_block`).
* **F-beta with beta=0.5** — the styling category combines the pass rate of positive
  rules ("this text IS bold") with that of negative rules ("this text is NOT bold")
  using a weighted harmonic mean that punishes false positives 4x harder than misses.
  This corpus contains **no** negative rules, so `neg_score` is always 1.0.
* **SemFmt** — shorthand for the `semantic_formatting` metric, reported 0..1 here and
  x100 on the leaderboard.
* **Overall** — the plain mean of the five leaderboard dimensions, so
  1 SemFmt point = 0.2 Overall points.

All logic below mirrors `evaluation/evaluators/parse.py:344-539` and
`evaluation/metrics/parse/rule_based_metric.py:132-262`; the docstrings cite the
lines it mirrors so drift can be caught.
"""

from __future__ import annotations

import collections
import glob
import json
import os
import sys
from typing import Any, Callable, Iterator

_HERE = os.path.dirname(os.path.abspath(__file__))
PB_ROOT = os.path.dirname(_HERE)  # .../parsebench
sys.path.insert(0, os.path.join(PB_ROOT, "src"))

from parse_bench.evaluation.metrics.parse.rules_base import create_test_rule  # noqa: E402
from parse_bench.evaluation.metrics.parse.utils import normalize_text  # noqa: E402

OUT_DIR = os.path.join(PB_ROOT, "output", "kdl_frontier_nano")
RULES_JSONL = os.path.join(PB_ROOT, "data", "text_formatting.jsonl")
FMT_REPORT = os.path.join(OUT_DIR, "text_formatting", "_evaluation_report.json")

# --- scoring constants, copied from evaluators/parse.py -----------------------
# parse.py:344-349 — the four positive/negative styling pairs.
STYLING_POS = ("is_bold", "is_strikeout", "is_sup", "is_sub")
STYLING_NEG = ("is_not_bold", "is_not_strikeout", "is_not_sup", "is_not_sub")
# parse.py:369
TITLE_TYPES = ("is_title", "title_hierarchy_percent")
# parse.py:511-517 — Semantic Formatting category weights.
FORMATTING_WEIGHTS = {
    "normalized_text_styling": 1.0,
    "normalized_title_accuracy": 1.0,
    "normalized_latex": 1.0 / 5.0,
    "normalized_code_block": 1.0 / 5.0,
}
# parse.py:356-372 — the correctness / order categories, used for the
# Content-Faithfulness collateral-damage check on the text_content split.
CORRECTNESS_TYPES = (
    "missing_word_percent",
    "unexpected_word_percent",
    "too_many_word_occurence_percent",
    "missing_sentence_percent",
    "unexpected_sentence_percent",
    "too_many_sentence_occurence_percent",
    "extra_content",
    "bag_of_digit_percent",
)
ORDER_TYPES = ("order",)
# parse.py:475-478
FAITHFULNESS_WEIGHTS = {"normalized_text_correctness": 1.0, "normalized_order": 0.5}

# Published KDL-Frontier-Parser-nano leaderboard row (leaderboard.csv, last data row).
PUBLISHED = {
    "Overall": 76.36,
    "Tables": 85.56,
    "Charts": 63.41,
    "Content_Faithfulness": 87.19,
    "Semantic_Formatting": 66.81,
    "Visual_Grounding": 78.84,
}
# Our reproduction of that row, read straight out of the per-split evaluation reports.
# Column -> split -> metric mapping is `scripts/sync_hf_leaderboard.py:35-42` plus
# `analysis/aggregation_report.py:36-42`:
#   Tables               = table/grits_trm_composite                 0.8576
#   Charts               = chart/rule_pass_rate                      0.6369
#   Content_Faithfulness = text_content/content_faithfulness         0.8718
#   Semantic_Formatting  = text_formatting/semantic_formatting       0.5242
#   Visual_Grounding     = layout/layout_element_rule_pass_rate      0.7419
# Overall = plain mean = 72.648, matching our reported 72.65.
OURS = {
    "Overall": 72.65,
    "Tables": 85.76,
    "Charts": 63.69,
    "Content_Faithfulness": 87.18,
    "Semantic_Formatting": 52.42,
    "Visual_Grounding": 74.19,
}


# --- rule loading -------------------------------------------------------------
def doc_stem(pdf_path: str) -> str:
    """`docs/text/text_dense__baoutou.pdf` -> `text_dense__baoutou`."""
    return os.path.basename(pdf_path)[:-4]


def load_rules(jsonl_path: str = RULES_JSONL) -> dict[str, list[dict[str, Any]]]:
    """
    Load `text_formatting.jsonl` grouped by document stem, preserving file order.

    Order matters: the evaluator averages per rule type, and `title_hierarchy_percent`
    is order-sensitive, so rules must be fed in the order the harness fed them.
    """
    by_doc: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    with open(jsonl_path) as fh:
        for line in fh:
            row = json.loads(line)
            by_doc[doc_stem(row["pdf"])].append(row)
    return dict(by_doc)


def rule_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten one jsonl row into the dict `create_test_rule` expects."""
    inner = json.loads(row["rule"]) if isinstance(row.get("rule"), str) else (row.get("rule") or {})
    return {"type": row["type"], "id": row.get("id"), "page": row.get("page"), **inner}


# --- artifact loading ---------------------------------------------------------
def artifact_index() -> dict[str, str]:
    """Map document stem -> path of its `*.raw.json` run artifact (any split)."""
    idx = {}
    for path in glob.glob(os.path.join(OUT_DIR, "*", "*.raw.json")):
        idx[os.path.basename(path)[: -len(".raw.json")]] = path
    return idx


def load_raw(path: str) -> dict[str, Any]:
    with open(path) as fh:
        return json.load(fh).get("raw_output") or {}


def elements_of(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the stored per-page element lists, tagging each with its page number."""
    return [
        dict(el, page_number=page["page_number"])
        for page in (raw.get("pages") or [])
        for el in (page.get("elements") or [])
    ]


# --- scoring ------------------------------------------------------------------
def score_from_rule_scores(
    per_rule: list[tuple[str, float]],
) -> tuple[float | None, dict[str, float], dict[str, float]]:
    """
    Turn a document's (rule_type, score) list into its Semantic Formatting value.

    Mirrors evaluators/parse.py:266-539 exactly:
      * per-type average for every type;
      * `normalized_text_styling` = F-beta(beta=0.5) over the *pooled* positive rules
        and the *pooled* negative rules (NOT the mean of per-type averages — see
        parse.py:388-406, which reads `rule_results` directly);
      * `normalized_title_accuracy` = mean of the per-type averages of
        `is_title` and `title_hierarchy_percent`;
      * latex / code_block = their own per-type averages;
      * SemFmt = weighted mean over whichever categories are present.

    :return: (semantic_formatting or None if no category present,
              category values, per-type averages)
    """
    buckets: dict[str, list[float]] = collections.defaultdict(list)
    for rtype, score in per_rule:
        buckets[rtype].append(float(score))
    per_type_avg = {t: sum(v) / len(v) for t, v in buckets.items()}

    cats: dict[str, float] = {}

    pos = [s for t in STYLING_POS if t in buckets for s in buckets[t]]
    neg = [s for t in STYLING_NEG if t in buckets for s in buckets[t]]
    if pos or neg:
        pos_score = sum(pos) / len(pos) if pos else 1.0
        neg_score = sum(neg) / len(neg) if neg else 1.0
        beta = 0.5
        if pos_score + neg_score > 0:
            cats["normalized_text_styling"] = (
                (1 + beta**2) * pos_score * neg_score / (beta**2 * pos_score + neg_score)
            )
        else:
            cats["normalized_text_styling"] = 0.0

    title_vals = [per_type_avg[t] for t in TITLE_TYPES if t in per_type_avg]
    if title_vals:
        cats["normalized_title_accuracy"] = sum(title_vals) / len(title_vals)
    if "is_latex" in per_type_avg:
        cats["normalized_latex"] = per_type_avg["is_latex"]
    if "is_code_block" in per_type_avg:
        cats["normalized_code_block"] = per_type_avg["is_code_block"]

    wsum = sum(FORMATTING_WEIGHTS[k] for k in cats)
    semfmt = sum(cats[k] * FORMATTING_WEIGHTS[k] for k in cats) / wsum if wsum else None
    return semfmt, cats, per_type_avg


def faithfulness_from_rule_scores(per_rule: list[tuple[str, float]]) -> float | None:
    """Content Faithfulness for one document (parse.py:475-495)."""
    buckets: dict[str, list[float]] = collections.defaultdict(list)
    for rtype, score in per_rule:
        buckets[rtype].append(float(score))
    per_type_avg = {t: sum(v) / len(v) for t, v in buckets.items()}
    cats: dict[str, float] = {}
    corr = [per_type_avg[t] for t in CORRECTNESS_TYPES if t in per_type_avg]
    if corr:
        cats["normalized_text_correctness"] = sum(corr) / len(corr)
    order = [per_type_avg[t] for t in ORDER_TYPES if t in per_type_avg]
    if order:
        cats["normalized_order"] = sum(order) / len(order)
    wsum = sum(FAITHFULNESS_WEIGHTS[k] for k in cats)
    return sum(cats[k] * FAITHFULNESS_WEIGHTS[k] for k in cats) / wsum if wsum else None


def run_rules(markdown: str, rows: list[dict[str, Any]]) -> list[tuple[str, float]]:
    """
    Execute the real benchmark rule objects against `markdown`.

    Mirrors rule_based_metric.compute (rule_based_metric.py:120-262): the content is
    normalised once and handed to every rule; a rule that raises scores 0.0, exactly
    as the harness does.

    BLANK-OUTPUT BRANCH. When the markdown is empty the harness short-circuits and
    forces *every* rule to 0.0 (`rule_based_metric.py:82-118`), with the comment that
    otherwise "blank-output docs silently drop out of the aggregate averages, inflating
    scores for tools that fail to parse hard documents". This matters: several
    "absence"-style rules (`unexpected_word_percent`, `too_many_word_occurence_percent`)
    would otherwise score a perfect 1.0 against an empty document, because an empty
    document contains no unexpected words. One document in this run
    (`text/text_multicolumns__2col`) has empty markdown, and omitting this branch
    inflated Content Faithfulness by +0.075 points.
    """
    if not markdown:
        return [(row["type"], 0.0) for row in rows]
    normalized = normalize_text(markdown)
    out: list[tuple[str, float]] = []
    for row in rows:
        rtype = row["type"]
        try:
            rule = create_test_rule(rule_payload(row))
            result = rule.run(markdown, normalized_content=normalized)
            score = float(result[2]) if len(result) == 3 else (1.0 if result[0] else 0.0)
        except Exception:
            score = 0.0
        out.append((rtype, score))
    return out


def aggregate(values: list[float]) -> float:
    """Corpus aggregate = plain mean over documents that produced the metric."""
    return sum(values) / len(values) if values else 0.0


# --- stored per-rule results (the shipped run, no re-execution) ---------------
def stored_rule_scores(report_path: str = FMT_REPORT) -> dict[str, list[tuple[str, float]]]:
    """
    Read the shipped evaluation report's per-rule results.

    This is the ground truth the leaderboard row was computed from, so oracle
    ceilings derived from it are exact for the full 476-document split — no replay
    fidelity caveat applies.
    """
    with open(report_path) as fh:
        report = json.load(fh)
    out: dict[str, list[tuple[str, float]]] = {}
    for ex in report["per_example_results"]:
        stem = doc_stem(ex["example_id"] + ".pdf")
        per_rule: list[tuple[str, float]] = []
        for m in ex["metrics"]:
            if m["metric_name"] != "rule_pass_rate":
                continue
            for r in m.get("metadata", {}).get("rule_results", []):
                score = r.get("score")
                if not isinstance(score, (int, float)):
                    score = 1.0 if r.get("passed") else 0.0
                per_rule.append((r.get("type", "unknown"), float(score)))
        out[stem] = per_rule
    return out


# --- corpora ------------------------------------------------------------------
def iter_markdown_corpus() -> Iterator[tuple[str, str, list[dict[str, Any]]]]:
    """
    Yield (stem, shipped_markdown, rules) for all scored text_formatting documents.

    Full 476-document coverage. Use for any patch expressible as
    `markdown -> markdown`.
    """
    rules = load_rules()
    arts = artifact_index()
    for stem in sorted(rules):
        path = arts.get(stem)
        if not path:
            continue
        md = load_raw(path).get("markdown") or ""
        yield stem, md, rules[stem]


def iter_element_corpus(
    require_byte_exact: bool = True,
) -> Iterator[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]]:
    """
    Yield (stem, elements, rules) for documents that can be re-assembled from
    stored per-element output.

    `require_byte_exact` keeps only documents whose reconstruction equals the
    shipped markdown byte for byte. Documents containing Picture/Chart elements
    generally fail this because the artifact does not persist `picture_path`.
    """
    from parse_bench.inference.providers.parse import kdl_frontier_nano as K

    rules = load_rules()
    arts = artifact_index()
    for stem in sorted(rules):
        path = arts.get(stem)
        if not path:
            continue
        raw = load_raw(path)
        els = elements_of(raw)
        if require_byte_exact:
            md, _ = K._nano_assemble_markdown(els)
            if K.postprocess_markdown(md) != (raw.get("markdown") or ""):
                continue
        yield stem, els, rules[stem]


def assemble(els: list[dict[str, Any]]) -> str:
    """Provider's own element list -> final markdown path."""
    from parse_bench.inference.providers.parse import kdl_frontier_nano as K

    md, _ = K._nano_assemble_markdown(els)
    return K.postprocess_markdown(md)


# --- measurement drivers ------------------------------------------------------
def measure_markdown_patch(
    patch: Callable[[str], str] | None,
    corpus: list[tuple[str, str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    """
    Score `patch(shipped_markdown)` over the full corpus.

    :param patch: markdown -> markdown, or None for the unmodified baseline.
    :return: {"semfmt": float, "per_type": {...}, "n": int, "docs": {stem: semfmt}}
    """
    vals: list[float] = []
    per_doc: dict[str, float] = {}
    type_acc: dict[str, list[float]] = collections.defaultdict(list)
    cat_acc: dict[str, list[float]] = collections.defaultdict(list)
    for stem, md, rows in corpus:
        patched = patch(md) if patch else md
        per_rule = run_rules(patched, rows)
        semfmt, cats, per_type = score_from_rule_scores(per_rule)
        if semfmt is not None:
            vals.append(semfmt)
            per_doc[stem] = semfmt
        for t, v in per_type.items():
            type_acc[t].append(v)
        for c, v in cats.items():
            cat_acc[c].append(v)
    return {
        "semfmt": aggregate(vals),
        "n": len(vals),
        "per_type": {t: aggregate(v) for t, v in sorted(type_acc.items())},
        "cats": {c: aggregate(v) for c, v in sorted(cat_acc.items())},
        "docs": per_doc,
    }


def fmt_delta(name: str, semfmt: float, base: float) -> str:
    """One-line report row: absolute SemFmt plus SemFmt/Overall deltas in points."""
    d = 100.0 * (semfmt - base)
    return f"{name:<52s} SemFmt={semfmt * 100:6.2f}  dSemFmt={d:+6.2f}  dOverall={d / 5:+5.2f}"
