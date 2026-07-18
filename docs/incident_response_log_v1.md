# Incident Response Log V1

This log records repeated failure paths and the durable guard added before the
pipeline resumed.

## 2026-07-17: Incident Prevention Existed Only As A Written Promise

### What Failed

Repeated failures had documentation in `AGENTS.md`, but official commands could
still be rerun immediately because no executable state gate existed. The first
explanation of the proposed gate was also phrased as though automatic incident
creation and blocking were already implemented when they were not.

During implementation, one oversized multi-file patch stalled and a targeted
test command incorrectly used dotted `tests.test_*` names even though this
repository's `tests` directory is not a Python package.

### Why It Happened

The incident process depended on conversation memory and written instructions.
There was no repository state that official entrypoints were required to check,
no surviving running marker for OOM/hard termination, and no verified-clear
operation. The patch and test-command mistakes also came from assuming command
shape instead of checking current file context and runner syntax first.

### Durable Guard

- Added `scripts/incident_gate.py` with repository-fixed state in
  `.pipeline_state/`.
- Official Stage 1-6, Stage 3.5, mixed pipeline, inventory publish, timeout,
  MLXP, and password SSH/SCP entrypoints now use `guarded_entrypoint`.
- Detached jobs are launched through `incident_gate.py run`, so the detached
  child owns the running marker and records its own nonzero exit.
- A hard timeout records the incident before `os._exit`; an OOM or other
  uncatchable termination leaves `running.json`, which the next official run
  promotes to an incident.
- An open incident blocks official execution. Clearing requires root cause,
  guard added, verification evidence, and a successful verification command
  when supplied. Resolved incidents append to one history JSONL.
- `run_tests.ps1` now rejects invalid dotted `tests.test_*` unittest arguments
  when `tests/__init__.py` is absent and points to pytest paths or discovery.
- Large manual patches are split after reading exact current file context;
  stalled patch calls are terminated and their partial diff is inspected before
  further editing.

### Verification

- `58` affected regression tests passed after entrypoint integration.
- `15` focused incident/background/timeout tests passed, including a real
  one-second hard timeout that exited through `os._exit(124)` and still wrote an
  incident.
- An isolated CLI smoke test recorded child `returncode=7`, blocked the next
  successful command with `IncidentOpenError`, refused execution until review,
  then allowed execution only after a successful verification command cleared
  the incident.
- The real repository state remained clear throughout the isolated smoke test:
  `.pipeline_state/incident.json` and `.pipeline_state/running.json` were both
  absent.

## 2026-07-17: Stage6 TSV Report Lost Full Caption Drill-Down

### What Failed

The 1M interactive report was built from Stage 6 aggregate TSVs and reused
`example_caption_ids` as `_caption_ids`. Row caption panels therefore showed at
most five captions even when `caption_count` was much larger.

### Why It Happened

The Stage 6 TSV report path optimized memory by switching from Stage 5
mention/edge records to aggregate count TSVs. The implementation accepted the
loss of full row-to-caption evidence as a report note instead of treating it as
a feature regression. There was no validation that row-caption drill-down
matched `caption_count`.

### Durable Guard

- `scripts/build_report_caption_index_from_facts.py` streams Stage 6
  `facts.jsonl` and attaches a `report_caption_index` table to `report.db`.
- `scripts/build_interactive_count_report.py` now reads `report_caption_index`
  first and falls back to `_caption_ids` only when the index is absent.
- `scripts/validate_interactive_report_db.py` can require the caption index and
  compare top rows' `caption_count` against indexed caption totals.

### Verification

- Local synthetic DB check: a row with two stored `_caption_ids` was indexed
  from three facts and returned all three caption ids.
- MLXP smoke check on 1M schema: 200,000 facts produced 35,792 indexed
  row-caption entries against the actual report DB schema.
- Production rebuild must run:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 300 -- scripts\run_mlxp_bash.py <script.sh>
```

where `<script.sh>` calls:

```bash
python3 scripts/validate_interactive_report_db.py \
  --report-db "$out/report.db" \
  --summary-json "$out/summary.json" \
  --require-caption-index \
  --check-top-caption-counts 3 \
  --min-patient-action-agent-triples 1
