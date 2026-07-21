# MLXP Speed Optimization Notes 2026-07-18

Purpose: measure speed-up options for the fixed-lexicon GPIC caption-to-concept
pipeline on MLXP before larger runs. This document records test conditions and
results used for decisions.

## Fixed Reference

- Environment: MLXP pod `prod-rsv-snu14ksh-20260718-4d7aba`
- Remote repo: `/root/work/gpic-caption-concepts-explainable`
- Remote repo commit during Stage 6 probes: `8184630`
- Runtime Python: `/root/work/gpic-linux-env/bin/python`
- Cgroup memory limit observed by Stage 6: `240.0 GiB`
- Stage 5 input reused for Stage 6 probes:
  - `/root/work/gpic_baselines/runs/baseline_50k_fixedlex_current_20260718T075309Z/stage5/canonical_mentions.jsonl`
  - `/root/work/gpic_baselines/runs/baseline_50k_fixedlex_current_20260718T075309Z/stage5/canonical_edges.jsonl`
- Stage 5 input filesystem evidence:
  - resolved path under `/mnt/ddn/prod-runs/snu14ksh/...`
  - `df -hT`: `lustre`, mounted at `/mnt/ddn/prod-runs/snu14ksh`
- NVMe output filesystem evidence:
  - output path under `/mnt/nvme/gpic_speed_tests/...`
  - `df -hT`: `xfs`, mounted at `/mnt/nvme`

## Baseline Already Measured

Run:

- `/root/work/gpic_baselines/runs/baseline_50k_fixedlex_current_20260718T075309Z`

Conditions:

- Input captions: 50,000 front GPIC rows
- Stage range: formal Stage 1-6 mixed pipeline
- Stage 6 backend: default `sqlite`
- Stage 6 output under the run directory on DDN/Lustre

Result:

- Stage 1-6 total: `995.529975s`
- Stage 6: `464.984527s`
- Stage 6 fact total: `8,880,202`
- Stage 6 count integrity: OK

## Experiment 1: Stage 6 Output On NVMe, SQLite Backend

Run:

- `/mnt/nvme/gpic_speed_tests/stage6_50k_nvme_20260718T111806Z`

Conditions:

- Stage range: Stage 6 only
- Input: same 50K Stage 5 canonical files as the fixed reference
- Input filesystem: DDN/Lustre
- Output filesystem: NVMe/XFS
- Count backend: `sqlite`
- SQLite cache policy: `rss_adaptive`
- Progress path: `/mnt/nvme/gpic_speed_tests/stage6_50k_nvme_20260718T111806Z/progress.json`

Result:

- Outer wall time: `457.578s`
- Stage 6 progress elapsed: `457.575s`
- Fact total: `8,880,202`
- Count integrity: OK, no deltas
- Table row counts matched the baseline shape, including:
  - `object_counts.tsv`: `12,765`
  - `attribute_counts.tsv`: `7,854`
  - `action_counts.tsv`: `1,795`
  - `relation_triple_counts.tsv`: `42,847`
  - `object_cooccurrence_pair_counts.tsv`: `1,225,934`

Interpretation:

- Moving Stage 6 output from DDN/Lustre to NVMe/XFS alone improved 50K Stage 6
  only slightly: `464.984527s -> 457.578s`.
- This does not support the claim that Stage 6 is dominated only by output
  filesystem latency at 50K.

## Experiment 2: Stage 6 Output On NVMe, Memory Backend

Run:

- `/mnt/nvme/gpic_speed_tests/stage6_50k_nvme_memory_20260718T113035Z`

Conditions:

- Stage range: Stage 6 only
- Input: same 50K Stage 5 canonical files as the fixed reference
- Input filesystem: DDN/Lustre
- Output filesystem: NVMe/XFS
- Count backend: `memory`
- Progress path: `/mnt/nvme/gpic_speed_tests/stage6_50k_nvme_memory_20260718T113035Z/progress.json`

Result:

- Outer wall time: `361.441s`
- Stage 6 progress elapsed: `360.661s`
- Fact total: `8,880,202`
- Count integrity: OK, no deltas
- Table row counts matched the sqlite run, including:
  - `object_counts.tsv`: `12,765`
  - `attribute_counts.tsv`: `7,854`
  - `action_counts.tsv`: `1,795`
  - `relation_triple_counts.tsv`: `42,847`
  - `object_cooccurrence_pair_counts.tsv`: `1,225,934`
- Observed RSS from progress polling stayed low for this 50K run:
  - `0.536 GiB` at 8K caption groups
  - `1.274 GiB` at 30K caption groups
  - `1.815 GiB` near completion

Interpretation:

- The memory backend is meaningfully faster on this 50K Stage 6 probe:
  - vs DDN sqlite baseline: `464.984527s -> 361.441s`
  - about `22.3%` faster for Stage 6
- This suggests SQLite accumulator overhead is a real part of Stage 6 cost.
- This does not yet prove memory backend is safe for 1M. It should be tested at
  a larger intermediate size with RSS progress before making it the default for
  production-scale runs.

## Experiment 3: Stage 6 Input And Output On NVMe, Memory Backend

Run:

- `/mnt/nvme/gpic_speed_tests/stage6_50k_all_nvme_memory_20260718T115009Z`

Conditions:

- Stage range: Stage 6 only
- The same 50K Stage 5 canonical files were copied from DDN/Lustre into:
  - `/mnt/nvme/gpic_speed_tests/stage6_50k_all_nvme_memory_20260718T115009Z/input_stage5/canonical_mentions.jsonl`
  - `/mnt/nvme/gpic_speed_tests/stage6_50k_all_nvme_memory_20260718T115009Z/input_stage5/canonical_edges.jsonl`
- Input filesystem during Stage 6: NVMe/XFS
- Output filesystem during Stage 6: NVMe/XFS
- Count backend: `memory`
- Copy time for the two 50K Stage 5 input files was below the one-second
  granularity of the shell timestamp used in the launch script.

Result:

- Outer wall time: `362.581s`
- Stage 6 progress elapsed: `361.859s`
- Fact total: `8,880,202`
- Count integrity: OK, no deltas
- Table row counts matched the previous Stage 6 probes.

Interpretation:

- Moving the Stage 5 input files from DDN/Lustre to NVMe did not improve the
  50K memory-backend Stage 6 result:
  - DDN input + NVMe output + memory backend: `361.441s`
  - NVMe input + NVMe output + memory backend: `362.581s`
- At 50K, Stage 6 input read location is not the observed bottleneck.
- The confirmed speed-up is from avoiding the SQLite accumulator path, not from
  moving input files to NVMe.

## Larger Artifacts Found

Existing larger Stage 5 artifacts are available on the same MLXP storage:

- `/mnt/ddn/prod-runs/snu14ksh/gpic_stage456/full_1m_20260716/stage5/canonical_mentions.jsonl`
  - size observed by `find -printf`: `14,116,106,189` bytes
- `/mnt/ddn/prod-runs/snu14ksh/gpic_stage456/smoke_limit10000/stage5/canonical_mentions.jsonl`
- `/mnt/ddn/prod-runs/snu14ksh/gpic_stage456/smoke_limit1000/stage5/canonical_mentions.jsonl`

No existing 100K/200K Stage 5 artifact was found in the searched MLXP paths.

## Remote Git Sync Status

The local branch was pushed through commit `42251ff`, but the active MLXP pod's
repo remains at commit `8184630`.

Auth-free probe from inside the pod:

```text
GIT_TERMINAL_PROMPT=0 git ls-remote origin mlxp-stage456-handoff
fatal: could not read Username for 'https://github.com': terminal prompts disabled
```

Decision:

- Do not use remote `git fetch`/`pull` in this pod for benchmark setup.
- The Stage 6-only probes above did not require the new mixed runner option
  because they called the existing Stage 6 function through the incident gate.
- A formal mixed Stage 1-6 run with `--stage6-count-backend memory` requires a
  code transfer path other than remote Git sync, or a fresh clone/session with
  working GitHub access.

## Code/Process Adjustments Made During This Probe

- Exposed `--progress` on standalone Stage 4, Stage 5, and Stage 6 wrappers so
  long formal stage probes can write progress JSON.
- Added a formal-stage contract test that all standalone Stage 4/5/6 wrappers
  expose progress and pass `progress_path`.
- Exposed `--stage6-count-backend` and `--stage6-sqlite-cache-rows` on
  `scripts/run_mixed_caption_pipeline.py`; default remains `sqlite`.
- Added mixed runner validation for invalid Stage 6 backend values.
- Updated `AGENTS.md`: a remote PID with `STAT` containing `Z` or `<defunct>`
  is a zombie and must not be reported as active work.

Verification:

- `.\scripts\run_tests.ps1 discover -s tests -p "test_formal_stage_memory_safety.py"`: OK, 6 tests
- `.\scripts\run_tests.ps1 discover -s tests -p "test_mixed_caption_pipeline.py"`: OK, 11 tests
- `.\scripts\run_python.ps1 -m compileall scripts src`: OK

## Next Candidate Tests

1. For a larger safety check, either create a bounded intermediate Stage 5
   artifact or run the existing 1M Stage 5 artifact with memory backend while
   monitoring RSS.
2. If RSS remains safely below the pod cgroup limit, run one formal mixed
   Stage 1-6 benchmark with `--stage6-count-backend memory` after the MLXP code
   path has commit `42251ff` or newer.
3. Keep report caption-index timing separate from Stage 1-6 timing, because it
   is a post-processing step for the interactive HTML report.

## Experiment 4: 1M Stage 6 Output On NVMe, Memory Backend

Run:

- `/mnt/nvme/gpic_speed_tests/stage6_1m_nvme_memory_20260718T132159Z`

Conditions:

- Stage range: Stage 6 only
- Input: existing 1M Stage 5 canonical files:
  - `/mnt/ddn/prod-runs/snu14ksh/gpic_stage456/full_1m_20260716/stage5/canonical_mentions.jsonl`
  - `/mnt/ddn/prod-runs/snu14ksh/gpic_stage456/full_1m_20260716/stage5/canonical_edges.jsonl`
- Input filesystem: DDN/Lustre
- Output filesystem: NVMe/XFS
- Count backend: `memory`
- Cgroup memory limit: `240 GiB`
- Effective Stage 6 RSS safety limit: `180 GiB`
- Repo commit on MLXP: `325ab93`

Result:

- Stage 6 progress elapsed: `7,128.213s` (`1h 58m 48s`)
- Fact total: `178,529,467`
- Count integrity: OK, no deltas
- Final progress RSS: `11.991 GiB`
- Highest observed poll RSS from `ps`: about `17.4 GiB` during final table
  writing; this stayed far below the `180 GiB` safety limit.
- `facts.jsonl` size: `94,005,624,899` bytes

Final fact type counts:

- `object_pair_in_caption`: `132,986,020`
- `entity_exists`: `10,352,739`
- `object_parent`: `10,270,122`
- `attribute_exists`: `5,739,552`
- `has_attribute`: `5,737,095`
- `event_role`: `4,245,559`
- `action_event`: `3,878,681`
- `relation_component`: `2,569,111`
- `relation`: `2,138,690`
- `has_quantity`: `283,146`
- `quantity_exists`: `283,146`
- `ambiguous_relation_candidate`: `45,606`

Final table row counts:

- `object_counts.tsv`: `112,119`
- `attribute_counts.tsv`: `36,784`
- `action_counts.tsv`: `5,444`
- `relation_triple_counts.tsv`: `381,395`
- `relation_component_counts.tsv`: `2,436`
- `object_cooccurrence_pair_counts.tsv`: `7,978,858`
- `object_attribute_pair_counts.tsv`: `319,282`
- `agent_patient_pair_counts.tsv`: `231,699`

Interpretation:

- The 1M memory-backend Stage 6 run completed successfully within the MLXP pod
  cgroup limit and did not show the earlier SQLite/large-index slowdown around
  the `139M` fact region.
- The memory backend is viable for 1M Stage 6 on this pod for the current count
  table cardinalities.
- The current Stage 6 bottleneck is still single-core Python streaming and fact
  generation/write, not memory pressure.

Incidents and guards during this run:

- The first relaunch failed before processing because `--progress` was
  registered twice. Fixed by making `add_memory_safety_args()` the single owner
  of the CLI option and by testing parser construction.
- The second relaunch failed before processing because `progress_path` was
  passed twice. Fixed by making `memory_safety_kwargs(args)` the single owner of
  `progress_path` conversion and by rejecting direct `progress_path=` in the
  formal Stage 4/5/6 wrappers.
- Both local and MLXP incidents were cleared only after targeted memory-safety
  tests passed.

Verification:

- Local `.\scripts\run_tests.ps1 discover -s tests -p "test_formal_stage_memory_safety.py"`:
  OK, 7 tests
- MLXP `PYTHONPATH=src /root/work/gpic-linux-env/bin/python -m unittest discover -s tests -p test_formal_stage_memory_safety.py`:
  OK, 7 tests
- MLXP Stage 6 summary `count_integrity.status`: `ok`

Next candidate tests:

1. Run a formal Stage 1-6 baseline using the existing 1M lexicon with
   `--stage6-count-backend memory`; keep caption-index/report generation outside
   the baseline timing.
