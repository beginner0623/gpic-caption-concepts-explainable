# V1 Output Schema

이 문서는 v1 caption-to-concept pipeline의 산출물 구조를 고정한다.

기준 문서:

- `AGENTS.md`
- `docs/rules_v1.md`
- `docs/implementation_plan_v1.md`

이 문서는 새 extraction rule을 추가하지 않는다.

## 0. Schema 원칙

v1 output은 문장을 새로 생성하지 않는다.

v1 output은 count 가능한 record를 만든다.

모든 주요 output row는 아래 정보를 추적할 수 있어야 한다.

- 어떤 caption에서 왔는가
- 어떤 token/span에서 왔는가
- 어떤 Rule ID에서 생성되었는가
- raw value는 무엇인가
- canonical value는 무엇인가
- object parent concept은 무엇인가. action/attribute type은 active output에서 보류한다.

중요:

- raw extraction과 canonicalization은 구분한다.
- count export는 새 linguistic interpretation을 하지 않는다.
- tag-list caption은 v1에서 extraction하지 않고 skip한다.

## 1. File-level Output 계획

구현 후 기본 output은 아래 파일들로 나눈다.

```text
outputs/
├─ caption_records.jsonl
├─ stage2_records.jsonl
├─ stage3_records.jsonl
├─ gpic_observed_object_inventory.tsv
├─ raw_mentions.jsonl
├─ raw_edges.jsonl
├─ canonical_mentions.jsonl
├─ canonical_edges.jsonl
├─ facts.jsonl
└─ counts/
   ├─ object_counts.tsv
   ├─ attribute_counts.tsv
   ├─ object_attribute_pair_counts.tsv
   ├─ action_counts.tsv
   ├─ agent_patient_pair_counts.tsv
   ├─ relation_triple_counts.tsv
   ├─ relation_component_counts.tsv
   ├─ ambiguous_relation_candidate_counts.tsv
   └─ object_cooccurrence_pair_counts.tsv
```

검사용 report는 별도 파일로 만든다.

```text
reports/
└─ sample_inspection_v1.md
```

## 2. CaptionRecord

파일:

- `caption_records.jsonl`

단위:

- caption 1개당 1 row

목적:

- caption 처리 여부와 전체 metadata를 기록한다.

Schema:

| field | type | required | 설명 |
|---|---|---:|---|
| `caption_id` | string | yes | GPIC caption id 또는 입력 row id |
| `caption` | string | yes | 원본 caption text |
| `caption_shape` | string | yes | `sentence` 또는 `tag_list` |
| `skipped` | boolean | yes | extraction skip 여부 |
| `skip_reason` | string or null | yes | 예: `tag_list_deferred` |
| `pipeline_version` | string | yes | 예: `v1_explainable` |
| `rule_ids` | list[string] | yes | caption-level decision에 관여한 rule id |
| `meta` | object | no | split, shard, source 등 optional metadata |

예시:

```json
{
  "caption_id": "000001",
  "caption": "A brown dog sits on a wooden bench.",
  "caption_shape": "sentence",
  "skipped": false,
  "skip_reason": null,
  "pipeline_version": "v1_explainable",
  "rule_ids": ["R1"],
  "meta": {}
}
```

tag-list skip 예시:

```json
{
  "caption_id": "000002",
  "caption": "brown boot, brick wall, display, indoor, large",
  "caption_shape": "tag_list",
  "skipped": true,
  "skip_reason": "tag_list_deferred",
  "pipeline_version": "v1_explainable",
  "rule_ids": ["R1", "R1.1"],
  "meta": {}
}
```

## 3. Stage2Record

파일:

- `stage2_records.jsonl`

단위:

- sentence caption 1개당 1 row

목적:

- Stage 2 preprocessing 결과를 사람이 확인할 수 있게 저장한다.
- 이 파일은 concept extraction output이 아니다.

Schema:

| field | type | required | 설명 |
|---|---|---:|---|
| `caption_id` | string | yes | source caption id |
| `caption` | string | yes | 원본 caption text |
| `stage` | integer | yes | 항상 `2` |
| `pipeline_version` | string | yes | 예: `v1_explainable` |
| `rule_ids` | list[string] | yes | 적용된 Stage 2 rule id |
| `tokens` | list[object] | yes | retokenize 이후 token list |
| `protected_spans` | list[object] | yes | quote, object MWE, hyphen merge metadata |
| `meta` | object | no | Stage 1에서 보존한 metadata |

중요:

