# Where the 257 element categories actually come from

**Target:** `/Users/amolpant/forecasting_networks/bfcl-sprint/parsebench/src/parse_bench/inference/providers/parse/kdl_frontier_nano.py` (3,323 lines; cited below as `K:<line>`)
**Date:** 2026-08-16
**Constraint honoured:** nothing under `parsebench/src/` was modified; nothing contacted the model endpoint. The instrumented run started at 20:06:58 (`instrumented_run.log`) was still alive and untouched throughout (`ps` shows pid 21771/21773, 10m17s elapsed, at the time of the last check).

Terms used, in plain language:

- **vLLM** — the open-source model server the pipeline talks to over an HTTP API shaped like OpenAI's `/v1/chat/completions`. One HTTP call = one image + one short text prompt.
- **Layout detection stage** — first of two model passes. The whole page is sent once; the model replies with special tokens giving a box and a *label* for each region.
- **Recognition stage** — second pass. Each region found above is cropped and sent back on its own to be turned into text/table/markdown.
- **Raw layout label** — the model's own word for a region, e.g. `header`, `list_item`, `table_caption`. Lower-cased, taken verbatim from the model's output.
- **Provider category** — the pipeline's internal 13-value vocabulary (`ElementCategory`, `K:97-117`), e.g. `Page-header`, `Section-header`.
- **Basic7** — the 7-label ontology the benchmark actually *scores* layout against by default (`DEFAULT_LAYOUT_EVALUATION_ONTOLOGY = "basic"`, `layout_ontology.py:130`). Both `Title` and `Section-header` collapse into a single `Section` label in it.
- **Ontology** — here just "which set of label names the score is computed over".

---

## 0. Headline answers

1. **The real category-assignment path is exactly the layout-token path we thought was bypassed.** `_nano_chat` → `is_native_layout_response` (`K:619`) → `parse_native_layout_tokens` (`K:655`) → `normalize_native_layout_items` (`K:661`) → `_category_for_item` (`K:757`) → `NATIVE_LAYOUT_CATEGORY_MAP` (`K:545`). There is exactly one secondary route, which can only *overwrite* an already-assigned category: `_nano_apply_picture_result` (`K:2802-2836`) sets `Chart` (`K:2822`, `K:2833`) or `Flowchart` (`K:2824`) from the second-stage picture response.
2. **`NATIVE_LAYOUT_CATEGORY_MAP` is not dead code. It is the sole source of 11 of the 12 categories ever observed** — proven below by categories that no other line in the file can produce.
3. **The contradiction was not a code contradiction at all — it was an experiment that never ran.** The "live 3-file run" performed **zero inference**. Its own summary says `"total": 0, "successful": 0, "failed": 0, "skipped": 12`. The 257 elements were read out of artifacts written by an *earlier* run at 18:27, before the hooks existed. `<|box_start|>` *is* present at runtime; it is simply never persisted.
4. **The `section_header` map-fix hypothesis is now empirically refuted, but for a different reason than "the map is unreachable."** The fix has been active in production the whole time (`emission.GENUINE_ABCD.section_header_map_fix = True`), and across **5,983 elements produced with the patched map in place, `Section-header` appears exactly 0 times**. The model does not emit the raw label `section_header`.
5. **The correct hook point is `K._nano_chat` (`K:2713`), filtered to the layout stage** — it is the only place the model's verbatim layout string exists, and the only hook that can also see the pages that die at `K:3091`. Plus one operational fix: the run must use `--force` or a fresh output directory, or the runner skips everything.

---

## 1. The real path, end to end

### 1.1 Entry

`KdlFrontierNanoProvider.run_inference` (`K:3216-3249`) renders pages (`_load_page_images`, `K:3198-3214`) and constructs the engine at `K:3232-3234`, then `_NanoEngine.parse_pages` (`K:3030-3066`) loops pages into `_parse_page` (`K:3068-3166`).

