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
- Stage 1 sentence-row input; Stage 2-6 one-process fast benchmark
- 중간 Stage 3/4/5 JSONL 파일을 쓰지 않고 최종 count까지 한 process에서 수행
- current benchmark summary reports `stage2_seconds`, `stage3_seconds`,
  `stage2_stage3_seconds`, `stage4_seconds`, and their aggregate
  `stage2_to_stage4_seconds`
- current benchmark summary also records `nvidia-smi` metadata when available,
  including observed `gpu_power_limit_w`, `gpu_power_draw_w`, `gpu_pstate`, GPU
  name, driver version, and CUDA version

Laptop silent/balanced/performance mode must not be inferred from memory. Use
the observed `gpu_power_limit_w` in the benchmark summary as the durable
evidence for the active power-cap condition.

## Stage 3 length bucketing option

`scripts\benchmark_fast_pipeline.py` supports an optional benchmark scheduling
flag:

```powershell
--length-bucket-size N
```

When `N > 0`, Stage 1 rows are buffered in chunks of `N` and sorted by raw
caption length inside each buffer before Stage 3 `nlp.pipe` batching. This is
not an extraction rule and does not add linguistic interpretation. It only
changes the order in which sentence captions are batched for the benchmark.

This option is mainly useful when the input is larger than one spaCy batch. For
the 790-caption local sample with `--batch-size 1664`, all captions fit in one
batch, so length bucketing is not expected to show a meaningful benefit.

Observed comparison on a synthetic 7,900-caption input made by repeating the
790-caption local sample ten times:

| input | batch_size | length_bucket_size | power cap | stage3_seconds | processing_seconds | processing_captions_per_second |
|---|---:|---:|---:|---:|---:|---:|
| 7,900 synthetic captions | 1664 | 0 | 82W | 27.36 | 36.49 | 216.49 |
| 7,900 synthetic captions | 1664 | 65536 | 78W | 23.03 | 31.69 | 249.31 |

In this run, length bucketing reduced Stage 3 time by about 15.8% and improved
processing throughput by about 15.2%. The input is synthetic and repeated, so
this is a scheduling benchmark rather than a quality benchmark.

## Legacy split timing example, not the speed baseline

This run was regenerated after the first timing-field rename. It predates the
Stage 2/Stage 3 internal timing hook, so it does not contain pure
`stage2_seconds` and `stage3_seconds`. It should not be treated as a new
best-speed baseline, because the 790-caption GPU benchmark showed substantial
run-to-run variance.

Summary file:

```text
outputs\benchmark_fast_pipeline\summary_790_batch1664_gpu_doc_direct_current.json
```

Command conditions:

| field | value |
|---|---:|
| sentence_count | 790 |
| model | `en_core_web_trf` |
| batch_size | 1664 |
| raw_extraction_mode | `doc-direct` |
| gpu_mode | `require` |
| gpu_enabled | true |

Measured timing:

| metric | seconds |
|---|---:|
| setup_seconds | 1.3935 |
| stage2_to_stage3_seconds | 3.6882 |
| stage4_seconds | 0.2584 |
| stage2_to_stage4_seconds | 3.9466 |
| stage5_seconds | 0.0524 |
| stage6_seconds | 0.7470 |
| processing_seconds | 4.7461 |
| total_seconds | 6.1396 |

Throughput:

| metric | value |
|---|---:|
| processing_captions_per_second | 166.45 |
| total_captions_per_second | 128.67 |

Note: the legacy `stage2_to_stage3_seconds` field is not pure Stage 3 timing.
Current benchmark summaries replace it with `stage2_seconds`,
`stage3_seconds`, and `stage2_stage3_seconds`.

Comparison with nearby runs:

| summary file | timing fields | processing_seconds | processing_captions_per_second |
|---|---|---:|---:|
| `summary_790_batch1664_gpu_doc_direct_seq.json` | old aggregate field only | 4.0922 | 193.05 |
| `summary_790_batch1664_gpu_doc_direct_current.json` | split timing fields | 4.7461 | 166.45 |
| `summary_790_batch1664_gpu_doc_direct_current_rerun.json` | split timing fields | 6.1883 | 127.66 |

Until a repeated benchmark reports median and variance, use
`summary_790_batch1664_gpu_doc_direct_seq.json` only as the best observed run,
not as a guaranteed steady-state speed.

명령 예시:

```powershell
.\scripts\run_python.ps1 scripts\benchmark_fast_pipeline.py `
  --input outputs\benchmark_speed_inprocess\sentence_rows_x10.jsonl `
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
