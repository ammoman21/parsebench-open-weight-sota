# ParseBench: the insurance-document subset

**Purpose.** ParseBench's headline number averages over ~2,079 pages of mixed enterprise
documents — UN statistical yearbooks, semiconductor datasheets, sustainability reports,
academic preprints, insurance rate filings. For an insurance product the useful claim is not
"we score *X* on ParseBench" but "we score *X* on the insurance documents inside ParseBench".
This report enumerates that subset and its annotation rules; the companion script
`parsebench/scripts/insurance_subset_score.py` computes the subset's scores using the
benchmark's own aggregation code.

Written 2026-08-11. Everything below was verified by reading the dataset and the framework's
source, not inferred. Anything unverified is flagged explicitly in
[§7 What is not verified](#7-what-is-not-verified).

---

## Terms used here (defined once, on first use)

| Term | Meaning |
|---|---|
| **dimension** | One of ParseBench's five capability slices, each with its own ground-truth format and its own metric: Tables, Charts, Content Faithfulness, Semantic Formatting, Visual Grounding. Internally the framework names them `table`, `chart`, `text_content`, `text_formatting`, `layout`. |
| **rule** | One machine-checkable assertion about one page, e.g. "the value 0.8079 must appear labelled 'IF / 193 UN Member States'". Rules are the records in the dataset's five `*.jsonl` files (JSON Lines: one JSON object per line). |
| **page-document** | One PDF in `data/docs/<dimension>/`. Long source documents were split into one PDF per sampled page, so 2,079 page-documents come from ~1,211 source documents. |
| **SERFF** | System for Electronic Rate and Form Filing — the system US insurers use to file rates and policy forms with state insurance regulators. SERFF pages in this dataset are real filings. |
| **NAIC** | National Association of Insurance Commissioners, the body coordinating US state insurance regulation. |
| **NCCI** | National Council on Compensation Insurance, which publishes the workers' compensation rating manuals US insurers file against. |
| **SFCR** | Solvency and Financial Condition Report — the public regulatory report EU insurers publish under the Solvency II capital regime. |
| **IUL** | Indexed Universal Life, a life insurance product. An *illustration* is the projected-values document shown to a prospective buyer. |
| **nat-cat** | Natural catastrophe. "Insured loss" is the portion of a catastrophe's economic loss borne by insurers. |
| **GriTS / GTRM** | The grid-based table-similarity F-scores ParseBench uses for the Tables dimension (`grits_trm_composite`). |
| **HMO / PPO** | Health Maintenance Organization / Preferred Provider Organization — two US health-insurance plan structures with different provider networks. |

---

## 1. Headline composition

| | Insurance | Other | All | Insurance share |
|---|---:|---:|---:|---:|
| **Page-documents** | **384** | 1,695 | 2,079 | **18.5 %** |
| **Annotation rules** | **8,429** | 160,582 | 169,011 | **5.0 %** |

The two shares differ by more than 3x because the insurance material is concentrated in the
**Tables** dimension, which carries exactly one rule per page (a full expected-table
comparison), whereas the text dimensions carry hundreds of small rules per page.

### 1.1 Dimension x insurance-file-count x rule-count

| Dimension (framework name) | Insurance files | Other files | All files | Insurance rules | Other rules | All rules | Insurance share of rules |
|---|---:|---:|---:|---:|---:|---:|---:|
| Charts (`chart`) | 40 | 528 | 568 | 366 | 4,498 | 4,864 | 7.5 % |
| Visual Grounding (`layout`) | 29 | 471 | 500 | 738 | 15,587 | 16,325 | 4.5 % |
| Tables (`table`) | **290** | 213 | 503 | 290 | 213 | 503 | **57.7 %** |
| Content Faithfulness (`text_content`) | 25 | 481 | 506 | 6,690 | 134,632 | 141,322 | 4.7 % |
| Semantic Formatting (`text_formatting`) | 24 | 452 | 476 | 345 | 5,652 | 5,997 | 5.8 % |
| **Total (file x dimension pairs)** | **408** | 2,145 | 2,553 | **8,429** | 160,582 | 169,011 | **5.0 %** |

Reading notes:

- The `text` inference directory (508 PDFs) feeds **two** evaluation dimensions,
  `text_content` and `text_formatting`, from the same parser output. Confirmed at
  `parsebench/src/parse_bench/pipeline/cli.py:19` (`_SHARED_EVAL_GROUPS = {"text": ["text_content",
  "text_formatting"]}`). All 25 insurance text documents carry Content Faithfulness rules; 24 of
  them also carry Semantic Formatting rules (`text_misc__dash`, the USAble Mutual rate filing,
  has none). The same asymmetry holds corpus-wide: 506 of 508 text documents have Content
  Faithfulness rules, 476 have Semantic Formatting rules. That is why the file totals (408)
  exceed the unique page-document count (384).
- The all-rules totals reproduce the README's dataset table exactly (4,864 / 16,325 / 503 /
  141,322 / 5,997, summing to 169,011 — `parsebench/README.md:101-110`), which confirms the rule
  files were read completely and nothing was double-counted.
