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
- Stage 2 object MWE retokenization은 비활성화됨
- object span/MWE 판단은 GPIC caption에서 관측한 object span inventory를 기준으로 수행함
- attribute synset/canonical 판단은 GPIC caption에서 관측한 attribute inventory를 기준으로 offline 준비함
- attribute type taxonomy는 아직 active Stage 5/6 output에 붙이지 않고 offline audit artifact로만 둠
- preposition MWE는 Stage 4에서 lexicon span으로 감지하고 relation edge/count 및 ambiguous relation occurrence count에 사용함
- COCO/LVIS/Objects365/OpenImages/Visual Genome source-label inventory는 active pipeline 입력이 아님
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
- relation component count
- ambiguous relation occurrence count
- object co-occurrence pair count

## 1. Six-Stage Pipeline

| Stage | 이름 | 입력 | 출력 | 핵심 원칙 |
|---|---|---|---|---|
| 1 | Caption shape 판단 | raw caption row | sentence 또는 tag-list shape label | caption 종류를 판단한다. tag-list는 v1 extraction 대상에서 제외한다. |
| 2 | spaCy preprocessing | caption text | protected spaCy Doc | tokenization 후 깨지면 안 되는 span만 merge한다. |
| 3 | spaCy linguistic annotation | protected spaCy Doc | token, POS, TAG, MORPH, lemma, dependency, noun chunk | spaCy annotation만 한다. concept extraction은 하지 않는다. |
| 3.5 | GPIC observed object and attribute inventories | Stage 3 records | observed object span inventory, observed attribute inventory | GPIC caption noun chunk에서 관측된 object span과 attribute modifier만 OEWN lookup하고 ambiguous는 offline으로 해결한다. |
| 4 | Raw concept extraction | annotated Doc + GPIC object inventory | raw mentions, raw edges | GPIC inventory에서 확정된 noun chunk selected span과 dependency에서 직접 보이는 것만 추출한다. |
| 5 | Canonicalization | raw mentions, raw edges | canonical labels, selected synset metadata, parent evidence | object는 GPIC observed inventory의 canonical surface, selected synset metadata, immediate hypernym parent evidence를 보존한다. inventory canonical이 없으면 raw surface로 남긴다. single ADP relation은 raw-preserving이고 preposition MWE relation은 Stage 4 lexicon canonical label을 보존한다. |
| 6 | Count export | canonical mentions, canonical edges | count tables, fact rows | 새 해석을 하지 않고 집계만 한다. |

## 2. Rule Table

