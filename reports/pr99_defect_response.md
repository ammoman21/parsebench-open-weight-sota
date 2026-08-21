# PR #99 defect response — two emission defects, fixes, and the honest rescore

**Date:** 2026-08-21.
**Trigger:** ParseBench maintainer boyang-zhang1's review of our PR #99 (florin-parser-nano,
submitted Overall 76.92) found two defects in our markdown emission that inflate the
Semantic Formatting dimension. He re-ran on identical model output with the defects fixed
and Semantic Formatting went down.

**Bottom line first:** both defects are real, both reproduced here byte-for-byte, both are
now fixed in `ourparser/emission.py`, and replaying the two submitted runs' stored model
output through the fixed emission gives **Overall 76.69 (was 76.92)** — see §4.
That still clears the published leader's 76.36, so the preregistered ranking claim
survives the correction, smaller (§5). Every number in this file states its source.

Terms used below, in plain language:

* **ParseBench** — LlamaIndex's document-parsing benchmark: a parser turns PDF pages into
  markdown, which is scored on five dimensions (Tables, Charts, Content Faithfulness,
  Semantic Formatting, Visual Grounding); Overall is their plain mean.
* **emission** — the final step of our pipeline that turns recognised page elements
  (category + bounding box + text) into the markdown string that gets scored.
* **replay** — re-running emission + scoring on the per-element model output saved during
  the original runs. No GPU, no new inference: the model's output is held fixed, so any
  score change is caused by the emission code alone.
* **fence** — a markdown code block delimited by ``` or ~~~ lines; the benchmark also uses
  fences for LaTeX blocks.

---

## 1. The two defects — reproduced, not taken on faith

Both reproduced in this session against the pre-fix `ourparser/emission.py` (the exact code
that produced the submitted runs; the byte-identity check in §3 proves that equivalence).

### Defect 1 — `bold_run_in_labels` breaks lists and reaches inside fences

`_LABEL_RE` (`ourparser/emission.py:468` pre-fix) matched "anything ending in a colon" at
the start of the whole line, and the skip test looked at each line in isolation.
Reproduction (real output, this session):

```
>>> bold_run_in_labels("- Note: check the seal")
'**- Note:** check the seal'          # bullet swallowed into the span; list destroyed
>>> bold_run_in_labels("1. Warning: hot surface")
'**1. Warning:** hot surface'         # same for numbered items
>>> bold_run_in_labels("```latex\n\\alpha: the first coefficient\nE: energy\n```")
'```latex\n**\\alpha:** the first coefficient\n**E:** energy\n```'   # fence interior bolded
```

Why this inflated Semantic Formatting: the scorer's bold matcher
(`parsebench/src/parse_bench/evaluation/metrics/parse/rules_formatting.py:173-200`) searches
the raw content for `**…query…**` anywhere, so the corrupted `**- Note:**` still earns
`is_bold` credit — the parser banked bold points while emitting broken markdown. That is
corruption-coupled credit, exactly as the maintainer said.

### Defect 2 — the relaxed heading gate promotes sentences ending in `.`

Preregistration component (d) (`PREREGISTRATION.md` §3) relaxed the vendored heading gate
`_is_titleish` by dropping two vetoes. One of them — the terminal-punctuation veto,
`_TERMINAL_PUNCT = tuple(".!?:;,")` at `kdl_frontier_nano.py:2471`, applied at `:2497` —
was doing double duty: it rejected genuine headings ending in `:` (the defect we were
fixing) but also rejected body sentences ending in `.` (the guard we should have kept).
Dropping it entirely promoted short sentences to headings. Reproduction (real output):

```
>>> title_promote("para one\n\nThe device was tested.\n\npara two", relaxed_gate)
'para one\n\n# The device was tested.\n\npara two'
```

Headings also earn scorer credit (the bold matcher's third arm accepts any `#` heading
line containing the query, `rules_formatting.py:199-202`; heading rules score them too),
so this inflated Semantic Formatting as well.

## 2. The fixes (in `ourparser/emission.py`; the PR's in-repo port still needs the mirror)

### Fix 1 — `bold_run_in_labels` (emission.py, `_LIST_PREFIX` + fence tracking)

