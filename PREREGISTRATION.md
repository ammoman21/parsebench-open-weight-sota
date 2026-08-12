# Preregistration — ParseBench submission

**Committed 2026-08-12, before any measured run of the patched pipeline.** The purpose of this
document is to fix the claim, the patch set and the protocol *in advance*, so the result cannot be
read as having been chosen after seeing the number.

Nothing below may be changed after the first measured run. Any change requires a dated amendment at
the bottom stating what changed and why, leaving the original text intact.

---

## 1. What we are claiming, and what we are not

**Position chosen: credibility-first, with the aggressive number disclosed alongside.**

We submit the **genuine-improvement patch set only** (§3) as our headline result, and we report
whatever score it produces — including if that score falls below the current open-weight leader's
published 76.36. In the same document we disclose the score achievable with the aggressive patch set
(§4) and explain why we did not submit it.

We are **not** claiming:
- "#1 overall on ParseBench" — LlamaIndex's own commercial product (LlamaParse Agentic, 84.88) leads
  the board, and LlamaIndex owns the benchmark. Our ceiling is the open-weight category.
- Any improvement measured against the published leader's row. All deltas are measured against **our
  own reproduction** of that pipeline (72.65 overall), because we cannot reproduce their published
  76.36 and it would be dishonest to bank the difference.
- Any improvement to the underlying model. We have trained nothing. Every change is to prompt or
  markdown emission.

## 2. Base model, environment, protocol

- **Base:** `KDLAI/KDL-Frontier-Parser-nano` (KoreaDeepLearning, 1.2B parameters, AGPL-3.0),
  unmodified weights.
- **Serving:** vLLM, `--served-model-name kdl-frontier-parser-nano --max-model-len 8192
  --gpu-memory-utilization 0.85 --max-num-seqs 24 --trust-remote-code --limit-mm-per-prompt
  {"image":1}` on a single NVIDIA H100 80GB. These are the serve flags published in the pipeline's
  own docstring.
- **Corpus:** the complete ParseBench dataset, 2,079 files, all five dimensions.
- **Scoring:** the benchmark's own evaluation code and its own default metric per dimension
  (`grits_trm_composite`, `rule_pass_rate`, `content_faithfulness`, `semantic_formatting`,
  `layout_element_rule_pass_rate`). Overall = unweighted mean of the five, as the benchmark computes it.
- **Chart LLM normaliser:** disabled (`LLAMACLOUD_BENCH_LLM_NORMALIZATION=off`) and declared. The
  benchmark defaults this to an LLM-as-judge normaliser using Claude Haiku, which contradicts its own
  README; our reproduction ran with it effectively off and matched published charts within 0.28.
- **Runs:** one validation run, then one final frozen run. Both reported. If they disagree by more
  than 0.3 overall we report both numbers and the disagreement rather than picking one.

## 3. Headline patch set — genuine improvements only

Submitted. Each entry is a defect fix or a real inference the pipeline was not making.

1. **`Section-header` category map fix.** `NATIVE_LAYOUT_CATEGORY_MAP:545-572` has no
   `section_header` key, so that category is never emitted (0 occurrences across 2,078 artifacts) and
   every heading collapses to `h1`. This makes 12.9% of `title_hierarchy_percent` structurally
   unreachable. Adding the key repairs an outright bug.
2. **Heading levels derived from `Title` bounding-box height.** The pipeline performs no hierarchy
   inference; this supplies it from geometry already present in the layout output.
3. **Bold applied to run-in `Label:` prefixes.** These runs *are* bold in the source documents and
   the pipeline drops them. This adds markup the model's own layout output supports.

**Optionally included, flagged as borderline:** relaxing the heading gate `_is_titleish:2489-2508` by
dropping its terminal-punctuation and label-value vetoes. These vetoes reject genuine headings. We do
**not** adopt the 30-word cap replacement, which is loose; we will use a 20-word cap and report the
choice. If this component's measured contribution is negative or within ±0.05 we drop it.

## 4. Aggressive patch set — measured and disclosed, NOT submitted

Reported in the writeup for transparency, with this reasoning attached.

- Short single-line `Text` elements promoted to `#` headings.
- `List-item` elements promoted to `##` headings.
- (`MAXBOLD` is excluded from every set, including this one, as degenerate.)

**Why disclosed rather than submitted.** The scorer's bold check accepts an annotated run appearing on
a `#`-heading line as evidence of bold, since headings render bold. This pipeline emits **no** inline
bold markup at all, so 100% of its bold credit arrives through that route. Promoting non-headings to
headings therefore raises the bold score without detecting any bold. Measured: the aggressive set
reaches **76.79** overall and a 20-line variant alone reaches **77.01**. We consider that a property
of the scorer, not of the parser, and publishing it as a finding is worth more than banking it as a rank.

## 5. Claim tiers, fixed in advance

| Outcome of the final run | What we claim |
|---|---|
| Genuine set ≥ 76.36 | Top open-weight position on ParseBench, with the patch set and reproduction code published, and the aggressive number disclosed. |
| Genuine set 72.65–76.36 | A measured improvement of *N* points over our own reproduction of the leader, plus the four defects and the scorer-coupling finding. No ranking claim. |
| Genuine set < 72.65 | The patches regressed. We report that, publish the defects and the coupling finding, and make no performance claim. |

