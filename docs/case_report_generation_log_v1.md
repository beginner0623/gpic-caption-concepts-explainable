# Case Report Generation Log v1

이 문서는 caption-to-concept 결과를 사람이 읽을 수 있는 Markdown report로 생성한 기록을 남긴다.

## 2026-07-02: sentence 100개 시험 report

목적:

- 10k 전체를 보기 전에 sentence caption 100개만 펼친 Markdown report를 만든다.
- 향후 1k 단위 split report 생성 형식을 시험한다.

입력 선택:

- 처음에는 `outputs/stage1_eval100/sentence_rows.jsonl`를 쓰려고 했으나 실제 sentence row가 79개뿐이었다.
- 사용자가 요청한 것은 "문장 100개"였으므로 `outputs/benchmark_real10k_train/sentence_rows_9896.jsonl.gz`에서 앞 100개 sentence row를 사용했다.

Pipeline command summary:

```powershell
.\scripts\run_python.ps1 scripts\run_stage3_annotate.py `
  --input outputs\benchmark_real10k_train\sentence_rows_9896.jsonl.gz `
  --output outputs\case_reports_sentence100_current\stage3_records.jsonl `
  --object-mwes resources\lexicons\object_mwes.tsv `
  --summary outputs\case_reports_sentence100_current\stage3_summary.jsonl `
  --model en_core_web_trf `
  --batch-size 128 `
  --limit 100 `
  --require-gpu

.\scripts\run_python.ps1 scripts\run_stage4_extract_raw.py `
  --input outputs\case_reports_sentence100_current\stage3_records.jsonl `
  --raw-mentions outputs\case_reports_sentence100_current\raw_mentions.jsonl `
  --raw-edges outputs\case_reports_sentence100_current\raw_edges.jsonl `
  --summary outputs\case_reports_sentence100_current\stage4_summary.jsonl

.\scripts\run_python.ps1 scripts\run_stage5_canonicalize.py `
  --raw-mentions outputs\case_reports_sentence100_current\raw_mentions.jsonl `
  --raw-edges outputs\case_reports_sentence100_current\raw_edges.jsonl `
  --lexicon-dir resources\lexicons `
  --canonical-mentions outputs\case_reports_sentence100_current\canonical_mentions.jsonl `
  --canonical-edges outputs\case_reports_sentence100_current\canonical_edges.jsonl `
  --summary outputs\case_reports_sentence100_current\stage5_summary.jsonl

.\scripts\run_python.ps1 scripts\run_stage6_export_counts.py `
  --canonical-mentions outputs\case_reports_sentence100_current\canonical_mentions.jsonl `
  --canonical-edges outputs\case_reports_sentence100_current\canonical_edges.jsonl `
  --output-dir outputs\case_reports_sentence100_current\stage6 `
  --summary outputs\case_reports_sentence100_current\stage6_summary.jsonl

.\scripts\run_python.ps1 scripts\build_caption_concept_md.py `
  --sentence-rows outputs\benchmark_real10k_train\sentence_rows_9896.jsonl.gz `
  --canonical-mentions outputs\case_reports_sentence100_current\canonical_mentions.jsonl `
  --canonical-edges outputs\case_reports_sentence100_current\canonical_edges.jsonl `
  --facts outputs\case_reports_sentence100_current\stage6\facts.jsonl `
  --output outputs\case_reports_sentence100_current\caption_to_concept_cases_0001_0100.md `
  --start 0 `
  --limit 100 `
  --max-object-pairs-per-caption 40
```

Main outputs:

- `outputs/case_reports_sentence100_current/caption_to_concept_cases_0001_0100.md`
- `outputs/case_reports_sentence100_current/stage3_records.jsonl`
- `outputs/case_reports_sentence100_current/raw_mentions.jsonl`
- `outputs/case_reports_sentence100_current/raw_edges.jsonl`
- `outputs/case_reports_sentence100_current/canonical_mentions.jsonl`
- `outputs/case_reports_sentence100_current/canonical_edges.jsonl`
- `outputs/case_reports_sentence100_current/stage6/facts.jsonl`

Observed counts:

- captions: 100
- Stage 3 tokens: 4,740
- Stage 3 noun chunks: 1,222
- raw mentions: 2,366
- raw edges: 1,348
- canonical mentions: 2,366
- canonical edges: 1,348
- Stage 6 facts: 20,972
- object pair facts: 17,958

Stage 5 note:

- `canonical_source_counts`: `raw_fallback = 2366`
- `parent_filled_counts`: `without_parent = 2366`
- Meaning: current lexicon coverage is still low. The report is useful for structural inspection, but not yet for synonym/parent coverage evaluation.

Validation:

