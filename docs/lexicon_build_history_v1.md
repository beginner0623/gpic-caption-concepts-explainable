# Lexicon Build History v1

이 문서는 caption-to-concept v1에서 lexicon 후보를 만들 때 사용한 source, rule, 결정 이력을 한곳에 모으는 master log다.

중요한 구분:

- `resources/source_labels/*`: 외부 dataset label을 정리한 후보 파일이다.
- `resources/lexicons/*`: 실제 pipeline에서 사용하는 active lexicon이다.
- source-label 후보를 만들었다고 해서 active extraction/canonicalization rule에 반영된 것은 아니다.

## 1. 공통 원칙

### 1.1 공통 synset 선정 rule과 dataset metadata input을 구분한다

synset 선정 흐름은 공통 rule 하나로 유지한다. 다만 각 dataset이 제공하는
metadata 종류가 다르므로, 공통 rule의 dataset evidence 입력값은 dataset마다 다르다.
이 차이는 새 전용 rule이 아니라 source adapter 차이다.

|dataset|허용하는 dataset-specific evidence|
|---|---|
|COCO|COCO label + COCO supercategory|
|Open Images|label + hierarchy, MID, parent metadata|
|LVIS|label surface lookup 뒤 남은 OEWN 후보를 고를 때 LVIS synset metadata를 evidence로 사용|
|Visual Genome|label surface lookup 뒤 남은 OEWN 후보를 고를 때 object-level synset occurrence metadata를 evidence로 사용|
|Objects365|metadata가 약하면 OEWN lookup + conflict check 중심|
|V3Det|hierarchy tree, category description|
|ImageNet / ImageNet-21K|WordNet synset ID 자체를 핵심 근거로 사용|

COCO supercategory evidence는 COCO에서만 쓴다. 다른 dataset label에 COCO supercategory mapping을 가져가지 않는다.

Dataset synset metadata가 있어도 source label surface lookup을 건너뛰지 않는다.
Synset metadata는 lookup query를 대체하는 rule이 아니라, source label lookup으로 얻은 후보가 여러 개일 때 어떤 후보를 고를지 정하는 evidence input이다.
Metadata가 source label lookup 결과와 맞지 않으면 query를 바꿔서 살리지 않고 conflict, ambiguous, 또는 unresolved로 기록한다.

### 1.2 공통 흐름

Dataset-specific evidence는 다르지만 전체 흐름은 공유한다.

1. source label 수집
2. OEWN 2025+ noun synset lookup
3. lookup recovery
4. source label lookup 결과 후보 안에서 dataset-specific evidence로 후보 filtering
5. WN3.0 lemma count fallback
6. objectness gate
7. unresolved 또는 conflict는 manual decision
8. selected 후보만 active lexicon 승격 검토

### 1.3 Active lexicon 승격 조건

Object MWE 후보를 active `object_mwes.tsv`로 승격하려면 최소 조건은 아래와 같다.

```text
is_mwe_candidate == true
AND mwe_candidate_status == selected
AND selected_oewn_synset != ""
```

`rejected`, `ambiguous`, `unresolved`는 active MWE로 쓰지 않는다.

### 1.4 Semantic alias는 자동 recovery rule로 쓰지 않는다

Source label 후보 생성에서 자동 lookup recovery로 허용하는 것은 형태 기반 normalization뿐이다.

허용:

- lowercase / whitespace normalization
- hyphen, underscore, space separator variant
- separator 제거 joined variant
- WordNet/OEWN Morphy 결과

금지:

- `potted plant -> pot plant` 같은 semantic alias
- `sports ball -> ball` 같은 head fallback
- 특정 label 하나를 살리기 위한 manual query replacement
- dataset label 실패를 숨기는 one-off rescue mapping

자동 rule로 조회되지 않으면 `unresolved`로 남긴다.
시각 object category와 맞지 않는 synset만 조회되면 `rejected` 또는 `ambiguous`로 남긴다.
Manual decision은 사용자가 특정 label의 synset 선택 또는 reject를 명시적으로 승인한 경우에만 기록한다.
Manual decision은 lookup query 자체를 바꾸는 근거로 쓰지 않는다.

### 1.5 Canonical 선택은 synset 선택과 분리한다

Synset은 의미 anchor이고 canonical은 count에 쓸 대표 surface다. 둘을 섞지 않는다.

틀린 방식:

```text
canonical = 사전 lemma 목록의 첫 표기
canonical = 특정 source dataset label
```

맞는 방식:

1. `selected_oewn_synset`을 의미 ID로 고정한다.
2. source label에서 만든 formal surface variants 또는 selected query와 형태적으로 연결되는 OEWN/WordNet lemma만 canonical 후보로 둔다.
   - lowercase 차이는 무시한다.
   - whitespace 반복은 하나로 정규화한다.
   - OEWN/WordNet 내부 underscore는 space 표기로 해석한다.
   - source label에서 separator variant와 joined variant를 만들 수 있다.
   - canonical 자체는 반드시 selected synset의 OEWN/WordNet lemma 중 하나여야 한다.
   - 같은 synset 안에 있더라도 source label과 형태 매칭되지 않는 lemma는 후보로 쓰지 않는다.
   - formal lookup case인 `exact`, `separator_variant`, `joined_variant`, `morphy`의 selected query도 canonical 후보 근거로 쓴다.
   - dataset별 semantic alias는 자동 canonical 후보 근거로 쓰지 않는다.
3. canonical 후보가 하나뿐이면 WN3.0 `lemma.count()`가 0이어도 그 lemma를 canonical surface로 선택한다.
   - 이 경우 count는 선택 기준이 아니라 기록값이다.
   - WN3.0 count mapping이 없어서 `-1`로 기록되는 경우도 후보가 하나뿐이면 선택한다.
4. canonical 후보가 둘 이상이면 WN3.0 `lemma.count()`를 비교한다.
5. count가 0보다 큰 단독 최대값이면 그 lemma를 canonical surface로 선택한다.
6. count가 모두 0이거나 동률이면 source dataset의 official label surface와 정확히 같은 lemma를 canonical surface로 선택한다.
   - 정확히 같다는 뜻은 lowercase와 whitespace normalization만 적용한다는 뜻이다.
   - 이 tie-break에서는 space, hyphen, underscore를 제거해서 같다고 보지 않는다.
   - 예: `hot dog`와 `hotdog`는 다르다.
7. official label surface와 같은 lemma가 하나도 없거나 둘 이상이면 남은 OEWN lemma 후보끼리 Google Books Ngram frequency를 비교한다.
8. source label variant와 형태 매칭되는 WordNet lemma가 없고 selected synset lemma가 여러 개이면 `ambiguous`로 둔다.
9. Google Books Ngram 후보군은 남은 OEWN/WordNet lemma 후보로 제한한다.
   - source surface 자체가 OEWN lemma가 아니면 canonical 후보가 아니다.
   - 같은 synset 내부 lemma라도 source surface variant 또는 selected query와 맞지 않는 `cell`, `board` 같은 generic lemma는 후보에 넣지 않는다.
