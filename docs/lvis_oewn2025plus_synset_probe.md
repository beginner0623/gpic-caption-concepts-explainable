# LVIS OEWN 2025+ Synset Probe

이 문서는 LVIS v1 category label을 OEWN 2025+ noun synset 후보로 변환한 결과다.

이 결과는 active `resources/lexicons/*`에 반영된 것이 아니다. Source-label 후보 생성 결과다.

## Source

|항목|값|
|---|---|
|LVIS annotation|`https://s3-us-west-2.amazonaws.com/dl.fbaipublicfiles.com/LVIS/lvis_v1_val.json.zip`|
|category rows|1203|
|source TSV|`resources/source_labels/lvis_v1_categories.tsv`|
|candidate TSV|`resources/source_labels/lvis_oewn2025plus_synset_candidates.tsv`|
|ambiguous TSV|`resources/source_labels/lvis_oewn2025plus_ambiguous.tsv`|
|unresolved TSV|`resources/source_labels/lvis_oewn2025plus_unresolved.tsv`|

LVIS category metadata 중 `name`, `synset`, `synonyms`, `def`, `frequency`, `image_count`, `instance_count`를 보존했다.

## Rule

1. LVIS `name`의 underscore는 source label surface에서 space로 해석한다.
2. prior integrated inventory에 같은 `lowercase + whitespace normalize` label key가 있으면 duplicate로 기록하고 OEWN lookup을 하지 않는다.
3. prior inventory에 없는 label만 source label surface로 OEWN 2025+ lookup을 수행한다.
4. lookup recovery는 exact, separator variant, joined variant, OEWN Morphy까지만 쓴다.
5. OEWN 후보가 하나면 그 후보를 선택한다.
6. OEWN 후보가 여러 개이면 LVIS `synset` metadata를 lookup 후보 선택 evidence로 쓴다.
7. LVIS `synset` metadata는 lookup query를 대체하지 않는다.
8. LVIS `synset`이 lookup 후보와 맞지 않으면 query를 바꿔서 살리지 않고 ambiguous로 남긴다.
9. LVIS `synset` metadata가 없을 때만 WN3.0 lemma count fallback을 쓴다.
10. selected candidate가 conditional/hard-conflict이면 objectness gate로 ambiguous/manual-check 처리한다.
11. 사용자가 명시한 ambiguous label decision은 `manual_select`로 기록하되, selected synset이 현재 lookup 후보 안에 있을 때만 허용한다.

## Result

|metric|value|
|---|---:|
|rows|1203|
|duplicate existing label-key rows|313|
|OEWN lookup rows|890|
|selected rows|771|
|selected by LVIS synset metadata rows|244|
|manual selected rows|28|
|ambiguous rows|0|
|unresolved rows|119|
|MWE candidate rows|416|
|LVIS synset not in lookup candidate rows|0|

Integrated inventory after COCO + Objects365 + OpenImages + LVIS:

|metric|value|
|---|---:|
|semantic inventory rows|1687|
|duplicate rows|562|
|source occurrence rows|2249|
|selected rows|1437|
|ambiguous rows|0|
|rejected rows|10|
|unresolved rows|240|
|conflict label keys|0|

## Manual-Selected Rows

아래 row들은 사용자가 명시한 synset으로 `manual_select` 처리했다. 이 decision은 lookup query를 바꾸지 않으며, selected synset이 현재 OEWN lookup 후보 안에 있을 때만 허용한다.

|label|selected synset|
|---|---|
|`award`|`oewn-06709228-n`|
|`Bible`|`oewn-06443410-n`|
|`calendar`|`oewn-06499232-n`|
|`card`|`oewn-06639513-n`|
|`diary`|`oewn-06413674-n`|
|`dollar`|`oewn-13417070-n`|
|`milestone`|`oewn-07285872-n`|
|`money`|`oewn-13406050-n`|
|`newspaper`|`oewn-06277798-n`|
|`notebook`|`oewn-06427062-n`|
|`passport`|`oewn-06512928-n`|
|`pennant`|`oewn-06888338-n`|
|`receipt`|`oewn-06532213-n`|
|`tag`|`oewn-07288121-n`|
|`birthday card`|`oewn-06639767-n`|
|`booklet`|`oewn-06425532-n`|
|`buoy`|`oewn-07280883-n`|
|`business card`|`oewn-06437074-n`|
|`identity card`|`oewn-06489042-n`|
|`checkbook`|`oewn-13435483-n`|
|`comic book`|`oewn-06608568-n`|
|`keycard`|`oewn-06489489-n`|
|`phonebook`|`oewn-06435397-n`|
|`postcard`|`oewn-06640445-n`|
|`brake light`|`oewn-07280695-n`|
|`street sign`|`oewn-06806967-n`|
|`windsock`|`oewn-07272250-n`|
|`softball`|`oewn-86432478-n`|

## Notes

- The latest LVIS candidate TSV has 0 ambiguous rows after the 28 manual decisions.
- No active object MWE or canonical lexicon was updated.
- Canonical decision files were not regenerated after LVIS in this step.
