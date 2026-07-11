"""Build LVIS-to-OEWN-2025+ synset candidate rows.

This script creates source-label candidate resources only. It does not update
active Stage 2 or Stage 5 lexicons.
"""

from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from collections import Counter
from pathlib import Path
from urllib.request import urlopen

import nltk
import wn
from nltk.corpus import wordnet as wn30
from wn.morphy import Morphy

from build_coco_oewn_candidates import (
    OEWN_SPEC,
    WN_DATA_DIR,
    _apply_objectness_gate,
    _bool,
    _check_wn30_available,
    _immediate_hypernym_parents,
    _is_mwe_candidate,
    _lookup_oewn_synsets,
    _mwe_candidate_status,
    _objectness_class,
    _select_by_wn30_lemma_count,
    _sense_key_from_oewn_sense_id,
)
from gpic_concepts_v1.atomic_io import atomic_text_writer


ROOT = Path(os.environ.get("GPIC_RUNTIME_ROOT", Path.cwd()))
NLTK_DATA_DIR = ROOT / "resources" / "nltk_data"
SOURCE_LABELS_DIR = ROOT / "resources" / "source_labels"
OBJECT_SOURCE_LABEL_INVENTORY = (
    SOURCE_LABELS_DIR / "object_source_label_synset_inventory.tsv"
)

LVIS_URL = "https://s3-us-west-2.amazonaws.com/dl.fbaipublicfiles.com/LVIS/lvis_v1_val.json.zip"
LVIS_SOURCE_VERSION = "lvis_v1_val"
LVIS_SOURCE_CLASS = "LVISCategory"

LVIS_SOURCE = SOURCE_LABELS_DIR / "lvis_v1_categories.tsv"
LVIS_CANDIDATES = SOURCE_LABELS_DIR / "lvis_oewn2025plus_synset_candidates.tsv"
LVIS_AMBIGUOUS = SOURCE_LABELS_DIR / "lvis_oewn2025plus_ambiguous.tsv"
LVIS_UNRESOLVED = SOURCE_LABELS_DIR / "lvis_oewn2025plus_unresolved.tsv"

MANUAL_LVIS_LABEL_REVIEW_TAG = "manual_select"

MANUAL_LVIS_LABEL_DECISIONS = {
    "award": {
        "synset": "oewn-06709228-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "Bible": {
        "synset": "oewn-06443410-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "birthday card": {
        "synset": "oewn-06639767-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "booklet": {
        "synset": "oewn-06425532-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "buoy": {
        "synset": "oewn-07280883-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "business card": {
        "synset": "oewn-06437074-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "calendar": {
        "synset": "oewn-06499232-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "identity card": {
        "synset": "oewn-06489042-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "card": {
        "synset": "oewn-06639513-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "checkbook": {
        "synset": "oewn-13435483-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "comic book": {
        "synset": "oewn-06608568-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "diary": {
        "synset": "oewn-06413674-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "dollar": {
        "synset": "oewn-13417070-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "keycard": {
        "synset": "oewn-06489489-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "milestone": {
        "synset": "oewn-07285872-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "money": {
        "synset": "oewn-13406050-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "newspaper": {
        "synset": "oewn-06277798-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "notebook": {
        "synset": "oewn-06427062-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "passport": {
        "synset": "oewn-06512928-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "pennant": {
        "synset": "oewn-06888338-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "phonebook": {
        "synset": "oewn-06435397-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "postcard": {
        "synset": "oewn-06640445-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "receipt": {
        "synset": "oewn-06532213-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "softball": {
        "synset": "oewn-86432478-n",
        "note": "user-approved LVIS ambiguous decision: LVIS definition says ball used in playing softball, choose artifact ball sense",
    },
    "brake light": {
        "synset": "oewn-07280695-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "street sign": {
        "synset": "oewn-06806967-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "tag": {
        "synset": "oewn-07288121-n",
        "note": "user-approved LVIS ambiguous decision",
    },
    "windsock": {
        "synset": "oewn-07272250-n",
        "note": "user-approved LVIS ambiguous decision",
    },
}


SOURCE_FIELDNAMES = [
    "dataset",
    "category_id",
    "label",
    "label_key",
    "source_version",
    "source_url",
    "source_class",
    "lvis_name",
    "lvis_synset",
    "lvis_synonyms",
    "lvis_def",
    "lvis_frequency",
    "lvis_image_count",
    "lvis_instance_count",
]