- `scripts/build_caption_concept_md.py` successfully generated a 100-caption Markdown file.
- Python UTF-8 read confirmed Korean report text is stored correctly.
- PowerShell `Get-Content` may display mojibake, but the file itself is UTF-8.

Known limitation of current report:

- Object co-occurrence pairs are capped per caption for readability.
- The cap used here is 40 ordered pairs per caption.
- Full object pair facts remain available in `stage6/facts.jsonl`.

## 2026-07-02: sentence 20개 Stage 3 포함 상세 report

목적:

- 100개 report가 너무 길어서 먼저 20개 caption만 펼친 Markdown report를 만든다.
- 같은 파일 안에 concept 결과뿐 아니라 사전에 가공된 Stage 3 annotation도 같이 보여준다.

입력:

- sentence rows: `outputs/benchmark_real10k_train/sentence_rows_9896.jsonl.gz`
- Stage 3 records: `outputs/case_reports_sentence100_current/stage3_records.jsonl`
- Stage 5 canonical mentions: `outputs/case_reports_sentence100_current/canonical_mentions.jsonl`
- Stage 5 canonical edges: `outputs/case_reports_sentence100_current/canonical_edges.jsonl`
- Stage 6 facts: `outputs/case_reports_sentence100_current/stage6/facts.jsonl`

Command:

```powershell
.\scripts\run_python.ps1 scripts\build_caption_concept_md.py `
  --sentence-rows outputs\benchmark_real10k_train\sentence_rows_9896.jsonl.gz `
  --stage3-records outputs\case_reports_sentence100_current\stage3_records.jsonl `
  --canonical-mentions outputs\case_reports_sentence100_current\canonical_mentions.jsonl `
  --canonical-edges outputs\case_reports_sentence100_current\canonical_edges.jsonl `
  --facts outputs\case_reports_sentence100_current\stage6\facts.jsonl `
  --output outputs\case_reports_sentence100_current\caption_to_concept_cases_0001_0020_with_stage3.md `
  --start 0 `
  --limit 20 `
  --max-object-pairs-per-caption 40