10. Google Books Ngram frequency는 English 2019 corpus, 2000-2019, case-insensitive, smoothing 0의 mean frequency를 사용한다.
11. Ngram mean frequency가 0보다 큰 단독 최대값이면 그 surface를 canonical surface로 선택한다.
12. Ngram evidence가 있는 후보가 하나뿐이고 그 mean frequency가 0보다 크면 그 surface를 canonical surface로 선택한다.
13. Ngram fallback 단계에 도달했는데 현재 저장된 Ngram evidence TSV에 해당 candidate evidence가 없으면 먼저 Google Ngram evidence를 생성하거나 갱신한다.
14. Google Ngram API 조회 뒤에도 positive evidence가 없거나 동률이면 `ambiguous`로 둔다.
15. source label과 형태 매칭되는 WordNet lemma가 없더라도 selected synset lemma가 하나뿐이면 그 lemma를 선택한다.

`wordfreq`, `SUBTLEX`는 현재 canonical 선택 rule에서 쓰지 않는다.

예:

```text
source surfaces:
  cell phone
  mobile phone
  cellphone

selected synset lemmas:
  cellular_telephone
  cellular_phone
  cellphone
  cell
  mobile_phone

canonical 후보:
  cellphone
  mobile_phone

제외:
  cell
  cellular_phone
  cellular_telephone
```

통합 inventory 기준 canonical decision은 아래 파일에 저장한다.

|file|role|
|---|---|
|`resources/source_labels/object_synset_canonical_decisions.tsv`|selected OEWN synset group별 canonical lemma decision|
|`resources/source_labels/object_synset_canonical_ambiguous.tsv`|canonical을 결정하지 못한 synset group|
|`resources/source_labels/google_ngram_canonical_frequency_evidence.tsv`|Google Books Ngram canonical frequency fallback evidence|

이 파일들은 active lexicon이 아니다. `ambiguous` row는 active canonical lexicon으로 승격하지 않는다. Active `resources/lexicons/*` 생성은 전체 dataset source-label 정리가 끝난 뒤 사용자가 명시적으로 지시할 때만 한다.

### 1.6 Parent evidence는 selected synset의 immediate hypernym을 전부 보존한다

Parent는 canonical surface string에서 다시 고르지 않는다. Parent evidence는 `selected_oewn_synset`에 직접 연결된 OEWN 2025+ 1-hop hypernym 전체다.

원칙:

1. `selected_oewn_synset`이 있는 row만 대상으로 한다.
2. selected synset의 모든 immediate hypernym을 parent evidence로 저장한다.
3. parent 하나를 억지로 고르지 않는다.
4. parent count를 만들 때는 parent lemma 하나가 아니라 parent synset id를 count key로 쓴다.
5. parent lemma는 display label 후보로만 본다.
6. unresolved, rejected, ambiguous-no-selected row는 parent evidence를 비워 둔다.
7. broad category까지 올라가는 closure는 현재 rule에 포함하지 않는다.

예:

```text
selected synset:
  dog

immediate parents:
  canine / canid
  domestic animal / domesticated animal
```

이 경우 parent evidence는 2개 모두 보존한다. `animal` 같은 더 넓은 category로 올리는 것은 별도 ontology closure rule이며 현재 후보 생성 rule에 포함하지 않는다.

### 1.7 Dataset 누적은 통합 inventory TSV에서만 한다

각 source dataset 후보 생성기는 자기 dataset의 label만 처리한다. 특정 dataset builder가 COCO 같은 이전 dataset 파일을 직접 읽어서 reuse하지 않는다.

누적 비교와 conflict 검사는 별도 통합 파일에서 한다.

|file|role|
|---|---|
|`resources/source_labels/object_source_label_synset_inventory.tsv`|duplicate를 제외한 source label synset 후보 row 누적|
|`resources/source_labels/object_source_label_duplicates.tsv`|prior inventory와 exact normalized label key가 겹쳐 semantic 처리를 생략한 source occurrence row|
|`resources/source_labels/object_source_label_synset_conflicts.tsv`|같은 `source_label_key`가 서로 다른 selected synset을 가진 경우 기록|

원칙:

1. COCO, Objects365, Open Images, LVIS, Visual Genome 등 각 dataset은 dataset별 후보 TSV를 만든다.
2. 통합 builder가 dataset별 TSV를 모아 semantic inventory TSV와 duplicate TSV를 분리해서 만든다.
3. 다음 dataset 처리 logic은 COCO 파일을 직접 보지 않는다.
4. 다음 dataset 처리 시 prior integrated inventory에 같은 `lowercase + whitespace normalize` label key가 있으면 duplicate row로 표시하고 OEWN lookup을 하지 않는다.
5. duplicate row는 selected synset, canonical surface, parent evidence를 비워 둔다.
6. duplicate row는 synset inventory에 넣지 않고 duplicate TSV에만 기록한다.
7. conflict가 있으면 통합 conflict TSV에 기록하고, 필요한 경우 사용자에게 보여준 뒤 manual decision으로 처리한다.
8. canonical surface는 dataset이 늘어나면 후보 surface pool이 달라지므로, 최종 active canonical lexicon 생성 단계에서 통합 inventory 기준으로 다시 계산한다.
9. parent evidence는 selected synset 기반이므로 dataset별 후보 row에 보존할 수 있지만, active parent lexicon 생성은 별도 단계에서 한다.

## 2. COCO Object Label 후보 생성

### 2.1 Source files

|file|role|
|---|---|
|`resources/source_labels/coco_instances_2017_categories.tsv`|COCO 80 category labels|
|`resources/source_labels/coco_wordnet_candidates.tsv`|초기 WordNet 후보 실험|
|`resources/source_labels/coco_oewn2025_synset_candidates.tsv`|OEWN 2025 후보 실험|
|`resources/source_labels/coco_oewn2025plus_synset_candidates.tsv`|현재 COCO OEWN 2025+ 후보 결과|

### 2.2 Current script

|file|role|
|---|---|
|`scripts/build_coco_oewn_candidates.py`|COCO label을 OEWN 2025+ synset candidate row로 변환|

### 2.3 COCO lookup rule

1. exact normalized label로 OEWN 2025+ noun synset 조회
2. 실패하면 hyphen, underscore, space separator variant 조회
3. 실패하면 hyphen, underscore, space 제거 joined variant 조회
4. 실패하면 OEWN Morphy noun lemmatization query 조회
5. 실패하면 unresolved

