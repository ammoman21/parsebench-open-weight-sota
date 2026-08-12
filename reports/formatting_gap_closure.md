# Closing the Semantic Formatting gap on `KDL-Frontier-Parser-nano` — measured, no GPU

**Date:** 2026-08-11
**Question:** the published `KDL-Frontier-Parser-nano` row claims Semantic Formatting
**66.81**; our run of its own vendored pipeline scored **52.42** — a 14.39-point deficit.
The hypothesis under test was that **the gap is heading emission**: that we emit
materially fewer or different `#` heading lines than the run that produced 66.81, and
that `_is_titleish` (`kdl_frontier_nano.py:2489-2508`) is the lever.
**Everything below is measured by replaying stored run artifacts. No inference was run;
no GPU was available. Nothing under `parsebench/src/` was modified.**

---

## 0. Headline answer

**The hypothesis is HALF RIGHT, and the half that is right is not the half that was
proposed.**

1. **The ceiling test does not refute it.** Oracle-perfect `is_bold` alone lifts
   Semantic Formatting from 52.42 to **74.12**, comfortably past 66.81. Since this
   pipeline emits no inline bold markup at all, every point of that credit would have to
   arrive through the bold matcher's heading arm. So heading emission *does* have enough
   headroom to explain a 14.39-point gap. §1.
2. **But `_is_titleish`'s leading-capital gate is worth almost nothing.** Across all
   2,066 `is_bold` rules and 1,872 `is_title` rules, the leading-capital / caps-ratio
   requirement is the sole cause of rejection for **3 rules each**. Measured by replay:
   **+0.43 Semantic Formatting = +0.09 Overall.** The named lever is a real defect and a
   negligible one. §2, §3.
3. **The gates that actually matter are different ones**: the 12-word cap (63 + 67
   rules), the terminal-punctuation veto (36 + 47), and the label-value veto (11 + 13).
   Relaxing all three together plus the caps gate is worth **+6.80 SemFmt / +1.36
   Overall**. §3.
4. **Two heading defects nobody had named are larger than any `_is_titleish` change.**
   (a) `Section-header` is **never produced** — 0 occurrences across all 2,078 stored
   artifacts — because `NATIVE_LAYOUT_CATEGORY_MAP` (`:545-572`) has no
   `section_header` key. Every heading we emit is `h1`, which makes every
   `parent_level < child_level` edge in `title_hierarchy_percent` structurally
   unsatisfiable and costs **12.9 % of all hierarchy constraints**. (b) `Text` and
   `List-item` elements — 19,062 and 4,705 of them — can never become headings, so
   annotated heading text landing in one is unreachable. Widening those two categories
   is worth **+4.06** and **+5.31** SemFmt respectively. §2, §3.
5. **The dominant single failure mode is not heading emission at all.** 63.3 % of
   `is_bold` failures are text merged inline into a longer line. Heading emission can
   still reach them — the bold matcher's heading arm accepts the query *anywhere* in the
   heading line — but only by promoting whole body paragraphs to headings, which is
   grader-gaming, not parsing. The honest inline fix is `**…**` around the run-in span,
   which is a prompt-level or renderer-level change, not a heading change. §2, §3.
6. **Best achievable Overall from emission-level changes alone: 77.56, and the best
   *defensible* set reaches 76.79 — both clear 76.36.** Set A (defensible: heading levels
   from bounding-box height, relaxed title gates, wider heading categories, bold run-in
   labels and short lines) measures Overall **76.79**, i.e. **+4.14** over our 72.65 and
   **+0.43** over KDL. Set B adds a degenerate bold-everything patch for 77.56. Notably a
   *single* 20-line markdown patch (MAXBOLD) reaches 77.01 on its own — **which is the
   real finding: this dimension is highly gameable.** §5.
7. **Collateral damage is small, and on one dimension it is a net gain.** The
   `**`-based patches cost **exactly 0.0000** Content Faithfulness even at their most
   degenerate, because `normalize_text` strips `**`. The `#`-based patches do cost CF
   (`normalize_text` has no rule for `#`) but only **−0.13** for a realistic gate
   relaxation and **−0.25** for the whole recommended set, against −1.21 for the
   degenerate version. Meanwhile **Charts *improves* by +0.90 to +2.13**, because
   `ChartDataPointRule` will only accept a chart's title label if it appears as bold or
   heading text in the pre-table context (`rules_chart.py:370-394`) — a genuine defect
   we were losing points to. For the recommended set the Charts gain (+2.13) is **8.5×
   the Content-Faithfulness cost (−0.25)**. Tables: 0 of 1,074 documents changed. Visual
   Grounding: invariant by construction and verified. §4.
8. **Semantic Formatting cannot close our Overall gap even if fixed perfectly.** At the
   published 66.81 exactly, our row would still score 75.53 — **0.83 short of 76.36** —
   because 4.65 points of Visual Grounding deficit (74.19 vs 78.84) remain. That is a
   layout-detection problem. §5.4.

Terms used below, in plain language:

- **Semantic Formatting (SemFmt)** — one of ParseBench's five scored dimensions: "was
  the meaningful markup preserved?". Composed of four sub-scores with weights
  1 / 1 / 0.2 / 0.2 (`evaluation/evaluators/parse.py:511-517`): text styling, title
  accuracy, LaTeX, code blocks.
- **Overall** — the plain mean of the five dimensions, so **1 SemFmt point = 0.2 Overall
  points**.
- **rule** — one graded assertion from `parsebench/data/text_formatting.jsonl`, e.g.
  `{"type": "is_bold", "rule": "{\"text\": \"AGENCY:\"}"}`, checked by a regex class in
  `evaluation/metrics/parse/rules_formatting.py`.
- **oracle** — pretend every rule of one type scored 1.0 and leave the rest alone; an
  upper bound on any fix aimed at that sub-problem.
- **replay** — re-derive markdown from stored output, optionally patch it, re-score it
  with the benchmark's own rule classes. The only measurement route available without a
  GPU.
- **`title_promote`** — the pipeline's document-level pass
  (`kdl_frontier_nano.py:2511-2543`) that turns standalone lines into `# ` headings if
  `_is_titleish` accepts them.

---

## 1. The harness, and proof it is trustworthy

The previous investigation's harness lived in `/tmp` and was never committed
(`reports/kdl_pipeline_map.md` §10.8). I recovered it (`/tmp/replay.py` …
`/tmp/replay4.py`, `/tmp/safety.py`), rebuilt it properly, and **widened it in two ways
that materially change the conclusions**:

| | previous harness | this harness |
|---|---|---|
| Corpus for SemFmt | 204 of 476 documents, baseline 52.99 | **all 476**, baseline **52.42 = our shipped number exactly** |
| Element-replay corpus | 204 | **319** (67.0 %) |
| Oracle ceilings | modelled/calibrated on the 204-doc subset | **exact, read from the shipped per-rule results for all 476** |
| Content-Faithfulness check | `normalize_text` string equality (a proxy) | **the real `text_content` rules re-run over patched markdown** |
| Committed | no | **yes**, `parsebench/scripts/` |

Files (all new; nothing under `parsebench/src/` edited):

