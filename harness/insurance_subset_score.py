#!/usr/bin/env python3
"""Score a ParseBench run restricted to its insurance-document subset.

WHY THIS EXISTS
---------------
ParseBench's headline number is an average over ~2,079 pages of mixed enterprise
documents (government statistics, semiconductor datasheets, sustainability
reports, academic papers, ...). For an insurance-specific product the useful
claim is not "we score X on ParseBench" but "we score X on the insurance
documents inside ParseBench". This script computes exactly that, using the
benchmark's own aggregation code so the numbers are directly comparable to the
published per-dimension and overall scores rather than being re-derived by hand.

Glossary (no unexplained shorthand)
-----------------------------------
* ParseBench "dimension"  -- one of five capability slices, each with its own
  ground truth format and its own metric. The five are: Tables, Charts,
  Content Faithfulness, Semantic Formatting, Visual Grounding. Internally the
  framework calls them `table`, `chart`, `text_content`, `text_formatting`,
  `layout`.
* "rule"                  -- one machine-checkable assertion about one page,
  e.g. "the value 0.8079 must appear labelled 'IF / 193 UN Member States'".
  Rules live in the dataset's `*.jsonl` files, one JSON object per line.
* SERFF                   -- System for Electronic Rate and Form Filing, the
  system through which US insurers file rates and policy forms with state
  insurance regulators. SERFF pages in this dataset are real rate filings.
* NAIC                    -- National Association of Insurance Commissioners,
  the US body that coordinates state insurance regulation.
* NCCI                    -- National Council on Compensation Insurance, which
  publishes the workers' compensation rating manuals US insurers file against.
* SFCR                    -- Solvency and Financial Condition Report, the
  public regulatory report EU insurers publish under the Solvency II regime.
* IUL                     -- Indexed Universal Life, a life insurance product;
  an "illustration" is the projected-values document shown to a buyer.
* GriTS / GTRM            -- the table-similarity metrics ParseBench uses for
  the Tables dimension (`grits_trm_composite`); a grid-comparison F-score.

WHERE THE AGGREGATION LOGIC COMES FROM (verified by reading, not assumed)
------------------------------------------------------------------------
1. Per-example metric values are re-aggregated by calling the framework's own
   method, so failure padding / micro pooling / `_predicted` variants behave
   identically to a normal run:
       src/parse_bench/evaluation/runner.py:1125  EvaluationRunner._aggregate_metrics
   The macro average this script reports is that method's
       aggregate[f"avg_{metric_name}"] = sum(values) / len(values)
   at src/parse_bench/evaluation/runner.py:1254.
2. The single "headline" metric for each dimension is the framework's own
   default-metric table:
       src/parse_bench/analysis/aggregation_report.py:36-42  _DEFAULT_METRICS
   which maps table -> grits_trm_composite, layout ->
   layout_element_rule_pass_rate, text_content -> content_faithfulness,
   text_formatting -> semantic_formatting, and (by the fallback at
   src/parse_bench/analysis/aggregation_report.py:69-75) chart ->
   rule_pass_rate.
3. The overall score is the unweighted mean of the five dimension scores, per
   the leaderboard's own label "Overall / Average across categories" at
   src/parse_bench/analysis/leaderboard_report.py:780-781. Cross-checked
   arithmetically against leaderboard.csv: KDL-Frontier-Parser-nano is listed
   as Tables 85.56, Charts 63.41, Content_Faithfulness 87.19,
   Semantic_Formatting 66.81, Visual_Grounding 78.84, Overall 76.36, and
   (85.56+63.41+87.19+66.81+78.84)/5 = 76.362.

WHAT IT READS
-------------
The scores come from the per-dimension `_evaluation_report.json` files that
`parse-bench evaluate run` writes (one per dimension subdirectory). Those hold
`per_example_results`, i.e. the per-page metric values. The sibling
`*.result.json` files in the same directories are *inference* outputs (raw and
normalised parser output) and carry no metrics, so they are used only to report
how many pages of each dimension the run has produced -- which is what makes a
partial run visible instead of silently mis-scored.

USAGE
-----
    python scripts/insurance_subset_score.py output/kdl_frontier_nano
    python scripts/insurance_subset_score.py output/kdl_frontier_nano --subset other
    python scripts/insurance_subset_score.py output/kdl_frontier_nano \
        --eval-dir /tmp/pb_eval_partial --data-dir data --json

Deterministic: no randomness, no wall-clock dependence, no network. Depends only
on the standard library plus the `parse_bench` package already in this repo.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# The insurance subset.
#
# Each entry is (document_family, expected_page_count, why_it_is_insurance).
# `document_family` is the source document's file stem; the dataset splits long
# documents into one PDF per sampled page, named `<family>_p<n>` or
# `<family>_page<n>`. `expected_page_count` is asserted at run time so that a
# future dataset revision which adds or removes pages fails loudly instead of
# quietly changing the denominator.
#
# HOW THIS LIST WAS BUILT (see reports/insurance_subset.md for the full audit):
#   1. Filename patterns (`insur`, `serff`, `sigma`, insurer names, ...).
#   2. A scan of every annotation rule's ground-truth text in the dataset's five
#      `*.jsonl` files, for insurance vocabulary.
#   3. A scan of the extractable text of all 2,037 text-bearing PDFs among the
#      2,079 documents, for high-precision insurance markers.
#   4. Every candidate from (1)-(3) was then read individually and kept or
#      rejected by hand. False positives rejected this way included a MOSFET
#      datasheet ("AONR32314"), a mediator panel list whose practice areas
#      mention "Insurance/Coverage" ("MAP-CategoryI-LON"), bank filings that
#      mention federal deposit insurance, and a Cardiff University paper whose
#      filename ("text_simple__cardif") looks like insurer BNP Paribas Cardif.
# --------------------------------------------------------------------------
INSURANCE_FAMILIES: dict[str, list[tuple[str, int, str]]] = {
    "chart": [
        ("2023-05-sigma-01-english", 7, "Swiss Re Institute 'sigma' insurance-market report"),
        ("67c07d7f417ce", 4, "AXA FY24 results: commercial lines / AXA XL Reinsurance"),
        ("SRI-Insights-August 2025_media_embargo", 5, "Swiss Re Institute sigma insights, insured catastrophe losses"),
        ("aviva-plc-annual-report-and-accounts-2024", 1, "annual report of insurer Aviva plc"),
        ("modeling-insured-catastrophe-loss-a-global-perspective-for-2025", 1, "insured catastrophe loss modelling"),
        ("natural-catastrophe-and-climate-report-2023", 5, "reinsurance broker nat-cat insured-loss report"),
        ("natural-catastrophe-and-climate-report-q3-2025", 1, "reinsurance broker nat-cat insured-loss report"),
        ("natural_catastrophe_and_climate_report_2024_h1", 1, "reinsurance broker nat-cat insured-loss report"),
        ("r_qt1212e", 2, "BIS Quarterly Review chapter on reinsurance and catastrophe bonds"),
        ("sigma-1-2021-en", 5, "Swiss Re Institute 'sigma' insurance-market report"),
        ("sri-sigma-natural-catastrophes-1-2025", 8, "Swiss Re Institute sigma nat-cat insured-loss report"),
    ],
    "layout": [
        ("2023-05-sigma-01-english", 3, "Swiss Re Institute sigma"),
        (
            "2025-mid-year-property-casualty-and-title-insurance-industries-analysis-report",
            1,
            "property & casualty / title insurance industry analysis",
        ),
        ("67c07d7f417ce", 1, "AXA FY24 results"),
        ("CEJ Lincoln Max Income illustration att1", 3, "Lincoln indexed universal life policy illustration"),
        ("Intact-Financial-Corporation-2020-Annual-Report", 1, "annual report of P&C insurer Intact Financial"),
        ("Integrated_Report_2025_e", 1, "Tokio Marine Holdings integrated annual report (insurer)"),
        ("Lancashire-Annual-Report-and-Accounts-2024", 3, "annual report of specialty insurer/reinsurer Lancashire"),
        ("SRI-Insights-August 2025_media_embargo", 1, "Swiss Re Institute sigma insights"),
        ("airmic-explained-artex-captive-insurance-v2", 1, "captive insurance explainer"),
        ("iul age 50 example", 2, "indexed universal life policy illustration"),
        ("p29", 1, "Arkansas rate exhibit, Allmerica Financial Benefit Insurance Company"),
        ("pdf_29f6bce2b33c", 1, "Lloyd's syndicate underwriting-performance analysis"),
        ("pdf_ccc50d8a450e", 2, "annual report of a specialty insurance/reinsurance underwriter"),
        ("pdf_d47bf4ce95f6", 3, "AXA board biographies (insurer annual report)"),
        ("pdf_fe474dd12f60", 1, "indexed universal life policy illustration (Builder IUL7)"),
        ("progressive_2024corporate-sustainability-report", 1, "sustainability report of auto insurer Progressive"),
        ("sample_page_16", 1, "Arkansas rate exhibit, Allmerica Financial Benefit Insurance Company"),
        ("sigma-1-2021-en", 1, "Swiss Re Institute sigma"),
        ("sri-sigma-natural-catastrophes-1-2025", 1, "Swiss Re Institute sigma nat-cat"),
    ],
    "table": [
        ("1H-2025-Global-Catastrophe-Recap", 1, "insured catastrophe loss recap"),
        ("20230125-weather-climate-catastrophe-insight", 1, "insured catastrophe loss report"),
        ("AZ LIC Rate Tables 2.0.v2", 14, "Arizona insurance company rate tables (per-policy rates by limit)"),
        ("BRWS-134565917", 34, "auto insurance rate filing: BI/PD/PIP/UM/COMP/COLL rate relativities"),
        ("BSC-Hospital-List-by-County (2)", 1, "Blue Shield of California HMO/PPO hospital network list"),
        ("CINF.2006.page_93.pdf_140594", 1, "Cincinnati Financial (insurer) annual-report table"),
        ("FBLB-134215544", 30, "Farm Bureau Property & Casualty Insurance Company rate filing"),
        ("LTCprodkitLincolnStateAvailabilty0216", 2, "Lincoln MoneyGuard long-term-care insurance product availability"),
        ("METLIFE-10Q-20240205 unrestricted", 2, "MetLife quarterly report (insurer)"),
        ("PrintableRulesSection", 1, "insurance rules manual pro-rata factor table"),
        ("SERFF_CA_random_pages 1", 104, "California insurance rate/form filings (SERFF)"),
        ("SERFF_Interstate_random_pages 1", 15, "Interstate Insurance Product Regulation Compact filings (SERFF)"),
        ("SERFF_TX_random_pages 1", 74, "Texas insurance rate/form filings (SERFF)"),
        ("UNM.2007.page_51.pdf_45297", 1, "Unum (insurer) annual-report table"),
        ("axa_urd2024_accessible_va", 1, "AXA universal registration document, insurance subsidiary ratings"),
        ("gallagherre-reinsurance-market-report-2024", 1, "reinsurance market report"),
        ("left-side sparse and no outline", 1, "North Carolina homeowners insurance losses by cause"),
        (
            "metlife_sustainability_report_2024_non_gaap_and_other_financial_disclosures",
            1,
            "MetLife financial disclosures (insurer)",
        ),
        ("p29", 1, "Arkansas rate exhibit, Allmerica Financial Benefit Insurance Company"),
        ("sample_page_16", 1, "Arkansas rate exhibit, Allmerica Financial Benefit Insurance Company"),
        ("tabular_2", 1, "Brazilian health plan referenced-hospital network grid by plan tier"),
        ("xl-re-europe-se-sfcr-2024", 2, "XL Re Europe SE Solvency and Financial Condition Report"),
    ],
    # The `text` inference directory feeds two evaluation dimensions,
    # text_content and text_formatting (see _SHARED_EVAL_GROUPS at
    # src/parse_bench/pipeline/cli.py:19). One PDF per document, no page splits.
    "text": [
        ("text_misc__dash", 1, "USAble Mutual Insurance Company small-group rate filing"),
        ("text_misc__docusigned", 1, "Texas Department of Insurance Commissioner's Order (NCCI item B-1447)"),
        ("text_misc__edit2", 1, "American Bankers Insurance Company of Florida renters programme manual"),
        ("text_misc__mark2", 1, "Ohio auto 'Road and Residence' rate and rule filing manual"),
        ("text_misc__templated", 1, "Illinois Department of Insurance letter-of-submission template"),
        ("text_multicolumns__3colceo", 1, "reinsurance group chairman's message"),
        ("text_multicolumns__3colsep", 1, "insurer annual report (motor/health/travel insurance)"),
        ("text_multicolumns__definitions", 1, "insurance glossary (policyholder, in-force, grievance ratio)"),
        ("text_multilang__arabic", 1, "Islamic Arab Insurance Co (SALAMA) policy wording"),
        ("text_multilang__discrimination", 1, "Geisinger Health Plan / Geisinger Indemnity Insurance Company notice"),
        ("text_multilang__german", 1, "German household contents insurance (Hausratversicherung) leaflet"),
        ("text_multilang__hindi", 1, "New Zealand Natural Hazards Insurance scheme consumer notice (Hindi)"),
        ("text_multilang__russian", 1, "California Department of Insurance consumer notice (Russian)"),
        ("text_multilang__spanish", 1, "Santander Seguros insurance product information sheet"),
        ("text_ocr__simple", 1, "actuarial loss-development / loss-reserve analysis"),
        ("text_simple__appendix", 1, "actuarial memorandum, Combined Insurance Company of America"),
        ("text_simple__edited", 1, "National Union Fire Insurance psychiatrists professional liability manual"),
        ("text_simple__hca", 1, "Washington Apple Health public health-insurance programme rules"),
        ("text_simple__instruct", 1, "Arizona property & casualty form, rate and rule filing instructions"),
        ("text_simple__marked", 1, "North Carolina Department of Insurance SERFF rate-filing instructions"),
        ("text_simple__partial", 1, "health insurance rate-increase justification (minimum loss ratio)"),
        ("text_simple__predictive", 1, "insurance predictive-model filing checklist"),
        ("text_simple__revision", 1, "NCCI workers compensation basic manual revision"),
        ("text_simple__slide", 1, "NAIC principles slide"),
        ("text_simple__strikeUnderline", 1, "health plan eligibility/enrolment provisions (Medicaid/CHIP)"),
    ],
}

# Evaluation dimension -> (report subdirectory, inference subdirectory,
# dataset rule file stem). Report and inference directories differ for the two
# text dimensions, which share one inference directory.
DIMENSIONS: list[tuple[str, str, str]] = [
    ("table", "table", "table"),
    ("chart", "chart", "chart"),
    ("text_content", "text", "text_content"),
    ("text_formatting", "text", "text_formatting"),
    ("layout", "layout", "layout"),
]

# Human-facing dimension names, matching the columns of leaderboard.csv.
DISPLAY_NAMES = {
    "table": "Tables",
    "chart": "Charts",
    "text_content": "Content Faithfulness",
    "text_formatting": "Semantic Formatting",
    "layout": "Visual Grounding",
}

# Only a page-number suffix may follow a family name. Requiring the letter "p"
# prevents `text_multilang__german` from swallowing `text_multilang__german2`.
_PAGE_SUFFIX = re.compile(r"[_ -]?p(?:age|g)?[_ ]?\d+\Z", re.IGNORECASE)


def _strip_page_suffix(stem: str) -> str:
    """Return `stem` with a trailing page-number suffix removed, if present."""
    return _PAGE_SUFFIX.sub("", stem)


@lru_cache(maxsize=None)
def insurance_stems(inference_dir: str) -> frozenset[str]:
    """Family names declared insurance for one inference directory."""
    return frozenset(family for family, _count, _why in INSURANCE_FAMILIES.get(inference_dir, []))


def classify(example_id: str) -> str:
    """Return "insurance" or "other" for a ParseBench example id.

    An example id looks like `table/SERFF_CA_random_pages 1_page276`, i.e.
    `<inference_dir>/<file stem>`.
    """
    if "/" not in example_id:
        return "other"
    inference_dir, stem = example_id.split("/", 1)
    stems = insurance_stems(inference_dir)
    if stem in stems:
        return "insurance"
    return "insurance" if _strip_page_suffix(stem) in stems else "other"


# --------------------------------------------------------------------------
# Loading and re-aggregating
# --------------------------------------------------------------------------


def _import_framework() -> tuple[Any, Any, Any]:
    """Import the pieces of `parse_bench` this script reuses.

    Adds `<repo>/src` to `sys.path` so the script also runs from a plain
    checkout without the package being installed.
    """
    repo_src = Path(__file__).resolve().parent.parent / "src"
    if repo_src.is_dir() and str(repo_src) not in sys.path:
        sys.path.insert(0, str(repo_src))
    from parse_bench.analysis.aggregation_report import _DEFAULT_METRICS
    from parse_bench.evaluation.runner import EvaluationRunner
    from parse_bench.schemas.evaluation import EvaluationSummary

    return EvaluationSummary, EvaluationRunner, _DEFAULT_METRICS


def headline_metric(dimension: str, available: set[str], default_metrics: dict[str, str]) -> str:
    """Pick the dimension's headline metric.

    Mirrors src/parse_bench/analysis/aggregation_report.py:66-75: use the
    framework's default for the dimension, else `rule_pass_rate`, else give up.
    """
    metric = default_metrics.get(dimension, "rule_pass_rate")
    if metric in available:
        return metric
    if "rule_pass_rate" in available:
        return "rule_pass_rate"
    return ""


def count_rules(data_dir: Path, rule_file_stem: str, example_ids: set[str]) -> int | None:
    """Count annotation rules attached to `example_ids` in a dataset rule file.

    Returns None when the rule file is not available, so a missing dataset
    degrades to a blank column instead of a wrong number.
    """
    path = data_dir / f"{rule_file_stem}.jsonl"
    if not path.is_file():
        return None
    total = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            pdf = json.loads(line).get("pdf", "")
            # "docs/table/SERFF_CA_random_pages 1_page276.pdf" -> example id
            parts = pdf.split("/")
            if len(parts) < 3:
                continue
            example_id = f"{parts[-2]}/{parts[-1].rsplit('.', 1)[0]}"
            if example_id in example_ids:
                total += 1
    return total


def data_dir_candidates(output_dir: Path, explicit: str | None) -> list[Path]:
    """Candidate dataset directories, most-trusted first.

    `_metadata.json` can point at the 12-document smoke split (`data/test`)
    left over from an earlier run, which would silently make every rule count
    and page-count check wrong. So the caller picks the first candidate whose
    declared page counts actually verify, rather than trusting the metadata.
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    metadata = output_dir / "_metadata.json"
    if metadata.is_file():
        try:
            recorded = json.loads(metadata.read_text(encoding="utf-8")).get("test_cases_dir")
        except (OSError, json.JSONDecodeError):
            recorded = None
        if recorded:
            candidates.append(Path(recorded))
    candidates.append(Path(__file__).resolve().parent.parent / "data")
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        if candidate.is_dir() and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def verify_subset(data_dir: Path | None) -> list[str]:
    """Check declared page counts against the dataset. Returns problem strings."""
    if data_dir is None:
        return ["dataset not found, declared page counts not verified"]
    docs = data_dir / "docs"
    if not docs.is_dir():
        return [f"{docs} not found, declared page counts not verified"]
    problems: list[str] = []
    for inference_dir, families in INSURANCE_FAMILIES.items():
        directory = docs / inference_dir
        if not directory.is_dir():
            problems.append(f"missing dataset directory {directory}")
            continue
        stems = [p.stem if p.suffix.lower() == ".pdf" else p.name for p in sorted(directory.iterdir())]
        for family, expected, _why in families:
            found = sum(1 for s in stems if s == family or (s.startswith(family) and _PAGE_SUFFIX.fullmatch(s[len(family) :])))
            if found != expected:
                problems.append(f"{inference_dir}/{family}: declared {expected} page(s), dataset has {found}")
    return problems