* **List items:** the list marker is split off before label matching, and the label is
  bolded inside the item text: `- Note: x` → `- **Note:** x`. Variant chosen by reading
  the scorer: `_build_bold_patterns` (`rules_formatting.py:173`) builds
  `\*\*(?!\s)…(?<!\s)\*\*` (`:194`) and searches it anywhere in the raw content, so a bold
  span inside a list item both renders correctly and scores. Verified directly against
  `FormattingRule` this session: `- **Note:** x`, `1. **Warning:** x`, `1) **…**`,
  `* **…**`, `+ **…**` all pass `is_bold`. (Side effect, disclosed: `*`-bulleted items are
  now in scope; the old whole-line regex excluded them only by accident of its
  first-character class.)
* **Fences:** fence state is tracked across lines with the same marker pattern as the
  vendored `_FENCE_RE` (``` or ~~~); interior lines are never touched.

```diff
-    tbl = _table_line_mask(md)
-    out: List[str] = []
-    for i, line in enumerate(md.split("\n")):
-        if tbl[i] or _skippable(line) or _HAS_BOLD.search(line):
-            out.append(line)
-            continue
-        m = _LABEL_RE.match(line)
-        if m and len(m.group(1).split()) <= 6:
-            line = f"**{m.group(1)}**{m.group(2)}{line[m.end():]}"
-        out.append(line)
-    return "\n".join(out)
+    tbl = _table_line_mask(md)
+    out: List[str] = []
+    in_fence = False
+    for i, line in enumerate(md.split("\n")):
+        if _FENCE_LINE.match(line):
+            in_fence = not in_fence
+            out.append(line)
+            continue
+        if in_fence or tbl[i] or _HAS_BOLD.search(line):
+            out.append(line)
+            continue
+        prefix = ""
+        body = line
+        lp = _LIST_PREFIX.match(line)
+        if lp:
+            prefix = lp.group(1)
+            body = line[lp.end():]
+        if _skippable(body):
+            out.append(line)
+            continue
+        m = _LABEL_RE.match(body)
+        if m and len(m.group(1).split()) <= 6:
+            body = f"**{m.group(1)}**{m.group(2)}{body[m.end():]}"
+        out.append(prefix + body)
+    return "\n".join(out)
```

### Fix 2 — `is_titleish_relaxed` (emission.py)

The vendored terminal-punctuation veto is restored for every character except the colon
(`_TERMINAL_PUNCT_NO_COLON = tuple(".!?;,")`); the label/value veto stays dropped; the
20-word cap stays. Keeping `:` out of the veto set is the whole point of component (d):
"Notes:" is a genuine heading the vendored gate wrongly rejected.

```diff
     if len(s.split()) > word_cap:
         return False
+    # PR #99 fix: the vendored veto minus the colon. A line ending in sentence
+    # punctuation is body text, not a heading; a line ending in `:` may be a heading.
+    if s.endswith(_TERMINAL_PUNCT_NO_COLON):
+        return False
     letters = K._LETTER_RE.findall(s)
```

Post-fix behavior, verified this session: `The device was tested.` is not promoted;
`Notes:` still is. One nearby behavior did **not** change and should not be mistaken for
part of this fix: `1. Scope of Works:` is rejected by the vendored numbered-list veto
(`_NUMLIST_RE`), which the relaxed gate always kept — it was rejected in the submitted
version too (verified both sides this session).

## 3. Tests

New file `ourparser/tests/test_emission.py` — 16 tests covering the maintainer's exact
cases (bulleted label, numbered label, fenced LaTeX, short sentence ending in `.`,
genuine `Notes:` heading still promoted, paragraph-leading `Label:` still bolded) plus
scorer-acceptance checks that run the benchmark's real `FormattingRule` against the
emitted forms, and an end-to-end test through `postprocess_markdown`.

```
$ parsebench/.venv/bin/python -m pytest ourparser/tests/ -q
38 passed, 3 warnings in 0.56s
```

(22 pre-existing tests + 16 new; the tests import the vendored benchmark module, so they
run under `parsebench/.venv` — the top-level `.venv` lacks the `markdown` dependency and
cannot import it, verified by attempting it.)

## 4. Rescore on identical stored model output

**What was replayed.** The two submitted full runs' artifacts:
`parsebench/output/it7_full/kdl_frontier_nano_patched/` and
`parsebench/output/it7_confirm/kdl_frontier_nano_patched/` (4,190 files each; per-document
`*.raw.json` stores the final markdown and the per-element model output;
`_metadata.json` confirms `emission_set=genuine_abcd`, 2,078 documents, 100% success).
Driver: `parsebench/scripts/pr99_rescore.py`; raw results in
`parsebench/scripts/_pr99_rescore.json`.

**Method.** For every scored document, markdown was rebuilt from the stored elements twice
through the production entry point (`ourparser.emission.build_markdown`, genuine_abcd
config): once with verbatim copies of the submitted (defective) functions, once with the
fixed code; both were scored with the benchmark's own rule classes, and the per-document
fixed score = stored score + (score(fixed rebuild) − score(submitted rebuild)).

**Validity checks (all from the rescore output):**

* *Scorer replication:* scoring the stored markdown reproduces the stored per-document
  metric with **zero mismatches** on every rule-scored split of both runs — 457
  Semantic-Formatting documents, 506 Content-Faithfulness documents and 568 Chart
  documents per run (`scorer_replication_mismatches: 0` in every JSON block; the joined
  stored aggregates equal the official report aggregates to full float precision, e.g.
  0.7170839894970746 for it7_full Semantic Formatting).
* *Reconstruction fidelity:* the submitted-code rebuild equals the stored markdown byte
  for byte on 303/457 formatting docs and 337/506 faithfulness docs (both runs),
  470/503 and 469/503 table docs, and **0/568 chart docs** — chart documents always
  contain Chart/Picture elements whose `picture_path` the artifact does not persist, so
  the Charts delta rests entirely on paired rebuilds. Every non-exact document
  spot-checked (all 23 in a 30-document pilot) contained Picture/Chart elements; zero
  picture-free mismatches. For those documents the paired delta still isolates the
  emission fix — both rebuilds lack the same image lines.
* *Determinism:* the it7_confirm run was independently recomputed by two separate
  processes; their JSON result blocks are identical (`a == b` verified).
* *Tables:* `grits_trm_composite` consumes only tables extracted from the markdown
  (`evaluation/evaluators/parse.py:893` → `extract_table_pairs`,
  `table_extraction.py:150`, whose actual-side extraction is independent of the expected
  side). Extracted tables were compared for every table document whose markdown changed
  under the fix: **it7_full 110 changed / 0 differ; it7_confirm 109 changed / 0 differ**
  (real command output, this session). Tables is therefore provably unchanged and the
  stored scores carry.
* *Visual Grounding:* computed from element `category`/`bbox`/`content`, which the
  emission code never writes to (`heading_levels_by_bbox` returns a side dict; no element
  mutation anywhere in `emission.py`). Carried forward unchanged, as flagged in the task:
  replay cannot re-measure it, and does not need to.

**Before/after (×100, Overall = plain mean of the five; produced by
`parsebench/scripts/pr99_table.py` from the rescore outputs):**

| Dimension | Run 1 submitted | Run 1 fixed | Run 2 submitted | Run 2 fixed | Mean submitted | Mean fixed | Mean delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tables | 86.14 | 86.14 | 86.05 | 86.05 | 86.10 | 86.10 | +0.00 |
| Charts | 65.39 | 65.25 | 65.27 | 65.13 | 65.33 | 65.19 | −0.14 |
| Content Faithfulness | 87.35 | 87.38 | 87.33 | 87.36 | 87.34 | 87.37 | +0.03 |
| Semantic Formatting | 71.71 | 70.66 | 71.66 | 70.62 | 71.68 | 70.64 | −1.04 |
| Visual Grounding | 74.15 | 74.15 | 74.14 | 74.14 | 74.14 | 74.14 | ±0.00 |
| **Overall** | **76.95** | **76.72** | **76.89** | **76.66** | **76.92** | **76.69** | **−0.23** |

Notes on cells:
* Submitted columns reproduce the official run aggregates exactly (76.947 / 76.891,
  reported as 76.95 / 76.89, mean 76.92 — same values as `LOOP_LOG.md` and the PR body).
* Visual Grounding is unchanged by construction; exact values 74.1463 / 74.1353, mean
  74.1408. The PR row's published "74.15" cell was a rounding of 74.145 (the mean of the
  two 2-dp cells); at full precision the mean rounds to 74.14. No score moved.
* The maintainer's finding is confirmed in sign and locus: Semantic Formatting drops
  1.04 points on identical model output once the corruption no longer earns credit;
  Charts drops 0.14 (the chart split also scores bold/heading-sensitive rules);
  Content Faithfulness *rises* 0.03 (the corrupted `**` tokens were noise to the text
  metrics); Tables and Visual Grounding are untouched.

## 5. What we can honestly claim now (preregistration §5 tiers)

PREREGISTRATION.md §5 fixed the claim tiers in advance:

* ≥ 76.36 → top open-weight position claim;
* 72.65–76.36 → "measured improvement of N points over our own reproduction (72.65)",
  no ranking claim;
* < 72.65 → the patches regressed; report and claim nothing.

**The fixed mean Overall is 76.69 (76.688), which is ≥ 76.36: tier 1 — the top
open-weight ranking claim survives the correction**, 0.33 points above the published
leader instead of 0.56, and it continues to carry the same environment caveat the PR
leads with (we measure the leader's own pipeline at 72.65 in our environment, not their
published 76.36; the same-environment improvement is now **+4.04**, was +4.30/+4.24).
Margin honesty: the margin over 76.36 (0.33) is larger than the run-to-run spread
(0.06) and larger than the bounded replay-transfer error (≤ 0.17 Overall), but it is
not large; if the maintainer's environment lands below ours, their numbers govern, as
the PR body already states.

## 6. Updates required downstream

**Status 2026-08-21 (later the same session): items 1–6 below are DONE on user approval**
— fixes mirrored into the staged provider (byte-identity vs the fixed ourparser emission
verified on all 2,078 documents of each run, 4,156 total, 0 mismatches:
`parsebench/scripts/pr99_port_identity.py`), row/README/PR-body/yaml/model-card/paper
updates applied with dated correction notes, LOOP_LOG entry appended. Pushing the
pr_staging inner repo, posting the PR comment, and the Hugging Face upload remain with
the user. Original list as written before approval:

1. **`pr_staging/ParseBench/src/parse_bench/inference/providers/parse/florin_parser_nano.py`**
   — the PR's in-repo port carries verbatim copies of both defective functions
   (`_is_titleish_relaxed` at `:235` without the punctuation veto; `_bold_run_in_labels`
   at `:359` without fence tracking or list handling). Mirror both fixes, then re-run the
   port's byte-identity replay against the stored runs (the PR body cites that check).
2. **`pr_staging/PR_BODY.md`** — scores table (five dimensions × two runs × mean),
   the +4.30/+4.24 same-environment deltas, and emission-change bullets 3 and 4
   (describe the fixed semantics).
3. **`pr_staging/ParseBench/leaderboard.csv`** (row `florin-parser-nano`) and
   **`pr_staging/ParseBench/README.md`** top-10 row — currently
   `76.92, 86.10, 65.33, 87.34, 71.69, 74.15`; replace with
   `76.69, 86.10, 65.19, 87.37, 70.64, 74.14` (fixed means, §4; the 74.15→74.14 VG cell
   is rounding only, see §4 notes).
4. **`publish/parsebench.yaml`** (value 76.92 + notes), **`publish/MODEL_CARD.md`**
   (results table + variance note), **`publish/koreadeep_note.md`** (72.65→76.95 delta),
   and the Hugging Face mirrors of the first two.
5. **`FINDINGS_PAPER.html` / `PARSEBENCH_WHITEPAPER.html`** §9 tables.
6. **`LOOP_LOG.md`** — dated entry recording this rescore.

## 7. Draft PR reply comment (NOT posted — for review)

> Thank you @boyang-zhang1 — both defects are confirmed. We reproduced them exactly as
> you described, against the same code that generated our submitted runs:
>
> 1. `bold_run_in_labels` matched its label pattern against the whole line, so a list
>    item `- Note: x` became `**- Note:** x` (bullet swallowed into the span, list
>    broken; same for `1. Warning: x`), and with no fence-state tracking it bolded
>    label-shaped lines inside ``` code/LaTeX fences.
> 2. Our relaxed heading gate dropped the stock terminal-punctuation veto entirely, so
>    ordinary short sentences ending in `.` were promoted to `#` headings.
>
> You are also right about the mechanism: the bold matcher searches raw content, so the
> corrupted spans still earned `is_bold` credit — part of our Semantic Formatting score
> was coupled to the corruption.
>
> Both are fixed, with tests for each of your cases. List items keep the marker outside
> the span (`- **Note:** x`, `1. **Warning:** x`), fence interiors are never touched
> (fence state tracked with the same pattern as the vendored `_FENCE_RE`), and the
> terminal-punctuation veto is restored for `.!?;,` — every stock character except `:`,
> which is the case the relaxation exists for (`Notes:` is a genuine heading the stock
> gate rejects).
>
> We then replayed both submitted runs' stored model output through the fixed emission
> — identical model output, emission-only change — and re-scored with the benchmark's
> own rule classes (scoring replication against the stored reports was exact on every
> rule-scored split before applying the fix). Honest before/after, both runs:
>
> | Dimension | Run 1 | Run 1 fixed | Run 2 | Run 2 fixed | Mean | Mean fixed |
> |---|---:|---:|---:|---:|---:|---:|
> | Tables | 86.14 | 86.14 | 86.05 | 86.05 | 86.10 | 86.10 |
> | Charts | 65.39 | 65.25 | 65.27 | 65.13 | 65.33 | 65.19 |
> | Content Faithfulness | 87.35 | 87.38 | 87.33 | 87.36 | 87.34 | 87.37 |
> | Semantic Formatting | 71.71 | 70.66 | 71.66 | 70.62 | 71.68 | 70.64 |
> | Visual Grounding | 74.15 | 74.15 | 74.14 | 74.14 | 74.15* | 74.14* |
> | **Overall** | 76.95 | 76.72 | 76.89 | 76.66 | **76.92** | **76.69** |
>
> Semantic Formatting drops 1.04 on identical model output — consistent in sign with
> your re-run. Visual Grounding is computed from the element payload, which the
> emission fixes don't touch, so it is carried unchanged (*the 0.01 movement in the
> mean cell is rounding: exact mean 74.1408*). Tables markdown changed on 110/503 and
> 109/503 documents, but the extracted table set is identical on every one of them, so
> `grits_trm_composite` is unchanged.
>
> Updated row: **Overall 76.69** (was 76.92) — Tables 86.10, Charts 65.19, Content
> Faithfulness 87.37, Semantic Formatting 70.64, Visual Grounding 74.14. We will update
> the PR accordingly: both fixes mirrored into `florin_parser_nano.py`, the
> `leaderboard.csv`/README row and PR-body table refreshed to these numbers, and the
> correction noted in the model card. Caveat as before: these are replay numbers on our
> stored runs — if your environment's re-run of the fixed pipeline lands elsewhere,
> your numbers govern.
>
> Thanks for the careful review — the entry is more honest for it.

## 8. What was NOT done / residual uncertainty

* No new inference: Visual Grounding is carried, and any interaction between the fixed
  markdown and live model behavior (there is none by construction — emission runs after
  the model) is untested by definition of replay.
* Non-byte-exact documents (missing `picture_path`) contribute paired deltas measured on
  rebuilds that both lack image lines; prior measurement of this transfer error bounded it
  at 0.16–0.84 Semantic-Formatting points, i.e. ≤ 0.17 Overall
  (`reports/formatting_gap_closure.md` §1.2).
* The maintainer's own fixed-emission numbers were not available to compare against ours;
  if they differ materially from §4, their environment's numbers govern (as the PR body
  already states).
* During this session, three background-monitor notifications reported "results" that were
  absent from the log file they claimed to tail; they were discarded and every number here
  was re-read from files or direct command output.