| Rule ID | Stage | Rule 이름 | 입력 | 출력 | 도구 | 도구 유형 | Rule 유형 | Count 영향 | Known limitation |
|---|---:|---|---|---|---|---|---|---|---|
| R1 | 1 | Caption shape 판단 | raw GPIC caption row의 `caption_type` | `sentence` 또는 `tag_list` | custom router | custom fixed rule | baseline | 처리 path 결정 | GPIC `caption_type` 값이 알려진 집합 밖이면 처리하지 않음 |
| R1.1 | 1 | Tag-list skip | `tag_list` caption | skipped record with reason | custom router | custom fixed rule | baseline exclusion | tag-list count 제외 | tag-list extraction은 v1에서 보류 |
| R2 | 2 | Tokenization | caption text | spaCy tokens | `en_core_web_trf` tokenizer-only `nlp.make_doc()` | spaCy rule-based tokenizer | baseline | 직접 count 없음 | tokenizer error가 뒤로 전파됨 |
| R3 | 2 | Quote span merge | tokenized quote span | merged quote token | custom quote detector + spaCy Retokenizer | custom fixed rule + spaCy rule-based | baseline | quote가 object로 오염되는 것을 줄임 | unmatched quote는 복구하지 않음 |
| R4 | 2 | Reserved: no object MWE retokenization | 없음 | 없음 | 없음 | inactive | removed baseline rule | 직접 count 없음 | object MWE는 Stage 4 selected span에서 처리 |
| R5 | 2 | Hyphen word merge | hyphen-connected word tokens | merged hyphen token | custom hyphen detector + spaCy Retokenizer | custom fixed rule + spaCy rule-based | baseline | hyphen lexical unit 보존 | numeric range와 symbol expression은 제외 |
| R6 | 3 | TAG annotation | protected Doc | token TAG | spaCy tagger | spaCy learned | baseline evidence | 직접 count 없음 | model error가 뒤로 전파됨 |
| R7 | 3 | Reserved: no object MWE POS correction | 없음 | 없음 | 없음 | inactive | removed baseline rule | 직접 count 없음 | Stage 2 object MWE merge가 없으므로 보정도 없음 |
| R8 | 3 | Dependency parsing | protected Doc | dependency tree | spaCy parser | spaCy learned | baseline evidence | 직접 count 없음 | attachment error가 뒤로 전파됨 |
| R9 | 3 | POS, MORPH annotation | tagged/parsed Doc | POS, MORPH | spaCy attribute_ruler | spaCy rule-based | baseline evidence | 직접 count 없음 | spaCy model 설정에 의존 |
| R10 | 3 | Lemmatization | annotated Doc | token lemma | spaCy lemmatizer | spaCy rule-based | baseline evidence | canonicalization 입력 | lemma는 canonical이 아님 |
| R11 | 3 | Noun chunking | annotated Doc | noun chunks | spaCy noun_chunks | spaCy rule-based over parse | baseline evidence | object/attribute 추출 입력 | spaCy가 놓친 chunk는 v1에서 복구하지 않음 |
| R11.1 | 3.5 | GPIC observed attribute inventory lookup | Stage 3 noun chunks, consumed object core token ids | observed attribute inventory rows | custom rule over Stage 3 records + OEWN lookup | custom fixed rule + external lexical evidence | offline inventory preparation | 직접 count 없음. Stage 4 attribute count를 위한 offline evidence | noun chunk 내부 selected object core span 밖 `amod`/`compound`/`nmod` token만 후보로 삼음 |
| R11.2 | 3.5 | Offline attribute canonical inventory build | selected attribute synset rows | canonical attribute surface evidence | OEWN lemma evidence, WN3 count evidence, optional Google Ngram evidence | fixed policy over offline evidence | offline canonical preparation | 직접 count 없음. Stage 5 attribute canonicalization 준비 | selected synset이 없으면 canonical inventory에서는 적용 불가로 둠 |
| R11.3 | 3.5 | Offline attribute parent taxonomy build | selected/canonical attribute inventory | offline attribute parent/type taxonomy artifact | manual taxonomy decision | explicit manual decision | offline taxonomy preparation | 직접 count 없음. active Stage 5/6에는 아직 반영하지 않음 | attribute parent/type은 OEWN hypernym이 아니라 taxonomy 방식이며 active output에서는 보류 |
| R11.4 | 3.5 | Offline action canonical inventory build | resolved observed action inventory | canonical action surface evidence | OEWN verb lemma evidence, WN3 count evidence, optional Google Ngram evidence | fixed policy over offline evidence | offline canonical preparation | 직접 count 없음. R22 action canonicalization 준비 | `raw_fallback` action row는 selected synset이 없으므로 canonical inventory 적용 불가로 둠 |
| R11.5 | 3.5 | Offline action canonical export | completed action canonical inventory | Stage 5 `action_synonyms.tsv` rows | generated TSV export from completed inventory | deterministic export | lexicon bundle preparation | R22 action count key에 영향 | canonical ambiguous 또는 non-chosen row는 export하지 않음 |
| R12 | 4 | Noun chunk selected span to object | noun chunk, GPIC observed object inventory | object mention with selected span metadata | custom rule over spaCy noun chunk + GPIC inventory lookup | custom fixed rule + inventory lookup | baseline extraction | object count | inventory row가 있으면 `chosen`/`excluded` 모두 object mention으로 세며, `needs_manual` 또는 selected synset의 unresolved canonical row는 Stage 4를 중단함 |
| R13 | 4 | Noun chunk modifier to attribute | noun chunk modifier | attribute mention, has_attribute edge | custom rule over chunk tokens | custom fixed rule | baseline extraction | attribute count, object-attribute pair count | chunk 밖 floating attribute는 붙이지 않음 |
| R14 | 4 | Noun chunk modifier to quantity | numeric or quantity-like chunk modifier | quantity mention, has_quantity edge | custom rule + small quantity lexicon | custom fixed rule + custom lexicon lookup | baseline extraction | quantity count | ambiguous quantity는 raw로 남김 |
| R15 | 4 | VERB or selected phrasal action span to action | VERB token, optional particle/preposition child evidence, OEWN verb lookup, relation MWE consumed token ids | action mention with selected action span metadata | custom rule over POS/dependency + OEWN verb lookup | custom fixed rule + external lexical evidence | baseline extraction | action count | no OEWN verb span이면 single VERB raw fallback. relation MWE token은 phrasal action 후보에서 제외 |
| R16 | 4 | `nsubj` to agent | VERB token, `nsubj` child | action-agent edge | custom rule over dependency | custom fixed rule | baseline extraction | agent/patient pair count | passive voice normalize 안 함 |
| R17 | 4 | Object dependency to patient | action head token or selected phrasal action preposition, object child | action-patient edge | custom rule over dependency + selected action span map | custom fixed rule | baseline extraction | agent/patient pair count | default `pobj`는 patient가 아니며, selected phrasal action span이 소비한 ADP의 direct `pobj`만 patient 후보로 사용 |
| R18 | 4 | Single ADP plus direct `pobj` to relation | ADP/preposition token, direct `pobj` child | source-relation-target edge | custom rule over dependency | custom fixed rule | baseline extraction | relation triple count | selected phrasal action span 또는 relation MWE span에 소비된 ADP는 single-ADP relation에서 제외 |
| R18.1 | 4 | Preposition MWE plus final `pobj` to relation | preposition MWE lexicon span, initial relation token head, final ADP direct `pobj` child | source-relation-target edge or ambiguous relation candidate edge with canonical relation MWE label and component metadata | custom span matcher + TSV lexicon + dependency evidence | custom fixed rule + custom lexicon lookup | baseline extraction | relation triple count, relation component count, ambiguous relation occurrence count | action-attached MWE with multiple object-mapped child source or target candidates is not disambiguated; candidate pairs are preserved separately but counted once per matched MWE occurrence |
| R19 | 5 | Object canonicalization from GPIC inventory | raw object surface, selected synset metadata, canonical surface evidence | canonical object label | GPIC observed object inventory source detail | fixed policy over offline canonical decision | baseline canonicalization | canonical object count | canonical surface가 없으면 raw surface 유지 |
| R20 | 5 | Attribute synonym canonicalization | raw attribute surface | canonical attribute | explicit TSV lexicon | custom lexicon lookup | baseline canonicalization | canonical attribute count | attribute type은 active output에서 보류. unknown attribute는 raw surface 유지 |
| R21 | 5 | Quantity raw-preserving canonicalization | raw quantity lemma | same quantity label | no extra tool | fixed policy | baseline canonicalization | quantity count | quantity normalization은 아직 하지 않음 |
| R22 | 5 | Action synonym canonicalization | raw action surface | canonical action | explicit TSV lexicon | custom lexicon lookup | baseline canonicalization | canonical action count | action parent_concepts lexicon은 아직 없음 |
| R23 | 5 | Object parent concept mapping | selected OEWN synset parent evidence | object parent display labels plus synset-id evidence | GPIC object inventory source detail | fixed policy over OEWN hypernym evidence | baseline canonicalization | object parent count | selected synset이 없으면 parent는 empty. 내부 근거는 synset ID이고, 사람이 보는 parent label은 parent lemma display를 먼저 쓴다. |
| R24 | 5 | Relation canonicalization | raw single-ADP relation label or preposition MWE label | single ADP는 raw-preserving, preposition MWE는 Stage 4 lexicon canonical relation label 유지 | no extra tool | fixed policy over Stage 4 evidence | baseline canonicalization | relation count | Stage 5에서 relation source/target 또는 label을 새로 추론하지 않음 |
| R25 | 6 | Count export | canonical mentions and edges | count tables, fact rows | exporter | custom fixed rule | baseline export | final output | 새 linguistic interpretation 금지. relation component와 ambiguous relation candidate는 Stage 4 relation MWE metadata에서만 생성 |

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