- **The Tables dimension is majority-insurance: 290 of 503 pages (57.7 %).** 193 of those are
  SERFF rate filings and a further 78 are two more insurance rate filings (see §3). This is the
  single most commercially useful fact in this report: a strong Tables score on ParseBench is
  substantially a claim about insurance rate-filing tables.

---

## 2. Matching criteria (and why)

The subset is defined as: **page-documents produced by, filed with, or substantively about the
insurance / reinsurance industry.** A document qualifies on *provenance* (the issuer is an
insurer, reinsurer, insurance regulator, insurance rating bureau, or insurance broker) or on
*subject* (the page's content is insurance rates, policy terms, insured losses, actuarial
analysis, or insurance regulation).

Filename matching alone is badly insufficient here, in **both** directions:

- **False negatives.** 78 of the table pages are insurance rate filings named only by their
  SERFF tracking number (`BRWS-134565917`, `FBLB-134215544`); 4 chart pages are an AXA results
  deck named `67c07d7f417ce`; the text dimension names every file by *layout characteristic*
  (`text_simple__marked`, `text_misc__dash`) with no issuer information at all.
- **False positives.** `AONR32314` is a MOSFET datasheet, not an Aon document.
  `text_simple__cardif` is a Cardiff University history paper, not insurer BNP Paribas Cardif.

So three independent passes were run, and every candidate was then read by hand:

1. **Filename patterns** — `insur`, `assur`, `reinsur`, `serff`, `sigma`, `catastroph`,
   `actuar`, `annuit`, `underwrit`, `solvency`, `sfcr`, `captive`, `medicare`, `medicaid`,
   `hmo`, `ppo`, `ltc`, plus insurer/broker/reinsurer names (aon, axa, allianz, zurich, chubb,
   aig, metlife, prudential, geico, progressive, travelers, hartford, munich, swiss, lloyd,
   beazley, hiscox, marsh, willis, gallagher).
2. **Ground-truth text scan** — all 169,011 rule records in the five `*.jsonl` files were
   parsed and their ground-truth strings concatenated per page-document (chart series labels,
   layout element text, table expected-markdown, text_content sentence bags, text_formatting
   target strings), then searched for insurance vocabulary in English, German, Italian,
   Spanish, Arabic and Hindi. 149 candidate documents surfaced.
3. **Extractable PDF text scan** — the full text layer of all 2,037 text-bearing PDFs among the
   2,079 (42 are `.jpg`/`.png` layout images, and 113 PDFs are scans with no text layer) was
   searched for high-precision markers: `insurance company`, `insurance premium/coverage/
   programme/department/commissioner/carrier/filing`, `reinsur*`, `policyholder*`, `SERFF`,
   `NAIC`, `loss ratio`, `solvency capital requirement`, `underwrit*`, `actuar*`, `annuit*`,
   `insured loss*`, `captive insur*`, `policy form`, `rate filing`, `property and/& casualty`.
   85 candidate documents surfaced, 5 of them not found by passes 1–2.
4. **Manual adjudication.** Every candidate from 1–3 was read (its ground truth, its PDF text,
   or both) and kept or rejected individually. Rejections are listed in §5.

The resulting subset is 384 page-documents. It is encoded in
`parsebench/scripts/insurance_subset_score.py` as `INSURANCE_FAMILIES`, one entry per source
document family with its expected page count and a one-line rationale. The script asserts those
page counts against the dataset at run time, so a future dataset revision that adds or drops
pages fails loudly rather than silently changing the denominator.

