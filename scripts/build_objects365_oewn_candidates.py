"""Build Objects365-to-OEWN-2025+ synset candidate rows.

This script creates source-label candidate resources only. It does not update
active Stage 2 or Stage 5 lexicons.
"""

from __future__ import annotations

import ast
import csv
import os
import time
from collections import Counter
from pathlib import Path
from urllib.request import urlopen

import nltk
import wn
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
    _select_canonical_surface,
    _surface_key,
)
from gpic_concepts_v1.atomic_io import atomic_text_writer


ROOT = Path(os.environ.get("GPIC_RUNTIME_ROOT", Path.cwd()))
NLTK_DATA_DIR = ROOT / "resources" / "nltk_data"
SOURCE_LABELS_DIR = ROOT / "resources" / "source_labels"
OBJECT_SOURCE_LABEL_INVENTORY = (
    SOURCE_LABELS_DIR / "object_source_label_synset_inventory.tsv"
)
OBJECTS365_SOURCE = SOURCE_LABELS_DIR / "objects365_v2_categories.tsv"
OBJECTS365_CANDIDATES = (
    SOURCE_LABELS_DIR / "objects365_oewn2025plus_synset_candidates.tsv"
)
OBJECTS365_AMBIGUOUS = (
    SOURCE_LABELS_DIR / "objects365_oewn2025plus_ambiguous.tsv"
)
OBJECTS365_UNRESOLVED = (
    SOURCE_LABELS_DIR / "objects365_oewn2025plus_unresolved.tsv"
)

MMDETECTION_COMMIT = "cfd5d3a985b0249de009b67d04f37263e11cdf3d"
OBJECTS365_SOURCE_URL = (
    "https://raw.githubusercontent.com/open-mmlab/mmdetection/"
    f"{MMDETECTION_COMMIT}/mmdet/datasets/objects365.py"
)
OBJECTS365_SOURCE_CLASS = "Objects365V2Dataset"
OBJECTS365_SOURCE_VERSION = f"objects365_v2_mmdetection_{MMDETECTION_COMMIT[:12]}"
MANUAL_OBJECTS365_LABEL_REVIEW_TAG = "manual_select"
MANUAL_OBJECTS365_FIRST_ALLOWED_TAG = "first_object_compatible_fallback"
MANUAL_OBJECTS365_REJECTED_TAG = "manual_reject"

