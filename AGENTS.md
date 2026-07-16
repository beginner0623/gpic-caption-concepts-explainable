# AGENTS.md

This repository is a fresh explainable baseline for GPIC caption-to-concept extraction.

The priority is explainability, not maximum recall.

## Required Reading

Before creating or editing any code, lexicon, report, or documentation, read:

1. `AGENTS.md`
2. `docs/rules_v1.md`
3. `docs/answer_protocol.md`

If the requested change conflicts with `docs/rules_v1.md`, stop and explain the conflict before editing.

## Current Project State

This project has the explainable v1 pipeline implemented through Stage 6.

Future work must still follow the Rule Gate before adding or changing rules.

## Active Workspace Guard

The active local project root after the OneDrive/junction migration is:

`C:\Users\rlath\Documents\Codex\gpic-caption-concepts-explainable`

This Codex conversation may still have a different default workspace. Before
running repository commands from a long-lived or migrated conversation, first
establish the active repo root:

- use the absolute `workdir` above for shell commands
- do not rely on the conversation default cwd
- if the current cwd is not the active root above, switch immediately to the
  active root for repo inspection and command execution
- if a command says `src`, `docs`, or expected pipeline files are missing, do
  not infer repo state from that cwd; treat it as the wrong workspace and retry
  from the active root above
- run `scripts\assert_active_workspace.ps1` before long-running scripts,
  generated-artifact commands, benchmarks, or tests whose result will guide the
  next decision
- if the guard fails, stop and fix the working directory before continuing

Do not treat "I will remember the new path" as sufficient. The path must be
verified by command evidence when the result matters.

## Remote Pod Command Guard

Do not run MLXP/Kubernetes pod commands by embedding long command strings in
nested local shells such as:

- `wsl.exe bash -lc "kubectl ... -- bash -lc '...$(...)...; ...'"`
- PowerShell strings that contain shell substitutions, semicolons, redirection,
  heredocs, or quoting that should be interpreted only inside the pod

This failure mode can silently execute part of the command on the local WSL or
PowerShell side instead of inside the pod, which can create local artifacts or
clone the repository in the wrong place.

Preferred remote execution patterns:

- use direct argv commands:
  `kubectl -n <ns> exec <pod> -- git -C /root/work/repo status --short`
- for multi-step remote work, create a checked script file with LF line endings
  and no BOM, copy it to the pod, then execute that script explicitly
- if stdin script execution is used, first verify no BOM/CRLF issue with a
  bounded `pwd`, `whoami`, and `hostname` probe

Before trusting a remote command result, verify the execution context with
command evidence from inside the pod:

- `pwd`
- `hostname`
- `whoami`
- expected repo branch and commit, using `git -C <remote_repo>`

If any command unexpectedly reports a Windows path, the conversation default
workspace, or a local WSL path while the intended target was MLXP, stop
immediately. Do not continue the main pipeline until the wrong local artifact
has been identified and either removed with an absolute-path safety check or
explicitly quarantined.

## Long-Running Process Guard

Long-running pipeline jobs must not be launched with ad hoc PowerShell
`Start-Process`, `cmd.exe /c start`, `start /b`, visible helper windows, or
hand-built shell backgrounding. Those launch modes have caused stale launcher
processes and hidden non-started jobs.

Use only these supported paths:

- foreground bounded execution:
  `scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds N <script> ...`
- detached/background execution:
  `scripts\run_python.ps1 scripts\run_background_job.py start --pid-file <json> --stdout <log> --stderr <log> --cwd <repo> -- <command> ...`
- detached/background adoption for an already-running valid job:
  `scripts\run_python.ps1 scripts\run_background_job.py adopt --pid <pid> --pid-file <json> --cwd <repo> ...`
- detached/background status:
  `scripts\run_python.ps1 scripts\run_background_job.py status --pid-file <json> --progress-output <progress.json>`
- detached/background bounded watch:
  `scripts\run_python.ps1 scripts\run_background_job.py watch --pid-file <json> --progress-output <progress.json> --expect-output <path> --max-seconds N`