2. If Stage 1-5 dominates, profile spaCy/lookup/canonical stages separately
   before changing Stage 6 further.
3. If Stage 6 remains worth optimizing, test parallel fact generation by caption
   shard with deterministic merge of count tables.

## Experiment 5: 50K Formal Stage 1-6 On NVMe, Memory Backend

Run:

- `/mnt/nvme/gpic_speed_tests/full50k_fixedlex_memory_20260718T160412Z`

Conditions:

- Stage range: formal mixed Stage 1-6
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `50,000` front GPIC-Nano rows
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition MWE lexicon: `resources/lexicons/preposition_mwes.tsv`
- GPU mode: `--require-gpu`
- spaCy batch size: `128`
- Output filesystem: NVMe/XFS
- Stage 6 count backend: `memory`
- Progress output: `progress.json`

Result:

- Total pipeline: `885.873699s`
- Throughput: `56.441454 captions/s`
- Stage 6: `362.072664s`
- Stage 6 fact total: `8,880,202`
- Stage 6 integrity: OK
- Stage 6 final RSS in progress: `3.634 GiB`

Stage timings:

| Stage | Seconds |
| --- | ---: |
| stage1_records | 2.719689 |
| stage1_mixed_caption_rows | 1.032841 |
| stage3_model_load | 2.639990 |
| stage3_sentence | 225.217261 |
| stage3_tag_list | 4.884540 |
| stage3_combined | 15.680831 |
| stage4_lookup_load | 0.829507 |
| stage4_extract_raw | 138.379483 |
| stage5_canonicalize | 131.560715 |
| stage6_export_counts | 362.072664 |
| total_pipeline | 885.873699 |

Comparison with the 50K fixed reference
`/root/work/gpic_baselines/runs/baseline_50k_fixedlex_current_20260718T075309Z`:

| Metric | Reference | NVMe + memory | Delta |
| --- | ---: | ---: | ---: |
| total_pipeline | 995.529975 | 885.873699 | -109.656276 |
| stage6_export_counts | 464.984527 | 362.072664 | -102.911863 |
| fact_total | 8,880,202 | 8,880,202 | 0 |

Validation:

- `fact_type_counts_equal`: true
- `table_row_count_equal`: true
- old/new count integrity: `ok` / `ok`

Interpretation:

- On the same 50K caption set, Stage 6 memory backend plus NVMe output is
  result-preserving and reduces total Stage 1-6 wall time by about `11.0%`.
- The measured total speed-up is mostly Stage 6: `102.9s` of the `109.7s`
  total improvement came from `stage6_export_counts`.
- Stage 3, Stage 4, and Stage 5 stayed close to the previous fixed-lexicon
  baseline, so the next optimization target should be Stage 4/5 processing or
  Stage 3 batching/parallelism rather than more Stage 6 storage changes.

## Experiment 6: 50K Formal Stage 1-6 With Stage 6 Facts Discarded

Run:

- `/mnt/nvme/gpic_speed_tests/full50k_fixedlex_memory_discard_20260719T094840Z`

Conditions:

- Same input, inventory bundle, preposition MWE lexicon, model, GPU mode, limit,
  and NVMe output filesystem as Experiment 5.
- Stage 6 count backend: `memory`
- Stage 6 facts output mode: `discard`
- `facts.jsonl` intentionally not written; count tables and Stage 6 integrity
  are still produced.

Result:

- Total pipeline: `647.8655s`
- Throughput: `77.176513 captions/s`
- Stage 6: `123.052012s`
- Stage 6 fact total: `8,880,202`
- Stage 6 integrity: OK
- `stage6/facts.jsonl`: absent as expected

Stage timings:

| Stage | Seconds |
| --- | ---: |
| stage1_records | 2.766426 |
| stage1_mixed_caption_rows | 1.039375 |
| stage3_model_load | 2.678540 |
| stage3_sentence | 224.935582 |
| stage3_tag_list | 4.907504 |
| stage3_combined | 15.494165 |
| stage4_lookup_load | 0.810275 |
| stage4_extract_raw | 138.931818 |
| stage5_canonicalize | 132.409393 |
| stage6_export_counts | 123.052012 |
| total_pipeline | 647.865500 |

Comparison with Experiment 5:

| Metric | Write facts | Discard facts | Delta |
| --- | ---: | ---: | ---: |
| total_pipeline | 885.873699 | 647.865500 | -238.008199 |
| stage6_export_counts | 362.072664 | 123.052012 | -239.020652 |
| fact_total | 8,880,202 | 8,880,202 | 0 |

Validation:

- `fact_total_equal`: true
- `fact_type_counts_equal`: true
- `table_row_counts_equal`: true
- discard count integrity: `ok`

Interpretation:

- Writing `facts.jsonl` accounts for about `239s` of the 50K run. When the
  workflow only needs count tables, `--stage6-facts-output-mode discard` is
  result-preserving for aggregates and gives a much larger win than the sqlite
  to memory count-backend change alone.
- At this point the 50K fixed-lexicon pipeline is dominated by Stage 3 parsing
  plus Stage 4/5 extraction/canonicalization, not by Stage 6 count aggregation.

## Experiment 7: Shallow JSON Record Serialization

Profile:

- `/mnt/nvme/gpic_speed_tests/stage45_profile_20260719T105352Z`

The Stage 4/5 cProfile run showed that a large share of time was spent in
`JsonRecord.to_dict() -> dataclasses.asdict()`, especially while writing JSONL
records. `asdict()` recursively deep-copies nested dict/list fields for every
record, but the pipeline only needs a JSON-serializable mapping for immediate
`json.dumps()`.

Change:

- `JsonRecord.to_dict()` now uses cached dataclass field names and returns a
  shallow `{field: value}` dict.
- Existing validation still happens in dataclass `__post_init__`.
- Tests assert shallow `to_dict()` is value-equal to `dataclasses.asdict()` for
  raw and canonical records.

Run:

- `/mnt/nvme/gpic_speed_tests/full50k_fixedlex_memory_discard_20260719T111739Z`

Conditions:

- Same as Experiment 6: fixed current inventory, NVMe output, memory Stage 6
  backend, and `--stage6-facts-output-mode discard`.

Result:

- Total pipeline: `526.698593s`
- Stage 4: `86.789123s`
- Stage 5: `102.331004s`
- Stage 6: `123.082176s`

Comparison with Experiment 6:

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| stage3_sentence | 224.935582 | 187.264461 | -37.671121 |
| stage4_extract_raw | 138.931818 | 86.789123 | -52.142695 |
| stage5_canonicalize | 132.409393 | 102.331004 | -30.078389 |
| stage6_export_counts | 123.052012 | 123.082176 | +0.030164 |
| total_pipeline | 647.865500 | 526.698593 | -121.166907 |

Validation:

- `fact_total_equal`: true
- `fact_type_counts_equal`: true
- `table_row_counts_equal`: true

Interpretation:

- The code change directly targets Stage 4/5 JSONL serialization and produced a
  Stage 4/5 combined improvement of about `82.2s` on 50K captions.
- The Stage 3 improvement in this run is likely runtime variance rather than a
  result of the schema change.
- After this change, the largest remaining controllable costs are Stage 3
  parsing and Stage 6 aggregate counting; Stage 4/5 are still meaningful but no
  longer dominated by `dataclasses.asdict()`.

## Experiment 8: Throttled Runtime Memory Checks

Profile source:

- `/mnt/nvme/gpic_speed_tests/stage45_profile_20260719T105352Z`

The same cProfile run showed another avoidable Stage 5 cost:
`ProgressWriter.check_memory()` called `/proc/self/status` through
`current_rss_kib()` for every raw mention and edge. That preserves the memory
safety guard, but it turns RSS polling into a hot loop.

Change:

- `MemorySafetyConfig` now has
  `memory_check_min_interval_seconds = 1.0`.
- `ProgressWriter.check_memory()` keeps the last check timestamp and skips RSS
  reads until the interval expires, unless `force=True` is passed.
- The safety limit and progress JSON memory reporting remain in the shared
  Stage 4/5/6 path.
- Tests cover the throttle behavior and progress JSON metadata.

Run:

- `/mnt/nvme/gpic_speed_tests/full50k_fixedlex_memory_discard_20260719T114948Z`

Conditions:

- Same as Experiment 7: fixed current inventory, NVMe output, memory Stage 6
  backend, and `--stage6-facts-output-mode discard`.

Result:

- Total pipeline: `462.962737s`
- Throughput: `108.000053 captions/s`
- Stage 4: `83.026928s`
- Stage 5: `46.615288s`
- Stage 6: `119.219013s`

Comparison with Experiment 7:

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| stage3_sentence | 187.264461 | 186.927990 | -0.336471 |
| stage4_extract_raw | 86.789123 | 83.026928 | -3.762195 |
| stage5_canonicalize | 102.331004 | 46.615288 | -55.715716 |
| stage6_export_counts | 123.082176 | 119.219013 | -3.863163 |
| total_pipeline | 526.698593 | 462.962737 | -63.735856 |

Validation:

- `fact_total_equal`: true
- `fact_type_counts_equal`: true
- `table_row_counts_equal`: true
- Stage 6 count integrity: `ok`
- `facts.jsonl` absent as expected in discard mode

Interpretation:

- The Stage 5 RSS polling bottleneck was real. Throttling memory checks in the
  shared `ProgressWriter` path preserves the guard while avoiding millions of
  `/proc` reads.
- Stage 3 is now the dominant fixed-lexicon cost on 50K, followed by Stage 6
  aggregate counting. Stage 4/5 combined dropped to about `129.6s`.

## Experiment 9: Stage 3 Batch-Size Sweep

Run:

- `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z`

Conditions:

- 50K GPIC-Nano front captions
- fixed current inventory
- `en_core_web_trf`
- H200 GPU required
- NVMe output
- Stage 6 memory backend
- `--stage6-facts-output-mode discard`
- batch sizes: `64`, `128`, `192`, `256`, `384`

Results:

| Batch Size | Stage 3 Sentence | Stage 4 | Stage 5 | Stage 6 | Total | Captions/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 189.237124 | 83.220668 | 44.448193 | 117.395992 | 460.864573 | 108.491741 |
| 128 | 187.439617 | 83.217839 | 46.461620 | 118.294628 | 462.479729 | 108.112847 |
| 192 | 184.815487 | 82.775271 | 46.629832 | 117.796177 | 458.738115 | 108.994649 |
| 256 | 186.967902 | 82.970629 | 44.891659 | 118.615852 | 460.135270 | 108.663698 |
| 384 | 187.210622 | 83.309055 | 45.258308 | 118.907498 | 461.652055 | 108.306677 |

Validation:

- All five batch sizes completed with return code `0`.
- All five runs had Stage 6 count integrity `ok`.
- All five runs produced identical Stage 6 `fact_total`: `8,880,202`.
- All five runs produced identical Stage 6 table row counts.

Interpretation:

- Batch size `192` was the fastest in this 50K sweep, but the difference is
  small: about `2.1s` faster than batch `64` and about `3.7s` faster than batch
  `128`.
- Larger batch sizes did not produce a meaningful speedup on this pipeline.
  Stage 3 sentence time varies only within roughly `4.4s` across the tested
  range.
- Use batch `192` as the current best candidate for the next larger
  fixed-lexicon validation, but do not expect a dramatic 1M gain from batch
  size alone.

## Experiment 10: CPU Sharded Stage 4-6

Run:

- `/mnt/nvme/gpic_speed_tests/stage456_sharded_cpu_50k_20260719T141523Z`

Baseline compared against:

- `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z/batch_192`

Conditions:

- MLXP pod: `prod-rsv-snu14ksh-20260718-4d7aba`
- Remote repo commit: `0c579f2e9e705f84b058cbff074f60ee0b147c9b`
- Stage 3 input reused from baseline:
  `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z/batch_192/stage3/stage3_records.jsonl`
- Input count: `50,000` Stage 3 records
- Shards/jobs: `4` caption-disjoint shards, `4` worker processes
- Stage range: Stage 4, Stage 5, Stage 6 only
- Stage 6 backend: per-shard `memory`
- Stage 6 fact rows: `--stage6-facts-output-mode discard`
- Output filesystem: `/mnt/nvme`

Result:

- Sharded runner total: `124.998811s`
- Slowest shard total: `69.141125s`
- Sum of shard worker times: `271.233594s`
- Merged Stage 6 `fact_total`: `8,880,202`
- Merged Stage 6 count integrity: `ok`
- Baseline Stage 4 + Stage 5 + Stage 6: `82.775271 + 46.629832 + 117.796177 = 247.201280s`

Validation:

- Stage 3 split produced `50,000` records and `50,000` unique caption IDs.
- Each shard had `12,500` Stage 3 records.
- The merged Stage 6 TSV output matched the baseline Stage 6 directory exactly:
  `mismatch_count=0` across all 12 count TSV files.
- Local tests:
  `.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p "test_stage456_sharded.py"`
  ran 4 tests OK.

Interpretation:

- CPU sharding Stage 4-6 produced about a `1.98x` speedup for the post-Stage-3
  segment on this 50K run.