예:

|COCO label|selected lookup|
|---|---|
|`cell phone`|`cellphone`|
|`wine glass`|`wineglass`|
|`skis`|`ski` via Morphy|
|`potted plant`|unresolved. `pot plant` semantic alias는 쓰지 않음|

### 2.4 COCO synset selection rule

1. synset이 1개면 일단 선택한다.
2. synset이 여러 개면 COCO supercategory direct lexfile evidence를 본다.
3. COCO direct lexfile evidence는 강한 것만 사용한다.

|COCO supercategory|OEWN lexfile evidence|
|---|---|
|`person`|`noun.person`|
|`animal`|`noun.animal`|
|`food`|`noun.food`|

나머지 COCO supercategory는 broad해서 자동 lexfile mapping으로 쓰지 않는다.

4. 그래도 여러 개면 WN3.0 sense key lemma count를 본다.
5. lemma count 최대값이 유일하면 선택한다.
6. count가 모두 0이거나 동률이면 ambiguous로 둔다.

### 2.5 Objectness gate

Selected synset이 나오더라도 OEWN lexfile이 object로 쓸 수 있는지 확인한다.

|class|lexfile|
|---|---|
|object-compatible|`noun.animal`, `noun.artifact`, `noun.body`, `noun.food`, `noun.object`, `noun.person`, `noun.plant`, `noun.substance`|
|conditional|`noun.communication`, `noun.group`, `noun.location`, `noun.phenomenon`, `noun.possession`, `noun.shape`, `noun.Tops`|
|hard conflict|`noun.act`, `noun.attribute`, `noun.cognition`, `noun.event`, `noun.feeling`, `noun.motive`, `noun.process`, `noun.quantity`, `noun.relation`, `noun.state`, `noun.time`|

Conditional 또는 hard-conflict는 자동으로 active lexicon에 넣지 않는다.

### 2.6 Manual COCO label decisions

Manual decision은 COCO label에만 적용한다. 일반 caption token이나 다른 dataset label에는 확장하지 않는다.

|label|decision|synset|reason|
|---|---|---|---|
|`person`|select|`oewn-00007846-n`|COCO person은 human being 의미다. OEWN에서는 이 의미가 `noun.Tops`다.|
|`traffic light`|select|`oewn-06887235-n`|COCO에서는 physical signal object다.|
|`stop sign`|select|`oewn-92470663-n`|COCO에서는 physical sign object다.|
|`sports ball`|reject||OEWN `sportsball`은 `noun.act`이며 physical ball이 아니다.|
|`kite`|select|`oewn-03626682-n`|COCO sports category의 kite는 toy artifact다.|
|`hot dog`|select|`oewn-07713282-n`|COCO food category는 bun에 담긴 hot dog 의미로 본다.|
|`cake`|select|`oewn-07644479-n`|COCO food category는 baked cake 의미로 본다.|
|`tv`|select|`oewn-04413042-n`|COCO electronic category는 physical TV set이다.|
|`microwave`|select|`oewn-03766619-n`|COCO appliance category는 microwave oven object다.|
|`toaster`|select|`oewn-04449446-n`|COCO appliance category는 physical toaster다.|
|`book`|select|`oewn-02873453-n`|사용자 결정: COCO book은 physical artifact sense로 고정한다.|
|`scissors`|select|`oewn-04155119-n`|COCO indoor category는 cutting tool object다.|

### 2.7 Current COCO result

|metric|value|
|---|---:|
|rows|80|
|selected OEWN synset rows|78|
|parent evidence rows|78|
|manual selected rows|11|
|manual rejected rows|1|
|unresolved rows|1|

`sports ball`은 `is_mwe_candidate=true`이지만 `mwe_candidate_status=rejected`이므로 active MWE로 쓰지 않는다.
`potted plant`는 자동 lookup rule로 OEWN noun synset을 찾지 못하므로 unresolved로 남긴다.

## 3. Objects365 Object Label 후보 생성

### 3.1 Source files

|file|role|
|---|---|
|`resources/source_labels/objects365_v2_categories.tsv`|Objects365 V2 365 category labels|
|`resources/source_labels/objects365_oewn2025plus_synset_candidates.tsv`|Objects365 OEWN 2025+ 후보 전체|
|`resources/source_labels/objects365_oewn2025plus_ambiguous.tsv`|ambiguous-like 후보|
|`resources/source_labels/objects365_oewn2025plus_unresolved.tsv`|unresolved-like 후보|

### 3.2 Current script

|file|role|
|---|---|
|`scripts/build_objects365_oewn_candidates.py`|Objects365 V2 label을 OEWN 2025+ synset candidate row로 변환|

### 3.3 Objects365 source rule

Objects365 source label은 MMDetection `Objects365V2Dataset`에서 가져왔다.

|항목|값|
|---|---|
|commit|`cfd5d3a985b0249de009b67d04f37263e11cdf3d`|
|class|`Objects365V2Dataset`|
|rows|365|

Objects365에는 COCO supercategory rule을 적용하지 않는다.

처리 원칙:

1. Objects365 후보 생성기는 COCO 후보 TSV를 직접 읽지 않는다.
2. prior source는 `object_source_label_synset_inventory.tsv`다.
3. current dataset인 Objects365 row는 prior inventory에서 제외하고 본다.
4. prior inventory에 같은 `label_key`가 있으면 `selection_status=duplicate_existing_label_key`로 기록하고 OEWN lookup을 하지 않는다.
5. duplicate row는 selected synset, canonical surface, parent evidence를 비워 둔다.
6. prior inventory에 없는 Objects365 label만 Objects365 source label 자체로 OEWN 2025+ lookup을 수행한다.
7. 같은 의미처럼 보여도 surface가 다르면 자동 reuse하지 않는다.
8. semantic alias, head fallback, label-specific rescue mapping은 쓰지 않는다.
9. 여러 OEWN synset 후보가 있으면 object-compatible + conditional lexfile 후보군 안에서 WN3.0 lemma count를 먼저 비교한다.
10. object-compatible + conditional 후보군 안에서 단독 positive max가 없으면 ambiguous로 남긴다.
11. object-compatible + conditional 후보가 없을 때만 나머지 후보에서 WN3.0 lemma count를 본다.
12. selected candidate가 conditional/hard-conflict이면 기존 objectness gate로 ambiguous/manual-check 처리한다.
13. 사용자가 명시적으로 승인한 Objects365 ambiguous label은 manual synset decision으로 선택한다.
14. 이미 selected된 row는 manual decision으로 덮어쓰지 않는다.
15. 여러 후보 중 첫 번째 허용 후보를 고른 manual selected row는 `first_object_compatible_fallback`으로 따로 tag한다.
16. 사용자가 명시적으로 reject한 label은 `selection_status=rejected`와 `manual_reject`로 남긴다.
17. typo correction, semantic alias, head fallback은 쓰지 않는다.
18. duplicate, selected, rejected, unresolved는 상태를 구분해 TSV에 남긴다.