1. `en_core_web_trf` tokenizer-only `nlp.make_doc()`
2. quote span merge
3. hyphen word merge

object MWE 기준:

- Stage 2에서는 object MWE를 merge하지 않는다.
- object MWE 또는 multi-word object 여부는 Stage 4에서 noun chunk 내부 selected span으로 판단한다.

Stage 2 산출물:

- 최종 concept이 아니다.
- token list와 protected span metadata를 inspection용 JSONL로 저장한다.

중요한 제외:

- relation MWE retokenization 없음. preposition MWE는 Stage 4에서 span metadata로만 처리
- phrasal action merge 없음
- quote placeholder 치환 없음
- `spacy.blank("en")` tokenizer 사용 없음

### Stage 3. spaCy linguistic annotation

포함:

- 기본 spaCy model은 `en_core_web_trf`
- tagger
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

### Stage 3.5. GPIC observed object inventory

입력:

- Stage 3 records
- GPIC sentence captions에서 관측된 noun chunk와 token evidence

하는 일:

- noun chunk 내부에서 root를 오른쪽 끝으로 갖는 left-expanding span을 만든다.
- left-expanding span이 DET/ADP/PRON 같은 function-word token으로 시작하면 multiword object 후보로 보지 않는다. 예: `A man`은 `aman` lookup으로 보내지 않고 `man`을 본다.
- 각 span을 GPIC observed surface로 보고 OEWN noun lookup을 수행한다.
- span head가 plural common noun이면 head lemma surface를 observed exact surface보다 먼저 lookup한다. 예: `men` -> `man`, `windows` -> `window`.
- plural common noun이 아니면 observed exact surface를 먼저 lookup한다.
- `joined_variant`처럼 space, hyphen, underscore를 제거해서 붙인 query로만 잡힌 span은 자동 `chosen`으로 올리지 않고 `needs_manual`로 둔다. 예: `A man -> aman`, `black shirt -> blackshirt`, `black top -> blacktop`.
- OEWN noun synset이 있는 가장 긴 span을 inventory row로 남긴다.
- selected synset이 있는 row는 selected synset의 immediate hypernym 전체를 parent evidence로 남긴다.
- parent evidence의 식별 기준은 parent synset ID다.
- 사람이 보는 parent label은 parent lemma display를 먼저 쓰고, parent synset ID는 별도 evidence로 함께 보존한다.
- `needs_manual` row가 하나라도 남아 있으면 canonical enrichment로 넘어가지 않는다. synset 선택 또는 objectness 판단이 끝난 뒤에만 canonical surface를 선정한다.
- manual resolution이 끝난 selected synset row는 offline canonical rule로 canonical surface를 선정한다.
- canonical surface 선정은 selected synset lemma set, observed caption surface variants, WN3 lemma count, observed exact surface, 저장된 Google Ngram evidence 순서로 진행한다.
- canonical matching key는 `strip + lowercase`, apostrophe/hyphen normalization, underscore-to-space, whitespace normalization, diacritic folding을 적용한다. 예: `café`는 matching key에서 `cafe`로 비교한다.
- canonical ambiguous가 남으면 `canonical_surface`를 비우고 별도 ambiguous TSV에 기록한 뒤 Stage 4로 진행하지 않는다.
- `decision_status`는 사람이 보는 최종 queue 상태만 기록한다.
  - `chosen`: 이미 고른 것. Stage 4에서 object mention으로 세도 된다.
  - `needs_manual`: 골라야 할 것. synset 선택 또는 objectness 판단을 offline/manual로 끝내야 한다.
  - `excluded`: count에는 넣지만, downstream에서 필터링할 수 있도록 quality/status tag로 남긴다.
- `decision_reason`은 왜 그 queue로 갔는지만 기록한다.
  - `selected_object_compatible`: synset이 선택됐고 object-compatible lexfile이다.
  - `manual_joined_variant_required`: separator 제거로 붙인 query가 synset을 찾았으나 false positive 위험이 있어 manual 확인이 필요하다.
  - `manual_objectness_required`: synset은 선택됐지만 conditional/hard-conflict lexfile이라 objectness 판단이 필요하다.
  - `manual_synset_required`: OEWN noun 후보가 있지만 selected synset이 없다.
  - `no_oewn_noun_synset`: OEWN noun 후보가 없다.
- `objectness_gate`는 `decision_reason`을 설명하는 evidence이며 main status로 쓰지 않는다.

