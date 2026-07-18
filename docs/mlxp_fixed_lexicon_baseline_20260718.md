# MLXP Fixed-Lexicon Baseline - 2026-07-18

Purpose: re-check the fixed-lexicon formal mixed GPIC Stage 1-6 pipeline on the
recreated MLXP pod, then measure the previously omitted interactive report
post-processing path.

## Environment

- MLXP pod: `prod-rsv-snu14ksh-20260718-4d7aba`
- Remote repo path: `/root/work/gpic-caption-concepts-explainable`
- Remote repo commit used by the pipeline: `8184630`
- Local runner commit containing the MLXP runtime prologue: `b24c9d0`
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Runtime: `/root/work/gpic-linux-env/bin/python`
- GPU: NVIDIA H200, `--require-gpu`
- spaCy model: `en_core_web_trf`, batch size `128`

The recreated pod required the local `scripts/run_mlxp_bash.py` runtime
prologue. The probe verified:

```text
torch_cuda=True
torch_gpu=NVIDIA H200
cupy=13.6.0
spacy_require_gpu=True
spacy_model_loaded=1
```

The remote repository was not fast-forwarded because the pod lacked
non-interactive GitHub credentials. This did not affect the benchmark path: the
needed runtime environment guard is supplied by the local runner before the
remote script runs.

## Stage 1-6 Smoke Runs

### 1K

Output:
`/root/work/gpic_baselines/runs/baseline_1k_fixedlex_smoke_20260718T074713Z`

- Captions: `1,000`
- Total pipeline: `34.874604s`
- Wrapper wall clock: `40s`
- Stage 6 facts: `195,635`
- Stage 6 integrity: `ok`

### 10K

Output:
`/root/work/gpic_baselines/runs/baseline_10k_fixedlex_current_20260718T074828Z`

- Captions: `10,000`
- Total pipeline: `217.037927s`
- Wrapper wall clock: `222s`
- Throughput: `46.074896 captions/s`
- Stage 6 facts: `1,744,077`
- Stage 6 integrity: `ok`

Selected timings:

| Stage | Seconds |
| --- | ---: |
| stage3_sentence | 46.239097 |
| stage4_extract_raw | 27.359630 |
| stage5_canonicalize | 27.509491 |
| stage6_export_counts | 107.051588 |

## 50K Stage 1-6 Baseline

Output:
`/root/work/gpic_baselines/runs/baseline_50k_fixedlex_current_20260718T075309Z`

- Captions: `50,000`
- Total pipeline: `995.529975s`
- Wrapper wall clock: `1000s`
- Throughput: `50.2245 captions/s`
- Output directory size after Stage 1-6: `9.4G`
- Stage 6 facts: `8,880,202`
- Stage 6 integrity: `ok`

Stage timings:

| Stage | Seconds |
| --- | ---: |
| stage3_sentence | 225.363023 |
| stage4_extract_raw | 137.611332 |
| stage5_canonicalize | 139.391485 |
| stage6_export_counts | 464.984527 |
| total_pipeline | 995.529975 |

Compared with the previous 50K run (`994.488594s`), this is effectively the
same speed. The recreated pod and runtime guard reproduced the earlier
baseline.

## 50K Interactive Report Post-Processing

The report path is separate from Stage 1-6 and was measured on the same 50K
output.

### Patient-Action-Agent Triple Helper

Command family:
`scripts/build_patient_action_agent_triples_from_facts.py`

- Input facts: `stage6/facts.jsonl`
- Output: `stage6/patient_action_agent_triple_counts.tsv`
- Wall clock: `29s`
- Triple rows: `30,649`

### Aggregate Report DB

Command family:
`scripts/build_interactive_count_report.py --input-mode stage6-tsv`

- Output: `interactive_report/report.db`
- Wall clock: `15s`

View row counts:

| View | Rows |
| --- | ---: |
| objects | 12,765 |
| attributes | 7,854 |
| actions | 1,795 |
| relations | 42,847 |
| object_cooccurrence | 1,225,934 |
| attribute_object_pairs | 55,439 |
| patient_action_pairs | 21,087 |
| agent_action_pairs | 19,294 |
| patient_action_agent_triples | 30,649 |
| relation_components | 967 |

### Full Caption Drill-Down Index

Command family:
`scripts/build_report_caption_index_from_facts.py`

- Input facts read: `8,880,202`
- Attempted index rows: `8,393,436`
- Final index rows: `8,305,490`
- Wall clock: `180s`
- Script elapsed: `179.347s`

Validation:

```text
has_caption_index=true
caption_mismatch_count=0
view_count=10
```

## Projection

Using the measured 50K wall-clock values as a simple linear estimate:

- Stage 1-6 only: `995.529975s * 20 = 19,910.5995s`, about `5h 31m 51s`
- Report post-processing: `(29s + 15s + 180s) * 20 = 4,480s`, about `1h 14m 40s`
- Combined Stage 1-6 plus report post-processing: about `6h 46m 31s`

This projection is a rough planning number, not a proven 1M guarantee. The
caption-index step may scale worse than linearly once SQLite index size and
filesystem writeback behavior change.

## Immediate Bottleneck Reading

Stage 6 remains the largest Stage 1-6 bottleneck: `464.984527s / 995.529975s`.
For report generation, the full caption drill-down index dominates:
`180s / 224s` of measured report post-processing.

Next optimization tests should therefore isolate:

- Stage 6 count export on NVMe scratch with copy-back to DDN
- caption-index SQLite build on NVMe scratch with copy-back to DDN
- `object_pair_in_caption` fact generation/indexing cost
