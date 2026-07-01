# GPU Benchmark Notes

검증일: 2026-07-01.

## Benchmark 조건

입력:

```text
outputs\benchmark_speed_inprocess\sentence_rows_x10.jsonl
```

조건:

- sentence captions: 790
- model: `en_core_web_trf`
- GPU mode: `--require-gpu`
- runtime path: `C:\Users\rlath\Documents\Codex\gpic-explainable-link`
- Stage 3-6 one-process fast benchmark
- 중간 Stage 3/4/5 JSONL 파일을 쓰지 않고 최종 count까지 한 process에서 수행

명령 예시:

```powershell
.\scripts\run_python.ps1 scripts\benchmark_fast_pipeline.py `
  --input outputs\benchmark_speed_inprocess\sentence_rows_x10.jsonl `
  --object-mwes resources\lexicons\object_mwes.tsv `
  --lexicon-dir resources\lexicons `
  --model en_core_web_trf `
  --batch-size 256 `
  --require-gpu `
  --summary outputs\benchmark_fast_pipeline\summary_790_batch256_gpu_ascii.json
```

## CPU 기준

기존 CPU fast benchmark 기준:

| metric | value |
|---|---:|
| batch_size | 128 |
| gpu_enabled | false |
| processing_captions_per_second | 53.61 |
| total_captions_per_second | 49.42 |
| processing_seconds | 14.74 |
| total_seconds | 15.98 |

## GPU batch sweep

첫 GPU 실행은 CuPy/NVRTC compile warm-up 영향으로 느릴 수 있다. 아래 표는 ASCII junction에서 `--require-gpu`로 실행한 관측값이다.

| batch_size | processing_captions_per_second | total_captions_per_second | processing_seconds | total_seconds |
|---:|---:|---:|---:|---:|
| 16 | 28.53 | 27.06 | 27.69 | 29.20 |
| 32 | 136.45 | 108.41 | 5.79 | 7.29 |
| 64 | 141.14 | 110.12 | 5.60 | 7.17 |
| 128 | 144.11 | 112.49 | 5.48 | 7.02 |
| 256 | 146.77 | 113.62 | 5.38 | 6.95 |
| 512 | 146.78 | 115.34 | 5.38 | 6.85 |
| 1024 | 172.03 | 130.06 | 4.59 | 6.07 |
| 2048 | 149.64 | 115.75 | 5.28 | 6.82 |

## 현재 결론

위 표는 기존 `stage3-record` 경로 기준이다. 이 경로는 spaCy Doc을 Stage 3 evidence table로 직렬화한 뒤 Stage 4가 그 table을 다시 읽는다.

추가로 `doc-direct` fast path를 검증했다. 이 경로는 같은 R12-R18 raw extraction rule을 annotated spaCy Doc에 직접 적용하며, Stage 3 evidence table 직렬화 왕복을 건너뛴다. Stage 3/4 공식 output schema는 바꾸지 않는다.

동일 입력 790개에서 기존 `stage3-record` 경로와 `doc-direct` 경로의 raw mentions 및 raw edges가 완전히 같은 것도 확인했다.

동일 입력 790개, `en_core_web_trf`, `--require-gpu`, batch 1024 기준 순차 실행 비교:

| raw_extraction_mode | processing_captions_per_second | total_captions_per_second | raw_mentions | raw_edges | facts |
|---|---:|---:|---:|---:|---:|
| `stage3-record` | 149.99 | 116.44 | 12530 | 6940 | 64110 |
| `doc-direct` | 177.49 | 131.15 | 12530 | 6940 | 64110 |

`doc-direct` 기준 batch sweep:

| batch_size | processing_captions_per_second | total_captions_per_second | processing_seconds | total_seconds |
|---:|---:|---:|---:|---:|
| 768 | 173.86 | 130.22 | 4.54 | 6.07 |
| 896 | 179.20 | 132.23 | 4.41 | 5.97 |
| 1024 | 178.04 | 131.43 | 4.44 | 6.01 |
| 1152 | 181.90 | 135.77 | 4.34 | 5.82 |
| 1280 | 181.30 | 134.18 | 4.36 | 5.89 |
| 1536 | 185.91 | 137.91 | 4.25 | 5.73 |
| 1664 | 193.05 | 142.50 | 4.09 | 5.54 |
| 1792 | 184.40 | 138.16 | 4.28 | 5.72 |
| 1920 | 190.82 | 141.90 | 4.14 | 5.57 |
| 2048 | 181.99 | 135.35 | 4.34 | 5.84 |

현재 로컬 RTX 5080 Laptop GPU 기준으로, 이 790개 benchmark에서는 `doc-direct`, batch 1664가 가장 빨랐다.

관측된 steady-state 처리량:

```text
약 193 captions/sec processing 기준
약 142 captions/sec total 기준
```

기존 CPU fast benchmark보다 processing 기준 약 3.6배 빠르다.

## 3일 100M 기준 환산

100M captions를 3일 안에 처리하려면 평균 약 386 captions/sec가 필요하다.

현재 로컬 GPU 단일 process의 관측값만 놓고 보면 3일 목표에는 부족하다.

단, 이 값은 로컬 RTX 5080 Laptop GPU 단일 process 기준이다. H200 16장 조건에서는 별도 multi-GPU shard benchmark가 필요하다.
