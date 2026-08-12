# ParseBench insurance-subset scores — KDL-Frontier-Parser-nano

Measured 2026-08-11 from a **complete** full-corpus run of `kdl_frontier_nano`, the top-ranked
open-weight model on ParseBench. Subset definition, matching criteria and judgement calls are in
[`insurance_subset.md`](insurance_subset.md). Reproduce with:

```bash
cd parsebench
.venv/bin/python scripts/insurance_subset_score.py output/kdl_frontier_nano --subset insurance
.venv/bin/python scripts/insurance_subset_score.py output/kdl_frontier_nano --subset other
.venv/bin/python scripts/insurance_subset_score.py output/kdl_frontier_nano --subset all
```

**Run provenance.** `parsebench/run_parity.sh` → `parse-bench run kdl_frontier_nano
--max_concurrent 8`, started 01:27 and finished 02:15 PDT on 2026-08-11 (`parity_run.log`).
Inference produced output for 2,078 of 2,079 page-documents. The one missing document,
`text/text_sparse__anex`, is **not** in the insurance subset and carries no annotation rules in
either text dimension, so no dimension was zero-padded: the script reports 0 examples scored
without inference output for every dimension and every subset. Scores below come from the run's
own `_evaluation_report.json` files written by `parse-bench evaluate run`.

---

## 1. Headline

| | Insurance subset | Non-insurance remainder | Full corpus |
|---|---:|---:|---:|
| **Overall** (unweighted mean of the five dimensions) | **74.77** | 72.92 | 72.65 |
| Page-documents | 384 | 1,695 | 2,079 |
| Annotation rules | 8,429 | 160,582 | 169,011 |

**On this run, `kdl_frontier_nano` scores 1.85 points higher on ParseBench's insurance documents
(74.77) than on everything else (72.92).** The gap is not uniform: it wins on Charts, Content
Faithfulness and Semantic Formatting, and loses on Tables and Visual Grounding.

---

## 2. Per dimension

| Dimension | Metric | Insurance | *n* | Non-insurance | *n* | Full corpus | *n* | Insurance − other |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Tables | `grits_trm_composite` | 84.18 | 290 | 87.91 | 213 | 85.76 | 503 | **−3.73** |
| Charts | `rule_pass_rate` | **70.69** | 40 | 63.16 | 528 | 63.69 | 568 | **+7.53** |
| Content Faithfulness | `content_faithfulness` | **89.63** | 25 | 87.05 | 481 | 87.18 | 506 | **+2.59** |
| Semantic Formatting | `semantic_formatting` | **57.39** | 24 | 52.14 | 452 | 52.42 | 476 | **+5.25** |
| Visual Grounding | `layout_element_rule_pass_rate` | 71.97 | 29 | 74.34 | 471 | 74.19 | 500 | **−2.38** |
| **Overall** | mean of the five | **74.77** | | 72.92 | | 72.65 | | **+1.85** |

Rules behind each score (insurance / non-insurance / all): Tables 290 / 213 / 503; Charts
366 / 4,498 / 4,864; Content Faithfulness 6,690 / 134,632 / 141,322; Semantic Formatting
345 / 5,652 / 5,997; Visual Grounding 738 / 15,587 / 16,325.

**Internal consistency check.** For every dimension, the *n*-weighted mean of the insurance and
non-insurance scores reproduces the full-corpus score to within 0.015 points (exactly, for
Tables / Charts / Content Faithfulness). The small residual on Semantic Formatting and Visual
Grounding is the framework's per-example zero-padding of failed examples, which does not
distribute linearly across a partition. This confirms the subsets partition the corpus with no
double-counting and no dropped examples.

---

## 3. What the differences mean

**Tables: −3.73 on insurance, and this is the dimension that matters most for us.** 290 of the
503 Tables pages are insurance documents (57.7 %), so the published Tables figure is already
mostly an insurance claim. The insurance tables — SERFF rate filings, auto rate-relativity grids,
per-policy rate tables — are structurally harder than the non-insurance remainder (10-K financial
statements, product catalogues): deep hierarchical headers, wide sparse grids, merged cells
spanning rate dimensions. A −3.73 gap on the subset that is the majority of the dimension means
the *non*-insurance minority is carrying the published number upward, not the reverse.

