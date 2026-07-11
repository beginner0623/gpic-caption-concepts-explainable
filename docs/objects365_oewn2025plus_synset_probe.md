# Objects365 OEWN 2025+ Synset Probe

이 문서는 Objects365 V2 source label을 OEWN 2025+ noun synset 후보로 정리한 결과다.

중요: 이 결과는 `resources/source_labels` 아래 후보 파일이다. `resources/lexicons`의 active extraction/canonicalization lexicon에는 아직 반영하지 않았다.

## 1. Source

|항목|값|
|---|---|
|dataset|Objects365 V2|
|source implementation|MMDetection `Objects365V2Dataset`|
|source commit|`cfd5d3a985b0249de009b67d04f37263e11cdf3d`|
|source class|`Objects365V2Dataset`|
|source rows|365|
|source TSV|`resources/source_labels/objects365_v2_categories.tsv`|

## 2. Rule

Objects365에는 COCO supercategory처럼 직접 쓸 수 있는 category metadata를 적용하지 않았다.

처리 순서:

1. Objects365 official label을 `lowercase + whitespace normalize`한 `label_key`로 만든다.
2. Objects365 후보 생성기는 COCO 후보 TSV를 직접 읽지 않는다.
   - prior evidence source는 통합 inventory TSV다.
   - 현재 dataset인 Objects365 row는 prior inventory에서 제외하고 본다.
3. prior integrated inventory에 같은 `label_key`가 있으면 `duplicate_existing_label_key`로 표시한다.
   - duplicate row는 OEWN lookup을 하지 않는다.
   - duplicate row는 selected synset, canonical surface, parent evidence를 비워 둔다.
4. prior inventory에 없는 Objects365 label만 OEWN 2025+ lookup을 수행한다.
5. lookup recovery는 형태 기반만 허용한다.
   - exact normalized label
   - hyphen, underscore, space separator variant
   - joined separator variant
   - OEWN Morphy noun result
6. semantic alias와 head fallback은 쓰지 않는다.
   - 예: `potted plant -> pot plant` 같은 rescue mapping 없음
   - 예: `sports ball -> ball` 같은 head fallback 없음
7. synset이 여러 개인데 Objects365 전용 metadata 근거가 없으면 WN3.0 sense-key lemma count를 fallback으로 쓴다.
8. WN3.0 count fallback은 object-compatible + conditional OEWN lexfile 후보군 안에서 먼저 적용한다.
   - object-compatible 또는 conditional 후보가 있으면 그 후보군 안에서만 단독 positive max를 찾는다.
   - 해당 후보군 안에서 단독 positive max가 없으면 ambiguous로 둔다.
   - object-compatible + conditional 후보가 없을 때만 나머지 후보에서 WN3.0 count를 본다.
   - conditional 후보가 단독 positive max이면 objectness gate에서 selected가 아니라 ambiguous/manual-check로 남는다.
9. selected synset은 OEWN lexfile objectness gate를 통과해야 한다.
10. canonical surface와 parent evidence는 후보 row에 evidence로만 기록한다.
   - 최종 canonical surface는 dataset 누적 후 통합 TSV 기준으로 다시 계산해야 한다.
   - parent evidence는 selected synset의 immediate hypernym evidence다.
11. 사용자가 명시적으로 승인한 Objects365 ambiguous label은 manual decision으로 selected 또는 rejected 처리한다.
12. 후보가 여러 개라 첫 번째 허용 후보를 고른 selected row는 일반 manual select와 구분해 `first_object_compatible_fallback`으로 tag한다.
13. typo correction이나 semantic rescue mapping은 쓰지 않는다. 예: `Noddles`는 `Noodles`로 고치지 않는다.

## 3. Output Files

|file|내용|
|---|---|
|`resources/source_labels/objects365_oewn2025plus_synset_candidates.tsv`|365개 전체 후보 row|
|`resources/source_labels/objects365_oewn2025plus_ambiguous.tsv`|ambiguous-like row|
|`resources/source_labels/objects365_oewn2025plus_unresolved.tsv`|unresolved-like row|
|`resources/source_labels/object_source_label_synset_inventory.tsv`|duplicate를 제외한 source label synset 후보 row 누적|
|`resources/source_labels/object_source_label_duplicates.tsv`|prior inventory와 exact normalized label key가 겹쳐 semantic 처리를 생략한 source occurrence row|
|`resources/source_labels/object_source_label_synset_conflicts.tsv`|같은 label key가 서로 다른 selected synset으로 간 conflict report|