### 1.2 Layout pass — the one and only place a category is born

```python
3084	        layout_image = prepare_native_layout_image(image)
3085	        layout_content = await _nano_chat(
3086	            client, self._url, _nano_payload("layout", self._model, layout_image),
3087	            semaphore,
3088	        )
3089	        if not layout_content or not layout_content.strip():
3090	            return []
3091	        if not is_native_layout_response(layout_content):
3092	            logger.warning("page %d: layout response has no <|box_start|> tokens", page_no)
3093	            return []
3094	        items = parse_native_layout_tokens(layout_content)
```

`parse_native_layout_tokens` (`K:655-658`):

```python
655	def parse_native_layout_tokens(content: str) -> list[dict[str, Any]]:
656	    raw_items = parse_native_raw_layout_tokens(content)
657	    normalized_items = normalize_native_layout_items(raw_items)
658	    return [item.to_output_dict() for item in normalized_items]
```

- `parse_native_raw_layout_tokens` (`K:630-652`) runs `_NATIVE_LAYOUT_RE` (`K:531-536`) over the string and stores `raw_category = match.group(5).strip().lower()` (`K:640`) into `NativeLayoutItem.raw_category` (`K:597`).
- `normalize_native_layout_items` (`K:661-730`) sets the category at `K:721`: `category=_category_for_item(item, metadata)`.
- `_category_for_item` (`K:757-763`) is the decision:

```python
757	def _category_for_item(item: NativeLayoutItem, metadata: dict[str, Any]) -> str:
758	    if item.raw_category in _LIST_CHILD_CATEGORIES and (
759	        item.raw_category in {"list_item", "ref_text"}
760	        or metadata.get("parent_raw_category") == "list"
761	    ):
762	        return "List-item"
763	    return normalize_layout_category(item.raw_category, NATIVE_LAYOUT_CATEGORY_MAP)
```

`normalize_layout_category` (`K:212-218`) = `_map_provider_category` (`K:227-239`, dictionary lookup, exact then case-folded, else pass the raw string through) followed by `_canonicalize_category` (`K:242-246`, keep it only if it case-folds to one of the 13 canonical names, otherwise **silently return `Text`**).

### 1.3 Where the raw label is destroyed

`to_output_dict` (`K:612-616`) does keep it — verified by running the real function offline in the parsebench virtual environment:

```
{'bbox': [0.1, 0.1, 0.9, 0.15], 'category': 'Page-header',    'layout_order': 0, 'raw_category': 'header',         'angle': 0}
{'bbox': [0.1, 0.2, 0.9, 0.26], 'category': 'Text',           'layout_order': 1, 'raw_category': 'section_header', 'angle': 0}
{'bbox': [0.1, 0.3, 0.9, 0.36], 'category': 'Section-header',  'layout_order': 2, 'raw_category': 'section-header', 'angle': 0}
{'bbox': [0.1, 0.4, 0.9, 0.46], 'category': 'Title',          'layout_order': 3, 'raw_category': 'title',          'angle': 0}
```

The raw label dies one function later, in `_nano_group_by_bucket` (`K:2745-2791`), which builds a **fresh** dict and copies only four fields across:

```python
2779	        element_info = {
2780	            "bbox": bbox,
2781	            "category": cat,
2782	            "layout_order": item.get("layout_order", 0),
2783	            "page_number": item.get("page_number", 1),
2784	            "preprocessed_image": preprocessed_img,
2785	        }
```

**`K:2779-2785` is the exact line range at which the model's raw layout label becomes unrecoverable.** This is also why `K:2754` reads `cat = item.get("category", "Text")` and looks as if categories arrived from nowhere: they arrived from `K:721`, three frames up.

Confirmed empirically (offline, stubbed HTTP): element dicts leaving `_parse_page` have keys `['angle', 'bbox', 'category', 'content', 'layout_order', 'page_number']` — no `raw_category`.

