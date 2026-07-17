# MLXP Fixed-Lexicon Baseline - 2026-07-17

Purpose: measure formal mixed GPIC caption-to-concept Stage 1-6 when the
object/attribute/action inventory is already fixed. Caption index/report DB
post-processing is excluded and should be benchmarked separately.

## Environment

- MLXP pod: `prod-rsv-snu14ksh-20260717-5d6540`
- Repo commit for 50K baseline: `5ba426828029b378dfebabde2909efecc20d5c3c`
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Output storage: `/root/work/gpic_baselines/runs` on DDN/Lustre
- GPU: NVIDIA H200, `--require-gpu`
- spaCy model: `en_core_web_trf`, batch size `128`
- Python runtime: `/root/work/gpic-linux-env/bin/python`
- Runtime guard: `cupy-cuda12x==13.6.0` with NVIDIA wheel `*/lib` directories
  exported in `LD_LIBRARY_PATH`.

The CuPy guard matters: `cupy-cuda12x==14.1.1` detected the GPU but failed in
Thinc/Torch DLPack conversion, while CuPy 13.6.0 required explicit CUDA library
paths so Thinc could import `cupy.cublas`.

## 10K Smoke

Output:
`/root/work/gpic_baselines/runs/baseline_10k_fixedlex_193d0bb_20260717T160445Z`

This was a smoke run before syncing the runtime guard commit to the pod repo.
Pipeline semantics were unchanged by the later commit.

- Captions: `10,000`
- Total pipeline: `217.736217s`
- Throughput: `45.927132 captions/s`
- Stage 6 facts: `1,785,581`
- Stage 6 facts JSONL: `914,190,803 bytes`

Stage timings:

| Stage | Seconds |
| --- | ---: |
| stage1_records | 0.553931 |
| stage1_mixed_caption_rows | 0.212265 |
| stage3_model_load | 2.185454 |
| stage3_sentence | 46.373559 |
| stage3_tag_list | 1.133886 |
| stage3_combined | 3.078359 |
| stage4_lookup_load | 0.783476 |
| stage4_extract_raw | 27.459820 |
| stage5_canonicalize | 27.725727 |
| stage6_export_counts | 107.363282 |

## 50K Baseline

Output:
`/root/work/gpic_baselines/runs/baseline_50k_fixedlex_5ba4268_20260717T161814Z`

- Captions: `50,000`
- Caption shapes: `49,506 sentence`, `494 tag_list`
- Total pipeline: `994.488594s` (`16m 34.489s`)
- Wrapper wall clock: `1000s`
- Throughput: `50.277097 captions/s`
- Output directory size at completion: `9.4G`
- Stage 6 facts: `8,880,202`
- Stage 6 integrity: `ok`, deltas `{}`.
- Stage 6 facts JSONL: `4,661,543,548 bytes`

Stage timings:

| Stage | Seconds |
| --- | ---: |
| stage1_records | 2.723634 |
| stage1_mixed_caption_rows | 1.051457 |
| stage3_model_load | 2.238887 |
| stage3_sentence | 224.300023 |
| stage3_tag_list | 4.856496 |
| stage3_combined | 15.857828 |
| stage4_lookup_load | 0.775507 |
| stage4_extract_raw | 140.323181 |
| stage5_canonicalize | 139.022690 |
| stage6_export_counts | 462.470217 |
| total_pipeline | 994.488594 |

Stage 6 fact counts:

| Fact type | Count |
| --- | ---: |
| object_pair_in_caption | 6,606,544 |
| entity_exists | 516,833 |
| object_parent | 512,697 |
| attribute_exists | 286,447 |
| has_attribute | 286,315 |
| event_role | 212,100 |
| action_event | 193,414 |
| relation_component | 128,301 |
| relation | 106,865 |
| has_quantity | 14,196 |
| quantity_exists | 14,196 |
| ambiguous_relation_candidate | 2,294 |

Stage 6 count table row counts:

| Table | Rows |
| --- | ---: |
| object_cooccurrence_pair_counts.tsv | 1,225,934 |
| object_attribute_pair_counts.tsv | 55,439 |
| relation_triple_counts.tsv | 42,847 |
| agent_patient_pair_counts.tsv | 40,381 |
| object_counts.tsv | 12,765 |
| attribute_counts.tsv | 7,854 |
| object_parent_counts.tsv | 7,696 |
| object_quantity_pair_counts.tsv | 2,049 |
| action_counts.tsv | 1,795 |
| relation_component_counts.tsv | 967 |
| quantity_counts.tsv | 256 |
| ambiguous_relation_candidate_counts.tsv | 213 |

## Immediate Reading

The 50K baseline projects to roughly `5.52h` for 1M captions for Stage 1-6
only, assuming similar data distribution and no late-scale storage cliff:

`994.488594s * 20 = 19,889.77188s = 5h 31m 29.8s`

The main bottleneck is Stage 6. For 50K, Stage 6 alone took `462.47s`, and
`object_pair_in_caption` contributed `6,606,544 / 8,880,202 = 74.4%` of facts.
Stage 3 GPU parsing is the second major cost at `224.30s` for sentence rows.

Caption index/report DB generation is not included here. The earlier 1M caption
index job was a separate post-processing path and needs its own baseline after
the NVMe/DDN comparison is fixed.

## Follow-Up Benchmark Targets

- Measure Stage 6 on NVMe scratch with final copy back to DDN, using a real path
  comparison and not filename-only path labels.
- Test Stage 6 variants that reduce or defer `object_pair_in_caption` cost.
- Measure Stage 4 and Stage 5 streaming throughput separately to see whether
  JSONL parsing/writing or Python rule logic dominates.
- Keep caption index/report DB as a separate benchmark lane.
