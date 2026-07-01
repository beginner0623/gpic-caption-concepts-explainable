# V1 Environment Setup

이 문서는 새 explainable baseline repo의 독립 실행 환경을 고정한다.

이 repo는 이전 `gpic-caption-concepts` repo의 `.mamba` 환경을 사용하지 않는다.

## 1. 환경 위치

프로젝트 전용 환경:

```text
.mamba/env
```

이 디렉토리는 `.gitignore`에 포함되어 GitHub에 올리지 않는다.

## 2. 의존성

의존성은 `environment.yml`에 기록한다.

현재 필요한 외부 라이브러리:

| dependency | 이유 |
|---|---|
| `spacy=3.8` | Stage 2 tokenization, PhraseMatcher, Retokenizer, filter_spans 실행 |
| `spacy-model-en_core_web_trf=3.8` | Stage 3 TAG, dependency, POS, MORPH, lemma, noun chunk annotation 기본 모델 |
| `click` | 현재 conda-forge spaCy import 검증에서 필요한 runtime dependency를 명시 고정 |

Stage 2는 tokenizer-only `spacy.blank("en")`를 사용한다.

Stage 3부터는 `en_core_web_trf`를 기본 모델로 사용한다.

## 3. 환경 생성

PowerShell에서 repo root 기준으로 실행한다.

```powershell
.\scripts\setup_env.ps1
```

이 스크립트는 아래 일을 한다.

1. `environment.yml`을 읽는다.
2. `.mamba/env`에 micromamba 환경을 만든다.
3. 새 환경에서 `spacy` import를 확인한다.

## 4. Python 실행

이 repo의 Python 코드는 항상 아래 runner로 실행한다.

```powershell
.\scripts\run_python.ps1 -m unittest discover -s tests
```

`run_python.ps1`은 아래 일을 한다.

1. `.mamba/env/python.exe`를 사용한다.
2. repo의 `src` 디렉토리를 `PYTHONPATH`에 추가한다.
3. 전달된 Python 인자를 그대로 실행한다.

## 5. 금지

- 이전 repo의 `.mamba/env/python.exe`를 사용하지 않는다.
- 전역 Python 설치를 요구하지 않는다.
- 새 의존성은 먼저 이 문서와 `environment.yml`에 기록한 뒤 추가한다.
