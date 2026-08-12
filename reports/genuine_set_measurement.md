# The genuine-only patch set, measured — ParseBench / `KDL-Frontier-Parser-nano`

**Date:** 2026-08-12
**Scope:** `PREREGISTRATION.md` §3 (submitted set) and §4 (disclosed-but-not-submitted set).
**Method:** replay over already-saved run artifacts in
`parsebench/output/kdl_frontier_nano/`. **No GPU was available and no inference was run.**
**Nothing under `parsebench/src/` was modified.**

---

## 0. Headline answer

**The genuine set lands between our reproduction and the published leader. Claim tier 2 of
the preregistration applies.**

| | Overall | vs our reproduction 72.65 | vs published KDL 76.36 |
|---|---|---|---|
| **Genuine set, (a)+(b)+(c)** | **73.72** | **+1.07** | −2.64 |
| **Genuine set, (a)+(b)+(c)+(d) — SUBMITTED** | **74.64** | **+1.99** | −1.72 |
| Aggressive set (disclosed, not submitted) | 75.65 | +3.00 | −0.71 |

So, in the preregistration's own words (§5, middle row): *"A measured improvement of
**1.99** points over our own reproduction of the leader, plus the four defects and the
scorer-coupling finding. No ranking claim."*

Six things a reader should take from this document before the detail:

1. **The borderline component (d) is kept.** Its marginal contribution on top of
   (a)+(b)+(c) is **+0.92 Overall** — 18 times the ±0.05 threshold at which the
   preregistration said to drop it. §3.3.
2. **Component (a), the `section_header` category-map fix, contributes exactly 0 to every
   number above, and it is not possible to measure it without a GPU.** The stored
   artifacts persist only the *canonical* element category, never the model's raw layout
   label, so there is no way to know which regions the model called `section_header`. The
   fix is in the shipped code and is correct by inspection; its value is unknown. This is
   the single most important caveat in this report. §2.
3. **No kill criterion fired.** The largest Content-Faithfulness cost across all four
   measured sets is **−0.23 points** (the aggressive set), against the preregistration's
   −0.30 limit. Tables: 0 of 1,074 documents changed. Visual Grounding: 0 of 400 documents
   changed. §5.
4. **The aggressive set as §4 actually defines it reaches 75.65, not the 76.79 the
   preregistration cites.** That 76.79 was inherited from an earlier exploration whose
   patch set contained a *third* member the preregistration's §4 text does not mention —
   "bold every own-line of ≤40 words". Re-measured with only the two promotions §4
   describes, the number is 75.65. **`PREREGISTRATION.md` §4 needs a dated amendment.** §6.
5. **The reimplementation reproduces the measured numbers exactly** — to ten decimal
   places, through the same method live inference calls. §4.
6. **Semantic Formatting still cannot close the gap to 76.36.** Even at the published
   Semantic Formatting of 66.81 our row would score 75.53, because 4.65 points of Visual
   Grounding deficit (74.19 vs 78.84) remain. That is a layout-detection problem, not a
   formatting one, and it is untouchable without a GPU. §7.

### Terms used in this document, in plain language

* **ParseBench** — LlamaIndex's document-parsing benchmark. 2,079 page-documents, five
  scored dimensions, **Overall** = the unweighted mean of the five. So one
  Semantic-Formatting point moves Overall by 0.2 points.