- `stage2_records.jsonl`은 `raw_mentions.jsonl`을 대체하지 않는다.
- object, attribute, action, relation은 Stage 4에서만 생성된다.

## 4. Stage3Record

파일:

- `stage3_records.jsonl`

단위:

- sentence caption 1개당 1 row

목적:

- Stage 3 spaCy linguistic annotation 결과를 사람이 확인할 수 있게 저장한다.
- 이 파일은 concept extraction output이 아니다.

Schema:

| field | type | required | 설명 |
|---|---|---:|---|
| `caption_id` | string | yes | source caption id |
| `caption` | string | yes | 원본 caption text |
| `stage` | integer | yes | 항상 `3` |
| `pipeline_version` | string | yes | 예: `v1_explainable` |
| `model` | string | yes | 기본값 `en_core_web_trf` |
| `rule_ids` | list[string] | yes | 적용된 Stage 2~3 rule id |
| `tokens` | list[object] | yes | POS, TAG, MORPH, lemma, dependency 포함 token table |
| `sentences` | list[object] | yes | spaCy sentence span table |
| `noun_chunks` | list[object] | yes | spaCy noun chunk table |
| `protected_spans` | list[object] | yes | Stage 2 protected span metadata |
| `meta` | object | no | Stage 1에서 보존한 metadata |

중요:

- `stage3_records.jsonl`은 `raw_mentions.jsonl`을 대체하지 않는다.
- object, attribute, action, relation은 Stage 4에서만 생성된다.
- NER output은 v1에서 사용하지 않으며 Stage 3 model load 시 disabled 처리한다.

## 4.5. GPIC Observed Object Inventory

파일:

- `gpic_observed_object_inventory.tsv`

단위:

- GPIC Stage 3 records에서 관측된 object span 후보 1개당 1 row

목적:

- Stage 4가 runtime OEWN lookup이나 외부 source-label inventory를 직접 쓰지 않도록, GPIC caption에서 관측된 noun chunk span의 OEWN lookup 결과와 objectness gate 결과를 고정한다.

핵심 field:

| field | 설명 |
|---|---|
| `span_key` | lookup key. observed surface를 `strip + lower + whitespace normalize`한 값 |
| `observed_surface` | GPIC caption에서 실제 관측된 span surface |
| `decision_status` | 사람이 보는 최종 queue 상태: `chosen`, `needs_manual`, `excluded` |
| `decision_reason` | queue로 보낸 이유: `selected_object_compatible`, `manual_joined_variant_required`, `manual_objectness_required`, `manual_synset_required`, `no_oewn_noun_synset` |
| `selected_oewn_synset` | synset이 결정된 경우 selected OEWN synset id |
| `selected_oewn_lexfile` | selected synset의 OEWN lexfile |
| `parent_oewn_synsets` | selected synset의 immediate hypernym synset IDs. pipe-separated |
| `parent_oewn_lexfiles` | parent synset id와 lexfile evidence. pipe-separated |
| `parent_lemmas` | parent synset id와 lemma display evidence. pipe-separated |
| `parent_selection_tag` | parent 선정 방식. 보통 `selected_all_immediate_oewn_hypernyms` |
| `canonical_surface` | selected synset lemma 중 offline canonical rule로 결정한 canonical object surface |
| `canonical_label_key` | canonical surface의 normalized key |
| `canonical_selection_tag` | canonical surface 선정 방식 또는 ambiguous 원인 |
| `canonical_candidate_lemmas` | observed surface variants와 매칭된 candidate OEWN lemmas |
| `canonical_candidate_lemma_counts` | candidate lemmas의 WN3 count evidence |
| `google_ngram_candidate_surfaces` | Ngram 비교가 필요할 때의 candidate surfaces |
| `google_ngram_candidate_mean_frequencies` | 저장된 Ngram frequency evidence |
| `objectness_gate` | selected synset lexfile의 objectness evidence: `object_compatible`, `conditional`, `hard_conflict`, empty |
| `all_oewn_synsets` | lookup된 OEWN noun synset 후보 전체 |
| `all_oewn_lexfiles` | 후보 synset들의 lexfile |
| `synset_selection_tag` | synset 선택 방식 또는 manual 필요 원인 |
| `wn30_lemma_counts` | WN3 lemma count evidence |

Stage 4 사용 기준:

- `decision_status=chosen`과 `decision_status=excluded` row는 object mention으로 생성한다.
- `decision_status=needs_manual` row가 matching되면 Stage 4는 raw fallback으로 넘기지 않고 중단한다.
- `decision_status=excluded` row는 count에는 포함하되 source detail에 status/reason을 보존한다.
- inventory에 없는 span은 object로 세지 않는다.