### 2.1 Relationship to the "197 files" figure

A plain filename grep for `insur|serff` over the HuggingFace repo file list returns exactly
**197 of 2,113** files — reproduced against the live API on 2026-08-11:

```
$ curl -s "https://huggingface.co/api/datasets/llamaindex/ParseBench?full=true" | ...
total files in repo: 2113
filename matches insur|serff: 197
docs/ files: 2079    {chart: 568, text: 508, table: 503, layout: 500}
```

The local checkout matches that file list document-for-document. Those 197 are 193 SERFF pages
plus `modeling-insured-catastrophe-loss...`, `2025-mid-year-property-casualty-and-title-insurance...`,
`airmic-explained-artex-captive-insurance-v2` and `aviva-plc-annual-report-and-accounts-2024`.
The 384-document subset here is that set plus 187 documents whose insurance identity is
established by content rather than by filename.

---

## 3. The subset, by document family

`n` = page-documents; `rules` = annotation rules attached to them across all dimensions.

### Tables (`table`) — 290 files, 290 rules

| Family | n | rules | What it is |
|---|---:|---:|---|
| `SERFF_CA_random_pages 1` | 104 | 104 | California insurance rate/form filings (SERFF) |
| `SERFF_TX_random_pages 1` | 74 | 74 | Texas insurance rate/form filings (SERFF) |
| `BRWS-134565917` | 34 | 34 | Auto insurance rate filing — bodily-injury / property-damage / personal-injury-protection / uninsured-motorist / comprehensive / collision rate relativities |
| `FBLB-134215544` | 30 | 30 | Farm Bureau Property & Casualty Insurance Company rate filing (company rate information, written premium, policyholders affected) |
| `SERFF_Interstate_random_pages 1` | 15 | 15 | Interstate Insurance Product Regulation Compact filings (SERFF) |
| `AZ LIC Rate Tables 2.0.v2` | 14 | 14 | Arizona insurance company rate tables (per-policy rates by limit and family count) |
| `LTCprodkitLincolnStateAvailabilty0216` | 2 | 2 | Lincoln MoneyGuard long-term-care insurance product state availability |
| `METLIFE-10Q-20240205 unrestricted` | 2 | 2 | MetLife quarterly report |
| `xl-re-europe-se-sfcr-2024` | 2 | 2 | XL Re Europe SE Solvency and Financial Condition Report |
| `1H-2025-Global-Catastrophe-Recap` | 1 | 1 | Insured catastrophe loss recap |
| `20230125-weather-climate-catastrophe-insight` | 1 | 1 | Insured catastrophe loss report |
| `BSC-Hospital-List-by-County (2)` | 1 | 1 | Blue Shield of California HMO/PPO hospital network list |
| `CINF.2006.page_93.pdf_140594` | 1 | 1 | Cincinnati Financial (insurer) annual-report table |
| `PrintableRulesSection` | 1 | 1 | Insurance rules manual pro-rata factor table (days in force x policy effective month) |
| `UNM.2007.page_51.pdf_45297` | 1 | 1 | Unum (insurer) annual-report table |
| `axa_urd2024_accessible_va` | 1 | 1 | AXA universal registration document — insurance-subsidiary credit ratings |
| `gallagherre-reinsurance-market-report-2024` | 1 | 1 | Reinsurance market report (return on equity, nat-cat losses) |
| `left-side sparse and no outline` | 1 | 1 | "North Carolina Homeowners Insurance Losses by Cause" — incurred losses, claims, pure premium |
| `metlife_sustainability_report_2024_non_gaap_...` | 1 | 1 | MetLife financial disclosures |
| `p29` | 1 | 1 | Arkansas rate exhibit, Allmerica Financial Benefit Insurance Company (private passenger auto) |
| `sample_page_16` | 1 | 1 | Arkansas rate exhibit, Allmerica Financial Benefit Insurance Company (annual mileage) |
| `tabular_2` | 1 | 1 | Brazilian health plan referenced-hospital network grid by plan tier |

### Charts (`chart`) — 40 files, 366 rules