When a background job is started, immediately verify all of the following:

- the pid file exists and reports `running: true`
- the expected child process is visible, not just a launcher process
- stdout/stderr log files are being written or intentionally empty
- the expected output artifact is either absent because the job is still in
  progress, or present with a fresh timestamp after completion
- long inventory builders that support progress artifacts are writing a fresh
  `*_progress.json` file with `status`, `phase`, processed counts, and
  `updated_at_utc`
- large Stage 3.5 inventory scans must be launched through
  `run_stage35_inventory_workflow.py` or with the relevant object/attribute/action
  inventory builder plus `--checkpoint-output <json> --resume-checkpoint`; this
  is one checkpoint JSON file per builder that is updated by atomic replace, not
  a pile of per-interval files. A progress JSON alone is not enough because it
  cannot resume after power loss, network loss, or a manually requested stop.

While a long job is running in the current Codex turn, do not merely say that a
progress file exists. Actively poll the available progress artifact or bounded
watch output and report concise user-facing updates at least every 30-60
seconds. Each update should include the current `status`, `phase`, key processed
counts such as `caption_total` or `inventory_rows_so_far`, and whether a manual
blocker/output artifact has appeared. If the progress artifact is missing,
stale, unreadable, or no longer changing while the process is still running,
inspect the process state before continuing.

Before sending a final answer or otherwise ending a turn after any background
job was started, adopted, or may still be active, run:

`scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 60 -- scripts\list_active_background_jobs.py --root outputs --fail-if-running`

If this command reports an active job, do not send a final answer. Continue
polling the job, or explicitly stop/quarantine the job only when it is stale or
wrong. This check is the durable pre-final guard; do not rely on memory that a
job was "probably done."

If a background launcher is visible but no expected child process exists, stop
the launcher and treat the job as not started.

For million-scale Stage 3.5 runs, do not use wall-clock timeout as a progress
health check. A healthy progress-producing scan must not be killed only because
it crossed an arbitrary elapsed-time boundary. Use progress heartbeat monitoring
and checkpoint/resume; set child-script wall-clock timeout to `0` unless a
specific short diagnostic command needs a bounded timeout.

The current formal Stage 4/5/6 implementation is monolithic: Stage 4 writes
after collecting raw mentions/edges, Stage 5 reads raw mentions/edges into
memory, and Stage 6 reads canonical mentions/edges and builds facts/count
tables in memory. It has been usable for smaller report runs, but it is not the
safe path for million-scale caption export. Do not run 1M+ captions through the
monolithic mixed pipeline unless a chunked/streaming Stage 4/5/6 runner has been
implemented and verified. `run_mixed_caption_pipeline.py` has a fail-fast guard
for this; do not disable it except for a deliberately bounded diagnostic on a
machine sized for the run.

Do not wrap formal Stage 4/5/6 scripts in `run_script_with_timeout.py` for
production-scale work. That wrapper uses a hard `os._exit` kill and Stage 4/5/6
currently do not have checkpoint/resume. The wrapper refuses
`run_mixed_caption_pipeline.py`, `run_stage4_extract_raw.py`,
`run_stage5_canonicalize.py`, and `run_stage6_export_counts.py` by default; use
`--allow-stage456-timeout` only for a deliberately bounded smoke diagnostic.

## Incident Response Guard

When the user points out a repeated mistake, a violated project rule, a stuck
process, a missing timeout, a wrong workspace, or an untracked background job,
do not resume the main pipeline first.

Follow this order:

1. Inspect the current external state with command evidence.
2. Stop or quarantine only the stale/incorrect process or artifact if one exists.
3. Identify the concrete failure path, not just the symptom.
4. Add or update a durable guard in code, wrapper scripts, or AGENTS.md so the
   same failure path is harder to repeat.
5. Verify the guard with a bounded command.
6. Only then resume the main pipeline step.