MANUAL_OBJECTS365_LABEL_DECISIONS = {
    "Air Conditioner": {
        "status": "select",
        "synset": "oewn-04047719-n",
        "note": "user-approved ambiguous decision: appliance artifact sense",
    },
    "Asparagus": {
        "status": "select",
        "synset": "oewn-07734958-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Basketball": {
        "status": "select",
        "synset": "oewn-02805592-n",
        "note": "user-approved ambiguous decision: basketball ball artifact sense",
    },
    "Belt": {
        "status": "select",
        "synset": "oewn-02830790-n",
        "note": "user-approved ambiguous decision: clothing/accessory belt artifact sense",
    },
    "Bracelet": {
        "status": "select",
        "synset": "oewn-02891211-n",
        "note": "user-approved ambiguous decision: bracelet/bangle artifact sense",
    },
    "Calculator": {
        "status": "select",
        "synset": "oewn-02942270-n",
        "note": "user-approved ambiguous decision: calculator artifact sense",
    },
    "CD": {
        "status": "select",
        "synset": "oewn-03083234-n",
        "note": "user-approved ambiguous decision: compact disc artifact sense",
    },
    "Cherry": {
        "status": "select",
        "synset": "oewn-07773108-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Cue": {
        "status": "select",
        "synset": "oewn-03150188-n",
        "note": "user-approved ambiguous decision: cue stick artifact sense",
    },
    "Cucumber": {
        "status": "select",
        "synset": "oewn-07734217-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Dolphin": {
        "status": "select",
        "synset": "oewn-02071627-n",
        "note": "user-approved ambiguous decision: dolphin animal sense, not dolphinfish",
    },
    "Donkey": {
        "status": "select",
        "synset": "oewn-02392211-n",
        "note": "user-approved ambiguous decision: animal sense",
    },
    "Durian": {
        "status": "select",
        "synset": "oewn-07778889-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Folder": {
        "status": "select",
        "synset": "oewn-03381125-n",
        "note": "user-approved ambiguous decision: physical folder artifact sense",
    },
    "Garlic": {
        "status": "select",
        "synset": "oewn-07834253-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Golf Club": {
        "status": "select",
        "synset": "oewn-03451003-n",
        "note": "user-approved ambiguous decision: golf club artifact sense",
    },
    "Grapefruit": {
        "status": "select",
        "synset": "oewn-07765945-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Hamburger": {
        "status": "select",
        "synset": "oewn-07712845-n",
        "note": "user-approved ambiguous decision: burger food sense, not ground beef",
    },
    "Hammer": {
        "status": "select",
        "synset": "oewn-03486255-n",
        "note": "user-approved ambiguous decision: hand-tool hammer artifact sense",
    },
    "Hanger": {
        "status": "select",
        "synset": "oewn-03495985-n",
        "note": "user-approved ambiguous decision: clothes hanger artifact sense",
    },
    "Helmet": {
        "status": "select",
        "synset": "oewn-03518281-n",
        "note": "user-approved ambiguous decision: protective helmet artifact sense",
    },
    "Jellyfish": {
        "status": "select",
        "synset": "oewn-01913388-n",
        "note": "user-approved ambiguous decision: jellyfish animal sense",
    },
    "Lettuce": {
        "status": "select",
        "synset": "oewn-07739304-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Lifesaver": {
        "status": "select",
        "synset": "oewn-03668045-n",
        "note": "user-approved ambiguous decision: life buoy/life ring artifact sense",
    },
    "Lighter": {
        "status": "select",
        "synset": "oewn-03671917-n",
        "note": "user-approved ambiguous decision: cigarette lighter artifact sense",
    },
    "Mango": {
        "status": "select",
        "synset": "oewn-07780131-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Medal": {
        "status": "select",
        "synset": "oewn-06719615-n",
        "note": "user-approved ambiguous decision: physical medal award sense",
    },
    "Napkin": {
        "status": "select",
        "synset": "oewn-03813077-n",
        "note": "user-approved ambiguous decision: table napkin artifact sense",
    },
    "Notepaper": {
        "status": "select",
        "synset": "oewn-06269819-n",
        "note": "user-approved ambiguous decision: physical notepaper object sense",
    },
    "Okra": {
        "status": "select",
        "synset": "oewn-07749370-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Onion": {
        "status": "select",
        "synset": "oewn-07737962-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Papaya": {
        "status": "select",
        "synset": "oewn-07778220-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Peach": {
        "status": "select",
        "synset": "oewn-07766980-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Pineapple": {
        "status": "select",
        "synset": "oewn-07769251-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Plum": {
        "status": "select",
        "synset": "oewn-07767427-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Pomegranate": {
        "status": "select",
        "synset": "oewn-07784670-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Pumpkin": {
        "status": "select",
        "synset": "oewn-07751486-n",
        "note": "user-approved ambiguous decision: pumpkin food/object sense, not vine",
    },
    "Red Cabbage": {
        "status": "select",
        "synset": "oewn-07730547-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Stroller": {
        "status": "select",
        "synset": "oewn-02769539-n",
        "note": "user-approved ambiguous decision: baby buggy/stroller artifact sense",
    },
    "Trophy": {
        "status": "select",
        "synset": "oewn-04495252-n",
        "note": "user-approved ambiguous decision: trophy/prize artifact sense",
    },
    "Volleyball": {
        "status": "select",
        "synset": "oewn-04547339-n",
        "note": "user-approved ambiguous decision: volleyball ball artifact sense",
    },
    "Watermelon": {
        "status": "select",
        "synset": "oewn-07772927-n",
        "note": "user-approved ambiguous decision: food sense",
    },
    "Yak": {
        "status": "select",
        "synset": "oewn-02407954-n",
        "note": "user-approved ambiguous decision: animal sense",
    },
    # Objects365 remaining ambiguous label decisions after object+conditional ranking.
    "Brush": {
        "status": "select",
        "synset": "oewn-02911542-n",
        "note": "user-approved remaining ambiguous decision: brush artifact sense",
    },
    "French": {
        "status": "reject",
        "note": "user-approved remaining ambiguous decision: reject French source label",
    },
    "Ring": {
        "status": "select",
        "synset": "oewn-04099721-n",
        "note": "user-approved remaining ambiguous decision: ring artifact sense",
    },
    "Target": {
        "status": "select",
        "synset": "oewn-04401354-n",
        "note": "user-approved remaining ambiguous decision: target artifact sense",
    },
    # Objects365 remaining ambiguous label decisions v2.
    "American Football": {
        "status": "reject",
        "synset": "oewn-00470726-n",
        "note": "user-approved reject: only American football game noun.act candidate; ball-object correction is not applied",
    },
    "Carriage": {
        "status": "select",
        "synset": "oewn-03901563-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: first artifact candidate",
    },
    "Crane": {
        "status": "select",
        "synset": "oewn-03131358-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: exclude person/proper noun candidates and choose artifact crane",
    },
    "Curling": {
        "status": "reject",
        "synset": "oewn-00462672-n",
        "note": "user-approved reject: only curling noun.act candidate",
    },
    "Dumpling": {
        "status": "select",
        "synset": "oewn-07717938-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: first food candidate",
    },
    "Extractor": {
        "status": "select",
        "synset": "oewn-03313097-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: first artifact candidate",
    },
    "Lobster": {
        "status": "select",
        "synset": "oewn-07808701-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: first food/animal candidate",
    },
    "Noddles": {
        "status": "reject",
        "synset": "oewn-05619467-n",
        "note": "user-approved reject: typo-looking label is not corrected to Noodles; resolved noddle candidate is noun.cognition",
    },
    "Paddle": {
        "status": "select",
        "synset": "oewn-03879526-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: first artifact candidate",
    },
    "Pasta": {
        "status": "select",
        "synset": "oewn-07879350-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: first food candidate",
    },
    "Pepper": {
        "status": "select",
        "synset": "oewn-13170289-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: plant and food are object-compatible; choose first by synset order",
    },
    "Printer": {
        "status": "select",
        "synset": "oewn-04011143-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: exclude person candidate and choose first artifact candidate",
    },
    "Projector": {
        "status": "select",
        "synset": "oewn-04016177-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: first artifact candidate",
    },
    "Scallop": {
        "status": "select",
        "synset": "oewn-07813617-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: exclude shape candidate and choose first food/animal candidate",
    },
    "Scooter": {
        "status": "select",
        "synset": "oewn-04569408-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: choose first artifact candidate and exclude animal scoter",
    },
    "Shrimp": {
        "status": "select",
        "synset": "oewn-07810135-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: exclude person insult sense and choose first food/animal candidate",
    },
    "Soccer": {
        "status": "reject",
        "synset": "oewn-00479273-n",
        "note": "user-approved reject: only soccer noun.act candidate; no object synset",
    },
    "Table Tennis": {
        "status": "reject",
        "synset": "oewn-00500274-n",
        "note": "user-approved reject: only table tennis/ping pong noun.act candidate",
    },
    "Tennis": {
        "status": "reject",
        "synset": "oewn-00483309-n",
        "note": "user-approved reject: only tennis noun.act candidate",
    },
    "Van": {
        "status": "select",
        "synset": "oewn-04527775-n",
        "selection_tag": MANUAL_OBJECTS365_FIRST_ALLOWED_TAG,
        "note": "user-approved first-allowed-candidate decision: exclude group sense and choose first artifact candidate",
    },
}


SOURCE_FIELDNAMES = [
    "dataset",
    "category_index",
    "label",
    "label_key",
    "source_version",
    "source_url",
    "source_class",
]


CANDIDATE_FIELDNAMES = [
    "dataset",
    "category_index",
    "label",
    "label_key",
    "source_version",
    "source_url",
    "source_class",
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
    "canonical_surface",
    "canonical_selection_tag",
    "canonical_candidate_lemmas",
    "canonical_candidate_lemma_counts",
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
    "synset_selection_tag",
    "decision_basis",
]


def main() -> None:
    profile_start = time.perf_counter()
    phase_start = profile_start

    def log_phase(name: str) -> None:
        nonlocal phase_start
        now = time.perf_counter()
        print(
            f"profile_phase={name} elapsed={now - profile_start:.3f}s "
            f"delta={now - phase_start:.3f}s",
            flush=True,
        )
        phase_start = now

    wn.config.data_directory = str(WN_DATA_DIR)
    nltk.data.path.insert(0, str(NLTK_DATA_DIR))
    log_phase("configure_paths")

    SOURCE_LABELS_DIR.mkdir(parents=True, exist_ok=True)
    source_rows = _load_or_create_source_rows()
    log_phase("load_or_create_source_rows")
    prior_by_label_key = _load_prior_label_inventory(
        OBJECT_SOURCE_LABEL_INVENTORY,
        current_dataset="objects365",
    )
    log_phase("load_prior_label_inventory")

    oewn = wn.Wordnet(OEWN_SPEC, expand="")
    log_phase("load_oewn")
    morphy = Morphy(oewn)
    log_phase("init_morphy")
    wn30_available = _check_wn30_available()
    log_phase("check_wn30_available")

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
    log_phase("build_candidate_rows")

    _write_tsv(OBJECTS365_CANDIDATES, CANDIDATE_FIELDNAMES, candidate_rows)
    log_phase("write_candidates")
    _write_tsv(
        OBJECTS365_AMBIGUOUS,
        CANDIDATE_FIELDNAMES,
        [row for row in candidate_rows if _is_ambiguous_like(row)],
    )
    log_phase("write_ambiguous")
    _write_tsv(
        OBJECTS365_UNRESOLVED,
        CANDIDATE_FIELDNAMES,
        [row for row in candidate_rows if _is_unresolved_like(row)],
    )
    log_phase("write_unresolved")

    print(f"wrote={OBJECTS365_SOURCE}")
    print(f"wrote={OBJECTS365_CANDIDATES}")
    print(f"wrote={OBJECTS365_AMBIGUOUS}")
    print(f"wrote={OBJECTS365_UNRESOLVED}")
    for key, value in sorted(_summarize(candidate_rows).items()):
        print(f"{key}={value}")


def _load_or_create_source_rows() -> list[dict[str, str]]:
    if OBJECTS365_SOURCE.exists():
        return _read_tsv(OBJECTS365_SOURCE)

    labels = _download_objects365_labels()
    rows = [
        {
            "dataset": "objects365",
            "category_index": str(index),
            "label": " ".join(label.strip().split()),
            "label_key": _surface_key(label),
            "source_version": OBJECTS365_SOURCE_VERSION,
            "source_url": OBJECTS365_SOURCE_URL,
            "source_class": OBJECTS365_SOURCE_CLASS,
        }
        for index, label in enumerate(labels)
    ]
    _write_tsv(OBJECTS365_SOURCE, SOURCE_FIELDNAMES, rows)
    return rows


def _download_objects365_labels() -> list[str]:
    source = urlopen(OBJECTS365_SOURCE_URL, timeout=30).read().decode("utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == OBJECTS365_SOURCE_CLASS:
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                if not any(
                    isinstance(target, ast.Name) and target.id == "METAINFO"
                    for target in stmt.targets
                ):
                    continue
                meta = ast.literal_eval(stmt.value)
                labels = list(meta["classes"])
                if len(labels) != 365:
                    raise ValueError(f"expected 365 labels, got {len(labels)}")
                return labels
    raise ValueError(f"could not find {OBJECTS365_SOURCE_CLASS} in source")


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


def _blank_candidate_row(source_row: dict[str, str]) -> dict[str, str]:
    row = {field: "" for field in CANDIDATE_FIELDNAMES}
    row.update(source_row)
    return row


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
    selected_synset, selection_tag, wn30_tag, wn30_counts = _select_synset_without_dataset_evidence(
        synsets=synsets,
        query=query,
        wn30_available=wn30_available,
    )
    selected_synset, selection_tag, objectness_class, objectness_gate = _apply_objectness_gate(
        selected_synset=selected_synset,
        selection_tag=selection_tag,
    )
    selected_synset, selection_tag, manual_decision, manual_note = (
        _apply_manual_objects365_label_decision(
            label=label,
            original_selection_status=_selection_status_for_synsets(
                selected_synset=selected_synset,
                synsets=synsets,
            ),
            selected_synset=selected_synset,
            selection_tag=selection_tag,
            oewn=oewn,
        )
    )
    if manual_decision.startswith("select"):
        objectness_class = _objectness_class(selected_synset.lexfile() or "")
        objectness_gate = "manual_override"
    selected_lemmas = selected_synset.lemmas() if selected_synset is not None else []
    canonical_surface, canonical_tag, canonical_candidates, canonical_counts = (
        _select_canonical_surface(
            label=label,
            selected_lookup_case=lookup_case,
            selected_query=query,
            selected_synset=selected_synset,
            wn30_available=wn30_available,
        )
    )
    parent_synsets, parent_selection_tag = _immediate_hypernym_parents(selected_synset)
    is_mwe_candidate = _is_mwe_candidate(label)

    if manual_decision.startswith("reject"):
        selection_status = "rejected"
    elif selected_synset is not None:
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
        "canonical_surface": canonical_surface,
        "canonical_selection_tag": canonical_tag,
        "canonical_candidate_lemmas": canonical_candidates,
        "canonical_candidate_lemma_counts": canonical_counts,
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
        "synset_selection_tag": selection_tag,
        "decision_basis": selection_tag,
    }


def _selection_status_for_synsets(
    selected_synset: wn.Synset | None,
    synsets: list[wn.Synset],
) -> str:
    if selected_synset is not None:
        return "selected"
    if not synsets:
        return "unresolved"
    return "ambiguous"


def _apply_manual_objects365_label_decision(
    *,
    label: str,
    original_selection_status: str,
    selected_synset: wn.Synset | None,
    selection_tag: str,
    oewn: wn.Wordnet,
) -> tuple[wn.Synset | None, str, str, str]:
    if original_selection_status != "ambiguous":
        return selected_synset, selection_tag, "", ""

    decision = MANUAL_OBJECTS365_LABEL_DECISIONS.get(label)
    if decision is None:
        return selected_synset, selection_tag, "", ""

    if decision["status"] == "reject":
        rejected_synset_id = decision.get("synset", "")
        if rejected_synset_id:
            _synset_by_id(oewn, rejected_synset_id)
            manual_decision = f"reject:{rejected_synset_id}"
        else:
            manual_decision = "reject"
        return (
            None,
            decision.get("selection_tag", MANUAL_OBJECTS365_REJECTED_TAG),
            manual_decision,
            decision["note"],
        )

    manual_synset = _synset_by_id(oewn, decision["synset"])
    if decision["status"] == "select":
        return (
            manual_synset,
            decision.get("selection_tag", MANUAL_OBJECTS365_LABEL_REVIEW_TAG),
            f"select:{manual_synset.id}",
            decision["note"],
        )
    return selected_synset, selection_tag, "", ""


def _synset_by_id(oewn: wn.Wordnet, synset_id: str) -> wn.Synset:
    try:
        return oewn.synset(synset_id)
    except Exception as exc:
        raise ValueError(
            f"manual Objects365 decision references missing synset: {synset_id}"
        ) from exc


def _select_synset_without_dataset_evidence(
    *,
    synsets: list[wn.Synset],
    query: str,
    wn30_available: bool,
) -> tuple[wn.Synset | None, str, str, str]:
    if not synsets:
        return None, "unresolved_no_oewn_noun_synset", "", ""
    if len(synsets) == 1:
        return synsets[0], "single_oewn_noun_synset", "", ""

    return _select_multiple_synsets_without_dataset_evidence(
        synsets=synsets,
        query=query,
        wn30_available=wn30_available,
    )


def _select_multiple_synsets_without_dataset_evidence(
    *,
    synsets: list[wn.Synset],
    query: str,
    wn30_available: bool,
) -> tuple[wn.Synset | None, str, str, str]:
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
            return (
                selected,
                "selected_by_object_or_conditional_wn30_lemma_count_before_objectness_gate",
                wn30_tag,
                counts,
            )
        return None, f"ambiguous_object_or_conditional_{wn30_tag}", wn30_tag, counts

    selected, wn30_tag, counts = _select_by_wn30_lemma_count(
        synsets, query, wn30_available
    )
    if selected is not None:
        return (
            selected,
            "selected_by_other_wn30_lemma_count_before_objectness_gate",
            wn30_tag,
            counts,
        )
    return None, f"ambiguous_no_object_or_conditional_{wn30_tag}", wn30_tag, counts


def _has_any_counts(synsets: list[wn.Synset]) -> bool:
    for synset in synsets:
        for sense in synset.senses():
            if sense.counts():
                return True
    return False


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]


def _write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    start = time.perf_counter()
    print(f"write_start={path.name} rows={len(rows)}", flush=True)
    with atomic_text_writer(path, newline="") as handle:
        print(
            f"write_opened={path.name} elapsed={time.perf_counter() - start:.3f}s",
            flush=True,
        )
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        print(
            f"write_header={path.name} elapsed={time.perf_counter() - start:.3f}s",
            flush=True,
        )
        writer.writerows(rows)
        print(
            f"write_rows={path.name} elapsed={time.perf_counter() - start:.3f}s",
            flush=True,
        )
    print(
        f"write_done={path.name} elapsed={time.perf_counter() - start:.3f}s",
        flush=True,
    )


def _summarize(rows: list[dict[str, str]]) -> dict[str, int]:
    status_counts = Counter(row["selection_status"] for row in rows)
    duplicate_count = status_counts["duplicate_existing_label_key"]
    return {
        "rows": len(rows),
        "source_label_rows": len(rows),
        "duplicate_existing_label_key_rows": duplicate_count,
        "oewn_lookup_rows": len(rows) - duplicate_count,
        "selected_rows": status_counts["selected"],
        "rejected_rows": status_counts["rejected"],
        "manual_selected_rows": sum(
            row["synset_selection_tag"] == MANUAL_OBJECTS365_LABEL_REVIEW_TAG
            for row in rows
        ),
        "manual_first_allowed_selected_rows": sum(
            row["synset_selection_tag"] == MANUAL_OBJECTS365_FIRST_ALLOWED_TAG
            for row in rows
        ),
        "manual_rejected_rows": sum(
            row["synset_selection_tag"] == MANUAL_OBJECTS365_REJECTED_TAG
            for row in rows
        ),
        "ambiguous_rows": status_counts["ambiguous"],
        "ambiguous_like_rows": sum(_is_ambiguous_like(row) for row in rows),
        "unresolved_rows": status_counts["unresolved"],
        "unresolved_like_rows": sum(_is_unresolved_like(row) for row in rows),
        "mwe_candidate_rows": sum(row["is_mwe_candidate"] == "true" for row in rows),
        "canonical_selected_rows": sum(bool(row["canonical_surface"]) for row in rows),
        "parent_evidence_rows": sum(bool(row["parent_oewn_synsets"]) for row in rows),
    }


def _is_ambiguous_like(row: dict[str, str]) -> bool:
    return row["selection_status"] == "ambiguous"


def _is_unresolved_like(row: dict[str, str]) -> bool:
    return row["selection_status"] == "unresolved"


if __name__ == "__main__":
    main()
