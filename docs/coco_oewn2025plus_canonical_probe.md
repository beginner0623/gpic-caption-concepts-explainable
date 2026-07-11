# COCO OEWN 2025+ Canonical Surface Probe

> Current status: historical COCO-only probe. 현재 canonical decision의 기준 파일은
> `resources/source_labels/object_synset_canonical_decisions.tsv`다. Dataset별 후보
> TSV의 `canonical_surface`는 active lexicon이나 최종 canonical decision으로 보지 않는다.

이 문서는 `resources/source_labels/coco_oewn2025plus_synset_candidates.tsv`에 적용한 canonical surface 선정 결과를 기록한다.

## Rule

1. `selected_oewn_synset`이 있는 row만 대상으로 한다.
2. selected synset의 OEWN lemma 중 source label 또는 Morphy selected query와 형태적으로 연결되는 lemma만 canonical 후보로 둔다.
   - lowercase 차이는 무시한다.
   - space, hyphen, underscore separator 차이는 무시한다.
   - 같은 synset 안에 있더라도 source label과 형태 매칭되지 않는 lemma는 후보에서 제외한다.
   - `morphy`로 lookup이 성공한 경우 selected query도 canonical 후보 근거로 쓴다.
   - dataset별 semantic alias는 자동 canonical 후보 근거로 쓰지 않는다.
3. canonical 후보가 하나뿐이면 WN3.0 `lemma.count()`가 0이어도 canonical surface로 선택한다.
   - 이 경우 count는 선택 기준이 아니라 기록값이다.
   - WN3.0 count mapping이 없어서 `-1`로 기록되는 경우도 후보가 하나뿐이면 선택한다.
4. canonical 후보가 둘 이상이면 WN3.0 `lemma.count()`를 비교한다.
5. count가 0보다 큰 단독 최대값이면 canonical surface로 선택한다.
6. count가 모두 0이거나 동률이면 source dataset의 official label surface와 정확히 같은 lemma를 canonical surface로 선택한다.
   - 정확히 같다는 뜻은 lowercase와 whitespace normalization만 적용한다는 뜻이다.
   - 이 tie-break에서는 space, hyphen, underscore를 제거해서 같다고 보지 않는다.
   - 예: `hot dog`와 `hotdog`는 다르다.
7. official label surface와 같은 lemma가 하나도 없거나 둘 이상이면 `ambiguous`로 둔다.
8. source label과 형태 매칭되는 WordNet lemma가 없으면 `ambiguous`로 둔다.
9. Google Ngram, `wordfreq`, `SUBTLEX`는 현재 구현하지 않는다.

## Summary

| metric | value |
|---|---:|
| COCO rows | 80 |
| selected OEWN synset rows | 78 |
| canonical selected rows | 78 |
| canonical ambiguous rows | 0 |
| not applicable rows | 2 |

## Canonical Selection Tag Counts

| tag | count |
|---|---:|
| `selected_single_label_or_lookup_matched_wordnet_lemma` | 76 |
| `selected_by_source_label_surface_after_wn30_all_zero` | 2 |
| `not_applicable_no_selected_synset` | 2 |

## Official Label Tie-Break Rows

| label | selected synset | synset lemmas | reason | candidate lemmas | candidate counts |
|---|---|---|---|---|---|
| `backpack` | `oewn-02772753-n` | `backpack\|back pack\|knapsack\|packsack\|rucksack\|haversack` | `selected_by_source_label_surface_after_wn30_all_zero` | `backpack\|back pack` | `backpack:0\|back pack:0` |
| `hot dog` | `oewn-07713282-n` | `hotdog\|hot dog\|red hot` | `selected_by_source_label_surface_after_wn30_all_zero` | `hotdog\|hot dog` | `hotdog:0\|hot dog:0` |

## Lookup Query Resolved Canonical Rows

| label | lookup case | selected query | selected synset | canonical surface | candidate counts |
|---|---|---|---|---|---|
| `skis` | `morphy` | `ski` | `oewn-04235116-n` | `ski` | `ski:0` |

## Unresolved Rows

| label | reason |
|---|---|
| `potted plant` | 자동 lookup rule로는 OEWN noun synset을 찾지 못한다. `pot plant` semantic alias는 사용하지 않는다. |