하지 않는 일:

- COCO/LVIS/Objects365/OpenImages/Visual Genome source-label inventory를 읽지 않는다.
- 외부 object dataset label을 GPIC caption span의 synonym 또는 canonical으로 쓰지 않는다.
- `needs_manual` row와 selected synset은 있지만 canonical surface가 비어 있는 row를 extraction 중에 자동으로 fallback하지 않는다.

산출물:

- `resources/gpic_inventory/observed_object_span_inventory.tsv`
- 이 파일은 GPIC caption에서 관측된 span만 담는다.

#### Stage 3.5. GPIC observed attribute inventory

입력:

- Stage 3 records
- Stage 3.5 object inventory에서 결정된 noun chunk selected object span

하는 일:

- noun chunk 내부 selected object lookup span 전체를 무조건 consumed로 보지 않는다.
- selected object의 canonical/core surface가 lookup span의 suffix token span과 매칭되면 그 core suffix token만 consumed로 본다.
- true MWE처럼 object core가 full phrase와 매칭되면 full phrase token이 consumed된다.
- consumed core token을 제외한 noun chunk 내부 token 중 `dep in {"amod", "compound", "nmod"}`이면 attribute 후보로 만든다.
- raw surface는 원문 그대로 보존한다.
- lookup query는 raw surface를 `lowercase + strip`한 값으로 만든다.
- OEWN 2025+에서 lookup한다.
- 없으면 Morphy 후 다시 검색한다.
- 그래도 없으면 selected synset은 비워 두되 `decision_status=chosen`, `decision_reason=no_oewn_attribute_synset`으로 남긴다. synset search에서는 제외하지만 count 후보에는 남긴다.
- 통합 attribute inventory에 selected synset이 있으면 그 selected synset을 사용한다.
- OEWN 2025+ 검색 결과 synset이 하나면 그 synset을 선택한다.
- OEWN 2025+ 검색 결과 synset이 여러 개면 sense key 기준 WordNet 3.0 lemma count를 사용한다.
  - lemma count > 0인 attribute-compatible 항목 중 최대값이 유일하면 선택한다.
  - 최대값이 동률이면 ambiguous로 둔다.
  - lemma count > 0인 conditional 항목 중 최대값이 유일하면 선택한다.
  - 최대값이 동률이면 ambiguous로 둔다.
  - attribute-compatible, conditional 후보가 없으면 그 외 항목 중 최대값이 유일할 때 선택한다.
  - 다시 최대값이 동률이면 ambiguous로 둔다.
  - lemma count가 모두 0이면 ambiguous로 둔다.
  - sense key 기준 WordNet 3.0 synset이 하나도 검색되지 않으면 ambiguous로 둔다.
- lookup query는 생성됐는데 OEWN API 결과가 비정상적이면 report한다.
- OEWN lexfile gate:
  - attribute-compatible은 auto selected 가능하다.
  - conditional과 hard_conflict는 `needs_manual`로 보내 manual 확인 대상으로 둔다.

attribute-compatible lexfiles:

- `adj.all`
- `adj.pert`
- `adj.ppl`
- `noun.attribute`
- `noun.shape`
- `noun.state`
- `noun.substance`

conditional lexfiles:

- `noun.Tops`
- `noun.act`
- `noun.animal`
- `noun.artifact`
- `noun.body`
- `noun.cognition`
- `noun.communication`
- `noun.event`
- `noun.food`
- `noun.group`
- `noun.location`
- `noun.object`
- `noun.person`
- `noun.phenomenon`
- `noun.plant`
- `noun.possession`
- `noun.process`
- `noun.quantity`
- `noun.relation`
- `noun.time`
- `verb.body`
- `verb.change`
- `verb.cognition`
- `verb.communication`
- `verb.competition`
- `verb.consumption`
- `verb.contact`
- `verb.creation`
- `verb.emotion`
- `verb.motion`
- `verb.perception`
- `verb.possession`
- `verb.social`
- `verb.stative`
- `verb.weather`

hard_conflict lexfiles:

- `adv.all`
- `noun.feeling`
- `noun.motive`

attribute status:

- `chosen`: selected synset이 있고 attribute-compatible gate를 통과함
- `needs_manual`: selected synset은 있으나 conditional/hard_conflict gate 때문에 사람이 봐야 하거나, OEWN 후보가 여러 개이고 rule로 selected synset을 못 고름. 구체적 원인은 `decision_reason`과 `synset_selection_tag`에 남김
- `excluded`: manual decision으로 downstream에서 구분해야 하는 attribute-like row. count에는 남기되 status로 보존함
- OEWN 후보가 없는 row도 `chosen`으로 남기되 `decision_reason=no_oewn_attribute_synset`과 빈 selected synset으로 구분한다.

offline attribute canonical inventory build:

- canonical enrichment로 넘어갈 수 있는 status는 `chosen`, `excluded`이다.
- `needs_manual` row가 남아 있으면 canonical enrichment를 중단한다.
- manual feedback에서 `decision_status=chosen`이어도 `selected_oewn_synset`이 비어 있으면 canonical surface를 정하지 않는다. count에는 raw surface로 남길 수 있도록 빈 selected synset evidence를 보존한다.
- `excluded` row는 selected synset 유무와 무관하게 canonical 대상이 아니다. `canonical_surface`와 `canonical_label_key`는 비우고 `canonical_selection_tag=not_applicable_excluded`로 표시한다.
- selected synset이 없으면 canonical surface를 정하지 않는다. `canonical_surface`와 `canonical_label_key`는 비우고 `canonical_selection_tag=not_applicable_no_selected_synset`으로 표시한다.
- input manual feedback TSV에 `canonical_surface` 또는 `manual_*` canonical tag가 있어도 canonical decision으로 쓰지 않는다.
- canonical surface는 이 단계가 selected synset evidence를 기준으로 처음부터 다시 계산한다.
- selected synset이 있으면 selected synset 안 WordNet/OEWN lemma를 가져온다.
- observed caption에서 생성한 surface variants와 형태 매칭되는 lemma만 남긴다.
  - lowercase + strip
  - morphy
  - space/underscore variants
  - hyphen space/underscore variants
  - 필요하면 separator 제거 variant