- End-to-end 50K speed would still include Stage 1/3 cost. Using the batch-192
  Stage 3 timing, a comparable sharded end-to-end estimate is roughly
  `184.815487 + 124.998811s` plus Stage 1/combine overhead, around `310s`
  before further Stage 3 parallelization.
- The next CPU optimization target is to integrate this Stage 4-6 sharded path
  into the fixed-lexicon full runner so Stage 1/3 output can feed it without
  manual path handoff.

## Experiment 11: Mixed Runner With CPU-Sharded Stage 4-6

Run:

- `/mnt/nvme/gpic_speed_tests/mixed_stage456_sharded_50k_20260719T143051Z`

Baseline compared against:

- `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z/batch_192`

Conditions:

- MLXP pod: `prod-rsv-snu14ksh-20260718-4d7aba`
- Stage range: formal mixed Stage 1-6
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `50,000` front GPIC-Nano rows
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition MWE lexicon: `resources/lexicons/preposition_mwes.tsv`
- GPU mode: `--require-gpu`
- spaCy batch size: `192`
- Stage 4-6 CPU shards/jobs: `4/4`
- Stage 6 backend: per-shard `memory`
- Stage 6 fact rows: `--stage6-facts-output-mode discard`
- Output filesystem: `/mnt/nvme`

Result:

- Total pipeline: `338.827369s`
- Throughput: `147.567772 captions/s`
- Stage 3 sentence: `186.988684s`
- Sharded Stage 4-6 wrapper: `125.067940s`
- Sharded Stage 4-6 internal total: `123.913601s`
- Slowest Stage 4-6 shard: `68.705798s`
- Sum of Stage 4-6 shard worker times: `271.697425s`
- Stage 6 `fact_total`: `8,880,202`
- Stage 6 count integrity: `ok`

Validation:

- The mixed runner now accepts `--stage456-shards` and invokes the sharded
  Stage 4-6 path directly after Stage 3 combined output.
- The final merged count TSVs are exposed under the standard `stage6/`
  directory, while shard internals remain under `stage456_sharded/`.
- The final `stage6/*.tsv` output matched the batch-192 baseline exactly:
  `mismatch_count=0` across all 12 count TSV files.
- Local tests:
  - `.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p "test_stage456_sharded.py"` ran 4 tests OK.
  - `.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p "test_mixed_caption_pipeline.py"` ran 15 tests OK.

Interpretation:

- Integrating CPU-sharded Stage 4-6 into the mixed runner is result-preserving
  for the 50K fixed-lexicon test.
- Compared with the best previous 50K batch sweep run (`458.738115s`),
  end-to-end time improved by about `119.91s`, roughly `1.35x` faster.
- The remaining dominant cost is Stage 3 sentence annotation (`186.99s`), so
  further CPU/GPU work should target Stage 3 parallelization or multi-process
  caption annotation next.

## Experiment 12: CPU Shard/Job Sweep For Stage 4-6

Run:

- `/mnt/nvme/gpic_speed_tests/stage456_cpu_shard_sweep_50k_20260719T144041Z`

Baseline compared against:

- `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z/batch_192`

Conditions:

- MLXP pod: `prod-rsv-snu14ksh-20260718-4d7aba`
- cgroup CPU quota: `1400000 100000`, i.e. 14 CPU cores
- cgroup memory max: `257698037760` bytes, about 240 GiB
- Stage 3 input reused from baseline:
  `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z/batch_192/stage3/stage3_records.jsonl`
- Stage range: Stage 4, Stage 5, Stage 6 only
- Stage 6 backend: per-shard `memory`
- Stage 6 fact rows: `--stage6-facts-output-mode discard`
- Each run byte-compared merged `stage6/*.tsv` against the batch-192 baseline.

Results:

| Jobs/Shards | Total | Slowest Shard | Sum Worker Time | Fact Total | Mismatches |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 186.327454 | 136.832836 | 266.370805 | 8,880,202 | 0 |
| 4 | 123.114464 | 68.652667 | 270.664526 | 8,880,202 | 0 |
| 8 | 98.512237 | 37.144097 | 289.439153 | 8,880,202 | 0 |
| 12 | 92.775303 | 26.411900 | 304.797518 | 8,880,202 | 0 |
| 14 | 91.816271 | 24.327859 | 324.216240 | 8,880,202 | 0 |

Interpretation:

- Best observed CPU setting for Stage 4-6 on this pod is `14` shards/jobs,
  matching the CPU quota.
- Gains taper after 8 jobs, but 14 jobs still wins by about `6.70s` over
  8 jobs and about `31.30s` over 4 jobs.
- All configurations were result-preserving against the baseline count TSVs.

## Experiment 13: Mixed Runner With 14-Way CPU-Sharded Stage 4-6

Run:

- `/mnt/nvme/gpic_speed_tests/mixed_stage456_sharded14_50k_20260719T145219Z`

Baseline compared against:

- `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z/batch_192`

Conditions:

- Stage range: formal mixed Stage 1-6
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `50,000` front GPIC-Nano rows
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition MWE lexicon: `resources/lexicons/preposition_mwes.tsv`
- GPU mode: `--require-gpu`
- spaCy batch size: `192`
- Stage 4-6 CPU shards/jobs: `14/14`
- Stage 6 backend: per-shard `memory`
- Stage 6 fact rows: `--stage6-facts-output-mode discard`
- Output filesystem: `/mnt/nvme`

Result:

- Total pipeline: `309.331014s`
- Throughput: `161.639143 captions/s`
- Stage 3 sentence: `185.901162s`
- Sharded Stage 4-6 wrapper: `97.264105s`
- Sharded Stage 4-6 internal total: `96.144590s`
- Slowest Stage 4-6 shard: `24.455131s`
- Sum of Stage 4-6 shard worker times: `328.570107s`
- Stage 6 `fact_total`: `8,880,202`
- Stage 6 count integrity: `ok`

Validation:

- Final `stage6/*.tsv` output matched the batch-192 baseline exactly:
  `mismatch_count=0` across all 12 count TSV files.
- The standard mixed output still exposes final counts under `stage6/`.

Interpretation:

- Compared with the previous best fixed-lexicon 50K batch sweep run
  (`458.738115s`), 14-way CPU-sharded Stage 4-6 reduces end-to-end time by
  `149.407101s`, about `1.48x` faster.
- Stage 3 now dominates the run. On this 50K profile, Stage 3 sentence
  annotation alone is about `60.1%` of total runtime.

## Experiment 14: Two-GPU Sharded Stage 3 Plus 14-Way Stage 4-6

Run:

- `/mnt/nvme/gpic_speed_tests/stage3_2gpu_stage456_50k_20260719T152415Z`

Baseline compared against:

- `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z/batch_192`

Conditions:

- MLXP pod: `prod-rsv-snu14ksh-20260720-72ec33`
- cgroup CPU quota: `2800000 100000`, i.e. 28 CPU cores
- cgroup memory max: `515396075520` bytes, about 480 GiB
- GPU hardware: two NVIDIA H200 GPUs
- Observed `nvidia-smi` at run start:
  - GPU 0: NVIDIA H200, driver `580.126.16`, pstate `P0`, power draw
    `76.39 W`, power limit `700.00 W`, memory used `0 MiB`,
    memory total `143771 MiB`
  - GPU 1: NVIDIA H200, driver `580.126.16`, pstate `P0`, power draw
    `81.11 W`, power limit `700.00 W`, memory used `0 MiB`,
    memory total `143771 MiB`
- Stage 1 input reused from baseline:
  `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z/batch_192/stage1/`
- Stage 3 model: `en_core_web_trf`
- spaCy batch size: `192`
- Stage 3 sentence shards/jobs: `2/2`
- Stage 3 GPU devices: `0,1`
- Stage 3 tag-list shards/jobs: `1/2` effective non-empty jobs
- Stage 4-6 CPU shards/jobs: `14/14`
- Stage 6 backend: per-shard `memory`
- Stage 6 fact rows: `--stage6-facts-output-mode discard`
- Inventory paths for Stage 4-6 were resolved from
  `resources/gpic_inventory/current/inventory_bundle.json`, not hardcoded TSV
  names.
- Output filesystem: `/mnt/nvme`

Result:

- Stage 3 sharded runner total: `128.620914s`
- Stage 3 wall-clock around the command: `133s`
- Sentence shard 0: `24,753` rows on GPU `0`, `101.404927s`,
  `gpu_enabled=true`
- Sentence shard 1: `24,753` rows on GPU `1`, `102.721552s`,
  `gpu_enabled=true`
- Tag-list shard: `494` rows on GPU `0`, `11.357271s`, `gpu_enabled=true`
- Stage 4-6 sharded runner total: `100.847686s`
- Stage 4-6 wall-clock around the command: `106s`
- Slowest Stage 4-6 shard: `25.152960s`
- Sum of Stage 4-6 shard worker times: `330.673927s`
- Stage 6 `fact_total`: `8,880,202`
- Stage 6 count integrity: `ok`

Validation:

- Stage 3 merged output matched the baseline Stage 3 file byte-for-byte:
  `byte_equal=true`, `50,000` expected rows and `50,000` actual rows.
- Merged Stage 6 TSV output matched the baseline Stage 6 directory exactly:
  `mismatch_count=0` across all 12 count TSV files.
- Local tests after adding the runner:
  - `.\scripts\run_python.ps1 -c "ast.parse(...)"`: `AST_OK`
  - `.\scripts\run_tests.ps1 discover -s tests -p test_stage3_sharded.py --timeout-seconds 120`:
    5 tests OK.
- Remote tests before the benchmark:
  - AST check for `run_stage3_sharded.py`, `run_stage456_sharded.py`, and
    `run_mixed_caption_pipeline.py`: `AST_OK`
  - `python -m unittest discover -s tests -p test_stage3_sharded.py`:
    5 tests OK.

Interpretation:

- Compared with the previous best fixed-lexicon 50K batch sweep run
  (`458.738115s`), this staged 2-GPU Stage 3 plus 14-way Stage 4-6 path takes
  about `229.47s` for Stage 3+4+5+6 after reusing baseline Stage 1 rows.
- A directly comparable full mixed-run number still needs integration into
  `run_mixed_caption_pipeline.py`, because this experiment reused baseline
  Stage 1 files instead of rerunning Stage 1 inside one command.
- Stage 3 sentence annotation was reduced from about `185.9s` in Experiment 13
  to a sharded Stage 3 total of `128.6s`, while preserving Stage 3 output
  exactly.
- The next optimization step is to integrate this Stage 3 sharded runner into
  the formal mixed runner, then run a single-command 50K Stage 1-6 comparison
  with the same Stage 6 exact-TSV validation.

## Experiment 15: Mixed Runner With Two-GPU Stage 3 And 14-Way Stage 4-6

Run:

- `/mnt/nvme/gpic_speed_tests/mixed_stage3_2gpu_stage45614_50k_20260719T154624Z`

Baseline compared against:

- `/mnt/nvme/gpic_speed_tests/batch_sweep_50k_20260719T121636Z/batch_192`

Conditions:

- MLXP pod: `prod-rsv-snu14ksh-20260720-72ec33`
- cgroup CPU quota: `2800000 100000`, i.e. 28 CPU cores
- cgroup memory max: `515396075520` bytes, about 480 GiB
- GPU hardware: two NVIDIA H200 GPUs
- Observed `nvidia-smi` at run start:
  - GPU 0: NVIDIA H200, driver `580.126.16`, pstate `P0`, power draw
    `76.41 W`, power limit `700.00 W`, memory used `0 MiB`,
    memory total `143771 MiB`
  - GPU 1: NVIDIA H200, driver `580.126.16`, pstate `P0`, power draw
    `80.27 W`, power limit `700.00 W`, memory used `0 MiB`,
    memory total `143771 MiB`
- Stage range: formal mixed Stage 1-6 in one `run_mixed_caption_pipeline.py`
  command
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `50,000` front GPIC-Nano rows
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition MWE lexicon: `resources/lexicons/preposition_mwes.tsv`
- GPU mode: `--require-gpu`
- spaCy batch size: `192`
- Stage 3 sentence shards/jobs: `2/2`
- Stage 3 tag-list shards: `1`
- Stage 3 GPU devices: `0,1`
- Stage 4-6 CPU shards/jobs: `14/14`
- Stage 6 backend: per-shard `memory`
- Stage 6 fact rows: `--stage6-facts-output-mode discard`
- Output filesystem: `/mnt/nvme`

Result:

- Total pipeline: `220.993083s`
- Throughput: `226.251425 captions/s`
- Stage 1 records: `1.713743s`
- Stage 1 mixed caption rows: `1.026964s`
- Sharded Stage 3 wrapper: `126.161664s`
- Sharded Stage 3 internal total: `125.875615s`
- Sharded Stage 3 slowest worker: `99.499632s`
- Sharded Stage 4-6 wrapper: `91.293184s`
- Sharded Stage 4-6 internal total: `90.197526s`
- Sharded Stage 4-6 slowest worker: `23.038390s`
- Stage 6 `fact_total`: `8,880,202`
- Stage 6 count integrity: `ok`

Validation:

- The mixed runner now accepts `--stage3-sentence-shards`,
  `--stage3-tag-shards`, `--stage3-jobs`, and `--stage3-gpu-devices`.
- Sharded Stage 3 writes the same standard mixed-run files under `stage3/`:
  `sentence_stage3_records.jsonl`, `tag_list_stage3_records.jsonl`, and
  `stage3_records.jsonl`.
- Stage 3 merged output matched the baseline Stage 3 file byte-for-byte:
  `stage3_byte_equal=true`, `50,000` expected rows and `50,000` actual rows.
- Final `stage6/*.tsv` output matched the batch-192 baseline exactly:
  `stage6_mismatch_count=0` across all 12 count TSV files.
- Local validation:
  - `.\scripts\run_python.ps1 -c "ast.parse(...)"`: `AST_OK`
  - `.\scripts\run_tests.ps1 discover -s tests -p test_mixed_caption_pipeline.py --timeout-seconds 120`:
    18 tests OK.
  - `.\scripts\run_tests.ps1 discover -s tests -p test_stage3_sharded.py --timeout-seconds 120`:
    5 tests OK.
- Remote validation before the benchmark:
  - AST check for `run_stage3_sharded.py`, `run_stage456_sharded.py`, and
    `run_mixed_caption_pipeline.py`: `AST_OK`
  - `python -m unittest discover -s tests -p test_stage3_sharded.py`:
    5 tests OK.
  - `python -m unittest discover -s tests -p test_mixed_caption_pipeline.py`:
    18 tests OK.

Interpretation:

- This is the first directly comparable single-command fixed-lexicon 50K
  Stage 1-6 benchmark with both Stage 3 GPU sharding and Stage 4-6 CPU
  sharding.
- Compared with the previous best fixed-lexicon batch sweep run
  (`458.738115s`), total time improved by `237.745032s`, about `2.08x`
  faster.
- Compared with Experiment 13's 14-way Stage 4-6 mixed run (`309.331014s`),
  the two-GPU Stage 3 integration saved `88.337931s` end to end.
- At 50K, the remaining largest component is still Stage 3 (`126.16s`), but
  Stage 4-6 has been reduced to about `91.29s` with exact count preservation.

## Experiment 16: 1M Mixed Runner With Two-GPU Stage 3 And 14-Way Stage 4-6

Run:

- `/mnt/nvme/gpic_speed_tests/mixed_stage3_2gpu_stage45614_1m_20260719T160244Z`

Conditions:

- MLXP pod: `prod-rsv-snu14ksh-20260720-72ec33`
- cgroup CPU quota: `2800000 100000`, i.e. 28 CPU cores
- cgroup memory max: `515396075520` bytes, about 480 GiB
- GPU hardware: two NVIDIA H200 GPUs
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `1,000,000` front GPIC-Nano rows
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition MWE lexicon: `resources/lexicons/preposition_mwes.tsv`
- GPU mode: `--require-gpu`
- spaCy batch size: `192`
- Stage 3 sentence shards/jobs: `2/2`
- Stage 3 tag-list shards: `1`
- Stage 3 GPU devices: `0,1`
- Stage 4-6 CPU shards/jobs: `14/14`
- Stage 6 backend: per-shard `memory`
- Stage 6 fact rows: `--stage6-facts-output-mode discard`
- Output filesystem: `/mnt/nvme`

Result:

- Total pipeline: `3449.240277s`, about `57m 29s`
- Throughput: `289.918915 captions/s`
- Stage 1 records: `38.991211s`
- Stage 1 mixed caption rows: `23.585378s`
- Sharded Stage 3 wrapper: `2335.015571s`
- Sharded Stage 3 internal total: `2328.476027s`
- Sharded Stage 3 slowest worker: `1868.245134s`
- Sharded Stage 4-6 wrapper: `1050.865381s`
- Sharded Stage 4-6 internal total: `1049.109395s`
- Sharded Stage 4-6 slowest worker: `396.294402s`
- Stage 6 `fact_total`: `178,529,467`
- Stage 6 count integrity: `ok`

Stage 6 output row counts:

- `object_counts.tsv`: `112,119`
- `attribute_counts.tsv`: `36,784`
- `action_counts.tsv`: `5,444`
- `relation_triple_counts.tsv`: `381,395`
- `relation_component_counts.tsv`: `2,436`
- `object_cooccurrence_pair_counts.tsv`: `7,978,858`
- `object_attribute_pair_counts.tsv`: `319,282`
- `agent_patient_pair_counts.tsv`: `231,699`
- `ambiguous_relation_candidate_counts.tsv`: `730`
- `object_parent_counts.tsv`: `19,802`
- `object_quantity_pair_counts.tsv`: `12,744`
- `quantity_counts.tsv`: `2,097`

Validation and monitoring notes:

- The run completed with `stage6_count_integrity=ok`.
- `mixed_runner_stderr.log` was empty in the final probe.
- Stage 3 sentence shards completed at `494,999` rows each; the tag-list shard
  completed at `10,002` rows, totaling `1,000,000` rows.
- Stage 4 completed on all 14 shards before Stage 5 began on each shard.
- Stage 5 completed on all 14 shards before Stage 6 completion on each shard.
- During the final Stage 6 count merge, Python RSS was observed around
  `30,406,952 KiB`, far below the 480 GiB cgroup memory limit.
- A monitoring bug was found in the initial compact probe: it looked for
  `progress_shard_*.json`, while Stage 3 shard progress files are written under
  `stage3_sharded/shard_progress/*.json`. The compact probe was corrected.
- The pod launch status JSON originally stayed at `status=launched` even after
  completion. The completed run was reconciled from `compact_summary.json`, and
  the local launcher was updated so future runs write terminal status metadata.

Interpretation:

- This is the first directly measured 1M fixed-lexicon Stage 1-6 run with both
  two-GPU Stage 3 sharding and 14-way Stage 4-6 CPU sharding.
- The original 50K fixed-lexicon baseline in
  `docs/mlxp_fixed_lexicon_baseline_20260718.md` measured `995.529975s` for
  50K, which projects to about `19,910.6s` (`5.53h`) for 1M. This 1M run took
  `3449.24s`, about `5.77x` faster than that projection.
- Experiment 15's optimized 50K run measured `220.993083s`, which linearly
  projects to about `4419.86s` for 1M. The actual 1M run was faster than that
  projection, likely because fixed overheads are amortized at larger scale.
- Stage 3 remains the dominant cost at 1M, followed by sharded Stage 4-6 count
  generation and merge.

## 2026-07-19: Stage5-Direct Report Caption Index Smoke On 50K

Purpose:

- Test whether full row-to-caption drill-down can be restored from Stage 5
  canonical mentions/edges without writing a large Stage 6 `facts.jsonl`.
- Keep the report base in aggregate Stage 6 TSV mode, then attach
  `report_caption_index` from Stage 5.

Local regression:

- Command:
  `.\scripts\run_tests.ps1 discover -s tests -p test_build_report_caption_index_from_stage5.py --timeout-seconds 120`
- Result: pass.
- The test verifies that Stage5-direct triple TSV generation matches the
  existing facts-based helper on a fixture, and that Stage5-direct
  `report_caption_index` rows match the existing facts-based index rows.

MLXP conditions:

- Pod: `prod-rsv-snu14ksh-20260720-72ec33`
- Source run:
  `/mnt/nvme/gpic_speed_tests/mixed_stage3_2gpu_stage45614_50k_20260719T154624Z`
- Source Stage 5 shards: `14`
- Source Stage 6 fact output mode: `discard`
- Output:
  `/mnt/nvme/gpic_speed_tests/report_stage5_direct_index_50k_20260719T173339Z`

Result:

- Stage5-direct `patient_action_agent_triple_counts.tsv`: `29s`
- Stage6-TSV interactive report DB build: `13s`
- Stage5-direct `report_caption_index`: `107s`
- Total wrapper runtime: `150s`
- Stage5-direct reconstructed fact count: `8,880,202`

## 2026-07-20: Hardware-Aware Mixed Runner Resource Selection

Purpose:

- Avoid hardcoding GPU IDs and CPU job counts when the same fixed-lexicon
  Stage 1-6 benchmark is moved across MLXP pods or other hardware.
- Make the selected resource plan auditable in the run output instead of
  relying on conversation memory.

Implementation:

- `scripts/run_mixed_caption_pipeline.py --auto-resources` now detects:
  - Linux cgroup CPU quota, process affinity, and `os.cpu_count()`
  - Linux cgroup memory limit
  - visible GPU devices from `CUDA_VISIBLE_DEVICES` or `nvidia-smi`
- The runner fills unset resource knobs:
  - Stage 3 sentence shards and GPU device assignment from visible GPU count
    when `--prefer-gpu` or `--require-gpu` is active
  - Stage 3 jobs from GPU count for sharded GPU annotation
  - Stage 4-6 shards/jobs from detected CPU cores when
    `--stage6-facts-output-mode discard` is used
- Explicit CLI values such as `--stage456-jobs 14` are preserved and recorded
  as explicit overrides.
- The resolved plan is written to `runtime_resource_plan` in
  `mixed_pipeline_summary.jsonl` and progress JSON.
- `--dry-run` prints the same projected plan and exits before inventory loading
  or Stage 1-6 execution. This lets a new MLXP pod be checked safely with:

  `scripts/run_python.ps1 scripts/run_script_with_timeout.py --timeout-seconds 60 -- scripts/run_mixed_caption_pipeline.py --input <caption.jsonl.gz> --output-dir <out> --dry-run --auto-resources --prefer-gpu --stage6-facts-output-mode discard`

Validation:

- The hard timeout wrapper was updated to allow only the mixed pipeline
  `--dry-run` path while continuing to block real Stage 4/5/6 execution.
- `.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_run_script_with_timeout.py`:
  5 tests OK.
- `.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_runtime_resources.py`:
  7 tests OK.
- `.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_mixed_caption_pipeline.py`:
  21 tests OK.
- `.\scripts\run_python.ps1 -m compileall scripts src\gpic_concepts_v1`:
  compile completed.
- Local CLI dry-run through the official timeout wrapper completed and reported
  a projected resource plan without reading inventories or running Stage 1-6.

Code-level optimization notes:

- Stage 3 already loads spaCy with `disable=["ner"]`, so the obvious unused-NER
  quick win is already present.
- Experiment 9 showed Stage 3 batch sizes `64`, `128`, `192`, `256`, and `384`
  differed only narrowly; future speed work should prioritize pipeline
  structure, sharding, serialization, and Stage 4-6 algorithms over more batch
  size sweeps.
- Stage 3 annotation summary now records a breakdown of:
  - model load
  - Stage 2 protected-doc preparation
  - spaCy `nlp.pipe`
  - record construction plus JSONL write overhead
- Sharded Stage 4-6 summary now records top-level wall time for:
  - Stage 3 record splitting
  - shard execution wall time
  - Stage 6 count-table merge
- Use these timing fields before proposing further algorithm changes. In
  particular, do not infer that batch size is the bottleneck unless
  `timing_seconds.spacy_pipe` dominates Stage 3 and changes with batch size.
- High-volume intermediate JSONL writers now skip recursive key sorting while
  keeping sorted JSON for small summary/progress files. The default
  `write_jsonl` behavior remains sorted, and unsorted output is opt-in at
  Stage 1 row files, Stage 3 records, Stage 4 raw graph files, Stage 5
  canonical graph files, optional Stage 6 facts, and shard split files.
  Synthetic local serialization probe on nested Stage 3-like records showed
  about `1.15x` faster JSON serialization for this portion. Count TSVs should
  remain semantically identical because all downstream readers use JSON field
  names, not key order.
- Attempted index rows: `8,393,436`
- Final `report_caption_index` rows: `8,305,490`
- Report DB size: `1,496,276,992` bytes
- Validator:
  `caption_mismatch_count=0`, `has_caption_index=true`, `errors=[]`

View row counts:

- `objects`: `12,765`
- `attributes`: `7,854`
- `actions`: `1,795`
- `relations`: `42,847`
- `object_cooccurrence`: `1,225,934`
- `attribute_object_pairs`: `55,439`
- `patient_action_pairs`: `21,087`
- `agent_action_pairs`: `19,294`
- `patient_action_agent_triples`: `30,649`
- `relation_components`: `967`

Interpretation:

- The Stage5-direct report-caption index restored full caption drill-down for
  the 50K aggregate TSV report without writing Stage 6 `facts.jsonl`.
- The measured direct-index time on 50K was `107s`, faster than the previous
  50K facts-based index time of `180s` recorded in
  `docs/mlxp_fixed_lexicon_baseline_20260718.md`, and avoids the large
  temporary facts file.

## 2026-07-20: Parallel Stage 6 Count-Table Merge Probe On 50K

Purpose:

- After the 50K fixed-lexicon auto-resource run, Stage 4/5/6 shard execution
  was only about `14s`, but Stage 6 count-table merge was about `65s`.
- Test whether merging independent Stage 6 count TSVs per table in parallel
  reduces that bottleneck, and record per-table merge time for the next
  optimization decision.

Implementation:

- `scripts/run_stage456_sharded.py` now accepts `--merge-jobs`.
- `merge_stage6_count_dirs()` merges independent count tables in parallel when
  `merge_jobs > 1`, while preserving the existing per-table
  `merge_count_table_shards()` semantics.