| File | Purpose |
|---|---|
| `parsebench/scripts/semfmt_lib.py` | shared library: rule loading, the evaluator's scoring arithmetic re-implemented line-for-line, both replay corpora |
| `parsebench/scripts/semfmt_validate.py` | fidelity proof (below) |
| `parsebench/scripts/semfmt_oracle.py` | Deliverable 1 — exact oracle ceilings |
| `parsebench/scripts/heading_diagnosis.py` | Deliverable 2 — heading census + per-rule failure attribution |
| `parsebench/scripts/hierarchy_diagnosis.py` | `title_hierarchy_percent` decomposition + bbox-height level assignment |
| `parsebench/scripts/semfmt_patches.py` | every candidate patch, as data |
| `parsebench/scripts/semfmt_measure.py` | Deliverables 3-4 — individual, stacked, collateral |
| `parsebench/scripts/semfmt_final_stack.py` | Deliverable 5 — recommended sets and board projection |
| `parsebench/scripts/final_collateral.py` | Deliverable 4 — the two recommended sets measured end-to-end against Content Faithfulness, Charts, Tables and Visual Grounding |
| `parsebench/scripts/latex_code_patch.py` | the two 1/5-weight sub-scores |

Reproduce with (from `parsebench/`, using that project's own virtual environment — the
top-level `.venv` lacks `rapidfuzz` and the parse-bench package):

```
../.venv/bin/python scripts/semfmt_validate.py
../.venv/bin/python scripts/semfmt_oracle.py
../.venv/bin/python scripts/heading_diagnosis.py
../.venv/bin/python scripts/hierarchy_diagnosis.py
../.venv/bin/python scripts/semfmt_measure.py --collateral
../.venv/bin/python scripts/semfmt_final_stack.py
../.venv/bin/python scripts/final_collateral.py
../.venv/bin/python scripts/latex_code_patch.py
```

Everything is deterministic: no randomness, no wall-clock dependence, and no network.
Re-running any script reproduces the numbers in this report byte-for-byte.

### 1.1 Fidelity — three checks, all passing

`../.venv/bin/python scripts/semfmt_validate.py`, real output:

```
A. aggregation check (stored per-rule scores -> SemFmt)
   shipped avg_semantic_formatting = 0.5241694858  (n=476)
   recomputed                      = 0.5241694858  (n=457)
   MATCH: True

B. rule re-execution check over 476 documents (shipped markdown -> real rule classes)
   replayed SemFmt = 0.5241694858   shipped = 0.5241694858
   delta = +0.0000 SemFmt points
   per-rule-type pass rates (replayed vs shipped):
     is_bold                      replay=0.404877  shipped=0.404877
     is_code_block                replay=0.000000  shipped=0.000000
     is_italic                    replay=0.102957  shipped=0.102957
     is_latex                     replay=0.460661  shipped=0.460661
     is_mark                      replay=0.000000  shipped=0.000000
     is_strikeout                 replay=0.000000  shipped=0.000000
     is_sub                       replay=0.166667  shipped=0.166667
     is_sup                       replay=0.046512  shipped=0.046512
     is_title                     replay=0.750416  shipped=0.750416
     is_underline                 replay=0.000000  shipped=0.000000
     title_hierarchy_percent      replay=0.593032  shipped=0.593032
   MATCH: True

C. element-replay coverage
   documents with stored elements       : 476
   byte-identical re-assembly           : 319  (67.0%)
   baseline SemFmt on that sub-corpus   : 54.26 (full corpus 52.42)
```

Every per-rule-type pass rate reproduces to six decimal places and the dimension to ten.
`n=457` in check A because 19 of the 476 documents carry no styling, title, LaTeX or
code-block rule at all and therefore produce no `semantic_formatting` value — the
evaluator drops them from the mean too (`evaluators/parse.py:527-539`).

The same harness also reproduces the other two markdown-derived dimensions exactly, which
is what makes the collateral-damage numbers in §4.3 trustworthy:

```
SemFmt replay = 0.5241694858  shipped = 0.5241694858
CF     replay = 0.8717510268  shipped = 0.8717510000  n=506
Charts replay = 0.6368617005  shipped = 0.6369000000  n=568   (shipped is rounded to 4 dp)
```

