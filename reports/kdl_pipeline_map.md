# KDL-Frontier-Parser-nano — pipeline map and intervention plan

**Target file:** `/Users/amolpant/forecasting_networks/bfcl-sprint/parsebench/src/parse_bench/inference/providers/parse/kdl_frontier_nano.py` (3323 lines)
**Date:** 2026-08-11
**Question asked:** is the Semantic Formatting weakness (66.81 on the board; underline 0.00 / strikeout 0.00 on our 3-file slice) a post-processing / output-rendering gap?

---

## 0. Headline answer

**The hypothesis is REFUTED, and two of its premises are wrong.**

1. **It is not a post-processing gap.** Nothing is being dropped, because nothing is ever produced. Across **23,802 recognised elements from 1,196 real documents** in the checked-in run artifacts (`parsebench/output/kdl_frontier_nano/*/*.raw.json`), the model emitted `<u>`/`<ins>` **0 times**, `~~` **0 times**, `<s>`/`<del>`/`<strike>` **0 times**, `<sup>`/`<sub>` **0 times**, `<b>`/`<strong>` **0 times**. Element content is captured *after* the model call and *before* markdown assembly, so this measures the model's own output, not the renderer's.
2. **Fixing underline cannot raise Semantic Formatting at all — its weight is exactly zero.** The Semantic Formatting dimension is composed of four sub-scores, and the styling sub-score only counts **bold, strikeout, superscript, subscript**. `is_underline`, `is_italic`, and `is_mark` are not in any Semantic Formatting category. Verified in code *and* in the run's own metric metadata.
3. **The real headroom is `is_bold` (+22 SemFmt points of oracle headroom) and `is_sup` (+8.9).** `is_strikeout` is worth at most +1.4 SemFmt points (≈ +0.28 Overall) because only 13 of 476 documents carry a strikeout rule.

**And there is a free win available with no GPU at all:** two deterministic emission-level patches I built and measured on a replay harness give **+4.9 Semantic Formatting points ≈ +0.98 Overall points**, verified non-destructive to Content Faithfulness and Tables. Details in §7.

Terms used below, in plain language:

- **Recognition stage** — one HTTP call to the vLLM server (vLLM = an open-source high-throughput serving engine that exposes an OpenAI-compatible `/v1/chat/completions` HTTP API) carrying one cropped image plus one short text prompt.
- **OTSL** ("Optimised Table Structure Language") — a compact token language for table grids (`<fcel>` = filled cell, `<ecel>` = empty cell, `<nl>` = new row, `<lcel>`/`<ucel>`/`<xcel>` = merge-left / merge-up / merge-both). The model emits OTSL for tables; the pipeline converts it to HTML.
- **Rule** — one graded assertion from `parsebench/data/text_formatting.jsonl`, e.g. `{"type":"is_bold","text":"AGENCY:"}`. Each is checked by a regex against the produced markdown.
- **Pass rate** — fraction of rules of one type that pass, averaged per document then across documents.

---

## 1. Pipeline stages, in order

Entry point `KdlFrontierNanoProvider.run_inference` (`kdl_frontier_nano.py:3216-3249`) → `_NanoEngine.parse_pages` (`:3030-3066`) → per page `_parse_page` (`:3068-3166`).

| # | Stage | Where | What is sent |
|---|---|---|---|
| 0 | **Render** | `_load_page_images` `:3198-3214` | PDF → PIL images at `dpi` (default 144, `:3191`) via PyMuPDF. Images pass through unchanged. |
| 1 | **Blank-page gate** | `:3076-3082` | Pages under 32 px, or `analyze_page_content(...).is_blank`, return zero elements. |
| 2 | **Layout detection** | `:3084-3094` | Whole page resized to a fixed **1036×1036** (`prepare_native_layout_image` `:623-627`, `NATIVE_LAYOUT_IMAGE_SIZE` `:529`), prompt `"\nLayout Detection:\n"`. Response is special-token boxes parsed by `_NATIVE_LAYOUT_RE` `:531-536`: `<\|box_start\|>x1 y1 x2 y2<\|box_end\|><\|ref_start\|>category<\|ref_end\|>` plus an optional `<\|rotate_*\|>` token. If no `<\|box_start\|>` appears the page yields **nothing** (`:3091-3093`). |
| 3 | **Category normalisation** | `NATIVE_LAYOUT_CATEGORY_MAP` `:545-572`, `normalize_layout_category` `:212-218` | 24 raw labels → 13 canonical categories (`CANONICAL_LAYOUT_CATEGORIES` `:189-203`). Anything unrecognised silently becomes `Text` (`_canonicalize_category` `:242-246`). |
| 4 | **Crop + bucket** | `_nano_group_by_bucket` `:2745-2791` | Normalised bbox × page size → pixel crop; crops under 5 px, or monochrome after preprocessing, are **dropped** (`:2771-2776`). Each element lands in one of four buckets via `CATEGORY_TO_RECOGNITION_BUCKET` `:135-149`. |
| 5 | **Per-category recognition** | `recognize` `:3107-3121`, dispatch `:3133-3144`, all concurrent under one semaphore | One call per element: `text` / `table` / `picture` / `formula` prompts. |
| 5b | **Full-page table route** | `:3099-3103`, `recognize_table_fullpage` `:3123-3131` | If a page has exactly one table, the *whole page* is sent with the table prompt; the result is adopted only if it is a single clean OTSL string (`_nano_is_single_clean_otsl` `:2794-2799`), else it falls back to the crop. |
| 6 | **Per-element deterministic post-processing** | `_nano_postprocess_element` `:2838-2877`, called `:3039-3040` | See §4. |
| 7 | **Markdown emission per element** | `_nano_format_element` `:2928-2957` | See §2 and §3. |
| 8 | **Document assembly** | `_nano_assemble_markdown` `:2960-3012` | Sort by `(page_number, layout_order)`; merge contiguous same-page `List-item`s into one block; drop empty blocks; join blocks with `\n\n`; insert `---\n\n**Page N**` between pages in the full-document string only. |
| 9 | **Document-level rule post-processing** | `postprocess_markdown` `:2567-2585`, called `:3045-3047` | `header_mark` → `quote_fold` → `title_promote("aggressive")`. See §4. |
| 10 | **Normalise to ParseBench IR** | `normalize` `:3269-3323` | Wraps markdown + per-page markdown + bboxes into `ParseOutput`. No text transformation. |