- 남은 OEWN lemma 후보가 하나면 canonical로 선택한다.
- 남은 OEWN lemma 후보가 여러 개라면 lemma.count()를 비교하여 단독 최대를 canonical로 선택한다.
- count가 전부 0이거나 동률이면 observed caption span surface와 동일한 lemma를 canonical로 선정한다.
  - 동일한 lemma가 없으면 selected synset의 전체 lemma set으로 되돌린 뒤 Google Ngram 기준 frequency를 비교한다.
  - 2개 이상이 남으면 남은 항목 기준 Google Ngram(2000-2019) frequency를 비교한다.
- 그래도 동률이면 ambiguous로 두고 manual로 결정한다.

offline attribute parent inventory build:

- attribute parent는 OEWN hypernym이 아니라 taxonomy 방식으로 manual 결정한다.
- attribute type도 canonical script가 정하지 않고 offline/manual taxonomy decision으로 채울 수 있다.
- type decision은 offline artifact의 `attribute_type`, `attribute_type_selection_tag`, `attribute_type_reason`에 기록할 수 있다.
- active Stage 5/6/report는 아직 attribute type을 사용하지 않는다.
- Stage 5는 typed inventory TSV를 직접 읽지 않는다. Stage 5용 lexicon bundle export는 attribute synonym만 활성화한다.
- active lexicon export 기준:
  - `decision_status=chosen`이고 `canonical_surface`가 있으면 `attribute_synonyms.tsv`에 `raw -> canonical`을 쓴다.
  - `decision_status=excluded` row는 `attribute_synonyms.tsv`에 쓰지 않는다.
  - selected synset이 없어 canonical surface가 비어 있는 row는 `attribute_synonyms.tsv`에 쓰지 않는다.
  - `attribute_types.tsv`는 active Stage 5용으로 export하지 않는다.
  - manual feedback에 canonical 값이 있더라도 `excluded` row의 canonical synonym으로 쓰지 않는다.

산출물:

- `resources/gpic_inventory/observed_attribute_inventory.tsv`
- 이 파일은 GPIC caption에서 관측된 attribute modifier만 담는다.

#### Stage 3.5. Preposition MWE lexicon bundle

입력:

- 외부 preposition MWE 후보 inventory
- manual keep/drop review가 끝난 preposition MWE row
- Google Ngram에서 관측된 user-approved generated spatial relation pattern row

하는 일:

- active runtime lexicon은 `resources/lexicons/preposition_mwes.tsv`에 둔다.
- lexicon row는 caption에서 실제 matching할 token sequence와 canonical relation label을 분리해서 보존한다.
- canonical relation label은 preposition MWE entry를 `lowercase + strip`한 값이다.
- matching token sequence는 실제 caption surface와 맞아야 하므로 source lemma만 있고 관측 surface가 다른 row는 관측 surface variant를 matcher에 넣는다.
- user-approved Google Ngram relation pattern row는 `term`을 matching token sequence와 canonical relation label로 같이 사용한다.
- Google Ngram relation pattern row는 `ngram_found == yes`이고 `ngram_status == ok`인 row만 active lexicon에 넣는다.
- relation component는 canonical relation label을 token 단위로 나눈 metadata다.

하지 않는 일:

- Stage 2 retokenization을 하지 않는다.
- preposition MWE lexicon으로 object/action/relation을 새로 의미 추론하지 않는다.
- target object가 dependency/object mapping에서 확인되지 않으면 relation edge를 만들지 않는다.
- source object가 직접 확인되지 않더라도 R18.1의 action-attached direct object-mapped child 후보 규칙 밖에서는 source를 복구하지 않는다.

#### Stage 3.5. GPIC observed action canonical inventory

Input:

- resolved GPIC observed action inventory

Rules:

- If any action inventory row still has `decision_status=needs_manual`, action
  canonical enrichment stops.
- `raw_fallback` rows have no selected synset, so canonical inventory is marked
  not applicable for those rows.
- `chosen` rows must have `selected_oewn_synset`.
- For selected synset rows, collect OEWN verb lemmas from the selected synset.
- Keep lemmas that match observed action surface variants or `selected_query`.
  - `lowercase + strip`
  - verb-head Morphy
- If one OEWN lemma candidate remains, use it as canonical.
- If multiple candidates remain, use the unique maximum WN3 lemma count.
- If counts are all zero or tied, prefer a lemma matching observed action
  surface or `selected_query`.
- If still unresolved, optional Google Ngram evidence may choose a unique max.
- If still unresolved, leave `canonical_surface` empty and write the row to the
  canonical ambiguous TSV.
- If any canonical ambiguous row remains, do not export the row as an R22 active
  action synonym.
- When no canonical ambiguous row remains, selected `chosen` rows may be
  exported to Stage 5 `action_synonyms.tsv`.
- `raw_fallback` rows are not exported because they have no selected synset and
  no canonical action surface.

### Stage 4. raw concept extraction

입력:

- `stage3_records.jsonl`에 저장된 token table, dependency table, noun chunk table
- `resources/gpic_inventory/observed_object_span_inventory.tsv`
- Stage 4는 spaCy model을 다시 실행하지 않는다.

정식 실행 gate:

- Stage 4 runner는 object inventory 전체를 먼저 검사한다.
- object inventory에 pending `decision_status` row가 하나라도 있으면 Stage 4를 실행하지 않는다.
- `chosen` row가 selected synset을 가졌지만 `canonical_surface`가 비어 있으면 canonical ambiguous 또는 canonical 미완료 상태로 보고 Stage 4를 실행하지 않는다.
- `chosen` row가 surface/head correction을 했지만 selected synset이 비어 있으면 Stage 4를 실행하지 않는다.
- 이 gate는 matched span에만 적용하지 않고 inventory 전체에 적용한다.

허용 추출:

- noun chunk 내부 selected span -> object
- noun chunk modifier -> attribute 또는 quantity
- VERB -> action
- `nsubj` -> agent
- `obj`, `dobj` -> patient
- preposition MWE + final direct `pobj` -> relation
- remaining single ADP/preposition + direct `pobj` -> relation

세부 기준:

- R12 object는 noun chunk 내부에서 root를 오른쪽 끝으로 갖는 left-expanding span을 만들고, GPIC observed object inventory에 row가 있는 가장 긴 span으로 만든다.
- lookup query order는 Stage 3.5와 동일하게 plural common noun head에서 head lemma surface를 먼저 본다. raw object mention text는 observed surface를 유지한다.
- inventory에 없는 span은 object count에서 제외한다.
- inventory row가 `decision_status=excluded`이면 object mention은 만들되 source_detail에 status/reason을 보존한다.
- inventory row가 `decision_status=needs_manual`이면 raw fallback으로 넘기지 않고 Stage 4를 중단한다. 이 항목은 offline resolution에서 먼저 해결해야 한다.
- inventory row에 selected synset이 있는데 `canonical_surface`가 비어 있으면 raw fallback으로 넘기지 않고 Stage 4를 중단한다. canonical ambiguous는 offline canonical inventory build에서 먼저 해결해야 한다.
- 선택된 lookup span 전체가 아니라 selected object core span token만 consumed 처리되고, action/relation edge 연결을 위해 같은 object mention으로 매핑한다.
- selected object core span은 inventory canonical/core surface가 lookup span의 suffix와 매칭되면 그 suffix token span이다.
- canonical/core suffix가 lookup span 안에서 매칭되지 않으면 fallback으로 lookup span 전체를 core로 본다.
- core span 밖 modifier token은 attribute/quantity 후보로 남긴다.
- R13 attribute modifier는 같은 noun chunk 안에서 `dep in {"amod", "compound", "nmod"}`인 token만 사용한다.
- R14 quantity modifier는 같은 noun chunk 안에서 `dep == "nummod"` 또는 `pos == "NUM"`인 token만 사용한다.
- R15 action은 `pos == "VERB"`인 token을 head로 보고, 가능한 경우 OEWN verb lookup으로 selected action span을 만든다.
- Stage 4는 action 후보를 만들기 전에 preposition MWE lexicon span을 먼저 감지하고, 선택된 span 내부 token을 `relation_mwe_consumed`로 둔다.
- preposition MWE span이 겹치면 longest span을 선택하고, 길이가 같으면 더 앞선 span을 선택한다.
- preposition MWE span은 retokenize하지 않고 metadata로만 남긴다.
- R15 selected action span 후보는 single VERB, VERB+particle, VERB+preposition, VERB+particle+preposition이다.
- particle 후보는 VERB의 child 중 `dep == "prt"` 또는 `tag == "RP"`인 token이다.
- preposition 후보는 VERB의 child 또는 particle의 child 중 `dep == "prep"` 또는 `pos == "ADP"`인 token이다.
- R15 preposition 후보는 token index가 VERB head보다 뒤에 있어야 한다. 즉 `prep.i <= verb.i`이면 VERB+preposition 또는 VERB+particle+preposition action 후보로 쓰지 않는다.
- R15 particle/preposition 후보 중 `relation_mwe_consumed` token은 phrasal action 후보에서 제외한다.
- R15 action lookup은 raw phrase를 `lowercase + strip`한 surface와, verb head만 Morphy한 surface만 사용한다. action에서는 separator 제거/underscore rescue를 하지 않는다.
- R15 raw phrase OEWN verb lookup은 반환 synset lemma 중 raw phrase surface와 형태가 정확히 맞는 lemma가 있는 synset만 exact hit로 인정한다. OEWN 내부 morphology로 반환된 base lemma synset은 exact hit로 보지 않는다.
- R15 exact hit가 없으면 verb head token만 Morphy하고 나머지 particle/preposition token과 다시 합친 query로 OEWN verb lookup을 한다. 이때도 반환 synset lemma 중 Morphy query와 형태가 맞는 synset만 hit로 인정한다.
- R15 Morphy query 중 OEWN verb hit query가 2개 이상이면 자동 선택하지 않고 `needs_manual`로 보낸다.
- R15 valid OEWN verb 후보가 있으면 longest span을 선택한다. 길이가 같고 VERB+particle과 VERB+preposition이 모두 가능하면 VERB+particle을 선택한다.
- R15 valid OEWN verb 후보의 synset 결정이 `needs_manual`이면 raw fallback으로 넘기지 않고 Stage 4를 중단한다. 이 항목은 offline action inventory/manual resolution에서 먼저 해결해야 한다.
- R15 valid OEWN verb 후보가 없으면 single VERB action mention을 raw fallback으로 만든다. 이 경우 selected synset이 없으므로 action inventory status는 `chosen`이 아니라 `raw_fallback`이다.
- R15 selected action span 내부 token은 action mention으로 매핑한다.
- R16 agent edge는 action head token의 direct child 중 `dep == "nsubj"`이고 그 child token이 selected object mapping에 있을 때만 만든다.
- R17 patient edge는 action head token의 direct child 중 `dep in {"obj", "dobj"}`이고 그 child token이 selected object mapping에 있을 때 만든다.
- R17 selected phrasal action span이 ADP를 소비한 경우, 그 ADP의 direct `pobj` child가 selected object mapping에 있으면 patient edge로 만든다.
- R18.1 preposition MWE relation edge는 matched span의 initial relation token head가 source object mapping에 있고, final ADP의 direct `pobj` child가 target object mapping에 있을 때 만든다.
- R18.1 matched span의 initial relation token head가 object가 아니고 `pos in {"VERB", "AUX"}`이면, 그 head의 direct child 중 object mapping이 있는 child를 dep label과 무관하게 relation source 후보로 본다.
- R18.1 final ADP의 direct `pobj` child가 여러 개이고 각각 object mapping이 있으면 target 후보가 여러 개인 것으로 본다.
- R18.1 source 후보와 target 후보가 각각 정확히 1개이고 둘 다 실제 mention이면 normal `relation` edge를 만든다.
- R18.1 source 후보 또는 target 후보가 0개이거나 2개 이상이면 source/target을 확정하지 않고 audit용 `ambiguous_relation_candidate` edge를 만든다. 이 edge는 normal relation triple count에는 넣지 않는다.
- R18.1 source 또는 target 후보가 0개인 경우에는 object mention을 새로 만들지 않고, edge endpoint에 audit-only sentinel `__missing_source__` 또는 `__missing_target__`을 둔다.
- R18.1 ambiguous relation candidate count는 후보 pair 개수가 아니라 matched MWE occurrence 단위로 센다. 같은 caption 안 같은 matched token indices와 relation label에서 나온 후보 pair 또는 missing endpoint candidate는 Stage 6에서 하나의 ambiguous relation occurrence fact로 묶는다.
- R18.1 relation label은 lexicon row의 canonical relation label을 쓴다.
- R18.1 relation edge와 ambiguous candidate edge source detail에는 raw span surface, matched token indices, relation components, initial relation token index, final ADP token index, source/target candidate metadata를 보존한다.
- R18 relation edge는 `pos == "ADP"` token의 direct child 중 `dep == "pobj"`가 target object mapping에 있고, ADP head token이 source object mapping에 있을 때만 만든다.
- R18 selected phrasal action span에 소비된 ADP token은 relation 후보에서 제외한다.
- R18 preposition MWE span에 소비된 ADP token은 single-ADP relation 후보에서 제외한다.
- Stage 4는 agent/patient/relation edge를 만들기 위해 새 object mention을 추가하지 않는다.