def score_dimension(
    dimension: str,
    report_dir: Path,
    output_dir: Path,
    subset: str,
    framework: tuple[Any, Any, Any],
) -> dict[str, Any]:
    """Aggregate one dimension over the requested subset.

    `output_dir` is used only to detect examples the evaluation scored as a hard
    zero because inference never produced output for them (see
    src/parse_bench/evaluation/runner.py:786 "Score test cases with no inference
    result as blank output (0.0)"). That behaviour is correct for a finished run
    and misleading for an unfinished one, so the count is surfaced.
    """
    EvaluationSummary, EvaluationRunner, default_metrics = framework
    report_path = report_dir / "_evaluation_report.json"
    row: dict[str, Any] = {
        "dimension": dimension,
        "display_name": DISPLAY_NAMES.get(dimension, dimension),
        "report": str(report_path),
        "metric": "",
        "score": None,
        "files": 0,
        "files_in_report": 0,
        "no_inference_output": 0,
        "note": "",
        "example_ids": set(),
    }
    if not report_path.is_file():
        row["note"] = "no _evaluation_report.json (evaluation not run for this dimension)"
        return row

    summary = EvaluationSummary.model_validate(json.loads(report_path.read_text(encoding="utf-8")))
    row["files_in_report"] = len(summary.per_example_results)
    selected = [
        result
        for result in summary.per_example_results
        if subset == "all" or classify(result.example_id) == subset
    ]
    row["files"] = len(selected)
    row["example_ids"] = {r.example_id for r in selected}
    row["no_inference_output"] = sum(
        1 for r in selected if not (output_dir / f"{r.example_id}.result.json").is_file()
    )
    if not selected:
        row["note"] = "no matching examples in this report"
        return row

    # Reuse the framework's own aggregation (runner.py:1125) verbatim.
    runner = EvaluationRunner.__new__(EvaluationRunner)
    aggregate = EvaluationRunner._aggregate_metrics(runner, selected)

    available = {key[len("avg_") :] for key in aggregate if key.startswith("avg_")}
    metric = headline_metric(dimension, available, default_metrics)
    if not metric:
        row["note"] = "no scoreable metric present"
        return row
    row["metric"] = metric
    row["score"] = aggregate[f"avg_{metric}"]
    row["aggregate"] = aggregate
    notes: list[str] = []
    failed = sum(1 for r in selected if not r.success)
    if failed:
        notes.append(f"{failed} failed")
    if row["no_inference_output"]:
        notes.append(f"{row['no_inference_output']} scored 0 with no inference output")
    row["note"] = "; ".join(notes)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score a ParseBench run restricted to its insurance-document subset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("output_dir", help="ParseBench pipeline output directory, e.g. output/kdl_frontier_nano")
    parser.add_argument(
        "--subset",
        choices=("insurance", "other", "all"),
        default="insurance",
        help="which documents to score (default: insurance)",
    )
    parser.add_argument(
        "--eval-dir",
        default=None,
        help="directory holding the per-dimension _evaluation_report.json files "
        "(default: OUTPUT_DIR itself)",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="dataset directory holding docs/ and the *.jsonl rule files "
        "(default: read from OUTPUT_DIR/_metadata.json, else ../data)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of a table")
    parser.add_argument("--no-rule-counts", action="store_true", help="skip rule counting (avoids reading large *.jsonl)")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    if not output_dir.is_dir():
        print(f"error: not a directory: {output_dir}", file=sys.stderr)
        return 1
    eval_root = Path(args.eval_dir) if args.eval_dir else output_dir
    framework = _import_framework()

    # Pick the first candidate dataset directory whose page counts verify.
    data_dir: Path | None = None
    subset_problems = ["no dataset directory found; page counts not verified"]
    for candidate in data_dir_candidates(output_dir, args.data_dir):
        problems = verify_subset(candidate)
        if data_dir is None or not problems:
            data_dir, subset_problems = candidate, problems
        if not problems:
            break

    rows: list[dict[str, Any]] = []
    for dimension, inference_dir_name, rule_stem in DIMENSIONS:
        row = score_dimension(dimension, eval_root / dimension, output_dir, args.subset, framework)
        # Pages of this dimension that inference has actually produced.
        inference_path = output_dir / inference_dir_name
        row["result_files_on_disk"] = (
            len(list(inference_path.glob("*.result.json"))) if inference_path.is_dir() else 0
        )
        row["rules"] = (
            None
            if args.no_rule_counts or data_dir is None
            else count_rules(data_dir, rule_stem, row["example_ids"])
        )
        row.pop("example_ids", None)
        row.pop("aggregate", None)
        rows.append(row)

    scored = [r["score"] for r in rows if r["score"] is not None]
    overall = sum(scored) / len(scored) if scored else None
    complete = len(scored) == len(DIMENSIONS)

    if args.json:
        print(
            json.dumps(
                {
                    "output_dir": str(output_dir),
                    "eval_dir": str(eval_root),
                    "subset": args.subset,
                    "dimensions": rows,
                    "overall": overall,
                    "overall_is_complete": complete,
                    "subset_verification_problems": subset_problems,
                },
                indent=2,
            )
        )
        return 0

    subset_files = sum(count for families in INSURANCE_FAMILIES.values() for _f, count, _w in families)
    print(f"ParseBench subset score  --  {output_dir}")
    print(f"  subset            : {args.subset}  (insurance subset = {subset_files} of 2079 page-documents)")
    print(f"  evaluation reports: {eval_root}")
    print(f"  dataset           : {data_dir if data_dir else '(not found)'}")
    print()
    header = f"{'dimension':22} {'metric':32} {'score':>8} {'scored/disk':>12} {'rules':>8}  note"
    print(header)
    print("-" * len(header))
    for row in rows:
        score = f"{row['score'] * 100:.2f}" if row["score"] is not None else "--"
        files = f"{row['files']}/{row['result_files_on_disk']}" if row["files"] else "0"
        rules = "--" if row["rules"] is None else str(row["rules"])
        print(
            f"{row['display_name']:22} {row['metric'] or '--':32} {score:>8} {files:>12} {rules:>8}  {row['note']}"
        )
    print("-" * len(header))
    overall_text = f"{overall * 100:.2f}" if overall is not None else "--"
    print(f"{'OVERALL':22} {'unweighted mean of dimensions':32} {overall_text:>8}")
    if not complete:
        print(f"  ^ PARTIAL: only {len(scored)} of {len(DIMENSIONS)} dimensions had a score; not comparable to a full run.")
    print()
    print("Scores are shown on the 0-100 scale used by leaderboard.csv (metric value x 100).")
    print("'scored/disk' is examples scored in this subset / inference .result.json files currently present")
    print("in the dimension's directory. If 'scored' exceeds the subset size, or 'disk' is below the")
    print("dimension total, the run or its evaluation is incomplete -- read the warning below.")
    stale = sum(row["no_inference_output"] for row in rows)
    if stale:
        print()
        print(
            f"WARNING: {stale} scored example(s) have no .result.json in {output_dir}. ParseBench scores a\n"
            "test case with no inference output as a hard zero (runner.py:786). If the run was still in\n"
            "progress when the evaluation ran, these zeros are artefacts -- re-run the evaluation after\n"
            "inference completes before quoting any number."
        )
    if subset_problems:
        print()
        print("SUBSET VERIFICATION PROBLEMS (page counts do not match the dataset):")
        for problem in subset_problems:
            print(f"  - {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
