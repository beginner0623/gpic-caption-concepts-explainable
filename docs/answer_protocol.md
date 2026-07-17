# Evidence-Gated Answer Protocol

This document prevents unsupported claims while working on the v1 explainable
caption-to-concept pipeline.

The main rule is simple:

> Do not turn one observation into a broader conclusion.

## 1. Claim Gate

For non-trivial claims, separate these four parts:

| Field | Meaning |
|---|---|
| Verified | What was directly observed from a command, file, test, or output. |
| Evidence | The command, output file, source file, or function used as evidence. |
| Inference | The interpretation made from the verified observation. |
| Unknown | What was not checked in this turn. |

Allowed wording:

```text
Verified: the latest benchmark summary has gpu_enabled=false.
Evidence: outputs/.../summary.json.
Inference: this run used CPU for spaCy.
Unknown: whether the physical GPU is unavailable.
```

Forbidden wording:

```text
The machine cannot use GPU.
```

unless physical GPU availability, driver/CUDA, PyTorch CUDA, spaCy GPU, and the
latest runtime device were all checked.

## 2. Code Truth Gate

When explaining current code behavior:

1. Read the relevant source file in the current turn.
2. State that the claim is based on the current repo code.
3. Name the file path or function.
4. If the file was not inspected, say "not checked in this turn".

Allowed wording:

```text
Current repo code: run_stage3_annotate() calls iter_stage3_records_from_rows().
Evidence: src/gpic_concepts_v1/stage3_annotate.py.
```

Forbidden wording:

```text
The code probably does...
```

when the user asked what the code currently does.

## 3. Benchmark Evidence Gate

Any speed or device claim must include:

- environment scope
- command or output file
- model
- input count
- stage range
- batch size
- whether intermediate files were written
- PyTorch CUDA status if GPU is discussed
- spaCy GPU/CuPy status if spaCy is discussed
- actual `gpu_enabled` or equivalent value from the run
- GPU metadata from the benchmark summary when available, including
  `gpu_power_limit_w`, `gpu_power_draw_w`, `gpu_pstate`, GPU name, driver
  version, and CUDA version

Recommended diagnostic command:

```powershell
.\scripts\run_python.ps1 scripts\check_runtime_env.py --spacy-model en_core_web_trf
```

For a hard spaCy GPU check:

```powershell
.\scripts\run_python.ps1 scripts\check_runtime_env.py --spacy-model en_core_web_trf --require-spacy-gpu
```

Repeated benchmark conditions must not be handled as memory-only promises. If a
condition should be checked in future runs, add it to the benchmark summary,
this protocol, or a benchmark document before relying on it.

### Benchmark Reasoning Principle

Do not patch reasoning mistakes by adding more mechanical checklist rules.

The recurring failure to avoid is adding a causal explanation outside the
requested reporting scope, then not doing the analysis that explanation
requires.

For benchmark work, distinguish these modes before answering:

- Reporting mode: state the measured result and evidence only.
- Analysis mode: explain why a result changed.

If analysis mode is needed or volunteered, first identify the analysis unit that
matches the system design. For this project, stage-level timings exist because
the pipeline was split into stages to expose bottlenecks. A speed explanation
that ignores those stage timings is not a supported analysis.

Do not let visually salient metadata, such as GPU power cap or pstate, replace
the analysis unit that was deliberately built into the benchmark output.

If the necessary analysis has not been done, stop at:

```text
The speed changed, but the cause is not established from this run.
```

## 4. Rule Change Gate

Do not add extraction, repair, fallback, canonicalization, or lexicon behavior
directly in code.

Required order:

1. Add or revise the rule in `docs/rules_v1.md`.
2. Record impact review in `docs/rule_change_review_log_v1.md`.
3. Include rule id, stage, input, output, tool, tool type, rule type, count
   impact, and known limitation.
4. Get explicit user approval for the rule change.
5. Add tests.
6. Implement.
7. Run regression tests.

The impact review must state:

- proposed rule or lexicon change
- target stage and rule id
- existing rules affected
- expected count-table impact
- false positive risk
- false negative risk
- reversibility
- verification plan
- decision status

If a behavior is excluded by v1 design, say:

```text
excluded by v1 design
```

Do not implement it as a hidden patch.

## 5. Hardware and Runtime Scope

Do not collapse these into one claim:

1. physical GPU availability
2. NVIDIA driver / CUDA runtime availability
3. PyTorch CUDA availability
4. spaCy GPU / CuPy availability
5. actual device used by the latest benchmark

Example:

```text
Verified: PyTorch CUDA is available.
Verified: spaCy require_gpu failed because CuPy is missing.
Inference: this spaCy run cannot use GPU in the current environment.
Unknown: whether another environment on the same machine can use spaCy GPU.
```

## 6. Korean Short Form

중요한 판단은 아래 형식으로 말한다.

```text
확인됨:
근거:
추론:
미확인:
```