* **the five dimensions** — **Tables** (table structure, scored by "GriTS", a
  grid-similarity measure); **Charts** (were the chart's data points extracted);
  **Content Faithfulness** (is the text correct, complete and in the right order);
  **Semantic Formatting** (was the meaningful markup — bold, headings, superscript,
  LaTeX, code fences — preserved); **Visual Grounding** (does each detected region's
  bounding box and text line up with the annotation).
* **rule** — one graded assertion from the benchmark's annotation files, e.g.
  `{"type": "is_bold", "rule": "{\"text\": \"AGENCY:\"}"}`, checked by a regular
  expression class in the benchmark's own scoring code.
* **element** — one detected region of a page: a category (`Title`, `Text`, `Table`, …),
  a bounding box, and the recognised text.
* **replay** — re-derive markdown from the stored per-element model output, then re-score
  it with the benchmark's own rule classes. The only measurement route without a GPU.
* **element sub-corpus** — the 319 of 476 scored Semantic-Formatting documents whose
  markdown re-assembles from stored elements *byte-identically* to what shipped. The
  other 157 contain `Picture`/`Chart` elements whose image path the artifact does not
  persist. Any change that acts before the final markdown exists can only be measured
  here; its delta is then added to the full-corpus baseline ("transfer", §8).
* **paired baseline** — when comparing a change that acts before the final markdown, the
  comparison markdown is *also* re-assembled from stored elements, so the difference
  isolates the change instead of mixing in reconstruction error. Only the delta is
  meaningful; the absolute paired baseline differs slightly from the shipped value.

---

## 1. The patch set, as code

The submitted changes are implemented as a provider subclass in **our own module**,
`ourparser/`, which sits *outside* the pinned `parsebench/` checkout. They are not runtime
patches applied by a measurement script — that is what the previous round measured, and
replacing it was the point of this one.

| file | what it is |
|---|---|
| `/Users/amolpant/forecasting_networks/bfcl-sprint/ourparser/emission.py` | the patched markdown emission, as pure functions of an element list. No endpoint, no GPU. |
| `/Users/amolpant/forecasting_networks/bfcl-sprint/ourparser/provider.py` | `KdlFrontierNanoPatchedProvider`, a subclass of the vendored provider, plus registration of two new pipeline names. |
| `/Users/amolpant/forecasting_networks/bfcl-sprint/ourparser/run_patched.py` | the launcher shim (see below). |
| `/Users/amolpant/forecasting_networks/bfcl-sprint/parsebench/scripts/genuine_set_measure.py` | the measurement, including the port-drift test and the reimplementation check. |

### 1.1 The four changes

| | change | where it lives in `ourparser/emission.py` | vendored lines a direct upstream fix would edit |
|---|---|---|---|
| **(a)** | add `"section_header": "Section-header"` to the layout label map | `PATCHED_NATIVE_LAYOUT_CATEGORY_MAP` | `kdl_frontier_nano.py:545-572` |
| **(b)** | heading depth from the `Title` element's bounding-box height, ranked per document, capped at 4 levels | `heading_levels_by_bbox`, `format_element` | `:2931-2933` |
| **(c)** | bold run-in `Label:` prefixes | `bold_run_in_labels` | new rule after `:2585` |
| **(d)** | relax the heading gate: drop **only** the terminal-punctuation and label-value vetoes, keep the leading-capital gate, cap promoted lines at **20 words** | `is_titleish_relaxed` | `:2489-2508` |

On (d), stated precisely because the previous round used a looser variant: we drop
`s.endswith(".!?:;,")` (`:2496-2497`) and `^.{1,40}:\s` (`:2498-2499`); we **keep** the
already-a-heading / bullet / numbered-item / table-row guards, the "must contain an ASCII
letter" guard, and the leading-capital-or-capitalisation-ratio requirement
(`:2504-2508`); and we replace the shipped 12-word cap with 20. The previous round's `T5`
dropped the capitalisation gate as well and used a 30-word cap; that is **not** what was
measured here.

Two further changes are implemented in the same module but flagged in code as **not
submitted**: short single-line `Text` promoted to `# `, and `List-item` promoted to `## `.
They exist so that §6's disclosed number is measured by our code rather than inherited.

### 1.2 Registration — it does work from outside the package, with one shim

ParseBench's `register_provider` and `register_pipeline` are public, importable functions,
so a new provider and new pipeline names can be registered entirely from outside
`parse_bench`. Two pipelines are registered:

```
kdl_frontier_nano_patched      the submitted set        (emission_set = genuine_abcd)
kdl_frontier_nano_aggressive   disclosed, not submitted (emission_set = aggressive_abcd)
```

**The one thing that does not work from outside is the benchmark's command line.**
`parse-bench` (defined by `parsebench/pyproject.toml` → `parse_bench.cli`) has no plugin
hook and no "extra modules to import" setting; it imports only its own hard-coded provider
list (`parse_bench/inference/providers/parse/__init__.py`). So an externally-registered
pipeline is invisible to it. Verified both ways:

```
$ ./parsebench/.venv/bin/python ourparser/run_patched.py inference list_pipelines | grep kdl
  kdl_frontier_nano
  kdl_frontier_nano_aggressive     <- ours
  kdl_frontier_nano_patched        <- ours

$ cd parsebench && ./.venv/bin/python -m parse_bench.cli inference list_pipelines | grep -c kdl_frontier_nano_patched
0                                  <- the plain CLI cannot see it
```

`ourparser/run_patched.py` is the smallest possible documented shim: it imports
`ourparser.provider` (which registers everything) and then hands control to ParseBench's
own unmodified `main()`. Use it exactly as you would use `parse-bench`:

```
KDL_NANO_ENDPOINT_URL=http://localhost:8000/v1 \
python ourparser/run_patched.py run kdl_frontier_nano_patched \
    --input_dir parsebench/data --output_dir parsebench/output/kdl_frontier_nano_patched
```

### 1.3 The two scoped bindings, disclosed

The subclass inherits every inference stage unchanged and replaces exactly one thing: the
function that turns the finished element list into markdown. Two of the things it needs
are looked up as *module globals by module-level functions* in the vendored file, where no
subclass hook can reach them:

* `NATIVE_LAYOUT_CATEGORY_MAP`, read by `_category_for_item` (`kdl_frontier_nano.py:763`);
* `_NanoEngine`, instantiated by name inside the vendored `run_inference`
  (`kdl_frontier_nano.py:3220`).

`ourparser.provider.patched_bindings()` rebinds those two attributes for the duration of
one document's inference and restores them afterwards, including on exception. This is
dependency injection through the only seam the vendored file offers — all of the
*behaviour* is ordinary code in `ourparser/emission.py`. It is scoped rather than applied
at import so that running the unpatched `kdl_frontier_nano` pipeline in the same process
is unaffected. An upstream fix would edit the two cited lines instead.

### 1.4 Reproduce

From `parsebench/`, **using that checkout's own virtual environment**:

```
./.venv/bin/python scripts/genuine_set_measure.py --collateral
```

Runtime 10 min 26 s, single-threaded, deterministic (no randomness, no wall-clock
dependence, no network). Results are also written to
`parsebench/scripts/_genuine_set_measure.json`.

> **Erratum on the previous report.** `reports/formatting_gap_closure.md` §1 tells the
> reader to run its scripts with `../.venv/bin/python` (i.e. the top-level
> `bfcl-sprint/.venv`). That interpreter cannot import the benchmark — it lacks
> `rapidfuzz`. The working interpreter is `parsebench/.venv/bin/python`. Every command in
> that report needs the same correction.

---

## 2. Component (a) cannot be measured by replay — and it may be worth nothing

This is the most important negative result in the report, so it is stated before any
number.

**The defect is real.** `NATIVE_LAYOUT_CATEGORY_MAP` (`kdl_frontier_nano.py:545-572`) has
no `section_header` key. Every key in it is lowercase-and-underscored (`list_item`,
`page_number`, `image_block`, …), which is the shape of the model's own raw layout labels,
while the pipeline's canonical spelling is hyphenated, `Section-header` (`:102`). An
unrecognised label therefore falls through `_canonicalize_category` (`:242-246`) — which
only knows the hyphenated spelling — and silently becomes `Text`. `Section-header` is the
only category the formatter renders as `## ` (`:2931-2933`), so that branch is dead code.
Confirmed empirically: **0 `Section-header` elements across all 2,078 stored artifacts.**

```
category census, all 2,078 stored artifacts
  Text 19,062   Title 6,031   List-item 4,705   Page-footer 3,193   Page-header 2,978
  Caption 2,547   Picture 2,190   Footnote 1,878   Chart 1,359   Table 1,242
  Formula 87   Flowchart 50   Section-header 0
```

**But it cannot be measured.** The stored artifact keeps only four fields per element —
`category`, `bbox`, `content`, `layout_order` — where `category` is already canonicalised.
The model's raw layout response (the `<|box_start|>…<|ref_start|>label<|ref_end|>` token
string that the map is applied to) is not persisted anywhere in `output/`; a search for
`box_start` across the whole output tree returns nothing. So there is no way to identify
which of the 19,062 `Text` elements the model actually labelled `section_header`.
Consequently:

* **(a) contributes exactly 0 to every measured number in this report, by construction.**
  All of the measured gain comes from (b), (c) and (d).
* **Its live contribution is unknown, and could legitimately be zero.** If the model's
  label vocabulary simply has no `section_header` token — plausible, since the map's
  26 keys look like a complete enumeration of that vocabulary, right down to an
  `"unknown"` entry — then adding the key changes nothing at all. Testing this needs one
  GPU run and a diff of the emitted category census.
* It is nonetheless kept in the submitted code: it costs nothing, it is correct if the
  label ever appears, and the alternative (shipping a knowingly dead `##` branch) is
  worse. It should be described in the writeup as *a defect we found and fixed whose value
  we could not measure*, never as a contributor to the score.

One consolation: the *consequence* of the defect — that every heading is depth 1 — is what
component (b) repairs directly, from geometry that is in the artifact. So the flat-heading
problem is addressed by the submitted set even though (a) itself is unmeasurable.

---

## 3. Semantic Formatting, measured

### 3.1 Baselines reproduce exactly

```
full corpus baseline        (n=457) SemFmt= 52.42   <- our shipped 52.4169, exactly
element sub-corpus baseline (n=307) SemFmt= 54.26   <- prior harness 54.2557, exactly
```

`n=457` of 476 because 19 documents carry no styling, title, LaTeX or code-block rule and
so produce no Semantic-Formatting value; the benchmark's own evaluator drops them from the
mean too.