Do not answer with only an apology, plan, or explanation when a durable guard is
possible. If no durable guard is possible, say exactly why and record the manual
check that must happen before resuming.

## Scope Boundary

Only the pipeline in `docs/rules_v1.md` is allowed:

1. caption shape judgment
2. spaCy preprocessing
3. spaCy linguistic annotation
3.5. GPIC observed object inventory preparation
4. raw concept extraction
5. canonicalization
6. count export

Stage 3.5 is an explicit offline preparation step between Stage 3 and Stage 4,
not a hidden extraction or repair stage.

Do not add stages, hidden repairs, fallback chains, or extra lexicon families unless the user explicitly approves an update to `docs/rules_v1.md`.

## Rule Gate

Every extraction or transformation rule must be written in `docs/rules_v1.md` before implementation.

Each rule must state:

- rule id
- stage
- input
- output
- tool
- tool type
- rule type
- count impact
- known limitation

If a rule cannot be explained in this format, do not implement it.

### Rule Impact Review Gate

Do not treat rule impact review as conversation memory.

Before adding or changing any rule or lexicon that can affect extraction,
canonicalization, or counts, record a review in `docs/rule_change_review_log_v1.md`.

Each review must state:

- proposed rule or lexicon change
- rule generality classification:
  - general rule
  - source-specific evidence rule
  - explicit user-approved manual decision
  - one-off patch / rescue mapping
- target stage and rule id
- existing rules affected
- expected count-table impact
- false positive risk
- false negative risk
- reversibility, including source columns, rule ids, or metadata
- verification plan
- decision status

Do not implement the change until the review is written and the user approves
the decision.

Before editing code, classify the proposed change. If it is a one-off patch,
dataset-label rescue mapping, or semantic alias made to save a single case, do
not implement it as an automatic rule. Leave the case unresolved, ambiguous, or
rejected unless the user explicitly approves the exact manual decision.

### Lexicon Candidate Gate

Do not add semantic aliases, label-specific rescue mappings, or one-off manual
lookups while building source-label candidates.

Allowed automatic lookup recovery is limited to documented lexical/formal
normalization, such as:

- case normalization
- whitespace normalization
- hyphen, underscore, and space separator variants
- joined separator variants
- WordNet/OEWN Morphy results

Forbidden unless the user explicitly approves the exact label decision:

- semantic aliasing, such as `potted plant -> pot plant`
- head fallback, such as `sports ball -> ball`
- dataset-label rescue mappings for a single failed label
- manual query replacement hidden inside candidate-generation code

If a source label cannot be resolved by the approved automatic lookup rules,
leave it `unresolved`. Synset selection is for choosing one representative noun
sense for the source object label, not for verifying the actual image object
sense. If a label appears not to be a standalone object noun, leave that as
source-label evidence or an unresolved/ambiguous candidate unless the user
explicitly approves a manual decision.

Manual decisions may select or reject a synset only after explicit user
approval. They must not silently change the lookup query used to justify the
row.

Once the user provides an explicit manual decision TSV or exact row decision,
that decision is authoritative for the pipeline even if a later semantic audit
would have preferred another synset. Treat semantic audit findings as advisory
notes only. Do not reopen, override, or block a user-approved manual decision
unless the user explicitly asks to revise that row.

## Allowed In V1

Allowed rule families are only:

- caption shape judgment: sentence vs tag-list
- spaCy tokenization
- raw quote span merge
- plain hyphen word merge
- spaCy tagger
- spaCy dependency parser
- spaCy attribute ruler
- spaCy lemmatizer
- spaCy noun chunks
- GPIC observed object span inventory built from Stage 3 GPIC records
- noun chunk selected span to object through the GPIC observed inventory
- noun chunk modifier to attribute or quantity
- VERB token to action
- `nsubj` child to agent
- `obj` or `dobj` child to patient
- ADP/preposition plus direct `pobj` to relation
- reviewed preposition MWE lexicon span plus final direct `pobj` to relation
- preposition MWE source/target candidate preservation from direct
  object-mapped dependency evidence, including missing-endpoint ambiguous
  occurrence audit rows