- Stage 6 merged summary now records:
  - `merge_jobs`
  - `table_merge_seconds`
- `scripts/run_mixed_caption_pipeline.py --auto-resources` now fills
  `stage456_merge_jobs` from detected CPU quota, records it in dry-run and
  progress summaries, and passes it to the sharded Stage 4/5/6 runner.

Validation:

- Local:
  `.\scripts\run_tests.ps1 --pytest tests/test_runtime_resources.py tests/test_stage456_sharded.py tests/test_mixed_caption_pipeline.py tests/test_stage6_export_counts.py tests/test_io_jsonl.py --timeout-seconds 180`
  passed `45` tests.
- Local incident-gate regression:
  `.\scripts\run_tests.ps1 --pytest tests/test_incident_gate.py --timeout-seconds 120`
  passed `14` tests.
- Remote MLXP compile and targeted unittest suite passed after applying the
  source sync zip to pod `prod-rsv-snu14ksh-20260720-72ec33`.

MLXP conditions:

- Pod: `prod-rsv-snu14ksh-20260720-72ec33`
- Input:
  `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `50,000`
- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_parallel_merge_50k_20260720T034928Z`
- Auto resource plan:
  - Stage 3 sentence shards/jobs: `2`, GPUs `0,1`
  - Stage 4/5/6 shards/jobs: `28`
  - Stage 6 merge jobs requested: `28`
  - Stage 6 merge jobs used: `12` (capped to number of count tables)
- Stage 6 count backend: `memory`
- Stage 6 facts output mode: `discard`

Result:

- Total pipeline: `214.054296s`
- Stage 3 sharded: `127.074555s`
- Stage 4/5/6 sharded: `83.402652s`
- Stage 4/5/6 internal timing:
  - split Stage 3 records: `9.708550s`
  - run shards wall: `14.866233s`
  - merge Stage 6 counts: `57.685604s`
- Stage 6 fact total: `8,880,202`
- Stage 6 count integrity: `ok`

Comparison to previous 50K auto-resource run:

- Previous total pipeline:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_unsorted_json_50k_20260720T032314Z`
  reported `218.126914s`.
- Total pipeline improved by about `4.07s`.
- Previous Stage 6 merge time was `65.123299s`.
- Stage 6 merge improved by about `7.44s`.

Per-table merge timing from the parallel run:

- `object_cooccurrence_pair_counts.tsv`: `57.493132s`
- `object_attribute_pair_counts.tsv`: `2.450052s`
- `agent_patient_pair_counts.tsv`: `2.052463s`
- `relation_triple_counts.tsv`: `1.614514s`
- all remaining count tables: under `1s` each

Interpretation:

- Parallel table merge helps, but the remaining merge bottleneck is almost
  entirely `object_cooccurrence_pair_counts.tsv`.
- Further speed work should target the object co-occurrence table merge
  algorithm itself, not more table-level parallelism.

## 2026-07-20: Stage 6 TSV Merge Row-Reader Probe On 50K

Purpose:

- The parallel merge probe showed the remaining bottleneck was one large TSV:
  `object_cooccurrence_pair_counts.tsv`.
- Reduce per-row Python overhead in the generic merge loop without changing
  count semantics or output order.

Implementation:

- `merge_count_table_shards()` now reads rows with `csv.reader` and header
  indices instead of `csv.DictReader`.
- It writes rows with `csv.writer` instead of constructing a dict for every
  output row.
- Existing validation remains:
  - schema mismatch detection
  - blank `count_key` detection
  - row width mismatch detection
  - value-field conflict detection
  - count integrity after merged Stage 6 tables

Validation:

- Local:
  `.\scripts\run_tests.ps1 --pytest tests/test_stage456_sharded.py tests/test_mixed_caption_pipeline.py tests/test_stage6_export_counts.py --timeout-seconds 180`
  passed `35` tests.
- Local incident-gate regression:
  `.\scripts\run_tests.ps1 --pytest tests/test_incident_gate.py --timeout-seconds 120`
  passed `14` tests.
- Remote MLXP compile and targeted unittest suite passed after applying the
  source sync zip to pod `prod-rsv-snu14ksh-20260720-72ec33`.
- Byte-level comparison between old and new merged TSV outputs reported
  `mismatch_count=0`.

MLXP merge-only conditions:

- Source run:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_parallel_merge_50k_20260720T034928Z`
- Source shard dirs:
  `stage456_sharded/shards/shard_*/stage6`
- Output:
  `/mnt/nvme/gpic_speed_tests/merge_only_row_reader_50k_20260720T035812Z`
- Merge jobs requested: `28`
- Merge jobs used: `12`

Result:

- Merge-only wall time: `50.071137s`
- Stage 6 count integrity: `ok`
- Stage 6 fact total: `8,880,202`
- `object_cooccurrence_pair_counts.tsv` merge time:
  - before row-reader optimization: `57.493132s`
  - after row-reader optimization: `49.946113s`
- All other table merge timings remained small; the largest non-cooccurrence
  table was `object_attribute_pair_counts.tsv` at `2.036517s`.

Interpretation:

- The row-reader optimization preserved byte-identical merged TSV output and
  reduced the dominant object co-occurrence merge by about `7.55s`.
- At this point the next meaningful speedup likely requires changing the
  object co-occurrence merge strategy itself, such as partitioning that one
  table by `count_key` hash before merging, rather than adding more table-level
  parallelism.

## 2026-07-20: Hash-Partitioned Object Co-Occurrence Merge Probe On 50K

Purpose:

- The remaining Stage 6 merge bottleneck was
  `object_cooccurrence_pair_counts.tsv`, a single table that could not benefit
  from table-level parallelism.
- Split that table by stable `count_key` hash, merge each partition with the
  existing merge semantics, then k-way merge the sorted partition outputs back
  into the same global `(-count, count_key)` order.

Implementation:

- `scripts/run_stage456_sharded.py` now accepts:
  - `--partitioned-merge-tables`
  - `--partitioned-merge-partitions`
- By default, only `object_cooccurrence_pair_counts.tsv` uses hash-partitioned
  merge.
- The partition count defaults to the requested `--merge-jobs` value.
- Other count tables still use the existing single-pass table merge.
- Stage 6 merged summary now records:
  - `table_merge_strategies`
  - `table_merge_details`
  - partition count, partition jobs, partition input row distribution
  - partition write, partition merge, and final k-way merge timings

Validation:

- Local:
  `.\scripts\run_tests.ps1 --pytest tests/test_stage456_sharded.py tests/test_mixed_caption_pipeline.py tests/test_stage6_export_counts.py --timeout-seconds 240`
  passed `36` tests.
- The new local regression test verifies that partitioned merge output is
  byte-identical to the single-pass merge output for
  `object_cooccurrence_pair_counts.tsv`.
- Remote MLXP compile and targeted unittest suite passed after applying the
  source sync zip to pod `prod-rsv-snu14ksh-20260720-72ec33`.
- Byte-level comparison against the previous merged Stage 6 TSV directory
  reported `mismatch_count=0`.

MLXP merge-only conditions:

- Source run:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_parallel_merge_50k_20260720T034928Z`
- Source shard dirs:
  `stage456_sharded/shards/shard_*/stage6`
- Output:
  `/mnt/nvme/gpic_speed_tests/merge_only_partitioned_cooccurrence_50k_20260720T044255Z`
- Merge jobs requested: `28`
- Table-level merge jobs used: `12`
- Object co-occurrence hash partitions: `28`
- Object co-occurrence partition jobs: `28`

Result:

- Merge-only wall time: `34.769159s`
- Stage 6 count integrity: `ok`
- Stage 6 fact total: `8,880,202`
- `object_cooccurrence_pair_counts.tsv` merge time:
  - row-reader merge-only probe: `49.946113s`
  - hash-partitioned merge probe: `32.703002s`
- Object co-occurrence partition timing:
  - partition write: `22.317958s`
  - partition merge: `2.761395s`
  - final k-way merge: `7.538368s`
- Partition balance:
  - nonempty partitions: `28 / 28`
  - min input rows per partition: `126,360`
  - max input rows per partition: `130,711`

Interpretation:

- Hash partitioning preserved exact merged TSV output and reduced the dominant
  object co-occurrence merge by about `17.24s` compared with the row-reader
  merge-only probe.
- Overall merge-only wall time improved from `50.071137s` to `34.769159s`.
- The remaining co-occurrence merge cost is mostly partition file writing and
  final k-way merge, not the per-partition aggregation itself.

Full 50K pipeline confirmation:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_parallel_merge_50k_20260720T044511Z`
- Total pipeline: `192.155327s`
- Throughput: `260.206161` captions/s
- Stage 3 sharded: `125.497467s`
- Stage 4/5/6 sharded: `63.010449s`
- Stage 4/5/6 internal timing:
  - split Stage 3 records: `9.656429s`
  - run shards wall: `14.101643s`
  - merge Stage 6 counts: `38.109125s`
- Stage 6 count integrity: `ok`
- Stage 6 fact total: `8,880,202`
- Object co-occurrence table merge strategy: `hash_partition`
- Object co-occurrence table merge time: `35.978755s`
- Byte-level comparison against
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_parallel_merge_50k_20260720T034928Z/stage6`
  reported `mismatch_count=0`.

Comparison to previous full 50K row-reader run:

- Previous total pipeline: `214.054296s`
- New total pipeline: `192.155327s`
- Total pipeline improvement: about `21.90s`
- Previous Stage 6 merge: `57.685604s`
- New Stage 6 merge: `38.109125s`
- Stage 6 merge improvement: about `19.58s`

## 2026-07-20: Stage 3 Raw Split/Combine And Auto Job Scheduling

Purpose:

- After Stage 6 merge optimization, Stage 3 became the dominant 50K cost.
- The sharded Stage 3 runner was spending avoidable time JSON-parsing rows just
  to split and recombine already valid JSONL.
- Auto resources also selected `stage3_jobs=2` on a 2-GPU pod even though the
  generated Stage 3 work contained three non-empty shards: two sentence shards
  plus one tag-list shard.

Implementation:

- `scripts/run_stage3_sharded.py` now splits JSONL shards by copying nonblank
  raw lines instead of parsing and reserializing every row.
- `scripts/run_mixed_caption_pipeline.py` now combines sharded Stage 3 records
  in caption order while preserving raw Stage 3 JSONL lines.
- Stage 3 sharded summaries now include detailed timings for row split,
  worker wall time, shard merge, and final caption-order combine.
- `choose_mixed_pipeline_resource_plan()` now selects automatic Stage 3 jobs
  from the total generated Stage 3 shard slots, bounded by detected CPU quota,
  instead of defaulting to GPU count. Explicit `--stage3-jobs` still wins.

Validation:

- Local:
  `.\scripts\run_tests.ps1 --pytest tests/test_runtime_resources.py tests/test_mixed_caption_pipeline.py tests/test_stage3_sharded.py --timeout-seconds 240`
  passed `37` tests.
- Remote MLXP:
  `outputs/mlxp_speed_tests/remote_apply_test_stage3_auto_jobs_20260720.sh`
  passed the same `37` tests on pod
  `prod-rsv-snu14ksh-20260720-72ec33`.
- The remote auto-resource smoke check reported:

  ```text
  AUTO_STAGE3_CHOSEN {'stage3_sentence_shards': 2,
                      'stage3_tag_shards': 1,
                      'stage3_jobs': 3,
                      'stage3_gpu_devices': ['0', '1'],
                      'stage456_shards': 28,
                      'stage456_jobs': 28,
                      'stage456_merge_jobs': 28}
  ```

Raw split/combine benchmark:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_raw_split_50k_20260720T052608Z`
- Total pipeline: `180.289884s`
- Stage 3 sharded: `117.816409s`
- Stage 4/5/6 sharded: `58.846863s`
- Stage 3 timing:
  - split sentence rows: `0.115188s`
  - split tag rows: `0.000806s`
  - run shards wall: `111.740871s`
  - combine caption order: `4.7245s`
- Byte-level Stage 6 comparison against the previous hash-partition run:
  `mismatch_count=0`

Manual `--stage3-jobs 3` scheduling probe:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_jobs3_50k_20260720T053011Z`
- Total pipeline: `168.975371s`
- Stage 3 sharded: `106.728564s`
- Stage 4/5/6 sharded: `58.72515s`
- Stage 3 timing:
  - run shards wall: `100.622255s`
  - combine caption order: `4.805285s`
  - total: `106.410342s`
- Interpretation: the small tag-list shard no longer waits behind a sentence
  shard, and sharing GPU 0 for the small tag shard did not materially slow the
  sentence shard on this H200 pod.

Default auto-resource confirmation after planner change:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_auto_jobs_50k_20260720T054333Z`
- Total pipeline: `171.267086s`
- Stage 3 sharded: `106.906779s`
- Stage 4/5/6 sharded: `60.777087s`
- Stage 3 sharded summary selected `jobs=3`.
- Runtime resource plan selected:
  - `stage3_sentence_shards=2`
  - `stage3_tag_shards=1`
  - `stage3_jobs=3`
  - `stage456_shards=28`
  - `stage456_jobs=28`
  - `stage456_merge_jobs=28`
