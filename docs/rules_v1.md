# V1 Explainable Rule Set

이 문서는 GPIC caption을 countable concept으로 바꾸기 위한 v1 baseline rule을 고정한다.

목표는 누락을 최소화하는 것이 아니라, 각 산출물이 어떤 rule에서 나왔는지 설명 가능한 baseline을 만드는 것이다.

현재 구현 상태:

- Stage 1 caption shape 판단 구현됨
- Stage 2 spaCy preprocessing 구현됨
- Stage 3 spaCy linguistic annotation은 `en_core_web_trf` 기준으로 구현됨
- Stage 4 raw concept extraction 구현됨
- Stage 5 canonicalization 구현됨
- Stage 6 count export 구현됨
- object MWE lexicon은 `resources/lexicons/object_mwes.tsv`에 header-only로 생성됨
- Stage 2 output은 concept output이 아니라 token/span inspection output임

## 0. Output 목표

최종 산출물은 문장 재생성이 아니다.

최종 산출물은 아래 count table을 만들 수 있는 구조화 records다.

- object count
- attribute count
- object-attribute pair count
- action count
- agent/patient pair count
- relation triple count
- object co-occurrence pair count

## 1. Six-Stage Pipeline

| Stage | 이름 | 입력 | 출력 | 핵심 원칙 |
|---|---|---|---|---|
| 1 | Caption shape 판단 | raw caption row | sentence 또는 tag-list shape label | caption 종류를 판단한다. tag-list는 v1 extraction 대상에서 제외한다. |
| 2 | spaCy preprocessing | caption text | protected spaCy Doc | tokenization 후 깨지면 안 되는 span만 merge한다. |
| 3 | spaCy linguistic annotation | protected spaCy Doc | token, POS, TAG, MORPH, lemma, dependency, noun chunk | spaCy annotation과 최소 POS correction만 한다. concept extraction은 하지 않는다. |
| 4 | Raw concept extraction | annotated Doc | raw mentions, raw edges | dependency와 noun chunk에서 직접 보이는 것만 추출한다. |
| 5 | Canonicalization | raw mentions, raw edges | canonical labels, parent concepts | explicit lexicon 기반으로만 단순화한다. relation은 raw-preserving이다. |
| 6 | Count export | canonical mentions, canonical edges | count tables, fact rows | 새 해석을 하지 않고 집계만 한다. |

## 2. Rule Table

