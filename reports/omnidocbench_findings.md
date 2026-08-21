# OmniDocBench findings — a first measurement of KDL-nano, a silently broken formula metric, and the measured price of a formatting fine-tune

Date: 19–20 August 2026 (box logs are UTC 20 Aug; local work 19 Aug PT).
Status: measurement + defect report. **This is not a leaderboard claim.**

All numbers in this document were re-verified against files on disk in this session;
every number carries a citation. Paths are relative to
`/Users/amolpant/forecasting_networks/bfcl-sprint/` unless absolute.

Epistemic labels used throughout:
- **[V]** verified this session — the cited file was read, or the cited command was run, here.
- **[A]** session-attested — recorded in the operator checkpoint written during the run
  (`omnidocbench/CHECKPOINT.md`); the primary artifact (e.g. a failed run's log) was not
  retained off the rented machine.
- **[E]** external fetch — a public web page fetched this session, with URL.

Terms, in plain language (defined once, used throughout):
- **OmniDocBench** — a public document-parsing benchmark (opendatalab/OmniDocBench on
  GitHub): given a page image, produce one markdown file; a toolkit scores it against
  human-made reference annotations. We evaluated on **v1.6_full**: 1,651 pages = 1,355
  original pages + 296 "hard" pages (100 equation-hard, 99 layout-hard, 97 table-hard)
  [V: counted from `omnidocbench/dataset/OmniDocBench.json` this session].
- **Edit distance (ED)** — minimum number of single-character insertions/deletions/
  substitutions to turn one string into another, normalized to 0–1 (0 = identical). Lower
  is better.
- **TEDS** (Tree Edit Distance-based Similarity) — a 0–1 table score comparing prediction
  and reference as HTML trees, node by node. Higher is better.
- **CDM** (Character Detection Matching) — a formula score that *renders* both the
  predicted and reference LaTeX (a typesetting language for mathematics) to images and
  matches the drawn characters visually. Higher is better. Rendering happens through
  `pdflatex`, the LaTeX-to-PDF compiler from TeX Live (the standard TeX software
  distribution).
- **Overall** — the benchmark's headline: `((1 − text ED) × 100 + TEDS × 100 + CDM × 100) / 3`
  [E: formula confirmed on the OmniDocBench GitHub README, fetched this session].
  Reading order is reported but not part of Overall.
- **KDL-nano** — shorthand for the 1.2-billion-parameter document-parsing vision-language
  model from KoreaDeepLearning that our ParseBench work builds on (served under the name
  `kdl-frontier-parser-nano`); "base" below means its unmodified weights.
- **it7** — our formatting-targeted fine-tune of that model (a LoRA adapter — low-rank
  adaptation, small correction matrices trained on top of frozen weights — merged into the
  weights), the model from the companion ParseBench paper (`FINDINGS_PAPER.html`).
- **GT** — ground truth, the benchmark's human-made reference annotations.

---

## 1. The three findings

1. **First OmniDocBench measurement of KDL-nano: Overall 80.49** (sample-weighted; 82.78
   under the leaderboard's own page-averaged convention — see §4.1) on the full 1,651-page
   corpus. That is mid-pack: 15.85 points behind the self-reported leader
   (PaddleOCR-VL-1.6 at 96.34) on the mixed-convention comparison, 13.56 behind on the
   same-convention comparison. The model does not appear on the public leaderboard; we
   are not aware of any prior OmniDocBench measurement of it.
2. **A six-defect environment chain under the CDM formula metric, ending in a silent
   zero.** On a stock Ubuntu 22.04 machine (Debian-family, TeX Live packaged from a
   February 2022 snapshot), the toolkit's formula renderer colors every token with the
   LaTeX command `\mathcolor` — which did not exist in that TeX stack. Every formula
   renders uncolored, every bounding box comes back empty, and **CDM reports 0.0 for
   every formula while reporting zero errors** (the run's own debug block:
   `sample_count: 66, exception_case_count: 0`). Five more mundane defects had to be
   fixed first to even reach that state. All six were fixed; the fixed environment
   produced the numbers in finding 1.
3. **A formatting fine-tune has a measurable price on a formatting-blind benchmark:
   −1.17 Overall.** it7 — trained to emit inline formatting that ParseBench rewards —
   scores 79.32 against the base model's 80.49 under identical serving, identical
   prompts, identical scoring. OmniDocBench's text normalizer deletes markup before
   scoring, so none of what it7 learned can help here, and what it displaced costs
   points in all three scored dimensions. We measured the specialization tax instead of
   hiding it.

---

## 2. What was measured

Two models, one benchmark, one environment:

- **base**: KDL-nano unmodified weights, served with vLLM (an open-source
  high-throughput model server exposing an OpenAI-compatible HTTP API) on a rented
  Vast.ai H100 GPU box, `max-num-seqs 128`, served name `kdl-frontier-parser-nano`,
  endpoint `127.0.0.1:18000` over an SSH tunnel [A: `omnidocbench/CHECKPOINT.md:4`].
- **it7**: the merged fine-tune from `it7_merged/`, served identically — same vLLM
  launch configuration, same served name, same port, same driver command; only the
  weights directory changed [A: `omnidocbench/CHECKPOINT.md:4,15`].
- **Scoring**: the upstream toolkit at a pristine checkout — `git log` shows upstream
  commit `193627a` (opendatalab/OmniDocBench), `git status`/`git diff` show **zero
  modifications outside its `result/` output directory** [V: run this session in
  `omnidocbench/toolkit/`].

## 3. Method

### 3.1 Emission profile (pure post-processing, no model change)

Our pipeline's markdown dialect differs from what the toolkit's extractor parses. Three
mismatches were found by reading the toolkit before spending any GPU money
(`reports/omnidocbench_feasibility.md`, written 2026-08-19) and fixed by a pure
post-processing profile, `ourparser/omnidoc_profile.py` (19/19 unit tests pass
[V: `.venv/bin/pytest ourparser/tests/test_omnidoc_profile.py` run this session]):

1. **Fenced formula blocks would have zeroed the formula dimension.** Our pipeline emits
   display formulas as ```` ```latex ```` fenced code blocks
   [V: `_nano_format_formula`,
   `parsebench/src/parse_bench/inference/providers/parse/kdl_frontier_nano.py:2911-2917`].
   The toolkit's extractor recognizes formulas only inside `$$…$$`, `\[…\]`, `$…$`,
   `\(…\)` [V: `display_reg`, `omnidocbench/toolkit/src/core/preprocess/extract.py:66-77`]
   — a fenced block is not a formula to it, so every display formula we emit would have
   been invisible to the formula matcher, and unmatched GT formulas score zero. The
   profile unwraps the fence and adds `$$…$$` when no delimiters are present; the LaTeX
   body passes through byte-for-byte.
2. **HTML superscript/subscript tags survive text normalization as garbage.** The
   toolkit's `clean_string` deletes every character that is not a letter/digit/
   underscore/Chinese character [V: `omnidocbench/toolkit/src/core/preprocess/
   data_preprocess.py:776-782`], so `E = mc<sup>2</sup>` becomes `Emcsup2sup` — the tag
   letters remain as edit-distance noise (executed demonstration in
   `reports/omnidocbench_feasibility.md`, Q1 table). GT writes super/subscripts as
   inline LaTeX `$...$` (3,644 GT texts carry it; zero GT text annotations carry
   `<sup>`/`<sub>` — measured over all 26,778 non-ignored text annotations, feasibility
   Q1). The profile converts `<sup>x</sup>` → `$^{x}$` and `<sub>x</sub>` → `$_{x}$` in
   running text, leaving tables alone (where tags are stripped on both sides and are
   provably neutral, `data_preprocess.py:505-506`).
3. **Emphasis markers inside table cells** are not stripped by the cell normalizer and
   GT cells carry none, so `**bold**` in a cell is a pure penalty; the profile strips
   `**`/`~~` inside table regions only.

### 3.2 Subset probe before the full spend

Before committing to the full run we measured a **50-page stratified sample**: seed
20260819, strata = data source × language, largest-remainder proportional allocation
[V: `omnidocbench/subset50/sampling_manifest.json`]. Results (base model):
text ED 0.0393, TEDS 0.9617 on 22 tables, CDM 0.6199 on 66 formula samples
[V: `omnidocbench/toolkit/result/pred_omnidoc_quick_match_metric_result.json`;
CDM from `omnidocbench/box_results/root/cdm_smoke6.log:37`]. Projected Overall ≈ 84.7,
which cleared the pre-registered GO gate (text ED ≤ 0.15, TEDS ≥ 0.70,
`reports/omnidocbench_feasibility.md`, GO/NO-GO section) — so the full run was funded.
The probe's optimism is quantified honestly in §5.

### 3.3 Empty-page sweep discipline over a flaky tunnel

The evaluator scores a **missing prediction file as an empty page**, not a skipped one
[V: `omnidocbench/toolkit/src/dataset/end2end_dataset.py:2017` —
`'!!!WARNING: No prediction for {img_name}, evaluate as empty page'`]. Inference ran
from a laptop through an SSH tunnel to the GPU box, and tunnels drop. The driver
(`ourparser/run_omnidoc.py`) therefore writes each page atomically (temp file + rename)
and treats an existing file as done, so a killed run restarts cleanly; after each run a
sweep pass deleted zero-byte files and re-ran the gaps. Sweep summaries: base
`done=143 skip=1508 fail=0`, it7 `done=181 skip=1470 fail=0`
[V: `omnidocbench/logs/full_base_sweep.log`, `full_it7_sweep.log`, last lines]. Final
state: **1,651 prediction files per model, zero empty** [V: counted this session with
`find … -name "*.md" | wc -l` and `-size 0`]. The scorer matched all 1,651 pages with
zero matching timeouts or fallbacks for both models [V: `match_debug` in both
`omnidocbench/box_results/result/pred_{base,it7}_quick_match_metric_result.json`].

### 3.4 Scoring runs

Both full scoring runs (with CDM) executed on the fixed GPU-box environment; the
authoritative outputs were copied back to
`omnidocbench/box_results/result/pred_{base,it7}_quick_match_metric_result.json` along
with the toolkit's own runtime-environment fingerprints
(`…_runtime_environment.json`) and stage-execution accounting. Both runs report zero
timeouts, zero errors, zero exceptions in every metric stage
[V: `metric_debug` blocks in both metric_result files: CDM `sample_count: 2352`,
TEDS `sample_count: 665`, all error counts 0].

## 4. Results

### 4.1 Full corpus (1,651 pages)

| Dimension (direction) | base | it7 | Δ (it7 − base) |
|---|---|---|---|
| Text edit distance (↓) | 0.0761 | 0.0908 | +0.0147 |
| Table TEDS (↑) | 0.8491 | 0.8406 | −0.0085 |
| Formula CDM (↑) | 0.6418 | 0.6298 | −0.0120 |
| Reading-order edit distance (↓, not in Overall) | 0.1730 | 0.1831 | +0.0101 |
| **Overall, sample-weighted** | **80.49** | **79.32** | **−1.17** |
| Overall, leaderboard convention (page-averaged) | 82.78 | 81.08 | −1.69 |

Sources [V]: base row values from
`omnidocbench/box_results/result/pred_base_quick_match_metric_result.json`
(text `ALL_page_avg` 0.07608850435924092; TEDS `all` 0.8490607133046941; CDM `all`
0.6418312074829932; reading order 0.17298081628304407); it7 from
`…/pred_it7_quick_match_metric_result.json` (0.09077664097094384 /
0.84064528531666 / 0.6298142006802722 / 0.1831033486449119). Overall recomputed this
session from those raw values: base ((1−0.076089)+0.849061+0.641831)/3×100 = 80.4934;
it7 = 79.3228.

**The two conventions, stated plainly** (this matters for any leaderboard comparison):
the benchmark's TEDS and CDM can be aggregated per *sample* (every table/formula counts
once — the `all` field) or per *page* (average per page, then across pages — the `page`
field). The upstream leaderboard's own table-generator notebook uses the **page**
convention [V: `omnidocbench/toolkit/tools/generate_result_tables.ipynb`, cell 2, read
this session — it takes `result[category]["page"][metric]["ALL"]`], and the leader's
leaderboard row is arithmetically consistent with it
(((1−0.0326)×100 + 97.5304 + 94.7619)/3 = 96.34 [E: row fetched from the OmniDocBench
GitHub README this session]). Our run summaries record both: sample-weighted 80.49/79.32
(computed above) and page-averaged 82.775/81.081 [V: `overall_notebook` in
`…/pred_base_quick_match_run_summary.json` and `…/pred_it7_quick_match_run_summary.json`].
We headline the **lower, sample-weighted** number; the same-convention gap to the leader
is 96.34 − 82.78 = **13.56**, the mixed-convention gap 96.34 − 80.49 = **15.85**.

Page denominators for context [V: `page_denominators` in the base run summary]: 1,557
pages carry scored text, 313 carry formulas, 458 carry tables, 1,638 carry reading
order; 2,352 formula samples, 665 table samples.

### 4.2 Placement

Self-reported rows from the public v1.6_full leaderboard [E: OmniDocBench GitHub README,
fetched this session]: PaddleOCR-VL-1.6 (0.9B, Apache-2.0 license; the license and a
96.33-on-v1.6 figure also on its Hugging Face model card, fetched this session) **96.34**;
olmOCR 85.74; Mistral OCR 85.66; Nanonets-OCR-s 83.61; POINTS-Reader 83.37; Marker 78.44.
KDL-nano at 82.78 (page-averaged, the comparable convention) sits between POINTS-Reader
and Marker: mid-pack among specialized systems, far from the leader. **We did not
reproduce the leader's number**; every leaderboard figure above is self-reported by the
respective team or the benchmark maintainers.

### 4.3 The feasibility predictions, scored

The pre-run feasibility analysis (`reports/omnidocbench_feasibility.md`, written before
any GPU spend) made checkable predictions; here is how they fared:

- Overall band **78–88** ("low confidence, ±8") → landed **80.49**. Inside the band.
- "Markup mostly neutral, but `<sup>`/`<sub>` is a penalty and inline LaTeX is the
  GT-matched encoding" → confirmed by the executed normalizer demonstration; fixed in
  the profile before the run.
- "Fenced formula blocks are a zero-score risk" → confirmed against the extractor
  regex; fixed in the profile before the run.
- "Formula third is the widest unknown (CDM 60–85)" → landed 64.18, low end of the band.
- "Pipe tables cap the table third near ~75–85 TEDS" → **wrong in our favor**: 84.91,
  at the top of the band, despite 39% of GT tables containing merged cells that pipe
  syntax cannot express (258/665, measured in feasibility Q3).

## 5. The subset probe drifted, and by how much

| Metric | 50-page probe | Full corpus | Drift |
|---|---|---|---|
| Text ED (↓) | 0.0393 | 0.0761 | ~1.9× worse on full |
| TEDS (↑) | 0.9617 (22 tables) | 0.8491 (665 tables) | −0.113 |
| CDM (↑) | 0.6199 (66 samples) | 0.6418 (2,352 samples) | +0.022 |
| Overall (sample conv.) | 84.74 | 80.49 | −4.25 |

[V: probe values §3.2; full values §4.1; probe Overall recomputed this session.]

The stratification was by page *type* (source × language), which cannot control the
within-stratum tail: the full corpus's hardest text pages (handwriting ED 0.389,
fuzzy-content ED 0.300 [V: base metric_result, text page groups]) are nearly absent from
50 pages, and 22 tables is far too few to price 665 (the probe's TEDS was 0.11 too
optimistic). CDM, the dimension the probe existed to de-risk, transferred almost exactly
(+0.02). Lesson recorded: a 50-page probe is a go/no-go instrument, not a forecast; its
text and table numbers were materially easier than the corpus it sampled.

## 6. The six-defect chain (forensic narrative)

Setting: a stock Vast.ai rental, Ubuntu 22.04.5 LTS (a Debian-family Linux), with the
distribution's own packages: `texlive-base 2021.20220204` (identifies itself as "TeX
Live 2022/dev/Debian"), ImageMagick 6.9.11-60 (the standard command-line image
converter), Ghostscript 9.55 [V: all from
`omnidocbench/box_results/result/pred_base_quick_match_run_summary.json`,
`runtime_environment` block — the toolkit's own fingerprint of the machine that produced
our numbers]. The toolkit's README recommends a Docker image or a hand-built TeX Live
2025 + ImageMagick 7 stack [V: `omnidocbench/toolkit/README.md:337-465`]; like, we
suspect, many self-evaluators, we started from what `apt install` provides. Six defects
stood between that machine and a correct CDM number. Each fix is listed with its
evidence status.

1. **ImageMagick's security policy blocks PDF conversion.** Debian-family systems ship
   a `policy.xml` that denies ImageMagick the PDF coder (a Ghostscript-vulnerability
   mitigation), so CDM's PDF→PNG step fails outright. The toolkit's README documents
   this exact edit for ImageMagick 7 [V: `README.md:461-465`]; on the box the
   ImageMagick 6 policy file needed the same surgery [A]. Symptom: conversion errors.
   Loud, at least.
2. **A 1,024 file-descriptor limit crashes the render workers.** (A file descriptor is
   the operating system's handle for an open file or pipe; the default per-process cap
   is 1,024.) The CDM stage runs parallel render workers; the crash presents as
   `OSError: Too many open files` in the renderer and, confusingly, as
   `AssertionError: can only join a started process` in the TEDS stage, because a
   worker that failed to start is later joined [A]. Fix: `ulimit -n 65535`, which the
   operator checkpoint bakes into the rerun instructions [V:
   `omnidocbench/CHECKPOINT.md:16`].
3. **`filelock` ≥ 3.20 raises on every render subprocess spawn.** The filelock library's
   newly added fork-safety guard (it refuses to be inherited across a process fork)
   fires each time a render worker spawns [A]. Fix: pin an older filelock; the final
   environment's package fingerprint contains no filelock at all [V: `python_packages`
   in the run summary].
4. **ImageMagick 6 has no `magick` binary.** The toolkit shells out to `magick`
   [V: `omnidocbench/toolkit/src/metrics/cdm/modules/latex2bbox_color.py:208,214`];
   ImageMagick 6 installs `convert`. Fix: a shim — the environment fingerprint shows
   `magick` at `/usr/local/bin/magick` reporting "ImageMagick 6.9.11-60" while the apt
   binaries live in `/usr/bin` [V: `external_tools` in the run summary; ImageMagick 6
   does not install a `/usr/local/bin/magick`, so this is the installed wrapper].
5. **matplotlib is imported but was not installed.** The plotting library is imported
   unconditionally by the toolkit's table preprocessing
   [V: `omnidocbench/toolkit/src/core/preprocess/table_utils.py:1,5`] and is absent from
   a minimal install [A]. Fix: `pip install matplotlib`; the final environment carries
   3.11.1 [V: run summary].
6. **The killer: `\mathcolor` does not exist on that TeX stack — and nothing says so.**
   This one produced *plausible-looking wrong numbers* rather than errors, which is why
   it gets its own section.

## 7. Anatomy of a silent zero

**What the toolkit does.** To find each rendered token, CDM's renderer wraps every
token of both prediction and GT LaTeX in a distinct color using the `\mathcolor`
command [V: `omnidocbench/toolkit/src/metrics/cdm/modules/latex_processor.py:347-374`],
compiles through a template that loads the `xcolor` color package
[V: `latex2bbox_color.py:33`, `\usepackage{xcolor}`], then locates each token's
bounding box by finding its color's pixels in the rendered image
[V: `latex2bbox_color.py:715`].

**What the environment had.** `\mathcolor` entered LaTeX's color support with the
2022-06-01 LaTeX release; the xcolor package picked it up in version 2.14, dated
2022-06-12 — its changelog reads "Load if it exists the code from LaTeX to define
\mathcolor" [E: xcolor ChangeLog fetched from CTAN this session]. Ubuntu 22.04's TeX
Live is a **February 2022** snapshot (`texlive-base 2021.20220204` [V: run summary]) —
months too old on both counts. On that stack `\mathcolor` is an undefined command.

**Why nothing failed.** The renderer invokes `pdflatex -interaction=nonstopmode`
[V: `latex2bbox_color.py:675`] — "log errors and keep going." An undefined command is
logged inside the `.tex` job's log, but a PDF is still produced, with every token in
default black. The toolkit checks only that the PDF file exists
[V: `latex2bbox_color.py:689-695`]; it parses the log only for page counts and overfull
boxes [V: `_parse_pdflatex_log`, `latex2bbox_color.py:229-251`]. The color-based box
extraction then finds no colored pixels, and the per-token bounding-box file is written
with empty boxes, without any error path being taken
[V: `latex2bbox_color.py:715-723`]. Downstream, every formula scores 0.0. The harness's
own error accounting — timeouts, errors, exceptions — remains pristine, because nothing
threw: the broken 50-page probe reported CDM 0.0 across the board [A: five failed smoke
runs preceded the retained sixth; their logs were not copied off the box] while the
identical accounting structure shows what it showed then and after the fix —
`sample_count: 66 … exception_case_count: 0`
[V: `omnidocbench/box_results/root/cdm_smoke6.log:340-360`, the fixed run, CDM 0.619879
at line 37 of the same log].

**The fix.** Install a current `xcolor.sty` into the user's local TeX tree
(`/root/texmf`) [A: `omnidocbench/CHECKPOINT.md:11`]; the very next smoke run returned
CDM 0.6199 with the same zero-exception accounting [V: `cdm_smoke6.log`].

**The implication, stated carefully.** Any CDM figure computed on a TeX stack older
than mid-2022 — which includes the stock TeX of Ubuntu 22.04, still a common server
image in 2026 — *may* be silently zeroed or partially zeroed, and the run's own outputs
give no sign. We do not claim any specific published number is affected; we cannot know,
and a fully zeroed formula dimension would usually be noticed by its implausible
magnitude. The dangerous case is the partial or unnoticed one. What we can say
precisely: the failure mode exists, it is silent by construction on the evaluator's
side, and we hit it on the most ordinary environment imaginable. A nuance in fairness
to the maintainers: the repository *ships* an environment test that would catch this —
`tools/test_environment_and_smoke.py` asserts CDM ≈ 1.0 on identical LaTeX and pins the
TeX Live year [V: read this session] — but it is opt-in, and the scoring entry point
(`pdf_validation.py`) never invokes it. Our disclosure (§10, Appendix A) proposes making
a one-formula canary mandatory in-band.

## 8. The it7 negative transfer, priced per dimension

it7 was trained (for ParseBench, see `FINDINGS_PAPER.html` §8b) to emit inline
formatting — bold, superscript, subscript — that its base prompts never request.
OmniDocBench is formatting-blind by construction: `clean_string` deletes markup from
both sides before text scoring (§3.1). So the fine-tune's entire learned behavior is,
at best, invisible here. It measured worse than invisible:

| Dimension | Change on the dimension's own 0–100 scale | Contribution to ΔOverall (÷3) |
|---|---|---|
| Text (ED 0.0761 → 0.0908) | −1.47 | −0.49 |
| Tables (TEDS 0.8491 → 0.8406) | −0.84 | −0.28 |
| Formulas (CDM 0.6418 → 0.6298) | −1.20 | −0.40 |
| **Overall** | **mean = −1.17** | **sum = −1.17** |

[V: recomputed this session from the two metric_result files. Overall is the mean of
the three dimension scores, so each dimension contributes one third of its own change;
the middle column averages to −1.17 and the right column sums to it.]

The direction is convention-robust (−1.17 sample-weighted, −1.69 page-averaged [V: run
summaries]). One nuance worth recording: *page-averaged* CDM barely moved (0.6701 →
0.6712 [V: `page` blocks in both metric_result files]) while sample-weighted CDM fell —
it7's formula losses concentrate on formula-dense pages. Reading order also worsened
(0.1730 → 0.1831), outside Overall.

This is the honest counterpart to the ParseBench result: the same weights that gained
+4.04 there (corrected 2026-08-21 from +4.30 after the maintainer's review of PR #99
found two emission defects on our side; see `reports/pr99_defect_response.md`) cost
−1.17 here. Specialization has a price, and a fine-tune sold as "free improvement"
should be required to show this table for a benchmark it was not tuned for.

## 9. Limitations

1. **One run per model.** No repeat runs, no variance estimate. ParseBench experience
   (two full runs agreeing to |Δ| = 0.06) suggests run-to-run noise well below the
   −1.17 transfer effect, but that is an inference from a different benchmark with a
   deterministic scorer, not a measurement here.
2. **The leader's number is self-reported and not reproduced by us.** 96.34 is the
   OmniDocBench README leaderboard row (96.33 on the model's own card) [E]. Our
   ParseBench work showed published and locally-measured numbers for the *same*
   pipeline can differ by 3.71 points; the 13.56–15.85 gap here is far larger than
   that, so the qualitative conclusion (mid-pack, far from the leader) is robust, but
   the gap's second digit is not meaningful.
3. **Aggregation convention.** Our headline 80.49 uses sample-weighted TEDS/CDM; the
   public leaderboard's generator uses page-averaged (82.78 for us). We report both;
   comparisons in this document say which is used at each point (§4.1).
4. **Subset-to-full drift.** The 50-page probe overestimated Overall by 4.25 points
   (§5). Any future probe of this corpus should oversample tables and hard-tail text
   pages, or be treated strictly as a gate.
5. **Session-attested links in the defect chain.** The six defects were each diagnosed
   and fixed live on the rented box; the failed runs' logs (smoke runs 1–5) were not
   retained. What survives on disk: the fixed environment's full fingerprint, the fixed
   smoke run's log, the operator checkpoint enumerating all six fixes
   [V/A as labeled in §6], and — for the killer — the complete code-level mechanism,
   verified line by line in the pristine upstream checkout this session (§7). The
   broken-state CDM 0.0 aggregate itself is attested, not retained.
6. **Cost accounting.** GPU spend ≈ **$16.64 ≈ $17** = 5.2 instance-hours × $3.20/hr.
   The hourly rate is verified [V: `omnidocbench/CHECKPOINT.md:2`]; the 5.2 hours is
   session accounting, consistent with the box's 6-hour watchdog hard cap
   [V: `CHECKPOINT.md:3`] and the retained on-box log span (02:28–06:11 UTC plus prior
   serving/inference time). Label: estimate. Laptop-side CPU evaluation time is not
   priced.

## 10. Disclosure plan

File one issue against `opendatalab/OmniDocBench` (draft below), leading with the
silent-zero mechanism and proposing an in-band environment canary. The other five
defects appear as supporting context — several are already half-documented in their
README, and defect 1's fix is documented there for ImageMagick 7. We are deliberately
*not* proposing they support old TeX stacks; we are proposing the evaluator refuse to
emit a number when its renderer is broken. Timing: after this document is reviewed;
the issue text is self-contained.

---

## Appendix A — draft GitHub issue

> **Title:** CDM silently scores 0.0 for every formula on pre-2022-06 TeX stacks
> (`\mathcolor` undefined) — please add an in-band render canary
>
> **Environment (real, common):** Ubuntu 22.04.5 LTS with the distribution's own
> packages: `texlive-base 2021.20220204` (pdfTeX reports "TeX Live 2022/dev/Debian"),
> ImageMagick 6.9.11-60, Ghostscript 9.55. Toolkit at commit `193627a`, unmodified.
>
> **What happens:** every CDM sample scores 0.0, and the run completes cleanly —
> `metric_debug` reports `timeout_case_count: 0, error_case_count: 0,
> exception_case_count: 0`. Nothing in the run output indicates a fault. On a mixed
> corpus the Overall number this produces looks entirely plausible.
>
> **Mechanism:**
> 1. `latex_processor.py` wraps every token in `\mathcolor{…}` (token coloring for
>    box extraction); the render template loads `xcolor`
>    (`latex2bbox_color.py`, `\usepackage{xcolor}`).
> 2. `\mathcolor` only exists since the 2022-06-01 LaTeX release / xcolor 2.14
>    (2022-06-12, per the xcolor ChangeLog). Ubuntu 22.04's TeX Live is a February
>    2022 snapshot, so the command is undefined.
> 3. `pdflatex` runs with `-interaction=nonstopmode` (`latex2bbox_color.py:675`): the
>    undefined-command error is logged but a PDF is still produced, all tokens black.
> 4. The code checks only that the PDF exists (`latex2bbox_color.py:689-695`); the log
>    is parsed only for page count/overfull (`_parse_pdflatex_log`). Color-based box
>    extraction finds no colored pixels; an all-empty bbox file is written with no
>    error path taken (`latex2bbox_color.py:715-723`). Every formula scores 0.
>
> **Repro:** on stock Ubuntu 22.04, `apt install texlive-latex-extra …`, fix the five
> mundane blockers (ImageMagick PDF policy, `ulimit -n`, filelock pin, `magick` shim
> for IM6, `pip install matplotlib`), run any end2end config with CDM enabled. All CDM
> = 0.0, zero errors reported. Installing a current `xcolor.sty` into the local texmf
> tree immediately restores correct scores (we measured 0.0 → 0.62 on the same 66
> formulas).
>
> **You already have the check — it just isn't wired in.**
> `tools/test_environment_and_smoke.py::test_cdm_identical` asserts CDM ≈ 1.0 on
> identical LaTeX and would have caught this, but `pdf_validation.py` never runs it,
> and hand-built environments (the common case outside your Docker image) are exactly
> the ones that skip it.
>
> **Proposed fixes, smallest first:**
> 1. **In-band canary:** before the CDM stage, render one known formula (e.g. `x^2`)
>    and assert its self-CDM ≈ 1.0; abort with a clear message otherwise. ~10 lines.
> 2. **Count silence as failure:** when a sample's bbox file contains only empty
>    boxes, increment an `empty_render_count` in `metric_debug` instead of scoring a
>    clean 0.0, and warn when it is >0 (a legitimately uncompilable prediction should
>    fail visibly on the *pred* side only — an empty *GT* render is always an
>    environment fault).
> 3. Optionally invoke the existing environment version test from `pdf_validation.py`
>    as a warning, not an assertion.
>
> We're happy to PR option 1+2 if the approach is acceptable. Full write-up with
> file:line citations available.

---

## Appendix B — source ledger (every number's file of record)

| Claim | File |
|---|---|
| base full-corpus metrics | `omnidocbench/box_results/result/pred_base_quick_match_metric_result.json` |
| it7 full-corpus metrics | `omnidocbench/box_results/result/pred_it7_quick_match_metric_result.json` |
| environment fingerprint, page denominators, notebook Overall | `…/pred_{base,it7}_quick_match_run_summary.json` |
| subset probe (text/TEDS) | `omnidocbench/toolkit/result/pred_omnidoc_quick_match_metric_result.json` |
| subset CDM 0.6199, 66 samples, fixed-run accounting | `omnidocbench/box_results/root/cdm_smoke6.log` |
| sampling protocol | `omnidocbench/subset50/sampling_manifest.json` |
| sweep discipline | `omnidocbench/logs/full_base_sweep.log`, `full_it7_sweep.log` |
| six-fix enumeration, box rate, serving config | `omnidocbench/CHECKPOINT.md` |
| CDM mechanism | `omnidocbench/toolkit/src/metrics/cdm/modules/latex2bbox_color.py`, `latex_processor.py` |
| extractor/normalizer behavior | `omnidocbench/toolkit/src/core/preprocess/extract.py`, `data_preprocess.py`, `end2end_dataset.py` |
| leaderboard convention | `omnidocbench/toolkit/tools/generate_result_tables.ipynb` cell 2 |
| pre-registered-style predictions | `reports/omnidocbench_feasibility.md` |
| emission profile + tests | `ourparser/omnidoc_profile.py`, `ourparser/tests/test_omnidoc_profile.py` |
| our fenced-formula emitter | `parsebench/src/parse_bench/inference/providers/parse/kdl_frontier_nano.py:2911-2917` |
| leader score/license | OmniDocBench GitHub README; huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6 (both fetched 2026-08-19/20) |
| xcolor `\mathcolor` history | CTAN xcolor ChangeLog (fetched this session) |