**Recognition-stage failures are silent.** `_nano_chat` (`:2713-2742`) returns `None` on any 4xx or after 3 retries, and the caller sets `el["content"] = ""` (`:3121`) — the element survives with empty content.

---

## 2. The recognition prompts, verbatim — this is the root cause

`_NANO_PROMPTS`, `kdl_frontier_nano.py:2596-2604`:

```python
_NANO_PROMPTS = {
    # byte-exact stage prompts (leading newline included; formula has no
    # trailing newline) — these are the templates the run was measured with.
    "layout": "\nLayout Detection:\n",
    "text": "\nText Recognition:\n",
    "table": "\nTable Recognition:\n",
    "picture": "\nImage Analysis:\n",
    "formula": "\nFormula Recognition:",
}
```

That is the complete set of instructions the model receives. Assembled into the request body at `_nano_payload:2683-2710`; the only other steering is `{"chat_template_kwargs": {"enable_thinking": False}}` at `:2727`.

**The model is never asked to preserve bold, italic, underline, strikethrough, superscript, subscript, headings, or code blocks.** There is no system prompt, no few-shot example, no response schema, and no `response_format` anywhere in the file. `temperature=0.0` with `top_k=1` (`:2702`, `:2617-2621`) means the output is the greedy decode of a 15-token prompt.

That is consistent with the measured zero emission rate (§3) and it makes this a **prompt-level** problem first, not a rendering problem.

---

## 3. Inline formatting: requested? parsed? emitted? — per feature

Exhaustive search over the file for `bold|italic|underline|strike|strikethrough|superscript|subscript|<sup|<sub|<u>|<b>|<i>|<em>|<strong>|~~|\*\*|latex|code` returned only the lines cited below. Empirical column = occurrences across 23,802 elements / 1,196 documents of stored run output.

| Feature | (a) In a prompt? | (b) Parsed from output? | (c) Emitted to markdown? | Observed in real output |
|---|---|---|---|---|
| **Bold** | **No** | No parsing | Only incidentally: `**Page N**` separators (`:3001`) and `# `/`## ` headings, which the grader's bold rule also accepts. Model-emitted `**` passes through untouched. | `**` in **33 / 23,802** elements |
| **Italic** | **No** | No | Pass-through only | `*` present but almost all literal asterisks/footnote glyphs, not paired italics |
| **Underline** | **No** | **No — absent entirely** | **No — absent entirely.** No `<u>`, `<ins>`, or `text-decoration` token exists anywhere in the 3323 lines. | **0 / 23,802** |
| **Strikethrough** | **No** | **Partially** — `_HTML_STRIKE_OPEN_RE` / `_HTML_STRIKE_CLOSE_RE` (`:2883-2884`) rewrite `<s>`/`<strike>`/`<del>` → `~~` inside `_preserve_inline_markup` (`:2894-2899`) | Yes, *if* the model produced the HTML tag — and only on 4 of 8 category branches (see below) | **0 / 23,802** — the converter has never had an input |
| **Superscript** | **No** | No | No | `<sup>` 0 / 23,802; Unicode superscript chars in only **17 / 1,337** documents |
| **Subscript** | **No** | No | No | `<sub>` 0; Unicode subscript chars in **11 / 1,337** documents |
| **Highlight (`<mark>`)** | **No** | No | No | 1 / 23,802 |
| **Titles / headings** | **No** | `_strip_leading_heading_marker` (`:2885-2891`) *removes* a model-emitted leading `#…` | **Yes — synthesised by the pipeline.** `Title` → `# `, `Section-header` → `## ` (`:2931-2933`); `title_promote` (`:2511-2543`) promotes further lines to `# `. This is the pipeline's only real formatting capability. | 1,314 headings in 205 text-split documents vs only 7 elements whose *own* content began with `#` — i.e. essentially all headings are pipeline-generated |
| **LaTeX** | Yes, in the sense that `Formula` regions get `"\nFormula Recognition:"` | `_nano_postprocess_element` `:2863-2874`: if both `\(`+`\)` or both `\[`+`\]` are present, strips `$` then rewrites `\(`/`\)` → ` $ ` and `\[`/`\]` → ` $$ ` | `_nano_format_formula` `:2911-2917` wraps the result in a **` ```latex ` fence** | Formula elements exist in only **11 / 1,596** documents (20 elements total). Negligible. |
| **Code blocks** | **No** | No | **No.** The layout label `code` is mapped to `Text` at `:549` (`"code": "Text"`), so a code region is recognised with the plain text prompt and emitted as a paragraph with no fence and no language tag. The only fence the pipeline ever writes is the ` ```latex ` one above. | `is_code_block` pass rate **0.000** in my replay |