CANDIDATE_FIELDNAMES = [
    *SOURCE_FIELDNAMES,
    "is_mwe_candidate",
    "mwe_candidate_status",
    "selection_status",
    "duplicate_existing_label_key",
    "duplicate_existing_datasets",
    "duplicate_existing_labels",
    "duplicate_existing_selected_oewn_synsets",
    "wordnet_source",
    "wordnet_version",
    "wordnet_lexicon_id",
    "selected_lookup_case",
    "selected_query",
    "has_oewn_noun_synset",
    "oewn_synset_count",
    "selected_oewn_synset",
    "selected_oewn_lexfile",
    "all_oewn_synsets",
    "all_oewn_lexfiles",
    "synset_lemmas",
    "parent_oewn_synsets",
    "parent_oewn_lexfiles",
    "parent_lemmas",
    "parent_selection_tag",
    "selected_oewn_objectness_class",
    "objectness_gate",
    "manual_decision",
    "manual_decision_note",
    "sense_counts_available",
    "wn30_available",
    "wn30_selection_tag",
    "wn30_lemma_counts",
    "lvis_synset_matched_oewn_synsets",
    "synset_selection_tag",
    "decision_basis",
]


def main() -> None:
    wn.config.data_directory = str(WN_DATA_DIR)
    nltk.data.path.insert(0, str(NLTK_DATA_DIR))

    SOURCE_LABELS_DIR.mkdir(parents=True, exist_ok=True)
    source_rows = _load_or_create_source_rows()
    prior_by_label_key = _load_prior_label_inventory(
        OBJECT_SOURCE_LABEL_INVENTORY,
        current_dataset="lvis",
    )

    oewn = wn.Wordnet(OEWN_SPEC, expand="")
    morphy = Morphy(oewn)
    wn30_available = _check_wn30_available()

    candidate_rows = [
        _build_candidate_row(
            source_row=row,
            prior_by_label_key=prior_by_label_key,
            oewn=oewn,
            morphy=morphy,
            wn30_available=wn30_available,
        )
        for row in source_rows
    ]

    _write_tsv(LVIS_CANDIDATES, CANDIDATE_FIELDNAMES, candidate_rows)
    _write_tsv(
        LVIS_AMBIGUOUS,
        CANDIDATE_FIELDNAMES,
        [row for row in candidate_rows if _is_ambiguous_like(row)],
    )
    _write_tsv(
        LVIS_UNRESOLVED,
        CANDIDATE_FIELDNAMES,
        [row for row in candidate_rows if _is_unresolved_like(row)],
    )

    print(f"wrote={LVIS_SOURCE}")
    print(f"wrote={LVIS_CANDIDATES}")
    print(f"wrote={LVIS_AMBIGUOUS}")
    print(f"wrote={LVIS_UNRESOLVED}")
    for key, value in sorted(_summarize(candidate_rows).items()):
        print(f"{key}={value}")


def _load_or_create_source_rows() -> list[dict[str, str]]:
    if LVIS_SOURCE.exists():
        return _read_tsv(LVIS_SOURCE)

    categories = _download_lvis_categories()
    rows = []
    for category in sorted(categories, key=lambda row: int(row["id"])):
        name = str(category["name"]).strip()
        label = _label_from_lvis_name(name)
        rows.append(
            {
                "dataset": "lvis",
                "category_id": str(category["id"]),
                "label": label,
                "label_key": _surface_key(label),
                "source_version": LVIS_SOURCE_VERSION,
                "source_url": LVIS_URL,
                "source_class": LVIS_SOURCE_CLASS,
                "lvis_name": name,
                "lvis_synset": str(category.get("synset", "")).strip(),
                "lvis_synonyms": "|".join(
                    str(item).strip() for item in category.get("synonyms", [])
                ),
                "lvis_def": str(category.get("def", "")).strip(),
                "lvis_frequency": str(category.get("frequency", "")).strip(),
                "lvis_image_count": str(category.get("image_count", "")).strip(),
                "lvis_instance_count": str(category.get("instance_count", "")).strip(),
            }
        )
    _write_tsv(LVIS_SOURCE, SOURCE_FIELDNAMES, rows)
    return rows