- Stage 6 count integrity: `ok`
- Stage 6 fact total: `8,880,202`
- Byte-level Stage 6 comparison against the manual `--stage3-jobs 3` run:
  `mismatch_count=0`

Comparison:

- Hash-partition full 50K before Stage 3 work: `192.155327s`
- Raw split/combine only: `180.289884s`
- Manual jobs=3 scheduling probe: `168.975371s`
- Default auto after planner change: `171.267086s`
- The default auto run is slightly slower than the manual probe by normal run
  noise, but it now chooses the same Stage 3 concurrency automatically and
  preserves byte-identical Stage 6 counts.

## 2026-07-20: Compact Stage 3 JSONL And Raw Stage 4/5/6 Split

Purpose:

- Stage 3 still spent about `11s` per sentence shard outside Stage 2 and spaCy
  model execution, mostly building records and writing JSONL.
- Stage 4/5/6 sharding still parsed and reserialized every Stage 3 JSONL row
  only to split rows across shards.

Implementation:

- `write_jsonl()` now builds a JSON encoder once per output file instead of
  calling `json.dumps()` with encoder options for every row.
- `write_jsonl(..., compact=True)` writes compact JSON separators while keeping
  parsed JSON semantics identical.
- `run_stage3_annotate()` uses compact JSONL for Stage 3 records.
- `split_stage3_records()` now preserves raw Stage 3 JSONL lines when writing
  Stage 4/5/6 shard inputs.
- `split_stage3_records()` extracts the leading Stage 3 `caption_id` with a
  lightweight regex and falls back to full `json.loads()` if the expected field
  order is not present. Duplicate-caption checks and caption digest generation
  are still retained.

Validation:

- Local compact JSONL/Stage 3 tests:
  `.\scripts\run_tests.ps1 --pytest tests/test_io_jsonl.py tests/test_stage3_annotate.py tests/test_stage3_sharded.py tests/test_mixed_caption_pipeline.py --timeout-seconds 300`
  passed `40` tests.
- Remote compact JSONL tests on MLXP:
  `outputs/mlxp_speed_tests/remote_apply_test_stage3_compact_json_20260720.sh`
  passed `40` tests.
- Local raw Stage 4/5/6 split tests:
  `.\scripts\run_tests.ps1 --pytest tests/test_stage456_sharded.py tests/test_io_jsonl.py tests/test_mixed_caption_pipeline.py --timeout-seconds 300`
  passed `35` tests.
- Remote raw split tests on MLXP:
  `outputs/mlxp_speed_tests/remote_apply_test_stage456_raw_split_20260720.sh`
  passed `31` tests.

Compact Stage 3 JSONL benchmark:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_compact_json_50k_20260720T055633Z`
- Baseline:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_auto_jobs_50k_20260720T054333Z`
- Total pipeline:
  - before compact JSONL: `171.267086s`
  - after compact JSONL: `167.505499s`
- Stage 3 sharded:
  - before: `106.906779s`
  - after: `104.629683s`
- Stage 4/5/6 sharded:
  - before: `60.777087s`
  - after: `59.458427s`
- Stage 3 combined JSONL size:
  - before: `635,188,997` bytes
  - after: `567,901,834` bytes
- Stage 3 sentence JSONL size:
  - before: `631,432,047` bytes
  - after: `564,533,038` bytes
- Stage 6 count integrity: `ok`
- Byte-level Stage 6 comparison against the baseline run:
  `mismatch_count=0`

Raw Stage 4/5/6 split benchmark:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage456_raw_split_50k_20260720T060623Z`
- Baseline:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_compact_json_50k_20260720T055633Z`
- Total pipeline:
  - before raw split: `167.505499s`
  - after raw split: `161.620333s`
- Stage 4/5/6 sharded:
  - before: `59.458427s`
  - after: `51.621294s`
- Stage 4/5/6 internal split:
  - before: `9.547941s`
  - after: `1.096984s`
- Stage 6 count integrity: `ok`
- Byte-level Stage 6 comparison against the baseline run:
  `mismatch_count=0`

Comparison after this round:

- Hash-partition full 50K before Stage 3 work: `192.155327s`
- Default auto after Stage 3 job scheduling: `171.267086s`
- Compact Stage 3 JSONL: `167.505499s`
- Raw Stage 4/5/6 split: `161.620333s`
- Net improvement from `192.155327s` to `161.620333s`: about `30.53s`
  on the same 50K fixed-lexicon MLXP benchmark shape.

## 2026-07-20: Compact Stage 4/5 JSONL Outputs

Purpose:

- After Stage 3 JSONL became compact, Stage 4 raw mentions/edges and Stage 5
  canonical mentions/edges were still written with default JSON separators.
- These files are read by Stage 5/6 and can be large, so compact separators
  reduce intermediate I/O without changing parsed JSON semantics.

Implementation:

- `run_stage4_extract_raw()` now writes `raw_mentions.jsonl` and
  `raw_edges.jsonl` with `write_jsonl(..., sort_keys=False, compact=True)`.
- `run_stage5_canonicalize()` now uses a reusable compact `JSONEncoder` for
  streaming `canonical_mentions.jsonl` and `canonical_edges.jsonl`.
- Summary JSONL output remains unchanged because it is tiny and human-facing.

Validation:

- Local tests:
  `.\scripts\run_tests.ps1 --pytest tests/test_io_jsonl.py tests/test_stage4_extract_raw.py tests/test_stage5_canonicalize.py tests/test_stage456_sharded.py --timeout-seconds 420`
  passed `69` tests.
- Remote MLXP tests:
  `outputs/mlxp_speed_tests/remote_apply_test_stage45_compact_json_20260720.sh`
  passed `69` tests.
- A partial-sync zip issue was caught before remote extraction: PowerShell
  `Compress-Archive` flattened individual file paths. The durable guard is now
  documented in `AGENTS.md`: partial remote code-sync zips must preserve
  explicit relative arcnames and list archive entries before upload.

Benchmark:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage45_compact_json_50k_20260720T062041Z`
- Baseline:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage456_raw_split_50k_20260720T060623Z`
- Total pipeline:
  - before compact Stage 4/5 JSONL: `161.620333s`
  - after compact Stage 4/5 JSONL: `158.999949s`
- Stage 4/5/6 sharded:
  - before: `51.621294s`
  - after: `50.471267s`
- Stage 4/5 intermediate JSONL size:
  - `raw_mentions.jsonl`: `1,442,348,584` -> `1,362,817,189` bytes
  - `raw_edges.jsonl`: `245,766,012` -> `228,422,189` bytes
  - `canonical_mentions.jsonl`: `704,648,635` -> `668,248,199` bytes
  - `canonical_edges.jsonl`: `297,069,007` -> `277,015,592` bytes
- Stage 6 count integrity: `ok`
- Stage 6 fact total: `8,880,202`
- Byte-level Stage 6 comparison against the baseline run:
  `mismatch_count=0`

Comparison after this round:

- Hash-partition full 50K before Stage 3 work: `192.155327s`
- Default auto after Stage 3 job scheduling: `171.267086s`
- Compact Stage 3 JSONL: `167.505499s`
- Raw Stage 4/5/6 split: `161.620333s`
- Compact Stage 4/5 JSONL: `158.999949s`
- Net improvement from `192.155327s` to `158.999949s`: about `33.16s`
  on the same 50K fixed-lexicon MLXP benchmark shape.

## 2026-07-20: Stage 3 Concurrency Sweep On 2x H200

Purpose:

- After compact JSONL work, the default auto-resource planner still selected
  only `2` sentence shards on the 2-GPU MLXP pod because it used GPU count
  directly.
- A sweep was run on the same 50K fixed-lexicon benchmark to find whether
  additional sentence shards per GPU improve Stage 3 throughput.

Benchmark setup:

- Pod: `prod-rsv-snu14ksh-20260720-72ec33`
- Hardware shape observed by the runner: 2 visible H200-class GPUs and 28 CPU
  jobs available to the pod.
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `50,000`
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition lexicon: `resources/lexicons/preposition_mwes.tsv`
- Common options:
  `--auto-resources --require-gpu --batch-size 192 --stage6-count-backend memory --stage6-facts-output-mode discard`
- Each probe compared Stage 6 TSV output against:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage45_compact_json_50k_20260720T062041Z/stage6`
- Every probe reported:
  - `mismatch_count=0`
  - `count_integrity=ok`
  - `fact_total=8,880,202`

Results:

| stage3 sentence shards | stage3 jobs | total seconds | stage3 seconds | stage456 seconds |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 3 | 158.999949 | 105.040351 | 50.471267 |
| 4 | 5 | 129.165917 | 75.141465 | 50.596389 |
| 6 | 7 | 117.314052 | 62.969500 | 50.834929 |
| 8 | 9 | 113.918472 | 58.943021 | 51.457814 |
| 10 | 11 | 111.933427 | 58.032890 | 50.461920 |
| 12 | 13 | 110.222421 | 56.526845 | 50.230075 |
| 16 | 17 | 109.463110 | 55.421831 | 50.566210 |
| 20 | 21 | 110.493946 | 56.494171 | 50.464250 |
| 24 | 25 | 110.164408 | 55.673032 | 50.941136 |

Conclusion:

- The best observed 50K setting on this pod was `16` sentence shards plus
  `1` tag shard, scheduled with `17` Stage 3 jobs.
- Higher concurrency (`20` or `24` sentence shards) did not improve total time,
  so the useful range plateaued around `8` sentence workers per H200-class GPU.
- The auto-resource planner now estimates Stage 3 sentence workers from GPU
  memory instead of raw GPU count:
  - `16GiB` GPU memory budget per Stage 3 sentence worker
  - maximum `8` sentence workers per GPU
  - final sentence shard count limited by available CPU jobs after tag shards
- This is hardware-aware rather than H200-name-specific: smaller GPUs and lower
  CPU quotas automatically produce fewer sentence shards, while explicit CLI
  shard/job overrides still win.

Validation:

- Local planner tests:
  `.\scripts\run_tests.ps1 --pytest tests/test_runtime_resources.py --timeout-seconds 180`
  passed `11` tests.
- Remote MLXP planner/mixed-runner tests:
  `outputs/mlxp_speed_tests/remote_apply_test_stage3_gpu_memory_auto_20260720.sh`
  passed `40` tests.
- Code-sync zip creation now uses `scripts/build_code_sync_zip.py` so partial
  remote sync archives preserve repository-relative entries before upload.
- Auto-resource confirmation run:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_gpu_memory_auto_50k_20260720T074953Z`
  - selected by auto:
    `stage3_sentence_shards=16`, `stage3_tag_shards=1`,
    `stage3_jobs=17`, `stage3_gpu_devices=[0,1]`
  - total pipeline: `109.647501s`
  - Stage 3 sharded: `55.628157s`
  - Stage 4/5/6 sharded: `50.529151s`
  - Stage 6 fact total: `8,880,202`
  - Stage 6 count integrity: `ok`
  - byte-level Stage 6 comparison against the compact Stage 4/5 JSONL
    baseline: `mismatch_count=0`

## 2026-07-20: 200K Auto-Resource Fixed-Lexicon Scaling Probe

Purpose:

- Confirm that the 50K auto-resource settings scale before attempting another
  million-caption run.
- Use the same fixed lexicon path and the hardware-aware planner without
  explicit Stage 3 shard/job overrides.

