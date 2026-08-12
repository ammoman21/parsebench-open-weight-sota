# ParseBench scoring specification — `text_formatting` (Semantic Formatting) and `chart` (Charts)

Reverse-engineered by reading the evaluation code, the shipped annotation files, and our own
`kdl_frontier_nano` results, then **executing the real matchers** against hand-built inputs to
confirm which output strings pass. Every claim below carries a `file:line` citation. Paths are
relative to `/Users/amolpant/forecasting_networks/bfcl-sprint/parsebench/`.

## Vocabulary used in this report (plain language)

- **Rule / annotation record** — one line of a `.jsonl` file describing one assertion about one PDF
  page, e.g. "the text `CONFIDENTIAL` must be struck through". A page's score is the fraction of its
  rules that pass.
- **Matcher** — the Python code that decides pass/fail for one rule. All formatting matchers are
  regular-expression searches over the model's raw Markdown output string.
- **Regular expression (regex)** — a pattern language for matching text. `<u>` means the literal
  characters `<u>`; `.*?` means "any characters, as few as possible".
- **Macro average** — average of per-document scores, each document weighted equally regardless of
  how many rules it has. **Micro average** — pool all rules from all documents, then divide passes
  by total rules. ParseBench's headline numbers are macro; `micro_*` keys also appear in the report
  JSON but are not the headline.