def _download_lvis_categories() -> list[dict]:
    payload = urlopen(LVIS_URL, timeout=60).read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        json_names = [name for name in archive.namelist() if name.endswith(".json")]
        if len(json_names) != 1:
            raise ValueError(f"unexpected LVIS zip contents: {archive.namelist()}")
        dataset = json.loads(archive.read(json_names[0]))
    categories = dataset.get("categories", [])
    if not categories:
        raise ValueError("LVIS annotation did not contain categories.")
    return categories


def _load_prior_label_inventory(
    path: Path,
    *,
    current_dataset: str,
) -> dict[str, list[dict[str, str]]]:
    if not path.exists():
        return {}

    inventory: dict[str, list[dict[str, str]]] = {}
    for row in _read_tsv(path):
        if row.get("dataset", "") == current_dataset:
            continue
        label_key = row.get("source_label_key", "")
        if not label_key:
            label_key = _surface_key(row.get("source_label", ""))
        if not label_key:
            continue
        inventory.setdefault(label_key, []).append(row)
    return inventory


def _build_candidate_row(
    *,
    source_row: dict[str, str],
    prior_by_label_key: dict[str, list[dict[str, str]]],
    oewn: wn.Wordnet,
    morphy: Morphy,
    wn30_available: bool,
) -> dict[str, str]:
    duplicate_rows = prior_by_label_key.get(source_row["label_key"])
    if duplicate_rows:
        return _build_duplicate_row(source_row, duplicate_rows)
    return _build_new_lookup_row(source_row, oewn, morphy, wn30_available)


def _blank_candidate_row(source_row: dict[str, str]) -> dict[str, str]:
    row = {field: "" for field in CANDIDATE_FIELDNAMES}
    row.update(source_row)
    return row


def _build_duplicate_row(
    source_row: dict[str, str],
    duplicate_rows: list[dict[str, str]],
) -> dict[str, str]:
    label = source_row["label"]
    row = _blank_candidate_row(source_row)
    row.update(
        {
            "is_mwe_candidate": _bool(_is_mwe_candidate(label)),
            "mwe_candidate_status": "duplicate_existing_label_key"
            if _is_mwe_candidate(label)
            else "not_mwe",
            "selection_status": "duplicate_existing_label_key",
            "duplicate_existing_label_key": "true",
            "duplicate_existing_datasets": "|".join(
                sorted({entry.get("dataset", "") for entry in duplicate_rows})
            ),
            "duplicate_existing_labels": "|".join(
                sorted({entry.get("source_label", "") for entry in duplicate_rows})
            ),
            "duplicate_existing_selected_oewn_synsets": "|".join(
                sorted(
                    {
                        entry.get("selected_oewn_synset", "")
                        for entry in duplicate_rows
                        if entry.get("selected_oewn_synset", "")
                    }
                )
            ),
            "selected_lookup_case": "duplicate_existing_label_key",
            "decision_basis": "duplicate_existing_label_key",
        }
    )
    return row