Run:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_gpu_memory_auto_200k_20260720T083204Z`
- Pod: `prod-rsv-snu14ksh-20260720-72ec33`
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `200,000`
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition lexicon: `resources/lexicons/preposition_mwes.tsv`
- Options:
  `--auto-resources --require-gpu --batch-size 192 --stage6-count-backend memory --stage6-facts-output-mode discard`

Auto-selected resources:

- `stage3_sentence_shards=16`
- `stage3_tag_shards=1`
- `stage3_jobs=17`
- `stage3_gpu_devices=[0,1]`
- `stage456_shards=28`
- `stage456_jobs=28`
- `stage456_merge_jobs=28`

Result:

- Total pipeline: `339.894327s`
- Throughput: `588.418176 captions/s`
- Stage 1 records: `6.777507s`
- Stage 1 mixed caption rows: `3.911497s`
- Stage 3 sharded: `187.442063s`
- Stage 4/5/6 sharded: `140.925207s`
- Stage 6 fact total: `35,799,756`
- Stage 6 count integrity: `ok`

Stage details:

- Stage 3 internal:
  - split sentence rows: `0.463685s`
  - run shards wall: `163.693364s`
  - merge sentence Stage 3 records: `3.293758s`
  - combine caption order: `18.910630s`
  - total: `186.382122s`
- Stage 4/5/6 internal:
  - split Stage 3 records: `4.212743s`
  - run shards wall: `45.399268s`
  - merge Stage 6 counts: `90.054821s`
  - total: `139.670179s`
- Dominant Stage 6 merge table:
  - `object_cooccurrence_pair_counts.tsv`: `84.676473s`
  - hash partition write: `60.871044s`
  - partition merge: `5.931448s`
  - final k-way merge: `17.641848s`

Scaling against 50K auto-resource confirmation:

| Limit | Total | Stage 3 | Stage 4/5/6 | Fact Total |
| ---: | ---: | ---: | ---: | ---: |
| 50K | `109.647501s` | `55.628157s` | `50.529151s` | `8,880,202` |
| 200K | `339.894327s` | `187.442063s` | `140.925207s` | `35,799,756` |

Interpretation:

- 200K total time is about `3.10x` the 50K time, not `4x`; the fixed overheads
  amortize well at this size.
- Stage 3 is about `3.37x` the 50K Stage 3 time.
- Stage 4/5/6 is about `2.79x` the 50K Stage 4/5/6 time, but Stage 6 merge is
  already dominated by the object co-occurrence table.
- A naive linear projection from the 200K run gives a 1M fixed-lexicon
  Stage 1-6 count-only runtime of about `1,699s` (`28.3min`) on this pod,
  excluding caption-index/report DB generation.

Process notes:

- The first remote poll only showed the mixed-level Stage 3 start because
  `progress.json` is not updated continuously inside Stage 3. The poller was
  updated to summarize Stage 3 shard progress files, process state, and
  Stage 4/5/6 file growth.
- Completed mixed progress embeds a very large summary JSON. The poller now
  compacts the progress object and truncates stdout/stderr tails to avoid
  another oversized status dump.

## 2026-07-20: 1M Auto-Resource Fixed-Lexicon Count-Only Run

Purpose:

- Measure the current Stage 1-6 fixed-lexicon count-only runtime at the target
  GPIC-Nano 1M scale on the 2x H200 MLXP pod.
- Keep caption-index/report DB generation out of this timing; this run measures
  TSV count generation with facts discarded.

Run:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_gpu_memory_auto_1m_20260720T084740Z`
- Pod: `prod-rsv-snu14ksh-20260720-72ec33`
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `1,000,000`
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition lexicon: `resources/lexicons/preposition_mwes.tsv`
- Options:
  `--auto-resources --require-gpu --batch-size 192 --stage6-count-backend memory --stage6-facts-output-mode discard`

Auto-selected resources:

- `stage3_sentence_shards=16`
- `stage3_tag_shards=1`
- `stage3_jobs=17`
- `stage3_gpu_devices=[0,1]`
- `stage456_shards=28`
- `stage456_jobs=28`
- `stage456_merge_jobs=28`

Result:

- Total pipeline: `1466.093043s` (`24m 26s`)
- Throughput: `682.085 captions/s`
- Stage 1 records: `35.950638s`
- Stage 1 mixed caption rows: `23.246409s`
- Stage 3 sharded: `916.012376s`
- Stage 4/5/6 sharded: `490.045417s`
- Stage 6 fact total: `178,529,467`
- Stage 6 count integrity: `ok`
- This is a count-TSV benchmark only. Report/UI-only derived views such as
  separate patient-action, agent-action, and patient-action-agent triple tables
  are not generated in this timing. The base Stage 6 role counts are present in
  `agent_patient_pair_counts.tsv` with a `role` column.

Stage details:

- Stage 3 internal:
  - split sentence rows: `3.230638s`
  - run shards wall: `781.112726s`
  - merge sentence Stage 3 records: `21.890495s`
  - combine caption order: `104.537064s`
  - total: `910.929472s`
- Stage 4/5/6 internal:
  - split Stage 3 records: `26.963129s`
  - run shards wall: `199.242190s`
  - merge Stage 6 counts: `262.231937s`
  - total: `488.440942s`
- Dominant Stage 6 merge table:
  - `object_cooccurrence_pair_counts.tsv`: `246.309243s`

Scaling:

| Limit | Total | Stage 3 | Stage 4/5/6 | Fact Total |
| ---: | ---: | ---: | ---: | ---: |
| 50K | `109.647501s` | `55.628157s` | `50.529151s` | `8,880,202` |
| 200K | `339.894327s` | `187.442063s` | `140.925207s` | `35,799,756` |
| 1M | `1466.093043s` | `916.012376s` | `490.045417s` | `178,529,467` |

Interpretation:

- The 1M run is faster than the 200K linear projection (`1699s`), mainly
  because fixed overheads continue to amortize and Stage 4/5/6 scales better
  than linear at this size.
- Stage 3 remains the largest block (`62.5%` of total time), while Stage 6
  count merging is dominated by object co-occurrence aggregation.
- During the run, cgroup `memory.current` rose above `440GB`, but selected
  `memory.stat` showed this was almost entirely file cache; `anon` memory stayed
  low during the merge/check phases. The completed run reported no stderr and
  `count_integrity=ok`.

Process notes:

- The 1M poller was tightened after an oversized status response: it now follows
  only the launched process tree, truncates command lines, and reports bounded
  Stage 3/Stage 4/5/6 file summaries.
- A completed remote launcher may remain as `STAT Z` (`<defunct>`). The poller
  treats that as not running and relies on `benchmark_result.json` and
  `job_status.json` for completion status.

## 2026-07-20: Fast Stage 3 Caption-ID Combine + Stage 6 Partition Write Tuning

Purpose:

- Reduce fixed-lexicon Stage 1-6 runtime without changing extraction,
  canonicalization, or count semantics.
- Target two measured overheads:
  - Stage 3 mixed combine was parsing full Stage 3 JSONL records only to check
    `caption_id`.
  - Stage 6 object co-occurrence hash partition writing dominated count merge
    time.

Implementation:

- Added `scripts/stage3_jsonl_utils.py` with a shared
  `extract_stage3_caption_id_from_line()` helper.
- `scripts/run_mixed_caption_pipeline.py` now uses that helper during
  `combine_stage3_records_in_caption_order()`, preserving raw Stage 3 JSONL
  lines while avoiding full `json.loads()` for the normal
  `{"caption_id": ...}` prefix shape.
- `scripts/run_stage456_sharded.py` now reuses the same helper instead of a
  local duplicate.
- Stage 6 partitioned count merge now:
  - uses stable `zlib.crc32()` partitioning instead of `hashlib.blake2b()`;
  - opens large count TSV streams with a 1 MiB buffer;
  - skips per-row field reordering when shard headers already match canonical
    count table field order.

Validation:

- Local targeted tests passed:
  `tests/test_mixed_caption_pipeline.py tests/test_stage456_sharded.py`
  (`31 passed`).
- Remote MLXP targeted tests passed on pod
  `prod-rsv-snu14ksh-20260720-72ec33` (`31 passed`).
- 50K and 200K benchmark outputs were byte-compared against the prior
  auto-resource Stage 6 TSV baselines:
  - 50K mismatch count: `0`
  - 200K mismatch count: `0`
- Stage 6 count integrity was `ok` in both runs.

50K results:

- Baseline:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_gpu_memory_auto_50k_20260720T074953Z`
- Stage3-only candidate:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_fast_caption_id_50k_20260720T123302Z`
- Stage3+Stage6 candidate:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_fast_caption_id_stage6_crc_50k_20260720T124941Z`

| Run | Total | Stage 3 | Stage 4/5/6 | Stage 3 combine |
| --- | ---: | ---: | ---: | ---: |
| Baseline | `109.647501s` | `55.628157s` | `50.529151s` | `4.730729s` |
| Fast caption-id combine | `106.274239s` | `50.667203s` | `52.027621s` | `1.384324s` |
| Fast combine + Stage 6 tuning | `102.308875s` | `51.180691s` | `47.717079s` | `1.374836s` |

Stage 6 object co-occurrence detail for the 50K combined run:

- `object_cooccurrence_pair_counts.tsv`: `28.535843s`
- partition write: `18.357917s`
- partition merge: `2.811475s`
- final k-way merge: `7.330714s`

200K results:

- Baseline:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_gpu_memory_auto_200k_20260720T083204Z`
- Stage3-only candidate:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_fast_caption_id_200k_20260720T123655Z`
- Stage3+Stage6 candidate:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_fast_caption_id_stage6_crc_200k_20260720T125237Z`

| Run | Total | Stage 3 | Stage 4/5/6 | Stage 3 combine | Object cooccurrence merge |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | `339.894327s` | `187.442063s` | `140.925207s` | `18.910630s` | about `84.676473s` from previous 200K auto-resource summary |
| Fast caption-id combine | `327.824887s` | `176.570173s` | `140.037621s` | `5.367105s` | `84.196554s` |
| Fast combine + Stage 6 tuning | `315.250059s` | `174.766738s` | `129.361179s` | `5.301728s` | `74.526650s` |

Interpretation:

- The fast caption-id combine is result-preserving and saves `13.54s` in the
  200K Stage 3 combine step.
- Stage 6 tuning is also result-preserving and saves about `9.67s` on the 200K
  object co-occurrence merge.
- Combined 200K improvement over the prior auto-resource baseline is
  `24.644268s` (`339.894327s -> 315.250059s`).
- The 1M run with this combined change is recorded in the next section with
  byte-diff validation against the prior 1M Stage 6 TSV baseline.

## 2026-07-20: 1M Fast Caption-ID Combine + Stage 6 CRC Partition Run

Purpose:

- Measure the same 1M fixed-lexicon count-only workload after the fast Stage 3
  caption-id combine and Stage 6 partition-write tuning.
- Validate that the optimized output is byte-identical to the prior 1M
  auto-resource Stage 6 TSV baseline.

Run:

- Output:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_fast_caption_id_stage6_crc_1m_20260720T135021Z`
- Baseline for byte comparison:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_gpu_memory_auto_1m_20260720T084740Z/stage6`
- Input: `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Limit: `1,000,000`
- Inventory bundle: `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition lexicon: `resources/lexicons/preposition_mwes.tsv`
- Options:
  `--auto-resources --require-gpu --batch-size 192 --stage6-count-backend memory --stage6-facts-output-mode discard`

Auto-selected resources:

- `stage3_sentence_shards=16`
- `stage3_tag_shards=1`
- `stage3_jobs=17`
- `stage3_gpu_devices=[0,1]`
- `stage456_shards=28`
- `stage456_jobs=28`
- `stage456_merge_jobs=28`

Result:

- Total pipeline: `1354.082689s` (`22m 34s`)
- Stage 1 records: `35.704333s`
- Stage 1 mixed caption rows: `22.516969s`
- Stage 3 sharded: `839.849944s`
- Stage 4/5/6 sharded: `455.190533s`
- Stage 6 fact total: `178,529,467`
- Stage 6 count integrity: `ok`
- Byte-level Stage 6 comparison against the prior 1M baseline:
  `mismatch_count=0`

Detailed timings:

- Stage 3 internal:
  - split sentence rows: `3.203791s`
  - run shards wall: `776.029236s`
  - merge sentence Stage 3 records: `21.917024s`
  - combine caption order: `33.230744s`
  - total: `834.544405s`
- Stage 4/5/6 internal:
  - split Stage 3 records: `26.741085s`
  - run shards wall: `193.991385s`
  - merge Stage 6 counts: `232.833716s`
  - total: `453.569260s`
- Dominant Stage 6 merge table:
  - `object_cooccurrence_pair_counts.tsv`: `217.352647s`
  - partition write: `153.263839s`
  - partition merge: `16.320788s`
  - final k-way merge: `47.577623s`

Comparison with the prior 1M auto-resource baseline:

| Metric | Prior 1M | Fast combine + CRC | Delta |
| --- | ---: | ---: | ---: |
| total_pipeline | `1466.093043s` | `1354.082689s` | `-112.010354s` |
| stage3_sharded | `916.012376s` | `839.849944s` | `-76.162432s` |
| stage456_sharded | `490.045417s` | `455.190533s` | `-34.854884s` |
| Stage 3 combine caption order | `104.537064s` | `33.230744s` | `-71.306320s` |
| object cooccurrence merge | `246.309243s` | `217.352647s` | `-28.956596s` |

Interpretation:

- The fast caption-id combine and Stage 6 partition-write tuning are
  result-preserving at 1M scale.
- The authoritative 1M count-only runtime is now about `22m 34s`, down from
  `24m 26s`.
- Most of the 1M gain came from avoiding full JSON parsing during Stage 3
  caption-order combine. The Stage 6 CRC/buffer tuning provided a smaller but
  visible gain on the object co-occurrence merge.

## 2026-07-20: Stage 3 spaCy Component Disable Audit

Purpose:

- Check whether disabling additional spaCy components can reduce Stage 3 time
  without changing Stage 6 count TSV outputs.
- Default Stage 3 already disables `ner`; this audit tested additionally
  disabling `attribute_ruler`.

Code changes made before the benchmark:

- Stage 3 now exposes a general `--stage3-disable-components` /
  `--disable-components` option instead of hard-coding only `ner`.
- Stage 3 summaries record both disabled and enabled spaCy components.
- The default remains `ner` only.

Validation before benchmark:

- Local:
  `run_tests.ps1 --pytest tests/test_stage3_annotate.py tests/test_stage3_sharded.py tests/test_mixed_caption_pipeline.py`
  passed: `36 passed`.
- Remote MLXP apply/test passed: `36` unittest tests OK.

50K benchmark:

- Baseline:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_fast_caption_id_stage6_crc_50k_20260720T124941Z`
- Candidate:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_disable_attribute_ruler_50k_20260720Tstage3audit`
- Candidate disabled components: `ner,attribute_ruler`