## 5. RawMention

파일:

- `raw_mentions.jsonl`

단위:

- raw concept mention 1개당 1 row

생성 stage:

- Stage 4 Raw concept extraction

허용 mention type:

- `object`
- `attribute`
- `quantity`
- `action`

Schema:

| field | type | required | 설명 |
|---|---|---:|---|
| `caption_id` | string | yes | source caption id |
| `mention_id` | string | yes | caption 내부 unique id. 예: `m0` |
| `mention_type` | string | yes | `object`, `attribute`, `quantity`, `action` |
| `text` | string | yes | 원문 surface text |
| `lemma` | string | yes | spaCy lemma 또는 retokenize lemma |
| `rule_id` | string | yes | mention을 만든 rule id |
| `stage` | integer | yes | v1 stage number. raw mention은 `4` |
| `confidence` | string | yes | v1 기본값은 `high`; 애매하면 `medium` 가능 |
| `char_start` | integer or null | yes | caption 내 character start |
| `char_end` | integer or null | yes | caption 내 character end |
| `token_start` | integer or null | yes | spaCy token start |
| `token_end` | integer or null | yes | spaCy token end, exclusive |
| `source_text` | string | no | noun chunk text 등 source span |
| `source_detail` | object | no | dep, head, POS 등 inspection용 evidence |

예시:

```json
{
  "caption_id": "000001",
  "mention_id": "m0",
  "mention_type": "object",
  "text": "dog",
  "lemma": "dog",
  "rule_id": "R12",
  "stage": 4,
  "confidence": "high",
  "char_start": 8,
  "char_end": 11,
  "token_start": 2,
  "token_end": 3,
  "source_text": "A brown dog",
  "source_detail": {
    "pos": "NOUN",
    "tag": "NN",
    "dep": "nsubj",
    "head": "sits"
  }
}
```

## 6. RawEdge

파일:

- `raw_edges.jsonl`

단위:

- raw edge 1개당 1 row

생성 stage:

- Stage 4 Raw concept extraction

허용 edge type:

- `has_attribute`
- `has_quantity`
- `event_role`
- `relation`
- `ambiguous_relation_candidate`

Schema:

| field | type | required | 설명 |
|---|---|---:|---|
| `caption_id` | string | yes | source caption id |
| `edge_id` | string | yes | caption 내부 unique id. 예: `e0` |
| `edge_type` | string | yes | `has_attribute`, `has_quantity`, `event_role`, `relation`, `ambiguous_relation_candidate` |
| `source_mention_id` | string | yes | source mention id |
| `target_mention_id` | string | yes | target mention id |
| `label` | string | yes | edge label. 예: `agent`, `patient`, `on` |
| `rule_id` | string | yes | edge를 만든 rule id |
| `stage` | integer | yes | raw edge는 `4` |
| `confidence` | string | yes | 기본값 `high` |
| `evidence_text` | string | no | edge 생성 근거가 되는 token/span |
| `source_detail` | object | no | dep, head 등 inspection용 evidence |

예시:

```json
{
  "caption_id": "000001",
  "edge_id": "e0",
  "edge_type": "event_role",
  "source_mention_id": "m2",
  "target_mention_id": "m0",
  "label": "agent",
  "rule_id": "R16",
  "stage": 4,
  "confidence": "high",
  "evidence_text": "dog -> sits",
  "source_detail": {
    "dep": "nsubj"
  }
}
```

## 7. CanonicalMention

파일:

- `canonical_mentions.jsonl`

단위:

- raw mention 1개에 대한 canonicalized row 1개

생성 stage:

- Stage 5 Canonicalization

Schema:

| field | type | required | 설명 |
|---|---|---:|---|
| `caption_id` | string | yes | source caption id |
| `mention_id` | string | yes | raw mention id와 동일 |
| `mention_type` | string | yes | raw mention type |
| `raw_text` | string | yes | raw surface text |
| `raw_lemma` | string | yes | raw lemma |
| `canonical` | string | yes | canonical label |
| `parent_concepts` | list[string] | yes | object parent synset IDs. object가 아니면 empty list |
| `canonical_rule_id` | string | yes | R19, R20, R21, R22 중 하나 |
| `parent_rule_id` | string or null | yes | object parent가 있으면 R23, 아니면 null |
| `canonical_source` | string | yes | `lexicon`, `gpic_observed_inventory`, 또는 `raw_fallback` |
| `parent_source` | string or null | yes | `selected_oewn_hypernym` 또는 null |
| `confidence` | string | yes | 기본값 `high`; fallback이면 `medium` 가능 |
| `canonical_detail` | object | yes | selected synset, parent evidence처럼 canonical label에 붙는 부가 정보. 없으면 `{}`. attribute type은 active output에서 보류 |