def _build_new_lookup_row(
    source_row: dict[str, str],
    oewn: wn.Wordnet,
    morphy: Morphy,
    wn30_available: bool,
) -> dict[str, str]:
    label = source_row["label"]
    lookup_case, query, synsets = _lookup_oewn_synsets(label=label, oewn=oewn, morphy=morphy)
    (
        selected_synset,
        selection_tag,
        wn30_tag,
        wn30_counts,
        lvis_matches,
    ) = _select_synset_with_lvis_metadata(
        synsets=synsets,
        query=query,
        lvis_synset_name=source_row["lvis_synset"],
        wn30_available=wn30_available,
    )
    selected_synset, selection_tag, objectness_class, objectness_gate = _apply_objectness_gate(
        selected_synset=selected_synset,
        selection_tag=selection_tag,
    )
    selected_synset, selection_tag, manual_decision, manual_note = (
        _apply_manual_lvis_label_decision(
            label=label,
            selected_synset=selected_synset,
            selection_tag=selection_tag,
            synsets=synsets,
            oewn=oewn,
        )
    )
    if manual_decision:
        objectness_class = _objectness_class(selected_synset.lexfile() or "")
        objectness_gate = "manual_override"
    selected_lemmas = selected_synset.lemmas() if selected_synset is not None else []
    parent_synsets, parent_selection_tag = _immediate_hypernym_parents(selected_synset)
    is_mwe_candidate = _is_mwe_candidate(label)

    if selected_synset is not None:
        selection_status = "selected"
    elif not synsets:
        selection_status = "unresolved"
    else:
        selection_status = "ambiguous"

    return {
        **source_row,
        "is_mwe_candidate": _bool(is_mwe_candidate),
        "mwe_candidate_status": _mwe_candidate_status(
            is_mwe_candidate=is_mwe_candidate,
            selected_synset=selected_synset,
            selection_tag=selection_tag,
        ),
        "selection_status": selection_status,
        "duplicate_existing_label_key": "false",
        "duplicate_existing_datasets": "",
        "duplicate_existing_labels": "",
        "duplicate_existing_selected_oewn_synsets": "",
        "wordnet_source": "oewn",
        "wordnet_version": "2025-plus",
        "wordnet_lexicon_id": OEWN_SPEC,
        "selected_lookup_case": lookup_case,
        "selected_query": query,
        "has_oewn_noun_synset": _bool(bool(synsets)),
        "oewn_synset_count": str(len(synsets)),
        "selected_oewn_synset": selected_synset.id if selected_synset is not None else "",
        "selected_oewn_lexfile": selected_synset.lexfile()
        if selected_synset is not None
        else "",
        "all_oewn_synsets": "|".join(synset.id for synset in synsets),
        "all_oewn_lexfiles": "|".join(
            f"{synset.id}:{synset.lexfile()}:{';'.join(synset.lemmas())}"
            for synset in synsets
        ),
        "synset_lemmas": "|".join(selected_lemmas),
        "parent_oewn_synsets": "|".join(synset.id for synset in parent_synsets),
        "parent_oewn_lexfiles": "|".join(
            f"{synset.id}:{synset.lexfile()}" for synset in parent_synsets
        ),
        "parent_lemmas": "|".join(
            f"{synset.id}:{';'.join(synset.lemmas())}" for synset in parent_synsets
        ),
        "parent_selection_tag": parent_selection_tag,
        "selected_oewn_objectness_class": objectness_class,
        "objectness_gate": objectness_gate,
        "manual_decision": manual_decision,
        "manual_decision_note": manual_note,
        "sense_counts_available": _bool(_has_any_counts(synsets)),
        "wn30_available": _bool(wn30_available),
        "wn30_selection_tag": wn30_tag,
        "wn30_lemma_counts": wn30_counts,
        "lvis_synset_matched_oewn_synsets": "|".join(synset.id for synset in lvis_matches),
        "synset_selection_tag": selection_tag,
        "decision_basis": selection_tag,
    }


def _apply_manual_lvis_label_decision(
    *,
    label: str,
    selected_synset: wn.Synset | None,
    selection_tag: str,
    synsets: list[wn.Synset],
    oewn: wn.Wordnet,
) -> tuple[wn.Synset | None, str, str, str]:
    decision = MANUAL_LVIS_LABEL_DECISIONS.get(label)
    if decision is None:
        return selected_synset, selection_tag, "", ""
    manual_synset = _synset_by_id(oewn, decision["synset"])
    if manual_synset.id not in {synset.id for synset in synsets}:
        raise ValueError(
            f"manual LVIS decision for {label!r} references synset outside lookup candidates: "
            f"{manual_synset.id}"
        )
    return (
        manual_synset,
        MANUAL_LVIS_LABEL_REVIEW_TAG,
        f"select:{manual_synset.id}",
        decision["note"],
    )


def _synset_by_id(oewn: wn.Wordnet, synset_id: str) -> wn.Synset:
    try:
        return oewn.synset(synset_id)
    except wn.Error as exc:
        raise ValueError(f"manual LVIS decision references missing synset: {synset_id}") from exc


