# is_underline, is_italic and is_mark are annotated and evaluated but contribute to no scored category (undocumented)

## What

The `text_formatting` dataset carefully annotates three styling types that turn out to carry zero weight in the published Semantic Formatting score:

| type | rules | documents (of 476) |
|---|---:|---:|
| `is_italic` | 655 | 155 |
| `is_underline` | 405 | 116 |
| `is_mark` | 88 | 13 |

Their matchers exist and run, their per-type sub-metrics (`rule_is_underline_pass_rate`, etc.) are emitted — but the headline `semantic_formatting` value is assembled from the styling category (bold, strikeout, superscript, subscript only), the title category, LaTeX and code blocks. A pipeline scoring 0% or 100% on underline/italic/highlight gets an identical Semantic Formatting number. Nothing in the README or the data documents this.

## Where

`src/parse_bench/evaluation/evaluators/parse.py:344-380` — `_TEXT_STYLING_PAIRS` lists only `is_bold`/`is_strikeout`/`is_sup`/`is_sub` (with their `is_not_*` twins); `_TITLE_TYPES`, `_CODE_BLOCK_TYPES` and `_LATEX_TYPES` cover the rest. `is_underline`, `is_italic`, `is_mark` (and `mark_color`) appear in no category set. Headline assembly at `parse.py:511-539`.

## Evidence

- Visible in the benchmark's own per-document output: for a page carrying two `is_underline` rules and one `is_strikeout` rule, the `normalized_text_styling` metadata reads `"included_types": ["is_strikeout"]` — both underline rules discarded from the score.
- Oracle simulation over all 476 documents of `data/text_formatting.jsonl`, re-implementing the aggregation in `parse.py:344-539` exactly: forcing `is_underline` (or `is_italic`, or `is_mark`) to a perfect 1.0 changes `avg_semantic_formatting` by **+0.00**.
- A related aggregation footnote: 19 of the 476 documents carry *only* unscored rule types, produce no `semantic_formatting` value at all, and silently drop out of the macro mean.

## Impact

Mostly wasted effort rather than a wrong score — but it is real effort: we spent most of a working day engineering underline emission before measuring that its ceiling is exactly zero, and the annotations invite anyone else to do the same. It also means three annotated phenomena the dataset paid to label are invisible to the leaderboard.

## Suggested fix

Either add the three types to a scored category (e.g. widen `_TEXT_STYLING_PAIRS`), or state their status explicitly in the README's dimension table so submitters can prioritise correctly. A one-line note would have saved us the day.

## Reproduction

Simulation and verification code: https://github.com/ammoman21/parsebench-open-weight-sota. The `included_types` example above is from `output/.../text/text_ocr__p4013` in our published run records.