### 3.2 Port-drift test — the ports are faithful

`ourparser/emission.py` re-implements three vendored functions with one injected seam
each (`assemble_markdown`, `title_promote`, `postprocess_markdown`). Ports drift, so the
measurement script first runs them with the *vendored* seam over **every** stored artifact
and requires byte-identical output. It also requires our `bold_run_in_labels` to equal the
function the previous round measured, so change (c) is provably the same rule.

```
1. PORT DRIFT TEST (our ports, vendored seam, vs the vendored functions)
   artifacts compared                          : 2041
   whole-document markdown mismatches          : 0
   per-page markdown mismatches                : 0
   bold_run_in_labels vs prior bold_labels     : 0 mismatches
   PORTS FAITHFUL: True
```

The script aborts before measuring anything if this fails.

### 3.3 The measurement

Element sub-corpus, 319 documents / 307 scored, paired baseline SemFmt 54.26. `hier` is
`title_hierarchy_percent`. **The ΔOverall column here is from Semantic Formatting alone**
(ΔSemFmt ÷ 5); the all-dimension Overall is in §7.

| configuration | SemFmt | ΔSemFmt | ΔOverall | `is_bold` | `is_title` | `hier` |
|---|---|---|---|---|---|---|
| baseline (vendored emission) | 54.26 | — | — | 0.418 | 0.789 | 0.642 |
| **GENUINE (a)+(b)+(c)** | **59.59** | **+5.33** | **+1.07** | 0.526 | 0.789 | 0.692 |
| **GENUINE (a)+(b)+(c)+(d)** | **63.04** | **+8.78** | **+1.76** | 0.584 | 0.819 | 0.718 |
| AGGRESSIVE on (a)+(b)+(c) | 66.67 | +12.41 | +2.48 | 0.670 | 0.828 | 0.722 |
| AGGRESSIVE on (a)+(b)+(c)+(d) | 68.14 | +13.88 | +2.78 | 0.697 | 0.840 | 0.733 |

`is_latex` (0.443), `is_sup` (0.047), `is_sub` (0.200), `is_strikeout` (0.000) and
`is_code_block` (0.000) are **identical in every row** — no change here touches them,
exactly as expected, since there is no such markup in the model's output to preserve.

