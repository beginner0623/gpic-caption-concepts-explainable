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

Recommended diagnostic command:

```powershell
.\scripts\run_python.ps1 scripts\check_runtime_env.py --spacy-model en_core_web_trf
```

For a hard spaCy GPU check:

```powershell
.\scripts\run_python.ps1 scripts\check_runtime_env.py --spacy-model en_core_web_trf --require-spacy-gpu
```

## 4. Rule Change Gate

Do not add extraction, repair, fallback, canonicalization, or lexicon behavior
directly in code.

Required order:

1. Add or revise the rule in `docs/rules_v1.md`.
2. Include rule id, stage, input, output, tool, tool type, rule type, count
   impact, and known limitation.
3. Get explicit user approval for the rule change.
4. Add tests.
5. Implement.
6. Run regression tests.

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
