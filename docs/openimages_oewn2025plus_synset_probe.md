# OpenImages OEWN 2025+ Synset Probe

이 문서는 OpenImages boxable class labels를 OEWN 2025+ noun synset 후보로 변환한 결과를 기록한다.

중요한 구분:

- 이 결과는 `resources/source_labels` 아래 source-label 분석 결과다.
- active `resources/lexicons/*` 파일은 생성하거나 수정하지 않았다.
- OpenImages MID와 hierarchy parent/child metadata는 보존했지만, 자동 synset rescue rule로 쓰지 않았다.

## Source

|item|value|
|---|---|
|class descriptions|`https://storage.googleapis.com/openimages/2018_04/class-descriptions-boxable.csv`|
|hierarchy|`https://storage.googleapis.com/openimages/2018_04/bbox_labels_600_hierarchy.json`|
|source version|`openimages_2018_04_boxable`|
|rows|601|

## Rule

1. prior integrated inventory에 같은 `lowercase + whitespace normalize` label key가 있으면 duplicate로 기록하고 OEWN lookup을 하지 않는다.
2. prior inventory에 없는 label만 OpenImages source label 자체로 OEWN 2025+ lookup을 수행한다.
3. lookup recovery는 형태 기반 recovery만 허용한다.
   - exact normalized label
   - hyphen, underscore, space separator variant
   - joined separator variant
   - OEWN Morphy noun result
4. semantic alias, head fallback, label-specific rescue mapping은 쓰지 않는다.
5. 여러 OEWN synset 후보가 있으면 object-compatible + conditional lexfile 후보군 안에서 WN3.0 lemma count를 먼저 비교한다.
6. object-compatible + conditional 후보군 안에서 단독 positive max가 없으면 ambiguous로 남긴다.
7. object-compatible + conditional 후보가 없을 때만 나머지 후보에서 WN3.0 lemma count를 본다.
8. selected candidate가 conditional/hard-conflict이면 기존 objectness gate로 ambiguous/manual-check 처리한다.
9. OpenImages hierarchy는 TSV에 보존하지만 자동 lexfile mapping으로 쓰지 않는다.
10. 사용자가 명시적으로 승인한 ambiguous label만 manual select 또는 reject로 처리한다.
11. manual decision은 lookup query를 바꾸지 않고, 이미 조회된 OEWN 후보 중 selected synset 또는 reject status만 고정한다.

## Output Files

|file|role|
|---|---|
|`resources/source_labels/openimages_boxable_classes.tsv`|OpenImages MID/display label/hierarchy metadata source rows|
|`resources/source_labels/openimages_oewn2025plus_synset_candidates.tsv`|OpenImages OEWN 2025+ 후보 전체|
|`resources/source_labels/openimages_oewn2025plus_ambiguous.tsv`|OpenImages ambiguous rows|
|`resources/source_labels/openimages_oewn2025plus_unresolved.tsv`|OpenImages unresolved rows|

## Summary

|metric|value|
|---|---:|
|source label rows|601|
|duplicate existing label-key rows|180|
|OEWN lookup rows|421|
|selected rows|359|
|rejected rows|2|
|ambiguous rows|0|
|unresolved rows|60|
|MWE candidate rows|168|
|parent evidence rows|359|
|manual selected rows|64|
|manual rejected rows|2|
|manual_select rows|58|
|manual first-allowed selected rows|6|

Integrated inventory after COCO + Objects365 + OpenImages:

|metric|value|
|---|---:|
|semantic inventory rows|797|
|duplicate rows|249|
|source occurrence rows|1046|
|conflict label keys|0|
|selected rows|666|
|ambiguous rows|0|
|rejected rows|10|
|unresolved rows|121|

## Manual Decision Summary

|decision type|count|
|---|---:|
|manual selected rows|64|
|manual_select rows|58|
|manual first-allowed selected rows|6|
|manual rejected rows|2|

Manual rejected labels:

`Cabinetry`, `Personal care`

Manual first-allowed selected labels after tag correction:

`Carnivore`, `Spatula`, `Squid`, `Footwear`, `Beaker`, `Shellfish`

Manual decisions are source-label candidate decisions only. They do not update active `resources/lexicons/*`.

## Ambiguous Tag Counts

|synset selection tag|count|
|---|---:|
|none|0|

## Ambiguous Labels

없음. `Table`, `Television`은 사용자 승인 manual decision으로 selected 처리했다.

## Execution Note

- OpenImages source download and candidate TSV generation required `require_escalated` because sandboxed network access failed.
- Integrated inventory generation required `require_escalated` because sandboxed same-directory temp file creation failed.
- After the remaining manual decision implementation, OpenImages candidate regeneration required `require_escalated` because sandboxed OEWN sqlite DB access failed.
- After the remaining manual decision implementation, integrated inventory regeneration required `require_escalated` because sandboxed same-directory temp file creation failed.
- After manual selection tag correction, OpenImages candidate regeneration and integrated inventory regeneration required `require_escalated` because sandboxed same-directory temp file creation failed.
- After object-compatible + conditional ranking pool implementation, OpenImages candidate regeneration required `require_escalated` because sandboxed OEWN sqlite DB access failed.
- After object-compatible + conditional ranking pool implementation, integrated inventory regeneration required `require_escalated` because sandboxed same-directory temp file creation failed.
- This means output generation succeeded outside the sandbox. It does not mean the sandbox permission issue is fixed.