**Charts: +7.53 on insurance.** The 40 insurance chart pages are dominated by Swiss Re *sigma*
and reinsurance-broker catastrophe reports — insured-loss bar and line charts with clean series
labels and units. These are easier than the corpus average, which includes dense
multi-series OECD and UN statistical graphics. Do not read this as "we are good at insurance
charts"; read it as "insurance charts in this corpus are comparatively tractable".

**Content Faithfulness: +2.59; Semantic Formatting: +5.25.** The 25 insurance text documents are
rate-filing instructions, policy manuals, actuarial memoranda and multilingual policy wordings.
They are prose-dense and single-column, which suits a parser better than the multi-column and
scanned-OCR documents that dominate the remainder.

**Visual Grounding: −2.38.** The 29 insurance layout pages include life-insurance policy
illustrations (`CEJ Lincoln Max Income illustration`, `iul age 50 example`) — dense numeric
tables interleaved with footnote blocks, where element-boundary localisation is hard.

**Sample-size caution.** The Charts (40), Content Faithfulness (25), Semantic Formatting (24) and
Visual Grounding (29) insurance slices are small. Only the Tables slice (290 pages) supports a
confident claim. No confidence intervals were computed; treat the four small-*n* dimension gaps
as directional, not measured. The Tables and Overall figures are the defensible ones.

---

## 4. Parity against the published leaderboard — three of five dimensions reproduce, two do not

`parsebench/leaderboard.csv` publishes KDL-Frontier-Parser-nano's full-corpus scores. Our
full-corpus run compares as follows:

| Dimension | Ours (full corpus) | Published | Delta |
|---|---:|---:|---:|
| Tables | 85.76 | 85.56 | +0.20 |
| Charts | 63.69 | 63.41 | +0.28 |
| Content Faithfulness | 87.18 | 87.19 | −0.01 |
| Semantic Formatting | 52.42 | 66.81 | **−14.39** |
| Visual Grounding | 74.19 | 78.84 | **−4.65** |
| **Overall** | **72.65** | **76.36** | **−3.71** |

Tables, Charts and Content Faithfulness reproduce to within 0.3 points, which is strong evidence
that the harness, the dataset and this scoring script are all wired up correctly. **Semantic
Formatting and Visual Grounding do not reproduce**, and the overall gap (−3.71) is almost entirely
those two dimensions. That is a parity problem in the run configuration, not in this subset
analysis, and it is out of scope here — but it means:

- The **insurance-vs-other comparison in §1–§2 is sound**: both sides were scored by the same
  harness on the same run, so any harness-level discrepancy affects both equally.
- **Do not quote the absolute insurance figure (74.77) externally until Semantic Formatting and
  Visual Grounding reproduce.** Two of its five components are known to be low. Once parity is
  achieved, re-run the script — it reads the run's own evaluation reports, so no changes are
  needed.

One error surfaced during evaluation and is recorded here for completeness:
`ModuleNotFoundError: No module named 'anthropic'` from
`parsebench/src/parse_bench/evaluation/metrics/parse/llm_normalization/strategy_judge.py:21`, an
optional LLM-judge text normaliser. It did **not** affect Content Faithfulness, which reproduced
to 0.01 points, so it is unlikely to explain the Semantic Formatting gap — but it was not ruled
out as a contributor either.

---

## 5. Defensible claims from this data

Usable today, subject to §4:

- "**57.7 % of ParseBench's Tables dimension — 290 of 503 pages — is insurance documents:
  SERFF rate filings, auto rate-relativity grids, Solvency II reports, insurer financial
  statements.**" Verified, no caveat.
- "**Insurance rate-filing tables are measurably harder than the rest of ParseBench's tables:
  the #1 open-weight parser scores 84.18 on them versus 87.91 on the non-insurance
  remainder.**" Verified on 290 vs 213 pages, largest sample in the dataset.
- "We score the insurance subset separately and reproducibly, with a scripted subset definition
  and the benchmark's own aggregation code." Verified.

Not usable yet:

- Any absolute overall number, insurance or otherwise, until the Semantic Formatting and Visual
  Grounding parity gaps in §4 are closed.
- Any per-dimension insurance claim outside Tables, until the small-*n* slices (24–40 pages) are
  either accepted as directional or given confidence intervals.

---

## 6. Raw output

Machine-readable results for all three subsets: `/tmp/score_insurance.json`,
`/tmp/score_other.json`, `/tmp/score_all.json` (regenerate at any time with `--json`; these are
in `/tmp` and are not durable).
