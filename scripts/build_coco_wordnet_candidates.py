"""Build COCO-to-WordNet candidate rows.

This script creates candidate resources only. It does not update the active
Stage 2/5 lexicons.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterable

import nltk
from nltk.corpus import wordnet as wn

from gpic_concepts_v1.atomic_io import atomic_text_writer


ROOT = Path(os.environ.get("GPIC_RUNTIME_ROOT", Path.cwd()))
DEFAULT_INPUT = ROOT / "resources" / "source_labels" / "coco_instances_2017_categories.tsv"
DEFAULT_OUTPUT = ROOT / "resources" / "source_labels" / "coco_wordnet_candidates.tsv"
DEFAULT_NLTK_DATA = ROOT / "resources" / "nltk_data"


COCO_SUPERCATEGORY_TO_WORDNET_LEXNAMES = {
    "person": {"noun.Tops", "noun.person"},
    "vehicle": {"noun.artifact"},
    "outdoor": {"noun.artifact"},
    "animal": {"noun.animal"},
    "accessory": {"noun.artifact"},
    "sports": {"noun.artifact"},
    "kitchen": {"noun.artifact"},
    "food": {"noun.food"},
    "furniture": {"noun.artifact"},
    "electronic": {"noun.artifact"},
    "appliance": {"noun.artifact"},
    "indoor": {"noun.artifact"},
}


FIELDNAMES = [
    "dataset",
    "category_id",
    "label",
    "supercategory",
    "source_version",
    "wordnet_query",
    "is_multiword",
    "has_wordnet_noun_synset",
    "wordnet_synset_count",
    "wordnet_synset",
    "wordnet_lexname",
    "all_wordnet_synsets",
    "all_wordnet_lexnames",
    "target_wordnet_lexnames",
    "matched_wordnet_lexnames",
    "canonical",
    "parent",
    "parent_synset",
    "synset_lemmas",
    "candidate_for_object_mwe",
    "synset_selection_tag",
    "decision_basis",
]


def main() -> None:
    nltk.data.path.insert(0, str(DEFAULT_NLTK_DATA))
    rows = list(_read_rows(DEFAULT_INPUT))
    candidate_rows = [_build_candidate_row(row) for row in rows]
    with atomic_text_writer(DEFAULT_OUTPUT, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, delimiter="\t")
        writer.writeheader()
        writer.writerows(candidate_rows)
    summary = _summarize(candidate_rows)
    print(f"wrote={DEFAULT_OUTPUT}")
    for key in sorted(summary):
        print(f"{key}={summary[key]}")


def _read_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            yield {key: (value or "").strip() for key, value in row.items()}


def _build_candidate_row(row: dict[str, str]) -> dict[str, str]:
    label = row["label"]
    query = _wordnet_query(label)
    synsets = wn.synsets(query, pos=wn.NOUN)
    is_multiword = _is_multiword(label)
    target_lexnames = COCO_SUPERCATEGORY_TO_WORDNET_LEXNAMES.get(
        row.get("supercategory", ""),
        set(),
    )
    matched_synsets = [synset for synset in synsets if synset.lexname() in target_lexnames]
    selected_synset, selection_tag = _select_synset(synsets, matched_synsets, target_lexnames)
    common = {
        **row,
        "wordnet_query": query,
        "is_multiword": _bool(is_multiword),
        "has_wordnet_noun_synset": _bool(bool(synsets)),
        "wordnet_synset_count": str(len(synsets)),
        "all_wordnet_synsets": "|".join(synset.name() for synset in synsets),
        "all_wordnet_lexnames": "|".join(
            f"{synset.name()}:{synset.lexname()}" for synset in synsets
        ),
        "target_wordnet_lexnames": "|".join(sorted(target_lexnames)),
        "matched_wordnet_lexnames": "|".join(
            f"{synset.name()}:{synset.lexname()}" for synset in matched_synsets
        ),
        "synset_selection_tag": selection_tag,
    }
    if selected_synset is None:
        return {
            **common,
            "wordnet_synset": "",
            "wordnet_lexname": "",
            "canonical": "",
            "parent": "",
            "parent_synset": "",
            "synset_lemmas": "",
            "candidate_for_object_mwe": "false",
            "decision_basis": selection_tag,
        }

    hypernyms = selected_synset.hypernyms()
    parent_synset = hypernyms[0] if hypernyms else None
    candidate_for_object_mwe = is_multiword
    return {
        **common,
        "wordnet_synset": selected_synset.name(),
        "wordnet_lexname": selected_synset.lexname(),
        "canonical": selected_synset.lemma_names()[0] if selected_synset.lemma_names() else "",
        "parent": (
            parent_synset.lemma_names()[0]
            if parent_synset is not None and parent_synset.lemma_names()
            else ""
        ),
        "parent_synset": parent_synset.name() if parent_synset is not None else "",
        "synset_lemmas": "|".join(selected_synset.lemma_names()),
        "candidate_for_object_mwe": _bool(candidate_for_object_mwe),
        "decision_basis": selection_tag,
    }


def _select_synset(
    synsets: list[wn.synset],
    matched_synsets: list[wn.synset],
    target_lexnames: set[str],
) -> tuple[wn.synset | None, str]:
    if not synsets:
        return None, "no_exact_wordnet_noun_synset"
    if len(synsets) == 1:
        return synsets[0], "single_exact_wordnet_noun_synset"
    if not target_lexnames:
        return None, "ambiguous_no_supercategory_lexname_policy"
    if len(matched_synsets) == 1:
        return matched_synsets[0], "selected_by_coco_supercategory_wordnet_lexname"
    if len(matched_synsets) > 1:
        return None, "ambiguous_after_coco_supercategory_wordnet_lexname"
    return None, "ambiguous_no_coco_supercategory_wordnet_lexname_match"


def _wordnet_query(label: str) -> str:
    return "_".join(label.strip().lower().replace("-", " ").split())


def _is_multiword(label: str) -> bool:
    return len(label.strip().replace("-", " ").split()) >= 2


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _summarize(rows: list[dict[str, str]]) -> dict[str, int]:
    return {
        "rows": len(rows),
        "multiword_rows": sum(row["is_multiword"] == "true" for row in rows),
        "wordnet_matched_rows": sum(row["has_wordnet_noun_synset"] == "true" for row in rows),
        "selected_wordnet_rows": sum(bool(row["wordnet_synset"]) for row in rows),
        "single_synset_selected_rows": sum(
            row["synset_selection_tag"] == "single_exact_wordnet_noun_synset"
            for row in rows
        ),
        "lexname_selected_rows": sum(
            row["synset_selection_tag"] == "selected_by_coco_supercategory_wordnet_lexname"
            for row in rows
        ),
        "ambiguous_wordnet_rows": sum(
            row["has_wordnet_noun_synset"] == "true" and not row["wordnet_synset"]
            for row in rows
        ),
        "object_mwe_candidates": sum(row["candidate_for_object_mwe"] == "true" for row in rows),
    }


if __name__ == "__main__":
    main()
