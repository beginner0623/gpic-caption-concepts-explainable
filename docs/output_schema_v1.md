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
- parent concept은 무엇인가

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

Schema:

| field | type | required | 설명 |
|---|---|---:|---|
| `caption_id` | string | yes | source caption id |
| `edge_id` | string | yes | caption 내부 unique id. 예: `e0` |
| `edge_type` | string | yes | `has_attribute`, `has_quantity`, `event_role`, `relation` |
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
| `parent_concepts` | list[string] | yes | parent concept chain. 없으면 empty list |
| `canonical_rule_id` | string | yes | R19, R20, R21, R22 중 하나 |
| `parent_rule_id` | string or null | yes | R23 또는 null |
| `canonical_source` | string | yes | `lexicon` 또는 `raw_fallback` |
| `parent_source` | string or null | yes | `lexicon` 또는 null |
| `confidence` | string | yes | 기본값 `high`; fallback이면 `medium` 가능 |
| `canonical_detail` | object | yes | attribute type처럼 canonical label에 붙는 부가 정보. 없으면 `{}` |

예시:

```json
{
  "caption_id": "000001",
  "mention_id": "m0",
  "mention_type": "object",
  "raw_text": "dogs",
  "raw_lemma": "dog",
  "canonical": "dog",
  "parent_concepts": ["animal"],
  "canonical_rule_id": "R19",
  "parent_rule_id": "R23",
  "canonical_source": "lexicon",
  "parent_source": "lexicon",
  "confidence": "high",
  "canonical_detail": {}
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
- relation label은 raw-preserving이다.

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
| `canonical_rule_id` | string or null | yes | relation raw-preserving이면 R24, role/attribute edge는 null 가능 |
| `confidence` | string | yes | 기본값 `high` |

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
  "confidence": "high"
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
- `has_attribute`
- `has_quantity`
- `action_event`
- `event_role`
- `relation`
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
| `raw_variants` | list[string] | caption 내 raw lemma variants |

`count_key`:

```text
entity_exists:{object}
```

### 10.2 `has_attribute`

대상:

- object --has_attribute--> attribute

`values`:

| field | type | 설명 |
|---|---|---|
| `object` | string | canonical object |
| `attribute` | string | canonical attribute |
| `attribute_type` | string or null | color, material, size 등 explicit lexicon 결과 |
| `object_parent_concepts` | list[string] | object parent concept |

`count_key`:

```text
has_attribute:{object}:{attribute}
```

### 10.3 `has_quantity`

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

### 10.4 `action_event`

대상:

- action mention

`values`:

| field | type | 설명 |
|---|---|---|
| `action` | string | canonical action |
| `parent_concepts` | list[string] | action parent concept |
| `raw_variants` | list[string] | caption 내 raw lemma variants |

`count_key`:

```text
action_event:{action}
```

### 10.5 `event_role`

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

### 10.6 `relation`

대상:

- object --relation--> object

`values`:

| field | type | 설명 |
|---|---|---|
| `source` | string | canonical source object |
| `relation` | string | raw-preserving relation label |
| `target` | string | canonical target object |

`count_key`:

```text
relation:{source}:{relation}:{target}
```

### 10.7 `object_pair_in_caption`

대상:

- 같은 caption 안에 같이 나온 object pair

기준:

- 같은 caption 기준
- 순서쌍 directed pair로 저장
- 자기 자신 pair는 만들지 않음

`values`:

| field | type | 설명 |
|---|---|---|
| `source_object` | string | canonical object |
| `target_object` | string | canonical object |

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
| `raw_variants` | list[string] | raw lemma/text variants |
| `rule_ids` | list[string] | 관련 rule ids |

### 11.2 table별 key

| file | source fact type | primary key |
|---|---|---|
| `object_counts.tsv` | `entity_exists` | `object` |
| `attribute_counts.tsv` | `has_attribute` | `attribute` |
| `object_attribute_pair_counts.tsv` | `has_attribute` | `object`, `attribute` |
| `action_counts.tsv` | `action_event` | `action` |
| `agent_patient_pair_counts.tsv` | `event_role` | `action`, `role`, `target` |
| `relation_triple_counts.tsv` | `relation` | `source`, `relation`, `target` |
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
