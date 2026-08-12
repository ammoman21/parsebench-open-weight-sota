# Parity targets — published BFCL v4 scores

Source: the official results repository linked from the leaderboard page,
`github.com/HuanzhiMao/BFCL-Result`, snapshot **2025-12-16** (the most recent published raw
results as of 2026-08-11). Leaderboard site states models are evaluated at harness commit
`f7cf735`; our checkout is `6ea5797`.

The live leaderboard page renders scores in JavaScript and cannot be read programmatically —
this repo is the machine-readable source.

## Naming convention (matters for parity)

- `qwen3-14b-FC` (lowercase) — evaluated via a **hosted API**.
- `Qwen_Qwen3-8B-FC` (underscore-prefixed) — evaluated **self-hosted** through local inference.

Our setup is self-hosted vLLM. There is **no** published self-hosted 14B row, so:
- compare against `qwen3-14b-FC` for same-model parity (serving path differs), and
- optionally run `Qwen/Qwen3-8B-FC` for same-serving-path parity (model differs).
Agreement on both would be conclusive.

## Published scores

| Group | Category | `qwen3-14b-FC` | `Qwen_Qwen3-8B-FC` |
|---|---|---|---|
| non_live | simple_python | **0.9525** | 0.9550 |
| non_live | simple_java | 0.6300 | 0.6100 |
| non_live | simple_javascript | 0.6600 | 0.6200 |
| non_live | multiple | 0.9300 | 0.9650 |
| non_live | parallel | 0.8000 | 0.9200 |
| non_live | parallel_multiple | 0.9200 | 0.8900 |
| non_live | irrelevance | 0.8583 | 0.8167 |
| live | live_simple | 0.8566 | 0.8450 |
| live | live_multiple | 0.7901 | 0.7968 |
| live | live_parallel | 0.6875 | 0.7500 |
| live | live_parallel_multiple | 0.7083 | 0.7917 |
| live | live_relevance | 0.8750 | 0.9375 |
| live | live_irrelevance | 0.7805 | 0.7647 |
| multi_turn | multi_turn_base | **0.3900** | 0.5050 |
| multi_turn | multi_turn_long_context | 0.3250 | 0.3450 |
| multi_turn | multi_turn_miss_func | 0.3400 | 0.4200 |
| multi_turn | multi_turn_miss_param | 0.3350 | 0.4000 |
| agentic | web_search_base | 0.0800 | 0.1500 |
| agentic | web_search_no_snippet | 0.1200 | 0.0900 |

Memory categories are absent from this snapshot (newer than 2025-12-16).

## Parity status

**`simple_python`: PASSED.** Our run 2026-08-11 scored **0.9500** (380/400) against published
**0.9525** (381/400) — a one-item difference, on a self-hosted rig versus their API-served run.
Strong evidence the harness, chat template, `hermes` parser, and scoring path are all correct.

**Still required: `multi_turn_base`, target 0.3900.** Single-turn is the easy case. Multi-turn is
where chat-template choice moves scores 6–8% (arXiv 2606.00135) and where per-turn errors
compound, so it is the real test of the rig. Landing within a few points of 0.39 validates the
setup end to end. A large gap means investigate before trusting anything downstream.

## Strategic read (feeds the Track B data mix, contract §6.3)

1. **Multi-turn is the opportunity: 0.325–0.390 across all four variants, 800 items.** Already the
   contract's largest slice — now confirmed by real numbers rather than assumption.
2. **Web search is near-floor: 0.08–0.12.** Enormous headroom, only 100 items, and it needs the
   SerpAPI key. Cheap to move if the aggregate counts agentic categories.
3. **Unexpected finding — Java and JavaScript are weak: 0.63 and 0.66**, versus 0.95 for Python,
   across 150 items. The Track B contract's universe is Python-shaped. **Add Java and JavaScript
   function schemas to B1**; this looks like the cheapest per-point gain on the board.
4. Single-turn Python categories are near-ceiling (0.93–0.96) — little to gain, but the deliberate
   easy tail in §6.3 protects against regressing them.

## Reproduce this table

`.venv/bin/python` against the GitHub contents API; script kept at
`scripts/fetch_parity_targets.py` (copied from the job tmp run that generated this file).
