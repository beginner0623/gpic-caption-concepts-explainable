# V1 Implementation Plan

이 문서는 `docs/rules_v1.md`에 정의된 rule을 실제 코드와 산출물로 구현하기 위한 실행 계획서다.

이 문서는 새 rule을 추가하지 않는다.

기준 문서:

- `AGENTS.md`: 작업 운영 규칙
- `docs/rules_v1.md`: 허용 rule과 금지 rule의 기준
- `docs/environment_setup_v1.md`: 독립 실행 환경 기준

## 0. 구현 원칙

v1 구현의 목표는 high recall이 아니다.

목표는 아래 조건을 만족하는 baseline이다.

- 각 mention과 edge가 어떤 Rule ID에서 나왔는지 추적 가능해야 한다.
- count export 단계에서는 새 linguistic interpretation을 하지 않아야 한다.
- 누락된 정보는 patch하지 않고 limitation으로 남겨야 한다.
- relation MWE, phrasal action, pronoun resolution, passive normalization은 v1에서 구현하지 않는다.
- 이전 prototype의 repair logic을 복사하지 않는다.
- tag-list caption은 v1에서 별도 segment parser를 쓰지 않는다.
- tag-list caption은 v1 extraction 대상에서 제외한다.
- tag-list caption은 skipped record로 남기고, reason은 `tag_list_deferred`로 기록한다.
- comma split, segment별 object/attribute grouping, tag-list 전용 추론은 v1에서 하지 않는다.

## 1. 최종 디렉토리 구조 계획

아래 구조를 기준으로 구현한다. 현재 Stage 1~5는 구현했고, Stage 6 count export는 다음 작업이다.

```text
gpic-caption-concepts-explainable/
├─ AGENTS.md
├─ AGENTS_ko.md
├─ docs/
│  ├─ rules_v1.md
│  ├─ implementation_plan_v1.md
│  ├─ output_schema_v1.md
│  ├─ environment_setup_v1.md
│  └─ known_limitations_v1.md
├─ resources/
│  └─ lexicons/
│     ├─ object_mwes.tsv
│     ├─ object_synonyms.tsv
│     ├─ object_parents.tsv
│     ├─ attribute_synonyms.tsv
│     ├─ attribute_types.tsv
│     ├─ action_synonyms.tsv
│     └─ action_parents.tsv
├─ scripts/
│  ├─ run_stage1_records.py
│  ├─ run_stage2_preprocess.py
│  ├─ run_stage3_annotate.py
│  ├─ run_stage4_extract_raw.py
│  ├─ run_pipeline_v1.py
│  ├─ inspect_sample_v1.py
│  └─ export_counts_v1.py
├─ src/
│  └─ gpic_concepts_v1/
│     ├─ __init__.py
│     ├─ config.py
│     ├─ schema.py
│     ├─ stage1.py
│     ├─ stage1_loader.py
│     ├─ stage2_preprocess.py
│     ├─ stage3_annotate.py
│     ├─ stage4_extract_raw.py
│     ├─ stage5_canonicalize.py
│     └─ stage6_export_counts.py
├─ tests/
│  ├─ test_stage2_preprocess.py
│  ├─ test_stage3_annotate.py
│  ├─ test_stage4_extract_raw.py
│  ├─ test_stage5_canonicalize.py
│  └─ test_stage6_export_counts.py
├─ data/
│  └─ samples/
└─ reports/
```

주의:

- `relation_mwes.tsv`는 만들지 않는다.
- `phrasal_actions.tsv`는 만들지 않는다.
- coreference 관련 파일은 만들지 않는다.

## 2. Milestone 1: 문서와 schema 고정

목표:

- 구현 전에 output 구조를 고정한다.

작업:

1. `docs/output_schema_v1.md` 작성
2. `docs/known_limitations_v1.md` 작성
3. `src/gpic_concepts_v1/schema.py` 작성

산출물:

- Mention schema
- Edge schema
- Canonical record schema
- Count row schema

검증:

- schema에 Rule ID 필드가 있는지 확인
- count export용 row가 새 해석 없이 만들 수 있는지 확인

완료 기준:

- object, attribute, quantity, action, relation, edge, fact 구조가 문서화되어 있음
- 각 구조가 `docs/rules_v1.md`의 Rule ID와 연결 가능함

## 3. Milestone 2: Stage 1 구현

대상 rule:

- R1 Caption shape 판단
- R1.1 Tag-list skip

작업:

1. `stage1_caption_shape.py` 작성
2. GPIC row의 `caption_type` field를 읽음
3. `caption_type == "tag"`이면 내부 shape를 `tag_list`로 매핑
4. `caption_type in {"short", "medium", "long"}`이면 내부 shape를 `sentence`로 매핑
5. 알려지지 않은 `caption_type`은 fallback rule 없이 에러로 처리
6. `tag_list`로 판정되면 Stage 2~6을 호출하지 않음
7. `tag_list` row는 `skipped=true`, `skip_reason=tag_list_deferred`로 기록