### 1.4 Recognition pass — the only other category writer

`_nano_apply_picture_result` (`K:2802-2836`), called from `recognize` at `K:3119`, can *overwrite* the layout-assigned category:

```python
2821	        if image_type == "chart":
2822	            el["category"] = "Chart"
2823	        elif image_type == "flow":
2824	            el["category"] = "Flowchart"
...
2831	    if content_str.startswith("|") and is_valid_markdown_table(content_str):
2832	        el["content"] = normalize_markdown_table_content(content_str)
2833	        el["category"] = "Chart"
```

Proof this route fires in production: `Flowchart` appears **50 times** in the completed Aug-11 run, and `Flowchart` is *not* a value in `NATIVE_LAYOUT_CATEGORY_MAP` (verified: the map's value set is `['Caption','Chart','Footnote','Formula','List-item','Page-footer','Page-header','Picture','Table','Text','Title']`). `K:2824` is the only line in the file that can produce it.

A grep for every category write site in the file returns exactly these two writers plus read-only defaults:

```
721:  category=_category_for_item(item, metadata)     <- layout route
2781: "category": cat,                                <- copy of the above
2822/2824/2833: el["category"] = "Chart"/"Flowchart"  <- recognition override
2754/2842/2929/3053/3290/3293: .get("category", ...)  <- reads only
```

### 1.5 Persistence

`parse_pages` (`K:3049-3058`) writes the four-field payload that ends up in `*.raw.json`:

```python
3053	                    "category": el.get("category", "Text"),
3054	                    "bbox": el.get("bbox"),
3055	                    "content": el.get("content") or "",
3056	                    "layout_order": el.get("layout_order", 0),
```

That is byte-for-byte the shape found in the artifacts (verified: `['bbox','category','content','layout_order']`). `normalize` (`K:3286-3297`) then copies `category` into `LayoutItemIR.type` and into the bounding-box label, which is what the Visual-Grounding / layout metrics consume.

---

## 2. Is `NATIVE_LAYOUT_CATEGORY_MAP` reachable? Yes — proof

The map is live. Three independent proofs:

1. **`Page-header` cannot be produced any other way.** The only line in the file that can yield the string `Page-header` is the map entry `"header": "Page-header"` (`K:554`). Without the map, raw label `header` would pass through `_map_provider_category` unchanged and then fail `_canonicalize_category` (`"header"` is not in `_CANONICAL_BY_CASEFOLD`, whose keys are `['caption','chart','flowchart','footnote','formula','list-item','page-footer','page-header','picture','section-header','table','text','title']`) → `Text`. The completed Aug-11 run contains **2,978 `Page-header` elements**. Same argument applies to `Page-footer` (3,193), `Caption` (2,547), `Footnote` (1,878), `Formula` (87) — none of those raw labels (`footer`, `page_number`, `*_caption`, `*_footnote`, `equation*`) is canonical, so each one required the map.
2. **Direct offline execution.** Feeding `parse_native_layout_tokens` a synthetic layout string produced `header → Page-header` (output quoted in §1.3). Wrapping `_category_for_item` and `parse_native_layout_tokens` and then driving the real `_NanoEngine._parse_page` with `_nano_chat` stubbed out (no network) produced `hook calls: {'_category_for_item': 4, 'parse_native_layout_tokens': 1}`. **Both hooks fire when the pipeline actually runs a page.** Script: `/Users/amolpant/forecasting_networks/bfcl-sprint/ourparser/diag/prove_hook_fires.py`.
3. **The map is rebound in production and the rebinding is observable in configuration.** `ourparser/provider.py` `patched_bindings()` replaces `K.NATIVE_LAYOUT_CATEGORY_MAP` with `emission.PATCHED_NATIVE_LAYOUT_CATEGORY_MAP` (`ourparser/emission.py:114-117`) whenever `config.section_header_map_fix` is true, which `GENUINE_ABCD` sets (`ourparser/emission.py:162-166`). Both the 18:27 run and the currently-running 20:06 run use `emission_set: genuine_abcd` (verified in the artifacts' own `pipeline.config`).

So the earlier statement "`NATIVE_LAYOUT_CATEGORY_MAP` lacks a `section_header` key" was **true as a fact about the vendored file** and **false as a description of what runs**: the patch has been in place since before the 18:27 run.

---

## 3. Reconciling the contradiction: the run never ran

The suspected options were "the token is present and stripped before persistence" or "a different function produces the elements". The answer is the **first**, and the reason the hooks saw nothing is a third option nobody listed: *the instrumented process did no inference at all*.

`parsebench/output/kdl_frontier_nano_patched/_summary.json`:

```json
{ "total": 0, "successful": 0, "failed": 0, "skipped": 12,
  "started_at": "2026-08-16T18:33:22.756165",
  "completed_at": "2026-08-16T18:33:22.763383" }
```

Seven milliseconds, twelve skips, zero inferences. `_metadata.json` from the same run records `"force": false`.

The skip is `InferenceRunner._is_already_processed` (`runner.py:264-292`), consulted before every document (`runner.py:801`, `:958`, `:1089`, `:1189`):

```python
264	    def _is_already_processed(self, example_id: str) -> bool:
266	        if self.force:
267	            return False
269	        raw_path, normalized_path = self._get_result_paths(example_id)
272	        if self.save_normalized and normalized_path.exists():
277	                if "request" in data and "output" in data:
278	                    return True
```

`force` defaults to `False` (`runner.py:136`, `cli.py:104`).

The 12 `*.result.json` files it found were written at **18:27**, by an earlier uninstrumented run. Re-counting elements from exactly those 12 files reproduces the reported figures precisely:

```
12 files, 257 elements
[('Text', 130), ('Title', 41), ('Page-header', 18), ('Page-footer', 14), ('Footnote', 14),
 ('Picture', 12), ('Caption', 11), ('List-item', 9), ('Chart', 5), ('Table', 3)]
```

That is the stated distribution, item for item. The 257 elements and the zero hook calls come from two different runs. Both label-capture sidecars are consistent with this: `runs/labels_smoke/label_capture_records.jsonl` and `runs/labels_smoke2/label_capture_records.jsonl` are **0 bytes**, and `runs/labels/` is empty.

**On the missing `<|box_start|>` in artifacts (evidence item 4):** that is expected and proves nothing. A grep of both output trees for `box_start`, `ref_start` and `raw_category` returns **no files**. The layout response string is a local variable (`layout_content`, `K:3085`) that is parsed and discarded inside `_parse_page`; only the *recognition-stage* output is ever stored, as `element["content"]`. The token's absence from disk is a property of the persistence code (`K:3049-3058`), not evidence about the model.

**On evidence item 5 (`raw_category` missing despite `NormalizedNativeLayoutItem` carrying it):** explained by `K:2779-2785`, §1.3.

### 3.1 The instrumentation itself is sound

`ourparser/instrument.py` wraps `K._category_for_item` and `K.parse_native_layout_tokens` as module attributes. Both are called through module-global lookup (`K:721` and `K:3094`), so the rebinding is visible. The runner is thread-based, not process-based (`runner.py:180`, `concurrent.futures.ThreadPoolExecutor`; no `ProcessPool`/`multiprocessing` anywhere in `runner.py` or either `cli.py`), so a process-wide monkeypatch covers every worker. §2 proof 2 shows both hooks firing 4× and 1× on a single synthetic page. **Nothing needs fixing in the hook mechanism; only in how the run is launched.**

---

## 4. Where a classification fix would actually go — and what the scoring board really rewards

### 4.1 Which numbers 0.784 / 0.869 are

From the completed Aug-11 run, `parsebench/output/kdl_frontier_nano/layout/_evaluation_report.json`, 500/500 examples successful:

| metric | value |
|---|---|
| `avg_layout_classification_pass_rate` | **0.7844** |
| `avg_layout_localization_pass_rate` | **0.8691** |
| `avg_layout_attribution_pass_rate` | 0.8478 |
| `avg_layout_reading_order_pass_rate` | 0.7971 |
| `avg_layout_element_rule_pass_rate` | 0.7419 |

Totals: 14,203 classification rules evaluated, 11,051 passed → **3,152 failing classification rules** is the entire prize.

The pass/fail decision is `evaluators/layoutdet.py:1085-1090`:

```python
1085	                if localization_pass and best_pred_idx is not None:
1086	                    pred_class_raw = page_predictions[best_pred_idx]["class_name"]
1087	                    pred_class_norm = pred_class_raw
1088	                    classification_pass = pred_class_norm == gt_class_norm
```

A plain string equality, and only reached when localization already passed (`classification_reason = "no_localization"` otherwise, `:1093`).

### 4.2 The decisive constraint nobody has accounted for: the scored ontology is Basic7

Predicted labels reach that comparison through `project_layout_predictions` (`evaluation/layout_label_mappers/projection.py:38-46`): `mapper.to_canonical(...)` then `mapper.to_target_ontology(label_for_view, target_ontology)`, with `target_ontology` defaulting to `"basic"` (`layout_ontology.py:130`). For this provider the mapper is `CanonicalPassthroughMapper` (`layout_label_mappers/mappers.py:45-58`) and the adapter pre-collapses `Chart`/`Flowchart` → `Picture` (`layout_adapters/adapters.py:2919`).

`CANONICAL_TO_BASIC` (`layout_ontology.py:139-158`) then merges:

- `Title` **and** `Section-header` → `Section`
- `Text`, `List-item`, `Caption`, `Footnote`, `Formula`, `Code`, `Document-index`, `Key-Value Region`, `Form`, both checkbox labels → `Text`
- `Page-header`, `Page-footer`, `Picture`, `Table` → themselves

Confirmed by the report's own per-class metric names, which are exactly the six Basic7 classes with ground-truth support: `avg_f1_Section 0.7167`, `avg_f1_Text 0.7094`, `avg_f1_Table 0.7957`, `avg_f1_Picture 0.6985`, `avg_f1_Page-footer 0.5871`, `avg_f1_Page-header 0.3608`.

Projecting `NATIVE_LAYOUT_CATEGORY_MAP` through that collapse shows the 26-key map is worth only **five distinguishable outcomes** at scoring time:

```
basic=Page-footer  provider=Page-footer  raw: footer, page_number
basic=Page-header  provider=Page-header  raw: header
basic=Picture      provider=Chart        raw: chart
basic=Picture      provider=Picture      raw: image, image_block
basic=Section      provider=Title        raw: title
basic=Table        provider=Table        raw: table
basic=Text         provider=Caption      raw: code_caption, image_caption, table_caption
basic=Text         provider=Footnote     raw: image_footnote, page_footnote, table_footnote
basic=Text         provider=Formula      raw: equation, equation_block, inline_formula
basic=Text         provider=List-item    raw: list, list_item, ref_text
basic=Text         provider=Text         raw: algorithm, aside_text, code, phonetic, text, unknown
```

Consequences, all load-bearing:

- **Fifteen of the 26 map keys are score-irrelevant for classification.** Every `Caption`, `Footnote`, `Formula` and `List-item` entry scores identically to `Text`. Perfecting caption-vs-footnote-vs-list-item earns exactly zero classification points.
- **`Section-header` vs `Title` is also worth exactly zero** — both are `Section`. So the only way a `Section-header` change can score is by moving elements out of `Text`, not by re-labelling existing `Title`s.
- The 45,322 predicted elements of the Aug-11 run project to: `Text` 28,279 · `Section` 6,031 · `Picture` 3,599 · `Page-footer` 3,193 · `Page-header` 2,978 · `Table` 1,242.

### 4.3 The `section_header` fix is refuted by production data

The fix has been live since before 18:27 (`section_header_map_fix=True` in `GENUINE_ABCD`). Counting `category` across every `*.raw.json` produced with the patched map in place:

| batch | documents | elements | `Section-header` |
|---|---|---|---|
| 18:27 (12 docs) | 12 | 257 | **0** |
| 20:08–20:11 (in-progress run, snapshot) | 230 | 5,726 | **0** |
| combined | 242 | **5,983** | **0** |

Categories seen in the in-progress batch: `Text` 2,305 · `List-item` 874 · `Title` 850 · `Page-header` 392 · `Page-footer` 340 · `Caption` 271 · `Picture` 245 · `Footnote` 180 · `Chart` 164 · `Table` 99 · `Flowchart` 4 · `Formula` 2. No `Section-header`.

The mechanism was never broken — adding the key does work (`section_header` → `Section-header` is reachable, and `section-header` with a hyphen already survives via `_canonicalize_category`, both verified in §1.3). **The model simply never emits `section_header`.** Twelve of the thirteen canonical categories are observed in the wild; `Section-header` is the only one that never appears, and the map cannot mint it from any other label.

### 4.4 Where the real classification headroom is

Ranked by Basic7 F1 in the Aug-11 run, the weakest class by a wide margin is **`Page-header`: F1 0.3608, precision 0.3723, recall 0.3930** — against `Section` 0.7167, `Text` 0.7094, `Picture` 0.6985, `Table` 0.7957, `Page-footer` 0.5871. `Page-header` and `Page-footer` are *identity-mapped* in Basic7, so unlike caption/footnote/list-item they are fully exposed to the metric.

`Page-header` and `Page-footer` are produced by exactly three map lines:

```python
553	    "footer": "Page-footer",
554	    "header": "Page-header",
563	    "page_number": "Page-footer",
```

So the highest-value single-line interventions, in order, are:

1. **`K:554` (`"header" → "Page-header"`)** — 2,978 predictions at F1 0.361; both precision and recall are near-chance, meaning the model's `header` label and the benchmark's `Page-header` class disagree systematically, not marginally. Worth diagnosing before changing: the fix might be re-routing some `header` → `Title`/`Text`, or it might be a localization/threshold artefact.
2. **`K:563` (`"page_number" → "Page-footer"`)** — page numbers appearing in a page *header* are currently forced to `Page-footer`. A y-coordinate-aware rule (the bbox is already in hand at `K:721`) would be strictly better than the current unconditional mapping.
3. **`K:2822`/`K:2833` (`Chart` override)** — harmless for classification, because the layout adapter collapses `Chart` → `Picture` (`adapters.py:2919`), so both branches score as `Picture` either way. Not a lever.

The single function where predicted categories are decided, and therefore the place any classification fix belongs, is:

> **`_category_for_item`, `kdl_frontier_nano.py:757-763`** — with its lookup table `NATIVE_LAYOUT_CATEGORY_MAP`, `kdl_frontier_nano.py:545-572`.

To emit a `Section-header`-equivalent category one only needs a map entry whose *value* is the exact string `"Section-header"` (`_canonicalize_category`, `K:242-246`, accepts it because it is in `CANONICAL_LAYOUT_CATEGORIES`, `K:191`; `CATEGORY_TO_RECOGNITION_BUCKET`, `K:137`, already routes it to the `text` recognition bucket so nothing downstream breaks; and `_nano_format_element`, `K:2931-2933`, already renders it as a `## ` heading). **The blocker is not the map — it is the absence of any raw label to hang it on.** Until the label-capture run reveals the model's actual vocabulary, there is no key to add.

### 4.5 Coupling warning

Changing the map is **not** a grounding-only change. `_nano_format_element` (`K:2931-2933`) turns `Section-header` into a `## ` markdown heading, which feeds the Semantic Formatting and Content Faithfulness dimensions. Any map edit must be measured on all three dimensions, not just layout classification.

---

## 5. Is the raw label recoverable, and what is the correct hook?

**Recoverable from existing artifacts: no.** Grep across both `parsebench/output/kdl_frontier_nano/` and `parsebench/output/kdl_frontier_nano_patched/` for `raw_category`, `box_start`, and `ref_start` returns **zero files**. Persisted element dicts hold `['bbox','category','content','layout_order']` only (`K:3049-3058`). The information is destroyed at `K:2779-2785` inside the process and was never written down.

**Recoverable in memory: yes, at four points.** In order of decreasing coverage:

| # | Hook | Sees | Limitation |
|---|---|---|---|
| **A** | `K._nano_chat` (`K:2713`), filtered to the layout stage | the model's **verbatim** layout string, including boxes, rotation tokens and any label the regex fails to match | none of consequence |
| B | `K.parse_native_raw_layout_tokens` (`K:630`) | `NativeLayoutItem.raw_category` (`K:597`) for every regex-matched region | loses regions the regex missed |
| C | `K.parse_native_layout_tokens` (`K:655`) | dicts that **do** carry `raw_category` (verified §1.3); also loses container items dropped at `K:691-698` | as above |
| D | `K._category_for_item` (`K:757`) | raw label + resulting category, per item | as above |

**Recommended: hook A.** Two reasons the other three cannot match it:

1. Only A sees pages that return `[]` at `K:3089-3093` — a page whose layout response is empty or malformed produces no items, so hooks B/C/D are silent and the page is indistinguishable from "blank page" in the capture. Given `avg_unmatched_gt_elements = 4.69` and `total_unmatched_gt_elements = 2,043` in the Aug-11 run, some recall loss may be happening exactly there and only A can attribute it.
2. Storing the raw string makes **every** future map variant, regex variant, and container-suppression variant measurable by replay with no further GPU time. Hooks B–D bake in the current regex and the current suppression rules at capture time.

`_nano_chat` is invoked as a module global at `K:3085` (layout) and `K:3115`/`K:3124` (recognition), so `K._nano_chat = wrapper` is sufficient — empirically confirmed: the offline proof script replaces exactly that attribute and the real `_parse_page` picks it up. Distinguish the layout call by the prompt text, `payload["messages"][0]["content"][-1]["text"] == _NANO_PROMPTS["layout"]` (`K:2698`, `K:2596-2604`), which is `"\nLayout Detection:\n"`.

### 5.1 Three operational changes without which any hook fails again

1. **Defeat the skip.** Pass `force=True` / `--force`, or point `--output_dir` at an empty directory. Otherwise `_is_already_processed` (`runner.py:264-292`) returns `True` for every already-written document and the run does nothing — the exact failure of the 18:30 and 18:33 attempts. *(The 20:06 run in progress is fine on this point: it is producing new documents at 20:08–20:11, so its hooks are firing for those.)*
2. **Flush incrementally.** `instrument.flush()` is called only from the `label_capture()` context manager's `finally` (`instrument.py:105-110`). A `kill -9`, an out-of-memory kill, or a lost SSH session yields nothing. Append each record to a JSON-Lines file as it is observed.
3. **Do not compute `raw_in_map` against the live map.** `instrument.py:49` evaluates `raw in K.NATIVE_LAYOUT_CATEGORY_MAP`, but during a `kdl_frontier_nano_patched` run that attribute is the *patched* map (`ourparser/provider.py` `patched_bindings`). So `section_header` will be reported as `raw_in_map: True` and will never show up in `unmapped_label_counts`. Compare against a snapshot of the vendored map taken at import time, and record both.

---

## 6. Side finding, unrelated to categories but material

**The `layout` group scores nothing at all under the patched pipeline.** `parsebench/output/kdl_frontier_nano_patched/layout/_evaluation_report.json`: `"successful": 0, "failed": 3`, every one with `"error": "Worker error: Inference output is not LayoutOutput and no provider adapter matched."`

Cause: the adapter is registered for the provider key `"kdl_frontier_nano"` only (`layout_adapters/adapters.py:2876`), and `create_layout_adapter` (`layout_adapters/registry.py:66-75`) matches provider names by exact membership (`provider_name in registration.keys`). The patched provider registers as `"kdl_frontier_nano_patched"` (`ourparser/provider.py`, `PATCHED_PIPELINE`), so no adapter matches and it falls through to `__default__`, which raises.

Fix is one line in our own code (not in `parsebench/src/`): register `KdlFrontierNanoLayoutAdapter` under the patched provider names too, via `parse_bench.evaluation.layout_adapters.registry.register_layout_adapter`, from `ourparser/provider.py`. **Until that is done, every classification/localization number for the patched pipeline is unmeasurable** — which also means the in-progress run will not produce a layout score to compare against 0.784.

---

## 7. What I could not determine

- **The model's actual raw layout-label vocabulary.** No artifact retains it and no completed capture exists. The in-progress 20:06 run will write `runs/labels/label_capture_summary.json` on exit (hook D, `instrument.py`), which will answer it for the ~230+ freshly inferred documents — but it will not cover the 12 skipped ones, its `raw_in_map` column is measured against the patched map (§5.1 item 3), and nothing is written until the process exits cleanly. I did not read it because it does not exist yet.
- **Why `Page-header` F1 is 0.3608.** I established it is the weakest scored class and that `K:554` is its only source, but not whether the failures are wrong-label, wrong-box, over-prediction, or a ground-truth convention mismatch. `avg_num_predictions 41.78` vs `avg_num_ground_truth 32.61` and `total_unmatched_pred_elements 5,007` vs `total_unmatched_gt_elements 2,043` say the pipeline over-predicts overall, but I did not break that down per class. The per-rule detail needed is in the run's `_evaluation_rule_results.csv` / `classification_reason` fields (`evaluators/layoutdet.py:1256-1257`) and was not analysed.
- **Whether any suppressed container item mattered.** `normalize_native_layout_items` drops `list` and `image_block` containers and equation children (`K:691-698`), and `_nano_group_by_bucket` drops sub-5px and monochrome crops (`K:2771-2776`). I did not quantify how many ground-truth elements those two filters cost.
- **The 18:27 run's launch command.** I could not find it in any checked-in script (`run_instrumented.sh` targets 20:06 and writes `runs/labels`), so I cannot state from primary evidence whether label capture was enabled then. `runs/labels/` exists but is empty, which is consistent either with a manual `mkdir` or with a killed run; I did not resolve which.

---

## 8. Verification commands used

All read-only; none contacted the endpoint.

```bash
# element counts + distribution from the 12 skipped artifacts  -> 257, matching distribution
cd parsebench/output/kdl_frontier_nano_patched && python3 -c "..."   # §3

# the smoking gun
cat parsebench/output/kdl_frontier_nano_patched/_summary.json         # skipped: 12, total: 0

# raw labels / layout tokens absent from every artifact
grep -rl "raw_category\|box_start\|ref_start" parsebench/output/kdl_frontier_nano{,_patched}   # no matches

# real parser, real venv, no network
parsebench/.venv/bin/python  # -> header→Page-header, section_header→Text, section-header→Section-header

# both hooks fire on a real _parse_page with _nano_chat stubbed
cd parsebench && .venv/bin/python ../ourparser/diag/prove_hook_fires.py
# hook calls: {'_category_for_item': 4, 'parse_native_layout_tokens': 1}
```

New file created (outside `parsebench/src/`, as permitted): `ourparser/diag/prove_hook_fires.py`.
