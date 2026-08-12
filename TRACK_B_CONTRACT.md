# Track B contract — synthetic tool-calling dataset

Version 0.2 (draft for human approval, 2026-08-10). Nothing gets built until Amol approves
this file. Once approved it is frozen; changes require a dated entry in §10 so parallel
agents never work against a moving target.

Changes from v0.1 are summarized in §10.

---

## 1. Objective

Produce **40,000–60,000 verified tool-calling training examples**, provably disjoint from the
Berkeley Function-Calling Leaderboard (BFCL) v4 test data, covering every scored category of
that benchmark, in a single machine-readable format ready for model training.

Success is judged by four things and nothing else:
- **Coverage** — every BFCL v4 scored category has a corresponding training slice.
- **Integrity** — zero overlap with benchmark content; 100% of shipped rows machine-verified.
- **Non-triviality** — the data teaches inference, not transcription (§6.1, §6.3).
- **Diversity** — the data teaches a general skill, not a handful of domains (§6.2).

Volume is a target, not a goal. 20,000 clean, hard, diverse examples beat 60,000 sloppy ones.

A stricter framing of the same point: the dataset must improve the model on tool-calling
**in general**, of which BFCL is one measurement. If a design choice would raise the
benchmark score while narrowing real capability, it is out of scope.

## 2. Vocabulary (used precisely throughout this document)

- **Function schema** — a machine-readable description of one tool given to the model in its
  prompt: name, human-readable description, parameters with types and descriptions, and which
  parameters are required. It contains no values.
- **Call** — the model's output action, e.g. `place_order(symbol='AAPL', amount=10)`. Argument
  values come from the user's message, not from the schema.
- **Record** — one row of our dataset: tools available, the conversation, the correct call(s).
  Defined in §4.
- **Single-turn** — one user message, model emits call(s), interaction ends, nothing executes.
- **Multi-turn** — several user messages where each call really executes against a stateful
  backend and its result influences later turns; graded by resulting state.
- **Environment** — executable Python simulating a tool backend (mock file system, mock
  trading account). Required because multi-turn correctness is only definable by running the
  calls and inspecting state.