예시:

```json
{
  "caption_id": "000001",
  "mention_id": "m0",
  "mention_type": "object",
  "raw_text": "dogs",
  "raw_lemma": "dog",
  "canonical": "dog",
  "parent_concepts": ["oewn-02085998-n", "oewn-01317541-n"],
  "canonical_rule_id": "R19",
  "parent_rule_id": "R23",
  "canonical_source": "gpic_observed_inventory",
  "parent_source": "selected_oewn_hypernym",
  "confidence": "high",
  "canonical_detail": {
    "parent_selection_tag": "selected_all_immediate_oewn_hypernyms"
  }
}
```

unknown fallback 예시:

```json
{
  "caption_id": "000001",
  "mention_id": "m4",
  "mention_type": "object",
  "raw_text": "treeline",
  "raw_lemma": "treeline",
  "canonical": "treeline",
  "parent_concepts": [],
  "canonical_rule_id": "R19",
  "parent_rule_id": null,
  "canonical_source": "raw_fallback",
  "parent_source": null,
  "confidence": "medium",
  "canonical_detail": {}
}
```

## 8. CanonicalEdge

파일:

- `canonical_edges.jsonl`

단위:

- raw edge 1개에 대한 canonicalized edge row 1개

생성 stage:

- Stage 5 Canonicalization

중요:

- canonicalization은 source/target을 바꾸지 않는다.
- agent/patient를 고치지 않는다.
- relation source/target을 바꾸지 않는다.
- single ADP relation label은 raw-preserving이다.
- preposition MWE relation label은 Stage 4 lexicon canonical relation label을 보존한다.

Schema:

| field | type | required | 설명 |
|---|---|---:|---|
| `caption_id` | string | yes | source caption id |
| `edge_id` | string | yes | raw edge id와 동일 |
| `edge_type` | string | yes | raw edge type |
| `source_mention_id` | string | yes | source mention id |
| `target_mention_id` | string | yes | target mention id |
| `label` | string | yes | edge label |
| `canonical_label` | string | yes | relation은 raw label 유지. event role은 `agent`/`patient` 유지 |
| `source_canonical` | string | yes | source mention canonical |
| `target_canonical` | string | yes | target mention canonical |
| `rule_id` | string | yes | edge 원 rule id |
| `canonical_rule_id` | string or null | yes | relation canonicalization이면 R24, role/attribute edge는 null 가능 |
| `confidence` | string | yes | 기본값 `high` |
| `canonical_detail` | object | yes | Stage 4 edge metadata 보존. preposition MWE relation이면 relation components 포함 가능 |

예시:

```json
{
  "caption_id": "000001",
  "edge_id": "e1",
  "edge_type": "relation",
  "source_mention_id": "m0",
  "target_mention_id": "m3",
  "label": "on",
  "canonical_label": "on",
  "source_canonical": "dog",
  "target_canonical": "bench",
  "rule_id": "R18",
  "canonical_rule_id": "R24",
  "confidence": "high",
  "canonical_detail": {}
}
```

## 9. FactRow

파일:

- `facts.jsonl`

단위:

- count 가능한 fact 1개당 1 row

생성 stage:

- Stage 6 Count export

허용 fact type:

- `entity_exists`
- `attribute_exists`
- `quantity_exists`
- `object_parent`
- `has_attribute`
- `has_quantity`
- `action_event`
- `event_role`
- `relation`
- `ambiguous_relation_candidate`
- `relation_component`
- `object_pair_in_caption`

공통 schema:

| field | type | required | 설명 |
|---|---|---:|---|
| `caption_id` | string | yes | source caption id |
| `fact_id` | string | yes | caption 내부 unique fact id |
| `fact_type` | string | yes | 허용 fact type 중 하나 |
| `count_key` | string | yes | aggregation key |
| `rule_ids` | list[string] | yes | fact 생성에 사용된 mention/edge/canonical rule ids |
| `source_mention_ids` | list[string] | yes | 관련 mention ids |
| `source_edge_ids` | list[string] | yes | 관련 edge ids |
| `values` | object | yes | fact type별 값 |