**Where the (a)+(b)+(c) gain comes from, mechanically.** `is_title` does not move at all
(0.789 → 0.789): the benchmark's title rule ignores heading depth, and (c) bolds an inline
label rather than a whole line, so neither change can create a title match. The gain is
entirely `is_bold` (0.418 → 0.526, from (c)) and `hier` (0.642 → 0.692, from (b)).
Component (b) does exactly and only what it was claimed to do.

**Heading-depth census** (element sub-corpus), showing (b) working:

| configuration | total heading lines | `#` | `##` | `###` | `####` |
|---|---|---|---|---|---|
| baseline | 2,174 | 2,174 | 0 | 0 | 0 |
| (a)+(b)+(c) | 2,174 | 1,526 | 296 | 150 | 202 |
| (a)+(b)+(c)+(d) | 3,090 | 2,442 | 296 | 150 | 202 |
| aggressive | 4,847 | 2,941 | 1,554 | 150 | 202 |

Change (c) bolds **575 lines** across the sub-corpus.

### 3.4 The decision on the borderline component (d) — KEEP

The preregistration says: *"If this component's measured contribution is negative or
within ±0.05 we drop it."* Its marginal contribution, measured on top of (a)+(b)+(c):

| dimension | marginal effect of (d) | Overall impact |
|---|---|---|
| Semantic Formatting | +3.45 points | +0.69 |
| Charts | +1.23 points | +0.25 |
| Content Faithfulness | −0.07 points | −0.01 |
| Tables, Visual Grounding | 0 | 0 |
| **net** | | **+0.92** |

**+0.92 Overall is 18× the ±0.05 drop threshold. (d) is kept, and the submitted set is
(a)+(b)+(c)+(d).**

### 3.5 Sensitivity of the two dials that had to be chosen

Reported so the choices are auditable. **Neither was picked after seeing the headline.**

Maximum heading depth for (b) — kept at **4**, the value the previous round's `A1` used,
so it is inherited rather than chosen here:

| max depth | ΔSemFmt on (a)+(b)+(c) | `hier` |
|---|---|---|
| 2 | +5.03 | 0.680 |
| 3 | +5.26 | 0.689 |
| **4 (used)** | **+5.33** | **0.692** |
| 6 | +5.40 | 0.694 |

The dial is nearly flat: the whole 2→6 range spans 0.37 SemFmt points, i.e. 0.07 Overall.

Word cap for (d) — fixed at **20** by the preregistration before measurement:

| word cap | ΔSemFmt on (a)+(b)+(c)+(d) |
|---|---|
| 12 (the shipped cap) | +7.41 |
| **20 (preregistered, used)** | **+8.78** |
| 30 (previous round's choice, rejected) | +10.36 |

The cap is monotone and material — which is precisely why fixing it in advance mattered.
Choosing 30 after the fact would have bought +0.32 Overall and been indefensible.

### 3.6 Transfer evidence, better than the previous round's

Component (c) acts on the final markdown, so it can be measured on **both** corpora. That
gives a direct check on the transfer assumption:

```
change (c) alone, full 476 docs : SemFmt=56.40  dSemFmt=+3.98  dOverall=+0.80
change (c) alone, sub-corpus    : SemFmt=58.23  dSemFmt=+3.97
   -> transfer disagreement 0.004 SemFmt points
```

The two agree to four thousandths of a Semantic-Formatting point — far tighter than the
0.16–0.84-point disagreement the previous round measured for its (larger) markdown
patches. This is evidence *for* transferring the sub-corpus deltas directly, but it is
evidence from a markdown-level change; the provider-level components (b) and (d) still
carry the §8 caveat.

---

## 4. Verification — the reimplementation reproduces the measurement exactly

The measured numbers must belong to the shipped code path, not to a measurement helper.
So the script re-measures everything a second time through
`PatchedNanoEngine.rebuild_markdown` — the method live inference itself calls — fed
elements read back from stored artifacts, and requires an exact match.

```
5. VERIFICATION THROUGH THE PROVIDER SUBCLASS
   baseline (vendored emission) engine SemFmt=54.2556787971  section-2 SemFmt=54.2556787971  MATCH=True
   GENUINE a+b+c                engine SemFmt=59.5857228096  section-2 SemFmt=59.5857228096  MATCH=True
   GENUINE a+b+c+d              engine SemFmt=63.0391857497  section-2 SemFmt=63.0391857497  MATCH=True
   AGGRESSIVE on a+b+c          engine SemFmt=66.6706002317  section-2 SemFmt=66.6706002317  MATCH=True
   AGGRESSIVE on a+b+c+d        engine SemFmt=68.1360466163  section-2 SemFmt=68.1360466163  MATCH=True
   ALL MATCH: True
```

Ten decimal places, five configurations, no mismatch. Note this is a *strong* check only
in combination with §3.2: on its own it would be trivially true (both paths call the same
function); with the drift test it says both that the code is one implementation and that
that implementation is a faithful extension of the vendored one.

What it does **not** verify: the two stages of the live pipeline our replay cannot reach —
that the scoped bindings behave under real inference, and that the layout stage's raw
labels are what we assume. Both need the GPU run.

---

## 5. Collateral on all five dimensions

Content Faithfulness and Charts are re-measured with the benchmark's real rule classes
over patched markdown, against a paired re-assembled baseline. Tables are checked by
byte-identity of every HTML `<table>…</table>` block and every pipe-table row. Visual
Grounding is checked by comparing each element's `(category, bbox, content)` triple before
and after a build — those three fields are the only inputs `layout_pages` is built from
(`kdl_frontier_nano.py:3287-3296`), and our emission code treats the element list as
read-only, so the check is of a structural claim.

```
shipped-markdown reference (the values on our leaderboard row):
  text_content   87.1751  (n=506)
  chart          63.6862  (n=568)
re-assembled paired baseline:
  text_content   87.3744  (n=506)
  chart          63.7993  (n=568)
```

| set | ΔContent Faithfulness | ΔCharts | Tables changed | Visual Grounding changed |
|---|---|---|---|---|
| **GENUINE (a)+(b)+(c)** | **−0.02** | **+0.04** | 0 / 1,074 | 0 / 400 |
| **GENUINE (a)+(b)+(c)+(d)** | **−0.09** | **+1.26** | 0 / 1,074 | 0 / 400 |
| AGGRESSIVE on (a)+(b)+(c) | −0.20 | +0.27 | 0 / 1,074 | 0 / 400 |
| AGGRESSIVE on (a)+(b)+(c)+(d) | −0.23 | +1.36 | 0 / 1,074 | 0 / 400 |

**Preregistration §6 kill criterion — "any patch moves Content Faithfulness, Tables or
Visual Grounding down by more than 0.3 → that patch is dropped": NOT TRIGGERED.** The
submitted set costs 0.09 Content-Faithfulness points, three times inside the limit; the
worst case anywhere in the table is 0.23. Tables and Visual Grounding are unchanged at
every setting.

Two mechanisms worth naming:

* **The Content-Faithfulness cost is a `#` cost, and it is small.** The benchmark's text
  normaliser strips `**` but has no rule for `#`, so heading markers survive into the
  comparison — which is why (d), a heading change, costs 0.07 while (c), a bold change,
  costs essentially nothing. The cost is much milder than raw normalisation would suggest
  because the sentence-level rules independently strip a leading `#{1,6}\s+`.
* **Charts *improves*, for a real reason.** The chart data-point rule will only accept a
  chart's title label if it appears in the pre-table context as bold text or as a heading.
  Our pipeline emits chart titles as plain `Text`, so those labels were invisible and the
  rule fell through to failure. Promoting genuine headings makes some of them visible:
  **+1.26 Charts from the submitted set**, which is 14× its Content-Faithfulness cost.
  This is a defect the benchmark was measuring and we were losing points to.

---

## 6. The aggressive set, re-measured — and a required amendment to the preregistration

Preregistration §4 defines the aggressive set as exactly two changes on top of the
submitted set: short single-line `Text` promoted to `# `, and `List-item` promoted to
`## `. `MAXBOLD` is excluded from every set. Measured with our code, on that definition:

| | Tables | Charts | Content Faith. | SemFmt | Visual Gr. | **Overall** | vs 76.36 |
|---|---|---|---|---|---|---|---|
| Aggressive on (a)+(b)+(c) | 85.76 | 63.96 | 86.98 | 64.83 | 74.19 | **75.15** | −1.21 |
| **Aggressive on (a)+(b)+(c)+(d)** | 85.76 | 65.05 | 86.95 | 66.30 | 74.19 | **75.65** | **−0.71** |

**`PREREGISTRATION.md` §4 states "the aggressive set reaches 76.79 overall". On §4's own
definition of that set, it reaches 75.65 — 1.14 points lower — and it does not clear
76.36.** The 76.79 figure came from the previous round's "Set A", which contained a third
member §4 does not mention: *bold every own-line of ≤40 words*. That member is a bolding
patch, not one of the two heading promotions, and it was the largest single contributor to
the 76.79. §4 needs a dated amendment restating the number as **75.65** for the set it
describes, or restating the set to include the ≤40-word bolding rule if 76.79 is the number
to be disclosed. **This is a correction to the preregistration, not a result, and it must
not be resolved by quietly choosing whichever number is convenient.**

The related figure §4 cites, "a 20-line variant alone reaches 77.01" (MAXBOLD), is
**inherited and was not re-measured here** — `MAXBOLD` was excluded from this round
entirely, as instructed. It should be labelled in the writeup as measured on 2026-08-11 by
the earlier harness, not by this one.

**Why the aggressive set is disclosed and not submitted** (unchanged from §4's reasoning,
and confirmed by the numbers above): the benchmark's bold check accepts an annotated run
appearing anywhere on a `#`-heading line as evidence of bold, because headings render bold.
This pipeline emits **no** inline bold markup of its own, so before change (c) 100% of its
bold credit arrived through that route. Promoting non-headings to headings therefore raises
the bold score without detecting any bold: the aggressive set takes `##` lines from 296 to
1,554 (§3.3's census), the 1,258 additions being list items, and its `is_bold` rises from
0.584 to 0.697 as a result. That is a property of the scorer, not of the parser.

---

## 7. Full five-dimension table — the deliverable

Semantic Formatting = the full-corpus baseline 52.42 plus the sub-corpus delta (§8 bounds
the error). Content Faithfulness and Charts = our shipped values plus their measured
paired deltas. Tables and Visual Grounding = our shipped values, verified unchanged.

| row | Tables | Charts | Content Faith. | **SemFmt** | Visual Gr. | **Overall** | vs 72.65 | vs 76.36 |
|---|---|---|---|---|---|---|---|---|
| our run as shipped | 85.76 | 63.69 | 87.18 | 52.42 | 74.19 | **72.65** | — | −3.71 |
| **GENUINE (a)+(b)+(c)** | 85.76 | 63.73 | 87.16 | **57.75** | 74.19 | **73.72** | **+1.07** | −2.64 |
| **GENUINE (a)+(b)+(c)+(d) — SUBMITTED** | 85.76 | **64.95** | 87.09 | **61.20** | 74.19 | **74.64** | **+1.99** | **−1.72** |
| aggressive on (a)+(b)+(c) *(not submitted)* | 85.76 | 63.96 | 86.98 | 64.83 | 74.19 | 75.15 | +2.50 | −1.21 |
| aggressive on (a)+(b)+(c)+(d) *(not submitted)* | 85.76 | 65.05 | 86.95 | 66.30 | 74.19 | 75.65 | +3.00 | −0.71 |
| published KDL row | 85.56 | 63.41 | 87.19 | 66.81 | 78.84 | 76.36 | — | — |

Per-dimension movement of the submitted set, all five, including where we lose:

| dimension | shipped | submitted set | Δ | direction |
|---|---|---|---|---|
| Tables | 85.76 | 85.76 | 0.00 | unchanged (0 of 1,074 documents' table markup altered) |
| Charts | 63.69 | 64.95 | **+1.26** | gain |
| Content Faithfulness | 87.18 | 87.09 | **−0.09** | **loss** |
| Semantic Formatting | 52.42 | 61.20 | **+8.78** | gain |
| Visual Grounding | 74.19 | 74.19 | 0.00 | unchanged (0 of 400 documents' element triples altered) |
| **Overall** | **72.65** | **74.64** | **+1.99** | |

**Which claim tier applies.** `PREREGISTRATION.md` §5, middle row: the genuine set lands
**between 72.65 and 76.36**, so the claim is a measured improvement of **+1.99 Overall over
our own reproduction of the leader**, plus the defects and the scorer-coupling finding,
and **no ranking claim**. The genuine set does **not** clear 76.36 and does not regress.

**Why no honest emission-level set clears 76.36, arithmetically.** Even at the published
Semantic Formatting of 66.81 exactly, our row would score
`(85.76 + 63.69 + 87.18 + 66.81 + 74.19) / 5 = 75.53` — still 0.83 short. Even at a
perfect Semantic Formatting of 100 it would score 82.16, but the residual 4.65-point
Visual Grounding deficit (74.19 vs 78.84) is untouched by anything in this report. Closing
the gap to the published row is a layout-detection problem and needs the GPU.

---

## 8. What I could not measure, stated explicitly

1. **Component (a), the `section_header` map fix — the single largest gap.** Unmeasurable
   by replay because the model's raw layout label is not persisted (§2). It contributes
   exactly 0 here and might contribute 0 live. Needs one GPU run and a category-census
   diff.
2. **The provider-level components (b) and (d) on 157 of 476 documents.** Their markdown
   cannot be reconstructed byte-exactly because the artifact does not persist
   `picture_path`, so their deltas are measured on 319 documents and transferred. §3.6
   shows a markdown-level change transferring to within 0.004 SemFmt points, and the
   previous round bounded its markdown-level transfer error at 0.16–0.84 points; neither
   is a *measurement* of the provider-level transfer error. **Treat the submitted set's
   74.64 as 74.6 ± 0.2.** The margin over 72.65 (+1.99) is far larger than that band, so
   the direction and rough size of the result are safe; the second decimal is not.
3. **Tables / GriTS was not recomputed**, only asserted invariant by byte-comparing table
   markup. A patch passing that check cannot change GriTS, but I did not re-run the metric.
4. **Visual Grounding's metric was not recomputed**, only its inputs. 0 of 400 documents
   showed any change to an element's `(category, bbox, content)` triple, and the metric is
   a pure function of those triples by code inspection. I did not re-run
   `layout_element_rule_pass_rate`.
5. **Live behaviour of the two scoped bindings** (§1.3) and of the launcher shim under a
   real inference run. Both are exercised only as far as registration and construction;
   neither has been driven against a vLLM endpoint.
6. **The 77.01 MAXBOLD figure in preregistration §4** is inherited from the 2026-08-11
   harness and was not re-measured, per instruction.
7. **Whether the published 66.81 Semantic Formatting run emits different headings.** We
   have no access to the leader's own outputs. Unchanged from the previous round.
8. **Insurance-subset scores** (preregistration §5) were out of scope for this round and
   are unchanged from `reports/insurance_subset_scores.md`.

## 9. Open items for whoever picks this up

1. **Amend `PREREGISTRATION.md` §4** with a dated entry, per §6 above. Do this before the
   writeup quotes either number.
2. **Decide how the writeup describes component (a).** The honest form is "a defect we
   found and fixed whose contribution we could not measure". It must not appear in any
   arithmetic.
3. **There is no git repository at `bfcl-sprint/`**, so nothing in this round could be
   committed in the ordinary sense. The only repository in the tree is the pinned upstream
   `parsebench/` checkout — one upstream commit, with the entire prior replay harness
   sitting untracked (`reports/formatting_gap_closure.md` §1's claim that it is
   "Committed: yes" is inaccurate). Files are written and in place at the paths in §1;
   putting them under version control needs a decision that is not mine to take: either
   initialise a repository at `bfcl-sprint/`, or write into the upstream checkout's
   history. The preregistration promises published reproduction code, so this needs
   resolving before submission.