| Family | n | rules | What it is |
|---|---:|---:|---|
| `sri-sigma-natural-catastrophes-1-2025` | 8 | 76 | Swiss Re Institute *sigma* nat-cat insured-loss report |
| `2023-05-sigma-01-english` | 7 | 69 | Swiss Re Institute *sigma* insurance-market report |
| `sigma-1-2021-en` | 5 | 47 | Swiss Re Institute *sigma* insurance-market report |
| `SRI-Insights-August 2025_media_embargo` | 5 | 47 | Swiss Re Institute *sigma* insights — insured catastrophe losses, 1H 2025 |
| `natural-catastrophe-and-climate-report-2023` | 5 | 36 | Reinsurance-broker nat-cat insured-loss report |
| `67c07d7f417ce` | 4 | 31 | AXA FY24 results — commercial lines, AXA XL Reinsurance, retail lines |
| `r_qt1212e` | 2 | 20 | BIS Quarterly Review chapter on the reinsurance market and catastrophe bonds |
| `aviva-plc-annual-report-and-accounts-2024` | 1 | 10 | Annual report of insurer Aviva plc |
| `modeling-insured-catastrophe-loss-a-global-perspective-for-2025` | 1 | 10 | Insured catastrophe loss modelling by peril |
| `natural-catastrophe-and-climate-report-q3-2025` | 1 | 10 | Reinsurance-broker nat-cat insured-loss report |
| `natural_catastrophe_and_climate_report_2024_h1` | 1 | 10 | Reinsurance-broker nat-cat insured-loss report |

### Visual Grounding (`layout`) — 29 files, 738 rules

| Family | n | rules | What it is |
|---|---:|---:|---|
| `pdf_d47bf4ce95f6` | 3 | 135 | AXA board biographies (insurer annual report) |
| `Lancashire-Annual-Report-and-Accounts-2024` | 3 | 101 | Annual report of specialty insurer/reinsurer Lancashire Holdings |
| `CEJ Lincoln Max Income illustration att1` | 3 | 75 | Lincoln indexed universal life policy illustration |
| `Integrated_Report_2025_e` | 1 | 60 | Tokio Marine Holdings integrated annual report |
| `pdf_29f6bce2b33c` | 1 | 55 | Lloyd's syndicate underwriting-performance analysis |
| `pdf_ccc50d8a450e` | 2 | 52 | Annual report of a specialty insurance/reinsurance underwriter |
| `airmic-explained-artex-captive-insurance-v2` | 1 | 48 | Captive insurance explainer (Airmic / Artex) |
| `2023-05-sigma-01-english` | 3 | 40 | Swiss Re Institute *sigma* |
| `progressive_2024corporate-sustainability-report` | 1 | 32 | Sustainability report of auto insurer Progressive |
| `iul age 50 example` | 2 | 26 | Indexed universal life policy illustration |
| `SRI-Insights-August 2025_media_embargo` | 1 | 21 | Swiss Re Institute *sigma* insights |
| `pdf_fe474dd12f60` | 1 | 18 | Indexed universal life policy illustration (Builder IUL7) |
| `2025-mid-year-property-casualty-and-title-insurance-industries-analysis-report` | 1 | 15 | P&C and title insurance industry analysis |
| `67c07d7f417ce` | 1 | 13 | AXA FY24 results |
| `sri-sigma-natural-catastrophes-1-2025` | 1 | 13 | Swiss Re Institute *sigma* nat-cat |
| `sigma-1-2021-en` | 1 | 11 | Swiss Re Institute *sigma* |
| `Intact-Financial-Corporation-2020-Annual-Report` | 1 | 11 | Annual report of P&C insurer Intact Financial |
| `p29` | 1 | 8 | Arkansas rate exhibit, Allmerica Financial Benefit Insurance Company |
| `sample_page_16` | 1 | 4 | Arkansas rate exhibit, Allmerica Financial Benefit Insurance Company |

### Content Faithfulness + Semantic Formatting (`text`) — 25 files, 7,035 rules

One PDF per document, no page splitting. `rules` combines both text dimensions.