def _select_synset_with_lvis_metadata(
    *,
    synsets: list[wn.Synset],
    query: str,
    lvis_synset_name: str,
    wn30_available: bool,
) -> tuple[wn.Synset | None, str, str, str, list[wn.Synset]]:
    if not synsets:
        return None, "unresolved_no_oewn_noun_synset", "", "", []
    if len(synsets) == 1:
        return synsets[0], "single_oewn_noun_synset", "", "", []

    lvis_matches = [
        synset
        for synset in synsets
        if lvis_synset_name and lvis_synset_name in _wn30_synset_names(synset)
    ]
    if len(lvis_matches) == 1:
        return lvis_matches[0], "selected_by_lvis_synset_metadata", "", "", lvis_matches
    if len(lvis_matches) > 1:
        selected, wn30_tag, counts = _select_by_wn30_lemma_count(
            lvis_matches, query, wn30_available
        )
        if selected is not None:
            return (
                selected,
                "selected_by_wn30_lemma_count_after_lvis_synset_metadata",
                wn30_tag,
                counts,
                lvis_matches,
            )
        return (
            None,
            f"ambiguous_after_lvis_synset_metadata_{wn30_tag}",
            wn30_tag,
            counts,
            lvis_matches,
        )

    if lvis_synset_name:
        return (
            None,
            "ambiguous_lvis_synset_not_in_oewn_lookup_candidates",
            "",
            "",
            [],
        )
    selected, wn30_tag, counts = _select_without_lvis_match(
        synsets=synsets,
        query=query,
        wn30_available=wn30_available,
    )
    if selected is not None:
        return selected, "selected_by_fallback_without_lvis_synset_metadata", wn30_tag, counts, []
    return None, f"ambiguous_no_lvis_synset_metadata_{wn30_tag}", wn30_tag, counts, []


def _select_without_lvis_match(
    *,
    synsets: list[wn.Synset],
    query: str,
    wn30_available: bool,
) -> tuple[wn.Synset | None, str, str]:
    object_or_conditional_synsets = [
        synset
        for synset in synsets
        if _objectness_class(synset.lexfile() or "")
        in {"object_compatible", "conditional"}
    ]
    if object_or_conditional_synsets:
        selected, wn30_tag, counts = _select_by_wn30_lemma_count(
            object_or_conditional_synsets, query, wn30_available
        )
        if selected is not None:
            return selected, wn30_tag, counts
        return None, f"object_or_conditional_{wn30_tag}", counts

    selected, wn30_tag, counts = _select_by_wn30_lemma_count(
        synsets, query, wn30_available
    )
    if selected is not None:
        return selected, wn30_tag, counts
    return None, f"no_object_or_conditional_{wn30_tag}", counts


def _wn30_synset_names(synset: wn.Synset) -> set[str]:
    names: set[str] = set()
    for sense in synset.senses():
        sense_key = _sense_key_from_oewn_sense_id(sense.id)
        if not sense_key:
            continue
        try:
            names.add(wn30.lemma_from_key(sense_key).synset().name())
        except Exception:
            continue
    return names


def _label_from_lvis_name(name: str) -> str:
    return " ".join(name.replace("_", " ").strip().split())


def _surface_key(text: str) -> str:
    return " ".join(text.strip().lower().replace("_", " ").split())


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]


def _write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _summarize(rows: list[dict[str, str]]) -> dict[str, int]:
    status_counts = Counter(row["selection_status"] for row in rows)
    duplicate_count = status_counts["duplicate_existing_label_key"]
    return {
        "rows": len(rows),
        "source_label_rows": len(rows),
        "duplicate_existing_label_key_rows": duplicate_count,
        "oewn_lookup_rows": len(rows) - duplicate_count,
        "selected_rows": status_counts["selected"],
        "ambiguous_rows": status_counts["ambiguous"],
        "ambiguous_like_rows": sum(_is_ambiguous_like(row) for row in rows),
        "unresolved_rows": status_counts["unresolved"],
        "unresolved_like_rows": sum(_is_unresolved_like(row) for row in rows),
        "mwe_candidate_rows": sum(row["is_mwe_candidate"] == "true" for row in rows),
        "selected_by_lvis_synset_metadata_rows": sum(
            row["synset_selection_tag"] == "selected_by_lvis_synset_metadata"
            for row in rows
        ),
        "lvis_synset_not_in_lookup_candidate_rows": sum(
            "lvis_synset_not_in_oewn_lookup_candidates" in row["synset_selection_tag"]
            for row in rows
        ),
    }


def _is_ambiguous_like(row: dict[str, str]) -> bool:
    return row["selection_status"] == "ambiguous"


def _is_unresolved_like(row: dict[str, str]) -> bool:
    return row["selection_status"] == "unresolved"


def _has_any_counts(synsets: list[wn.Synset]) -> bool:
    for synset in synsets:
        for sense in synset.senses():
            if sense.counts():
                return True
    return False


if __name__ == "__main__":
    main()