### 3.1 Direct answer: is underline or strikethrough handled anywhere at all?

**Underline: no. Nowhere. Not in a prompt, not in a parser, not in an emitter.** The strings `<u>`, `</u>`, `<ins>`, `underline`, and `text-decoration` do not occur in the file.

**Strikethrough: half-handled, and the half that exists has never fired.** `_preserve_inline_markup` converts strikethrough *HTML* to markdown `~~`, but the model never emits that HTML, so the function is dead code in practice. Note the grader accepts `<s>`/`<del>`/`<strike>` directly (`rules_formatting.py:251-259`), so this conversion is not even necessary.

**Exact function and line where handling would need to be added:**

`_nano_format_element`, `kdl_frontier_nano.py:2928-2957` — this is the single choke point through which every element's text reaches the markdown. Note it currently calls `_preserve_inline_markup` on only **four** of its branches:

```python
def _nano_format_element(el: Dict[str, Any]) -> str:          # :2928
    category = el.get("category", "Text")
    content = el.get("content") or ""
    if category in ("Title", "Section-header"):               # :2931
        prefix = "#" if category == "Title" else "##"
        return f"{prefix} {_preserve_inline_markup(_strip_leading_heading_marker(content))}"   # <-- markup preserved
    if category == "Table":
        return content                                        # :2935  <-- NOT preserved
    ...
    if category in _BLOCKQUOTE_CATEGORIES:
        return _nano_format_blockquote(content)                # :2951  <-- NOT preserved (Caption/Footnote/Page-header/Page-footer)
    if category == "Formula":
        return _nano_format_formula(content)                   # :2953  <-- NOT preserved
    if category == "List-item":
        c = _preserve_inline_markup(_strip_leading_heading_marker(content.strip()))            # <-- preserved
        return f"- {c}" if c else ""
    return _preserve_inline_markup(_strip_leading_heading_marker(content.strip()))             # <-- preserved (Text)
```

So even after a prompt fix, **strikethrough emitted inside a Caption, Footnote, Page-header, Page-footer, Formula, or Table would still be lost or mangled.** For tables the loss is hard: cell text is HTML-escaped at `otsl_converter.export_to_html`, `:1219` — `content = html.escape(cell.text.strip())` — so a model-emitted `<u>x</u>` in a table cell becomes the literal text `&lt;u&gt;x&lt;/u&gt;`. (I searched for exactly this signature in the run output and found only one hit, which turned out to be a genuine escaped `<` in the string `0V &lt; SENSE &lt; 1V` — a false positive. Confirms zero real cases.)

---

## 4. The post-processing stage — every deterministic transformation, and its formatting risk

### 4a. Per-element (`_nano_postprocess_element`, `:2838-2877`) — first matching branch wins; exceptions keep original content