## 4. Summary

|metric|count|
|---|---:|
|rows|365|
|duplicate existing label-key rows|69|
|OEWN lookup rows|296|
|selected rows|229|
|selected total|229|
|rejected rows|7|
|ambiguous-like rows|0|
|unresolved-like rows|60|
|manual selected rows|46|
|manual first-allowed selected rows|14|
|manual rejected rows|7|
|canonical selected rows|228|
|parent evidence rows|229|
|MWE candidate rows|80|

Integrated inventory after COCO + Objects365:

|metric|count|
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

`Person`, `Chair`, `Potted Plant`처럼 prior inventory와 exact normalized label key가 겹치는 row는 Objects365 후보 생성 단계에서 duplicate로 기록하고, synset/canonical/parent 처리는 하지 않는다.

현재 conflict report에 남은 exact label-key conflict는 0개다.

## 5. Ambiguous Rows

현재 남은 ambiguous-like row는 0개다.

Object-compatible + conditional first ranking 이후 남았던 4개 row는 사용자 승인 manual decision으로 처리했다.

|label|decision|selected synset|note|
|---|---|---|---|
|`Ring`|select|`oewn-04099721-n`|ring artifact sense|
|`Brush`|select|`oewn-02911542-n`|brush implement sense|
|`Target`|select|`oewn-04401354-n`|sports equipment target sense|
|`French`|reject||object label synset으로 쓰지 않음|

이번 v2에서 사용자가 승인한 first-allowed selected row는 별도 tag로 남겼다.

|label|selected synset|lexfile|decision note|
|---|---|---|---|
|`Van`|`oewn-04527775-n`|`noun.artifact`|group sense 제외 후 첫 artifact 후보|
|`Paddle`|`oewn-03879526-n`|`noun.artifact`|첫 artifact 후보|
|`Scooter`|`oewn-04569408-n`|`noun.artifact`|animal `scoter` 제외 후 첫 artifact 후보|
|`Crane`|`oewn-03131358-n`|`noun.artifact`|person/proper noun 후보 제외 후 artifact crane|
|`Pepper`|`oewn-13170289-n`|`noun.plant`|plant/food 후보가 모두 object-compatible이라 synset order 첫 후보|
|`Extractor`|`oewn-03313097-n`|`noun.artifact`|첫 artifact 후보|
|`Carriage`|`oewn-03901563-n`|`noun.artifact`|첫 artifact 후보|
|`Projector`|`oewn-04016177-n`|`noun.artifact`|첫 artifact 후보|
|`Printer`|`oewn-04011143-n`|`noun.artifact`|person 후보 제외 후 첫 artifact 후보|
|`Shrimp`|`oewn-07810135-n`|`noun.food`|person insult sense 제외 후 food/animal 중 첫 후보|
|`Pasta`|`oewn-07879350-n`|`noun.food`|첫 food 후보|
|`Scallop`|`oewn-07813617-n`|`noun.food`|shape 후보 제외 후 food/animal 중 첫 후보|
|`Dumpling`|`oewn-07717938-n`|`noun.food`|첫 food 후보|
|`Lobster`|`oewn-07808701-n`|`noun.food`|food/animal 중 첫 후보|

이번 v2에서 사용자가 reject한 row는 `selection_status=rejected`로 남겼다.

|label|rejected candidate|reason|
|---|---|---|
|`Soccer`|`oewn-00479273-n`|OEWN 후보가 `noun.act: soccer`뿐이며 object synset이 없음|
|`American Football`|`oewn-00470726-n`|`noun.act: American football game`뿐이며 공 object correction은 하지 않음|
|`Tennis`|`oewn-00483309-n`|`noun.act: tennis`뿐임|
|`Noddles`|`oewn-05619467-n`|typo-looking label이지만 `Noodles`로 고치지 않음; `noddle`은 `noun.cognition`|
|`Curling`|`oewn-00462672-n`|`noun.act: curling`뿐임|
|`Table Tennis`|`oewn-00500274-n`|`noun.act: table tennis / ping pong`뿐임|

