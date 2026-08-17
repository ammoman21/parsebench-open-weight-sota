# EDGAR harvest — real-filing training pairs for the formatting fine-tune

Date: 2026-08-17. Code: `ourparser/finetune/harvest_edgar.py`. Output:
`edgar_data_sample/` (300 rows). Every number below is quoted from a command
that actually ran in this session; the harvester prints its own gate results on
every run and exits non-zero if a gate fails.

## Vocabulary (plain language, first use)

- **EDGAR** — Electronic Data Gathering, Analysis, and Retrieval: the SEC's
  (Securities and Exchange Commission, the US financial regulator) public
  repository of company filings. Filings are HTML, so inline styling is exact
  ground truth read from the markup, not human annotation.
- **10-K / 10-Q** — a company's annual / quarterly report filing.
- **SIC code** — Standard Industrial Classification, the SEC's sector coding;
  6311/6321/6331/6411 are life, accident & health, property & casualty
  insurers, and insurance brokers.
- **CIK** — Central Index Key, the SEC's numeric company identifier.
- **DOM** — Document Object Model, the parsed tree of an HTML page; "derivable
  from the DOM" means we compute each text run's effective bold/strike/
  superscript/subscript state from tags plus inline CSS.
- **Fragment / region** — one self-contained block (a paragraph, or a short
  heading paired with its following paragraph) rendered as a crop a few
  hundred pixels tall, matching what the production layout detector feeds the
  model.
- **Negative** — a fragment with no scoreable styling; the target is plain
  text. Negatives teach the model restraint (the v2 synthetic probe failed by
  bolding indiscriminately).

## What was fetched

20 filings — the most recent 10-K and 10-Q for each of 10 insurance-sector
issuers: TRV, ALL, PGR, CB, AIG, HIG, AFL, CINF, WRB, AIZ (filing dates
2026-02-12 … 2026-08-07, printed per filing by the run). Fair-access
compliance, verified in code (`harvest_edgar.py:96-116`): User-Agent
`research contact shaurya@florin.inc`, a hard 0.25 s inter-request delay
(4 requests/second, under the 5/s brief), and every URL cached under
`edgar_cache/` (113 MB), so re-runs make zero network requests.

## Fragment yield per filing

From the final run (kept = after within-filing near-duplicate removal, with
negatives pre-capped at 120/filing; styled fragments are never pre-capped):

| filing | kept | near-dups dropped | | filing | kept | near-dups dropped |
|---|---|---|---|---|---|---|
| AFL 10-Q | 173 | 51 | | CINF 10-Q | 143 | 8 |
| AFL 10-K | 229 | 120 | | CINF 10-K | 155 | 16 |
| AIG 10-Q | 276 | 95 | | HIG 10-Q | 256 | 102 |
| AIG 10-K | 400 | 199 | | HIG 10-K | 336 | 155 |
| AIZ 10-Q | 147 | 34 | | PGR 10-Q | 140 | 5 |
| AIZ 10-K | 161 | 74 | | PGR 10-K | 179 | 4 |
| ALL 10-Q | 151 | 12 | | TRV 10-Q | 151 | 59 |
| ALL 10-K | 196 | 44 | | TRV 10-K | 201 | 177 |
| CB 10-Q | 133 | 66 | | WRB 10-Q | 136 | 39 |
| CB 10-K | 208 | 45 | | WRB 10-K | 172 | 50 |

Cross-filing near-duplicates dropped: **416** (filings share large amounts of
boilerplate — forward-looking-statement paragraphs, identical note headers).
Post-dedupe pools: **1,206 styled / 2,331 negative** candidates, from which 300
were sampled (seed 0, deterministic). Final per-company row counts:
AFL 31, AIG 65, AIZ 19, ALL 26, CB 14, CINF 14, HIG 58, PGR 25, TRV 30,
WRB 18. Target lengths 60–846 chars, median 212.

## Quality gate results (printed by the run; all PASS)

- **(a) Blank renders: 0 / 300 — PASS.** Every PNG is re-opened after the
  batch render and its difference-from-white bounding box checked
  (`harvest_edgar.py`, `gate_blank_renders`); a None box anywhere fails the
  run. This is the guard against a repeat of the synthetic pipeline's
  blank-CJK incident.
