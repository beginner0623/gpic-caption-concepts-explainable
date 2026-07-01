# AGENTS_ko.md

이 파일은 `AGENTS.md`의 한국어 설명판이다.

기준 파일은 `AGENTS.md`이고, 이 파일은 사람이 읽기 쉽게 같은 내용을 한국어로 풀어쓴 companion file이다.

## 프로젝트 목적

이 repository는 GPIC caption-to-concept extraction을 위한 새 explainable baseline이다.

우선순위는 maximum recall이 아니라 explainability다.

## 필수로 먼저 읽을 파일

코드, lexicon, report, documentation을 만들거나 수정하기 전에 반드시 아래 파일을 먼저 읽는다.

1. `AGENTS.md`
2. `docs/rules_v1.md`

요청받은 변경이 `docs/rules_v1.md`와 충돌하면, 편집을 시작하지 말고 먼저 충돌 내용을 설명한다.

## 현재 프로젝트 상태

이 프로젝트는 explainable v1 pipeline을 Stage 6까지 구현한 상태다.

앞으로 rule을 추가하거나 바꿀 때도 반드시 Rule Gate를 먼저 따른다.

## Scope Boundary

허용되는 구조는 `docs/rules_v1.md`에 적힌 6단계 pipeline뿐이다.

1. caption shape judgment
2. spaCy preprocessing
3. spaCy linguistic annotation
4. raw concept extraction
5. canonicalization
6. count export

사용자가 명시적으로 `docs/rules_v1.md` 업데이트를 승인하지 않는 한, stage, hidden repair, fallback chain, extra lexicon family를 추가하지 않는다.

## Rule Gate

모든 extraction 또는 transformation rule은 구현 전에 반드시 `docs/rules_v1.md`에 먼저 적혀 있어야 한다.

각 rule은 반드시 아래 항목을 가져야 한다.

- rule id
- stage
- input
- output
- tool
- tool type
- rule type
- count impact
- known limitation

이 형식으로 설명할 수 없는 rule은 구현하지 않는다.

## V1에서 허용되는 것

v1에서 허용되는 rule family는 아래 항목뿐이다.

- caption shape judgment: sentence vs tag-list
- spaCy tokenization
- raw quote span merge
- explicit object lexicon 기반 object MWE merge
- plain hyphen word merge
- spaCy tagger
- object MWE POS correction
- spaCy dependency parser
- spaCy attribute ruler
- spaCy lemmatizer
- spaCy noun chunks
- noun chunk root to object
- noun chunk modifier to attribute or quantity
- VERB token to action
- `nsubj` child to agent
- `obj` 또는 `dobj` child to patient
- ADP/preposition plus direct `pobj` to relation
- object synonym canonicalization
- attribute synonym and type canonicalization
- quantity raw-preserving canonicalization
- action synonym canonicalization
- parent concept mapping
- relation raw-preserving policy
- flat count export

## V1에서 금지되는 것

아래 기능은 v1에서 구현하지 않는다.

- pronoun resolution
- generic anaphora resolution
- `one`, `another`, `others`, `both` instance splitting
- passive voice normalization
- inherited agent repair
- skipped reference role recovery
- self-edge repair
- PP source disambiguation
- with-absolute recovery
- scene context fallback rules
- relation MWE collapse
- phrasal action collapse
- Python code 내부의 broad hidden hardcoded word list
- GPIC-error-specific patch rules
- count export 단계에서의 새로운 linguistic interpretation

## 구현 규칙

구현을 시작할 때는 아래 원칙을 따른다.

- 함수는 작고 single-purpose로 유지한다.
- output row에 rule id가 보이게 한다.
- lexicon은 `resources/lexicons` 아래 TSV 파일로 둔다.
- project policy를 code comment 안에 숨기지 않는다.
- 이전 prototype의 logic을 복사하지 않는다.
- dependency를 추가할 때는 왜 필요한지 문서화한다.
- generated report를 손으로 수정하지 않는다.

## 커뮤니케이션 규칙

이 repository를 설명할 때는 아래 원칙을 따른다.

- `docs/rules_v1.md`의 6단계 v1 stage 번호를 사용한다.
- 구현된 동작과 제안 중인 동작을 구분한다.
- 기능이 없으면 "not implemented"라고 말한다.
- v1에서 의도적으로 제외한 기능이면 "excluded by v1 design"이라고 말한다.
- 이 baseline을 high-recall이라고 설명하지 않는다.

이 repository는 아래처럼 설명한다.

> documented limitations를 가진 explainable caption-to-concept baseline

## Evidence-Gated Answer Protocol / 근거 기반 답변 규칙

중요한 설명, 코드 동작 설명, 속도 측정, CPU/GPU 판단, rule 동작 설명은 반드시 `docs/answer_protocol.md`를 따른다.

핵심 원칙:

- 관찰한 사실과 추론을 섞지 않는다.
- 현재 코드 동작은 관련 파일을 읽은 뒤에만 설명한다.
- benchmark나 GPU/CPU 관련 주장은 command, output file, model, input 개수, stage 범위, batch size, 중간 파일 write 여부, 실제 `gpu_enabled` 값을 함께 적는다.
- 한 라이브러리의 실행 상태로 하드웨어 전체 능력을 단정하지 않는다.
- physical GPU, driver/CUDA, PyTorch CUDA, spaCy GPU/CuPy, latest run device를 서로 구분한다.
- rule, repair, fallback, lexicon behavior는 먼저 `docs/rules_v1.md`에 적고 승인받은 뒤 구현한다.

중요 판단은 아래 형식을 사용한다.

```text
확인됨:
근거:
추론:
미확인:
```

금지되는 표현:

- "이 PC는 GPU를 못 쓴다"처럼 현재 run 결과를 하드웨어 결론으로 확대하는 말
- 코드를 읽지 않고 "현재 코드는 이렇게 한다"고 단정하는 말
- command, input 개수, stage 범위 없이 benchmark 속도를 단정하는 말