예시:

```json
{
  "caption_id": "000001",
  "fact_id": "f0",
  "fact_type": "entity_exists",
  "count_key": "entity_exists:dog",
  "rule_ids": ["R12", "R19", "R23"],
  "source_mention_ids": ["m0"],
  "source_edge_ids": [],
  "values": {
    "object": "dog",
    "parent_concepts": ["animal"]
  }
}
```

## 10. Fact Type별 values schema

### 10.1 `entity_exists`

대상:

- object mention

`values`:

| field | type | 설명 |
|---|---|---|
| `object` | string | canonical object |
| `parent_concepts` | list[string] | object parent concept |
| `raw_variants` | list[string] | caption 내 raw surface variants. `strip + lower` |

`count_key`:

```text
entity_exists:{object}
```

### 10.2 `attribute_exists`

대상:

- attribute mention

`values`:

| field | type | 설명 |
|---|---|---|
| `attribute` | string | canonical attribute |
| `raw_variants` | list[string] | caption 내 raw surface variants. `strip + lower` |

`count_key`:

```text
attribute_exists:{attribute}
```

### 10.3 `quantity_exists`

대상:

- quantity mention

`values`:

| field | type | 설명 |
|---|---|---|
| `quantity` | string | raw-preserving quantity |
| `raw_variants` | list[string] | caption 내 raw surface variants. `strip + lower` |

`count_key`:

```text
quantity_exists:{quantity}
```

### 10.4 `object_parent`

대상:

- object mention의 parent concept evidence

`values`:

| field | type | 설명 |
|---|---|---|
| `object` | string | canonical object |
| `parent` | string | parent display label |
| `parent_synset_id` | string | parent OEWN synset id evidence |
| `raw_variants` | list[string] | object raw variants |

`count_key`:

```text
object_parent:{object}:{parent}
```

### 10.5 `has_attribute`

대상:

- object --has_attribute--> attribute

`values`:

| field | type | 설명 |
|---|---|---|
| `object` | string | canonical object |
| `attribute` | string | canonical attribute |
| `object_parent_concepts` | list[string] | object parent concept |

`count_key`:

```text
has_attribute:{object}:{attribute}
```

### 10.6 `has_quantity`

대상:

- object --has_quantity--> quantity

`values`:

| field | type | 설명 |
|---|---|---|
| `object` | string | canonical object |
| `quantity` | string | raw or normalized quantity |

`count_key`:

```text
has_quantity:{object}:{quantity}
```

### 10.7 `action_event`

대상:

- action mention

`values`:

| field | type | 설명 |
|---|---|---|
| `action` | string | canonical action |
| `raw_variants` | list[string] | caption 내 raw surface variants. `strip + lower` |

`count_key`:

```text
action_event:{action}
```

### 10.8 `event_role`

대상:

- action --agent--> object
- action --patient--> object

`values`:

| field | type | 설명 |
|---|---|---|
| `action` | string | canonical action |
| `role` | string | `agent` 또는 `patient` |
| `target` | string | canonical object |
| `target_parent_concepts` | list[string] | target parent concept |

`count_key`:

```text
event_role:{action}:{role}:{target}
```

### 10.9 `relation`

대상:

- object --relation--> object

`values`:

| field | type | 설명 |
|---|---|---|
| `source` | string | canonical source object |
| `relation` | string | single ADP raw label 또는 preposition MWE canonical relation label |
| `target` | string | canonical target object |
| `source_parent_concepts` | list[string] | source parent synset IDs |
| `target_parent_concepts` | list[string] | target parent synset IDs |

`count_key`:

```text
relation:{source}:{relation}:{target}
```

### 10.10 `relation_component`

대상:

- preposition MWE relation edge의 component metadata

`values`:

| field | type | 설명 |
|---|---|---|
| `relation` | string | canonical relation MWE label |
| `component_index` | string | component 순서 index |
| `component` | string | relation MWE component token |
| `raw_variants` | list[string] | relation raw span variants |

`count_key`:

```text
relation_component:{relation}:{component_index}:{component}
```

### 10.11 `ambiguous_relation_candidate`

대상:

- preposition MWE에서 source 또는 target 후보가 0개이거나 2개 이상인 경우의 후보 relation occurrence
- normal relation triple로 확정하지 않고 candidate로만 count한다.
- source 또는 target 후보가 0개인 경우 object mention을 만들지 않고
  `source_missing` 또는 `target_missing` 상태로 기록한다.

`values`:

| field | type | 설명 |
|---|---|---|
| `source_status` | string | `source_resolved`, `source_ambiguous`, or `source_missing` |
| `relation` | string | preposition MWE canonical relation label |
| `target_status` | string | `target_resolved`, `target_ambiguous`, or `target_missing` |
| `candidate_sources` | list[string] | canonical candidate source objects or `source_missing` |
| `candidate_targets` | list[string] | canonical candidate target objects or `target_missing` |
| `candidate_pair_count` | string | preserved Stage 4 candidate edge count for this matched occurrence |
| `raw_variants` | list[string] | matched raw MWE span variants |

`count_key`:

```text
ambiguous_relation_candidate:{source_status}:{relation}:{target_status}
```

### 10.12 `object_pair_in_caption`

대상:

- 같은 caption 안에 같이 나온 object pair

기준:

- 같은 caption 기준
- unique canonical object label 기준
- 순서쌍 directed pair로 저장
- 자기 자신 pair는 만들지 않음

`values`:

| field | type | 설명 |
|---|---|---|
| `source_object` | string | canonical object |
| `target_object` | string | canonical object |
| `source_parent_concepts` | list[string] | source parent synset IDs |
| `target_parent_concepts` | list[string] | target parent synset IDs |

`count_key`:

```text
object_pair_in_caption:{source_object}:{target_object}
```

## 11. Count Tables

count table은 `facts.jsonl`에서 aggregation으로 만든다.

count export는 새 concept을 만들지 않는다.

### 11.1 공통 count table schema

| field | type | 설명 |
|---|---|---|
| `count_key` | string | aggregation key |
| `count` | integer | fact row count |
| `caption_count` | integer | unique caption count |
| `example_caption_ids` | list[string] | 일부 example ids |
| `raw_variants` | list[string] | raw surface variants. `strip + lower` |
| `rule_ids` | list[string] | 관련 rule ids |

### 11.2 table별 key

| file | source fact type | primary key |
|---|---|---|
| `object_counts.tsv` | `entity_exists` | `object` |
| `attribute_counts.tsv` | `attribute_exists` | `attribute` |
| `quantity_counts.tsv` | `quantity_exists` | `quantity` |
| `object_parent_counts.tsv` | `object_parent` | `object`, `parent` |
| `object_attribute_pair_counts.tsv` | `has_attribute` | `object`, `attribute` |
| `object_quantity_pair_counts.tsv` | `has_quantity` | `object`, `quantity` |
| `action_counts.tsv` | `action_event` | `action` |
| `agent_patient_pair_counts.tsv` | `event_role` | `action`, `role`, `target` |
| `relation_triple_counts.tsv` | `relation` | `source`, `relation`, `target` |
| `relation_component_counts.tsv` | `relation_component` | `relation`, `component_index`, `component` |
| `ambiguous_relation_candidate_counts.tsv` | `ambiguous_relation_candidate` | `candidate_source`, `relation`, `target` |
| `object_cooccurrence_pair_counts.tsv` | `object_pair_in_caption` | `source_object`, `target_object` |

## 12. ID 규칙

caption 내부 id:

- mention id: `m0`, `m1`, `m2`, ...
- edge id: `e0`, `e1`, `e2`, ...
- fact id: `f0`, `f1`, `f2`, ...

전역 uniqueness가 필요하면:

```text
{caption_id}:{local_id}
```

예:

```text
000001:m0
000001:e0
000001:f0
```

## 13. Tag-list 처리

v1에서 tag-list caption은 extraction 대상에서 제외한다.

tag-list caption은 `caption_records.jsonl`에는 남긴다.

그러나 아래 파일에는 row를 만들지 않는다.

- `raw_mentions.jsonl`
- `raw_edges.jsonl`
- `canonical_mentions.jsonl`
- `canonical_edges.jsonl`
- `facts.jsonl`
- count tables

tag-list caption의 `CaptionRecord`는 다음과 같아야 한다.

```json
{
  "caption_shape": "tag_list",
  "skipped": true,
  "skip_reason": "tag_list_deferred",
  "rule_ids": ["R1", "R1.1"]
}
```

## 14. Forbidden Output Mutation

아래 일은 schema상 허용하지 않는다.

- canonicalization에서 source/target 바꾸기
- count export에서 mention 추가하기
- count export에서 edge 추가하기
- count export에서 relation source 고치기
- count export에서 pronoun/reference 복구하기
- skipped tag-list caption에서 concept 생성하기

필요해 보이면 `docs/rules_v1.md` 변경부터 논의한다.