- **(b) Bold-span provenance: 0 failures / 10 — PASS.** For 10 random styled
  samples, every `**span**` in the target was independently located inside a
  bold-styled element (b/strong/heading tag or font-weight ≥ 600 style) of the
  fragment's rendering HTML, by a separate DOM inspection that shares no code
  with the target derivation. The 10 side-by-side comparisons are in the run
  output. Beyond the automated gate, 5 rendered crops were opened and read by
  eye against their targets in this session, including a bold+italic risk
  headline (bold marked, italic correctly unmarked) and two hanging-indent
  bullet items.
- **(c) Dedupe:** 1,356 within-filing + 416 cross-filing near-duplicates
  dropped (word 4-gram Jaccard ≥ 0.6, plus exact normalized-text hash).
- **(d) Split and markers:** styled 225 / negatives 75 (**25%** exactly).
  Marker occurrences in targets: `**bold**` 242 pairs, `~~strike~~` 0,
  `<sup>` 0, `<sub>` 0 (see limitations).

Also verified this session:

- **Determinism** (project convention): two runs at seed 0 produce
  byte-identical `data.jsonl` (`cmp` clean).
- **Prompt byte-identity:** all 300 rows carry exactly
  `"\nText Recognition:\n"` and exactly the keys
  `{image, prompt, target, source_url, styled}` (asserted programmatically).

## Defect found and fixed during verification

First-run bullet items rendered wrong: EDGAR marks bullets as hanging indents
(`padding-left` on the block, negative `text-indent`, bullet glyph, then a
`padding-left` span holding the text). The cleaner kept `text-indent` but
dropped `padding-left`, clipping the bullet glyph off the page edge while the
target still contained "•" — and the span's padding gap appeared in no target,
giving "•a downgrade" against an image showing a spaced bullet. Fixed by
keeping `padding-left`/`margin-left` in the style whitelist and emitting a
space in the target at padded-span boundaries; re-verified by eye on
`region_00011.png` and `region_00019.png` in the final dataset.

## Honest limitations

1. **The sample is bold-only.** Zero `~~strike~~`, `<sup>`, `<sub>` markers —
   and this is a property of the corpus, not an extraction bug: a regex scan
   of all 20 raw cached HTML files found **0** occurrences of
   `<sup>`/`vertical-align:super`, **0** of `<sub>`/`vertical-align:sub`, and
   **2** of `line-through` (both a struck-through bullet glyph in AFL filings
   — punctuation only, which the marker rules deliberately leave plain).
   Modern inline-XBRL filings put footnote references inside tables and use
   almost no superscript in running text. EDGAR data therefore complements —
   does not replace — the synthetic generator for strike/sup/sub coverage.
   Scaling to more issuers/older filings may surface some `<sup>`, but plan
   for the synthetic pipeline to remain the sole source of those markers.
2. **Tables are skipped entirely** (any block inside `<table>` is excluded).
   Much of a filing's typography — and its footnote superscripts — lives in
   financial tables. Cell-level fragments are extractable but need column
   width/border reconstruction to look right; deliberately out of scope here.
3. **EDGAR italic conventions:** many filings set risk-factor headers in
   bold+italic. Targets mark bold only (italic scores in no ParseBench
   category — reports/parsebench_scoring_spec.md §0.4), so the model sees
   italic glyphs labeled as plain/bold. That is the intended training signal,
   but it means this data teaches "ignore italics" implicitly.
4. **Rendering is re-typeset, not a screenshot of the filing.** Fragments are
   re-rendered at randomized width/size/base font inside the batch renderer
   (copied verbatim from `generate_data.py:222-258`), with original inline
   font styles preserved but colors dropped (some filings use white-on-color
   headers that would render blank on white). Layout is therefore
   EDGAR-flavoured, not pixel-identical to the SEC viewer.
5. **`vertical-align: top/text-top` spans** (an occasional sup-like idiom) are
   neutralized in the render rather than modeled, so image and target agree;
   none occurred in these 20 filings.
6. **Sector concentration is deliberate** (insurance SIC codes per the plan),
   so vocabulary diversity is narrower than the synthetic set.

## Ready to scale?

Yes, for bold-texture data: pools already hold 1,206 styled + 2,331 negative
deduped fragments from just 20 filings, so ~3k fragments needs roughly 40–60
filings (2–3× the ticker list, or 2 more years of filings per issuer) — one
flag change (`--n 3000`, more tickers/`per_form`). Rate math: ~2 network
requests per new filing at 4 req/s; fetch time is dominated by download size
(~5 MB average), minutes not hours. The known scaling risks are listed above:
no strike/sup/sub will appear at any scale on this corpus, and cross-filing
dedupe cost grows quadratically (fine at 3k; revisit the O(n²) Jaccard loop
beyond ~20k candidates).