| Rule ID | Stage | Rule 이름 | 입력 | 출력 | 도구 | 도구 유형 | Rule 유형 | Count 영향 | Known limitation |
|---|---:|---|---|---|---|---|---|---|---|
| R1 | 1 | Caption shape 판단 | raw GPIC caption row의 `caption_type` | `sentence` 또는 `tag_list` | custom router | custom fixed rule | baseline | 처리 path 결정 | GPIC `caption_type` 값이 알려진 집합 밖이면 처리하지 않음 |
| R1.1 | 1 | Tag-list skip | `tag_list` caption | skipped record with reason | custom router | custom fixed rule | baseline exclusion | tag-list count 제외 | tag-list extraction은 v1에서 보류 |
| R2 | 2 | Tokenization | caption text | spaCy tokens | spaCy tokenizer | spaCy rule-based | baseline | 직접 count 없음 | tokenizer error가 뒤로 전파됨 |
| R3 | 2 | Quote span merge | tokenized quote span | merged quote token | custom quote detector + spaCy Retokenizer | custom fixed rule + spaCy rule-based | baseline | quote가 object로 오염되는 것을 줄임 | unmatched quote는 복구하지 않음 |
| R4 | 2 | Object MWE merge | tokens, object MWE lexicon | merged object token | object lexicon + spaCy PhraseMatcher + spaCy filter_spans + spaCy Retokenizer | custom lexicon lookup + spaCy rule-based | baseline | object count 안정화 | lexicon에 없는 MWE는 merge하지 않음 |
| R5 | 2 | Hyphen word merge | hyphen-connected word tokens | merged hyphen token | custom hyphen detector + spaCy Retokenizer | custom fixed rule + spaCy rule-based | baseline | hyphen lexical unit 보존 | numeric range와 symbol expression은 제외 |
| R6 | 3 | TAG annotation | protected Doc | token TAG | spaCy tagger | spaCy learned | baseline evidence | 직접 count 없음 | model error가 뒤로 전파됨 |
| R7 | 3 | Object MWE POS correction | Step 2에서 merge된 object MWE token | POS=`NOUN`, TAG=`NN` | custom component | custom fixed rule | baseline | merged object가 noun chunk/object 후보가 되도록 보정 | Step 2에서 merge된 object MWE에만 적용 |
| R8 | 3 | Dependency parsing | protected Doc | dependency tree | spaCy parser | spaCy learned | baseline evidence | 직접 count 없음 | attachment error가 뒤로 전파됨 |
| R9 | 3 | POS, MORPH annotation | tagged/parsed Doc | POS, MORPH | spaCy attribute_ruler | spaCy rule-based | baseline evidence | 직접 count 없음 | spaCy model 설정에 의존 |
| R10 | 3 | Lemmatization | annotated Doc | token lemma | spaCy lemmatizer | spaCy rule-based | baseline evidence | canonicalization 입력 | lemma는 canonical이 아님 |
| R11 | 3 | Noun chunking | annotated Doc | noun chunks | spaCy noun_chunks | spaCy rule-based over parse | baseline evidence | object/attribute 추출 입력 | spaCy가 놓친 chunk는 v1에서 복구하지 않음 |
| R12 | 4 | Noun chunk root to object | noun chunk | object mention | custom rule over spaCy noun chunk | custom fixed rule | baseline extraction | object count | pronoun/reference/context repair 없음 |
| R13 | 4 | Noun chunk modifier to attribute | noun chunk modifier | attribute mention, has_attribute edge | custom rule over chunk tokens | custom fixed rule | baseline extraction | attribute count, object-attribute pair count | chunk 밖 floating attribute는 붙이지 않음 |
| R14 | 4 | Noun chunk modifier to quantity | numeric or quantity-like chunk modifier | quantity mention, has_quantity edge | custom rule + small quantity lexicon | custom fixed rule + custom lexicon lookup | baseline extraction | quantity count | ambiguous quantity는 raw로 남김 |
| R15 | 4 | VERB to action | VERB token | action mention | custom rule over POS | custom fixed rule | baseline extraction | action count | auxiliary/state ambiguity 남음 |
| R16 | 4 | `nsubj` to agent | VERB token, `nsubj` child | action-agent edge | custom rule over dependency | custom fixed rule | baseline extraction | agent/patient pair count | passive voice normalize 안 함 |
| R17 | 4 | `obj` or `dobj` to patient | VERB token, `obj` or `dobj` child | action-patient edge | custom rule over dependency | custom fixed rule | baseline extraction | agent/patient pair count | prepositional object는 patient로 쓰지 않음 |
| R18 | 4 | ADP plus direct `pobj` to relation | ADP/preposition token, direct `pobj` child | source-relation-target edge | custom rule over dependency | custom fixed rule | baseline extraction | relation triple count | multi-word preposition collapse 없음 |
| R19 | 5 | Object synonym canonicalization | raw object lemma | canonical object | explicit TSV lexicon | custom lexicon lookup | baseline canonicalization | canonical object count | unknown object는 raw lemma 유지 |
| R20 | 5 | Attribute synonym and type canonicalization | raw attribute lemma | canonical attribute, attribute type | explicit TSV lexicon | custom lexicon lookup | baseline canonicalization | canonical attribute count | unknown attribute는 raw lemma 유지 |
| R21 | 5 | Quantity raw-preserving canonicalization | raw quantity lemma | same quantity label | no extra tool | fixed policy | baseline canonicalization | quantity count | quantity normalization은 아직 하지 않음 |
| R22 | 5 | Action synonym canonicalization | raw action lemma | canonical action | explicit TSV lexicon | custom lexicon lookup | baseline canonicalization | canonical action count | unknown action은 raw lemma 유지 |
| R23 | 5 | Parent concept mapping | canonical label | parent concept | explicit TSV lexicon | custom lexicon lookup | baseline canonicalization | parent count | ontology traversal 아님 |
| R24 | 5 | Relation raw-preserving | raw relation lemma | same relation label | no extra tool | fixed policy | baseline canonicalization | relation count | `in front of` 같은 MWE relation은 아직 단순화하지 않음 |
| R25 | 6 | Count export | canonical mentions and edges | count tables, fact rows | exporter | custom fixed rule | baseline export | final output | 새 linguistic interpretation 금지 |

## 3. Stage별 상세 기준

### Stage 1. Caption shape 판단

하는 일:

- raw caption을 `sentence` path 또는 `tag_list` path로 보낸다.

하지 않는 일:

- tokenization
- POS tagging
- object extraction
- tag-list 내부 의미 추론

v1 기준:

- 확인된 GPIC row field인 `caption_type`을 사용한다.
- `caption_type == "tag"`이면 내부 shape를 `tag_list`로 둔다.
- `caption_type in {"short", "medium", "long"}`이면 내부 shape를 `sentence`로 둔다.
- 그 외 `caption_type` 값은 추측하지 않고 error로 처리한다.
- comma 개수, 문장부호, 문장 길이로 tag-list를 추정하지 않는다.
- `tag_list`로 판정되면 v1에서는 Stage 2~6 extraction을 실행하지 않는다.
- `tag_list` caption은 skipped record로 남기고, reason은 `tag_list_deferred`로 기록한다.
- comma-separated segment split, segment별 object/attribute grouping, tag-list 전용 relation 추론은 v1에서 하지 않는다.

### Stage 2. spaCy preprocessing

순서:

1. spaCy tokenizer
2. quote span merge
3. object MWE merge
4. hyphen word merge

object MWE 기준:

- `resources/lexicons/object_mwes.tsv`를 사용한다.
- 현재 v1 초기 파일은 header-only이며 자동으로 추가된 phrase는 없다.
- lexicon에 명시된 phrase만 spaCy PhraseMatcher로 찾고 Retokenizer로 merge한다.

Stage 2 산출물:

- 최종 concept이 아니다.
- token list와 protected span metadata를 inspection용 JSONL로 저장한다.

중요한 제외:

- relation MWE merge 없음
- phrasal action merge 없음
- quote placeholder 치환 없음

### Stage 3. spaCy linguistic annotation

포함:

- 기본 spaCy model은 `en_core_web_trf`
- tagger
- object MWE POS correction
- parser
- attribute_ruler
- lemmatizer
- noun_chunks

하지 않는 일:

- object 생성
- attribute 생성
- action 생성
- relation 생성
- coreference 처리

### Stage 4. raw concept extraction

입력:

- `stage3_records.jsonl`에 저장된 token table, dependency table, noun chunk table
- Stage 4는 spaCy model을 다시 실행하지 않는다.

허용 추출:

- noun chunk root -> object
- noun chunk modifier -> attribute 또는 quantity
- VERB -> action
- `nsubj` -> agent
- `obj`, `dobj` -> patient
- ADP/preposition + direct `pobj` -> relation

세부 기준:

- R12 object는 noun chunk의 `root_i` token에서만 만든다.
- 같은 `root_i`에서 object mention은 caption 안에서 1개만 만든다.
- R13 attribute modifier는 같은 noun chunk 안에서 `dep in {"amod", "compound"}`인 token만 사용한다.
- R14 quantity modifier는 같은 noun chunk 안에서 `dep == "nummod"` 또는 `pos == "NUM"`인 token만 사용한다.
- R15 action은 `pos == "VERB"`인 token에서만 만든다.
- R16 agent edge는 action token의 direct child 중 `dep == "nsubj"`이고 그 child token이 이미 object mention일 때만 만든다.
- R17 patient edge는 action token의 direct child 중 `dep in {"obj", "dobj"}`이고 그 child token이 이미 object mention일 때만 만든다.
- R18 relation edge는 `pos == "ADP"` token의 direct child 중 `dep == "pobj"`가 target object이고, ADP head token이 source object일 때만 만든다.
- Stage 4는 agent/patient/relation edge를 만들기 위해 새 object mention을 추가하지 않는다.

명시적 제외:

- `pobj`를 action patient로 쓰지 않는다.
- passive voice를 고치지 않는다.
- relation source disambiguation을 하지 않는다.
- self-edge repair를 하지 않는다.
- pronoun/reference resolution을 하지 않는다.
- scene context fallback을 하지 않는다.

### Stage 5. canonicalization

허용:

- object synonym lookup
- attribute synonym lookup
- attribute type lookup
- quantity raw-preserving
- action synonym lookup
- parent concept lookup
- relation raw-preserving

금지:

- canonicalization 단계에서 새 object를 만들지 않는다.
- canonicalization 단계에서 agent/patient를 고치지 않는다.
- canonicalization 단계에서 relation source/target을 바꾸지 않는다.

### Stage 6. count export

허용 count:

- object count
- attribute count
- object-attribute pair count
- action count
- agent/patient pair count
- relation triple count
- object co-occurrence pair count

금지:

- count export에서 새 rule 적용 금지
- count export에서 누락 복구 금지
- count export에서 semantic repair 금지

## 4. Explicitly Excluded From V1

아래 기능은 v1에서 구현하지 않는다.

| 제외 항목 | 이유 |
|---|---|
| pronoun resolution | antecedent scoring이 필요해 설명 가능성이 떨어짐 |
| generic anaphora resolution | `the object`, `the device` 같은 표현의 antecedent 선택이 필요함 |
| `one`, `another`, `others`, `both` splitting | subgroup과 instance modeling이 필요함 |
| passive voice normalization | raw dependency 기준을 넘어 semantic role rewrite가 필요함 |
| inherited agent repair | 후처리 patch가 되기 쉬움 |
| skipped reference role recovery | 앞선 repair 실패를 다시 고치는 구조가 됨 |
| self-edge repair | coreference/relation repair에 의존함 |
| PP source disambiguation | relation source 선택에 semantic scoring이 필요함 |
| with-absolute recovery | spaCy가 놓친 object를 patch rule로 복구하는 구조가 됨 |
| scene context fallback | object/context 분리 rule이 복잡해짐 |
| tag-list segment-specific extraction | comma segment split과 segment별 object/attribute grouping이 새 rule을 필요로 함 |
| tag-list same-pipeline extraction | tag-list를 문장처럼 parsing하면 입력 형식 mismatch로 dependency/noun chunk가 흔들림 |
| relation MWE collapse | v1 계획 밖. relation은 raw-preserving |
| phrasal action collapse | v1 계획 밖. action은 VERB lemma 기반 |
| LLM extraction | v1은 rule-based baseline |
| GPIC error-specific patch | rule 설명성이 무너짐 |

## 5. Rule Change Protocol

새 rule을 추가하려면 먼저 이 문서에 아래 형식으로 추가한다.

구현은 그 다음이다.

필수 항목:

- Rule ID
- Stage
- 입력
- 출력
- 도구
- 도구 유형
- Rule 유형
- Count 영향
- Known limitation

승인 전에는 코드에 넣지 않는다.