- **F-beta / weighted harmonic mean** — a way of combining two rates (here: "did you apply the
  styling you should have" and "did you avoid styling you shouldn't have") that punishes the low one
  more than a plain average would. `beta = 0.5` weights the second more heavily.
- **Sub-metric** — a per-rule-type score emitted alongside the headline, e.g.
  `rule_is_underline_pass_rate`. Some sub-metrics feed the headline; several do not (see §3).

---

## 0. Executive answer, up front

1. **Underline wants `<u>text</u>` (or `<ins>text</ins>`) and nothing else.** Not `__text__`, not
   `<span style="text-decoration:underline">`. `rules_formatting.py:243-248`.
2. **Strikeout wants `~~text~~` or `<s>` / `<del>` / `<strike>`.** `rules_formatting.py:250-259`.
3. **Both score exactly 0.00 for `kdl_frontier_nano` because the pipeline emits none of those
   markers anywhere** — zero occurrences of `<u>`, `<ins>`, `~~`, `<s>`, `<del>`, `<strike>`,
   `<mark>`, `<sup>`, `<sub>` across all 200 of its `text/*.result.json` outputs (measured, §5).
   It is not a wrong-marker problem and not a matcher problem. The model emits plain text.
4. **Critically: fixing underline will not move the Semantic Formatting score at all.**
   `is_underline`, `is_italic`, `is_mark` and `mark_color` are *not members of any scored category*
   (`evaluators/parse.py:344-380`). They appear as sub-metrics and in `rule_pass_rate`, but the
   published `Semantic_Formatting` column is built only from bold / strikeout / superscript /
   subscript / title / LaTeX / code-block. Underline is a **vanity metric** on this leaderboard.
5. The three levers that *do* move the number, in order of measured headroom (§7):
   **superscript `<sup>` (+7.05 points), strikeout `~~` (+1.37), LaTeX `$…$` (+1.44),
   code blocks (+0.54), subscript `<sub>` (+0.18)** — plus the always-dominant bold and title terms.

---

## 1. The complete list of rule types in `text_formatting`

The dimension's annotations live in `data/text_formatting.jsonl` (5,997 rules over 476 documents).
Each line is **one rule**, not one document; a document's rules are grouped by the `pdf` field.
Record shape (`data/text_formatting.jsonl:1`):

```json
{"pdf": "docs/text/text_dense__baoutou.pdf", "category": "text_formatting",
 "id": "text_dense__baoutou_is_title_0", "type": "is_title",
 "rule": "{\"text\": \"BAOTOU 包头\", \"level\": 1}", "page": null,
 "expected_markdown": null, "tags": [...]}
```

Note `rule` is a **JSON string** that must itself be parsed; `type` is duplicated at top level.

### 1.1 Observed rule-type census

Counted from `data/text_formatting.jsonl` (full set) and `data/test/text_formatting.jsonl` (36-rule
test slice):

| `type` | rules (full) | docs containing it (of 476) | rules (test slice) | matcher class |
|---|---|---|---|---|
| `is_bold` | 2066 | 327 | 15 | `FormattingRule` |
| `is_title` | 1872 | 402 | 13 | `TitleLevelRule` |
| `is_italic` | 655 | 155 | 0 | `FormattingRule` |
| `is_underline` | 405 | 116 | 4 | `FormattingRule` |
| `title_hierarchy_percent` | 402 | 402 | 2 | `TitleHierarchyPercentRule` |
| `is_sup` | 318 | 86 | 0 | `FormattingRule` |
| `is_latex` | 123 | 32 | 0 | `LatexRule` |
| `is_mark` | 88 | 13 | 1 | `FormattingRule` |
| `is_strikeout` | 44 | 13 | 1 | `FormattingRule` |
| `is_sub` | 14 | 6 | 0 | `FormattingRule` |
| `is_code_block` | 10 | 5 | 0 | `CodeBlockRule` |

**No `is_not_*` (negative) rules exist anywhere in the shipped data** — verified by
`grep -c 'is_not_' data/text_formatting.jsonl data/text_content.jsonl` → `0` and `0`. This matters
for the aggregation (§3): the "avoid false styling" half of the styling score is always a free 1.0.

Rule types the code supports but that do **not** occur in `text_formatting.jsonl`:
`is_not_bold` / `is_not_italic` / `is_not_underline` / `is_not_strikeout` / `is_not_mark` /
`is_not_sup` / `is_not_sub` (enum at `evaluation/metrics/parse/test_types.py:53-67`), and
`mark_color` (`test_types.py:63`). `is_header` / `is_footer` (`test_types.py:74-75`) occur only in
`text_content.jsonl` (278 and 307 rules there).

### 1.2 Exact sub-metric names emitted

From `output/kdl_frontier_nano/text_formatting/_evaluation_report.json` → `aggregate_metrics`
(prefixed `avg_` / `min_` / `max_`, plus `micro_` for a few):

```
avg_rule_pass_rate                          0.3224
avg_rule_is_bold_pass_rate                  0.5341
avg_rule_is_title_pass_rate                 0.5139
avg_rule_title_hierarchy_percent_pass_rate  0.5139
avg_rule_is_underline_pass_rate             0.0000
avg_rule_is_strikeout_pass_rate             0.0000
avg_rule_is_mark_pass_rate                  0.0000
avg_normalized_text_styling                 0.3811
avg_normalized_title_accuracy               0.5139
avg_normalized_text_score                   0.3618
avg_semantic_formatting                     0.3618
micro_rule_pass_rate                        0.5000
total_rule_pass_rate_passed / _evaluated    18 / 36
```

The per-rule-type name is mechanically `rule_{type}_pass_rate` — built at
`evaluators/parse.py:275-285`:

```python
metrics.append(
    MetricValue(
        metric_name=f"rule_{rule_type}_pass_rate",
        value=pass_rate,
        metadata={"score_sum": score_sum, "total": total, "rule_type": rule_type},
    )
)
```

so `is_sup` → `rule_is_sup_pass_rate`, `is_latex` → `rule_is_latex_pass_rate`, etc. Those two
did not appear in our aggregate because our 3-document slice contains no `is_sup` / `is_latex` rules.

The headline for the dimension is **`semantic_formatting`**:
`analysis/aggregation_report.py:36-42` sets the default display metric per category —

```python
_DEFAULT_METRICS: dict[str, str] = {
    "table": "grits_trm_composite",
    "layout": "layout_element_rule_pass_rate",
    "text_content": "content_faithfulness",
    "text_formatting": "semantic_formatting",
    "form": "rule_form_field_pass_rate",
}
```

and `scripts/sync_hf_leaderboard.py:35-42` maps the dimension to the public column —

```python
TASK_TO_COLUMN = {
    "mean": "Overall", "table": "Tables", "chart": "Charts",
    "text_content": "Content_Faithfulness",
    "text_formatting": "Semantic_Formatting",
    "layout": "Visual_Grounding",
}
```

`README.md:106` confirms: `**Semantic Formatting** | text_formatting.jsonl | Semantic Formatting
Score | 476 | 476 | 5,997`.

### 1.3 What each rule type checks

All formatting matchers run against the **raw** Markdown string (`md_content`), not the
punctuation-stripped normalised form, because normalisation deletes markers
(`rules_formatting.py:317-334`, docstring: *"We search the raw md_content (not the normalized
version) because normalize_text strips all formatting markers"*).

- **`is_bold` / `is_italic` / `is_underline` / `is_strikeout` / `is_mark` / `is_sup` / `is_sub`** —
  `FormattingRule` (`rules_formatting.py:120`). The type name is split into a *kind* and a
  *polarity*: `is_not_X` → kind `X`, expect-absent; `is_X` → kind `X`, expect-present
  (`rules_formatting.py:150-158`). Each kind has its own list of regexes
  (`rules_formatting.py:376-384`); the rule passes if **any** regex matches
  (`rules_formatting.py:340-341`).
- **`mark_color`** — `MarkColorRule` (`rules_formatting.py:413`): text must be inside a `<mark …>`
  tag **and** the colour string must appear literally in that tag's attributes
  (`rules_formatting.py:446-456`).
- **`is_latex`** — `LatexRule` (`rules_formatting.py:513`): the annotated formula, stripped of its
  delimiters and with all whitespace removed, must equal one of the formulas found in the output
  after the same normalisation (`rules_formatting.py:490-510, 532-534`).
- **`is_code_block`** — `CodeBlockRule` (`rules_formatting.py:570`): there must be a fenced code
  block whose language tag equals the annotated `language` (lower-cased) and whose body contains the
  annotated `code` (exact substring, or substring after collapsing all runs of whitespace to one
  space) (`rules_formatting.py:598-622`).
- **`is_title`** — `TitleLevelRule` (`rules_formatting.py:708`). **The annotated `level` field is
  ignored** — docstring `rules_formatting.py:715-716`: *"The `level` field is currently ignored for
  matching; any heading level (1-6) or standalone bold title line can satisfy the rule."*
- **`title_hierarchy_percent`** — `TitleHierarchyPercentRule` (`rules_formatting.py:786`). A
  *graduated* rule: it returns a fractional score, not just pass/fail. Constraints are
  (a) each expected title exists, (b) for each parent→child edge, the child appears **later in the
  document** and at a **strictly deeper heading level**, (c) declared sibling order is preserved
  (order only, no depth requirement) (`rules_formatting.py:882-919`). Score = satisfied / total
  constraints; it only "passes" at `score >= 0.999` (`rules_formatting.py:919-920`) but the
  fractional score is what feeds the aggregate.
- **`is_header` / `is_footer`** — `PageSectionRule` (`rules_formatting.py:944`). Not used in
  `text_formatting`; it prefers structured `parse_output.layout_pages[].page_header_markdown` /
  `page_footer_markdown` over Markdown scanning (`rules_base.py:391-421`,
  `rules_formatting.py:974-995`).

---

## 2. For each rule type: exactly what output passes

Everything in this section was **executed** against the real matchers via
`create_test_rule(...).run(content)` (`rules_base.py:424`). `PASS`/`FAIL` below are observed
results, not predictions.

### 2.0 Two cross-cutting behaviours you must understand first

**(a) Markup tolerance between words, not around the query.** The rule text is `re.escape`d and then
each space becomes "optional inline markup + whitespace + optional inline markup"
(`rules_formatting.py:34, 42-55`):

```python
_INLINE_MARKUP_OPT = r"(?:\*{1,2}|~~|__?|</?\w+(?:\s[^>]*)?>)*"
...
joiner = _INLINE_MARKUP_OPT + r"\s+" + _INLINE_MARKUP_OPT
tolerant = joiner.join(parts)
return _INLINE_MARKUP_OPT + tolerant + _INLINE_MARKUP_OPT
```

So nested markup *inside* the span is tolerated (`<u>Hello **World**</u>` passes for text
`Hello World`), but arbitrary *extra words* inside the tag are not (see (b)).

**(b) `underline`, `strikeout`, `mark`, `sup`, `sub` require the tag to wrap the query text almost
exactly.** Their pattern builders are bare `open + query + close` with no filler
(`rules_formatting.py:243-280`). Bold and italic are the exception — they allow filler inside the
span (`rules_formatting.py:189-199, 215-239`), so `**Population:**` satisfies the query
`Population`. Measured:

```
PASS  is_underline text='Hello World'  content='<u>Hello World</u>'
FAIL  is_underline text='Hello World'  content='<u>Hello World.</u>'          # extra "." inside tag
FAIL  is_underline text='Hello World'  content='<u>prefix Hello World suffix</u>'
PASS  is_bold      text='Population'   content='**Population:**'             # filler allowed
```

**(c) Backslash escapes are undone before matching** (`rules_formatting.py:39, 334`), so
`\~\~gone\~\~` still passes `is_strikeout`. **(d) All patterns are case-insensitive**, so `<U>` works.

### 2.1 `is_underline` — **`<u>text</u>` or `<ins>text</ins>`. Nothing else.**

```python
# src/parse_bench/evaluation/metrics/parse/rules_formatting.py:243-248
@staticmethod
def _build_underline_patterns(escaped_query: str) -> list[re.Pattern]:
    """Detect <u>text</u> or <ins>text</ins>."""
    return [
        re.compile(r"<u>" + escaped_query + r"</u>", re.IGNORECASE),
        re.compile(r"<ins>" + escaped_query + r"</ins>", re.IGNORECASE),
    ]
```

Real annotation (`data/test/text_formatting.jsonl:1`):

```json
{"pdf": "docs/text/text_ocr__p4013.pdf", "id": "text_ocr__p4013_is_underline_0",
 "type": "is_underline", "rule": "{\"text\": \"LIGHT AIRCRAFT PHOTOGRAPHIC MODIFICATION.\"}"}
```

- **PASSES:** `<u>LIGHT AIRCRAFT PHOTOGRAPHIC MODIFICATION.</u>` — note the trailing period is part
  of the annotated text and must be inside the tag.
- **FAILS (what we ship today):** `LIGHT AIRCRAFT PHOTOGRAPHIC MODIFICATION. - Recommend that Army
  aircraft…` (verbatim from `output/kdl_frontier_nano/text/text_ocr__p4013.result.json`).

Measured behaviour table:

| content | result |
|---|---|
| `<u>Hello World</u>` | PASS |
| `<ins>Hello World</ins>` | PASS |
| `<U>Hello World</U>` | PASS |
| `**<u>Hello World</u>**` | PASS |
| `<u>*Hello World*</u>` | PASS |
| `# <u>Hello World</u>` | PASS (works inside a heading) |
| `<u>Hello</u> <u>World</u>` | PASS (word-by-word underlining) |
| `__Hello World__` | **FAIL** |
| `<span style="text-decoration:underline">Hello World</span>` | **FAIL** |
| `<u>Hello World.</u>` for query `Hello World` | **FAIL** |

Also verified against the real Swedish annotation `{"text": "upphävd genom:"}`
(`data/test/text_formatting.jsonl:36`): `<u>upphävd genom:</u>` → PASS.

### 2.2 `is_strikeout` — **`~~text~~`, `<s>`, `<del>`, or `<strike>`**

```python
# rules_formatting.py:250-259
@staticmethod
def _build_strikeout_patterns(escaped_query: str) -> list[re.Pattern]:
    """Detect ~~text~~ or <s>text</s> / <del>text</del> / <strike>text</strike>."""
    return [
        re.compile(r"~~" + escaped_query + r"~~", re.IGNORECASE),
        re.compile(
            r"<(?:s|del|strike)>" + escaped_query + r"</(?:s|del|strike)>",
            re.IGNORECASE,
        ),
    ]
```

Real annotations: `{"text": "CONFIDENTIAL"}` (`data/test/text_formatting.jsonl:3`),
`{"text": "Estevan, Sask.,"}` (`data/text_formatting.jsonl:377`).

| content | result |
|---|---|
| `~~CONFIDENTIAL~~` | PASS |
| `<s>CONFIDENTIAL</s>` / `<del>…</del>` / `<strike>…</strike>` | PASS |
| `~~Estevan, Sask.,~~` | PASS (punctuation inside is fine — it's part of the query) |
| `~~a~~ ~~b~~` for query `a b` | PASS |
| `\~\~gone\~\~` | PASS (escapes undone) |
| `~~CONFIDENTIAL extra~~` for query `CONFIDENTIAL` | **FAIL** (no filler allowed) |
| `~gone~` (single tilde) | **FAIL** |
| plain `CONFIDENTIAL` (what we ship) | **FAIL** |

### 2.3 `is_bold` — **`**text**`, `<b>text</b>`, *or any Markdown/HTML heading line containing the text***

```python
# rules_formatting.py:189-205
_not_bold_close = r"(?:(?!\*\*).)*?"
_not_b_close_tag = r"(?:(?!</b>).)*?"
return [
    re.compile(r"\*\*(?!\s)" + _not_bold_close + escaped_query + _not_bold_close + r"(?<!\s)\*\*",
               re.IGNORECASE | re.DOTALL),
    re.compile(r"<b>" + _not_b_close_tag + escaped_query + _not_b_close_tag + r"</b>",
               re.IGNORECASE | re.DOTALL),
    re.compile(r"^[ \t]*#{1,6}[ \t]+[^\n]*?" + escaped_query + r"[^\n]*?[ \t]*(?:#+[ \t]*)?$",
               re.IGNORECASE | re.MULTILINE),
]
```

The **third arm is the important one**: a `#`-heading line whose text contains the query counts as
bold. This is the entire reason `kdl_frontier_nano` scores 0.534 on `rule_is_bold_pass_rate` while
emitting only **one** `**` in 200 output files (§5).

| content | query | result |
|---|---|---|
| `**Population:** 2.5m` | `Population:` | PASS |
| `**Population:**` | `Population` | PASS (substring of bold span) |
| `# Population of city` | `Population` | PASS (heading arm) |
| `## The Overview of things` | `Overview` | PASS (query anywhere on the heading line) |
| `### Overview ###` | `Overview` | PASS (closing hashes tolerated) |
| `<b>Population</b>` | `Population` | PASS |
| `<strong>Population</strong>` | `Population` | **FAIL** — `<strong>` is not recognised |
| `__Population__` | `Population` | **FAIL** |

Two `**` spans on one line do not bleed into each other: the `(?:(?!\*\*).)*?` "tempered" filler
stops at the next `**`, so `**Name:** John **Age:**` does not make `John` test as bold
(docstring `rules_formatting.py:180-186`).

### 2.4 `is_italic` — **`*text*`, `_text_`, `<i>`, or `<em>`**

`rules_formatting.py:222-239`. Negative look-around excludes `**`/`__`.

| content | query | result |
|---|---|---|
| `*note*`, `_note_`, `<i>note</i>`, `<em>note</em>` | `note` | PASS |
| `**note**` | `note` | **FAIL** (correctly rejects bold-as-italic) |

Real annotation: `{"text": "(Formerly Link Intime India Private Limited)"}`
(`data/text_formatting.jsonl`, `text_dense__canara_is_italic_56`).

### 2.5 `is_sup` — **`<sup>text</sup>` or Unicode superscript characters. NOT LaTeX `^`.**

```python
# rules_formatting.py:268-273
@staticmethod
def _build_sup_patterns(escaped_query: str) -> list[re.Pattern]:
    """Detect <sup>text</sup>. Unicode superscripts handled separately."""
    return [
        re.compile(r"<sup>" + escaped_query + r"</sup>", re.IGNORECASE),
    ]
```

Unicode fallback (`rules_formatting.py:282-299`, char table at `:115`): a run of consecutive
superscript characters is NFKD-normalised to plain ASCII and the query must be a substring of it.

Real annotations: `{"text": "(1)"}` and `{"text": "(2)"}` (`data/text_formatting.jsonl:96`,
`text_dense__canara_is_sup_60/61`).

| content | query | result |
|---|---|---|
| `text<sup>(1)</sup>` | `(1)` | PASS |
| `note<sup>1</sup>` | `1` | PASS |
| `x²` | `2` | PASS (Unicode arm) |
| `note <sup> (1) </sup>` | `(1)` | **FAIL** — spaces inside the tag break it |
| `x^2^` | `2` | **FAIL** |
| `x$^2$` | `2` | **FAIL** |
| `$x^{2}$` | `2` | **FAIL** |

**This is the single biggest scoring lever (§7): +7.05 points.** 318 rules over 86 documents, and
our pipeline emits zero `<sup>`.

### 2.6 `is_sub` — **`<sub>text</sub>` or Unicode subscript characters**

`rules_formatting.py:275-280`; Unicode table at `:117`, fallback at `:301-315`.

| content | query | result |
|---|---|---|
| `H<sub>2</sub>O` | `2` | PASS |
| `H₂O` | `2` | PASS |
| `H<sub> 2 </sub>O` | `2` | **FAIL** (spaces) |
| `H~2~O` | `2` | **FAIL** |

### 2.7 `is_mark` — **bare `<mark>text</mark>`, with NO attributes**

```python
# rules_formatting.py:261-266
@staticmethod
def _build_mark_patterns(escaped_query: str) -> list[re.Pattern]:
    """Detect <mark>text</mark>."""
    return [
        re.compile(r"<mark>" + escaped_query + r"</mark>", re.IGNORECASE),
    ]
```

**Trap:** the pattern is the literal string `<mark>`, so an attributed tag fails.

| content | query | result |
|---|---|---|
| `<mark>6-11</mark>` | `6-11` | PASS |
| `<mark style="background-color: yellow">6-11</mark>` | `6-11` | **FAIL** for `is_mark` |
| `==6-11==` | `6-11` | **FAIL** |
| `# <mark>3. Scope of Work</mark>` | `3. Scope of Work` | PASS |
| `<mark># 3. Scope of Work</mark>` | `3. Scope of Work` | **FAIL** (the `#` is inside the tag) |

Whereas `mark_color` **requires** attributes (`rules_formatting.py:440-456`):
`<mark style="background-color: yellow">6-11</mark>` → PASS; bare `<mark>6-11</mark>` → FAIL.
The two are mutually exclusive on a single tag. Fortunately **no `mark_color` rules exist in the
shipped data**, so the correct output is the bare `<mark>`. Real annotation:
`{"text": "6-11"}` (`data/test/text_formatting.jsonl:25`).

### 2.8 `is_title` — **`#`…`######` heading starting with the text, `<h1>`–`<h6>`, or a whole line that is exactly bold**

Patterns at `rules_formatting.py:743-760`; fallback normalised comparison at `:771-778` using
`_extract_title_events` (`:648-705`), which also treats a standalone bold line as a title at
synthetic level 7.

| content | query | result |
|---|---|---|
| `## Overview` | `Overview` | PASS |
| `## Overview of things` | `Overview` | PASS (heading may continue after the text) |
| `## The Overview` | `Overview` | **FAIL** — heading must *start* with the text (`^#{1,6}\s+` + query) |
| `<h3>Overview</h3>` | `Overview` | PASS (any level; `level` is ignored) |
| `**Overview**` alone on its line | `Overview` | PASS |
| `**Overview** and more text` | `Overview` | **FAIL** — bold-title arm is line-anchored `^…$` |
| `Overview` + `--------` (setext underline) | `Overview` | **FAIL** — setext headings are not parsed |

Real annotations: `{"text": "BAOTOU 包头", "level": 1}` (`data/text_formatting.jsonl:1`),
and from our failing slice `{"text": "► B KOMMISSIONENS BESLUT"}` — which we emitted as plain body
text (`_evaluation_report.json`: *"Expected '► B KOMMISSIONENS BESLUT' to be a title, but no
matching heading or bold formatting found"*).

### 2.9 `title_hierarchy_percent` — heading levels must strictly deepen down the tree

Real annotation (`data/text_formatting.jsonl:9`):

```json
{"title_hierarchy": {"BAOTOU 包头": {"Population:": {}, "Province:": {},
 "Major Ethnic Groups:": {}, "Christians:": {}, "Status of Evangelization": {},
 "Pray for Baotou": {}, "Overview of Baotou": {}}}}
```

Constraint set is built at `rules_formatting.py:803-871`; scoring at `:873-925`:

```python
total_constraints = len(expected_titles) + len(edges)
...
for parent, child, require_deeper_level in edges:
    ...
    order_ok = parent_pos < child_pos
    depth_ok = parent_level < child_level if require_deeper_level else True
```

- **PASSES:** `# BAOTOU 包头` followed by `## Population:`, `## Province:`, … in the annotated order.
  Verified: a three-level `# / ## / ###` nest scored 1.000.
- **FAILS:** all children at the same level as the parent, or a child appearing above its parent, or
  a title emitted as plain text. Our real failure
  (`output/kdl_frontier_nano/text_formatting/_evaluation_report.json`): *"Title hierarchy
  score=0.250; missing title 'av den 16 januari 1997'; missing title 'om godkannande av metoder…'"*
- Note titles are normalised for comparison (`_normalize_title_label` →
  `metrics/parse/utils.py:normalize_text`), which folds case, quotes, fullwidth punctuation and
  accents — hence `godkännande` compared as `godkannande` in the message above.

### 2.10 `is_latex` — a `$…$`, `$$…$$`, `\(…\)` or `\[…\]` delimited formula, compared with all whitespace removed

Extraction `rules_formatting.py:497-510`; normalisation `:477-494` (strip delimiters, unescape HTML
entities, delete **all** whitespace); comparison `:532-534`.

| content | annotated `formula` | result |
|---|---|---|
| `$a^2 + b^2 = c^2$` | `a^2+b^2=c^2` | PASS (whitespace-insensitive) |
| `$$a^2+b^2=c^2$$` | `a^2+b^2=c^2` | PASS |
| `\(a^2+b^2=c^2\)` | same | PASS |
| `\[a^2+b^2=c^2\]` | same | PASS |
| `a^2+b^2=c^2` (no delimiters) | same | **FAIL** — delimiters are mandatory |
| `$a^{2}+b^{2}=c^{2}$` | `$a^2+b^2=c^2$` | **FAIL** — brace style must match exactly |

The matcher is a **set-membership test on exact normalised strings**, so `{2}` vs `2`, `\times` vs
`\cdot`, `\dfrac` vs `\frac` all fail. There is an explicit diagnostic for pipelines that replace
formulas with a placeholder before evaluation (`rules_formatting.py:539-544`).

Beware the annotations here: several `is_latex` records are not mathematics at all, e.g.
`{"formula": "136,977.71, as of January 18, 2012, together with interest accrued to January 18,
2012 in the amount of"}` (`data/text_formatting.jsonl:151`) — an annotator artifact where a
`$`-delimited currency run was captured as a formula. Passing those means emitting
`$136,977.71, as of January 18, 2012, …$`, which is not sane output. Treat `is_latex` headroom as
partly unreachable.

### 2.11 `is_code_block` — fenced block with a matching language tag

`rules_formatting.py:556-567` (extraction), `:598-622` (comparison).

| content | rule | result |
|---|---|---|
| ` ```python\nx = 1\n``` ` | `{"language":"python","code":"x = 1"}` | PASS |
| ` ```Python\nx  =  1\n``` ` | same | PASS (language lower-cased; whitespace collapsed) |
| ` ```\nx = 1\n``` ` | same | **FAIL** — the language tag is required |

Real annotation (`data/text_formatting.jsonl:730`): `{"language": "python", "code": "self.mm_list =
sorted([x for x in self.files_list if str(x).endswith('_mm.tif')])\n…"}`.

---

## 3. How the dimension score aggregates

Three stages. All of it lives in `evaluators/parse.py` (per document) and `runner.py` (across
documents).

### Stage 1 — per rule type, within one document (`evaluators/parse.py:268-285`)

```python
per_type_avg: dict[str, float] = {}
for rule_type, type_results in rule_types.items():
    total = len(type_results)
    score_sum = sum(r.get("score", 1.0 if r.get("passed", False) else 0.0) for r in type_results)
    pass_rate = score_sum / total if total > 0 else 0.0
    per_type_avg[rule_type] = pass_rate
```

Graduated rules (`title_hierarchy_percent`) contribute their fractional score, not 0/1.

`rule_pass_rate` for the document is the mean score over **all** its rules regardless of type
(`metrics/parse/rule_based_metric.py:265-268`):

```python
total_score = 0.0
for r in rule_results:
    total_score += float(r["score"])
pass_rate = total_score / total if total > 0 else 0.0
```

### Stage 2 — category scores, within one document

**Which types belong to which category** (`evaluators/parse.py:344-380`):

```python
_TEXT_STYLING_PAIRS = [
    ("is_bold", "is_not_bold"),
    ("is_strikeout", "is_not_strikeout"),
    ("is_sup", "is_not_sup"),
    ("is_sub", "is_not_sub"),
]
...
_TITLE_TYPES = {"is_title", "title_hierarchy_percent"}
_CODE_BLOCK_TYPES = {"is_code_block"}
_LATEX_TYPES = {"is_latex"}
```

**`is_underline`, `is_italic`, `is_mark`, `mark_color` appear in NO category.** This is the single
most consequential fact in this report. Confirmed empirically by our own result file — for
`text/text_ocr__p4013`, which has 2 `is_underline` rules and 1 `is_strikeout` rule, the
`normalized_text_styling` metadata reads:

```json
{"num_pos_rules": 1, "num_neg_rules": 0, "pos_score": 0.0, "neg_score": 1.0,
 "included_types": ["is_strikeout"], "per_type_scores": {"is_strikeout": 0.0}}
```

Only `is_strikeout` was included; both underline rules were discarded from the score.

**`normalized_text_styling`** is *not* a mean of per-type averages despite the code comment. It
pools **individual rules** across the four positive types and combines with the negative pool using
a weighted harmonic mean with `beta = 0.5` (`evaluators/parse.py:389-411`):

```python
pos_rules = [r for r in rule_results if r.get("type") in _TEXT_STYLING_POS_TYPES]
neg_rules = [r for r in rule_results if r.get("type") in _TEXT_STYLING_NEG_TYPES]
...
pos_score = sum(_rule_score(r) for r in pos_rules) / len(pos_rules) if pos_rules else 1.0
neg_score = sum(_rule_score(r) for r in neg_rules) / len(neg_rules) if neg_rules else 1.0
beta = 0.5
if pos_score + neg_score > 0:
    cat_value = (1 + beta**2) * pos_score * neg_score / (beta**2 * pos_score + neg_score)
```

Because **no `is_not_*` rules exist in the data**, `neg_score` is always the default `1.0`, so this
reduces to a fixed monotone boost of the positive rate:

```
normalized_text_styling = 1.25 · pos / (0.25 · pos + 1)
```

e.g. `pos = 0.25 → 0.2941` (matches our `text_simple__results` result exactly), `pos = 0.8182 →
0.8491` (matches `text_simple__edited`). Consequence: within styling, **`is_bold` dominates by rule
count** — 2066 bold rules vs 318 sup, 44 strikeout, 14 sub.

**All other categories** are the plain mean of the per-type averages present
(`evaluators/parse.py:430-432`):

```python
cat_scores = [per_type_avg[t] for t in type_set if t in per_type_avg]
if cat_scores:
    cat_value = sum(cat_scores) / len(cat_scores)
```

So `normalized_title_accuracy = (rule_is_title_pass_rate + rule_title_hierarchy_percent_pass_rate)
/ 2` when both are present.

### Stage 3 — the headline, within one document (`evaluators/parse.py:511-539`)

```python
_FORMATTING_WEIGHTS: dict[str, float] = {
    "normalized_text_styling": 1.0,
    "normalized_title_accuracy": 1.0,
    "normalized_latex": 1.0 / 5.0,
    "normalized_code_block": 1.0 / 5.0,
}
...
for cat_name, weight in _FORMATTING_WEIGHTS.items():
    if cat_name in _cat_values:
        fmt_weighted_sum += _cat_values[cat_name] * weight
        fmt_weight_sum += weight
...
fmt_value = fmt_weighted_sum / fmt_weight_sum
```

**Absent categories are dropped from both numerator and denominator** — a document with no LaTeX
rules is not penalised. Verified in our results: `text_simple__edited` shows
`"weights": {"normalized_text_styling": 1.0, "normalized_title_accuracy": 1.0}, "weight_sum": 2.0`.

`normalized_text_score` (`evaluators/parse.py:451-479`) is a *different*, broader combination that
also folds in `normalized_text_correctness` and `normalized_order` at weight 1.0 each. In the
`text_formatting` group there are no correctness/order rules, so
`normalized_text_score == semantic_formatting` numerically — which is exactly what our aggregate
shows (`avg_normalized_text_score == avg_semantic_formatting == 0.36182533810169765`). Do not
confuse them: on the `text_content` group they diverge.

### Stage 4 — across documents (`runner.py:1252-1256`)

```python
for metric_name, values in metric_values.items():
    if values:
        aggregate[f"avg_{metric_name}"] = sum(values) / len(values)
        aggregate[f"min_{metric_name}"] = min(values)
        aggregate[f"max_{metric_name}"] = max(values)
```

**Plain unweighted macro average over documents.** A document with 3 rules counts as much as one
with 200. Documents that *errored* are padded in with a synthetic `0.0`
(`runner.py:1240-1248`), so a pipeline that crashes on a page is penalised rather than excused.
`micro_rule_pass_rate` (`runner.py:1259-1265`) pools raw pass counts and is reported but is not the
headline.

**Answer to the question as asked:** the dimension score is a **macro (per-document) mean of a
per-document weighted mean of category scores**, where the styling category is itself a
micro-average over individual styling rules passed through an F-0.5 transform. It is *not* a flat
mean of rule pass rates and *not* micro-averaged over rules.

---

## 4. Why underline and strikeout score exactly 0.00

Three separate findings; the first is the answer, the second is the reason it also doesn't matter
much, the third is a housekeeping note.

### 4.1 The model emits no styling markers at all — measured, not inferred

Scanning the `markdown` field of all 200 `output/kdl_frontier_nano/text/*.result.json` files:

```
files scanned: 200
<u>                    occurrences=     0  files_containing=0
<ins>                  occurrences=     0  files_containing=0
~~                     occurrences=     0  files_containing=0
<s>/<del>/<strike>     occurrences=     0  files_containing=0
<mark                  occurrences=     0  files_containing=0
<sup>                  occurrences=     0  files_containing=0
<sub>                  occurrences=     0  files_containing=0
**bold**               occurrences=     1  files_containing=1
heading#               occurrences=  1291  files_containing=184
$latex$                occurrences=    34  files_containing=13
```

So: **not a wrong-marker problem, not a matcher problem — the pipeline produces nothing to match.**
`is_underline`, `is_strikeout`, `is_mark`, `is_sup` and `is_sub` are all structurally 0.00 for this
pipeline, on every document, by construction.

A corollary worth internalising: `rule_is_bold_pass_rate = 0.534` is earned **almost entirely
through the heading arm** of the bold matcher (`rules_formatting.py:201-204`) — 1291 `#` headings vs
1 `**`. The pipeline is being credited for bold it never emitted.

Concrete evidence for one page. Annotation
(`data/test/text_formatting.jsonl:1-3`) asks for underline on
`LIGHT AIRCRAFT PHOTOGRAPHIC MODIFICATION.` and `QM BATH UNITS SOUGHT AS BRIDGE BUILDING
EQUIPMENT.`, and strikeout on `CONFIDENTIAL`. The output
(`output/kdl_frontier_nano/text/text_ocr__p4013.result.json`, `output.markdown`) contains the text
verbatim and unstyled:

```
LIGHT AIRCRAFT PHOTOGRAPHIC MODIFICATION. - Recommend that Army aircraft organic to the
infantry division be modified and additional photographic equipment authorized …

# UNCLASSIFIED
```

— and the word `CONFIDENTIAL` does not appear at all (the page's classification banner was read as
`UNCLASSIFIED` / `(RESTRICTED)`), so even correct `~~` markup would need correct OCR first.

### 4.2 Underline is excluded from the score anyway

Per §3 Stage 2: `is_underline` is in no `_NORMALIZED_CATEGORIES` set. I verified by simulation over
all 476 documents in `data/text_formatting.jsonl` (§7): moving `is_underline` from 0.0 to 1.0
changes the dimension score by **+0.00**. Same for `is_italic` and `is_mark`. Fixing underline
raises `avg_rule_is_underline_pass_rate` and `avg_rule_pass_rate` only — neither is the published
column.

### 4.3 A gap in the run we should note

`output/kdl_frontier_nano/text_formatting/_evaluation_report.json` covers only **3 documents**
(`total_examples: 3`), against a full dimension of 476. The directory has no per-file
`*.result.json` at all, and `_evaluation_rule_results.csv` is 0 bytes. The per-file artifacts for
this dimension live in `output/kdl_frontier_nano/text/` (the test IDs are `text/…`, so the inference
outputs are keyed by the `text` group, shared with `text_content`). Our 0.3618 local number is
therefore **not comparable** to the published 66.81; it is a 3-document sample. The published 66.81
for `KDL-Frontier-Parser-nano` comes from `leaderboard.csv:77`, not from this run.

---

## 5. The `chart` dimension, briefly

### 5.1 Composition

`data/chart.jsonl` is **100% `chart_data_point`** — 4,864 rules, all one type (verified by census).
The Charts column therefore reduces to `avg_rule_pass_rate` over chart documents; there is no
chart-specific entry in `_DEFAULT_METRICS` (`analysis/aggregation_report.py:36-42`) so the dashboard
falls back to `rule_pass_rate` (`:67-74`). `README.md:104` names the metric
"ChartDataPointMatch". Our local aggregate confirms
`avg_rule_chart_data_point_pass_rate == avg_rule_pass_rate == 0.5`.

Record shape (`data/chart.jsonl:1`):

```json
{"pdf": "docs/chart/(Web_version)_E-Government_Survey_2024_1392024_p101.pdf",
 "category": "chart", "id": "b17e5e98d6fc2763", "type": "chart_data_point",
 "rule": "{\"labels\": [\"IF\", \"193 UN Member States\"], \"max_diffs\": 0,
           \"normalize_numbers\": true, \"value\": \"0.8079\"}"}
```

`labels` is typically `[category-axis label, series label]`. Defaults:
`normalize_numbers = True`, `relative_tolerance = 0.01`, `max_diffs = 0`
(`test_cases/parse_rule_schemas.py:368-373` and `:46`).

### 5.2 What `ChartDataPointRule` requires

**A parsed table is mandatory.** `rules_chart.py:495-509`:

```python
def run(self, content: str, normalized_content: str | None = None) -> tuple[bool, str, float]:
    """Check if value is associated with all labels in any table."""
    tables_to_check = []
    md_tables = parse_markdown_tables(content)
    tables_to_check.extend(md_tables)
    html_tables = parse_html_tables(content)
    tables_to_check.extend(html_tables)
    if not tables_to_check:
        return False, "No tables found in content", 0.0
```

Verified: prose (`"In 2015 OECD invested 7200…"`), a bullet list (`"- 2015 OECD: 7200"`) and a JSON
code block all return **FAIL — "No tables found in content"**. Only a Markdown pipe table or an HTML
`<table>` counts.

Then, in order:

1. **Find the value in some cell.** `rules_chart.py:249-272` — fuzzy string match at threshold
   `max(0.5, 1 - max_diffs/len(value))`, OR numeric match through `numbers_match`
   (`:124-157`) with `relative_tolerance`. Number parsing (`:36-101`) strips `$ € £ ¥`, `~ ≈`, `%`,
   thousands separators and spaces, and **applies k/M/B/T multipliers**. Caveat measured: expected
   `7.2` vs cell `7.2k` **FAILS**, because `7.2k` normalises to `7200`. Emit the magnitude the chart
   displays; do not abbreviate a plain number, and do not spell out an abbreviated one.
2. **Phase 1 — every label must be associated with that cell** by appearing in the **same row or the
   same column** (or in a tracked colspan/rowspan header) (`rules_chart.py:312-368`). Label match is
   `fuzz.partial_ratio` at the same threshold, or an alphanumeric-only substring test
   (`:330-336`).
3. **Phase 2 — labels not found in the table may be satisfied from `context_before`**, but only
   as **formatted** text: a Markdown `#`-heading, `**bold**`, an HTML `<h1>`–`<h6>`, or
   `<strong>`/`<b>` (`_extract_formatted_labels`, `rules_chart.py:370-394`, matched at full-string
   ratio ≥ 0.60, `:434-461`), or a `<caption>` / heading via
   `_is_label_in_heading_or_caption` (`:463-493`). Plain paragraph text does **not** qualify.
4. `context_before` is 5 preceding lines for a Markdown table
   (`table_parsing.py:173`) or up to 3 previous siblings capped at the last 300 characters for an
   HTML table, with any `<caption>` prepended (`table_parsing.py:366-392`).
5. **Both orientations are tried** for the array-style rules (`rules_chart.py:1279`), and
   `_check_label_association` searches row *and* column, so a row-oriented or column-oriented table
   both work. Verified: a transposed table (`| Series | 2015 | 2021 |` / `| OECD | 7200 | 10500 |`)
   passes for `value=7200, labels=["2015","OECD"]`.

### 5.3 Our real chart failure, and its fix

`output/kdl_frontier_nano/chart/ADL_Future_of_automotive_mobility_2024_1_p17.result.json` scored
**0/8**. Every message is the same shape:

> `Value found but labels not associated: Value at (1, 1) missing labels: ['favorable attitude'] (data labels ['global'] in table, title labels [] in context)`

The output emitted (verbatim, abridged):

```html
# Figure 10. Desire to use autonomous/semiautonomous cars
...
<table>
<thead><tr><th>Region</th><th>Value</th></tr></thead>
<tbody>
<tr><td>Global</td><td>16</td></tr>
<tr><td>Europe</td><td>-17</td></tr>
...
<tr><td>Favorable attitude, Unfavorable attitude</td><td></td></tr>
</tbody>
</table>
```

The two series were collapsed into a generic `Value` column, and the legend was dumped as a
data row. The annotations (`data/test/chart.jsonl:11,16`) demand
`{"value":"16","labels":["Global","Favorable attitude"]}` and
`{"value":"-17","labels":["Europe","Unfavorable attitude"]}`.

I tested four candidate output shapes against those two real rules. Results:

| output shape | result |
|---|---|
| **A. series names as column headers** (`\| Region \| Favorable attitude \| Unfavorable attitude \|`) | **PASS, PASS** |
| **B. HTML `<table>` with `<caption>` naming the series** | PASS, PASS |
| **C. long/tidy form**, explicit `Series` column (`\| Region \| Series \| Value \|`) | **PASS, PASS** |
| **D. one table per series, each under its own `##` heading** | PASS, PASS |
| **E. as-shipped** (`Value` header, no series anywhere) | **FAIL, FAIL** |

**Rule of thumb: never emit a column called `Value`. Every series must be nameable from the table
itself (header cell or a `Series` column), because context matching only works for headings, bold
and captions and is fragile.** Shape A (wide, series as headers) or C (tidy, explicit series column)
are the safe choices.

The other two chart documents in our slice show the two remaining failure modes: 5/5 pass when the
table has proper headers, and `05021ff2-en_p19` scores 5/10 with *"Value '44' not found in any
table"* — a second chart on the page was not converted to a table at all.

---

## 6. Target output spec — a worked example

The following Markdown was **run through the real matchers** and passes every rule type listed
after it (all 16 assertions PASS; nothing was tuned by trial and error beyond the two corrections
noted below).

````markdown
# Quarterly Pricing Notice

## Section 3. Revised Schedule

The <u>authorised representative</u> must countersign. The former price
~~USD 1,250.00~~ is superseded by **USD 1,180.00** as of 1 April 2026.<sup>3</sup>

**Definitions.**

*Eligible Party* means any entity listed in Annex A.<sup>(1)</sup>

Dissolved oxygen is reported as O<sub>2</sub> saturation.

The <mark>renewal window</mark> closes on 30 June.

The premium is computed as $P = \frac{L \times E}{1 - C}$.

```python
premium = (loss * exposure) / (1 - commission)
```

### Figure 4. Net favourability by region

| Region | Favorable attitude | Unfavorable attitude |
| --- | --- | --- |
| Global | 16 | -8 |
| Europe | 12 | -17 |
````

Verified passing assertions:

| rule | payload | result |
|---|---|---|
| `is_title` | `{"text":"Quarterly Pricing Notice","level":1}` | PASS |
| `is_title` | `{"text":"Section 3. Revised Schedule","level":2}` | PASS |
| `is_title` | `{"text":"Definitions."}` | PASS |
| `title_hierarchy_percent` | `{"Quarterly Pricing Notice":{"Section 3. Revised Schedule":{"Figure 4. Net favourability by region":{}}}}` | PASS (1.000) |
| `is_bold` | `{"text":"USD 1,180.00"}` | PASS |
| `is_bold` | `{"text":"Revised Schedule"}` (heading arm) | PASS |
| `is_italic` | `{"text":"Eligible Party"}` | PASS |
| `is_underline` | `{"text":"authorised representative"}` | PASS |
| `is_strikeout` | `{"text":"USD 1,250.00"}` | PASS |
| `is_sup` | `{"text":"3"}` | PASS |
| `is_sup` | `{"text":"(1)"}` | PASS |
| `is_sub` | `{"text":"2"}` | PASS |
| `is_mark` | `{"text":"renewal window"}` | PASS |
| `is_latex` | `{"formula":"P = \\frac{L \\times E}{1 - C}"}` | PASS |
| `is_code_block` | `{"language":"python","code":"premium = (loss * exposure) / (1 - commission)"}` | PASS |
| `chart_data_point` | `{"value":"16","labels":["Global","Favorable attitude"]}` | PASS |
| `chart_data_point` | `{"value":"-17","labels":["Europe","Unfavorable attitude"]}` | PASS |

Two corrections I had to make while validating, both worth encoding as generation rules:

1. `**Definitions.** *Eligible Party* means …` on one line **fails** `is_title` — the bold-title arm
   is line-anchored (`rules_formatting.py:753-756`). A run-in bold lead-in must be given its own
   line to count as a title.
2. `<mark style="background-color: yellow">…</mark>` **fails** `is_mark`. Use a bare `<mark>`.

### 6.1 Distilled generation rules

Emit, always:

- `<u>…</u>` for underline; the tag must contain **exactly** the underlined run, punctuation included.
- `~~…~~` for strikethrough (`<s>` / `<del>` / `<strike>` also accepted).
- `<sup>…</sup>` / `<sub>…</sub>` with **no spaces inside the tags**; Unicode `²` / `₂` also count.
  Never LaTeX `^`/`_` for a visual super/subscript.
- `**…**` for bold; **never `<strong>`, never `__…__`**.
- `*…*` or `_…_` or `<i>`/`<em>` for italic.
- Bare `<mark>…</mark>` for highlight, no attributes.
- ATX `#`-headings (`# … ######`), one level deeper per nesting step, in document order; never setext
  (`===` / `---`) underlines. A heading must **begin** with the title text.
- Standalone bold lines for sub-headings the layout renders in bold rather than as a heading.
- `$…$` (inline) or `$$…$$` (block) around formulas, preserving the source's brace style.
- Fenced code with an explicit lowercase language tag.
- Charts as Markdown pipe tables or HTML `<table>`, with **series names as column headers** (or an
  explicit `Series` column), values in the magnitude the chart displays, and the figure title as a
  `#`-heading or `<caption>` immediately above the table.

Avoid:

- Plain text where the source shows styling (the current failure mode).
- A generic `Value` column for chart series.
- Attributes on `<mark>`; spaces inside `<sup>`/`<sub>`; `<strong>`; `__underline__`;
  `<span style="text-decoration:underline">`; `==highlight==`; `^sup^`/`~sub~`.
- Wrapping extra words inside `<u>`/`~~`/`<sup>`/`<sub>`/`<mark>` beyond the styled run.

---

## 7. Where the points actually are (measured headroom)

Simulation over all 476 documents in `data/text_formatting.jsonl`, reimplementing the exact
aggregation from `evaluators/parse.py:344-539` and `runner.py:1252-1256`. Method: hold
`is_bold` and the two title types at a single calibrated pass rate `x` and set everything else to 0,
solve for `x` such that the macro mean equals the published 66.81 (`leaderboard.csv:77`) — this
gives `x = 0.7294` — then flip one rule type at a time to a perfect 1.0 and re-measure.

| change | resulting Semantic Formatting | delta |
|---|---|---|
| calibrated baseline | 66.81 | — |
| `is_sup` → 1.0 | 73.86 | **+7.05** |
| `is_latex` → 1.0 | 68.25 | +1.44 |
| `is_strikeout` → 1.0 | 68.18 | +1.37 |
| `is_code_block` → 1.0 | 67.35 | +0.54 |
| `is_sub` → 1.0 | 66.99 | +0.18 |
| all five together | 77.38 | **+10.57** |
| `is_underline` → 1.0 | 66.81 | **+0.00** |
| `is_italic` → 1.0 | 66.81 | **+0.00** |
| `is_mark` → 1.0 | 66.81 | **+0.00** |

Reading: **superscript is the prize.** 318 rules across 86 of 476 documents, currently zero, and
the fix is mechanical — emit `<sup>` for footnote markers and ordinal/reference superscripts.
Strikeout and subscript are cheap wins but small (13 and 6 documents). Underline, italic and mark
are worth zero on this column no matter how well we do them (they do move `avg_rule_pass_rate`,
which is not published for this dimension).

Also note 19 of the 476 documents (476 − 457 scored in simulation) carry **only** unscored rule
types and produce no `semantic_formatting` value at all; they are silently absent from the mean.

Remaining headroom beyond these five sits in `is_bold` (2066 rules, 327 documents) and the two title
types (1872 + 402 rules, 402 documents) — both already partially earned, both weighted 1.0, and
together they are ~90% of the metric's mass.

---

## 8. Things I could not determine, and cautions

1. **The exact statistic behind the published `Semantic_Formatting` column is inferred, not
   verified.** The repo maps `text_formatting → semantic_formatting` for its own dashboard
   (`analysis/aggregation_report.py:40`) and `text_formatting → Semantic_Formatting` for the
   Hugging Face sync (`scripts/sync_hf_leaderboard.py:40`), but the code that *writes*
   `.eval_results/parsebench.yaml` — the file the sync script reads the `value` from — is **not in
   this repository** (only the URLs are, `sync_hf_leaderboard.py:32-33`). I am inferring
   `avg_semantic_formatting × 100`. Consistency with the observed value gives some confidence but
   this is not proof.
2. **Our local numbers are from a 3-document slice, not the benchmark.** The
   `output/kdl_frontier_nano/text_formatting/` report covers `total_examples: 3` of 476 and has no
   per-file results (§4.3). Local `semantic_formatting = 0.3618` should not be compared to 66.81.
3. **The `is_latex` headroom is partly unreachable.** Several annotations capture prose that
   happened to sit between two `$` currency signs (`data/text_formatting.jsonl:151`). Passing them
   requires emitting nonsense. The +1.44 in §7 is an upper bound.
4. **I did not read the source PDFs.** I cannot confirm that a given `is_underline` or `is_sup`
   annotation is visually correct — only what the scorer demands. For `text_ocr__p4013`, the
   `is_strikeout` target `CONFIDENTIAL` does not appear in our output at all, which suggests the
   annotation refers to a banner our OCR read differently; some fraction of these rules may be
   unreachable for reasons other than markup.
5. **`_evaluation_rule_results.csv` for `text_formatting` is empty (0 bytes)** in this run. I read
   rule-level detail out of `_evaluation_report.json` instead. I did not investigate why the CSV is
   empty.
6. I did not examine the LLM-judge path (`metrics/parse/rule_based_judge_metric.py`,
   `metrics/parse/llm_normalization/`). Our report JSON contains no `rule_pass_rate_judge` metric,
   so it was inactive for this run, but I have not confirmed it is inactive by default or that it
   never touches formatting rules.
7. `max_diffs` defaults to 0 for formatting rules and is not used by the formatting matchers at all
   (only by the chart and table matchers). If future annotations set it on a formatting rule it will
   be silently ignored. Not a current issue; flagging in case it changes.

---

## Appendix — files read

Evaluation code:
- `src/parse_bench/evaluation/metrics/parse/rules_formatting.py` (all 1012 lines)
- `src/parse_bench/evaluation/metrics/parse/rules_chart.py` (all 1363 lines)
- `src/parse_bench/evaluation/metrics/parse/rules_base.py` (all 614 lines)
- `src/parse_bench/evaluation/metrics/parse/rule_based_metric.py:120-280`
- `src/parse_bench/evaluation/metrics/parse/table_parsing.py:55-75, 165-235, 355-425`
- `src/parse_bench/evaluation/metrics/parse/test_types.py:53-75`
- `src/parse_bench/evaluation/metrics/parse/utils.py:1-60`
- `src/parse_bench/evaluation/evaluators/parse.py:200-540`
- `src/parse_bench/evaluation/runner.py:1125-1290`
- `src/parse_bench/evaluation/metric_aggregation.py` (all 43 lines)
- `src/parse_bench/test_cases/parse_rule_schemas.py:40-52, 364-445`
- `src/parse_bench/analysis/aggregation_report.py:1-80`
- `src/parse_bench/analysis/metric_definitions.py:150-280`
- `scripts/sync_hf_leaderboard.py:1-120`

Data:
- `data/text_formatting.jsonl` (5997 rules, 476 documents) and `data/test/text_formatting.jsonl` (36)
- `data/chart.jsonl` (4864 rules) and `data/test/chart.jsonl` (23)
- `apps/annotator/rule_definitions.json` (field schemas only; contains no markup guidance)
- `README.md:99-117`, `leaderboard.csv`

Results:
- `output/kdl_frontier_nano/text_formatting/_evaluation_report.json`
- `output/kdl_frontier_nano/chart/_evaluation_report.json`
- `output/kdl_frontier_nano/text/*.result.json` (all 200, scanned for markers)
- `output/kdl_frontier_nano/chart/ADL_Future_of_automotive_mobility_2024_1_p17.result.json`
- `output/kdl_frontier_nano/text/text_ocr__p4013.result.json`