```

## 2026-07-17: MLXP Inline Shell Quoting And BOM Failures

### What Failed

Several MLXP commands were sent as nested PowerShell/Bash inline strings. The
commands failed with broken quotes or a UTF BOM before `set`, and one failed
script still created a partial output directory.

### Why It Happened

The execution path relied on ad hoc nested shell strings:

- PowerShell string interpolation
- WSL argument parsing
- `kubectl exec`
- remote `bash -lc`
- heredocs

This made it easy for quoting, pipes, or BOM bytes to be interpreted at the
wrong layer.

### Durable Guard

- `scripts/run_mlxp_bash.py` sends a local script file as raw bytes to
  `kubectl exec ... bash -s`, strips UTF BOMs, and avoids nested command
  quoting.
- `AGENTS.md` now requires this runner for multi-step MLXP commands from the
  Windows/Codex desktop workspace.

### Verification

The runner successfully executed the MLXP preparation check after the ad hoc
inline command path failed.

## 2026-07-17: Full Caption Index Build Slowdown Was Misdiagnosed

### What Failed

During the 1M full-caption report index build, progress slowed sharply after
roughly 140M Stage 6 fact rows. The first explanation given was that SQLite
primary-key duplicate checks became expensive after crossing 100M indexed rows.
The follow-up explanation then overcorrected and implied that Lustre/DDN sync
I/O was the direct cause.

### Why It Happened

That explanation was too narrow and was stated before checking process wait
state and I/O counters. The slowdown was not proven to be only SQLite B-tree
growth. The later storage comparison probe was also invalid: both the supposed
NVMe and DDN test DBs were written under the same `/mnt/nvme/...` work
directory, so it did not compare different filesystems at all.

The valid evidence from the live run was narrower:

- the process was alive and continued to consume CPU
- `/proc/<pid>/wchan` showed `cl_sync_io_wait` at one sampled moment
- `/proc/<pid>/io` showed continued read/write progress
- the slowdown occurred after the report DB and primary-key index were already
  very large

This proves that I/O wait happened during the slowdown. It does not distinguish
between DDN shared load, Linux dirty-page writeback throttling, SQLite
write-amplification/cache spill, primary-key duplicate-check cost, fact-type
distribution changes, or a combination of those factors.

### Durable Guard

Before diagnosing a long-running MLXP/SQLite slowdown, collect process evidence:

- `ps -o pid,ppid,stat,etime,pcpu,pmem,rss,vsz,cmd -p <pid>`
- `/proc/<pid>/wchan`
- `/proc/<pid>/io` before and after a short interval
- DB file size and mount/disk status

Do not label the bottleneck as CPU, SQLite, B-tree, network filesystem, or lock
contention until those checks have been read.

For storage comparisons, prove the target files are on different filesystems
with `df -hT`, `stat -f`, and resolved absolute paths. If both probes write to
the same mount, record the comparison as invalid.

For report-index performance probes, do not use an empty/small DB to explain
production-scale behavior. A diagnostic probe must reproduce the relevant
shape, including a large existing DB, a large primary-key index, `INSERT OR
IGNORE`, comparable batch size, and the target filesystem. Otherwise it is only
a smoke test.

### Verification

For the active 1M caption-index build, `/proc/<pid>/wchan` reported
`cl_sync_io_wait`, and `/proc/<pid>/io` showed continued write progress over a
10-second interval. The only safe conclusion is:

> I/O wait was observed during the slowdown, but the root cause was not fully
> isolated.

The invalid NVMe/DDN probe result must not be reused as evidence.

## 2026-07-17: Blackwell Password SSH Automation Misdiagnosis

### What Failed

The first Blackwell `ssh`/`scp` automation used a one-off Python PTY wrapper
based on `pty.openpty()` plus `subprocess.Popen`. The SSH password prompt was
not handled as a controlling terminal, so the correct password path failed or
hung. I then discussed password ambiguity before first proving that the
automation path itself was valid.

### Why It Happened

OpenSSH reads passwords from its controlling terminal. A file descriptor from
`pty.openpty()` is not automatically the child process's controlling terminal.
That made the credential failure look like a password problem even though the
actual failure path was the automation wrapper. I also skipped the incident
guard order: identify the concrete failure path and add a durable guard before
continuing the main transfer.

### Durable Guard

- Added `scripts/run_password_ssh_pty.py`, a reusable Linux/WSL-only helper
  that uses `pty.fork()` so the child SSH/SCP process has a real controlling
  terminal.
- The helper reads the password from an environment variable and does not
  hardcode credentials.
- `AGENTS.md` now requires this helper for password-based SSH/SCP automation
  from the Windows/Codex desktop workspace.
- Multi-step Blackwell commands must be written as a local `.sh` file, uploaded
  with SCP through the helper, and executed with SSH through the helper. Do not
  place long remote `bash -lc` scripts inside PowerShell strings.
- Before a large transfer, run a bounded remote `echo ok` probe through the
  same helper. Do not infer that a password is wrong until the
  controlling-terminal path or a direct interactive terminal has been tested.

### Verification

The `pty.fork()` path successfully ran a bounded Blackwell probe:

```text
ssh -p 55031 rlathgns3@147.46.219.233 echo ok
...
ok
```

The same controlling-terminal path then completed the 1M full-caption report
package upload to Blackwell with SCP progress reaching `100%` and exit status
`0`.

A later attempted inline remote deploy command failed locally when PowerShell
parsed remote shell syntax (`&&`). This confirmed the need for the uploaded
remote-script guard above.

## 2026-07-17: Successful CLI Help Was Recorded As An Incident

### What Failed

The first verification of the newly supported no-timeout MLXP foreground path
ran `scripts/run_mlxp_bash.py --help`. `argparse` correctly exited with
`SystemExit(0)`, but `PipelineRun.__exit__` treated every exception-shaped exit
as an unhandled failure and opened an incident. The open incident then correctly
blocked the following MLXP runtime probe.

### Why It Happened

Python CLI parsers implement a successful `--help` response with
`SystemExit(0)`. The incident gate distinguished normal function returns from
nonzero return codes, but did not distinguish successful and failed
`SystemExit` codes.

### Durable Guard

- `PipelineRun.__exit__` now removes the running marker without opening an
  incident for `SystemExit(None)` and `SystemExit(0)`.
- Nonzero `SystemExit` still creates a `nonzero_exit` incident.
- Regression tests cover both successful and nonzero `SystemExit` behavior.

### Verification

`scripts/run_tests.ps1 --timeout-seconds 120 discover -s tests -p
test_incident_gate.py` completed 11 tests with `OK`, including the two new
`SystemExit` cases.

## 2026-07-18: MLXP Verification Bypassed The Remote Runner

### What Failed

After the 50K fixed-lexicon baseline completed, a final DDN verification was
attempted with direct local `kubectl cp` and `kubectl exec` commands from the
Windows/Codex desktop shell. The command failed before reaching MLXP:

- the local shell had no active Kubernetes context, so `kubectl` tried
  `localhost:8080`
- the Windows temp path contained a drive-letter colon, so `kubectl cp` parsed
  the local path as a remote path

This was not a pipeline failure. It was a violation of the already documented
MLXP remote command guard.

### Why It Happened

The repository already had `scripts/run_mlxp_bash.py` and `AGENTS.md` required
that runner for multi-step MLXP commands. I skipped that runner during a
post-run verification and recreated the exact class of nested local/remote
execution mistake the guard was meant to avoid.

### Durable Guard

- Treat direct `kubectl cp`/inline `kubectl exec` from the Windows/Codex
  desktop shell as a process violation for this repository unless it is a
  deliberately bounded one-argv diagnostic.
- Use `scripts/run_mlxp_bash.py <script.sh>` for multi-step MLXP checks. It
  streams a local LF/no-BOM shell script to remote `bash -s` and avoids both
  PowerShell quoting and Windows path parsing.
- If the active MLXP pod has expired, do not fall back to direct `kubectl`.
  First update the pod argument or run the check from the user's interactive
  MLXP shell.

### Verification

The repository state after the interruption was checked locally:

```text
## mlxp-stage456-handoff...origin/mlxp-stage456-handoff
8184630 Record MLXP fixed-lexicon baseline
5ba4268 Stabilize MLXP GPU runtime guard
```

The baseline measurements remain recorded in
`docs/mlxp_fixed_lexicon_baseline_20260717.md`; the failed command was only a
redundant remote-storage verification attempt.

## 2026-07-18: New MLXP Pod Lost CUDA Wheel Library Paths

### What Failed

The recreated MLXP pod could see the H200 GPU and `spacy.require_gpu()`
returned true, but loading `en_core_web_trf` failed with:

```text
CuPy failed to load libnvrtc.so.12
```

### Why It Happened

`scripts/setup_mlxp_runtime.sh` exported the NVIDIA wheel library directories
inside the setup process, but that `LD_LIBRARY_PATH` was not persisted into
later MLXP benchmark/probe shells. A fresh pod or shell could therefore import
CuPy far enough for `spacy.require_gpu()` to pass, then fail when the
transformer model needed NVRTC during model load.

### Durable Guard

- `scripts/run_mlxp_bash.py` now prepends the GPIC MLXP runtime guard to remote
  scripts by default.
- The guard discovers `/root/work/gpic-linux-env` NVIDIA wheel `*/lib`
  directories and exports them into `LD_LIBRARY_PATH` before the user script
  runs.
- `--no-runtime-env` is available only for deliberate diagnostics.
- `tests/test_run_mlxp_bash.py` fixes the runner contract so the CUDA library
  path guard remains prepended.

### Verification

The targeted runner test passed:

```text
scripts/run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_run_mlxp_bash.py
Ran 2 tests in 0.043s
OK
```

The same pod probe then loaded the spaCy transformer model successfully:

```text
torch_cuda=True
torch_gpu=NVIDIA H200
cupy=13.6.0
spacy_require_gpu=True
spacy_model_loaded=1
```

## 2026-07-18: MLXP Remote Git Sync Assumed GitHub Credentials

### What Failed

After the recreated MLXP pod probe passed, I attempted to fast-forward the
remote pod repository with `git fetch origin mlxp-stage456-handoff`. The pod
could not read a GitHub username non-interactively:

```text
fatal: could not read Username for 'https://github.com': No such device or address
```

The incident gate correctly opened an incident and blocked the next official
runner invocation.

### Why It Happened

The remote repository update was not required for the next benchmark step: the
new runtime library guard is prepended by the local `run_mlxp_bash.py` before
the remote script runs. I treated remote Git sync as mandatory and tried it
without first proving that the pod had non-interactive GitHub credentials.

### Durable Guard

- `AGENTS.md` now requires a bounded `GIT_TERMINAL_PROMPT=0` GitHub access
  probe before using remote `git fetch`/`pull`/`merge` as part of an MLXP
  workflow.
- If the pod cannot access GitHub non-interactively, benchmark execution must
  not depend on remote Git sync. Use the already verified remote commit when
  sufficient, or use an explicit file/bundle transfer path.

### Verification

The open incident itself is the verification that the guard caught the failed
official run:

```text
summary=Official run exited nonzero: bounded_script_runner
returncode=128
```

The preceding MLXP runtime probe verified that the local runner prologue is
sufficient for the immediate benchmark path even before remote repo sync:

```text
spacy_require_gpu=True
spacy_model_loaded=1
```

## 2026-07-18: Report DB Build Correctly Refused Missing Triple Helper

### What Failed

The first attempt to build a 50K interactive report DB from Stage 6 TSVs failed
because `patient_action_agent_triple_counts.tsv` was not present in the Stage 6
directory.

### Why It Happened

`build_interactive_count_report.py --input-mode stage6-tsv` requires the helper
triple count table so the report does not silently show an empty
patient-action-agent triple view. The Stage 1-6 benchmark produces Stage 6
facts and standard count TSVs, but the helper triple table is a separate
post-processing artifact.

### Durable Guard

No new code guard was needed. The existing report-builder guard did the right
thing: it refused to build a misleading report and printed the required next
command family:

```text
Build it first with scripts/build_patient_action_agent_triples_from_facts.py
using the Stage 6 facts.jsonl.
```

### Verification

The failure happened before writing `report.db`, so no incomplete interactive
report was accepted as valid. The next valid report build must first create
`stage6/patient_action_agent_triple_counts.tsv` from `stage6/facts.jsonl`.

## 2026-07-18: GitHub SSH Deploy-Key Probe Used The Wrong Success Criterion

### What Failed

After creating and registering an MLXP pod deploy key, the verification script
ran `ssh -T git@github.com` inside a guarded MLXP command. GitHub printed a
successful authentication message for the deploy key, but the command exited
nonzero because GitHub does not provide shell access. The incident gate
correctly treated the official remote command as failed.

### Why It Happened

The probe used an interactive SSH authentication check as though exit code `0`
meant success. For GitHub deploy keys, the operation the pipeline actually needs
is repository Git access, not shell access. The correct guarded verification is
therefore `git ls-remote` against the SSH repository URL.

### Durable Guard

- `AGENTS.md` now states that GitHub SSH deploy-key validation must not use
  `ssh -T git@github.com` exit code as the official success criterion.
- Guarded MLXP Git verification should use `git ls-remote` for the intended
  repository URL, or explicitly capture and interpret `ssh -T` output without
  letting the expected nonzero shell-access exit fail the official command.

### Verification

The incident was opened before any pipeline or benchmark mutation resumed. The
next verification must clear this incident only after `git ls-remote` succeeds
from the MLXP pod using the deploy key.

## 2026-07-18: Formal Stage Progress CLI Was Registered Twice

### What Failed

The first 1M Stage 6 memory-backend worker on MLXP exited before processing any
rows. The remote incident recorded an argparse construction failure:

```text
argparse.ArgumentError: argument --progress: conflicting option string: --progress
```

### Why It Happened

The formal Stage 4/5/6 wrappers still registered their own `--progress`
argument after progress reporting had been centralized in
`add_memory_safety_args()`. The existing test only checked that the script text
contained progress-related strings, so it did not actually construct the
argparse parser and could not catch duplicate option registration.

### Durable Guard

- Removed wrapper-local `--progress` registrations from Stage 4, Stage 5, and
  Stage 6. `add_memory_safety_args()` is now the single owner of that CLI
  option.
- Strengthened `tests/test_formal_stage_memory_safety.py` so it imports each
  formal stage runner and calls `parse_args()` with `--progress`. If a duplicate
  option is introduced again, parser construction fails in the test.

### Verification

The targeted memory-safety test must pass locally and on MLXP before the 1M
Stage 6 memory worker is relaunched.