### 3.4 Current Objects365 result

|metric|value|
|---|---:|
|rows|365|
|duplicate existing label-key rows|69|
|OEWN lookup rows|296|
|selected total|229|
|manual selected rows|46|
|manual first-allowed selected rows|14|
|manual rejected rows|7|
|ambiguous-like rows|0|
|unresolved-like rows|60|
|MWE candidate rows|80|

Current integrated inventory after COCO + Objects365:

|metric|value|
|---|---:|
|semantic inventory rows|376|
|duplicate rows|69|
|source occurrence rows|445|
|COCO rows|80|
|Objects365 semantic rows|296|
|selected rows|307|
|ambiguous rows|0|
|rejected rows|8|
|unresolved rows|61|
|conflict label keys|0|

상세 결과는 `docs/objects365_oewn2025plus_synset_probe.md`에 기록했다.

## 4. OpenImages Object Label 후보 생성

### 4.1 Source files

|file|role|
|---|---|
|`resources/source_labels/openimages_boxable_classes.tsv`|OpenImages MID/display label/hierarchy metadata source rows|
|`resources/source_labels/openimages_oewn2025plus_synset_candidates.tsv`|OpenImages OEWN 2025+ 후보 전체|
|`resources/source_labels/openimages_oewn2025plus_ambiguous.tsv`|OpenImages ambiguous 후보|
|`resources/source_labels/openimages_oewn2025plus_unresolved.tsv`|OpenImages unresolved 후보|

### 4.2 Current script

|file|role|
|---|---|
|`scripts/build_openimages_oewn_candidates.py`|OpenImages boxable label을 OEWN 2025+ synset candidate row로 변환|

### 4.3 OpenImages source rule

OpenImages source label은 공식 `class-descriptions-boxable.csv`와 `bbox_labels_600_hierarchy.json`에서 가져왔다.

|항목|값|
|---|---|
|class descriptions|`https://storage.googleapis.com/openimages/2018_04/class-descriptions-boxable.csv`|
|hierarchy|`https://storage.googleapis.com/openimages/2018_04/bbox_labels_600_hierarchy.json`|
|rows|601|

OpenImages MID와 hierarchy parent/child metadata는 TSV에 보존하지만 자동 synset rescue rule로 쓰지 않는다.

처리 원칙:

1. OpenImages 후보 생성기는 COCO/Objects365 후보 TSV를 직접 읽지 않는다.
2. prior source는 `object_source_label_synset_inventory.tsv`다.
3. current dataset인 OpenImages row는 prior inventory에서 제외하고 본다.
4. prior inventory에 같은 `label_key`가 있으면 `selection_status=duplicate_existing_label_key`로 기록하고 OEWN lookup을 하지 않는다.
5. duplicate row는 selected synset, canonical surface, parent evidence를 비워 둔다.
6. prior inventory에 없는 OpenImages label만 OpenImages source label 자체로 OEWN 2025+ lookup을 수행한다.
7. semantic alias, head fallback, label-specific rescue mapping은 쓰지 않는다.
8. 여러 OEWN synset 후보가 있으면 object-compatible + conditional lexfile 후보군 안에서 WN3.0 lemma count를 먼저 비교한다.
9. object-compatible + conditional 후보군 안에서 단독 positive max가 없으면 ambiguous로 남긴다.
10. object-compatible + conditional 후보가 없을 때만 나머지 후보에서 WN3.0 lemma count를 본다.
11. selected candidate가 conditional/hard-conflict이면 기존 objectness gate로 ambiguous/manual-check 처리한다.
12. 사용자가 명시적으로 승인한 ambiguous label은 manual synset decision으로 선택하거나 reject한다.
13. manual decision은 lookup query를 바꾸지 않는다.
14. OpenImages hierarchy parent label은 자동 rule로 쓰지 않고, 사용자가 승인한 manual decision의 note/evidence로만 남긴다.

### 4.4 Current OpenImages result

|metric|value|
|---|---:|
|rows|601|
|duplicate existing label-key rows|180|
|OEWN lookup rows|421|
|selected rows|359|
|manual selected rows|64|
|manual_select rows|58|
|manual first-allowed selected rows|6|
|manual rejected rows|2|
|rejected rows|2|
|ambiguous rows|0|
|unresolved rows|60|
|MWE candidate rows|168|
|parent evidence rows|359|

Current integrated inventory after COCO + Objects365 + OpenImages:

|metric|value|
|---|---:|
|semantic inventory rows|797|
|duplicate rows|249|
|source occurrence rows|1046|
|COCO rows|80|
|Objects365 semantic rows|296|
|OpenImages semantic rows|421|
|selected rows|666|
|ambiguous rows|0|
|rejected rows|10|
|unresolved rows|121|
|conflict label keys|0|

상세 결과는 `docs/openimages_oewn2025plus_synset_probe.md`에 기록했다.

## 5. LVIS Object Label 후보 생성

### 5.1 Source files

|file|role|
|---|---|
|`resources/source_labels/lvis_v1_categories.tsv`|LVIS v1 category label/synset metadata source rows|
|`resources/source_labels/lvis_oewn2025plus_synset_candidates.tsv`|LVIS OEWN 2025+ 후보 전체|
|`resources/source_labels/lvis_oewn2025plus_ambiguous.tsv`|LVIS ambiguous 후보|
|`resources/source_labels/lvis_oewn2025plus_unresolved.tsv`|LVIS unresolved 후보|

### 5.2 Current script

|file|role|
|---|---|
|`scripts/build_lvis_oewn_candidates.py`|LVIS category label을 OEWN 2025+ synset candidate row로 변환|

### 5.3 LVIS source rule

LVIS source category는 `lvis_v1_val.json.zip` annotation의 `categories`에서 가져왔다.

|항목|값|
|---|---|
|annotation|`https://s3-us-west-2.amazonaws.com/dl.fbaipublicfiles.com/LVIS/lvis_v1_val.json.zip`|
|rows|1203|
|metadata preserved|`name`, `synset`, `synonyms`, `def`, `frequency`, `image_count`, `instance_count`|

처리 원칙:

