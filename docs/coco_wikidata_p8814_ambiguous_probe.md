# COCO Wikidata P8814 Ambiguous Probe

Date: 2026-07-04

Purpose: estimate how many currently ambiguous COCO WordNet candidates would be resolved by the revised policy:

1. If WordNet exact lemma count evidence exists, use WordNet frequency order.
2. If all exact lemma counts are zero, use source metadata and Wikidata P8814 as fallback evidence.
3. If multiple candidates remain, keep the row ambiguous.

Input file:

- `resources/source_labels/coco_wordnet_candidates.tsv`

Current COCO candidate state:

- total COCO rows: 80
- current ambiguous rows: 24

Probe result:

- ambiguous rows with WordNet exact lemma count evidence: 23
- ambiguous rows with all exact lemma counts equal to zero: 1
- the only all-zero row is `hot dog`

`hot dog` evidence:

- local NLTK WordNet version: 3.0
- local candidates:
  - `hotdog.n.01`, offset `10187710-n`, lexname `noun.person`, exact count `0`
  - `hotdog.n.02`, offset `07697537-n`, lexname `noun.food`, exact count `0`
  - `frank.n.02`, offset `07676602-n`, lexname `noun.food`, exact count `0`
- Wikidata hot dog item has P8814 values:
  - `07692347-n`
  - `07713282-n`
- direct lookup of those P8814 offsets in local NLTK WordNet 3.0 failed.

Interpretation:

- The count-first policy alone resolves 23 of the 24 current ambiguous COCO rows.
- Wikidata P8814 does not resolve additional rows under direct local NLTK WordNet 3.0 offset matching.
- Before P8814 can be used as selection evidence, a WordNet 3.1 to local WordNet 3.0 mapping must be verified.
- Even after such mapping, `hot dog` may remain ambiguous if both Wikidata P8814 values map to food candidates and the COCO food filter leaves more than one candidate.

Decision:

- No runtime lexicon change.
- No active rule implementation.
- P8814 remains a proposed fallback evidence source pending version-mapping verification.