| Family | rules | What it is |
|---|---:|---|
| `text_multicolumns__3colsep` | 530 | Insurer annual report (motor / health / travel insurance, policyholders) |
| `text_multilang__discrimination` | 512 | Geisinger Health Plan / Geisinger Indemnity Insurance Company non-discrimination notice |
| `text_multicolumns__3colceo` | 477 | Reinsurance group chairman's message (nat-cat losses, volatile markets) |
| `text_multilang__spanish` | 451 | Santander Seguros insurance product information sheet |
| `text_multilang__russian` | 438 | California Department of Insurance homeowners/renters consumer notice (Russian) |
| `text_multilang__arabic` | 383 | Islamic Arab Insurance Co (SALAMA) policy wording |
| `text_multicolumns__definitions` | 382 | Insurance glossary (fair value change account, funds for future appropriation, grievance ratio, in-force) |
| `text_simple__appendix` | 356 | Actuarial memorandum — persistency and morbidity assumptions, Combined Insurance Company of America |
| `text_multilang__german` | 329 | German household contents insurance (Hausratversicherung) leaflet |
| `text_ocr__simple` | 285 | Actuarial loss-development / loss-reserve analysis (tail factors, Bornhuetter-Ferguson) |
| `text_simple__edited` | 286 | National Union Fire Insurance Company of Pittsburgh psychiatrists professional liability manual rules |
| `text_simple__strikeUnderline` | 277 | Health plan eligibility and enrolment provisions (Medicaid / CHIP special enrolment) |
| `text_simple__marked` | 269 | North Carolina Department of Insurance SERFF rate-filing instructions |
| `text_simple__instruct` | 258 | Arizona general instructions for property & casualty form, rate and rule filings |
| `text_simple__hca` | 247 | Washington Apple Health public health-insurance programme rules |
| `text_simple__predictive` | 247 | Insurance predictive-model filing checklist (telematics, loss ratios, pure premium) |
| `text_multilang__hindi` | 234 | New Zealand Natural Hazards Insurance scheme consumer notice (Hindi) |
| `text_misc__templated` | 184 | Illinois Department of Insurance letter-of-submission template (SERFF references) |
| `text_simple__partial` | 179 | Health insurance rate-increase justification (minimum loss ratio requirement) |
| `text_misc__mark2` | 162 | Ohio auto "Road and Residence" rate and rule filing manual (rating algorithm steps) |
| `text_misc__docusigned` | 148 | Texas Department of Insurance Commissioner's Order, NCCI item B-1447 |
| `text_simple__revision` | 130 | NCCI workers compensation basic manual revision (alternate employer endorsement) |
| `text_misc__dash` | 105 | USAble Mutual Insurance Company 2021 off-exchange small-group rate filing |
| `text_misc__edit2` | 93 | American Bankers Insurance Company of Florida renters insurance programme manual |
| `text_simple__slide` | 73 | NAIC "restructuring of business obligations" principles slide |

---

## 4. Judgement calls (each one is arguable — listed so a reader can re-cut the subset)

**Included on issuer provenance even though the specific page is not itself insurance content.**
These are pages sampled from insurers' own reports where the sampled page happens to be a
remuneration chart, a carbon-emissions table, or a non-GAAP reconciliation. The document is an
insurance document; the page is a corporate-reporting page.
`chart/aviva-plc-annual-report-and-accounts-2024` (1), `layout/progressive_2024corporate-sustainability-report` (1),
`table/metlife_sustainability_report_2024_non_gaap_...` (1), `layout/pdf_d47bf4ce95f6` (3 — AXA
board biographies). **Total 6 files.** Dropping all six would remove 1 of 40 chart files, 4 of 29
layout files and 1 of 290 table files.

**Included as health-insurance / health-plan documents.** US and Brazilian health coverage sits
inside insurance for our purposes, but a reader focused on property & casualty may want it out.
`table/BSC-Hospital-List-by-County (2)` (1), `table/tabular_2` (1),
`text/text_multilang__discrimination` (1), `text/text_simple__hca` (1),
`text/text_simple__strikeUnderline` (1). **Total 5 files.** `text_simple__hca` (Washington Apple
Health) and `text_simple__strikeUnderline` (Medicaid/CHIP enrolment) are *public* programmes
rather than private carriers, which is the weakest link in the set.

**Included as insurance-market analysis by non-insurers.** `chart/r_qt1212e` is a Bank for
International Settlements Quarterly Review chapter on the reinsurance market and catastrophe
bonds (2 files). Content is squarely insurance; the publisher is a central-bank body.