1. LVIS `name`의 underscore는 surface label에서 space로 해석한다.
2. prior integrated inventory에 같은 `label_key`가 있으면 duplicate로 기록하고 OEWN lookup을 하지 않는다.
3. prior inventory에 없는 LVIS label만 LVIS source label surface로 OEWN 2025+ lookup을 수행한다.
4. lookup recovery는 exact, separator variant, joined variant, OEWN Morphy까지만 허용한다.
5. OEWN 후보가 하나면 그 후보를 선택한다.
6. OEWN 후보가 여러 개이면 LVIS `synset` metadata를 lookup 후보 선택 evidence로 쓴다.
7. LVIS `synset` metadata는 lookup query를 대체하지 않는다.
8. LVIS `synset`이 lookup 후보와 맞지 않으면 query를 바꿔서 살리지 않고 ambiguous로 남긴다.
9. LVIS `synset` metadata가 없을 때만 WN3.0 lemma count fallback을 쓴다.
10. selected candidate가 conditional/hard-conflict이면 기존 objectness gate로 ambiguous/manual-check 처리한다.
11. 사용자가 명시한 ambiguous label decision은 `manual_select`로 기록하되, selected synset이 현재 lookup 후보 안에 있을 때만 허용한다.

### 5.4 Current LVIS result

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

Integrated inventory snapshot after COCO + Objects365 + OpenImages + LVIS, before Visual Genome:

|metric|value|
|---|---:|
|semantic inventory rows|1687|
|duplicate rows|562|
|source occurrence rows|2249|
|COCO rows|80|
|Objects365 semantic rows|296|
|OpenImages semantic rows|421|
|LVIS semantic rows|890|
|selected rows|1437|
|ambiguous rows|0|
|rejected rows|10|
|unresolved rows|240|
|conflict label keys|0|

## 6. Integrated canonical decision

### 6.1 Current script

|file|role|
|---|---|
|`scripts/build_object_synset_canonical_decisions.py`|통합 source-label inventory의 selected OEWN synset group 기준 canonical lemma decision 생성|

### 6.2 Current output

|file|role|
|---|---|
|`resources/source_labels/object_synset_canonical_decisions.tsv`|selected OEWN synset group별 canonical decision|
|`resources/source_labels/object_synset_canonical_ambiguous.tsv`|canonical을 자동 결정하지 못한 synset group|

### 6.3 COCO + Objects365 + OpenImages + LVIS snapshot

|metric|value|
|---|---:|
|selected inventory rows|1437|
|selected synset groups|1368|
|canonical selected rows|1368|
|canonical ambiguous rows|0|
|parent evidence filled rows|1368|
|parent evidence empty rows|0|
|Google Ngram evidence rows|78|
|Google Ngram evidence synset groups|38|

Notable canonical decisions:

|source labels|canonical|selection tag|reason|
|---|---|---|---|
|`Game board`|`gameboard`|`selected_single_source_or_lookup_matched_synset_lemma`|source label joined variant가 selected OEWN lemma `gameboard`와 매칭되어 단일 후보가 됨|
|`cell phone`|`cellphone`|`selected_single_source_or_lookup_matched_synset_lemma`|source label joined variant가 selected OEWN lemma `cellphone`와 매칭되어 단일 후보가 됨|
|`hair drier`, `Hair Dryer`|`hair dryer`|`selected_by_google_ngram_frequency_unique_max`|남은 OEWN lemma 후보 `hair dryer`, `hair drier` 사이에서 Google Ngram 단독 최대값|
|`Chips`, `French Fries`|`chips`|`selected_by_google_ngram_frequency_unique_max`|남은 OEWN lemma 후보 `chips`, `french fries` 사이에서 Google Ngram 단독 최대값|
|`remote`, `Remote control`|`remote`|`selected_by_google_ngram_frequency_unique_max`|남은 OEWN lemma 후보 `remote`, `remote control` 사이에서 Google Ngram 단독 최대값|
|`donut`, `Doughnut`|`doughnut`|`selected_by_google_ngram_frequency_unique_max`|남은 OEWN lemma 후보 `doughnut`, `donut` 사이에서 Google Ngram 단독 최대값|
|`Glasses`, `spectacles`|`glasses`|`selected_by_google_ngram_frequency_unique_max`|남은 OEWN lemma 후보 `glasses`, `spectacles` 사이에서 Google Ngram 단독 최대값|
|`Ice cream`, `icecream`|`icecream`|`selected_by_google_ngram_frequency_unique_max`|남은 OEWN lemma 후보 `icecream`, `ice cream` 사이에서 Google Ngram 단독 최대값|

상세 결과는 `docs/object_synset_canonical_decisions_probe.md`에 기록했다.

Note: 이전 snapshot에서는 신규 34개 canonical candidate group이 Google Ngram evidence 미조회 상태라 ambiguous로 남아 있었다. 현재 snapshot에서는 `resources/source_labels/google_ngram_canonical_frequency_evidence.tsv`를 재생성한 뒤 canonical decision을 다시 만들었고, ambiguous row는 0개다.

Note: 이 canonical decision result는 COCO + Objects365 + OpenImages + LVIS 통합 inventory 기준 historical snapshot이다. Visual Genome v14 manual noun mapping 적용 후 current snapshot은 아래 섹션에 따로 기록한다. Active `resources/lexicons/*` 생성은 아직 하지 않았다.

## 7. Visual Genome v14 manual noun-synset mapping

### 7.1 Source

|file|role|
|---|---|
|`resources/source_labels/visual_genome_ambiguous_manual_decisions_v14_complete_noun_mapping.tsv`|사용자가 제공한 Visual Genome ambiguous row별 manual noun-synset decision overlay|

처리 원칙:

1. v14 file의 `manual_decision_for_codex=select:oewn-...-n`만 적용한다.
2. `label_key`가 current Visual Genome candidate row와 매칭되어야 한다.
3. selected synset은 current candidate row의 `all_oewn_synsets` 안에 있어야 한다.
4. lookup query는 바꾸지 않는다.
5. OEWN lexfile/objectness class는 reject 기준이 아니라 diagnostic metadata로 유지한다.
6. candidate row의 `synset_selection_tag`는 `manual_select`로 단순화하고, v14의 `decision_tag`, `confidence`, `decision_file_version`, `decision_note`는 `manual_decision_note`에 보존한다.

### 7.2 Verification

|check|value|
|---|---:|
|v14 decision rows|4,499|
|unique label keys|4,499|
|conflicting label keys|0|
|invalid decisions|0|
|missing current candidate keys|0|
|manual synset outside current `all_oewn_synsets`|0|

### 7.3 Visual Genome result after v14 overlay

|metric|value|
|---|---:|
|rows|82,761|
|duplicate existing label-key rows|1,350|
|selected rows|13,111|
|manual selected rows|4,499|
|ambiguous rows|0|
|unresolved rows|68,300|
|MWE candidate rows|62,576|

## 8. Current integrated inventory and canonical decision after Visual Genome

### 8.1 Integrated inventory

