# V1 Speed Benchmark

이 문서는 v1 explainable pipeline의 실행 속도 측정 기록이다.

중요한 전제:

- 이 벤치는 extraction rule을 바꾸지 않는다.
- Stage 3의 spaCy 실행을 `nlp.pipe(batch_size=128)`로 묶어 실행한다.
- tag-list caption은 v1 설계대로 제외한다.
- benchmark는 extraction rule을 새로 바꾸지 않는다. passive voice는 현재 v1 Stage 4 rule 상태를 그대로 따른다.

## 2026-07-01 Batch Stage 3 Optimization

입력:

- `outputs/benchmark_speed_inprocess/sentence_rows_x10.jsonl`
- sentence caption 790개
- `en_core_web_trf`
- batch size 128
- GPU disabled. Local environment has CUDA-visible PyTorch, but spaCy GPU requires CuPy and was not active.

검증:

- 이전 x10 Stage 3 output과 새 batch Stage 3 output의 SHA256 hash가 같았다.
- 즉 batch 실행 변경으로 Stage 3 annotation 결과는 바뀌지 않았다.
- 전체 test suite: 39 passed.

## CLI Stage 3 Only

명령:

```powershell
.\scripts\run_python.ps1 scripts\run_stage3_annotate.py `
  --input outputs\benchmark_speed_inprocess\sentence_rows_x10.jsonl `
  --output outputs\benchmark_stage3_batch_cli\stage3_records.jsonl `
  --summary outputs\benchmark_stage3_batch_cli\stage3_summary.jsonl `
  --batch-size 128
```

결과:

- 790 captions
- 21.00 sec
- 약 37.6 captions/sec

이 값에는 Python process start, spaCy model load, Stage 3 JSONL write가 포함된다.

## One-Process Fast Benchmark

명령:

```powershell
.\scripts\run_python.ps1 scripts\benchmark_fast_pipeline.py `
  --input outputs\benchmark_speed_inprocess\sentence_rows_x10.jsonl `
  --lexicon-dir resources\lexicons `
  --summary outputs\benchmark_fast_pipeline\summary_790.json `
  --batch-size 128
```

결과:

| metric | value |
|---|---:|
| sentence_count | 790 |
| setup_seconds | 1.25 |
| stage2_to_stage4_seconds | 14.05 |
| stage2_seconds | not recorded in this historical run |
| stage3_seconds | not recorded in this historical run |
| stage2_stage3_seconds | not recorded in this historical run |
| stage4_seconds | not recorded in this historical run |
| stage5_seconds | 0.04 |
| stage6_seconds | 0.64 |
| processing_seconds | 14.74 |
| total_seconds | 15.98 |
| processing_captions_per_second | 53.61 |
| total_captions_per_second | 49.42 |

Batch size sweep:

Current `benchmark_fast_pipeline.py` keeps the fast streaming path and reports
Stage 2, Stage 3, and Stage 4 timing separately:

- `stage2_seconds`: `nlp.make_doc()` plus Stage 2 span protection.
- `stage3_seconds`: batched `nlp.pipe()` linguistic annotation.
- `stage2_stage3_seconds`: `stage2_seconds + stage3_seconds`.
- `stage2_to_stage4_seconds`: full streaming loop through Stage 4.
- `stage2_to_stage4_overhead_seconds`: loop overhead not assigned to Stage 2,
  Stage 3, or Stage 4.

Older rows in this document were produced before the split, so only the
aggregate `stage2_to_stage4_seconds` is available for them.

| batch_size | processing_captions_per_second | total_captions_per_second |
|---:|---:|---:|
| 32 | 54.27 | 49.85 |
| 64 | 53.59 | 49.44 |
| 128 | 56.40 | 51.73 |
| 256 | 55.90 | 51.52 |

반복 실행마다 약간 흔들리며, 현재 로컬 CPU 기준 관측 범위는 대략 50-56 captions/sec이다.

해석:

- 장기 실행에서 model load는 거의 무시되므로 현재 로컬 CPU 기준 현실적인 처리량은 약 50-56 captions/sec 근처다.
- 병목은 Stage 3 spaCy transformer annotation이다.
- Stage 5 canonicalization과 Stage 6 count export는 현재 규모에서는 병목이 아니다.