현재 코드 설명은 코드를 읽은 뒤에만 말한다.

속도, CPU/GPU, benchmark 주장은 command, input 개수, stage 범위, batch size,
중간 파일 write 여부, 실제 GPU 사용 여부를 함께 적는다.

rule 변경은 먼저 `docs/rules_v1.md`에 적고 승인받은 뒤 구현한다.

## 7. Filesystem And Escalation Claims

Do not say that a permission issue is solved just because a command succeeded
with `require_escalated`.

Before running a generated-artifact command, distinguish the path condition:

- if the output path is inside the current sandbox writable roots, try the
  bounded command normally first
- if the output path is outside the current sandbox writable roots, do not run a
  predictable failing sandbox attempt first; request `require_escalated` for the
  same narrow bounded command from the beginning

When explaining this case, say:

```text
Verified: the active output path is outside the current sandbox writable roots.
Inference: a normal sandbox write would be expected to fail.
Action: use the same narrow bounded command with require_escalated.
```

Do not present that expected failure as new diagnostic evidence from the script.

Separate these cases:

| Case | Meaning |
|---|---|
| `apply_patch` succeeded | Manual repository edit succeeded through the patch tool. |
| normal script write succeeded | The subprocess could write within the current sandbox/workspace. |
| `require_escalated` succeeded | The command succeeded outside the sandbox after approval. |
| permission issue fixed | The underlying path, cache, temp, or sandbox cause was removed and verified without escalation. |

Allowed wording:

```text
Verified: the generated TSV was written after rerunning the narrow script with
require_escalated.
Inference: the output was produced successfully.
Unknown: whether the same script now writes without escalation.
```

Forbidden wording:

```text
The permission problem is fixed.
```

unless the same relevant write path has succeeded without escalation.

When explaining repository file changes:

- say whether the file was edited by `apply_patch` or generated by a script
- say whether escalation was used
- if escalation was used, treat it as an execution mode, not a root-cause fix

## 8. Encoding Claims

Do not say a Korean Markdown or TSV file is corrupted just because PowerShell
displayed mojibake.

Before making an encoding claim, verify with an explicit UTF-8 read, for
example:

```powershell
.\scripts\run_python.ps1 -c "from pathlib import Path; print(repr(Path('docs/rules_v1.md').read_text(encoding='utf-8')[:300]))"
```

Separate these cases:

| Case | Meaning |
|---|---|
| UTF-8 strict read succeeds and `repr()` shows Korean | File content is valid UTF-8; display/output path is the likely issue. |
| UTF-8 strict read fails | File bytes are not valid UTF-8. |
| UTF-8 strict read succeeds but `repr()` shows mojibake characters | File content itself is likely already mojibake. |

Do not copy patch context from mojibake terminal output. Use an explicit UTF-8
read or ASCII-safe `repr()` when patching Korean text.

## 9. Report Freshness Claims

Do not describe a Markdown report as current unless its summary was checked
against the source artifact in the current turn or the report records its
snapshot scope.

This is not an instruction to scan every previous report on every task. It
applies when a report is edited, used as evidence, or naturally discovered to be
stale while working.

For source-label candidate reports, verify summary counts from the TSV columns
that actually encode the state:

- `selection_status`
- `selected_oewn_synset`
- `manual_decision`
- `synset_selection_tag`
- `mwe_candidate_status`

Allowed wording:

```text
Verified: the COCO source TSV has 78 selected rows, 1 rejected row, and 1
unresolved row.
Evidence: resources/source_labels/coco_oewn2025plus_synset_candidates.tsv.
Inference: the old Markdown line ambiguous_oewn_rows=1 is stale.
```

Forbidden wording:

```text
The report is current.
```

if only the Markdown file itself was read.

## 10. Enforced Incident Gate

Do not describe incident prevention as implemented unless the current command
path is guarded by `scripts/incident_gate.py`.

Official Stage 1-6 entrypoints, Stage 3.5 workflow, mixed pipeline, inventory
publish, bounded script runner, and supported remote wrappers must check the
repository-fixed `.pipeline_state` directory before execution. Detached jobs
must wrap the detached child itself; guarding only the launcher is invalid.

An open `.pipeline_state/incident.json` blocks official execution. An
uncompleted `.pipeline_state/running.json` becomes an incident on the next
official invocation when its recorded process is no longer verifiably active.
OOM, hard termination, and power loss are therefore detected by the surviving
marker even when exception cleanup could not run.

Do not clear an incident merely to retry. Clearing requires all of:

- concrete root cause
- durable guard added or an explicit reason why only a manual guard is possible
- verification evidence
- successful verification command when the incident has an executable check

Tests, diagnostics, and the incident CLI remain runnable while an incident is
open so the failure can be investigated and verified. A direct internal Python
function call that bypasses the guarded entrypoint is outside this guarantee
and must not be presented as an official run.