명시적 제외:

- 일반 `pobj`를 action patient로 쓰지 않는다. 단, selected phrasal action span에 소비된 ADP의 direct `pobj`는 patient 후보로 쓴다.
- passive voice를 고치지 않는다.
- semantic relation source disambiguation을 하지 않는다. 단, R18.1 action-attached preposition MWE에서 direct object-mapped child 후보가 보이면 단일 후보는 relation으로 만들고, 다중 후보는 별도 ambiguous relation candidate로 보존한다.
- self-edge repair를 하지 않는다.
- pronoun/reference resolution을 하지 않는다.
- scene context fallback을 하지 않는다.

### Stage 5. canonicalization

정식 실행 gate:

- Stage 5 runner는 active attribute canonicalization이 필요한 run에서 attribute inventory를 입력으로 받아야 한다.
- attribute inventory에 `needs_manual` row가 하나라도 있으면 Stage 5를 실행하지 않는다.
- `chosen` row가 selected synset을 가졌지만 `canonical_surface`가 비어 있으면 canonical ambiguous 또는 canonical 미완료 상태로 보고 Stage 5를 실행하지 않는다.
- selected synset이 없는 `chosen` row는 `decision_reason=no_oewn_attribute_synset`이면 canonical 적용 불가 row로 보고 Stage 5를 막지 않는다.
- 이 gate를 통과하지 않은 Stage 5/6/Markdown output은 정식 caption-to-concept 결과로 부르지 않는다.

허용:

- object selected synset metadata preservation
- object canonical surface from GPIC observed inventory
- object raw surface fallback when canonical surface is absent
- attribute synonym lookup
- attribute type lookup은 active output에서 보류
- quantity raw-preserving
- action synonym lookup
- action parent concept lookup은 아직 비활성
- object parent concept mapping은 Stage 4 source detail의 selected OEWN immediate hypernym evidence를 사용함
- object `parent_concepts`는 parent lemma display를 먼저 쓰고, parent synset ID는 `parent_oewn_synsets` evidence로 보존함
- relation canonicalization은 Stage 4 evidence를 보존한다.
  - single ADP relation은 raw-preserving이다.
  - preposition MWE relation은 Stage 4 lexicon canonical relation label을 그대로 유지한다.

금지:

- canonicalization 단계에서 새 object를 만들지 않는다.
- canonicalization 단계에서 agent/patient를 고치지 않는다.
- canonicalization 단계에서 relation source/target을 바꾸지 않는다.

### Stage 6. count export

허용 count:

- object count
- object parent count
- attribute count
- quantity count
- object-attribute pair count
- object-quantity pair count
- action count
- agent/patient pair count
- relation triple count
- relation component count
- ambiguous relation occurrence count
- object co-occurrence pair count

aggregation 기준:

- `count`는 같은 `count_key`를 가진 fact row 수
- `caption_count`는 unique caption 수
- `example_caption_ids`는 최대 5개
- rows는 `count` 내림차순, 그 다음 `count_key` 오름차순
- raw variants는 raw surface를 `strip + lower`한 값
- parent 관련 count table은 사람이 읽는 `parent_concepts`를 먼저 보여주고, 같은 parent의 synset ID는 `parent_synset_ids` 계열 evidence column에 별도로 남긴다.
- relation component count는 preposition MWE relation edge의 `relation_components` metadata에서만 만든다.
- relation component count는 `relation`, `component`, `component_index`를 집계한다.
- ambiguous relation occurrence count는 preposition MWE edge 중 `edge_type == "ambiguous_relation_candidate"`인 Stage 4 metadata에서만 만든다.
- ambiguous relation occurrence count는 후보 pair가 아니라 `caption_id + matched_token_indices + relation` 단위로 묶어 센다.
- ambiguous relation occurrence count는 `source_status`, `relation`, `target_status`를 집계하고, candidate source/target 목록은 evidence column으로 보존한다. normal relation triple count에는 포함하지 않는다.

object co-occurrence 기준:

- 같은 caption 안의 unique canonical object label set으로 만든다.
- directed pair를 만든다. 즉 `A -> B`, `B -> A`를 모두 만든다.
- `source_object == target_object`인 self pair는 만들지 않는다.
- 같은 caption 안에 같은 canonical object mention이 여러 개 있어도 같은 object끼리 pair는 만들지 않는다.

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
| PP source disambiguation | relation source 선택에 semantic scoring이 필요함. R18.1의 action-attached direct object-mapped child 후보 보존은 scoring이 아니라 candidate fact 보존이므로 별도 허용 |
| with-absolute recovery | spaCy가 놓친 object를 patch rule로 복구하는 구조가 됨 |
| scene context fallback | object/context 분리 rule이 복잡해짐 |
| tag-list segment-specific extraction | comma segment split과 segment별 object/attribute grouping이 새 rule을 필요로 함 |
| tag-list same-pipeline extraction | tag-list를 문장처럼 parsing하면 입력 형식 mismatch로 dependency/noun chunk가 흔들림 |
| undocumented phrasal action repair | OEWN verb lookup으로 선택되지 않은 prep/particle 구조를 semantic patch로 복구하지 않음 |
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

## Appendix. GPIC Object Inventory Manual-Resolution Gate

This rule applies before parent enrichment, canonical enrichment, and Stage 4
runtime extraction with a manual-resolved GPIC object inventory.

Allowed final statuses:

- `decision_status=chosen`
- `decision_status=excluded`

Pending statuses:

- `needs_manual`
- `manual_required`
- `ambiguous`
- blank or unknown explicit `decision_status`

Gate rules:

- Parent enrichment must stop before OEWN loading if any pending row remains.
- Canonical enrichment must stop before OEWN loading if any pending row remains.
- Stage 4 runner must stop before raw extraction if any pending row remains in
  the object inventory.
- Stage 4 runner must stop before raw extraction if a selected object synset
  has no `canonical_surface`.
- Stage 4 treats unknown explicit decision statuses as `needs_manual`.
- If a row is `chosen` and its surface/head form was changed, the selected
  synset must be re-looked-up and written into `selected_oewn_synset`.
- A `chosen` row with changed `selected_query` or `canonical_surface` but blank
  `selected_oewn_synset` is invalid and must be blocked as:
  - `surface_correction_requires_synset_lookup`
- `excluded` rows are not pending manual work. They remain countable metadata
  under the current policy.

## Appendix. GPIC Attribute Inventory Manual-Resolution Gate

This rule applies before Stage 5 canonicalization when attribute output is part
of the formal caption-to-concept result.

Allowed final statuses:

- `decision_status=chosen`
- `decision_status=excluded`

Pending statuses:

- `needs_manual`
- blank or unknown explicit `decision_status`

Gate rules:

- Stage 5 runner must stop before canonicalization if any pending row remains
  in the attribute inventory.
- Stage 5 runner must stop before canonicalization if a chosen attribute row
  has a selected synset but no `canonical_surface`.
- A chosen attribute row with no selected synset is allowed only as a no-synset
  fallback row. It remains countable through raw surface fallback and should be
  identified by `decision_reason=no_oewn_attribute_synset`.
- Stage 5/6/Markdown output created without passing this gate is preview output,
  not a formal caption-to-concept result.

## Appendix. GPIC Action Inventory Manual-Resolution Gate

This rule applies before formal Stage 4 extraction when an action inventory is
passed to the Stage 4 runner.

Allowed final statuses:

- `decision_status=chosen` with a non-empty `selected_oewn_synset`
- `decision_status=raw_fallback` with an empty `selected_oewn_synset`

Pending statuses:

- `needs_manual`
- blank or unknown explicit `decision_status`
- `chosen` with an empty `selected_oewn_synset`

Gate rules:

- Stage 4 runner must stop before raw extraction if any pending row remains in
  the action inventory.
- `raw_fallback` rows are allowed because they mean OEWN found no verb synset
  for that observed action span; count/export uses raw surface fallback.
- A manual action decision must select a synset from the current OEWN candidate
  list for that row.
- If manual resolution chooses one Morphy query from an ambiguous query set,
  write the selected singular query into `selected_query` and preserve the
  decision note in the manual decision artifact.