|metric|value|
|---|---:|
|semantic inventory rows|83,098|
|duplicate rows|1,912|
|source occurrence rows|85,010|
|COCO rows|80|
|Objects365 semantic rows|296|
|OpenImages semantic rows|421|
|LVIS semantic rows|890|
|Visual Genome semantic rows|81,411|
|selected rows|14,548|
|ambiguous rows|0|
|rejected rows|10|
|unresolved rows|68,540|
|conflict label keys|0|

### 8.2 Canonical decision

|metric|value|
|---|---:|
|selected inventory rows|14,548|
|selected synset groups|9,192|
|canonical selected rows|8,145|
|canonical ambiguous rows|1,047|

Canonical ambiguous rows are not synset-selection ambiguity. They are canonical-surface ambiguity inside already selected synset groups, mostly because Google Ngram evidence is not available for the new Visual Genome-expanded groups.

|canonical selection tag|count|
|---|---:|
|`ambiguous_wn30_mapping_missing_google_ngram_evidence_missing`|990|
|`ambiguous_wn30_all_zero_or_missing_google_ngram_evidence_missing`|54|
|`ambiguous_no_source_variant_or_lookup_matched_oewn_lemma`|2|
|`ambiguous_wn30_tie_google_ngram_evidence_missing`|1|

## 9. Related detailed logs

|file|content|
|---|---|
|`docs/rule_change_review_log_v1.md`|rule change review, side-effect review, decision history|
|`docs/coco_oewn2025plus_synset_probe.md`|COCO OEWN 2025+ current summary|
|`docs/objects365_oewn2025plus_synset_probe.md`|Objects365 OEWN 2025+ current summary|
|`docs/openimages_oewn2025plus_synset_probe.md`|OpenImages OEWN 2025+ current summary|
|`docs/lvis_oewn2025plus_synset_probe.md`|LVIS OEWN 2025+ current summary|
|`docs/object_synset_canonical_decisions_probe.md`|COCO + Objects365 + OpenImages + LVIS 통합 inventory 기준 canonical decision historical snapshot|
|`docs/coco_oewn2025_synset_probe.md`|OEWN 2025 intermediate probe|
|`docs/coco_wikidata_p8814_ambiguous_probe.md`|Wikidata P8814 ambiguous probe|
## 9. Current canonical decision after chunked Google Ngram evidence

This section records the current snapshot after applying Visual Genome v14 manual noun-synset decisions and regenerating Google Books Ngram fallback evidence with chunked requests.

Generated artifacts:

| file | meaning |
|---|---|
| `resources/source_labels/google_ngram_canonical_frequency_evidence.tsv` | Google Books Ngram fallback evidence for unresolved canonical candidates |
| `resources/source_labels/object_synset_canonical_decisions.tsv` | selected OEWN synset group canonical decision |
| `resources/source_labels/object_synset_canonical_ambiguous.tsv` | remaining canonical-surface ambiguity |

Ngram evidence generation:

| metric | value |
|---|---:|
| candidate synset groups needing Ngram | 1,084 |
| requested unique surfaces | 2,454 |
| final evidence rows | 2,457 |
| final evidence synset groups | 1,084 |
| final `ok` rows | 2,456 |
| final `missing` rows | 1 |
| final timeout/error rows | 0 |

Canonical decision result:

| metric | value |
|---|---:|
| selected inventory rows | 14,548 |
| selected synset groups | 9,192 |
| canonical decision rows | 9,192 |
| canonical selected rows | 9,192 |
| canonical ambiguous rows | 0 |

Canonical selection tag counts:

| tag | count |
|---|---:|
| `selected_single_source_or_lookup_matched_synset_lemma` | 7,885 |
| `selected_by_google_ngram_frequency_unique_max` | 1,079 |
| `selected_by_unique_official_source_surface` | 148 |
| `selected_by_wn30_lemma_count_unique_positive_max` | 75 |
| `selected_by_single_available_positive_google_ngram` | 5 |

There are no remaining canonical-surface ambiguous rows.

Note: `Moon|moon` and `sun|Sun` collapse to one normalized Ngram candidate each.
The previous evidence build skipped such groups because it only queried groups
with at least two normalized candidates. The current build queries unresolved
single-candidate groups too, so `moon` and `sun` now have positive Ngram
evidence and are selected automatically.

Note: canonical source surface support keys now include OEWN Morphy noun results
for every source label. This resolved `lice -> louse` and `fila -> filum`
without adding label-specific mappings. The new `horse flies` candidates were
then resolved by Google Ngram as `horse fly`.

Note: Google Ngram returns possessive phrases with apostrophe spacing, e.g.
`men 's` and `cat 's feet`, even when the query surface is `men's` or
`cat's feet`. The evidence builder now normalizes this API spelling back to
the source surface key and prefers the `(All)` case-insensitive aggregate row.
This resolved `men's` vs `men's room` as `men's`, and `cat's feet` vs
`cat's foot` as `cat's feet`.

Note: Google Ngram also returns hyphenated phrases with spaces around hyphens,
e.g. `ping - pong table` and `table - tennis table`. The evidence builder now
normalizes punctuation spacing between word characters, so these API surfaces
match the requested candidate surfaces `ping-pong table` and
`table-tennis table`. This resolved the final canonical ambiguity as
`ping-pong table`.

This snapshot is still source-label evidence only. It has not been promoted into active `resources/lexicons/*`.

## 10. Wiktionary/Wiktextract Preposition MWE Candidate Probe

This section records an offline source probe for preposition-form MWE
candidates. It is not an active relation MWE lexicon and it has not changed
Stage 4 relation extraction.

Source:

| field | value |
|---|---|
| source | Wiktionary via Kaikki/Wiktextract |
| POS page | `https://kaikki.org/dictionary/English/pos-prep/index.html` |
| JSONL | `https://kaikki.org/dictionary/English/pos-prep/kaikki.org-dictionary-English-by-pos-prep.jsonl` |
| filter | `lang_code == "en"`, `pos == "prep"`, surface has at least two whitespace-delimited tokens |

Generated artifacts:

| file | meaning |
|---|---|
| `outputs/wiktionary_prep_mwe_candidates/wiktionary_prep_mwe_candidates.tsv` | unique surface-level candidate rows |
| `outputs/wiktionary_prep_mwe_candidates/wiktionary_prep_mwe_senses.tsv` | sense-level evidence rows |
| `outputs/wiktionary_prep_mwe_candidates/wiktionary_prep_mwe_summary.json` | generation summary |

Generation result:

| metric | value |
|---|---:|
| JSONL entries read | 870 |
| English prep entries | 870 |
| single-token prep entries excluded | 592 |
| MWE prep entries | 278 |
| MWE prep senses | 389 |
| unique MWE surfaces | 278 |

Notes:

- MWE here means at least two whitespace-delimited tokens.
- Single-token prepositions, contractions, abbreviations, and symbols were not
  retained in the candidate TSV.