- object synonym canonicalization
- attribute synonym canonicalization
- attribute type taxonomy only as an offline audit artifact, not active Stage 5/6 output
- quantity raw-preserving canonicalization
- action synonym canonicalization
- action type mapping
- object parent concept mapping
- relation raw-preserving policy for single ADP relations
- relation MWE label preservation and relation component count export from
  documented Stage 4 preposition MWE metadata
- flat count export

External source-label inventories such as COCO, LVIS, Objects365, OpenImages,
Visual Genome, V3Det, or ImageNet are not active runtime inputs for the GPIC
caption pipeline unless `docs/rules_v1.md` is explicitly updated. Treat those
files as historical probes or offline evidence only.

## Forbidden In V1

Do not implement these in v1:

- pronoun resolution
- generic anaphora resolution
- `one`, `another`, `others`, `both` instance splitting
- passive voice normalization
- inherited agent repair
- skipped reference role recovery
- self-edge repair
- semantic PP source disambiguation
- with-absolute recovery
- scene context fallback rules
- undocumented relation MWE repair or semantic relation source/target recovery
- phrasal action collapse
- broad hidden hardcoded word lists inside Python code
- GPIC-error-specific patch rules
- any new linguistic interpretation during count export

## Implementation Rules

When implementation begins:

- keep functions small and single-purpose
- keep rule ids visible in output rows
- store lexicons as TSV files under `resources/lexicons`
- do not hide policy inside code comments
- do not copy logic from the previous prototype
- do not add a dependency without documenting why it is needed
- do not change generated reports by hand

## Communication Rules

When explaining this repository:

- use the six v1 stage numbers from `docs/rules_v1.md`
- distinguish implemented behavior from proposed behavior
- say "not implemented" when a feature is absent
- say "excluded by v1 design" when a feature is intentionally omitted
- do not describe this as high-recall

Use this description:

> an explainable caption-to-concept baseline with documented limitations

## Repeated Benchmark Rules

Do not treat repeated benchmark requirements as conversation memory.

If the user says a benchmark condition must be checked "from now on" or "for
future experiments", encode it in one of these durable places before relying on
it:

- the benchmark script summary output
- this `AGENTS.md`
- `docs/answer_protocol.md`
- a benchmark-specific document under `docs/`

For GPU benchmarks, record hardware/runtime metadata in the benchmark summary
when `nvidia-smi` is available:

- GPU name
- driver version
- CUDA version if reported by `nvidia-smi`
- observed power limit in watts
- observed power draw in watts
- GPU pstate

Do not say "I will check it manually next time" as a substitute for durable
benchmark instrumentation or documentation.

For benchmark answers, do not fix reasoning mistakes by adding more checklist
rules. Separate reporting from analysis. If a causal explanation is given, first
use the analysis unit built for the benchmark; in this project that means the
stage-level timing fields. If that analysis has not been done, report the
measurement and say the cause is not established.

## Durable Process Judgment Rules

Do not treat newly discovered process rules as conversation-only conclusions.

If a recurring workflow problem is identified during the thread, decide whether
it needs durable documentation before moving on.

Examples include:

- what kinds of experiments must be logged
- what benchmark metadata must be recorded
- what checks must run before reporting results
- what optimization attempts were tried and rejected
- what practices caused confusion and should not be repeated

If the process judgment should affect future work, encode it in one of these
places before relying on it:

- this `AGENTS.md`
- `docs/answer_protocol.md`
- a topic-specific document under `docs/`
- the relevant script output or summary file

Do not merely say "we should do this from now on" when the point is meant to
survive context loss.

### Decision-Impacting Test Records

Do not treat all test runs the same.

Routine unit test passes may be reported in the final answer or commit message
without adding a separate durable log entry.

However, record the test command, result, and interpretation in a durable place
when the test affects a future decision. This includes:

- a test failure and the root cause or fix
- a regression test used to accept a code change
- a benchmark-adjacent test used before or after a speed comparison
- a test used to accept or reject an optimization
- a test result used to decide the next work direction

Use the relevant existing document when possible, such as a benchmark document,
an optimization log, or a topic-specific file under `docs/`.

Do not say "the tests passed, so this is enough" if that test result is being
used as evidence for a durable technical decision but is not recorded anywhere
except the chat.

### Test Runner Safety

Default to `unittest` in this repository.

Use the bounded wrappers:

- `scripts\run_tests.ps1`
- `scripts\diagnose_test_runtime.ps1`
- `scripts\run_unittest_with_timeout.py`
- `scripts\run_pytest_with_timeout.py`

`scripts\run_tests.ps1` runs `unittest` by default. Use pytest only as a
diagnostic exception by passing `--pytest`.

The unittest wrapper runs in-process and uses a hard `os._exit` timeout. This
keeps the default runner simpler than pytest, but it does not by itself bypass
Codex sandbox file-write restrictions.

The pytest wrappers run pytest with a child-process timeout and disable pytest's
cache provider. This avoids hangs from pytest cache finalization in
junction/OneDrive or sandboxed paths.

The wrappers default test temp files to
`C:\Users\Public\Documents\ESTsoft\CreatorTemp\gpic-explainable-link-tests`
when available. If a sandboxed test run fails with `PermissionError`
while writing inside a temp directory, do not infer that the pipeline code is
broken. First verify with the same bounded command outside the sandbox and, when
useful, with a narrow `run_python.ps1 -c` write probe.

Do not run an all-in-one diagnostic group. Run one bounded group at a time.

Do not use `scripts\run_python.ps1 -m unittest` or
`scripts\run_python.ps1 -m pytest` as a validation runner. `run_python.ps1`
only locates the project Python and executes the arguments; it is not the
repository's test timeout boundary. Use `scripts\run_tests.ps1` or the bounded
Python test wrappers instead.

`scripts\run_python.ps1` enforces this rule: it rejects direct interactive
Python, `-m unittest`, `-m pytest`, and direct `.py` script execution except for
the bounded wrapper scripts. Do not bypass that guard.

After any interrupted, hung, or user-aborted test command, do not immediately
rerun a test. First inspect for stale project `python.exe` or PowerShell
processes, stop only the stale processes that belong to the interrupted command,
and record the root cause if it affects future work.

For test temp paths in this repository, avoid `Path.resolve()` when deriving a
repo-local temp directory. This repo can be opened through a junction/link, and
`resolve()` may silently switch from the logical Codex path to the OneDrive
target path. Prefer an explicit temp root or a non-resolving logical repo path.
If a temp helper falls back to a shared Public temp path after a write failure,
do not keep rerunning the test; inspect the temp path decision first.

### Filesystem Write And Escalation Policy

Do not treat filesystem permissions as conversation memory.

Use `apply_patch` for manual edits to repository files, including code,
documentation, small TSV lexicons, and small configuration files.

Use Python or command-line scripts for generated artifacts only when the file is
better produced mechanically, such as large TSV/JSON/HTML/Markdown outputs,
downloaded resources, or benchmark reports.

For generated artifacts:

1. Before running a generated-artifact command, check whether the command writes
   inside the current sandbox writable roots.
   - If the target repository or output directory is outside the writable roots,
     do not run a doomed sandbox attempt first.
   - Run the same narrow bounded command with `require_escalated` from the
     beginning.
   - State that this is required because the active repo/output path is outside
     the sandbox writable roots, not because the script or pipeline logic is
     broken.
2. Run the script normally first only when it is expected to write inside the
   current writable workspace.
3. Generated TSV/CSV writers should write to a same-directory temporary file and
   then replace the final path atomically. Do not rewrite final TSV/CSV paths
   directly with `open("w")` when the output is a generated artifact.
