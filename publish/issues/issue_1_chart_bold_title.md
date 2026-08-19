# ChartDataPointRule rejects correct data extraction when the chart title is not bold or a heading

## What

`chart_data_point` scoring has a phase-2 fallback for labels not found inside the table itself (typically the chart/series title): the label may be satisfied from the text preceding the table. But that fallback only accepts the label if it is *formatted* — `**bold**`, `<b>`/`<strong>`, a Markdown or HTML heading, or a `<caption>`. Plain paragraph text does not qualify. A parser that extracts every data point correctly but renders the chart title as an ordinary text line loses those rule checks on typographic grounds.

## Where

- `src/parse_bench/evaluation/metrics/parse/rules_chart.py:370-394` — `_extract_formatted_labels` collects only bold/heading/strong spans from `context_before`.
- `rules_chart.py:434-461` — the context match runs only against those formatted labels.
- `rules_chart.py:463-493` — the heading/caption alternative (`_is_label_in_heading_or_caption`).

(Line numbers from the commit we pinned in mid-August 2026.)

## Evidence

We measured this as a side effect while studying the Semantic Formatting dimension, using a replay harness that re-scores stored outputs with the benchmark's own rule classes (baseline reproduces the shipped Charts number, 63.686 vs 0.6369 rounded):

- Applying bold/heading markup patches **that change no table markup at all** (byte-identity verified: 0 of 1,074 documents had any `<table>` block or pipe-table row change) moved the Charts dimension for the leading open-weight pipeline from **63.80 to 65.93 (+2.13)**.
- Decomposed: bolding alone is worth **+0.90** Charts; heading promotion up to **+2.31**. The gain saturates once chart titles are marked.
- The extraction itself was byte-identical in every case. Only the typography around the tables changed.

The mechanism is that this pipeline emits chart titles as plain `Text` elements, so the annotated title labels were invisible to `_extract_formatted_labels` and the rules fell through to failure.

## Impact

- The Charts dimension partially measures typography rather than extraction, penalising parsers that emit correct data with plain-text titles.
- It also couples Charts to Semantic Formatting: any bold/heading-emission change moves the Charts score as collateral, which makes cross-pipeline Charts comparisons noisier than the deterministic-rule design intends.

## Suggested fix

Accept the title label from plain text in `context_before` as well — the context is already tightly scoped (5 preceding lines for a Markdown table, ~300 chars / 3 siblings for HTML), so the false-positive surface is small. Alternatively, keep the formatted-text requirement but score title association as a separate sub-signal so data-point extraction is not zeroed by it.

## Reproduction

Measurement code and saved records: https://github.com/ammoman21/parsebench-open-weight-sota (see `parsebench/scripts/final_collateral.py` and the accompanying measurement JSON). Happy to provide anything else that helps.
