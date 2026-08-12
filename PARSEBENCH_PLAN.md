# Target: state-of-the-art open-weight model on ParseBench

Written 2026-08-11. This supersedes BFCL as the headline target. BFCL work is retained as a
credibility artifact (the timeout-contamination finding), not as the claim.

## Why this board

**The claim available:** *"state-of-the-art open-weight model for enterprise document parsing"* —
on a benchmark whose corpus includes insurance rate filings. One qualifier deep, on a live and
current board, and it is literally the first stage of the product pipeline rather than a trophy.

### Verified directly (2026-08-11)

- Dataset `llamaindex/ParseBench`: **11,614 downloads, 116 likes, 2,113 files**, last modified
  2026-04-19. Eval framework: `github.com/run-llama/ParseBench`. Paper: arXiv 2604.08538.
- **Insurance content is real: 197 of 2,113 corpus files match insurance.** Confirmed filenames
  include `docs/table/SERFF_CA_random_pages*` (California's System for Electronic Rate and Form
  Filing — actual insurance rate filings),
  `modeling-insured-catastrophe-loss-a-global-perspective-for-2025`,
  `2025-mid-year-property-casualty-and-title-insurance-industries-analysis-report`,
  `airmic-explained-artex-captive-insurance-v2`.
- Corpus: ~2,000 human-verified pages from *"publicly available enterprise documents spanning
  insurance, finance, government."* Doc categories on disk: `chart`, `layout`, `table`, `text`.
- **Submission is self-serve**, verbatim from the dataset card: *"To contribute a model's score,
  open a PR on the model's HuggingFace repo adding a `.eval_results/parsebench.yaml` file."*
  No form, no email, no gatekeeper. Inclusion requires the model be publicly accessible (open
  weights or self-serve API) and finish a run in *"roughly single-digit hours."*
- **Evaluation is deterministic** — the README states it does **not** use an LLM judge. So running
  it costs GPU time only, and scores cannot drift with a judge model.
- **Five dimensions**, with exact scale:

| Dimension | Metric | Pages | Docs | Rules |
|---|---|---:|---:|---:|
| Tables | GTRM (GriTS + TableRecordMatch) | 503 | 284 | continuous |
| Charts | ChartDataPointMatch | 568 | 99 | 4,864 |
| Content Faithfulness | omissions / hallucinations / reading-order | 506 | 506 | 141,322 |
| Semantic Formatting | bold, strikethrough, super/subscript, titles, LaTeX, code | 476 | 476 | 5,997 |
| Layout (Visual Grounding) | Element Pass Rate (IoA + classification + attribution) | 500 | 321 | 16,325 |

### From research, NOT personally verified — confirm before relying on

- Top overall: LlamaParse Agentic **84.88** (the benchmark owner's own product).
- **#1 open-weight: `KDL-Frontier-Parser-nano` at 76.36 — a 1.16B model**, above a 35B model
  (74.28) and Gemini 3 Flash (75.05).
- 21 leaderboard entries, ~20 submitted by the maintainer; one outsider entry took a top-5 slot.
- **Weak dimensions: Semantic Formatting best open-weight ~66.81** (AWS Textract 3.71, Docling
  1.03); **Charts — most parsers under 6%.**
- The winning outsider entry was a pipeline, not a monolithic model — their words: *"2-stage,
  multi-region pipeline: layout detection on a 1036×1036-resized page → per-region crops →
  per-category recognition requests (text / table / picture / formula, each with its own prompt and
  decode params) → deterministic rule-based post-processing."*
- Maintainers reproduce submissions: on that outsider PR they found a 20-point gap, demanded
  reproduction code, re-ran all five dimensions, and corrected one metric downward.

**Step 0 is therefore: fetch the live leaderboard and confirm the four numbers above.** The plan's
target depends on them.

## The attack: two near-empty dimensions

The aggregate averages five dimensions. Three (Tables, Content Faithfulness, Visual Grounding) are
contested. Two are nearly unclaimed, and both are rule-checkable:

1. **Semantic Formatting (476 pages, 5,997 discrete rules).** Best open weight ~66.81; commercial
   APIs score 1–4. This is preservation of bold, strikethrough, superscript/subscript, titles,
   LaTeX, and code blocks in the Markdown output. **Much of this is likely post-processing
   discipline rather than model capability** — a rendering problem, not a vision problem. Cheapest
   points on the board, possibly with no training at all.
2. **Charts (568 pages, 4,864 rules).** Most parsers under 6%. Exact data-point extraction with
   correct labels from bar/line/pie/compound charts. Harder — needs real visual reasoning — but the
   floor is so low that any genuine capability is a large aggregate gain.

Moving Semantic Formatting from ~66 to ~85 and Charts from ~6 to ~30 shifts the aggregate
materially without touching the other three dimensions.

## Steps

**0. Confirm the board (1 hour, $0).** Fetch live entries and per-dimension scores. Establish the
exact number to beat for #1 open-weight. If the gap is already larger than reported, re-scope before
spending anything.

**1. Baseline (half day, ~$20).** Clone the eval framework, run an off-the-shelf open parser
(Qwen3-VL class, or an existing open parser) on all five dimensions on the rented H100. Record
per-dimension scores. Eval is deterministic so this is repeatable and cheap.

**2. Per-rule diagnosis (half day, $0).** Semantic Formatting has 5,997 discrete rules and Charts
4,864 — so failures are enumerable, exactly like the BFCL Java taxonomy. Classify what is failing:
model capability, pipeline routing, or output post-processing. **Expect a large share of Semantic
Formatting to be post-processing.**

**3. Build the pipeline (1–2 days).** Follow the shape that already won: layout detection → region
crops → per-category handling (text / table / chart / formula, each with its own prompt and decode
settings) → deterministic post-processing that preserves formatting markers. This is scaffold
engineering, which is the team's strength, and it does not require a large training run.

**4. Targeted fine-tune only if diagnosis demands it (1–2 days, $100–300).** LoRA on the chart
dimension is the likely candidate, since data-point extraction is a genuine capability gap.
Synthetic training data is straightforward — render charts with known underlying values.

**5. Submit (half day).** Add `.eval_results/parsebench.yaml` to your own model repo via PR.
Publish reproduction code alongside, because the maintainers will re-run it. Budget 2–3 days of
review iteration. That review is a feature: a score that survives it is worth ten self-reported
ones.

## Claim discipline

- The honest claim is **"#1 open-weight on ParseBench"**, not "#1 overall" — LlamaIndex's own
  commercial product leads the board at ~84.88 and they own the benchmark. Say so plainly. Being
  best open-weight is the more useful claim for insurance anyway (data sovereignty, auditability,
  self-hosting).
- Report all five dimensions including where you lose. Publishing losses is what makes the win
  credible.
- Report per-dimension deltas against the baseline so the gain is attributable to specific work.
- Pre-register the target and the fallback ("top-3 open-weight, #1 on Semantic Formatting") before
  the final run.

## Budget

~$150–400 GPU, 3–8 days, one or two people. No SerpAPI. No new external dependencies. The rented
H100 already running Track A can serve this.

## Honest risks

- **Different stack.** This is a vision-language task; the text harness built for BFCL does not
  transfer. New tooling, new failure modes.
- **Vendor-owned benchmark.** LlamaIndex owns both the board and the leading entry. They have been
  fair to the one outsider so far, but the ceiling for an external entry is "best open-weight."
- **Thin board cuts both ways.** 21 entries and ~20 self-submitted means topping it is achievable
  and also that the board carries less prestige than a contested one. The insurance-corpus angle,
  not the rank alone, is what makes the claim land.