**Excluded, though defensible to include.**

| Excluded | n | Why excluded |
|---|---:|---|
| `table/VRSK.2012...`, `table/VRSK.2018...` | 2 | Verisk Analytics — a data/analytics **vendor to** P&C insurers, not an insurer. Nearly all its revenue is insurance-derived, so including it is arguable. |
| `table/13_axa_world_funds` | 1 | An AXA-branded document, but it is a mutual-fund net-asset-value statement from AXA's asset-management arm — asset management, not insurance. |
| `layout/ar2025e_11` | 2 | A Japanese trading house whose divisions include an "Insurance Solutions Department"; the company is not an insurer. |

**Excluded as clear false positives** (each read individually): `table/AONR32314` (MOSFET
datasheet, matched "AON"); `table/MAP-CategoryI-LON` (mediator/arbitrator panel list whose
practice-area column reads "Insurance/Coverage, Insurance/Policyholder");
`text/text_simple__cardif` (Cardiff University history paper, matched insurer name "Cardif");
`text/text_multicolumns__10k2col` and `text/text_simple__att10k`, `text/text_simple__10k`
(company filings mentioning federal deposit insurance or employee life-insurance benefits);
`text/text_multicolumns__energy` (FERC *electricity* rate filings — "rate filing" collision);
`text/text_simple__program` (conference programme with a session titled "Prepare for
Catastrophe"); `text/text_simple__templated` (data-breach notification letter offering
identity-theft insurance reimbursement); `text/text_multilang__spanish2` (Chilean cemetery
concession regulation mentioning "compañías de seguros"); `layout/2025 Sustainability Report`
(matched "NAIC" inside "NAICS", the US industry classification code);
`layout/agcm` (AGCM Asia Growth Capital Management fund key-information document);
`layout/UC-INTEGRATO-...` (UniCredit), `layout/Informe-Anual-Consolidado-2024` (CaixaBank),
`layout/fh_2025_004e` (FUJIFILM), `layout/Monroe Capital ...` (private-credit *underwriting*),
`layout/i1040gi_1` (IRS Form 1040 instructions), `table/USPS 10-k` (actuarial pension
assumptions), `table/Coca Cola 10-k`, `table/Apple 10-k`, `table/corp-q1-2025` (a bank).

---

## 5. Reproducing the numbers

```bash
cd parsebench
# per-dimension and overall scores on the insurance subset
.venv/bin/python scripts/insurance_subset_score.py output/kdl_frontier_nano --subset insurance
# the same for everything else, for a fair comparison
.venv/bin/python scripts/insurance_subset_score.py output/kdl_frontier_nano --subset other
.venv/bin/python scripts/insurance_subset_score.py output/kdl_frontier_nano --subset all
# machine-readable
.venv/bin/python scripts/insurance_subset_score.py output/kdl_frontier_nano --json
```

The script does **not** re-implement ParseBench's scoring. It:

1. loads each dimension's `_evaluation_report.json` (written by `parse-bench evaluate run`) and
   validates it with the framework's own `EvaluationSummary` model;
2. filters `per_example_results` to the requested subset;
3. re-aggregates by **calling the framework's own method**,
   `EvaluationRunner._aggregate_metrics` at
   `parsebench/src/parse_bench/evaluation/runner.py:1125` — so failure zero-padding,
   micro-pooling and `_predicted` variants behave exactly as in a normal run. The reported
   number is that method's macro average,
   `aggregate[f"avg_{metric_name}"] = sum(values) / len(values)`
   (`parsebench/src/parse_bench/evaluation/runner.py:1254`);
4. selects each dimension's headline metric from the framework's own default-metric table,
   `_DEFAULT_METRICS` at
   `parsebench/src/parse_bench/analysis/aggregation_report.py:36-42`
   (`table` → `grits_trm_composite`, `layout` → `layout_element_rule_pass_rate`,
   `text_content` → `content_faithfulness`, `text_formatting` → `semantic_formatting`, and
   `chart` → `rule_pass_rate` via the fallback at lines 69-75);