4. Long-running generated-artifact Python scripts must be executed through
   `scripts\run_script_with_timeout.py`, not by calling the target script
   directly through `scripts\run_python.ps1`. The runner executes the target
   script in-process and uses a hard `os._exit` timeout so a timed-out script
   does not leave a Python child process behind.
5. If it fails with a sandbox, junction, OneDrive, network, cache, or
   `PermissionError` problem, rerun the same narrow command with
   `require_escalated`.
6. Do not describe `require_escalated` as a fix for the permission problem. It is
   an approved outside-sandbox execution for that command.
7. Keep generated output paths explicit. Avoid relying on `Path.resolve()` when a
   repository path may be a junction to OneDrive.
8. Keep temp and cache paths explicit when a script writes temporary files.
9. Record durable decisions about generated artifacts, permission failures, or
   escalation use in the relevant log or document when they affect future work.

Do not use shell write tricks such as `echo > file`, `Set-Content`, or Python
one-off writes for manual repository edits when `apply_patch` can express the
change.

### Generated Report Summary Sync

Do not treat Markdown report summaries as self-validating.

This is not a requirement to scan every old report on every task. Apply it when
a report is being edited, cited as current evidence, or naturally discovered to
be stale during the current work.

When a generated TSV/CSV/JSON source artifact changes, any Markdown document
that is being updated or cited as its current summary must be checked against
the source artifact before reporting or editing.

For source-label candidate reports:

- use the current TSV columns as the source of truth, such as
  `selection_status`, `selected_oewn_synset`, `manual_decision`,
  `synset_selection_tag`, and `mwe_candidate_status`
- do not infer current `selected`, `ambiguous`, `rejected`, or `unresolved`
  counts from an older Markdown summary
- if a report was generated from an older inventory snapshot, mark it as
  historical and state the snapshot scope
- do not call a snapshot report "current" after new source datasets have been
  added unless it has been regenerated from the new source artifact
- historical decision logs may keep their original numbers, but a current probe
  report that is touched or cited must either match the latest source artifact
  or clearly state that it is a historical snapshot

When updating only the explanatory Markdown around a generated artifact, use
`apply_patch`. Do not edit large generated TSV/CSV artifacts by hand.

### Formal Pipeline And Inventory Reuse

Do not treat preview/debug outputs as normal pipeline outputs.

Stage 5/6 outputs are formal caption-to-concept results only when all required
inventory gates for that run have passed. If a command uses a preview or debug
escape hatch, such as `--allow-unresolved-attribute-preview`, the output path,
summary, report, and user-facing answer must call it preview/debug output. Do
not continue from that output as if it were a formal pipeline artifact.

Do not rebuild a GPIC observed inventory in isolation when a resolved prior
inventory for the same concept family exists. The stable prior is
`resources/gpic_inventory/current/inventory_bundle.json`, not an ad hoc
`outputs/...` snapshot.

For production Stage 3.5 inventory expansion:

- always load inventory inputs from the current bundle
- run `scripts/run_stage35_inventory_workflow.py` with `--use-current-inventory`
- do not manually combine `--object-inventory`, `--attribute-prior-inventory`,
  `--action-prior-inventory`, or `--base-lexicon-dir`
- if a completed component must be promoted before the full workflow is
  complete, use `scripts/publish_current_inventory_component.py` so
  `resources/gpic_inventory/current` is updated component-wise
- never call an `outputs/...` TSV "current" unless it has been published into
  `resources/gpic_inventory/current`
- after generation, report how many rows were reused versus newly queued when
  the script exposes those counts

This applies across caption shapes. A tag-list inventory is not a separate
semantic namespace from sentence inventory; the same `span_key`/surface policy
must reuse the same resolved evidence unless the rule document explicitly says
otherwise.

Do not infer that a previous object-inventory workflow automatically carried
over to attributes or actions. Check the actual command arguments before
running the build.

Keep inventory gates phase-specific. If the current phase is synset/manual
resolution, report only unresolved manual/synset rows as blockers. Do not mix
canonical-surface blockers into that report. Run and report the canonical gate
only after the synset/manual gate is clear.

