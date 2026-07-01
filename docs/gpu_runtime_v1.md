# GPU Runtime Notes

검증일: 2026-07-01.

## 확인된 사실

현재 repo의 실제 위치에는 한글, 공백, 괄호가 포함되어 있다.

```text
C:\Users\rlath\OneDrive\Desktop\PILAB\0. 연구과제\기영님 연구과제(blue maze)\caption to concept\gpic-caption-concepts-explainable
```

이 경로에서 CuPy를 직접 실행하면 NVRTC가 CuPy header를 열지 못하는 문제가 확인되었다.

대표 오류:

```text
cannot open source file "cupy/complex.cuh"
```

같은 repo와 같은 `.mamba/env`를 ASCII junction 경로로 실행하면 CuPy와 spaCy GPU model load가 통과한다.

사용 중인 ASCII junction:

```text
C:\Users\rlath\Documents\Codex\gpic-explainable-link
```

검증된 GPU:

```text
NVIDIA GeForce RTX 5080 Laptop GPU, 16303 MiB
```

## 실행 방식

`scripts/run_python.ps1`는 다음 순서로 runtime root를 정한다.

1. `GPIC_RUNTIME_ROOT` 환경변수가 있으면 그 경로를 사용한다.
2. 없으면 `C:\Users\<user>\Documents\Codex\gpic-explainable-link`에 `.mamba/env/python.exe`와 `src`가 있는지 확인한다.
3. 있으면 그 ASCII junction을 runtime root로 사용한다.
4. 없으면 script가 있는 repo root를 그대로 사용한다.

## 검증 명령

```powershell
.\scripts\run_python.ps1 scripts\check_runtime_env.py --spacy-model en_core_web_trf --require-spacy-gpu
```

통과 기준:

- `python.executable`이 ASCII junction 아래의 `.mamba/env/python.exe`를 가리킨다.
- `spacy.require_gpu`가 `true`다.
- `spacy.model.loaded`가 `true`다.

## 해석

이 문제는 "GPU가 없다"가 아니다. 확인된 GPU와 CUDA runtime은 존재한다.

현재 확인된 원인은 경로 문제다. 원래 repo 경로에서 CuPy header 파일은 실제로 존재하지만, NVRTC compile 단계가 그 header를 열지 못했다. ASCII junction으로 같은 파일을 접근했을 때는 통과했다.