- **Teacher model** — the open-weight model we call via API to write natural language (e.g.
  the user's phrasing). Never a source of ground truth; gold is always constructed by us or
  verified by execution.
- **Inference distance** — how much reasoning separates the user's words from the correct
  call. Low distance ("base of 10, height of 5" → `base=10, height=5`) teaches transcription.
  High distance ("can I afford the $47 widget?" → check balance, then compare) teaches skill.
- **Leakage** — the answer being visibly present in the prompt: a schema description
  containing example values, or a user message naming the function or restating parameter
  names verbatim. Leaked examples train copying.
- **Mode collapse** — a generator producing thousands of superficially different but
  structurally near-identical samples (always 4 turns, always the happy path, always the same
  register). The dominant risk when a language model authors the data.
- **Out-of-distribution generalization** — performance on inputs unlike the training data.
  The property we actually want; narrow training data destroys it.
- **Difficulty band** — the range of examples a reference model gets right sometimes but not
  always (target 20–80% pass rate). Examples outside the band teach little: always-right ones
  are trivial, always-wrong ones are usually broken or impossible.
- **Held-out-domain test** — train on a subset of domains, evaluate on domains never seen.
  The only direct measurement of whether the model learned the skill or memorized domains.
- **Decontamination** — proving our content shares no identifiers or near-identical
  descriptions with BFCL test data. The evidence that our score is legitimate.
- **Provenance** — per-record metadata (generator version, teacher model, seed) so any row
  can be audited or regenerated.

## 3. What the benchmark actually contains (verified by reading its data files)

Ground truth for the design. Categories, item counts, and the shape of each:

| BFCL v4 category | Items | Shape |
|---|---|---|
| `simple_python` / `_java` / `_javascript` | 400 / 100 / 50 | 1 tool on menu, 1 correct call |
| `multiple` | 200 | several tools, 1 correct call (selection) |
| `parallel` | 200 | 1 message → several simultaneous calls |
| `parallel_multiple` | 200 | several tools AND several calls |
| `irrelevance` | 240 | no tool can satisfy the request → correct action is to call nothing |
| `live_*` (simple/multiple/parallel/parallel_multiple/irrelevance/relevance) | ~1,000 total | same shapes, real user-contributed schemas, messier |
| `multi_turn_base` | 200 | ~4 user turns against stateful environments |
| `multi_turn_miss_func` | 200 | a needed tool is withheld → model must recognize impossibility |
| `multi_turn_miss_param` | 200 | required info absent → model must ask, not guess |
| `multi_turn_long_context` | 200 | same, environment padded with distractor state |
| `memory_kv` / `memory_vector` / `memory_rec_sum` | (see data) | facts established early recalled much later |
| `web_search_base` / `_no_snippet` | (see data) | search tool driven to answer a question |
| `format_sensitivity` | (see data) | same task, varied surface formats; measures brittleness |

Observed conventions we mirror (not copy):
- Menu schemas use `{"type": "dict", "properties": {...}, "required": [...]}`.
- Answer keys allow **multiple acceptable values per argument** (e.g. an optional `unit` may
  be `"units"` or `""`). Our records must support the same, or graders will mark correct
  behavior wrong.
- Multi-turn answer keys are **a list of call-lists, one per user turn**.
- Environment classes expose `_load_scenario(dict)`, prefix internals with `_`, and are
  compared by public-attribute equality after execution.
- Multi-turn function descriptions carry a domain-context prefix sentence.

**Note on turn counts:** the benchmark clusters around 4 user turns. We deliberately
oversample 6–12 (§6.2) so the model is robust beyond what the benchmark tests.

## 4. The record schema (B0) — the contract every component obeys

One JSON object per line. Fields:

```
id                str    unique, "{generator}_{domain}_{index}"
category_target   str    which BFCL category this trains for (enum, see §3)
turn_type         str    "single" | "multi"
domain            str    e.g. "logistics"
tools             list   function schemas visible to the model (§3 conventions)
excluded_tools    list   schemas deliberately withheld (miss_func training); usually []
conversation      list   [{role, content}] user/assistant/tool messages in order
gold              list   per turn: list of acceptable call sets. Supports multiple
                         acceptable values per argument, mirroring the benchmark.
gold_kind         str    "calls" | "no_call" | "clarify"
environment       dict   {class_name, initial_state} for multi-turn; null for single-turn
verification      dict   {method: "constructed"|"replay"|"round_trip", passed: bool,
                         detail: str}
leakage           dict   {checked: bool, max_overlap: float, passed: bool}      [NEW v0.2]
diversity         dict   multi-turn only: {turn_count, failure_texture,
                         dependency_structure, register}                        [NEW v0.2]
difficulty        int    1–5, assigned by generator
baseline_pass_rate float|null  filled during QC by probing a reference model;
                         used for difficulty-band filtering (§6.3)              [NEW v0.2]
format_variant    str    which surface rendering (for format-robustness training)
provenance        dict   {generator, generator_version, teacher_model, teacher_license,
                         seed, created_by}
```

Hard rules: a record is invalid unless `verification.passed` **and** `leakage.passed` are
true; `gold_kind: "no_call"` requires `gold: []`; multi-turn records require a non-null
`environment` and a populated `diversity` block; every record must pass
`datagen/schema.py::validate(record)` before being written.

## 5. Components, interfaces, and acceptance criteria

Each component is one agent's assignment. **Interfaces are mandatory** — this is what makes
parallel work integrate. All components additionally obey §6.

### B0 — Schema and validators (serial, built first by orchestrator)
`datagen/schema.py`: `validate(record) -> None (raises)`, `Record` dataclass,
`to_training_format(record) -> dict`, `to_eval_format(record) -> dict`,
`check_leakage(record) -> LeakageReport` (§6.1).
**Accept**: round-trip test on hand-written fixtures for all category types; malformed and
leaked records rejected with clear messages.

### B1 — API universe (wave 1, ~4 agents split by domain group)
`datagen/universe/{group}.py`: `build(seed:int) -> list[Domain]` where a `Domain` has `name`,
`functions` (schemas), `value_samplers` (per parameter, realistic values).
Requirements: **60+ domains total** (raised from 50), 5–30 functions each, at least 30% of
domains contain deliberately confusable function pairs, parameter types spanning
integers/floats/strings/enums/booleans/arrays/nested objects/optionals, three naming styles.
**Schema descriptions must contain no example values** (§6.1).
**Accept**: `pytest` passes; all schemas validate; determinism check; printed table of
domain/function/type-distribution counts; leakage check clean; ≥20 sampled schemas readable.

### B2 — Decontamination checker (wave 1, 1 agent, blocking)
`datagen/decontam/checker.py`: `extract_benchmark_identifiers() -> BenchmarkIdentifiers`
(the ONLY code permitted to read BFCL data), `check_names(names) -> Report`,
`check_descriptions(texts, threshold=0.85) -> Report`, `check_corpus(path) -> Report`.
Name overlap must be exact-match zero; description similarity uses local embeddings
(`sentence-transformers`, installed) with a max cosine ceiling.
**Accept**: correctly flags a deliberately-planted BFCL function name in a fixture; reports
zero overlap on B1 output; emits `reports/decontamination.md`.

### B3 — Mock environments (wave 2, ~8 agents — LONG POLE)
`datagen/envs/{domain}.py`: class with `_load_scenario(dict)`, public tool methods returning
dicts, `snapshot() -> dict`, `reset(seed)`. Deterministic; no wall-clock, no network.
**Target 12–15 environments** (raised from 8) to satisfy the ≤8%-per-domain cap in §6.2;
agents may build two simpler environments each rather than one elaborate one.
**Accept**: `pytest` per environment covering happy path, error path, and state mutation;
replay determinism; smoke test proving a generator can drive it end-to-end; auto-derived
schemas match actual method signatures.

### B4 — Single-turn generator (wave 3)
`datagen/gen/single_turn.py`: `generate(domains, n, seed, variants) -> Iterator[Record]`.
Method: sample gold call first, then teacher writes the user question that would elicit it.
Emits all single-turn variants incl. `no_call` (irrelevance) and `clarify` (missing param).
Requirements: **hardness floor and no-leakage rules per §6.1**; **paraphrase requirement**
(user message must refer to parameters in different words than the schema uses);
**round-trip filter mandatory** (an independent model answers cold; keep only if its call
matches gold), discards logged with reasons.
**Accept**: round-trip pass rate reported (expect ≥70%); 50 samples human-reviewable;
category and difficulty distributions match request; leakage clean on 100% of rows.

### B5 — Multi-turn generator (wave 3)
`datagen/gen/multi_turn.py`: same signature. Planner decomposes a goal into a gold call
sequence, executes against a B3 environment, teacher narrates the user side per turn.
Emits base / miss_func / miss_param / long_context variants.
Requirements: **all five diversity axes of §6.2 sampled independently per record and recorded
in the `diversity` block**; one generation request per record (never "give me N scenarios")
to suppress mode collapse.
**Accept**: 100% replay-verified; turn-count histogram matching §6.2 targets; all five axes
populated with reported entropy; each variant present.

### B6 — Memory generator (wave 3)
`datagen/gen/memory.py`: long dialogues (20–60 turns) planting facts needed later.
**Accept**: plant-to-use distance histogram; recall verified programmatically.

### B7 — Format and adversarial augmentation (wave 3)
`datagen/gen/augment.py`: `augment(record, n_variants, seed) -> list[Record]`. Re-renders
system prompts, schema styles, template shapes, and distractor-tool sets; **gold unchanged by
construction**; each variant re-validated.
Added in v0.2: **keep preferentially the perturbations that break a reference model** — real
adversarial pressure on axes that provably cannot change the correct answer. This is the safe
substitute for a full adversarial training loop (explicitly out of scope for this sprint).
**Accept**: ≥5 distinct variant styles; automated re-verification passes 100%; before/after
example printed; report of which perturbation styles most degrade the reference model.

### B8 — Quality control and assembly (wave 4)
`datagen/qc/pipeline.py`: exact and near-duplicate removal; **difficulty-band filter (§6.3)**;
**diversity measurement (§6.4)**; mix balancing; final `check_corpus` decontamination pass;
90/10 train/dev split with **domain-disjoint held-out slice** for the generalization test;
tokenized export; `reports/dataset_card.md`, `reports/diversity.md`, `reports/cost.md`.
**Accept**: statistics report matches §7 targets; rejection counts logged by reason; dev split
never overlaps train; held-out-domain slice contains domains absent from train; final
decontamination report clean.

## 6. Cross-cutting data quality requirements  [NEW in v0.2]

These bind every generator. A component that meets its own interface but violates §6 is not done.

### 6.1 No leakage, and a hardness floor
- Schema descriptions may **never** contain example values ("e.g. 10 units" is banned).
- Generated user messages may **never** name the target function, nor restate parameter names
  verbatim. Enforced by `check_leakage`: token-overlap between the user message and the
  schema's identifiers must stay below a threshold; violations are rejected, not warned.
- **Menu size floor**: at most 20% of the single-turn corpus may present a single tool.
  Selection-style records must offer ≥3 tools including at least one plausible-but-wrong
  candidate from the same domain.
- **Paraphrase requirement**: the user's phrasing for a parameter should differ from the
  schema's wording ("how much have I got" vs. `balance`).

### 6.2 Diversity, engineered as controlled axes
Diversity is sampled explicitly, never hoped for. Every multi-turn record samples
independently from:
- **Turn count** — 2 to 12. Target distribution: ~30% in 2–4, ~40% in 5–8, ~30% in 9–12
  (deliberately harder than the benchmark's ~4-turn cluster).
- **Domain** — no domain exceeds **8%** of the multi-turn slice (the reason for 12–15
  environments).
- **Failure texture** — happy path; call fails and must be retried; user changes their mind
  mid-conversation; ambiguous request needing clarification; impossible request; user supplies
  wrong information that must be caught.
- **Dependency structure** — linear chain; branching (a result selects the next path); a call
  that must be undone; long-range dependency (turn 9 needs turn 2's output).
- **Register** — terse; verbose; non-native phrasing; typo-laden; over-polite; brusque.

Mode-collapse suppression: **one teacher request per record**, each seeded with a different
sampled combination of the axes above. Never ask a teacher for many examples in one call.

### 6.3 Difficulty calibration (the cheap substitute for an adversarial loop)
- During QC, probe each candidate with a small reference model, k attempts, and record
  `baseline_pass_rate`.
- **Keep-band**: prefer 20–80%. Always-right examples are trivial; always-wrong ones are
  usually broken, impossible, or mislabeled and must be inspected rather than shipped blind.
- **Retain a deliberate easy tail** — roughly 20% easy / 50% medium / 30% hard. A model
  trained only on hard cases over-complicates simple requests, and the benchmark scores the
  easy categories too.
- **Failure-driven top-up**: once Track A reports per-category baseline gaps, generate
  additional data targeted at the weakest categories. This is the one place Track A informs
  Track B, and it happens at assembly time only.

### 6.4 Measurement and reporting (trust nothing unmeasured)
`reports/diversity.md` must contain: pairwise embedding-similarity distribution over
conversations (tight clustering is the mode-collapse signature); per-axis entropy against
§6.2 targets; domain share table; turn-count histogram; difficulty histogram with
`baseline_pass_rate` distribution; and the **held-out-domain result** once a model exists.

## 7. Volume targets (adjustable at the wave-3 gate)

| Slice | Target | Notes |
|---|---|---|
| Single-turn simple/multiple | 12,000 | ≤20% single-tool (§6.1) |
| Parallel / parallel_multiple | 4,000 | |
| Irrelevance (`no_call`) | 3,000 | models over-call; heavily weighted on purpose |
| Missing-param (`clarify`) | 2,000 | |
| Multi-turn base | 6,000 | the leaderboard's weakest area = our biggest gain |
| Multi-turn miss_func / miss_param / long_context | 4,500 | 1,500 each |
| Memory | 3,000 | |
| Web-search style | 1,500 | |
| Format/adversarial variants (augmentation) | ×1.5 on all above | |

Final mix ratios get tuned once Track A's per-category baseline gaps are known (§6.3).

## 8. Gates (Amol decides at each; work stops until he says go)

- **Gate B-α** — after wave 1: decontamination report clean, universe statistics sane,
  leakage check clean, 20 sampled schemas read and approved by Amol.
- **Gate B-β** — after wave 2: all environments tested, generator smoke test green,
  ≥12 environments present.
- **Gate B-γ** — after wave 3: **Amol reads 50 sampled generated examples** and judges them
  natural, unambiguous, and non-trivial. Reviewed alongside `reports/diversity.md` (difficulty
  histogram, per-axis entropy, similarity distribution). This is the taste gate; no automation
  substitutes for it.
- **Gate B-δ** — after wave 4: dataset card, statistics, diversity and cost reports reviewed;
  dataset frozen and handed to Track C.

## 9. Budget and ownership

- Teacher API spend ceiling: **$500**, plus up to **$150** for reference-model probing in
  §6.3 (new in v0.2). Report actual spend per wave; stop and ask if a wave would exceed its
  share.
- No GPU spend in Track B.
- Every agent reports: what it built, the real command output proving acceptance, what it did
  not do, and what it is uncertain about.

## 10. Amendments

**v0.2 (2026-08-10)** — following Amol's review:
1. Added §6.1 no-leakage rules and menu-size hardness floor; new `leakage` record field and
   `check_leakage` validator. Prevents examples where the answer is visible in the prompt
   (his question: "if the machine-readable description is just the tool call itself…").
2. Added §6.2 five controlled diversity axes with a per-domain 8% cap; new `diversity` record
   field; one-teacher-request-per-record rule to suppress mode collapse.
3. Raised environment target 8 → **12–15** and domain target 50 → **60+** to make the
   diversity caps achievable.
4. Added §6.3 difficulty-band filtering with `baseline_pass_rate`, an explicit easy tail, and
   failure-driven top-up — adopted as the deliberate, cheap substitute for a full adversarial
   generator/solver loop, which is **out of scope for this sprint** by decision.
5. Added §6.4 mandatory diversity measurement and a domain-disjoint held-out slice for
   generalization testing; new `reports/diversity.md`.
6. Extended B7 to keep perturbations that break a reference model (adversarial pressure on
   axes that cannot change gold).
7. Objective §1 restated to make transferable capability, not benchmark score, the goal.