### Encoding Hygiene

Do not trust a mojibake-looking PowerShell display as evidence that a file is
actually corrupted.

For Korean or mixed Korean/English Markdown and TSV files:

1. Prefer Python `Path.read_text(encoding="utf-8", errors="strict")` or another
   explicit UTF-8 reader when verifying file content.
2. Do not use `Get-Content` without `-Encoding UTF8` for Korean text.
3. Do not copy patch context from mojibake terminal output. If patch context is
   needed, obtain it from an explicit UTF-8 read or ASCII-safe `repr()`.
4. If text looks corrupted in command output, verify the file bytes/content with
   UTF-8 strict reading before claiming the file itself is corrupted.
5. Scripts that write Markdown, JSON, CSV, or TSV must specify
   `encoding="utf-8"` and, for CSV/TSV, `newline=""`.
6. PowerShell output is allowed for quick inspection, but it is not sufficient
   evidence for Korean file integrity unless UTF-8 decoding has been verified.

## Karpathy Guidelines

These behavioral guidelines reduce common LLM coding mistakes. They bias toward
caution over speed; for trivial tasks, use judgment.

### 1. Think Before Coding

Do not assume. Do not hide confusion. Surface tradeoffs.

Before implementing:

- state assumptions explicitly
- if uncertain, ask
- if multiple interpretations exist, present them rather than picking silently
- if a simpler approach exists, say so
- push back when warranted
- if something is unclear, stop, name what is confusing, and ask

### 2. Simplicity First

Write the minimum code that solves the problem. Do nothing speculative.

- no features beyond what was asked
- no abstractions for single-use code
- no flexibility or configurability that was not requested
- no error handling for impossible scenarios
- if 200 lines could be 50, rewrite it
- ask whether a senior engineer would call the solution overcomplicated; if yes,
  simplify it

### 3. Surgical Changes

Touch only what is necessary. Clean up only the mess created by the current
change.

When editing existing code:

- do not improve adjacent code, comments, or formatting
- do not refactor things that are not broken
- match existing style, even if a different style would be preferable
- if unrelated dead code is noticed, mention it rather than deleting it

When the current change creates orphans:

- remove imports, variables, or functions made unused by the current change
- do not remove pre-existing dead code unless asked

Every changed line must trace directly to the user's request.

### 4. Goal-Driven Execution

Define success criteria and loop until verified.

Transform tasks into verifiable goals:

- "Add validation" means write tests for invalid inputs, then make them pass.
- "Fix the bug" means write a test that reproduces it, then make it pass.
- "Refactor X" means ensure tests pass before and after.

For multi-step tasks, state a brief plan:

1. Step -> verify: check.
2. Step -> verify: check.
3. Step -> verify: check.

Strong success criteria allow independent progress. Weak criteria, such as
"make it work", require clarification.

## Evidence-Gated Answer Protocol

Follow `docs/answer_protocol.md` for any non-trivial explanation, especially
claims about current code behavior, runtime environment, GPU/CPU status,
benchmark speed, rule behavior, or generated outputs.

Do not present an inference as a verified fact.

When making a claim about the current repository or environment, separate:

- verified observation
- code/file evidence
- inference
- unknown or unchecked state

For code behavior:

- inspect the relevant file before explaining the implemented behavior
- cite the file path or function name in the answer
- say "not checked in this turn" if the file was not inspected

For runtime and benchmark claims:

- state the exact command or output file used as evidence
- state model, input size, batch size, stage range, intermediate-file policy,
  GPU/CPU status, and environment scope
- never infer hardware capability from one library's runtime status
- separate physical GPU availability, PyTorch CUDA availability, spaCy GPU/CuPy
  availability, and the actual device used in the latest run

Forbidden unless independently verified in the current turn:

- "this machine cannot use GPU"
- "only CPU is available"
- "the code currently does X" without reading the relevant code
- "the benchmark speed is X" without the command, input size, and stage range
