# V1 Speed Benchmark

이 문서는 v1 explainable pipeline의 실행 속도 측정 기록이다.

중요한 전제:

- 이 벤치는 extraction rule을 바꾸지 않는다.
- Stage 3의 spaCy 실행을 `nlp.pipe(batch_size=128)`로 묶어 실행한다.
- tag-list caption은 v1 설계대로 제외한다.
- relation MWE, coreference, passive normalization 등은 v1 설계대로 구현하지 않는다.

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
  --object-mwes resources\lexicons\object_mwes.tsv `
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
  --object-mwes resources\lexicons\object_mwes.tsv `
  --lexicon-dir resources\lexicons `
  --summary outputs\benchmark_fast_pipeline\summary_790.json `
  --batch-size 128
```

결과:

| metric | value |
|---|---:|
| sentence_count | 790 |
| setup_seconds | 1.25 |
| stage3_stage4_seconds | 14.05 |
| stage5_seconds | 0.04 |
| stage6_seconds | 0.64 |
| processing_seconds | 14.74 |
| total_seconds | 15.98 |
| processing_captions_per_second | 53.61 |
| total_captions_per_second | 49.42 |

Batch size sweep:

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