Result:

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| total_pipeline | `102.308875s` | `55.792173s` |
| stage3_sharded | `51.180691s` | `48.500293s` |
| noun_chunk_total | `522,180` | `0` |
| Stage 6 TSV mismatch count | `0` baseline reference | `12` |

Rejected:

- Disabling `attribute_ruler` removes noun chunk production in
  `en_core_web_trf` for this pipeline.
- The apparent speedup is invalid because object/action/relation extraction
  collapses; all 12 Stage 6 count TSVs differ from the baseline.
- Do not disable `attribute_ruler` for this pipeline.

Incidental bug found and fixed during the audit:

- Stage 6 memory backend wrote count TSV headers by inferring value columns
  from actual rows.
- Empty shard count tables could therefore omit required value fields, e.g.
  empty `relation_component_counts.tsv` missing
  `relation/component_index/component`, causing sharded merge schema mismatch.
- Fixed by writing memory backend count table headers from
  `COUNT_TABLE_SPECS` even when the table has zero rows.
- Added coverage in `tests/test_stage6_export_counts.py` for full headers on
  empty `relation_component_counts.tsv`.

Test-runner stability fix:

- `run_tests.ps1`, `run_pytest_with_timeout.py`,
  `run_unittest_with_timeout.py`, and `diagnose_test_runtime.py` now default
  test temp roots to repo-local `outputs/.test_tmp/...`.
- `run_tests.ps1` also creates a unique `GPIC_TEST_TEMP_ROOT` per invocation.
- This avoids CreatorTemp permission/lock noise during incident verification.

## 2026-07-21: Stage 6 Raw-Line Count Merge

Purpose:

- Reduce Stage 6 merge overhead after sharded count-table export, especially
  `object_cooccurrence_pair_counts.tsv`.
- Preserve the exact Stage 6 TSV outputs byte-for-byte against the current 50K
  baseline.

Implementation:

- `scripts/run_stage456_sharded.py` now avoids full TSV parse/serialize cycles
  in the canonical-header partition writer and final k-way merge.
- Partition writing reads each canonical TSV data row as a raw line and parses
  only `count_key`.
- Final k-way merge reads sorted partition rows as raw lines and parses only
  the sort fields needed for ordering.
- CSV parsing remains as a fallback for rows that require it.

Validation:

- Local targeted tests passed:
  `run_tests.ps1 --pytest tests/test_run_mlxp_cp.py tests/test_run_mlxp_bash.py tests/test_stage456_sharded.py tests/test_stage6_export_counts.py`
  with `28 passed`.
- Remote MLXP targeted tests passed:
  `tests/test_stage456_sharded.py` and `tests/test_stage6_export_counts.py`
  with `18 passed`.
- Remote run:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage6_raw_line_merge_50k_20260721T053535Z`
- Baseline:
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_fast_caption_id_stage6_crc_50k_20260720T124941Z`
- Stage 6 TSV byte comparison:
  `mismatch_count=0`
- Stage 6 count integrity:
  `ok`
- Stage 6 fact total:
  `8,880,202` in both runs.

50K timing:

| Metric | Baseline | Raw-line merge | Delta | Speedup |
| --- | ---: | ---: | ---: | ---: |
| total_pipeline | `102.308875s` | `84.270709s` | `-18.038166s` | `1.21x` |
| stage456_sharded | `47.717079s` | `29.662841s` | `-18.054238s` | `1.61x` |
| merge_stage6_counts | `30.824614s` | `13.638709s` | `-17.185905s` | `2.26x` |
| object cooccurrence merge | `28.535843s` | `11.396035s` | `-17.139808s` | `2.50x` |

Decision:

- Accepted as result-preserving at 50K scale.
- The next benchmark should treat this run as the Stage 6 merge baseline before
  testing additional count-path optimizations.

## 2026-07-21: Stage 3 Worker Count Sweep

Purpose:

- Check whether the auto resource plan is over-parallelizing Stage 3 on the
  2x H200 MLXP pod.
- Compare lower Stage 3 sentence shard/job counts against the accepted raw-line
  Stage 6 merge baseline.

Baseline:

- `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage6_raw_line_merge_50k_20260721T053535Z`
- Auto plan:
  - `stage3_sentence_shards=16`
  - `stage3_jobs=17`
  - `stage3_gpu_devices=0,1`

Sweep:

- Sweep root:
  `/mnt/nvme/gpic_speed_tests/stage3_worker_sweep_50k_20260721T071045Z`
- Every candidate used:
  - 50K GPIC-Nano front captions
  - fixed current inventory bundle
  - `--require-gpu`
  - `--batch-size 192`
  - `--stage6-count-backend memory`
  - `--stage6-facts-output-mode discard`
  - Stage 6 TSV byte comparison against the baseline

Results:

| Config | sentence shards | jobs | Stage 6 mismatch | total pipeline | Stage 3 | Stage 4/5/6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline auto | `16` | `17` | `0` | `84.270709s` | `51.223274s` | `29.662841s` |
| s04_j05 | `4` | `5` | `0` | `102.628146s` | `68.916123s` | `30.213157s` |
| s08_j09 | `8` | `9` | `0` | `90.016457s` | `55.610176s` | `30.954686s` |
| s12_j13 | `12` | `13` | `0` | `87.503503s` | `53.617591s` | `30.508612s` |

Decision:

- Rejected lowering Stage 3 worker count.
- The current auto plan, 8 sentence workers per H200 (`16` sentence shards plus
  one tag-list shard), is still the fastest tested 50K configuration.
- Do not lower `stage3_sentence_shards` on this hardware for throughput.

Incident and guard:

- Initial sweep attempt failed before launching the pipeline because the script
  redirected stdout/stderr into `"$run_dir"` before creating that directory.
- The opened incident was cleared only after recording root cause, guard, and
  verification evidence.
- The sweep script now creates each per-config `run_dir` and writes
  `write_preflight.txt` before any pipeline redirection.

## 2026-07-21: Stage 3 Profiling From Accepted 50K Baseline

Purpose:

- Break down the accepted raw-line Stage 6 merge baseline to identify the next
  useful optimization target.
- Avoid a new run when existing worker summaries already contain profiling
  fields.

Profiled run:

- `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage6_raw_line_merge_50k_20260721T053535Z`
- Pipeline Stage 3 wall time:
  `51.223274s`
- Stage 3 sharded internal total:
  `50.912454s`
- Stage 3 run-shards wall:
  `48.575327s`

Aggregated worker timing:

| Timing bucket | Sum across workers | Max single worker | Notes |
| --- | ---: | ---: | --- |
| `model_load` | `74.651460s` | `4.725552s` | Concurrent across workers; adds about one model-load slice to wall time |
| `annotation_and_write` | `616.171983s` | `38.849861s` | Concurrent worker work |
| `stage2_prepare` | `33.889698s` | `2.486729s` | Stage 2 protection/token preparation |
| `spacy_pipe` | `538.779622s` | `35.106509s` | Dominant sentence-worker cost |
| `record_build_json_write_overhead` | `43.502663s` | `20.976023s` | Sentence record/write is small; tag-list is currently total-only |

Shape-specific timing:

- Sentence rows:
  - `annotation_and_write`: `595.195960s`
  - `spacy_pipe`: `538.779622s`
  - `stage2_prepare`: `33.889698s`
  - `record_build_json_write_overhead`: `22.526640s`
- Tag-list rows:
  - one tag-list worker, `494` rows
  - total worker time: `25.595914s`
  - not on the Stage 3 wall-time critical path because sentence workers run
    longer.

Interpretation:

- The next bottleneck is the spaCy transformer/parser pass itself
  (`spacy_pipe`), not JSON serialization or Stage 3 record construction.
- Record/write optimization would at best target about `1.4s` on the slowest
  sentence worker in this 50K run, so it is not the next high-leverage target.
- Stage 3 wall time is mainly:
  - concurrent model load, about `4.7s`
  - slowest sentence worker `spacy_pipe`, about `35.1s`
  - slowest sentence worker Stage2/record overhead, about `3.9s`
  - remaining subprocess/scheduling/shard orchestration overhead.

Next candidates:

- If optimizing Stage 3 further, focus on spaCy/GPU execution:
  - batch-size sweep around the accepted worker plan
  - spaCy pipe/multiprocessing alternatives
  - persistent worker/model reuse only if the pipeline can preserve exact output
    and avoid introducing lifecycle complexity.
- Do not spend time first on Stage 3 JSON writer optimization; current profiling
  says it is not the dominant path.

## 2026-07-21: Stage 3 Batch-Size Sweep

Purpose:

- Test whether changing spaCy `nlp.pipe` batch size improves Stage 3 throughput
  while keeping the accepted worker/GPU plan.
- Use the accepted raw-line Stage 6 merge run as the baseline.

Baseline:

- `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage6_raw_line_merge_50k_20260721T053535Z`
- batch size: `192`
- auto resources:
  - `stage3_sentence_shards=16`
  - `stage3_jobs=17`
  - `stage3_gpu_devices=0,1`

Sweep:

- Sweep root:
  `/mnt/nvme/gpic_speed_tests/stage3_batch_sweep_50k_20260721T072624Z`
- Candidates:
  - `batch_size=64`
  - `batch_size=128`
  - `batch_size=256`
- Each candidate was compared byte-for-byte against the baseline Stage 6 TSVs.

Results:

| Config | Batch size | Stage 6 mismatch | total pipeline | Stage 3 | Stage 4/5/6 |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | `192` | `0` | `84.270709s` | `51.223274s` | `29.662841s` |
| b064 | `64` | `0` | `87.168091s` | `53.390635s` | `30.253223s` |
| b128 | `128` | `0` | `85.941297s` | `52.347763s` | `30.014017s` |
| b256 | `256` | `0` | `84.646849s` | `51.333459s` | `29.865745s` |

Decision:

- Rejected changing the default batch size.
- `batch_size=256` was close but still slower than the accepted `192` baseline.
- `64` and `128` were clearly slower.
- Keep `--batch-size 192` for the current 2x H200 auto-resource plan.

Next implication:

- The simple Stage 3 parameter sweeps tested so far, worker count and batch
  size, did not beat the accepted baseline.
- Further Stage 3 speedup likely requires changing execution structure rather
  than tuning only public knobs, for example model reuse across chunks,
  alternate spaCy execution patterns, or bypassing unneeded transformer outputs
  only if exact Stage 6 TSV output remains byte-identical.

## 2026-07-21: Accepted 1M Fixed-Lexicon Count-Only Baseline

Purpose:

- Measure the current accepted fixed-lexicon Stage 1-6 count-only runtime at
  the full 1M GPIC-Nano scale, instead of extrapolating from 50K.
- Use the accepted 50K configuration without additional experimental changes:
  - auto resource selection
  - 2 H200 GPUs
  - `--batch-size 192`
  - Stage 6 memory count backend
  - Stage 6 facts discarded
  - raw-line Stage 6 count merge code

Run:

- `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage6_raw_line_1m_20260721T074208Z`
- Input:
  `/root/work/gpic_baselines/inputs/gpic_nano_front1000000.jsonl.gz`
- Inventory bundle:
  `resources/gpic_inventory/current/inventory_bundle.json`
- Preposition MWE lexicon:
  `resources/lexicons/preposition_mwes.tsv`

Resource plan:

- Detected CPU quota: `28` cores
- Detected memory limit: `480 GiB`
- Detected GPUs: `2 x NVIDIA H200`
- Auto-selected:
  - `stage3_gpu_devices=0,1`
  - `stage3_sentence_shards=16`
  - `stage3_tag_shards=1`
  - `stage3_jobs=17`
  - `stage456_shards=28`
  - `stage456_jobs=28`
  - `stage456_merge_jobs=28`

Timing:

| Metric | Time |
| --- | ---: |
| total pipeline | `1229.436503s` |
| total pipeline | `20m 29.4s` |
| stage1 mixed caption rows | `22.595822s` |
| stage1 records | `35.433092s` |
| Stage 3 sharded | `842.928653s` |
| Stage 4/5/6 sharded | `327.548215s` |
| Stage 6 count merge | `99.368260s` |

Stage 6:

- fact total: `178,529,467`
- count integrity: `ok`
- Byte-level comparison against the prior validated 1M Stage 6 baseline
  `/mnt/nvme/gpic_speed_tests/mixed_auto_resources_stage3_fast_caption_id_stage6_crc_1m_20260720T135021Z/stage6`
  reported `12/12` TSV files identical and `mismatch_count=0`.
- object co-occurrence merge: `83.916751s`
  - partition write: `47.299937s`
  - partition merge: `16.945985s`
  - final k-way merge: `19.476338s`
- next largest table merges:
  - object-attribute pairs: `15.274274s`
  - relation triples: `14.829559s`
  - agent/patient pairs: `12.912190s`

Interpretation:

- The accepted 1M fixed-lexicon count-only runtime is about `20.5` minutes on
  the current 2x H200 / 28-core MLXP pod.
- Stage 3 is still the dominant cost at 1M scale.
- Stage 6 merge remains visible but is no longer the dominant full-pipeline
  cost after raw-line merge optimization.
