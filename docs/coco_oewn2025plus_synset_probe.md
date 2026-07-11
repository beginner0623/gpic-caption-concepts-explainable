# COCO Object MWE 후보 + OEWN 2025+ Synset Probe

이 문서는 active lexicon 반영 결과가 아니라 COCO source label을 OEWN 2025+ 기준으로 조회한 후보 생성 결과다.
`resources/lexicons` 아래 active extraction/canonicalization lexicon은 수정하지 않았다.

## 적용한 규칙

1. exact 또는 normalized label로 OEWN 2025+ noun synset을 조회한다.
2. 실패하면 hyphen, underscore, space separator variant를 조회한다.
3. 실패하면 hyphen, underscore, space를 제거한 joined variant를 조회한다.
4. 실패하면 OEWN Morphy noun lemmatization query를 조회한다.
5. COCO supercategory direct lexfile evidence는 `person`, `animal`, `food`만 쓴다.
6. 여러 synset이 남으면 OEWN sense id를 WordNet sense key로 바꿔 WN3.0 lemma count를 확인한다.
7. selected 후보가 나오더라도 lexfile objectness gate를 통과해야 최종 selected로 남긴다.
8. object-compatible lexfile은 pass, conditional/hard-conflict lexfile은 manual-check ambiguous로 보낸다.
9. 사용자가 승인한 COCO label-level manual decision은 일반 rule보다 우선한다.
10. selected OEWN synset이 있는 row는 모든 immediate hypernym을 parent evidence로 기록한다. parent 하나를 고르지 않는다.

## Objectness Gate

- object-compatible: `noun.animal`, `noun.artifact`, `noun.body`, `noun.food`, `noun.object`, `noun.person`, `noun.plant`, `noun.substance`
- conditional: `noun.communication`, `noun.possession`, `noun.phenomenon`, `noun.shape`, `noun.location`, `noun.group`, `noun.Tops`
- hard conflict: `noun.act`, `noun.attribute`, `noun.cognition`, `noun.event`, `noun.feeling`, `noun.motive`, `noun.process`, `noun.quantity`, `noun.relation`, `noun.state`, `noun.time`

## Summary

- `rows`: 80
- `mwe_candidate_rows`: 15
- `oewn_matched_rows`: 79
- `selected_oewn_rows`: 78
- `parent_evidence_rows`: 78
- `ambiguous_oewn_rows`: 0
- `rejected_oewn_rows`: 1
- `unresolved_oewn_rows`: 1
- `manual_selected_rows`: 11
- `manual_rejected_rows`: 1

## Lookup Case Count

|case|count|
|---|---|
|exact|75|
|joined_variant|3|
|morphy|1|
|unresolved|1|

## Selection Tag Count

|tag|count|
|---|---|
|manual_reject|1|
|manual_select|11|
|selected_by_coco_supercategory_oewn_lexfile|11|
|selected_by_wn30_lemma_count|22|
|selected_by_wn30_lemma_count_after_coco_lexfile|2|
|single_oewn_noun_synset|32|
|unresolved_no_oewn_noun_synset|1|

## MWE Candidate Status Count

|status|count|
|---|---|
|not_mwe|65|
|rejected|1|
|selected|13|
|unresolved|1|

## Objectness Gate Count

|gate|objectness_class|count|
|---|---|---|
|manual_override|conditional|3|
|manual_override|object_compatible|8|
|not_applicable||2|
|pass|object_compatible|67|

## Manual Label Decisions

아래 결정은 일반적인 synset selection rule이 아니라 COCO category label에 대한 명시적 결정이다.

|label|decision|selected synset|lexfile|reason|
|---|---|---|---|---|
|`person`|select|`oewn-00007846-n`|`noun.Tops`|COCO `person`은 human being 의미다. OEWN에서는 이 의미가 `noun.Tops`에 들어간다.|
|`traffic light`|select|`oewn-06887235-n`|`noun.communication`|신호라는 의미 때문에 communication lexfile이지만 COCO에서는 물리 object다.|
|`stop sign`|select|`oewn-92470663-n`|`noun.communication`|sign이라는 의미 때문에 communication lexfile이지만 COCO에서는 물리 object다.|
|`sports ball`|reject|||OEWN `sportsball`은 `noun.act`이며 COCO의 physical ball 의미가 아니다.|
|`kite`|select|`oewn-03626682-n`|`noun.artifact`|COCO sports category의 kite는 toy artifact 의미다.|
|`hot dog`|select|`oewn-07713282-n`|`noun.food`|COCO food category는 sausage-only가 아니라 bun에 담긴 hot dog 의미로 본다.|
|`cake`|select|`oewn-07644479-n`|`noun.food`|COCO food category는 baked cake 의미로 본다.|
|`tv`|select|`oewn-04413042-n`|`noun.artifact`|COCO electronic category는 physical TV set 의미다.|
|`microwave`|select|`oewn-03766619-n`|`noun.artifact`|COCO appliance category는 microwave oven object 의미다.|
|`toaster`|select|`oewn-04449446-n`|`noun.artifact`|COCO appliance category는 physical toaster 의미다.|
|`book`|select|`oewn-02873453-n`|`noun.artifact`|사용자 결정: COCO `book`은 physical artifact sense로 고정한다.|
|`scissors`|select|`oewn-04155119-n`|`noun.artifact`|COCO indoor category는 cutting tool object 의미다.|

## 해석

- COCO 80 category 중 `sports ball`은 reject, `potted plant`는 unresolved로 남겼다.
- 현재 COCO 후보 TSV에는 ambiguous row가 없다. 예전 summary의 `ambiguous_oewn_rows: 1`은 `sports ball`의 manual reject 반영 전 상태가 남은 stale summary였다.
- `sports ball` 자체는 COCO object label이지만, OEWN 2025+에서 조회되는 `sportsball` synset은 `noun.act`라서 object synset으로 쓰지 않는다.
- `potted plant`는 자동 lookup rule로 OEWN noun synset을 찾지 못한다. `pot plant` semantic alias는 쓰지 않는다.
- parent evidence는 selected OEWN synset 기준 immediate hypernym 전체다. 예를 들어 `dog`는 `canine/canid`와 `domestic animal/domesticated animal` parent를 모두 보존한다.
- 이 파일은 source-label 후보 파일이다. active extraction lexicon으로 승격하려면 별도 side-effect review가 필요하다.
- `synset_lemmas`는 OEWN이 제공하는 surface 후보 목록이다. canonical probe는 `docs/coco_oewn2025plus_canonical_probe.md`에 따로 기록한다.

