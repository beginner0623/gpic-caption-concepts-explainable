# COCO OEWN 2025 Synset Probe

Date: 2026-07-04

이 문서는 COCO instances 2017 category label 80개를 OEWN 2025 core 기준으로 다시 조회한 결과를 기록한다.

이 probe는 source-label candidate 생성이다. Active Stage 2 object MWE lexicon이나 Stage 5 canonicalization lexicon은 수정하지 않았다.

## Source And Tool

- source label file: `resources/source_labels/coco_instances_2017_categories.tsv`
- OEWN data dir: `resources/wn_data`
- OEWN lexicon: `oewn:2025`
- Python reader: `wn==1.1.0`
- script: `scripts/build_coco_oewn_candidates.py`
- output TSV: `resources/source_labels/coco_oewn2025_synset_candidates.tsv`

## Selection Policy Used In This Probe

1. COCO label을 lowercase space-separated query로 정규화한다.
2. `wn.Wordnet("oewn:2025", expand="")`에서 noun synset 후보를 조회한다.
3. 후보가 0개면 `no_oewn_noun_synset`으로 둔다.
4. 후보가 1개면 선택한다.
5. 후보가 여러 개면 COCO `supercategory`를 OEWN `lexfile()` 후보군으로 바꿔 필터한다.
6. 필터 후 1개만 남으면 선택한다.
7. 필터 후 2개 이상 남으면 ambiguous로 둔다.

OEWN 2025의 `Sense.counts()`는 이번 COCO label 후보들에서 모두 비어 있었다. 따라서 sense count 기반 선택은 사용하지 않았다.

## Summary

| metric | value |
|---|---:|
| rows | 80 |
| OEWN noun matched rows | 75 |
| no OEWN noun synset rows | 5 |
| selected rows | 51 |
| single synset selected rows | 31 |
| selected by COCO supercategory + OEWN lexfile | 20 |
| ambiguous rows | 24 |
| multiword rows | 15 |
| rows with sense counts | 0 |

## No Synset Rows

| label | supercategory |
|---|---|
| skis | sports |
| sports ball | sports |
| wine glass | kitchen |
| potted plant | furniture |
| cell phone | electronic |

## Ambiguous Rows

COCO supercategory + OEWN lexfile까지 적용해도 아래 24개는 단일 synset으로 떨어지지 않았다.

| label | supercategory | reason |
|---|---|---|
| car | vehicle | multiple `noun.artifact` synsets |
| bus | vehicle | multiple `noun.artifact` synsets |
| train | vehicle | multiple `noun.artifact` synsets |
| truck | vehicle | multiple `noun.artifact` synsets |
| boat | vehicle | multiple `noun.artifact` synsets |
| bench | outdoor | multiple `noun.artifact` synsets |
| cat | animal | multiple `noun.animal` synsets |
| cow | animal | multiple `noun.animal` synsets |
| tie | accessory | multiple `noun.artifact` synsets |
| bottle | kitchen | multiple `noun.artifact` synsets |
| cup | kitchen | multiple `noun.artifact` synsets |
| fork | kitchen | multiple `noun.artifact` synsets |
| knife | kitchen | multiple `noun.artifact` synsets |
| spoon | kitchen | multiple `noun.artifact` synsets |
| bowl | kitchen | multiple `noun.artifact` synsets |
| hot dog | food | multiple `noun.food` synsets |
| cake | food | multiple `noun.food` synsets |
| chair | furniture | multiple `noun.artifact` synsets |
| couch | furniture | multiple `noun.artifact` synsets |
| bed | furniture | multiple `noun.artifact` synsets |
| toilet | furniture | multiple `noun.artifact` synsets |
| keyboard | electronic | multiple `noun.artifact` synsets |
| sink | appliance | multiple `noun.artifact` synsets |
| book | indoor | multiple `noun.artifact` synsets |

## Hot Dog Check

OEWN 2025 후보:

| OEWN synset | lexfile | lemmas | definition |
|---|---|---|---|
| `oewn-10207329-n` | `noun.person` | `hotdog`, `hot dog` | someone who performs dangerous stunts |
| `oewn-07713282-n` | `noun.food` | `hotdog`, `hot dog`, `red hot` | a frankfurter served hot on a bun |
| `oewn-07692347-n` | `noun.food` | `frank`, `frankfurter`, `hotdog`, `hot dog`, `dog`, `wiener`, `wienerwurst`, `weenie` | a smooth-textured sausage |

COCO supercategory `food`를 적용하면 `noun.person` sense는 제거된다. 하지만 `noun.food`가 두 개 남기 때문에 단일 synset으로 선택하지 않는다.

Wikidata hot dog item `Q181055`의 `WordNet 3.1 Synset ID (P8814)` 값은 `07692347-n`과 `07713282-n`이다.

OEWN 2025에서는 이 두 값이 각각 아래처럼 직접 매핑된다.

| Wikidata P8814 | OEWN 2025 id |
|---|---|
| `07692347-n` | `oewn-07692347-n` |
| `07713282-n` | `oewn-07713282-n` |

따라서 Wikidata P8814는 hot dog의 person sense를 제거하는 데는 도움이 되지만, COCO supercategory를 쓴 뒤에도 남는 두 food sense 중 하나를 고르지는 못한다.

## Conclusion

OEWN 2025로 바꿔도 COCO label synset disambiguation 문제가 사라지지는 않는다.

- `hot dog`는 여전히 ambiguous다.
- ambiguous는 `hot dog` 하나가 아니라 24개다.
- Wikidata P8814는 OEWN 2025 id와 매핑되지만, `hot dog`에서는 두 food synset을 모두 가리키므로 단일 선택 근거로 충분하지 않다.

현재 기준에서는 ambiguous row를 active lexicon으로 승격하지 않고, conflict/ambiguous candidate로 남기는 것이 설명 가능하다.