5. reports the overall score as the **unweighted mean of the five dimension scores**, per the
   leaderboard's own label "Overall / Average across categories" at
   `parsebench/src/parse_bench/analysis/leaderboard_report.py:780-781`. Verified arithmetically
   against `parsebench/leaderboard.csv`: KDL-Frontier-Parser-nano is published as Tables 85.56,
   Charts 63.41, Content_Faithfulness 87.19, Semantic_Formatting 66.81, Visual_Grounding 78.84,
   Overall 76.36, and (85.56 + 63.41 + 87.19 + 66.81 + 78.84) / 5 = 76.362.

Two correctness guards worth knowing about:

- **Stale `_metadata.json`.** `output/kdl_frontier_nano/_metadata.json` still records
  `test_cases_dir = data/test`, the 12-document smoke split, from an earlier run. Naively
  trusting it makes every rule count wrong. The script therefore tries each candidate dataset
  directory and keeps the first whose declared page counts verify.
- **Zero-padding of missing pages.** ParseBench deliberately scores a test case with no
  inference output as a hard **0**, to stop a parser that fails on hard documents from having
  them dropped from its denominator (`parsebench/src/parse_bench/evaluation/runner.py:786`,
  "Score test cases with no inference result as blank output (0.0)"). That is right for a
  finished run and *wrong* for a run still in progress. The script counts scored examples with
  no `.result.json` on disk and prints an explicit warning when any exist.

---

## 6. Measured scores

Full results in [`insurance_subset_scores.md`](insurance_subset_scores.md), written separately so
this characterisation stays stable as runs are re-scored. Summary for the complete
`kdl_frontier_nano` full-corpus run of 2026-08-11:

| Dimension | Insurance | Non-insurance | Full corpus |
|---|---:|---:|---:|
| Tables | 84.18 (n=290) | 87.91 (n=213) | 85.76 |
| Charts | 70.69 (n=40) | 63.16 (n=528) | 63.69 |
| Content Faithfulness | 89.63 (n=25) | 87.05 (n=481) | 87.18 |
| Semantic Formatting | 57.39 (n=24) | 52.14 (n=452) | 52.42 |
| Visual Grounding | 71.97 (n=29) | 74.34 (n=471) | 74.19 |
| **Overall** | **74.77** | 72.92 | 72.65 |

Two dimensions do not yet reproduce the published leaderboard — see item 1 of §7.

---

## 7. What is not verified

1. **Absolute comparability to the published leaderboard.** Our full-corpus run reproduces the
   published KDL-Frontier-Parser-nano scores to within 0.3 points on Tables, Charts and Content
   Faithfulness, but is 14.4 points low on Semantic Formatting and 4.7 low on Visual Grounding
   (full table in `insurance_subset_scores.md` §4). That is a run-configuration parity problem,
   not a subset problem — the insurance-vs-other comparison is unaffected because both sides are
   scored by the same harness on the same run — but **no absolute overall number should be quoted
   externally until those two dimensions reproduce.** Separately, evaluation logged
   `ModuleNotFoundError: No module named 'anthropic'` from an optional LLM-judge text normaliser
   (`parsebench/src/parse_bench/evaluation/metrics/parse/llm_normalization/strategy_judge.py:21`);
   it did not affect Content Faithfulness, which reproduced to 0.01 points, but it was not ruled
   out as a contributor to the Semantic Formatting gap.
2. **Recall of the subset.** A page could be an insurance document while containing none of the
   ~40 insurance markers in either its text layer or its ground truth — for example a bare
   rate grid with no prose. 42 layout files are images (`.jpg`/`.png`) with no text layer, and
   113 PDFs are scans with no text layer; for those, only the ground-truth annotations were
   searchable. The subset should be treated as a high-precision lower bound.
3. **Issuer identification for opaque filenames.** `pdf_ccc50d8a450e` was read as "a specialty
   insurance and reinsurance underwriter" and `pdf_29f6bce2b33c` as a Lloyd's syndicate
   analysis, from page content; the specific companies were not identified. This does not affect
   membership, only the descriptive label.
4. **Source-document counts.** All counts here are page-documents (one PDF each). The number of
   distinct *source* documents behind the insurance subset was not computed; the family table in
   §3 is the closest proxy (77 families).
5. **Page-count drift.** The declared per-family page counts were verified against this
   checkout of the dataset only. The script re-asserts them on every run, so a dataset revision
   will surface as a loud failure rather than a silent change.
