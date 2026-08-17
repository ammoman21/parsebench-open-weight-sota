# Publish & submit checklist (execute only on explicit user go)

PRE (blocking): [ ] confirmation run scored; both runs within tolerance -> fill variance into
model card + yaml  [ ] merged weights fully synced + sha256 verified  [ ] decide HF org name
("Florin" placeholders in 3 files)

1. HF: create repo <org>/florin-parser-nano -> upload merged/ + adapter/ + MODEL_CARD.md
   (as README.md) + .eval_results/parsebench.yaml. License field agpl-3.0. PRIVATE first,
   flip public at submission moment.
2. GitHub repo public: flip parsebench-open-weight-sota to public (rotate nothing — secret
   scan was clean; re-run scan first anyway).
3. ParseBench submission: PR to run-llama/ParseBench adding provider/pipeline
   (kdl_frontier_nano_patched + our weights endpoint doc) OR eval-results route per their
   card. Include reproduction commands + the environment-gap disclosure up front.
4. Courtesy notes: KoreaDeep (base-model attribution + the Section-header dead-code and
   over-header findings); LlamaIndex (five benchmark defects incl. silent __default__
   adapter fallback, chart bold-title rule, zero-weight categories).
5. Findings paper: update §9 tables with it7 numbers + confirmation variance; add fine-tune
   section from FINETUNE_METHOD.html.