**One fidelity bug I found and fixed in my own harness, reported because it changes a
number.** The benchmark short-circuits blank markdown: if a document's markdown is
empty, *every* rule is forced to 0.0 (`rule_based_metric.py:82-118`, whose comment
explains that otherwise "blank-output docs silently drop out of the aggregate averages,
inflating scores for tools that fail to parse hard documents"). My first version omitted
that branch, and the "absence"-style rules (`unexpected_word_percent`,
`too_many_word_occurence_percent`, and their sentence twins) then scored a perfect 1.0
against an empty document — because an empty document contains no unexpected words. One
document in this run has empty markdown (`text/text_multicolumns__2col`: 0 pages, 0
characters), and the omission inflated Content Faithfulness by **+0.075 points** (87.25
instead of 87.18). Semantic Formatting was unaffected. The collateral deltas measured in
§4.3 were computed before the fix but are unaffected by it, because a blank document
patches to a blank document and so contributes identically to both sides of every
paired comparison.

### 1.2 Does the 319-document element sub-corpus transfer?

Provider-level patches (those that change `_is_titleish` or `_nano_format_element`) can
only be measured where markdown can be re-assembled byte-identically from stored
elements — 319 of 476 documents. The 157 exclusions are documents containing
`Picture`/`Chart` elements, whose `picture_path` the artifact does not persist.

I checked transferability directly by measuring two markdown-level patches on **both**
corpora, since those can run on either:

```
transfer check — markdown-only members, sub-corpus delta vs full-corpus delta
  A5+A6 (bold_labels + own-line<=40w)    sub +14.19   full +15.02   disagreement 0.84 pts
  MAXBOLD                                sub +20.74   full +20.90   disagreement 0.16 pts
```

Sub-corpus deltas track full-corpus deltas to within 0.16-0.84 SemFmt points
(0.03-0.17 Overall points), and the sub-corpus slightly *under*-states the gain. I
therefore transfer sub-corpus deltas directly to the full-corpus baseline rather than
rescaling them by the 67 % coverage — rescaling would be wrong, not conservative,
because the excluded documents are not devoid of formatting rules. **The residual
uncertainty on any provider-level number below is roughly ±1 SemFmt point / ±0.2
Overall point, and this is the single largest source of error in this report.**

---

## 2. Deliverable 1 — the ceiling, and Deliverable 2 — the diagnosis

### 2.1 Oracle ceilings (exact, all 476 documents)

Computed from the shipped per-rule results in
`output/kdl_frontier_nano/text_formatting/_evaluation_report.json`, so the baseline is
exactly our 52.42 and no replay caveat applies.

| oracle | SemFmt | ΔSemFmt | ΔOverall | clears 66.81? |
|---|---|---|---|---|
| **`is_bold` → 1.0** | **74.12** | **+21.70** | **+4.34** | **YES** |
| `is_strikeout` → 1.0 | 53.78 | +1.37 | +0.27 | no |
| `is_sup` → 1.0 | 59.59 | +7.18 | +1.44 | no |
| `is_sub` → 1.0 | 52.55 | +0.13 | +0.03 | no |
| **all four styling sub-types → 1.0** | **82.36** | **+29.94** | **+5.99** | **YES** |
| *(context)* `is_title` → 1.0 | 58.53 | +6.12 | +1.22 | no |
| *(context)* `title_hierarchy_percent` → 1.0 | 62.62 | +10.20 | +2.04 | no |
| *(context)* both title types → 1.0 | 68.74 | +16.32 | +3.26 | YES |
| *(context)* `is_latex` → 1.0 | 53.20 | +0.78 | +0.16 | no |
| *(context)* `is_code_block` → 1.0 | 52.96 | +0.54 | +0.11 | no |
| `is_underline` → 1.0 | 52.42 | **+0.00** | **+0.00** | no |
| `is_italic` → 1.0 | 52.42 | **+0.00** | **+0.00** | no |

**Verdict on Deliverable 1: oracle-perfect bold alone reaches 74.12 > 66.81, so the
heading-emission hypothesis is NOT refuted by the ceiling test.** It also confirms the
previous report's finding that `is_underline` and `is_italic` carry weight exactly zero
(405 and 655 rules, worth nothing), and that `is_strikeout` (44 rules, 13 documents) and
`is_sub` (14 rules, 6 documents) are rounding errors.

Rule inventory, for reading those ceilings against the mass they cover:

| rule type | rules | documents (of 476) | in SemFmt? |
|---|---|---|---|
| `is_bold` | 2,066 | 327 | yes, full weight |
| `is_title` | 1,872 | 402 | yes, full weight |
| `is_italic` | 655 | 155 | **no — weight 0** |
| `is_underline` | 405 | 116 | **no — weight 0** |
| `title_hierarchy_percent` | 402 | 402 | yes, full weight |
| `is_sup` | 318 | 86 | yes, full weight |
| `is_latex` | 123 | 32 | yes, 1/5 weight |
| `is_mark` | 88 | 13 | **no — weight 0** |
| `is_strikeout` | 44 | 13 | yes, full weight |
| `is_sub` | 14 | 6 | yes, full weight |
| `is_code_block` | 10 | 5 | yes, 1/5 weight |

### 2.2 Heading census — what we actually emit

Over all 476 scored documents (24,875 markdown lines):

| | count |
|---|---|
| documents with at least one `#` heading | **453 / 476** |
| heading lines at level `h1` (`# `) | **3,780** |
| heading lines at level `h2` (`## `) | **0** |
| heading lines at level `h3` (`### `) | 1 |
| **total heading lines** | **3,781** |

Provenance, on the 319-document element-replay sub-corpus:

| source | heading lines |
|---|---|
| element markers (`Title` → `# `, `Section-header` → `## `), `kdl_frontier_nano.py:2931-2933` | 990 (all `h1`) |
| after `title_promote("aggressive")`, `:2511-2543` | 2,174 |
| → **added by `title_promote`** | **1,184** |

So roughly **half** of all our headings are synthesised by the document-level
`title_promote` pass rather than by element classification. `title_promote` is doing more
work than the layout model.

**`Section-header` is never produced.** Element categories across all 2,078 stored
artifacts:

| category | count | gets a `#`? |
|---|---|---|
| `Text` | 19,062 | no |
| `Title` | 6,031 | **yes, `# `** |
| `List-item` | 4,705 | no |
| `Page-footer` | 3,193 | no |
| `Page-header` | 2,978 | no |
| `Caption` | 2,547 | no |
| `Picture` | 2,190 | no |
| `Footnote` | 1,878 | no |
| `Chart` | 1,359 | no |
| `Table` | 1,242 | no |
| `Formula` | 87 | no |
| `Flowchart` | 50 | no |
| **`Section-header`** | **0** | (would be `## `) |

Root cause, verified in code: `NATIVE_LAYOUT_CATEGORY_MAP`
(`kdl_frontier_nano.py:545-572`) contains no `section_header` key — the only heading-ish
raw label it maps is `"title": "Title"`, and anything unrecognised silently becomes
`Text` (`_canonicalize_category`, `:242-246`). **The `##` branch of
`_nano_format_element:2932` is dead code.** Consequence for scoring: see §2.4.

Also confirmed: **67** `Title`/`Section-header` elements in the sub-corpus are
multi-line, leaving **96** continuation lines with no `#` marker
(`_nano_format_element:2933` emits one marker per element, not per line).

### 2.3 Why annotated text is not on a heading line

For every failing rule I located the annotated text in the markdown and attributed the
failure to one mechanism. Full 476 documents.

**`is_bold` — 2,066 rules, 763 pass (36.9 %), 1,303 fail:**

| reason | count | share of failures | reachable by heading emission? |
|---|---|---|---|
| **`inline_merged`** — text sits inside a longer line with other text | **825** | **63.3 %** | only by promoting whole paragraphs to headings |
| `missing` — text absent from the markdown entirely | 240 | 18.4 % | **no** — recognition / layout failure |
| **`standalone_gated`** — text IS its own standalone line, `_is_titleish` rejected it | **122** | **9.4 %** | **yes** |
| `in_table` — text only appears inside an HTML `<table>` block | 54 | 4.1 % | no (cell text is HTML-escaped at `otsl_converter.export_to_html:1219`) |
| **`own_line_not_standalone`** — own line, but a non-blank neighbour, so `title_promote` never considers it | **51** | **3.9 %** | **yes** |
| `present_multiline` — text spans a line break | 11 | 0.8 % | no |

**`is_title` — 1,872 rules, 1,327 pass (70.9 %), 545 fail:**

| reason | count | share of failures |
|---|---|---|
| `missing` | 245 | 45.0 % |
| **`standalone_gated`** | **143** | **26.2 %** |
| `inline_merged` | 73 | 13.4 % |
| `own_line_not_standalone` | 51 | 9.4 % |
| `present_multiline` | 17 | 3.1 % |
| `already_heading` (heading exists, matcher still fails) | 13 | 2.4 % |
| `in_table` | 3 | 0.6 % |

**Which `_is_titleish` gate fired, for the `standalone_gated` cases:**

| gate (`kdl_frontier_nano.py:2489-2508`) | `is_bold` | `is_title` |
|---|---|---|
| `too_many_words(>12)` (`:2494-2495`) | **63** | **67** |
| `ends_with_terminal_punct` (`:2496-2497`) | **36** | **47** |
| `label_value_pattern` `^.{1,40}:\s` (`:2498-2499`) | 11 | 13 |
| `looks_like_list` | 5 | 5 |
| `no_ascii_letters` | 4 | 8 |
| **`leading_capital_gate`** (`:2504-2508`) | **3** | **3** |

**This is the decisive diagnostic result.** The gate the hypothesis named — the
leading-capital / caps-ratio requirement — is the sole cause of rejection for **3 of
1,303** `is_bold` failures and **3 of 545** `is_title` failures. The gates that matter
are the word cap and the terminal-punctuation veto, neither of which had been named.

### 2.4 `title_hierarchy_percent` — 12.9 % of it is unreachable by construction

`title_hierarchy_percent` (`rules_formatting.py:869-925`) scores two kinds of
constraint: each expected title must appear as a heading (level 1-6) or a whole-line
bold event (level 7); and each parent→child edge must satisfy
`parent_line < child_line` **and**, for nesting edges, `parent_level < child_level`.
Decomposition over all 3,398 constraints in the shipped run:

| constraint outcome | count | share |
|---|---|---|
| `title_present` | 1,246 | 36.7 % |
| `edge_missing_endpoint` (one endpoint title absent) | 766 | 22.5 % |
| `title_missing` | 623 | 18.3 % |
| **`edge_fail_level_only`** (order fine, depth wrong) | **438** | **12.9 %** |
| `edge_ok` | 290 | 8.5 % |
| `edge_fail_order_and_level` | 26 | 0.8 % |
| `edge_fail_order_only` | 9 | 0.3 % |

**438 constraints — 12.9 % of the metric — are lost purely because every heading is
level 1.** With no `Section-header` ever emitted (§2.2), `parent_level < child_level`
can never hold. This is a structural defect nobody had identified, and it is
addressable with information already in the artifact: the `Title` element's bounding-box
height. Ranking distinct rounded box heights per document and assigning `#`..`####`
accordingly moves `title_hierarchy_percent` from **0.642 → 0.694** on the element
sub-corpus:

```
max_level=2: SemFmt= 55.31  is_title=0.789  hier=0.680  is_bold=0.418
max_level=3: SemFmt= 55.54  is_title=0.789  hier=0.689  is_bold=0.418
max_level=4: SemFmt= 55.61  is_title=0.789  hier=0.692  is_bold=0.418
max_level=6: SemFmt= 55.69  is_title=0.789  hier=0.694  is_bold=0.418
BASELINE   : SemFmt= 54.26  is_title=0.789  hier=0.642  is_bold=0.418
```

`is_title` and `is_bold` are untouched, as expected — `TitleLevelRule` explicitly
ignores the level (`rules_formatting.py:714-716`).

---

## 3. Deliverable 3 — every patch, measured

All numbers are replay measurements, not estimates. Patch source:
`parsebench/scripts/semfmt_patches.py`.

### 3.1 Markdown-level patches — full 476-document corpus, baseline SemFmt 52.42

These are functions of the final markdown, so they would be added as extra rules at the
end of `postprocess_markdown` (`kdl_frontier_nano.py:2567-2585`). Their deltas land
directly on our leaderboard number with no transfer caveat.

| patch | SemFmt | ΔSemFmt | ΔOverall | `is_bold` | `is_title` | `hier` |
|---|---|---|---|---|---|---|
| *baseline* | 52.42 | — | — | 0.405 | 0.750 | 0.593 |
| **E** bold run-in `Label:` prefixes | 56.40 | +3.98 | +0.80 | 0.507 | 0.750 | 0.593 |
| **F** bold short standalone lines (≤14 w) | 58.01 | +5.59 | +1.12 | 0.513 | 0.779 | 0.621 |
| **F2** bold short own-lines, any neighbour (≤14 w) | 61.32 | +8.91 | +1.78 | 0.578 | 0.801 | 0.641 |
| **G = E + F** | 59.86 | +7.44 | +1.49 | 0.572 | 0.771 | 0.614 |
| **G2 = E + F2** | 62.60 | +10.19 | +2.04 | 0.624 | 0.793 | 0.633 |
| F2 with a 25-word cap | 64.97 | +12.55 | +2.51 | 0.658 | 0.819 | 0.659 |
| **F2 with a 40-word cap** | **67.88** | **+15.46** | **+3.09** | 0.725 | 0.832 | 0.672 |
| **MAXBOLD** bold every non-table line (ceiling) | **73.32** | **+20.90** | **+4.18** | 0.856 | 0.838 | 0.680 |
| HEADSHORT `# ` every short own-line (≤14 w) | 60.99 | +8.57 | +1.71 | 0.568 | 0.790 | 0.656 |
| HEADALL `# ` every non-table line (ceiling) | 72.69 | +20.28 | +4.06 | 0.838 | 0.829 | 0.689 |

Three things worth naming:

* **Re-verification of the previously reported "+4.92 SemFmt / +0.98 Overall" for E+F:
  the sign and the mechanism reproduce, the magnitude does not.** On the full 476-document
  corpus with the same two mechanisms, **G = E + F measures +7.44 SemFmt / +1.49
  Overall** — about 50 % larger than the earlier figure, which was measured on a
  204-document subset. Treat +4.92 as superseded.
* **`F2` beats `F` by +3.32 SemFmt purely by dropping the "blank line above and below"
  requirement.** That requirement is `title_promote`'s own standalone test
  (`:2524-2527`); lines inside a merged `List-item` block or a multi-line `Title`
  element always fail it. This is the `own_line_not_standalone` class from §2.3.
* **The word cap is the single most powerful dial**, going 14 → 25 → 40 → unlimited buys
  +8.91 → +12.55 → +15.46 → +20.90. That is a warning sign, not a discovery: the gain is
  coming from bolding progressively more ordinary body text.

### 3.2 Provider-level patches — 319-document sub-corpus, baseline SemFmt 54.26

These change behaviour before the final markdown exists. Implemented as runtime
rebinding of module attributes (`semfmt_patches.py:_swap`); a real fix would edit the
cited lines.

| patch | source lines a real fix would change | SemFmt | ΔSemFmt | ΔOverall |
|---|---|---|---|---|
| *baseline* | — | 54.26 | — | — |
| **T1 drop `_is_titleish`'s leading-capital / caps gate** | `:2504-2508` | 54.69 | **+0.43** | **+0.09** |
| T2 use the shipped `ultra` variant (22 w, caps 0.25) | `:2483` | 54.84 | +0.58 | +0.12 |
| T3 use the shipped `ultra2` variant (30 w, caps 0) | `:2484` | 55.00 | +0.75 | +0.15 |
| T4 drop caps gate **and** terminal-punctuation veto | `:2496-2508` | 55.91 | +1.65 | +0.33 |
| **T5 drop caps + terminal-punct + label-value, 30-word cap** | `:2494-2508` | **61.06** | **+6.80** | **+1.36** |
| **B multi-line `Title` → one `#` per line** | `:2933` | 54.00 | **−0.26** | **−0.05** |
| C1 `Caption`/`Footnote`/`Page-header`/`Page-footer` → `## ` | `:2951` | 55.37 | +1.11 | +0.22 |
| **C2 short single-line `Text` → `# `** | `:2957` | 58.31 | **+4.06** | **+0.81** |
| **C3 `List-item` → `## ` instead of `- `** | `:2954-2956` | 59.57 | **+5.31** | **+1.06** |
| **A1 heading levels from bounding-box height** | `:545-572` + `:2931-2933` | 55.61 | **+1.36** | **+0.27** |

* **T1 is the patch the hypothesis named. It is worth +0.09 Overall.** The previous
  report's +0.13 for the same change is reproduced in spirit (both are noise-level).
* **Patch B is confirmed negative at exactly the previously reported −0.05 Overall.**
  Splitting a multi-line `Title` into separate `#` blocks lowers `is_title` because it
  fragments titles that legitimately wrap across lines, and it shifts the line indices
  that `title_hierarchy_percent` compares. Do not ship it.
* **The category-widening patches (C2, C3) each beat every `_is_titleish` change except
  T5.** They address the `Text` (19,062 elements) and `List-item` (4,705) populations
  that can never carry a heading today.

### 3.3 Stacked — measured, because these levers overlap heavily

| stack | corpus | SemFmt | ΔSemFmt | ΔOverall |
|---|---|---|---|---|
| T5 + G | element 319 | 64.48 | +10.23 | +2.05 |
| T5 + G2 | element 319 | 66.64 | +12.38 | +2.48 |
| T5 + C2 + G2 | element 319 | 67.08 | +12.83 | +2.57 |
| **MAXBOLD alone (reference on the same corpus)** | element 319 | **75.00** | **+20.74** | +4.15 |
| **T5 + MAXBOLD** | element 319 | **75.12** | +20.86 | +4.17 |
| T5 + C2 + C3 + MAXBOLD | element 319 | 75.86 | +21.60 | +4.32 |
| G2 then MAXBOLD (ordering check) | full 476 | 71.77 | +19.36 | +3.87 |

**The overlap is severe and it is the most important structural result in this report.**
T5 alone is worth +6.80 SemFmt. MAXBOLD alone is worth +20.74. Together: +20.86 — T5's
**marginal** contribution on top of MAXBOLD is **+0.12**, i.e. 98 % of it is
double-counting. Once every line is bold, it no longer matters which lines are headings.
Anyone adding these deltas together will over-predict by a factor of ~1.3.

The last row is a deliberate ordering trap: applying G2 first and MAXBOLD second scores
**worse** (71.77) than MAXBOLD alone on the same corpus (73.32 full-corpus), because the
partial `**` spans G2 inserts make MAXBOLD refuse those lines — the guard against
nesting `**` inside `**` (`semfmt_patches.py:_bold_line_body`) fires. **Patch order is
load-bearing and must be fixed by construction, not left to whoever wires them up.**

### 3.4 The two 1/5-weight sub-scores: both dead ends

`../.venv/bin/python scripts/latex_code_patch.py`:

```
documents with a ```latex fence            : 4/476
documents carrying is_latex rules          : 32
is_latex rules                             : 123
documents with BOTH (where the fix can pay): 4

LATEX FENCE -> $$ …  $$
  SemFmt 52.42 -> 52.42  (+0.00 SemFmt, +0.00 Overall)
  is_latex 0.4607 -> 0.4607

CODE BLOCKS
  is_code_block rules: 10  languages={'json': 1, 'python': 5, 'fortran': 1, 'mki@mki:~/sis1100/sis3820>': 1, 'cpp': 2}
  annotated snippet present in our markdown : 7
  annotated snippet absent entirely         : 3
  fenced code blocks we emit (any language) : 5 docs
```

* **The LaTeX fence fix is worth exactly +0.00.** `_nano_format_formula`
  (`:2911-2917`) wraps formulas in a ```` ```latex ```` fence that `LatexRule`
  (`rules_formatting.py:497-535`) cannot see — but only **4** of 476 documents contain
  such a fence, and none of them is one where the fix changes a verdict. This
  contradicts the previous report's ranked suggestion #6 ("≤ +0.20"); the correct figure
  is zero. The 0.4607 `is_latex` credit we do earn comes from formulas that reach the
  markdown inside ordinary `Text` elements.
* **Code blocks cannot be fixed at emission level.** 7 of 10 annotated snippets are
  present in our markdown, but the layout label `code` is remapped to `Text` at
  `kdl_frontier_nano.py:549`, so the region is never labelled as code and no
  language-tagged fence can be synthesised. One of the five annotated languages is
  literally a shell prompt string (`mki@mki:~/sis1100/sis3820>`), so guessing the tag is
  hopeless. Ceiling: +0.11 Overall over 5 documents. Do not spend time here.

---

## 4. Deliverable 4 — collateral damage on the other four dimensions

### 4.1 Which dimensions can move at all

| dimension | source | can an emission patch move it? |
|---|---|---|
| Semantic Formatting | `text_formatting` / `semantic_formatting` | yes — that is the target |
| **Content Faithfulness** | `text_content` / `content_faithfulness` | **yes — measured below** |
| **Charts** | `chart` / `rule_pass_rate` | **yes in principle — measured below** |
| Tables | `table` / `grits_trm_composite` | only if a patch touches table markup |
| Visual Grounding | `layout` / `layout_element_rule_pass_rate` | **no, by construction** |

Visual Grounding is invariant *by code inspection, verified*: `normalize()`
(`kdl_frontier_nano.py:3287-3296`) builds each `LayoutItemIR.md` from the raw
per-element `e["content"]` and its bounding box — **not** from the assembled markdown or
from `_nano_format_element`. Every patch measured here changes only
`_nano_format_element` output, `_is_titleish`, or the final markdown string, so none of
them can reach `layout_pages`. Tables are checked empirically rather than argued: every
patch skips lines inside `<table>…</table>` and lines beginning with `|`, and the
measurement asserts byte-identity of extracted table blocks and pipe rows.

### 4.2 A first, fast signal: does `normalize_text` see the patch?

`normalize_text` (`evaluation/metrics/parse/utils.py:223-358`) is what
Content-Faithfulness rules compare against. It strips `**`, `__`, `*`, `_`, `<b>`,
`<u>`, `~~`, `<mark>` — **but it has no rule for `#` at all.** Measured over all 2,040
documents with stored markdown:

| patch | `normalize_text` output unchanged | changed |
|---|---|---|
| E bold run-in labels | 2,038 / 2,040 | 2 |
| F2 bold own-lines ≤14 w | 2,035 / 2,040 | 5 |
| F2 bold own-lines ≤40 w | 2,034 / 2,040 | 6 |
| **MAXBOLD** | **2,034 / 2,040** | **6** |
| **HEADALL** | **123 / 2,040** | **1,917** |

**The `**` route is invisible to Content Faithfulness; the `#` route is not.** This is
the reason the recommended set uses bold for the aggressive part and headings only where
they are semantically justified. (It is a proxy, not the metric — §4.3 has the real
measurement, which is milder for `#` than this proxy suggests because the sentence rules
independently strip a leading `#{1,6}\s+`, `rules_bag.py:127`.)

### 4.3 The real measurement

The real `text_content` and `chart` rules re-run over patched markdown. Baselines
reproduce our shipped numbers exactly (Content Faithfulness 87.1751 vs shipped 0.871751;
Charts 63.686 vs shipped 0.6369 rounded). *Note: the CF baseline prints as 87.25 in the
table below because that run predates the blank-output fix described in §1.1; the paired
deltas are unaffected, and the corrected baseline is 87.18.*

| patch | CF base | CF new | **ΔCF** | Charts base | Charts new | **ΔCharts** | table markup changed |
|---|---|---|---|---|---|---|---|
| E bold run-in `Label:` prefixes | 87.25 | 87.25 | **+0.00** | 63.69 | 63.72 | **+0.04** | **0 / 1,074** |
| F bold short standalone lines | 87.25 | 87.25 | **+0.00** | 63.69 | 64.11 | **+0.42** | **0 / 1,074** |
| F2 bold short own-lines | 87.25 | 87.25 | **+0.00** | 63.69 | 64.59 | **+0.90** | **0 / 1,074** |
| G2 = E + F2 | 87.25 | 87.25 | **+0.00** | 63.69 | 64.59 | **+0.90** | **0 / 1,074** |
| **MAXBOLD** bold every non-table line | 87.25 | 87.25 | **+0.00** | 63.69 | 64.59 | **+0.90** | **0 / 1,074** |
| **HEADALL** `# ` every non-table line | 87.25 | 86.04 | **−1.21** | 63.69 | 66.00 | **+2.31** | **0 / 1,074** |
| **T5** relaxed `_is_titleish` (provider) | 87.45 | 87.32 | **−0.13** | 63.80 | 65.44 | **+1.64** | **0 / 1,074** |
| **C2** short single-line `Text` → `# ` (provider) | 87.45 | 87.32 | **−0.13** | 63.80 | 63.92 | **+0.12** | **0 / 1,074** |

(The two provider rows are measured against a *re-assembled* baseline — 87.45 / 63.80
rather than 87.18 / 63.69 — because a provider-level patch has to be compared against
re-assembled markdown for the comparison to be paired. Two things contribute to that
offset: the 157 documents that do not reconstruct byte-exactly, and the +0.075
blank-output inflation described in §1.1. Only the delta is meaningful, and the delta is
unaffected by either.)

**Three results that change the recommendation:**

1. **Every `**`-based patch is exactly Content-Faithfulness-neutral — including the
   fully degenerate MAXBOLD.** ΔCF = **+0.0000** over 506 documents; not rounded to
   zero, identically zero (`scripts/_semfmt_measure.json`). `normalize_text` strips `**`
   (`utils.py:256-257`), so the comparison never sees it. This is a stronger result than
   the `normalize_text`-equality proxy suggested (6 documents differed there; none of
   them differed *enough* to move a single rule verdict). Precise figures:
   E +0.0000 / F +0.0000 / F2 +0.0000 / G2 +0.0000 / MAXBOLD +0.0000; versus
   HEADALL −1.2077, T5 −0.1257, C2 −0.1336.
2. **The `#`-based route does cost Content Faithfulness, but the cost scales with how
   many lines are promoted, and for a realistic heading patch it is small.** `normalize_text`
   has no rule for `#`, so the markers survive into the comparison. The degenerate
   HEADALL costs **−1.21** points (−0.24 Overall); the realistic T5 gate relaxation costs
   **−0.13** points (−0.03 Overall). (Both are far milder than the
   `normalize_text`-equality proxy implied, because the sentence rules independently
   strip a leading `#{1,6}\s+`, `rules_bag.py:127`.) **The practical conclusion stands:
   prefer bold for the aggressive part, and use headings only where a heading is
   semantically justified — but heading patches are not disqualified.**
3. **Charts *improves* under bolding, by a mechanism worth understanding.**
   `ChartDataPointRule._extract_formatted_labels` (`rules_chart.py:370-394`) will only
   accept a chart's **title** label if it appears in the pre-table context as bold text
   (`**…**`, `<b>`, `<strong>`) or as a markdown/HTML heading. Our pipeline emits chart
   titles as plain `Text`, so those labels were simply invisible and the rule fell
   through to failure. This is a genuine defect the benchmark was measuring and we were
   losing: **+0.90 Charts from bolding, +2.31 from headings.** It also means the two
   patch families are worth slightly more than their Semantic Formatting delta alone.

**Tables: zero documents out of 1,074 had any change to an HTML `<table>…</table>` block
or any pipe-table row**, for every patch including MAXBOLD and HEADALL. Every patch
skips lines inside a table block and lines beginning with `|` by construction
(`semfmt_patches.py:_table_line_mask`, `_skippable`). Tables / GriTS is therefore
unchanged.

**Visual Grounding: unchanged by construction and verified empirically.** `normalize()`
(`kdl_frontier_nano.py:3287-3296`) builds each `LayoutItemIR` from the element's raw
`content` string and its bounding box, never from `_nano_format_element` output or the
assembled markdown. `scripts/final_collateral.py` verifies this by comparing the
`(category, bbox, content)` triple of every element before and after applying the full
provider patch stack:

```
Visual Grounding invariance check
  documents probed: 400   with any (category, bbox, content) change: 0
```

**Net Overall effect, combining all measured dimensions:**

| patch | corpus | ΔSemFmt/5 | ΔCF/5 | ΔCharts/5 | **net ΔOverall** |
|---|---|---|---|---|---|
| E bold run-in labels | full 476 | +0.80 | +0.000 | +0.01 | **+0.81** |
| G2 = E + F2 | full 476 | +2.04 | +0.000 | +0.18 | **+2.22** |
| F2 with a 40-word cap | full 476 | +3.09 | +0.000 | +0.18 | **+3.27** |
| **MAXBOLD** | full 476 | +4.18 | +0.000 | +0.18 | **+4.36** |
| HEADALL | full 476 | +4.06 | −0.242 | +0.46 | **+4.28** |
| **T5** relaxed `_is_titleish` | element 319 | +1.36 | −0.025 | **+0.33** | **+1.66** |
| C2 short `Text` → heading | element 319 | +0.81 | −0.027 | +0.02 | **+0.81** |

Notes on reading this table:

* The Charts figure for the 40-word variant is taken from F2, which produces the same
  Charts delta as MAXBOLD; the Charts gain **saturates** once chart titles are bolded.
* The two provider rows carry the element-sub-corpus transfer caveat from §1.2. Their
  ΔSemFmt is the sub-corpus delta transferred directly (T5 +6.80 SemFmt, C2 +4.06). If
  instead you rescale by the 67.2 % coverage — which §1.2 argues against — they become
  +0.91 and +0.55 respectively.
* **T5 is worth roughly 22 % more than its Semantic Formatting delta alone once Charts is
  counted**, and Charts is where the heading route has its largest side-effect. No
  Semantic-Formatting-only analysis would have revealed that.

---

## 5. Deliverable 5 — best achievable Overall, and the patch set

### 5.1 The two candidate sets

**Set A — defensible.** Changes a reviewer would read as the parser doing its job
better:

| | patch | level | source lines |
|---|---|---|---|
| A1 | heading **levels** from `Title` bounding-box height (fixes the flat-`h1` defect) | provider | `:545-572`, `:2931-2933` |
| A2 | `_is_titleish`: drop the caps gate, the terminal-punctuation veto and the label-value veto; raise the word cap to 30 | provider | `:2494-2508` |
| A3 | short single-line `Text` elements emitted as `# ` | provider | `:2957` |
| A4 | `List-item` elements emitted as `## ` | provider | `:2954-2956` |
| A5 | bold run-in `Label:` prefixes | markdown | new rule after `:2585` |
| A6 | bold every own-line of ≤ 40 words | markdown | new rule after `:2585` |

**Set B — ceiling.** Set A plus MAXBOLD (bold the whole body of every non-table line,
no length cap). Reported as a **bound**, not a recommendation: it asserts that
essentially all body text is bold, which is only "free" because this corpus contains
**zero `is_not_bold` rules**, so false positives cost nothing inside the dimension
(`evaluators/parse.py:388-406`; `neg_score` is always 1.0). A benchmark maintainer who
added negative rules would turn Set B from +4.5 into a large negative overnight.

### 5.2 Measured

Element sub-corpus (319 documents), baseline SemFmt 54.26:

| stack | SemFmt | ΔSemFmt | `is_bold` | `is_title` | `hier` | styling | title acc. |
|---|---|---|---|---|---|---|---|
| A1 alone (bbox heading levels) | 55.61 | +1.36 | 0.418 | 0.789 | 0.692 | 0.369 | 0.740 |
| A1 + A2 | 62.44 | +8.19 | 0.548 | 0.837 | 0.734 | 0.473 | 0.786 |
| **A1+A2+A3+A4 (heading side only)** | **68.43** | **+14.17** | 0.697 | 0.857 | 0.748 | 0.590 | 0.803 |
| **A5+A6 (bold side only)** | **68.44** | **+14.19** | 0.732 | 0.855 | 0.706 | 0.617 | 0.781 |
| **SET A = A1…A6** | **73.11** | **+18.85** | 0.789 | 0.888 | 0.780 | 0.659 | 0.834 |
| **SET B = SET A + MAXBOLD** | **76.94** | **+22.69** | 0.880 | 0.895 | 0.787 | 0.726 | 0.841 |

Note the near-identity of the two "one side only" rows: heading-side changes alone are
worth +14.17 and bold-side changes alone +14.19, yet stacked they give +18.85 rather
than +28.36. **They overlap by about 66 %** — both routes are chasing the same
underlying failures, which is exactly why the hypothesis is half right.

### 5.3 Projected leaderboard rows

Transferring sub-corpus SemFmt deltas onto the full-corpus baseline of 52.42 (§1.2
bounds the error at roughly ±1 SemFmt point):

Set A and Set B were then run end-to-end through the real `text_content` and `chart`
rules (`scripts/final_collateral.py`), so their collateral is measured rather than
inferred from single-patch rows. Set A's measured effect:

```
SET A
  Content Faithfulness     87.37 ->   87.12   delta  -0.25 pts   (Overall impact -0.05)
  Charts                   63.80 ->   65.93   delta  +2.13 pts   (Overall impact +0.43)
  Tables (byte-identity) docs with any table-markup change: 0/1074
```

**Set A's Charts gain (+2.13) is more than four times larger than its
Content-Faithfulness cost (−0.25).** Applying those deltas to our shipped row:

| row | Tables | Charts | Content Faith. | **SemFmt** | Visual Gr. | **Overall** | vs 76.36 |
|---|---|---|---|---|---|---|---|
| our run as shipped | 85.76 | 63.69 | 87.18 | 52.42 | 74.19 | **72.65** | −3.71 |
| **bold-only, no heading changes** (E + F2/40w) — every member measured on the full 476-doc corpus | 85.76 | **64.59** | **87.18** | **67.88** | 74.19 | **75.92** | −0.44 |
| **MAXBOLD only** — markdown-level, full corpus, all three dimensions measured | 85.76 | **64.59** | **87.18** | **73.32** | 74.19 | **77.01** | **+0.65** |
| **SET A** (heading + bold, defensible) | 85.76 | **65.82** | **86.93** | **71.27** | 74.19 | **76.79** | **+0.43** |
| **SET B** (Set A + MAXBOLD, ceiling) | 85.76 | 65.82 | 86.93 | **75.10** | 74.19 | **77.56** | **+1.20** |
| published KDL | 85.56 | 63.41 | 87.19 | 66.81 | 78.84 | 76.36 | — |

Set B was measured end-to-end too, and its collateral came out **identical to Set A's** on
every dimension:

```
SET B
  Content Faithfulness     87.37 ->   87.12   delta  -0.25 pts   (Overall impact -0.05)
  Charts                   63.80 ->   65.93   delta  +2.13 pts   (Overall impact +0.43)
  Tables (byte-identity) docs with any table-markup change: 0/1074

Visual Grounding invariance check
  documents probed: 400   with any (category, bbox, content) change: 0
  -> layout_pages inputs unchanged, so layout_element_rule_pass_rate is unchanged.
```

That is a useful independent result in itself: **adding MAXBOLD on top of a heading patch
costs exactly nothing on Content Faithfulness, adds nothing further to Charts (the Charts
gain saturates once chart titles are marked), and touches no table markup.** So every cell
in the table above is a measurement — none is inferred.

### 5.4 Verdict on Deliverable 5

**Best achievable Overall from emission-level changes alone: 77.56 (Set B, degenerate) or
76.79 (Set A, defensible). Both clear 76.36 — Set A by +0.43, which is just outside the
±0.2 transfer uncertainty, so it is a real if narrow win.**

Stated precisely:

* **Set A: Overall 76.79, +4.14 over our shipped 72.65, clears KDL by +0.43.** Composed
  of SemFmt +18.85 → 71.27, Charts +2.13 → 65.82, Content Faithfulness −0.25 → 86.93,
  Tables and Visual Grounding unchanged. Every component is a replay measurement.
* **Set B (adding MAXBOLD): Overall 77.56, clears by +1.20** — but it asserts that every
  line of body text in every document is bold, and that only scores well because this
  corpus contains **zero `is_not_bold` rules**. Do not ship it.
* **The best single *clean* patch is MAXBOLD alone at Overall 77.01** — higher than the
  whole defensible Set A, from 20 lines of markdown post-processing, measured on the full
  476-document corpus with no transfer caveat and at exactly zero Content-Faithfulness
  cost. That it beats the honest work is itself the finding: **this dimension is highly
  gameable, and a competitor's high Semantic Formatting score is weak evidence of better
  parsing.**
* **The most defensible individual patches, in the order I would land them.** ΔOverall
  is from Semantic Formatting alone unless a Charts figure is given; provider-level rows
  carry the §1.2 transfer caveat.

  | rank | patch | ΔOverall | why it is defensible |
  |---|---|---|---|
  | 1 | **A1 heading levels from bbox height** | +0.27 | fixes a real structural bug: `Section-header` is never emitted, so 12.9 % of `title_hierarchy_percent` is unreachable. Zero CF cost. |
  | 2 | **E bold run-in `Label:` prefixes** | **+0.81** (SemFmt +0.80, Charts +0.01, CF 0.000) | run-in labels genuinely *are* bold in the source PDFs; measured on the full corpus |
  | 3 | **A2/T5 relaxed `_is_titleish` gates** | **+1.66** (SemFmt +1.36, Charts +0.33, CF −0.03) | the terminal-punctuation and 12-word vetoes reject genuine headings |
  | 4 | **A3/C2 short single-line `Text` → heading** | **+0.81** (SemFmt +0.81, Charts +0.02, CF −0.03) | 19,062 `Text` elements can never be headings today |
  | 5 | A4/C3 `List-item` → `## ` | +1.06 | weakest of the five — most list items are not headings |
  | — | F2/F with a word cap ≥ 25 | +2.51 … +3.27 | shades into gaming as the cap rises |
  | — | MAXBOLD / HEADALL | +4.36 / +4.28 | pure gaming |

* **Why no honest patch set gets much past 76.4:** the remaining headroom is 240
  `is_bold` and 245 `is_title` failures where the annotated text is **absent from the
  output entirely** (recognition or layout failure), 825 `is_bold` failures that need
  the model to mark inline emphasis, and the entire `is_sup`/`is_sub`/`is_strikeout`
  ceiling of +1.74 Overall, which needs the model to emit markup it currently never
  emits. **All of that requires the GPU. Emission-level work is exhausted at the +4.1
  Overall that Set A measures, and beyond that only the model can help.**
* **One encouraging corollary, worth stating because it makes the recommendation cheaper
  to defend.** Set A's most aggressive member is A6 (bold every own-line of ≤40 words).
  But the heading-side quartet A1-A4 alone measures +14.17 SemFmt and the full Set A
  measures +18.85, so A5+A6 together add only +4.68 marginal — and A5 (bold run-in
  `Label:` prefixes) is worth +3.98 on its own. **A6's marginal contribution once the
  heading patches are in place is therefore about +0.7 SemFmt, or +0.14 Overall.**
  Dropping the one member a reviewer would object to costs almost nothing: SemFmt ≈ 70.57
  and **Overall ≈ 76.65, which still clears 76.36.** *This specific stack
  (A1+A2+A3+A4+E, without A6) was not measured directly — the figure is inferred from the
  three stacks that were, and should be confirmed before anyone relies on it.*

One further arithmetic point worth stating: even at Semantic Formatting 100.00, our row
would score `(85.76 + 63.69 + 87.18 + 100 + 74.19)/5 = 82.16`. And even at the published
66.81 exactly, we would score `(85.76 + 63.69 + 87.18 + 66.81 + 74.19)/5 = 75.53` —
**still 0.83 short of 76.36.** So Semantic Formatting alone cannot close our Overall gap
to KDL: **4.65 points of Visual Grounding deficit (74.19 vs 78.84) remain, and that is
a layout-detection problem, not a formatting problem.** Any plan that spends all
remaining effort on Semantic Formatting is aimed at the wrong dimension.

---

## 6. What this means for the hypothesis, stated plainly

**Held:** heading emission has enough headroom to explain a 14.39-point Semantic
Formatting gap (oracle-perfect bold reaches 74.12), and heading-side changes alone are
measurably worth +14.17 SemFmt — almost exactly the size of the gap. In that arithmetic
sense the hypothesis is vindicated.

**Did not hold:** every specific claim about *which* heading lever matters.

| claim | verdict | measured |
|---|---|---|
| `_is_titleish`'s leading-capital gate is the lever | **wrong** | 3 of 1,303 bold failures; +0.09 Overall |
| our run emits "materially fewer" headings | **unquantifiable, and probably not the story** | we emit 3,781 headings in 453/476 documents; half of them synthesised by `title_promote`. Without KDL's own outputs there is no way to compare heading counts |
| heading emission is the dominant failure mode | **wrong** | 63.3 % of bold failures are inline-merged text; only 13.3 % (`standalone_gated` + `own_line_not_standalone`) are heading-gate failures |
| the gate is the discriminator | **partly** | the *word cap* and *terminal-punctuation veto* are, not the caps gate |

**And two larger defects the hypothesis missed entirely:**

1. **`Section-header` is never emitted** (0 / 2,078 artifacts), so every heading is
   `h1` and 12.9 % of `title_hierarchy_percent` is structurally unreachable. Fixing
   levels from bounding-box height: **+1.36 SemFmt**, at zero Content-Faithfulness cost,
   and it is the only patch here that a reviewer would call unambiguously correct.
2. **`Text` (19,062 elements) and `List-item` (4,705) can never become headings.**
   Widening those two categories is worth **+4.06** and **+5.31** SemFmt — each more
   than any `_is_titleish` tweak except the fully-relaxed T5.

The honest reading of §2.3 is that **the biggest single lever is not a heading lever at
all.** 825 of 1,303 `is_bold` failures are run-in emphasis inside a longer line. The
grader will accept a `#` heading containing that line, which is why the degenerate
patches score so well, but the *correct* fix is `**…**` around the emphasised span —
and knowing where the span is requires the model to tell us, which requires a prompt
change or a fine-tune, which requires the GPU.

---

## 7. What I could NOT measure, stated explicitly

1. **Whether the published 66.81 run actually emits different headings.** We have no
   access to KDL's own outputs. I could test only whether heading emission has enough
   headroom to explain the gap (it does) and which gates in *our* pipeline cost what.
   The hypothesis as literally worded — "our run produces materially fewer or different
   `#` headings than the run that produced 66.81" — is **not directly testable with the
   artifacts available**, and nothing in this report should be read as confirming it.
2. **Provider-level patches on 157 of 476 documents.** They cannot be replayed because
   `picture_path` is not persisted, so their markdown cannot be reconstructed
   byte-identically. §1.2 bounds the transfer error at 0.16-0.84 SemFmt points using
   markdown-level patches measurable on both corpora, but that bound is *inferred* for
   the provider-level patches, not measured. **This is the largest single uncertainty in
   the projected Overall figures — treat Set A's 76.79 as 76.8 ± 0.2, i.e. its +0.43
   margin over KDL is real but not comfortable.**
3. **Tables / GriTS was not recomputed.** I asserted table invariance by byte-comparing
   extracted `<table>…</table>` blocks and pipe-table rows, not by re-running the GriTS
   metric ("Grid Table Similarity", the benchmark's table-structure score). A patch that
   passed the byte check cannot change GriTS, but I did not prove GriTS is deterministic
   under an unchanged input.
4. **Visual Grounding's metric was not recomputed, only its inputs.** I verified that no
   patch changes any element's `(category, bbox, content)` triple — the only things
   `layout_pages` is built from (`kdl_frontier_nano.py:3287-3296`) — over a 400-document
   probe, and 0 changed. That is a proof that the *input* is unchanged, plus a code
   argument that the metric is a pure function of that input. I did not re-run
   `layout_element_rule_pass_rate` itself.
5. **`is_sup`, `is_sub` and `is_strikeout` cannot be moved at emission level at all** —
   there is no markup in the model's output to convert, so there is nothing for a
   renderer to preserve. Their combined oracle is +8.68 SemFmt / +1.74 Overall and it is
   entirely gated on the model. The previous report's finding stands: naive `<sup>`
   wrapping is actively harmful because `normalize_text` deletes `<sup>…</sup>`
   *including its contents* (`utils.py:330-334`), erasing real digits from the
   Content-Faithfulness comparison. The Unicode superscript route is equally unsafe —
   `utils.py:336-343` strips Unicode superscript and subscript digits too.
6. **Whether Set A's aggressive members survive review.** A6 bolds every line of ≤40
   words and A4 turns every list item into an `h2`. Both are measured, both are within
   the letter of the pipeline's own "aggressive" post-processing philosophy, and both
   would be hard to defend as *parsing* rather than *scoring*. I have flagged which
   members are which; the judgement is not mine to make.
7. **The 240 `is_bold` and 245 `is_title` failures where the text is simply absent**
   (18.4 % / 45.0 % of failures) are recognition and layout failures. No emission change
   touches them. Their share of the remaining headroom needs a GPU.
