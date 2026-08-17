
## NIGHT MANDATE AMENDMENT (user, ~02:15 PDT) — strategy for the rest of the night

Priority-ordered claims to chase (user explicitly opened category/insurance scopes):
1. **Overall open-weight SOTA** (>76.36 full corpus) — still primary if reachable.
2. **Category SOTA: Semantic Formatting.** Best OPEN-WEIGHT formatting on the board is 69.30.
   If our corpus formatting clears that, "best open-weight Semantic Formatting on ParseBench"
   is a clean, board-defined category claim. Likely the most reachable real claim tonight.
3. **Insurance-subset SOTA** — our published-methodology subset (384 docs incl. SERFF).
   Leader's reproduction scores 74.77 there. Comes FREE with any full-corpus run via
   scripts/insurance_subset_score.py. Most on-thesis; weaker external validity than a board
   category (our subset definition), so it is claim #3 not #1.

AMENDED RULE — calibration full run: the 70-subset gate existed to avoid wasted $3 runs, but
the subset->corpus transfer coefficient is currently guesswork and now gates all decisions.
Therefore: after it6/it7 probes, fire ONE full-corpus run on the best checkpoint even if
subset < 70, explicitly labelled CALIBRATION. It also yields the insurance-subset and
formatting-category numbers free. (PREREGISTRATION submission tiers unchanged.)

Real-data path: EDGAR harvester (subagent) -> it7 on real fragments if gates pass.
Architecture changes (unfreezing vision tower, other bases): OUT of scope tonight except as
a final cheap experiment if time remains after it7; full redesigns are days, not hours.
Sanity discipline: every conclusion cross-checked against a second measurement before acting
(plausibility rules in ~/.claude/CLAUDE.md apply to every number).