## Practical Notes

3일 안에 100M captions를 처리하려면 단일 로컬 프로세스 기준으로는 부족하다.

현재 로컬 CPU 기준 단순 추정:

- 50-56 captions/sec
- 4.32M-4.84M captions/day
- 100M captions 약 20.7-23.1일

3일 목표를 맞추려면 대략 평균 386 captions/sec 이상이 필요하다.

가능한 속도 개선 방향:

1. H200 환경에서 spaCy transformer GPU 실행을 실제 활성화한다.
2. `cupy-cuda12x` 등 spaCy GPU에 필요한 CuPy를 환경에 설치한다.
3. shard 단위로 여러 process 또는 여러 GPU에 분산한다.
4. 중간 JSONL을 매 stage마다 쓰지 않는 streaming/one-process production runner를 따로 만든다.
5. 정확도 희생을 감수할 수 있으면 `en_core_web_lg` 또는 lighter parser를 별도 benchmark한다.

## 2026-07-11 Sentence100 Formal Stage Run

목적:

- 현재 preposition MWE 및 action/attribute inventory가 반영된 formal
  Stage 3-6 경로에서 100 caption 실행 시간을 확인한다.

입력:

- `outputs/case_reports_sentence100_0101_0200_current/sentence_rows_0101_0200.jsonl`
- captions: 100
- model: `en_core_web_trf`
- batch size: 128
- Stage 3 GPU mode: `--require-gpu`
- intermediate files: Stage 3, Stage 4, Stage 5, Stage 6 JSONL/TSV 모두 write
- output directory:
  `outputs/benchmark_sentence100_0101_0200_preposition_mwe_20260711_214442`

Runtime metadata:

- GPU: NVIDIA GeForce RTX 5080 Laptop GPU
- driver: 592.01
- CUDA reported by `nvidia-smi`: 13.1
- post-run pstate: P8
- post-run power draw/cap: 4W / 69W
- Stage 3 summary: `gpu_enabled=true`, `gpu_mode=require`

Measured elapsed time:

| segment | seconds |
|---|---:|
| Stage 3 internal Stage 2 + annotation + write | 10.397 |
| Stage 4 raw extraction + write | 7.951 |
| Stage 5 canonicalization + write | 1.025 |
| Stage 6 count export + write | 1.545 |
| Core Stage 3-6 total | 20.918 |
| Markdown report render | 0.998 |
| Core Stage 3-6 + Markdown total | 21.916 |

Throughput:

| scope | captions/sec |
|---|---:|
| Core Stage 3-6 | 4.781 |
| Core Stage 3-6 + Markdown | 4.563 |

Reference-only Stage 2 inspection artifact:

- `scripts/run_stage2_preprocess.py` over the same 100 sentence rows took
  6.313 seconds.
- This value is not added to Stage 3-6 total because Stage 3 already performs
  Stage 2 protection internally before annotation.

Interpretation:

- This is a cold, process-per-stage measurement, so it includes Python process
  startup, spaCy model load, GPU setup, and intermediate file writes.
- It should not be compared directly to older one-process streaming benchmark
  rows without accounting for setup and file-write policy differences.

Follow-up diagnostic:

- A same-input in-process diagnostic run reported `processing_seconds=1.915`
  and `total_seconds=3.377`, or about `52.21` processing captions/sec.
- That diagnostic is not a formal output-equivalent run because the current
  `benchmark_fast_pipeline.py` does not use the same completed action inventory
  path as the formal Stage 4 runner; its edge counts differed from the formal
  run.
- A separate Stage 4 no-write diagnostic with the formal object/action/
  preposition inventories measured:
  - object inventory load: 0.004 seconds
  - action inventory load: 0.001 seconds
  - preposition MWE lexicon load: 0.002 seconds
  - actual extraction over 100 Stage 3 records: 0.086 seconds
- Therefore the 20.918-second formal measurement mostly reflects cold
  per-stage process/import/model setup and intermediate file-write overhead, not
  the raw Stage 4 extraction algorithm itself.