산출물:

- caption shape record
- skipped record for tag-list rows

검증:

- `caption_type=short/medium/long` row가 sentence path로 가는지 확인
- `caption_type=tag` row가 tag-list path로 가는지 확인
- 알려지지 않은 `caption_type`에 대해 추측하지 않고 에러를 내는지 확인

완료 기준:

- Stage 1에서 concept extraction이 일어나지 않음
- `tag_list` 여부가 이후 report와 output metadata에 남음
- `tag_list`가 별도 comma segment extraction으로 빠지지 않음
- `tag_list`가 sentence pipeline으로도 들어가지 않음

## 4. Milestone 3: Stage 2 구현

대상 rule:

- R2 Tokenization
- R3 Quote span merge
- R4 Object MWE merge
- R5 Hyphen word merge

작업:

1. `stage2_preprocess.py` 작성
2. spaCy tokenizer 사용
3. quote span detector 구현
4. object MWE lexicon loader 구현
5. PhraseMatcher + filter_spans + Retokenizer 적용
6. hyphen word detector 구현
7. Stage 1에서 `sentence`로 통과한 caption만 preprocessing에 들어옴

산출물:

- Stage 2 inspection JSONL
- token list
- protected span metadata

lexicon:

- `resources/lexicons/object_mwes.tsv`
- 초기 상태는 header-only
- GPIC sample을 보고 자동으로 항목을 추가하지 않음

검증:

- quote span이 하나의 token으로 merge되는지 확인
- object MWE lexicon에 있는 phrase만 merge되는지 확인
- hyphen word가 merge되는지 확인
- relation MWE가 merge되지 않는지 확인
- quote placeholder 치환이 일어나지 않는지 확인
- tag-list caption이 Stage 2에 들어오지 않는지 확인

완료 기준:

- Stage 2는 span protection만 수행하고 concept을 만들지 않음
- Stage 2는 sentence caption만 처리함

## 5. Milestone 4: Stage 3 구현

대상 rule:

- R6 TAG annotation
- R7 Object MWE POS correction
- R8 Dependency parsing
- R9 POS, MORPH annotation
- R10 Lemmatization
- R11 Noun chunking

작업:

1. `stage3_annotate.py` 작성
2. `en_core_web_trf` spaCy model pipeline 구성
3. object MWE POS correction component 작성
4. token annotation inspection helper 작성

산출물:

- token table
- dependency table
- noun chunk table

검증:

- object MWE merge token만 POS=`NOUN`, TAG=`NN` 보정되는지 확인
- 일반 token의 POS/TAG를 custom rule로 덮어쓰지 않는지 확인
- noun chunk가 downstream extraction 입력으로 제공되는지 확인

완료 기준:

- Stage 3는 linguistic evidence만 만들고 concept extraction을 하지 않음

## 6. Milestone 5: Stage 4 구현

대상 rule:

- R12 Noun chunk root to object
- R13 Noun chunk modifier to attribute
- R14 Noun chunk modifier to quantity
- R15 VERB to action
- R16 `nsubj` to agent
- R17 `obj` or `dobj` to patient
- R18 ADP plus direct `pobj` to relation

작업:

1. `stage4_extract_raw.py` 작성
2. `stage3_records.jsonl`을 입력으로 사용
3. noun chunk root 기반 object mention 생성
4. noun chunk 내부 modifier 기반 attribute/quantity 생성
5. VERB token 기반 action mention 생성
6. dependency child 기반 agent/patient edge 생성
7. ADP/preposition + direct `pobj` 기반 relation edge 생성

산출물:

- raw mentions
- raw edges

검증:

- mention마다 Rule ID가 있는지 확인
- edge마다 Rule ID가 있는지 확인
- relation/action edge 생성을 위해 새 object mention을 추가하지 않는지 확인
- `pobj`가 action patient로 들어가지 않는지 확인
- passive voice rewrite가 일어나지 않는지 확인
- pronoun resolution이 일어나지 않는지 확인
- relation MWE collapse가 일어나지 않는지 확인
- tag-list 전용 segment grouping이 일어나지 않는지 확인
- tag-list caption이 Stage 4에 들어오지 않는지 확인

완료 기준:

- raw extraction 결과가 dependency와 noun chunk에서 직접 보이는 정보로만 구성됨

## 7. Milestone 6: Stage 5 구현

대상 rule:

- R19 Object synonym canonicalization
- R20 Attribute synonym and type canonicalization
- R21 Quantity raw-preserving canonicalization
- R22 Action synonym canonicalization
- R23 Parent concept mapping
- R24 Relation raw-preserving

작업:

1. `stage5_canonicalize.py` 작성
2. TSV lexicon loader 작성
3. object canonical lookup 구현
4. attribute canonical/type lookup 구현
5. quantity raw-preserving 구현
6. action canonical lookup 구현
7. parent concept lookup 구현
8. relation raw-preserving policy 구현

산출물:

- canonical mentions
- canonical edges

검증:

- unknown term은 raw lemma를 유지하는지 확인
- relation label이 새로 collapse되지 않는지 확인
- canonicalization 단계에서 agent/patient/source/target이 바뀌지 않는지 확인
- parent concept이 explicit TSV에 있는 경우에만 붙는지 확인

완료 기준:

- Stage 5는 label normalization만 수행하고 graph repair를 하지 않음
- 2026-07-01 현재 `outputs/stage5_eval100/` 생성 완료
- eval100 summary: canonical mentions 1253, canonical edges 694
- header-only lexicon 상태라 canonical source는 전부 `raw_fallback`, parent는 전부 empty
- local mention id collision 방지를 위해 canonical edge lookup은 `(caption_id, mention_id)` 기준으로 수행

## 8. Milestone 7: Stage 6 구현

대상 rule:

- R24 Count export

작업:

1. `stage6_export_counts.py` 작성
2. object count export
3. attribute count export
4. object-attribute pair count export
5. action count export
6. agent/patient pair count export
7. relation triple count export
8. object co-occurrence pair count export

산출물:

- TSV 또는 JSONL count tables
- flat fact rows

검증:

- count export에서 새 mention이나 edge가 생성되지 않는지 확인
- count row가 raw evidence와 Rule ID로 역추적 가능한지 확인
- object co-occurrence pair는 같은 caption 기준으로만 계산되는지 확인

완료 기준:

- count export는 집계만 수행함

## 9. Milestone 8: Sample inspection report

목표:

- 사람이 rule 동작을 눈으로 확인할 수 있는 sample report를 만든다.

작업:

1. `inspect_sample_v1.py` 작성
2. 20개 caption sample report 생성
3. 각 caption에 대해 아래 항목 표시

표시 항목:

- raw caption
- caption shape
- tag-list 여부
- skipped 여부와 skip reason
- protected tokens
- POS/TAG/lemma/dependency
- noun chunks
- raw mentions
- raw edges
- canonical labels
- count facts

검증:

- report가 rule 설명용인지 확인
- report에서 새 rule 판단이 일어나지 않는지 확인

완료 기준:

- 20개 sample을 보고 pipeline 흐름을 설명할 수 있음

## 10. Milestone 9: Regression tests

목표:

- v1 rule이 의도치 않게 늘어나거나 섞이는 것을 막는다.

테스트 항목:

- quote는 object로 count되지 않음
- object MWE lexicon에 있는 phrase만 merge됨
- tag-list caption이 comma segment extractor로 빠지지 않음
- tag-list caption이 sentence pipeline으로도 들어가지 않음
- tag-list caption이 `tag_list_deferred`로 skip됨
- relation MWE collapse가 일어나지 않음
- `pobj`는 action patient로 들어가지 않음
- pronoun resolution이 일어나지 않음
- passive voice normalization이 일어나지 않음
- count export에서 새 interpretation이 일어나지 않음

완료 기준:

- rule boundary를 깨는 변경이 test에서 잡힘

## 11. Milestone 10: Small benchmark

목표:

- 구현이 너무 느리지 않은지 rough speed만 확인한다.

범위:

- 100 captions
- 1,000 captions
- 필요하면 10,000 captions

측정:

- captions/sec
- stage별 소요 시간
- memory rough check

주의:

- benchmark 결과를 보고 rule을 patch하지 않는다.
- 정확도 개선은 rule 변경 절차를 거친다.

## 12. 구현 순서 요약

권장 순서:

1. schema 문서와 schema code
2. Stage 1
3. Stage 2
4. Stage 3
5. Stage 4 object/attribute/quantity
6. Stage 4 action/agent/patient
7. Stage 4 relation
8. Stage 5 canonicalization
9. Stage 6 count export
10. sample inspection report
11. regression tests
12. small benchmark

## 13. 구현 중 금지 체크리스트

아래 항목이 필요해 보이면 즉시 구현을 멈추고 `docs/rules_v1.md` 변경 여부를 먼저 논의한다.

- pronoun을 antecedent에 연결하고 싶어짐
- `the object`, `the device`를 앞 object와 merge하고 싶어짐
- passive voice를 active role로 바꾸고 싶어짐
- `in front of`, `on top of`를 하나의 relation으로 collapse하고 싶어짐
- `look at`, `pick up` 같은 phrasal action을 collapse하고 싶어짐
- self-edge를 repair하고 싶어짐
- count export에서 누락된 row를 보정하고 싶어짐
- GPIC sample을 보고 특정 단어를 Python set에 추가하고 싶어짐

v1에서는 이런 상황을 limitation으로 남긴다.
