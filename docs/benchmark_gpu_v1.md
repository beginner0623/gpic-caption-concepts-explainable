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

현재 로컬 RTX 5080 Laptop GPU 기준으로, 이 790개 benchmark에서는 batch 1024가 가장 빨랐다.

관측된 steady-state 처리량:

```text
약 172 captions/sec processing 기준
약 130 captions/sec total 기준
```

기존 CPU fast benchmark보다 processing 기준 약 3.2배 빠르다.

## 3일 100M 기준 환산

100M captions를 3일 안에 처리하려면 평균 약 386 captions/sec가 필요하다.

현재 로컬 GPU 단일 process의 관측값만 놓고 보면 3일 목표에는 부족하다.

단, 이 값은 로컬 RTX 5080 Laptop GPU 단일 process 기준이다. H200 16장 조건에서는 별도 multi-GPU shard benchmark가 필요하다.