## 6. Unresolved-Like Rows

총 60개다. prior inventory duplicate row는 unresolved에 포함하지 않는다.

|type|count|labels|
|---|---:|---|
|`unresolved`|60|Other Shoes, Cabinet/shelf, Handbag/Satchel, Picture/Frame, Storage box, Leather Shoes, Bowl/Basin, Moniter/TV, Trash bin Can, Barrel/bucket, Bakset, Pen/Pencil, Wild Bird, Canned, Traffic cone, Stuffed Toy, Power outlet, Traffic Sign, Ballon, Dinning Table, Blackboard/Whiteboard, Other Fish, Orange/Tangerine, Machinery Vehicle, Green Vegetables, Skiboard, Nightstand, Surveillance Camera, Skating and Skiing shoes, Other Balls, Computer Box, Cleaning Products, Cutting/chopping Board, Side Table, Billards, Cigar/Cigarette, Heavy Truck, Extention Cord, Tong, Coffee Machine, Washing Machine/Drying Machine, Hotair ballon, Wallet/Purse, Speed Limit Sign, Induction Cooker, Router/modem, Poker Card, Hamimelon, Mushroon, Board Eraser, Tape Measur/ Ruler, Crosswalk Sign, Campel, Formula 1, Buttefly, Egg tart, Baozi, Table Teniis paddle, Cosmetics Brush/Eyeliner Pencil, Cosmetics Mirror|

## 7. MWE Candidate Status

|status|count|
|---|---:|
|not MWE|285|
|unresolved|36|
|selected|31|
|duplicate_existing_label_key|11|
|rejected|2|

Rejected MWE candidates:

- American Football
- Table Tennis

Unresolved MWE candidates:

- Other Shoes
- Storage box
- Leather Shoes
- Potted Plant
- Trash bin Can
- Wild Bird
- Traffic cone
- Stuffed Toy
- Power outlet
- Traffic Sign
- Dinning Table
- Other Fish
- Machinery Vehicle
- Green Vegetables
- Surveillance Camera
- Skating and Skiing shoes
- Other Balls
- Computer Box
- Cleaning Products
- Cutting/chopping Board
- Side Table
- Heavy Truck
- Extention Cord
- Coffee Machine
- Washing Machine/Drying Machine
- Hotair ballon
- Speed Limit Sign
- Induction Cooker
- Poker Card
- Board Eraser
- Tape Measur/ Ruler
- Crosswalk Sign
- Formula 1
- Egg tart
- Table Teniis paddle
- Cosmetics Brush/Eyeliner Pencil
- Cosmetics Mirror

## 8. Execution Notes

- Compile check passed: `.\scripts\run_python.ps1 -m compileall scripts`
- First normal run failed on network download with `ConnectionRefusedError`.
- The same narrow generation command succeeded with `require_escalated`.
- After script output filtering was adjusted, a normal rerun failed with `PermissionError` while rewriting the generated TSV.
- The same narrow generation command succeeded with `require_escalated`.
- These escalation runs produced the output files, but they do not mean the underlying sandbox permission behavior was fixed.
- Object-compatible-first WN3.0 selection update compile check passed: `.\scripts\run_python.ps1 -m compileall scripts`
- The normal regeneration run failed with `PermissionError` while rewriting `objects365_oewn2025plus_synset_candidates.tsv`.
- The same narrow generation command succeeded with `require_escalated`.
- Manual ambiguous synset decision update compile check passed: `.\scripts\run_python.ps1 -m compileall scripts`
- The normal regeneration run failed with `PermissionError` while rewriting `objects365_oewn2025plus_synset_candidates.tsv`.
- The same narrow generation command succeeded with `require_escalated`.
- Remaining ambiguous label decision v2 compile check passed: `.\scripts\run_python.ps1 -m compileall scripts`
- The normal regeneration run failed with `PermissionError` while rewriting `objects365_oewn2025plus_synset_candidates.tsv`.
- The same narrow generation command succeeded with `require_escalated`.
