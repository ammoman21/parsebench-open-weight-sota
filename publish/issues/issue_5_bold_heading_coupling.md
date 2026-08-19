# is_bold accepts any heading line containing the text, so heading promotion earns bold credit — a ~20-line transformation exceeded the then-leading score (disclosed, not exploited)

## What

The bold matcher accepts three kinds of evidence: `**text**`, `<b>text</b>`, or **any `#`-heading line containing the annotated text**. The heading arm is a reasonable proxy on its own — headings render bold. But two properties of the current corpus compose with it badly:

1. The leading open-weight pipeline emits **no inline markup at all** — across 23,802 elements from 1,196 documents there is not one bold, strikethrough, superscript or subscript marker — so **100% of its bold credit arrives through the heading arm**. Its bold score is effectively a count of how many lines it labels as headings.
2. The shipped data contains **zero negative styling rules** (`grep -c 'is_not_' data/text_formatting.jsonl` → 0), so the "avoid false styling" half of the styling score is always a free 1.0 and indiscriminate marking costs nothing inside the dimension.

Together these make Semantic Formatting — and through it, Overall — movable by reformatting alone, without detecting any bold.

## Where

- `src/parse_bench/evaluation/metrics/parse/rules_formatting.py:189-205` — `_build_bold_patterns`; the third pattern is the heading arm (`^[ \t]*#{1,6}[ \t]+...`, matching the query anywhere on the heading line).
- `src/parse_bench/evaluation/evaluators/parse.py:388-406` — with no negative rules present, `neg_score` defaults to 1.0.

## Evidence (measured, then disclosed rather than submitted)

Measured by replay over the full corpus with the benchmark's own rule classes (baseline reproduces the shipped Semantic Formatting to ten decimal places):

- Promoting short body-text lines and list items to headings — changing nothing about reading accuracy — moves the leading pipeline's Overall by about **three points**.
- A single ~20-line markdown post-processing rule (bold the body of every non-table line) reaches **Overall 77.01**, above the then-published open-weight leader (76.36), at **exactly 0.0000** cost to Content Faithfulness (the text normalizer strips `**` before comparison) and with 0 of 1,074 documents' table markup changed.

We put this in our public preregistration as a property of the scorer, not of any parser, and excluded every configuration containing it from anything we submit. We are filing it so it can be fixed before someone banks it instead.

## Impact

A high Semantic Formatting score is currently weak evidence of better parsing for any pipeline that emits few real markers, and the dimension is quietly coupled to heading policy. Conversely, if negative rules are ever added, scores earned this way would invert overnight — which is a fairness problem in both directions.

## Suggested fix

Two complementary changes:

1. **Require an explicit bold marker when the annotated span is not itself a heading in the ground truth.** The annotations already know which spans are headings; the heading arm of the matcher could be gated on that, keeping the legitimate "headings render bold" credit while closing the promotion route.
2. **Add `is_not_bold` (and sibling) negative rules** to the dataset so indiscriminate marking has a cost. The schema already supports them (`test_types.py`); the data just contains none.

## Reproduction

Replay harness, patch definitions and saved measurement records: https://github.com/ammoman21/parsebench-open-weight-sota (see `parsebench/scripts/semfmt_measure.py`, `semfmt_patches.py`, `final_collateral.py`).
