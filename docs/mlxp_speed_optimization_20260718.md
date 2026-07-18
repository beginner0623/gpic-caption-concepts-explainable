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
