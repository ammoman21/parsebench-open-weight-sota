# Target: top BFCL v4 `simple_java` — execution plan

Written 2026-08-11. Supersedes the multi-turn target for the immediate sprint (multi-turn is a
42-point gap; this is a 1-point gap). Multi-turn remains the longer-horizon goal.

## Why this category

Pulled from the live leaderboard CSVs (`gorilla.cs.berkeley.edu/data_non_live.csv`, 109 models):

- **Top score is 67.00%, held by a five-way tie**: o4-mini (Prompt), Qwen3-32B (Prompt),
  Qwen3-30B-A3B-Instruct-2507 (Prompt), Mistral-Small-2506 (Prompt), Gemini-2.5-Flash (Prompt).
- **Our base `Qwen3-14B (Prompt)` is at 66.00% — one item behind the leaders.** (`Qwen3-14B (FC)`
  is 63.00%. **Target the Prompt flavor**: all five leaders are Prompt.)
- Median across 109 models is 60.00%. The entire field is jammed between ~55% and 67%.
- Only **100 items**, so a full evaluation takes minutes and costs cents.
- The same models score 95–97% on `simple_python`. A 30-point language gap for identical models is
  a data/format artifact, not a reasoning limit — which is what makes it trainable.

## Why the field is stuck at 67% — diagnosed, not assumed

Fetched the published per-item failure records for four of the top models
(o4-mini, Qwen3-32B, gemini-2.5-flash, qwen3-14b) from the results repository:

- **27 of 100 items are failed by all four models.** Union of failures = 39 items.
- So 61 items everyone passes, **12 items are the contested margin**, 27 are the hard core.
- Ceiling without cracking the hard core is **73%**. The leaders at 67% are dropping ~6 of the 12
  contested items, which is where the immediate win is.

Dominant error strings across all four models: `Invalid syntax. Failed to decode AST. Error parsing
java the source code`; `Incorrect type for parameter 'ids'. Expected type ArrayList, got str`;
`Expected type HashMap, got str`; `Expected type Array, got str`; `Invalid value for parameter ...
'new GenericView(...)'`.

### Inspected four hard-core items — they split into three distinct causes

1. **`simple_java_35` — genuine model error, trainable.** Model emitted
   `keys=["user:online:today", "user:online:yesterday"]` — JSON/Python list syntax, which is not
   valid Java, so the Java parser rejected the whole call. Correct Java is
   `new String[]{"user:online:today", "user:online:yesterday"}`. **This is the core trainable gap:
   models fall back to Python-style collection literals in a Java context.**
2. **`simple_java_85` — probable checker defect.** Model emitted correct Java:
   `argv="new String[]{\"/path/to/classes\", \"60\"}"`. The checker parsed it into
   `['\"/path/to/classes\"', '\"60\"']` — **retaining the escaped quote characters inside the
   strings** — and compared against gold `['/path/to/classes', '60']`. A correct answer scored
   wrong because the Java-array parser does not strip quotes.
3. **`simple_java_9` — answer-key rigidity.** Model wrote
   `new MultiPoint(Arrays.asList(new Point(1,2), ...))`; gold accepts only
   `new MultiPoint(new Point[]{new Point(1,2), ...})`. Both are plausible Java; the checker does
   exact matching on the constructor expression.
4. **`simple_java_1` — mixed.** Model used a Java `HashMap` literal where gold wants a JSON dict,
   *and* got a key name wrong (`schema` vs `schemaFilter`) — that part is a real model error.

**Strategic consequence: this cannot lose badly.** Either we train past 67% and top the category,
or a material share of the 27-item hard core is checker defects and we publish a second finding of
the same species as the timeout discovery — most likely both.

## Steps

**1. Clean baseline (hours, ~$5).** Run `simple_java` in **Prompt** flavor, 3 independent runs,
report mean and standard deviation. Confirm we reproduce ~66%. With 100 items, one item = one
point, so variance matters more here than anywhere else.

**2. Classify all 39 union-failure items (hours, $0).** We already have the published failure
records for four models. Label each: *genuine model error* / *checker defect* / *answer-key
rigidity*. Output: `reports/java_failure_taxonomy.md`. This sets the realistic ceiling **and** is
finding #2 for the writeup.

**3. Synthetic Java training data (~1 day).** The simplest possible instance of the Track B
contract — single-turn, no environments needed. Target exactly the diagnosed failure modes:
   - Java collection literals: `new String[]{...}`, `new int[]{...}`, `Arrays.asList(...)`,
     `new ArrayList<>(...)`, `new HashMap<String,Object>(){{ put(...); }}`
   - Parameter types `ArrayList`, `HashMap`, `Array` where the model tends to emit a bare string
   - Object-constructor arguments (`new GenericView(...)`, `ByteBuffer.allocate(...)`)
   - Enum-style values (`XyzmMode.XYZ`, `BitOperation.AND`)
   - Negative examples: Python-style `["a","b"]` marked wrong, correct Java array marked right
   All rules from `CLAUDE.md` still bind: no BFCL content, MIT/Apache teacher only, decontamination
   check before training. Hold out 10% as dev.

**4. LoRA fine-tune + evaluate (~1 day, ~$100–300).** The harness supports single-GPU adapters
natively: `bfcl generate --model MODEL --test-category simple_java --backend vllm --num-gpus 1
--local-model-path /path/to/base --enable-lora --max-lora-rank 128`. Select checkpoints on our
own dev split only.

**5. Submit and publish.** Model-handler PR per `CONTRIBUTING.md`
(*"Raise a Pull Request with your new Model Handler and the necessary updates to the model
config"*). Outside PRs from small orgs demonstrably merge (MiniCPM-SALA, Pelican-VL,
FunctionGemma-270m, katanemo, MadeAgents, Bittensor are all on the board). Note maintainers batch
public-page refreshes roughly monthly, so a merged PR may not appear immediately.

## Success criteria (set now, before training)

- **Primary: ≥70.00% on `simple_java`, Prompt flavor, mean of 3 runs.** Not 68%. With 100 items a
  1–2 item margin over a five-way tie is inside noise, and the claim has to survive that. 70%
  gives 3 points of clearance.
- **Stretch: ≥73%**, which requires winning the entire contested margin.
- **Fallback claim if we land 67–69%:** tied-for-first plus the failure taxonomy and the checker
  defect — pre-registered now so it isn't goalpost-moving later.
- Report the FC flavor too, since the FC-vs-Prompt gap is itself a settings-axis result.

## Budget

~$100–300 GPU, 2–4 days, one person. No SerpAPI needed. No new external dependencies.

## Follow-on, same pipeline

`simple_javascript`: top **84.00%** (Open-Mistral-Nemo-2407, Prompt), ours 70.00% Prompt / 66.00%
FC, 50 items. Needs +14 — harder, but identical machinery. Winning both supports a cleaner claim:
**#1 on non-Python function calling**, which is stronger than either category alone.