```

Output:

- `outputs/case_reports_sentence100_current/caption_to_concept_cases_0001_0020_with_stage3.md`

Included Stage 3 sections per caption:

- protected spans: quote/hyphen/object MWE 같은 protected span metadata
- noun chunks: chunk text, token span, root, root lemma, root POS/TAG/DEP, root head
- tokens: token index, text, lemma, POS, TAG, MORPH, DEP, head index, head text, object MWE flag

Validation:

- script execution succeeded with `caption_count=20` and `stage3_records_included=true`.
- generated Markdown contains `Stage 3 Linguistic Annotation`, `Protected Spans`, `Noun Chunks`, and `Tokens / POS / Lemma / Dependency` sections.

Note:

- This was report rendering only. No extraction rule, canonicalization rule, or count-export rule was changed.

## 2026-07-07: sentence 101-200개 다른 샘플 run

목적:

- 기존 앞 100개가 아닌 다른 sentence caption 100개로 현재 object inventory gate를 확인한다.

입력:

- source pool: `outputs/benchmark_real10k_train/sentence_rows_9896.jsonl.gz`
- selected offset: 100
- selected limit: 100
- subset file: `outputs/case_reports_sentence100_0101_0200_current/sentence_rows_0101_0200.jsonl`

실행 결과:

- Stage 3 completed.
  - captions: 100
  - tokens: 4661
  - noun chunks: 1169
  - GPU enabled: true
- GPIC observed object inventory built.
  - inventory rows: 567
  - chosen: 317
  - excluded: 38
  - needs_manual: 212
  - needs_manual reasons:
    - manual_joined_variant_required: 2
    - manual_objectness_required: 129
    - manual_synset_required: 81
- Diagnostic parent enrichment was run before manual resolution.
  - This was not a valid final pipeline step because `needs_manual=212` rows still remained.
  - selected_synset_missing_rows: 119
  - parent_filled_rows: 448
- Diagnostic canonical enrichment was also run before manual resolution.
  - This exposed one canonical matching issue but should not be treated as a completed canonical pipeline step.
  - Current script now blocks canonical enrichment when `needs_manual` rows remain.
- The diagnostic canonical run initially found one unresolved canonical row:
  - observed_surface: `café`
  - selected synset: `oewn-02939042-n`
  - issue: observed surface `café` did not match OEWN lemma `cafe`
- Added general canonical matching key diacritic folding and re-ran the diagnostic canonical enrichment.
  - canonical_ambiguous_rows: 0
  - canonical_selected_rows: 448
- Stage 4 was then intentionally blocked by remaining manual synset/objectness rows.
  - first blocker caption_id: `03c02adce7cf29116e375e28c818f14f23bd6a3c71e3db70f29d2abcbb5ecfed`
  - first blocker surface: `jersey`
  - reason: `manual_synset_required`
  - tag: `ambiguous_wn30_all_zero`

Main outputs:

- `outputs/case_reports_sentence100_0101_0200_current/stage3_records.jsonl`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory.tsv`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_needs_manual.tsv`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_canonical_ambiguous.tsv`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_canonical_summary.json`

Note:

- This run did not generate Stage 5/6 outputs or a caption-level concept report because current policy requires `needs_manual` rows to be resolved before Stage 4 extraction.

## 2026-07-07: sentence 101-200 manual-resolved inventory run

Purpose:

- Import the reviewed manual-resolution TSV for the sentence 101-200 sample.
- Recompute parent evidence and canonical labels after manual synset/objectness decisions.
- Verify that Stage 4-6 can run after `needs_manual` rows are removed.

Inputs:

- manual resolved TSV from Downloads:
  - `gpic_observed_object_inventory_100_manual_resolved.tsv`
- manual resolution audit TSV from Downloads:
  - `gpic_observed_object_inventory_100_manual_resolution_audit.tsv`

Imported outputs:

- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_manual_resolved.tsv`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_manual_resolution_audit.tsv`

Manual-resolution distribution:

- inventory rows: 567
- `chosen`: 514
- `excluded`: 53
- `needs_manual`: 0
- audit rows: 212
- audit `chosen`: 197
- audit `excluded`: 15

Corrections before final enrichment:

- Fixed one invalid manual OEWN ID:
  - row: `helmets`
  - old synset: `oewn-03521675-n`
  - corrected synset: `oewn-03518281-n`
  - reason: OEWN local lookup showed `oewn-03518281-n` as the protective headgear sense.
- Fixed one manual head-correction row with a missing selected synset:
  - row: `white feathers`
  - old selected query: `white feather`
  - old selected synset: blank
  - corrected selected query: `feather`
  - corrected synset: `oewn-89570581-n`
  - reason: `white feather` is the symbolic communication sense, while caption object counting needs the physical feather sense.

Parent enrichment:

- output:
  - `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_manual_resolved_parents.tsv`
- rows: 567
- parent_filled_rows: 514
- parent_empty_rows: 0
- parent_lookup_error_rows: 0
- selected_synset_missing_rows: 53

Canonical enrichment:

- output:
  - `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_manual_resolved_parent_canonical.tsv`
- rows: 567
- canonical_selected_rows: 514
- canonical_ambiguous_rows: 0
- canonical_lookup_error_rows: 0
- selected_synset_missing_rows: 53
- `needs_manual` precondition passed.

Stage 4 extraction:

- raw mentions:
  - `outputs/case_reports_sentence100_0101_0200_current/raw_mentions_manual_resolved.jsonl`
- raw edges:
  - `outputs/case_reports_sentence100_0101_0200_current/raw_edges_manual_resolved.jsonl`
- captions: 100
- raw mentions: 2242
- raw edges: 1224
- mention type counts:
  - object: 1169
  - attribute: 604
  - action: 432
  - quantity: 37
- edge type counts:
  - has_attribute: 604
  - event_role: 386
  - relation: 197
  - has_quantity: 37

Stage 5 canonicalization:

- canonical mentions:
  - `outputs/case_reports_sentence100_0101_0200_current/canonical_mentions_manual_resolved.jsonl`
- canonical edges:
  - `outputs/case_reports_sentence100_0101_0200_current/canonical_edges_manual_resolved.jsonl`
- canonical mention total: 2242
- canonical edge total: 1224
- canonical_source_counts:
  - gpic_observed_inventory: 1065
  - raw_fallback: 1177
- parent_filled_counts:
  - with_parent: 1065
  - without_parent: 1177

Stage 6 count export:

- output directory:
  - `outputs/case_reports_sentence100_0101_0200_current/counts_manual_resolved`
- fact_total: 21833
- fact type counts:
  - entity_exists: 1169
  - action_event: 432
  - event_role: 386
  - has_attribute: 604
  - has_quantity: 37
  - relation: 197
  - object_pair_in_caption: 19008
- table row counts:
  - object_counts.tsv: 504
  - attribute_counts.tsv: 253
  - object_attribute_pair_counts.tsv: 537
  - action_counts.tsv: 200
  - agent_patient_pair_counts.tsv: 345
  - relation_triple_counts.tsv: 182
  - object_cooccurrence_pair_counts.tsv: 16324

Note:

- `excluded` rows are not treated as `needs_manual`; Stage 4 preserves their decision metadata and still counts them according to the current policy.
- The 53 rows without selected synset are handled as no-synset rows; canonical enrichment marks them `not_applicable_no_selected_synset`.