- Candidate rows keep Wiktionary tags, alternative/form-of targets,
  categories, and sample glosses as evidence.
- No active `resources/lexicons/*` file was updated.

## 11. External Preposition Source Candidate Probe

This section records an offline scrape/probe for additional preposition and
preposition-containing MWE sources requested for manual review. It is not an
active relation MWE lexicon and it has not changed Stage 4 relation extraction.

Sources pulled into `outputs/external_preposition_sources/`:

| source | local path | note |
|---|---|---|
| STREUSLE | `outputs/external_preposition_sources/streusle` | GitHub clone of `nert-nlp/streusle`; JSON/CoNLL-U source data |
| PASTRIE | `outputs/external_preposition_sources/pastrie` | GitHub clone of `nert-nlp/pastrie`; JSON/CoNLL-U-Lex source data |
| PDEP-derived data | `outputs/external_preposition_sources/pdep_ca4pdep` | GitHub clone of `kenclr/ca4pdep`; PDEP-derived feature/count/substitute tables |
| TPP-derived summary | `outputs/external_preposition_sources/pdep_ca4pdep/data/featsTPP.txt` | TPP feature summary bundled in `ca4pdep`; not the original TPP 373-preposition inventory |
| TPP original appendix inventory | ACL Anthology PDF `https://aclanthology.org/W02-0802.pdf` | Litkowski (2002) Appendix Table A-2; extracted as 373 NODE preposition entries |

Generated artifacts:

| file | meaning |
|---|---|
| `outputs/external_preposition_sources/candidate_tables/external_preposition_mwe_candidates_combined.tsv` | combined review table across STREUSLE, PASTRIE, PDEP, and available TPP feature summaries |
| `outputs/external_preposition_sources/candidate_tables/streusle_preposition_mwe_candidates.tsv` | unique STREUSLE preposition-related MWE candidate rows |
| `outputs/external_preposition_sources/candidate_tables/streusle_preposition_mwe_occurrences.tsv` | STREUSLE occurrence-level evidence |
| `outputs/external_preposition_sources/candidate_tables/pastrie_preposition_mwe_candidates.tsv` | unique PASTRIE MWE candidate rows |
| `outputs/external_preposition_sources/candidate_tables/pastrie_preposition_mwe_occurrences.tsv` | PASTRIE occurrence-level evidence |
| `outputs/external_preposition_sources/candidate_tables/streusle_p_lexcat_preposition_mwe_candidates.tsv` | stricter STREUSLE subset where occurrence `lexcat == P` |
| `outputs/external_preposition_sources/candidate_tables/streusle_p_lexcat_preposition_mwe_occurrences.tsv` | occurrence rows supporting the stricter STREUSLE `lexcat == P` subset |
| `outputs/external_preposition_sources/candidate_tables/pastrie_p_lexcat_preposition_mwe_candidates.tsv` | stricter PASTRIE subset where occurrence `lexcat == P` |
| `outputs/external_preposition_sources/candidate_tables/pastrie_p_lexcat_preposition_mwe_occurrences.tsv` | occurrence rows supporting the stricter PASTRIE `lexcat == P` subset |
| `outputs/external_preposition_sources/candidate_tables/streusle_pastrie_p_lexcat_preposition_mwe_candidates.tsv` | combined source-level STREUSLE/PASTRIE `lexcat == P` candidate rows |
| `outputs/external_preposition_sources/candidate_tables/streusle_pastrie_p_lexcat_preposition_mwe_candidates_clean.tsv` | review-ready STREUSLE/PASTRIE `lexcat == P` rows after removing single-word split/typo artifacts |
| `outputs/external_preposition_sources/candidate_tables/streusle_pastrie_p_lexcat_preposition_mwe_candidates_excluded.tsv` | excluded artifact rows removed from the clean STREUSLE/PASTRIE `lexcat == P` inventory |
| `outputs/external_preposition_sources/candidate_tables/pdep_preposition_inventory.tsv` | PDEP preposition surface inventory with sense counts |
| `outputs/external_preposition_sources/candidate_tables/pdep_sense_substitutes.tsv` | PDEP sense-level substitutable preposition evidence |
| `outputs/external_preposition_sources/candidate_tables/tpp_feature_preposition_summary.tsv` | available TPP feature-summary preposition rows from `featsTPP.txt` |
| `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_inventory.tsv` | original TPP/NODE appendix inventory extracted from Litkowski (2002), Table A-2 |
| `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_mwe_inventory.tsv` | multiword-only subset of the Litkowski (2002) appendix inventory |
| `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_mwe_manual_reaudit.tsv` | final curation decisions for the 222 TPP appendix multiword candidates |
| `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_mwe_inventory_clean.tsv` | TPP appendix multiword candidates kept after final curation |
| `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_mwe_inventory_excluded.tsv` | TPP appendix multiword candidates dropped after final curation |
| `outputs/external_preposition_sources/candidate_tables/combined_preposition_mwe_inventory.tsv` | deduplicated combined preposition MWE inventory from TPP, PDEP, Wiktionary, STREUSLE, and PASTRIE |
| `outputs/external_preposition_sources/candidate_tables/combined_preposition_mwe_source_rows.tsv` | source-row evidence behind the combined preposition MWE inventory |
| `outputs/external_preposition_sources/candidate_tables/combined_non_preposition_mwe_inventory.tsv` | deduplicated entries from the same sources that are not kept as preposition MWEs |
| `outputs/external_preposition_sources/candidate_tables/combined_non_preposition_mwe_source_rows.tsv` | source-row evidence behind the non-preposition-MWE inventory |
| `outputs/external_preposition_sources/candidate_tables/combined_preposition_mwe_conflicts.tsv` | entries that appear as preposition MWE in at least one source and non-preposition-MWE in another source |
| `outputs/external_preposition_sources/candidate_tables/external_preposition_source_manifest.tsv` | source file manifest |
| `outputs/external_preposition_sources/candidate_tables/external_preposition_source_summary.json` | generation summary |

Generation result:

| metric | value |
|---|---:|
| combined MWE candidate rows | 1,014 |
| STREUSLE preposition-related MWE occurrences | 1,177 |
| STREUSLE unique candidates | 653 |
| STREUSLE `lexcat == P` occurrences | 137 |
| STREUSLE `lexcat == P` unique candidates | 50 |
| PASTRIE MWE occurrences | 329 |
| PASTRIE unique candidates | 210 |
| PASTRIE `lexcat == P` occurrences | 74 |
| PASTRIE `lexcat == P` unique candidates | 34 |
| Combined STREUSLE/PASTRIE `lexcat == P` source rows | 84 |
| Combined STREUSLE/PASTRIE `lexcat == P` unique surface keys | 62 |
| Clean STREUSLE/PASTRIE `lexcat == P` source rows | 82 |
| Clean STREUSLE/PASTRIE `lexcat == P` unique surface keys | 60 |
| Excluded STREUSLE/PASTRIE `lexcat == P` artifact rows | 2 |
| Clean STREUSLE/PASTRIE `lexcat == P` rows flagged for unknown SNACS supersense | 3 |
| PDEP preposition entries | 304 |
| PDEP multiword preposition entries | 166 |
| PDEP sense rows | 1,039 |
| TPP feature-summary prepositions | 44 |
| TPP feature-summary multiword prepositions | 0 |
| TPP appendix prepositions | 373 |
| TPP appendix multiword prepositions | 222 |
| TPP appendix multiword candidates kept after final curation | 199 |
| TPP appendix multiword candidates dropped after final curation | 23 |
| TPP appendix extraction corrections from final curation | 5 |
| Combined preposition MWE source rows | 699 |
| Combined preposition MWE unique entries | 365 |
| Combined non-preposition-MWE source rows | 190 |
| Combined non-preposition-MWE unique entries | 179 |
| Combined source disagreement entries after manual drop | 0 |

Notes:

- STREUSLE rows were filtered to MWEs that are preposition-related by lexcat,
  token evidence, or SNACS supersense evidence.
- PASTRIE rows are broader because the corpus itself is described as MWE
  annotation limited to expressions containing a preposition.
- The stricter STREUSLE/PASTRIE `lexcat == P` files keep only MWE occurrences
  whose holistic lexical category is `P`/multiword preposition. They do not keep
  `contains_adp_token`-only rows, `p_supersense`-only rows, `PP` idiomatic
  prepositional phrases, or verbal MWE rows.
- The stricter `lexcat == P` subset is cleaner, but it remains offline evidence
  for manual review rather than an active relation-MWE lexicon.
- A later review step excludes `into` (`In To`) and `within` (`win in`) from
  the STREUSLE/PASTRIE `lexcat == P` clean inventory because their holistic
  lexlemma is a single-token preposition rather than a true multiword
  preposition candidate.
- The clean STREUSLE/PASTRIE `lexcat == P` source table still records `at hand`,
  `in my hand`/surface `in my hands`, and `in this day` with
  `review_supersense_unknown`, but the combined prep-MWE inventory drops them
  as manual decisions because they are idiomatic or ordinary PP expressions, not
  preposition MWEs that take an NP complement.
- PDEP rows come from `prepcnts.csv` and `sense-subs.csv`, which the source
  repository documents as PDEP-derived database extracts.
- The PDEP inventory extraction did perform the intended inventory filter:
  `prepcnts.csv` has 304 preposition entries, and 166 of them have at least two
  whitespace-delimited tokens.
- TPP rows currently come only from the `ca4pdep` TPP feature summary, where the
  44 retrieved preposition labels are all single-token labels.
- Do not interpret `TPP feature-summary multiword prepositions = 0` as evidence
  that the original TPP has no phrasal prepositions. It only describes the
  retrieved `featsTPP.txt` feature-summary artifact.
- Follow-up on 2026-07-10 found the original NODE/TPP appendix list in
  Litkowski (2002), Table A-2. The paper states that the NODE inventory has 373
  prepositions and 847 senses; the extracted appendix table has exactly 373
  entries, including 222 multiword entries.
- The archived `clres.com/prepositions.html` page confirms that Online TPP once
  linked `tppdata.zip` for downloading the full database, but Wayback CDX did
  not show a retrievable 200-status capture for `tppdata.zip` during this probe.
- The current historical `clres.com/prepositions.html` host was checked on
  2026-07-10 and redirects to unrelated casino content, so the live host was not
  used as a data source.
- The final TPP curation keeps expressions whose whole construction has a
  prepositional use, including P+NP+P, coordinated prepositions, and P
  sequences. It drops NP/AP/AdvP/participial-headed expressions. It keeps 199
  of the 222 extracted multiword candidates and drops 23.
- Five extraction corrections are recorded in the final curation output: `#à la` to
  `à la`, `head and shoulders` to `head and shoulders above`, `above inside` to
  `inside`, `not someone's idea` to `not someone's idea of`, and
  `of this side of` to `this side of`.
- The combined preposition MWE inventory deduplicates exact lowercase/whitespace
  normalized entries across TPP final KEEP rows, PDEP multiword preposition
  rows, Wiktionary English `pos=prep` MWE rows, and the clean
  STREUSLE/PASTRIE `lexcat == P` rows. It keeps source provenance in the
  `sources`, `source_entries`, `source_statuses`, and source-reason columns.
- For STREUSLE/PASTRIE rows, the combined inventory uses observed corpus
  surfaces as matcher/lookup `entry` and `lookup_forms`; the corpus MWE
  `lexlemma` is preserved separately as `canonical_lemma` evidence. Thus
  corpus lemmas such as `accord to`, `in term of`, `see as`, and
  `when it come to` are not used as direct lookup entries when their observed
  surfaces are `according to`, `in terms of`, `seeing as`, `when it came to`,
  or `when it comes to`.
- Wiktionary rows tagged as `misspelling` are excluded from the prep-MWE
  inventory and retained in the non-preposition-MWE inventory with
  `wiktionary_misspelling_variant_not_lookup_form`.
- The rows `a matter of`, `as if`, `at hand`, `for example`,
  `from the ground up`, `in my hands`, `in this day`, `seeing as`, and
  `the dickens` are manually dropped from the prep-MWE inventory. These are
  treated as noun-phrase fragments, complete PP/adverbial expressions,
  conjunction-like clause linkers, ordinary PP expressions, or source dump
  errors rather than preposition MWEs that should be matched as relation
  expressions.
- The STREUSLE/PASTRIE variants `d t`, `out ta`, and `rather then` are not kept
  as standalone prep-MWE entries. They are retained only as surface-variant
  evidence under `due to`, `out of`, and `rather than`.
- The combined non-preposition-MWE inventory includes TPP final DROP rows,
  STREUSLE/PASTRIE artifact exclusions, and PDEP single-token prepositions
  marked as `single_word_preposition_not_mwe`.
- On 2026-07-10, the user explicitly approved dropping source-disagreement
  entries from the prep-MWE inventory. The originally reviewed eight entries
  were `a cut above`, `bare of`, `in memoriam`, `little short of`,
  `nothing short of`, `preparatory to`, `short for`, and `shot through with`.
  The same conflict-drop rule is applied to the current combined source audit;
  affected keep-side source rows are retained in the non-preposition-MWE source
  rows with `manual_conflict_drop` evidence, and the regenerated conflict file
  has zero unresolved entries.
- No active `resources/lexicons/*` file was updated.
