# Integrated Object Synset Canonical Decisions Probe

이 문서는 현재 `object_source_label_synset_inventory.tsv` 기준 canonical lemma decision 결과를 기록한다.

현재 scope는 COCO + Objects365 + OpenImages + LVIS 통합 inventory다.

중요한 구분:

- 이 결과는 `resources/source_labels` 아래 source-label 분석 결과다.
- active `resources/lexicons/*` 파일은 생성하거나 수정하지 않았다.
- active lexicon 생성은 전체 dataset 정리가 끝난 뒤 사용자가 명시적으로 지시할 때만 한다.

## Rule

1. `selection_status == selected`이고 `selected_oewn_synset`이 있는 inventory row만 사용한다.
2. row 단위가 아니라 `selected_oewn_synset` group 단위로 canonical을 결정한다.
3. canonical 후보는 selected synset의 OEWN lemma 중 source label에서 만든 formal surface variants 또는 formal lookup selected query와 형태적으로 맞는 lemma만 사용한다.
4. surface 비교는 lowercase + whitespace normalize 기준이다.
5. OEWN/WordNet underscore는 display space로 해석한다.
6. source label에서 separator variant와 joined variant를 만들 수 있지만, 이것은 OEWN lemma 후보를 거르는 support key일 뿐이다.
7. 후보가 하나면 WN3.0 count가 0이거나 missing이어도 선택한다.
8. 후보가 둘 이상이면 WN3.0 `lemma.count()`가 0보다 큰 단독 최대값일 때 선택한다.
9. count가 없거나 동률이면 source dataset official label surface와 정확히 같은 후보가 하나일 때만 선택한다.
10. 그래도 결정되지 않으면 Google Books Ngram frequency를 비교한다.
11. Google Books Ngram 후보군도 남은 OEWN lemma 후보로만 제한한다. Source official surface 자체가 OEWN lemma가 아니면 canonical 후보가 아니다.
12. Google Ngram fallback 단계에 도달했는데 저장된 evidence TSV에 해당 candidate evidence가 없으면 먼저 Google Ngram evidence를 생성하거나 갱신한다.
13. Google Books Ngram English 2019 corpus, 2000-2019, case-insensitive, smoothing 0의 mean frequency가 0보다 큰 단독 최대값이면 그 surface를 canonical으로 선택한다.
14. Google Ngram API 조회 뒤에도 결정되지 않으면 ambiguous로 둔다.

## Output Files

|file|role|
|---|---|
|`resources/source_labels/object_synset_canonical_decisions.tsv`|selected OEWN synset group별 canonical decision|
|`resources/source_labels/object_synset_canonical_ambiguous.tsv`|canonical을 자동 결정하지 못한 synset group|
|`resources/source_labels/google_ngram_canonical_frequency_evidence.tsv`|Google Books Ngram frequency evidence|

## Summary

|metric|value|
|---|---:|
|selected inventory rows|1437|
|selected synset groups|1368|
|canonical decision rows|1368|
|canonical selected rows|1368|
|canonical ambiguous rows|0|
|parent evidence filled rows|1368|
|parent evidence empty rows|0|
|Google Ngram evidence rows|78|
|Google Ngram evidence synset groups|38|
|Google Ngram evidence status `ok`|77|
|Google Ngram evidence status `missing`|1|

## Canonical Selection Tag Counts

|tag|count|
|---|---:|
|`selected_single_source_or_lookup_matched_synset_lemma`|1314|
|`selected_by_unique_official_source_surface`|8|
|`selected_by_wn30_lemma_count_unique_positive_max`|8|
|`selected_by_google_ngram_frequency_unique_max`|38|

## Canonical Ambiguous Rows

현재 없음.

이전 snapshot에서는 34개 row가 Google Ngram evidence 미조회 상태라 ambiguous로 남아 있었다. 현재 snapshot에서는 `google_ngram_canonical_frequency_evidence.tsv`를 새로 생성한 뒤 canonical decision을 재생성해서 34개가 모두 해소됐다.

## Google Ngram Fallback Rows

|source labels|selected synset|chosen canonical|candidate mean frequencies|
|---|---|---|---|
|`hair drier`, `Hair Dryer`|`oewn-03488399-n`|`hair dryer`|`hair drier:6.84305013696e-11`, `hair dryer:1.12193144497e-09`|
|`Chips`, `French Fries`|`oewn-07726825-n`|`chips`|`chips:5.2664348299e-10`, `french fries:3.65047294476e-11`|
|`remote`, `Remote control`|`oewn-04082075-n`|`remote`|`remote control:1.62401151554e-11`, `remote:3.86420522837e-10`|
|`donut`, `Doughnut`|`oewn-07654678-n`|`doughnut`|`doughnut:5.11211845078e-09`, `donut:3.46026813106e-11`|
|`Glasses`, `spectacles`|`oewn-04279164-n`|`glasses`|`spectacles:7.16374494447e-12`, `glasses:2.59214673164e-11`|
|`Ice cream`, `icecream`|`oewn-07630109-n`|`icecream`|`ice cream:1.65240903773e-10`, `icecream:6.38426390052e-10`|

전체 Google Ngram fallback row는 `object_synset_canonical_decisions.tsv`에서 `canonical_selection_tag == selected_by_google_ngram_frequency_unique_max`로 확인한다.

Google Ngram evidence에서 `missing`인 surface는 `bow-tie` 1개다. 같은 synset group의 다른 후보 `bow tie`, `bowtie` evidence가 있어서 해당 group은 `bowtie`로 선택됐다.

## Not Ngram Fallback

|source labels|selected synset|chosen canonical|selection tag|why|
|---|---|---|---|---|
|`Game board`|`oewn-02860303-n`|`gameboard`|`selected_single_source_or_lookup_matched_synset_lemma`|source label joined variant `gameboard`가 selected OEWN lemma `gameboard`와 매칭되어 단일 후보가 됨|
|`cell phone`|`oewn-02995984-n`|`cellphone`|`selected_single_source_or_lookup_matched_synset_lemma`|source label joined variant `cellphone`이 selected OEWN lemma `cellphone`와 매칭되어 단일 후보가 됨|

## Execution Note

- syntax check:
  - pycache를 쓰지 않는 `compile()` 방식으로 통과했다.
- generation:
  - sandbox 안에서는 atomic temp file 생성이 `PermissionError`로 실패했다.
  - 같은 bounded command를 `require_escalated` 실행 모드로 돌려 TSV를 생성했다.
- current regeneration:
  - LVIS까지 포함한 통합 inventory 기준으로 canonical decision을 재생성했다.
  - Parent evidence는 1368개 canonical decision row 전부에 채워졌다.
  - Google Ngram evidence는 38개 synset group에 대해 새로 조회했다.
  - Google Ngram evidence 조회 후 canonical ambiguous row는 0개다.
- permission status:
  - 이 실행은 output 생성 성공을 의미한다.
  - sandbox write permission 문제가 해결되었다는 뜻은 아니다.