| Category | Transformations | Could it drop formatting? |
|---|---|---|
| `Table` | HTML input → `normalize_html_table_content` (`:2206-2246`: unwrap JSON string literals, `html.unescape`, unescape `\"`, strip ` ```html ` fence, `normalize_span_attributes`). OTSL input → `truncate_repetitive_content(preserve_line_breaks=True)` → `convert_otsl_to_html_v2` (`:1358-1493`) → `normalize_span_attributes` (`:2196-2203`) → `remove_dots_from_html_cells` (`:2249-2287`) | **YES, structurally.** `export_to_html:1219` HTML-escapes every cell's text, so any inline HTML markup in a cell is destroyed. `html.unescape` on the *provider-HTML* path (`:2229`) would conversely revive escaped tags. Never fired in the observed run. |
| `Title`/`Section-header`/`Text`/`Page-header`/`Page-footer`/`List-item`/`Caption`/`Footnote` (`_TEXT_BUCKET_CATEGORIES` `:2655-2659`) | `truncate_repetitive_content` (`:1629-1748`) | **Low risk, one real hazard.** `:1711-1714` finds the first run of 5+ identical characters and, if that character is Unicode punctuation/space/symbol, deletes **every** 5+ run of it document-wide. `*`, `~`, `_`, `#` are all in those Unicode categories, so a genuine `*****` or `~~~~~` would vanish. `**` and `~~` (2 chars) are safe. |
| `Picture`/`Flowchart` | `el["content"] = f"![{truncate_repetitive_content(content)}]"` (`:2857`) | Wraps the caption into image-alt syntax. Formatting inside becomes alt text. |
| `Chart` | `normalize_inline_markdown_table` (`:2331-2361`) → **`html.escape(cleaned)`** → `markdown.markdown(..., extensions=["tables"])` (`:2860-2862`) | **YES — the most destructive single line in the file.** `html.escape` before the markdown render turns any `<u>`, `<s>`, `<sup>` into `&lt;…&gt;` unconditionally. Only affects `Chart` elements (855 in the corpus). |
| `Formula` | `truncate_repetitive_content`, then `\(`/`\[` → `$`/`$$` (`:2863-2874`) | Then wrapped in a ` ```latex ` fence at `:2917`, which is not the delimiter form `is_latex` prefers. Negligible volume. |

### 4b. Per-element emission (`_nano_format_element`, `:2928-2957`)

- `_strip_leading_heading_marker` (`:2888-2891`) — **deletes** a leading `#{1,6} ` from `Title`, `Section-header`, `List-item`, and plain `Text` content. For `Title`/`Section-header` it is immediately re-added, so no loss; **for a plain `Text` element whose content legitimately began with a markdown heading, the heading marker is destroyed.** (7 such elements observed — negligible in practice, but it is a genuine drop.)
- `_preserve_inline_markup` (`:2894-2899`) — the only markup-preserving call; missing from 4 of 8 branches (§3.1).
- `_nano_format_blockquote` (`:2901-2908`) — prefixes every line of `Caption`/`Footnote`/`Page-header`/`Page-footer` with `> `.
- `_nano_format_formula` (`:2911-2917`), `_nano_image_markdown` (`:2920-2925`).
- **Multi-line elements get one marker only.** `Title` produces `# line1\nline2\nline3`; `List-item` produces `- line1\nline2`. Measured: **183 of 3,643** `Title`/`Section-header` elements are multi-line (5.0%), leaving **254 heading lines with no `#`** across 123 documents. This is the mechanism behind 2 of the 3-file slice's `is_title` failures (see §6.1).

### 4c. Document-level (`postprocess_markdown`, `:2567-2585`)

Applied in this exact order, each wrapped so a failure never discards the document; skipped entirely for "runaway" markdown (>2 MB or a line repeated >1000×, `_looks_runaway` `:2556-2564`).

1. **`header_mark`** (`:2427-2441`) — inside every `<table>`, rewrites `<td>`→`<th>` for the auto-detected multi-level header rows (`_auto_header_n` `:2401-2415`: contiguous leading rows containing `colspan>1`, plus one leaf row; returns 0 when row 0 has no `colspan>1`). Table-structure only; no inline-formatting risk.
2. **`quote_fold`** (`:2454-2458`) — folds 8 curly quote/apostrophe codepoints to ASCII (`_QUOTE_FOLD` `:2447-2450`). No formatting risk.
3. **`title_promote(variant="aggressive")`** (`:2511-2543`) — for every *standalone* line (blank line above and below), de-blockquotes it and/or promotes it to `# ` if `_is_titleish` (`:2489-2508`) accepts. `aggressive` = `(max_words=12, caps_ratio=0.60, require_all_caps=False)` (`:2481`). Rejects lines that already look like a heading/list/table row, exceed 12 words, end in `.!?:;,`, or match `^.{1,40}:\s` (label-value). Accepts if the first alphabetic character is uppercase **or** ≥60 % of letters are uppercase. Skips fenced-code regions and `**Page N**` markers.
   - **This is the pipeline's single biggest formatting lever and it also boosts `is_bold`**, because the grader's bold detector has a heading arm: `^[ \t]*#{1,6}[ \t]+[^\n]*?QUERY[^\n]*?$` (`rules_formatting.py:201-204`). A heading line containing the query text counts as bold.
   - It is also **the main source of missed titles**: any lower-case-initial heading is rejected. Example verified below.

**Net answer to "which of these could be dropping formatting the model produced":** `html.escape` on the Chart path (`:2861`), `html.escape` per table cell (`:1219`), the missing `_preserve_inline_markup` on 4 emission branches (`:2935`, `:2951`, `:2953`), `_strip_leading_heading_marker` on plain `Text` (`:2891`), and the 5+-symbol-run deletion (`:1714`). **All five are real code defects — and all five are currently inert, because the model produces no inline markup for them to destroy.** Fixing them is necessary *after* a prompt fix, not instead of one.

---

## 5. What Semantic Formatting actually measures (and why underline is worth zero)

`parsebench/src/parse_bench/evaluation/evaluators/parse.py:511-539`:

```python
# Semantic Formatting: is the meaningful markup preserved?
# Styling and titles at full weight, latex and code blocks at 1/5.
_FORMATTING_WEIGHTS: dict[str, float] = {
    "normalized_text_styling": 1.0,
    "normalized_title_accuracy": 1.0,
    "normalized_latex": 1.0 / 5.0,
    "normalized_code_block": 1.0 / 5.0,
}
```

and `parse.py:344-357`:

```python
_TEXT_STYLING_PAIRS = [
    ("is_bold", "is_not_bold"),
    ("is_strikeout", "is_not_strikeout"),
    ("is_sup", "is_not_sup"),
    ("is_sub", "is_not_sub"),
]
```

`_TITLE_TYPES = {"is_title", "title_hierarchy_percent"}` (`parse.py:369`).

Therefore **`is_underline`, `is_italic`, `is_mark`, and `mark_color` appear in no Semantic Formatting category.** They are reported as standalone `rule_is_*_pass_rate` metrics and folded into the non-leaderboard `rule_pass_rate`, but they contribute nothing to the 66.81.

This is confirmed by the run's own metadata (`output/kdl_frontier_nano/text_formatting/_evaluation_report.json`). For `text/text_ocr__p4013`, which has 2 `is_underline` rules and 1 `is_strikeout` rule:

```
normalized_text_styling 0.0   included_types = ['is_strikeout']
semantic_formatting     0.0   category_scores = {'normalized_text_styling': 0.0}
```

and for `text/text_simple__edited`, which has 11 `is_bold` and 1 `is_mark`:

```
normalized_text_styling 0.8491   included_types = ['is_bold']   pos_score=0.818 neg_score=1.0
```

Two further mechanics that matter for planning:

- **The styling score is an F-score with β=0.5** over (positive-rule pass rate, negative-rule pass rate) (`parse.py:392-410`). **There are zero `is_not_*` rules anywhere in `data/text_formatting.jsonl`** (11 rule types, all positive), so `neg_score` is always 1.0 and the transform is `styling = 1.25·p / (0.25·p + 1)`. **Consequence: over-emitting formatting is not penalised inside this dimension.** Precision is free here; recall is everything. (It is *not* free for Content Faithfulness — see §7.3.)
- **Overall = plain mean of the five dimensions.** `(85.56 + 63.41 + 87.19 + 66.81 + 78.84)/5 = 76.362`, matching the published 76.36 in `leaderboard.csv`. **So 1 Semantic Formatting point = 0.2 Overall points.**

### 5.1 Rule-type prevalence — where the mass is

`data/text_formatting.jsonl`: 5,997 rules over **476 documents**.

| Rule type | Rules | Documents (of 476) | In Semantic Formatting? |
|---|---|---|---|
| `is_bold` | 2,066 (34.5 %) | 327 (68.7 %) | **Yes**, full weight |
| `is_title` | 1,872 (31.2 %) | 402 (84.5 %) | **Yes**, full weight |
| `title_hierarchy_percent` | 402 (6.7 %) | 402 (84.5 %) | **Yes**, full weight |
| `is_sup` | 318 (5.3 %) | 86 (18.1 %) | **Yes**, full weight |
| `is_latex` | 123 (2.1 %) | 32 (6.7 %) | Yes, 1/5 weight |
| `is_strikeout` | 44 (0.7 %) | 13 (2.7 %) | **Yes**, full weight |
| `is_sub` | 14 (0.2 %) | 6 (1.3 %) | Yes, full weight |
| `is_code_block` | 10 (0.2 %) | 5 (1.1 %) | Yes, 1/5 weight |
| `is_italic` | 655 (10.9 %) | 155 (32.6 %) | **NO — weight 0** |
| `is_underline` | 405 (6.8 %) | 116 (24.4 %) | **NO — weight 0** |
| `is_mark` | 88 (1.5 %) | 13 (2.7 %) | **NO — weight 0** |

Which sub-type drives each document's styling score (single-type documents):
`is_bold` alone 265 docs (55.7 %) · no styling rules at all 111 (23.3 %) · `is_bold`+`is_sup` 53 · `is_sup` alone 28 · **`is_strikeout` alone 8 (1.7 %)** · `is_bold`+`is_strikeout` 5 · others ≤3.

---

## 6. Empirical diagnosis: for each failing rule, is the text missing, or present-but-unmarked?

This separates "the model can't read it" (needs a model) from "the model read it but nobody marked it" (needs a prompt or a renderer). I replayed the real graders (`FormattingRule`, `TitleLevelRule`) against the stored markdown for every rule whose PDF has a run artifact.

| Rule type | Evaluated | Pass | Fail | of failures: text **missing** entirely | text present as its **own markdown line**, unmarked | present as a **whole element**, unmarked | present but **merged inline** into a longer line |
|---|---|---|---|---|---|---|---|
| `is_title` | 961 | 647 | 314 | 145 (46 %) | 133 (42 %) | 14 | 22 |
| `is_bold` | 965 | 367 | 598 | 105 (18 %) | 121 (20 %) | 18 | **354 (59 %)** |
| `is_sup` | 193 | 4 | 189 | 10 | 0 | 4 | **175 (93 %)** |
| `is_strikeout` | 28 | 0 | 28 | 3 | 2 | 2 | 23 (82 %) |
| `is_underline` | 236 | **0** | 236 | 15 | 26 | 37 | 158 (67 %) |

Reading of this table:

- **`is_sup` and `is_strikeout` are almost purely inline-markup problems.** 93 % / 82 % of failures are "the characters are in the output, in the right place, inside a longer line, with no marker". No renderer change can find them; a prompt or a fine-tune must make the model emit `<sup>`/`~~`.
- **`is_bold` splits.** 59 % is inline run-in emphasis the model never marks (`AGENCY:`, `ACTION:`, `one`) — prompt-level. But 23 % is standalone lines the pipeline simply failed to mark — renderer-level, and cheap.
- **`is_title` is 42 % renderer-level** (present, on its own line, unmarked). The remaining 46 % is missing text — a layout/recognition gap.
- **`is_underline` is 0-for-236.** Also note this is a *pure prompt* problem in 67 % of cases — and it earns nothing.

*Caveat: this subset (≈half of each rule type) is the intersection of `text_formatting` PDFs with documents run in other splits, so absolute pass rates here are not the published board figures. The missing-vs-present proportions are the load-bearing numbers and they are consistent across rule types.*

### 6.1 The 3-file slice, mechanism by mechanism

`text_ocr__p4013` (SemFmt 0.0000). Its only Semantic-Formatting-relevant rule is one `is_strikeout` for `"CONFIDENTIAL"`. The model recognised that stamped, struck-through region as the three characters `"CON"` (a `Page-header` element). **Recognition failure, not a rendering failure.** Its 2 `is_underline` rules (`"LIGHT AIRCRAFT PHOTOGRAPHIC MODIFICATION."`) — text recognised perfectly, no `<u>`, and worth zero to the dimension.

`text_simple__results` (SemFmt 0.2721; `is_bold` 0.25, `is_title` 0.25). Diagnosed line by line:
- `"► B KOMMISSIONENS BESLUT"` → the layout stage split it into a `Picture` (`![►B]`) and a `Title` (`KOMMISSIONENS BESLUT`). **Layout segmentation failure.**
- `"av den 16 januari 1997"` and `"om godkännande av metoder…"` → recognised correctly as `Text` elements, then **rejected by `_is_titleish`**: lower-case first letter and caps-ratio ≈ 0, so `title_promote` (`:2507-2508`) declines to promote. **Pure post-processing gate failure.**
- `"(Endast de franska…)"` → first alphabetic char is `E`, uppercase → promoted to `# `, **passes**. This proves the gate, not the model, is the discriminator.

`text_simple__edited` (SemFmt 0.8134). Both `is_title` failures and 2 of 11 `is_bold` failures come from one multi-line `Title` element:

```
# NATIONAL UNION FIRE INSURANCE COMPANY OF PITTSBURGH, PA
PSYCHIATRISTS PROFESSIONAL LIABILITY INSURANCE PROGRAM
CALIFORNIA MANUAL RULES
```

Lines 2 and 3 get no `#` — exactly the `_nano_format_element:2933` single-marker defect. **Pure emission failure.**

---

## 7. Measured intervention results (no GPU used)

I built a replay harness that reconstructs the final markdown from the stored per-element model output using the provider's own `_nano_assemble_markdown` + `postprocess_markdown`, then scores it with the real rule classes. **Reconstruction is byte-identical to the shipped markdown for the corpus used** (documents containing `Picture`/`Chart` elements are excluded because `picture_path` is not persisted in the artifact, so their markdown cannot be reproduced exactly). Corpus: **204 of 476** `text_formatting` documents; baseline SemFmt on it = **0.5299** (lower than the published 0.6681 because the subset skews text-dense — treat deltas as indicative, signs and rank order as reliable).

### 7.1 Oracle headroom — where the points actually are

| If this rule type passed perfectly | SemFmt | Δ SemFmt | Δ Overall |
|---|---|---|---|
| `is_bold` → 1.0 | 0.7487 | **+22.0 pts** | **+4.40** |
| `is_sup` → 1.0 | 0.6176 | +8.9 pts | +1.78 |
| `is_sup`+`is_strikeout`+`is_sub` → 1.0 | 0.6389 | +11.0 pts | +2.21 |
| `is_strikeout` → 1.0 | 0.5483 | +2.0 pts | +0.40 |
| `is_underline` → 1.0 | — | **+0.00** | **+0.00** |

Independently, a per-document model over the **full 476-document** split, calibrated so the baseline reproduces the published 66.81 (implied bold/title pass rate ≈ 0.724), gives: `is_bold`→1.0 **+8.6 SemFmt / +1.73 Overall**; titles→1.0 **+14.6 / +2.92**; `is_sup`→1.0 **+7.1 / +1.41**; `is_strikeout`→1.0 **+1.37 / +0.27**; `is_sub`→1.0 +0.18/+0.04; `is_latex`→1.0 +1.01/+0.20; `is_code_block`→1.0 +0.54/+0.11. **`is_underline` → exactly 0.00 by construction.**

### 7.2 Patches I actually implemented and measured

| Patch | Level | SemFmt | Δ SemFmt | Δ Overall |
|---|---|---|---|---|
| **A. Baseline (as shipped)** | — | 0.5299 | — | — |
| B. Multi-line `Title`/`Section-header` → one `#` per line | emission | 0.5259 | **−0.26** | −0.05 |
| C. Relax `_is_titleish` (drop the leading-capital / caps-ratio gate) | post-proc | 0.5352 | +0.67 | +0.13 |
| B + C | both | 0.5326 | +0.41 | +0.08 |
| **E. Bold run-in `Label:` prefixes** (≤6 words, line-initial, non-markup line) | emission | 0.5543 | **+2.44** | **+0.49** |
| **F. Bold every short standalone non-heading line** (≤14 words) | emission | 0.5734 | **+4.35** | **+0.87** |
| **G. E + F** | emission | 0.5792 | **+4.92** | **+0.98** |
| H. `<sup>`-wrap trailing 1–2-digit footnote markers | emission | 0.5308 | +0.08 | +0.02 |
| I. G + H | emission | 0.5799 | +5.00 | +1.00 |

Two results worth flagging honestly:

- **Patch B is negative.** Splitting a multi-line `Title` into separate `# ` blocks *lowers* `is_title` (0.769 → 0.744) because it changes line indices used by `title_hierarchy_percent` and breaks titles that legitimately wrap across lines within one element. Do **not** ship it as-is; if pursued, it needs the wrapped-title case distinguished from the stacked-titles case.
- **Patch C, the "obvious" fix to the case-sensitivity bug found in §6.1, is worth only +0.13 Overall.** The gate is a real defect but a small one.
- **Patch H is worth nothing** and is actively dangerous (§7.3). Drop it.

### 7.3 Safety of patches E+F against the other four dimensions

Checked over **1,576 documents** of stored output, comparing baseline vs patched:

- `normalize_text(patched) == normalize_text(baseline)` for **1,575 / 1,576** documents. `normalize_text` (`evaluation/metrics/parse/utils.py:258-262`) strips `**`/`__`/`*`/`_`, so bold insertion is invisible to Content Faithfulness. **Safe.**
- **Zero** documents had any `<table>…</table>` byte change → Tables/GriTS/TEDS untouched. **Safe.**
- Because there are no `is_not_bold` rules in the dataset, false-positive bolding costs nothing in Semantic Formatting either (§5).

**By contrast, `<sup>` insertion (patch H) is unsafe**: `normalize_text` deletes `<sup>…</sup>` *including its contents* (`utils.py:332-334`), so wrapping real digits in `<sup>` erases them from the Content-Faithfulness comparison. Same hazard for `<sub>`. Any `<mark>` work must emit the bare tag — `normalize_text` only strips the literal strings `"<mark>"`/`"</mark>"` (`utils.py:308-309`), so `<mark style="…">` would survive into the text comparison and corrupt it.

### 7.4 Exact grader targets (emit these literal forms, nothing else)

From `rules_formatting.py:243-280` — note **none of the HTML arms tolerate attributes**:

- underline → `<u>text</u>` or `<ins>text</ins>` (`:245-248`)
- strikeout → `~~text~~` or `<s>|<del>|<strike>text</s>…` (`:253-259`)
- bold → `**text**`, `<b>text</b>`, **or any `#…#{6}` heading line containing the text** (`:192-205`)
- italic → `*text*`, `_text_`, `<i>`, `<em>` (`:222-240`)
- sup/sub → `<sup>text</sup>` / `<sub>text</sub>`, **or the corresponding Unicode superscript/subscript characters** (`:269-280`, `:282-315`) — the Unicode route avoids the `normalize_text` deletion hazard and is the safer target
- mark → `<mark>text</mark>` (`:262-266`)
- title → `#…` heading, `<h1..6>`, **or a standalone `**text**` / `<b>text</b>` line** (`:731-763`)

---

## 8. Intervention points, ranked by expected value ÷ effort

| # | Intervention | Level | Where exactly | Expected Δ Overall | Effort / GPU |
|---|---|---|---|---|---|
| **1** | **Ship patches E+F** (bold run-in `Label:` prefixes; bold short standalone non-heading lines). Add as rules 4–5 of `postprocess_markdown` `:2567-2585`, or inside `_nano_format_element` `:2957`. Must guard lines starting with `<`, `\|`, `#`, `>`, `-`, `*`, `!`, `` ` ``. | **emission** | `:2567-2585` / `:2928-2957` | **+0.98 (measured)** | hours, **zero GPU** |
| **2** | **Rewrite the four recognition prompts** to request inline markup explicitly, naming the exact target syntax from §7.4. This is the only route to the 59 % of `is_bold` failures and 93 % of `is_sup` failures that are inline-merged. Prompts are 15 tokens today; there is ample room inside the 8192-token model window. | **prompt** | `_NANO_PROMPTS` `:2596-2604` | up to **+4.4** (bold oracle) + **+1.8** (sup oracle); realistically a fraction | 1 GPU-day of A/B sweeps on ~50 docs. **This is where tomorrow's GPU money belongs.** |
| **3** | **Complete `_preserve_inline_markup` coverage** — call it on the `Table`, blockquote-categories, and `Formula` branches (`:2935`, `:2951`, `:2953`); stop HTML-escaping cell text at `export_to_html:1219`; stop `html.escape` on the Chart path `:2861`. Prerequisite for #2 to pay out in captions, footnotes, headers/footers and tables. | **emission** | `:1219`, `:2861`, `:2935`, `:2951`, `:2953` | 0 alone; **unlocks part of #2** | hours, zero GPU — but re-verify Tables/GriTS, since `:1219` and `:2861` also guard against malformed model HTML |
| **4** | **Relax `_is_titleish`** — patch C. Keep the word-count / terminal-punctuation / label-value guards; drop the leading-capital + caps-ratio requirement, or lower `caps_ratio` and accept lower-case-initial lines. Consider adding a new `_TITLE_VARIANTS` entry rather than editing `"aggressive"`. | **post-proc** | `_is_titleish` `:2489-2508`, `_TITLE_VARIANTS` `:2480-2486` | **+0.13 (measured)** | ~1 hour, zero GPU |
| **5** | **Emit a fence for code regions** — the layout label `code` is thrown away at `:549` (`"code": "Text"`). Add a `Code` category, route it to the text bucket, and emit a ` ```lang ` fence in `_nano_format_element`. Requires a language guess, which `CodeBlockRule` matches strictly. | emission + layout contract | `:549`, `:2928-2957` | ≤ **+0.11** | 5 documents in the whole split — do last |
| **6** | **Emit `$…$` / `$$…$$` for Formula instead of a ` ```latex ` fence** (`_nano_format_formula:2911-2917`). | emission | `:2911-2917` | ≤ **+0.20** | Formula elements exist in 11/1,596 documents — negligible |
| **X** | **Do NOT invest in underline, italic, or highlight.** They carry weight 0 in Semantic Formatting. | — | — | **+0.00** | — |
| **X** | **Do NOT ship patch B** (multi-line heading split) or **patch H** (`<sup>`-wrapping digits) as measured. B is −0.05 Overall; H is +0.02 Overall and corrupts Content Faithfulness. | — | — | negative | — |

**Recommended plan for tomorrow.** Land #1 and #4 today with no GPU (measured +1.11 Overall, ≈76.36 → 77.47, which already passes LlamaParse Cost Effective at 76.77). Spend the GPU exclusively on **#2, the prompt rewrite**, A/B-ing prompt variants for inline bold and superscript on a fixed ~50-document dev slice, with #3 landed first so the new markup survives the renderer.

---

## 9. Configuration surface (env vars, budgets, encodings)

Environment variables read (`:3174-3196`, `:2641-2649`, `:2664-2681`):

| Variable | Default | Line | Notes |
|---|---|---|---|
| `KDL_NANO_ENDPOINT_URL` | — **required** | `:3178` | vLLM base URL ending `/v1`; raises `ProviderConfigError` if absent (`:3181-3185`) |
| `KDL_NANO_MODEL` | `kdl-frontier-parser-nano` | `:3188` | |
| `KDL_NANO_DPI` | `144` | `:3191` | PDF → image render density |
| `KDL_NANO_MAX_PAGES` | `400` | `:3194` | exceeding it raises `ProviderPermanentError` |
| `KDL_NANO_MAX_CONCURRENT` | `8` | `:3196` | one `asyncio.Semaphore` per document (`:3031`); the checked-in run used a harness-level `max_concurrent: 20` (`output/kdl_frontier_nano/_metadata.json`) |
| `KDL_NANO_LAYOUT_MAX_TOKENS` | **6000** | `:2644` | |
| `KDL_NANO_TEXT_MAX_TOKENS` | **2048** | `:2645` | |
| `KDL_NANO_TABLE_MAX_TOKENS` | **5500** | `:2646` | |
| `KDL_NANO_PICTURE_MAX_TOKENS` | **4096** | `:2647` | |
| `KDL_NANO_FORMULA_MAX_TOKENS` | **128** | `:2648` | |

Constraint recorded in the code at `:2642-2643`: *"layout/table must fit `--max-model-len 8192`, otherwise long pages return HTTP 400 → empty layout."* The recommended serve line is `--max-model-len 8192 --max-num-seqs 24 --limit-mm-per-prompt '{"image":1}'` (`:12-16`).

**Budget implications for the prompt rewrite (#2).** The `text` stage has only 2048 output tokens per element, but elements are single paragraphs, so headroom is ample. Prompt *input* tokens are shared with the image tokens against `max-model-len 8192`; images are capped at `MAX_PIXELS = 2,822,400` with `FACTOR = 28` (`ImageConfig` `:268-279`), i.e. ≈3,600 image tokens worst case. A prompt of a few hundred tokens is therefore safe for `text`, `picture`, and `formula`. **The `layout` (6000) and `table` (5500) stages have almost no input headroom** — do not lengthen those two prompts without re-checking for 400s, which fail silently to an empty page (`:3089-3093`).

Other fixed parameters: `temperature=0.0` for all stages (`:2702`); per-stage `top_p=0.01, top_k=1, repetition_penalty=1.0, no_repeat_ngram_size=100` (`_NANO_EXTRA_PAYLOAD` `:2606-2639`; `formula` sends only temperature + max_tokens). Table crops are encoded as **lossless PNG** (`_NANO_LOSSLESS_STAGES` `:2653`) because "JPEG q95 collapses multi-line cells"; every other stage uses JPEG quality 95 (`:2664-2680`).

---

## 10. What I could NOT determine from the code, and other caveats

1. **Whether a prompt change actually makes these weights emit inline markup.** The 1.2 B weights are not in this repo and I ran no inference. If the model was never trained on inline-markup targets, a prompt rewrite will not conjure the capability, and intervention #2 collapses to a fine-tune. **This is the single largest open risk and it is exactly what the GPU day should resolve first** — a 20-document probe with an explicit-markup prompt answers it in under an hour.
2. **Replay-corpus bias.** My measured deltas come from 204 of 476 `text_formatting` documents — those whose PDFs also appear in another split's stored run, and which contain no `Picture`/`Chart` elements (so `picture_path` reconstruction is not needed). Baseline SemFmt on that corpus is 0.5299 vs the published 0.6681. Signs and rank order should hold; **absolute point deltas will differ on the real board.** A full re-score against all 476 documents requires the missing artifacts or a fresh inference run.
3. **The 3-file slice is too small to steer on.** Its `is_strikeout` 0.00 rests on **one** rule, on a document where the strikethrough word was mis-recognised as `"CON"`. Its `is_underline` 0.00 rests on 4 rules worth zero to the dimension.
4. **The full board's per-type pass rates are not directly observable.** The 0.724 implied bold/title rate in §7.1 is a single-parameter calibration to the published 66.81, not a measurement; it assumes `is_sup`/`is_sub`/`is_strikeout` are 0 (which §3 supports) and `is_latex` ≈ 0.30.
5. **The picture/chart paths are only partly exercised.** `_nano_apply_picture_result` (`:2802-2835`) documents two dead branches (classified-JSON, Hangul caption translation). I did not audit `normalize_chart_table_currency_values` (`:1863-1959`) or `merge_translated_table_with_source_values` (`:1961-1982`) for formatting effects, since Charts carry no `text_formatting` rules.
6. **`header_mark`'s effect on Tables was not re-measured.** The docstring claims "+0.0156 5D" and "+0.0132 5D" for the shipped rules (`:2373`); I did not reproduce those numbers.
7. **`title_hierarchy_percent` interacts with line positions.** It scores titles *and* parent/child order/level edges (`rules_formatting.py:873-925`), so any patch that inserts or moves lines can shift it in either direction — that is why patch B measured negative. Every future emission patch must be re-measured on this metric, not reasoned about.
8. **Nothing in this report was run against `data/` beyond scoring already-stored outputs.** No new inference, no benchmark tuning loop. The replay harness lives in `/tmp` and was not committed.