In every tier we publish all five dimensions **including the ones where we lose**, and we report the
insurance-subset scores for the Tables dimension only — the other four insurance slices are 24–40
pages and will be labelled directional.

## 6. Kill criteria

- **Validation run misses the replay prediction by more than 0.3 overall** → stop, diagnose, do not
  submit. This would mean the replay harness does not reflect live inference.
- **Any patch moves Content Faithfulness, Tables or Visual Grounding down by more than 0.3** → that
  patch is dropped, regardless of what it gains elsewhere.
- **Visual Grounding investigation yields nothing by Thursday noon** → ship without it.

## 7. Run budget

Two H100 runs at ~70 minutes and ~$4 each. A third only if the two disagree beyond tolerance. Total
committed: **≤$15**. All analysis runs on the committed replay harness at zero marginal cost.

## 8. Disclosures

- We reproduce the leader's published overall score as **72.65, not 76.36** — a 3.71-point shortfall
  we could not explain. Three dimensions reproduce within 0.3; Semantic Formatting is 14.39 low and
  Visual Grounding 4.65 low. A control model (`Chandra-ocr-2`) reproduced its own published chart
  score exactly and its formatting within 3.17, which establishes that the scoring is sound and the
  deficits are per-model. Two candidate causes were tested and eliminated: the chart LLM normaliser
  and output truncation.
- The replay harness had a fidelity bug (a missing blank-markdown short-circuit) that inflated Content
  Faithfulness by 0.075. Found, fixed, and all three markdown-derived dimensions now reproduce exactly.
- No file under the upstream `parsebench/src/` checkout is modified. Patches are a provider subclass in
  our own module.
- This work is for publication only. Nothing here goes into a production system.

---

### Amendments
(none)

### Amendment 1 — 2026-08-12, after the genuine-set measurement, before any live run

**§4 mischaracterised the aggressive set, and the error was mine.** §4 as written lists two changes
(short single-line `Text` → `#`, `List-item` → `##`) and attributes **76.79** to them. That 76.79 was
measured on a set containing a **third** member §4 never mentions: bold applied to every own-line of
≤40 words. Re-measured on §4's own two-change definition, the aggressive set reaches **75.65** — which
**does not clear 76.36.**

Consequences, stated plainly:
- The premise that a ranking claim was available is weaker than §4 implied. Neither the submitted set
  (74.64) nor the aggressive set as defined (75.65) clears the published leader.
- The 77.01 MAXBOLD figure quoted in §4 is inherited from an earlier agent, was not re-measured, and
  MAXBOLD remains excluded from every set.
- **Claim tier 2 of §5 applies:** a measured improvement over our own reproduction, no ranking claim.

**Component (a), the `section_header` map fix, contributes exactly 0 and is unmeasurable by replay.**
Stored artifacts persist only the *canonicalised* category; the model's raw layout label is absent from
`output/` entirely. So which elements the model labelled `section_header` cannot be known without live
inference, and if the model's label vocabulary lacks that token the fix is a no-op. The defect is real
by inspection (0 `Section-header` across 2,078 artifacts; the `##` branch is dead code) and the fix
ships — but **it must never appear in any arithmetic**, and it is excluded from every number below.

**Component (d) is kept.** Marginal contribution +0.92 Overall (Semantic Formatting +3.45, Charts
+1.23, Content Faithfulness −0.07) — 18× the ±0.05 drop threshold in §3. The preregistered 20-word cap
was used; the 30-word cap would have bought a further +0.32, which is exactly why fixing the cap in
advance mattered.

**Measured results (replay, full 476-document scoring corpus):**

| set | Tables | Charts | Content Faith. | Sem. Fmt | Visual Gr. | Overall | vs 72.65 | vs 76.36 |
|---|---|---|---|---|---|---|---|---|
| our reproduction as shipped | 85.76 | 63.69 | 87.18 | 52.42 | 74.19 | 72.65 | — | −3.71 |
| genuine (b)+(c) | 85.76 | 63.73 | 87.16 | 57.75 | 74.19 | 73.72 | +1.07 | −2.64 |
| **genuine (b)+(c)+(d) — SUBMITTED** | 85.76 | 64.95 | 87.09 | 61.20 | 74.19 | **74.64** | **+1.99** | −1.72 |
| aggressive — disclosed, not submitted | 85.76 | 65.05 | 86.95 | 66.30 | 74.19 | 75.65 | +3.00 | −0.71 |

Treat the submitted figure as **74.6 ± 0.2** (provider-level transfer error is unmeasured on 157 of
476 documents). No kill criterion fired: worst Content Faithfulness cost anywhere is −0.23; the
submitted set costs −0.09. Tables 0/1,074 documents changed; Visual Grounding 0/400.

**Consequent change of priority (not a change of claim):** the **4.65-point Visual Grounding deficit
is now the only remaining route to a ranking claim** — 74.64 + 4.65 would clear 76.36 comfortably. It
is promoted from a Thursday nice-to-have to the critical path.

**Also flagged:** there is no git repository at `bfcl-sprint/`; the only repo is the pinned upstream
`parsebench/` checkout. Earlier reports describing the harness as "committed" were inaccurate — the
files exist but are not version-controlled. §8 promises published reproduction code, so this must be
resolved before submission.
