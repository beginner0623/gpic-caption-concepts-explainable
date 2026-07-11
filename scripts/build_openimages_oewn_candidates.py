"""Build OpenImages-to-OEWN-2025+ synset candidate rows.

This script creates source-label candidate resources only. It does not update
active Stage 2 or Stage 5 lexicons.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
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
    _has_any_counts,
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

OPENIMAGES_CLASS_DESCRIPTIONS_URL = (
    "https://storage.googleapis.com/openimages/2018_04/class-descriptions-boxable.csv"
)
OPENIMAGES_HIERARCHY_URL = (
    "https://storage.googleapis.com/openimages/2018_04/bbox_labels_600_hierarchy.json"
)
OPENIMAGES_SOURCE_VERSION = "openimages_2018_04_boxable"
OPENIMAGES_SOURCE_CLASS = "OpenImagesBoxable"

OPENIMAGES_SOURCE = SOURCE_LABELS_DIR / "openimages_boxable_classes.tsv"
OPENIMAGES_HIERARCHY_RAW = SOURCE_LABELS_DIR / "openimages_bbox_labels_600_hierarchy.json"
OPENIMAGES_CANDIDATES = (
    SOURCE_LABELS_DIR / "openimages_oewn2025plus_synset_candidates.tsv"
)
OPENIMAGES_AMBIGUOUS = (
    SOURCE_LABELS_DIR / "openimages_oewn2025plus_ambiguous.tsv"
)
OPENIMAGES_UNRESOLVED = (
    SOURCE_LABELS_DIR / "openimages_oewn2025plus_unresolved.tsv"
)

MANUAL_OPENIMAGES_LABEL_REVIEW_TAG = "manual_select"
MANUAL_OPENIMAGES_FIRST_ALLOWED_TAG = "first_object_compatible_fallback"
MANUAL_OPENIMAGES_REJECTED_TAG = "manual_reject"

MANUAL_OPENIMAGES_LABEL_DECISIONS = {
    "Alpaca": {
        "status": "select",
        "synset": "oewn-02440903-n",
        "note": "user-approved OpenImages decision: parent Mammal, choose animal alpaca sense",
    },
    "Animal": {
        "status": "select",
        "synset": "oewn-00015568-n",
        "note": "user-approved OpenImages decision: children are animal categories, choose generic animal sense",
    },
    "Artichoke": {
        "status": "select",
        "synset": "oewn-07734492-n",
        "note": "user-approved OpenImages decision: parent Vegetable, choose food artichoke sense",
    },
    "Beaker": {
        "status": "select",
        "synset": "oewn-02818969-n",
        "selection_tag": MANUAL_OPENIMAGES_FIRST_ALLOWED_TAG,
        "note": "user-approved first-order fallback: first container-compatible beaker artifact sense",
    },
    "Bell pepper": {
        "status": "select",
        "synset": "oewn-07736620-n",
        "note": "user-approved OpenImages decision: parent Vegetable, choose food bell pepper sense",
    },
    "Butterfly": {
        "status": "select",
        "synset": "oewn-02276911-n",
        "note": "user-approved OpenImages decision: parent Moths and butterflies, choose animal butterfly sense",
    },
    "Band-aid": {
        "status": "select",
        "synset": "oewn-02789081-n",
        "note": "user-approved OpenImages decision: parent Medical equipment, choose Band Aid medical equipment sense",
    },
    "Bust": {
        "status": "select",
        "synset": "oewn-02929572-n",
        "note": "user-approved OpenImages decision: parent Sculpture, choose sculpture bust artifact sense",
    },
    "Cabinetry": {
        "status": "reject",
        "synset": "oewn-00608657-n",
        "note": "user-approved reject: only cabinetry/cabinetwork noun.act candidate",
    },
    "Canary": {
        "status": "select",
        "synset": "oewn-01535980-n",
        "note": "user-approved OpenImages decision: parent Bird, choose animal canary sense",
    },
    "Cantaloupe": {
        "status": "select",
        "synset": "oewn-07771905-n",
        "note": "user-approved OpenImages decision: parent Fruit, choose food cantaloupe sense",
    },
    "Carnivore": {
        "status": "select",
        "synset": "oewn-02077948-n",
        "selection_tag": MANUAL_OPENIMAGES_FIRST_ALLOWED_TAG,
        "note": "user-approved first-order fallback: parent Mammal, choose first carnivore animal sense",
    },
    "Christmas tree": {
        "status": "select",
        "synset": "oewn-03030309-n",
        "note": "user-approved OpenImages decision: choose decorated Christmas tree artifact sense",
    },
    "Cocktail": {
        "status": "select",
        "synset": "oewn-07927917-n",
        "note": "user-approved OpenImages decision: parent Drink, choose mixed drink cocktail sense",
    },
    "Coin": {
        "status": "select",
        "synset": "oewn-13409418-n",
        "note": "user-approved OpenImages decision: single conditional object candidate, accept coin sense",
    },
    "Cream": {
        "status": "select",
        "synset": "oewn-03133170-n",
        "note": "user-approved OpenImages decision: parent Personal care, choose ointment/emollient artifact sense",
    },
    "Crown": {
        "status": "select",
        "synset": "oewn-03143320-n",
        "note": "user-approved OpenImages decision: parent Fashion accessory, choose crown/diadem artifact sense",
    },
    "Doughnut": {
        "status": "select",
        "synset": "oewn-07654678-n",
        "note": "user-approved OpenImages decision: parent Pastry, choose food doughnut sense",
    },
    "Drill": {
        "status": "select",
        "synset": "oewn-03244429-n",
        "note": "user-approved OpenImages decision: parent Tool, choose drill tool artifact sense",
    },
    "Food": {
        "status": "select",
        "synset": "oewn-00021445-n",
        "note": "user-approved OpenImages decision: children/parent are food taxonomy, choose generic food sense",
    },
    "Footwear": {
        "status": "select",
        "synset": "oewn-03385972-n",
        "selection_tag": MANUAL_OPENIMAGES_FIRST_ALLOWED_TAG,
        "note": "user-approved first-order fallback: first footwear artifact sense",
    },
    "Gondola": {
        "status": "select",
        "synset": "oewn-03452391-n",
        "note": "user-approved OpenImages decision: parent Boat, choose boat gondola sense",
    },
    "Grinder": {
        "status": "select",
        "synset": "oewn-03464972-n",
        "note": "user-approved OpenImages decision: parent Tool, choose tool grinder artifact sense",
    },
    "Hedgehog": {
        "status": "select",
        "synset": "oewn-01896466-n",
        "note": "user-approved OpenImages decision: parent Mammal, choose true hedgehog animal sense",
    },
    "Honeycomb": {
        "status": "select",
        "synset": "oewn-09241222-n",
        "note": "user-approved OpenImages decision: parent Food, choose honeycomb food sense",
    },
    "Lavender": {
        "status": "select",
        "synset": "oewn-12870477-n",
        "note": "user-approved OpenImages decision: parent Flower, choose lavender plant/flower sense",
    },
    "Leopard": {
        "status": "select",
        "synset": "oewn-02131037-n",
        "note": "user-approved OpenImages decision: parent Carnivore, choose animal leopard sense",
    },
    "Lynx": {
        "status": "select",
        "synset": "oewn-02129704-n",
        "note": "user-approved OpenImages decision: parent Carnivore, choose animal lynx/catamount sense",
    },
    "Mixer": {
        "status": "select",
        "synset": "oewn-03780732-n",
        "note": "user-approved OpenImages decision: parent Home/Kitchen appliance, choose kitchen mixer artifact sense",
    },
    "Mug": {
        "status": "select",
        "synset": "oewn-03802912-n",
        "note": "user-approved OpenImages decision: parent Tableware, choose mug artifact sense",
    },
    "Mushroom": {
        "status": "select",
        "synset": "oewn-07750720-n",
        "note": "user-approved OpenImages decision: parent Food, choose food mushroom sense",
    },
    "Nail": {
        "status": "select",
        "synset": "oewn-03810284-n",
        "note": "user-approved OpenImages decision: parent Tool, choose metal nail artifact sense",
    },
    "Otter": {
        "status": "select",
        "synset": "oewn-02447450-n",
        "note": "user-approved OpenImages decision: parent Carnivore, choose animal otter sense",
    },
    "Ostrich": {
        "status": "select",
        "synset": "oewn-01521519-n",
        "note": "user-approved OpenImages decision: parent Bird, choose ostrich animal sense",
    },
    "Panda": {
        "status": "select",
        "synset": "oewn-02513086-n",
        "note": "user-approved OpenImages decision: parent Bear, choose giant panda animal sense distinct from red panda",
    },
    "Pastry": {
        "status": "select",
        "synset": "oewn-07638317-n",
        "note": "user-approved OpenImages decision: parent Baked goods, choose baked pastry food sense, not pastry dough",
    },
    "Personal care": {
        "status": "reject",
        "synset": "oewn-00666719-n",
        "note": "user-approved reject: only personal care noun.act candidate",
    },
    "Platter": {
        "status": "select",
        "synset": "oewn-03969492-n",
        "note": "user-approved OpenImages decision: parent Tableware, choose serving dish/platter artifact sense",
    },
    "Poster": {
        "status": "select",
        "synset": "oewn-06806283-n",
        "note": "user-approved OpenImages decision: parent Office supplies, choose poster/placard/notice/bill/card sense",
    },
    "Popcorn": {
        "status": "select",
        "synset": "oewn-07748612-n",
        "note": "user-approved OpenImages decision: parent Snack, choose food popcorn sense",
    },
    "Punching bag": {
        "status": "select",
        "synset": "oewn-04030356-n",
        "note": "user-approved OpenImages decision: parent Sports equipment, choose punching bag artifact sense",
    },
    "Raccoon": {
        "status": "select",
        "synset": "oewn-02510652-n",
        "note": "user-approved OpenImages decision: parent Carnivore, choose animal raccoon sense",
    },
    "Racket": {
        "status": "select",
        "synset": "oewn-04045857-n",
        "note": "user-approved OpenImages decision: parent Sports equipment, choose racket artifact sense",
    },
    "Rocket": {
        "status": "select",
        "synset": "oewn-04106523-n",
        "note": "user-approved OpenImages decision: parent Aircraft, choose rocket/projectile artifact sense",
    },
    "Saucer": {
        "status": "select",
        "synset": "oewn-04146374-n",
        "note": "user-approved OpenImages decision: parent Tableware, choose dish/saucer artifact sense",
    },
    "Scorpion": {
        "status": "select",
        "synset": "oewn-01773034-n",
        "note": "user-approved OpenImages decision: parent Invertebrate, choose scorpion animal sense",
    },
    "Shellfish": {
        "status": "select",
        "synset": "oewn-07799186-n",
        "selection_tag": MANUAL_OPENIMAGES_FIRST_ALLOWED_TAG,
        "note": "user-approved first-order fallback: parent Seafood, choose food shellfish sense",
    },
    "Shorts": {
        "status": "select",
        "synset": "oewn-04212364-n",
        "note": "user-approved OpenImages decision: parent Clothing, choose short pants sense",
    },
    "Spatula": {
        "status": "select",
        "synset": "oewn-04277257-n",
        "selection_tag": MANUAL_OPENIMAGES_FIRST_ALLOWED_TAG,
        "note": "user-approved first-order fallback: parent Kitchen utensil, choose first spatula artifact sense",
    },
    "Sombrero": {
        "status": "select",
        "synset": "oewn-04266740-n",
        "note": "user-approved OpenImages decision: parent Hat, choose sombrero artifact sense",
    },
    "Squash": {
        "status": "select",
        "synset": "oewn-07731306-n",
        "note": "user-approved OpenImages decision: parent Vegetable, choose food squash sense",
    },
    "Squid": {
        "status": "select",
        "synset": "oewn-07797777-n",
        "selection_tag": MANUAL_OPENIMAGES_FIRST_ALLOWED_TAG,
        "note": "user-approved first object-compatible fallback: parent Marine invertebrates|Seafood, choose squid/calamari food sense",
    },
    "Stretcher": {
        "status": "select",
        "synset": "oewn-04343930-n",
        "note": "user-approved OpenImages decision: parent Medical equipment, choose patient-transport stretcher artifact sense",
    },
    "Taco": {
        "status": "select",
        "synset": "oewn-07896726-n",
        "note": "user-approved OpenImages decision: parent Food, choose food taco sense",
    },
    "Table": {
        "status": "select",
        "synset": "oewn-04386330-n",
        "note": "user-approved remaining ambiguous decision: table artifact sense",
    },
    "Tap": {
        "status": "select",
        "synset": "oewn-04566737-n",
        "note": "user-approved OpenImages decision: parent Plumbing fixture, choose water faucet/water tap/tap/hydrant artifact sense",
    },
    "Tart": {
        "status": "select",
        "synset": "oewn-07639542-n",
        "note": "user-approved OpenImages decision: parent Pastry, exclude person sense and choose food tart sense",
    },
    "Tiger": {
        "status": "select",
        "synset": "oewn-02132256-n",
        "note": "user-approved OpenImages decision: parent Carnivore, choose tiger animal sense",
    },
    "Television": {
        "status": "select",
        "synset": "oewn-04413042-n",
        "note": "user-approved remaining ambiguous decision: television receiver artifact sense",
    },
    "Tin can": {
        "status": "select",
        "synset": "oewn-02950393-n",
        "note": "user-approved OpenImages decision: parent Container, choose can/container artifact sense",
    },
    "Turtle": {
        "status": "select",
        "synset": "oewn-01665425-n",
        "note": "user-approved OpenImages decision: parent Reptile, choose animal turtle sense",
    },
    "Watercraft": {
        "status": "select",
        "synset": "oewn-04537861-n",
        "note": "user-approved OpenImages decision: parent Vehicle, choose vessel/watercraft artifact sense",
    },
    "Whisk": {
        "status": "select",
        "synset": "oewn-04586220-n",
        "note": "user-approved OpenImages decision: parent Kitchen utensil, choose kitchen whisk artifact sense",
    },
    "Winter melon": {
        "status": "select",
        "synset": "oewn-07772072-n",
        "note": "user-approved OpenImages decision: parent Vegetable, choose food winter melon sense",
    },
    "Wrench": {
        "status": "select",
        "synset": "oewn-04613932-n",
        "note": "user-approved OpenImages decision: parent Tool, choose wrench/spanner artifact sense",
    },
    "Zucchini": {
        "status": "select",
        "synset": "oewn-07732103-n",
        "note": "user-approved OpenImages decision: parent Squash, choose food zucchini sense",
    },
}


SOURCE_FIELDNAMES = [
    "dataset",
    "category_id",
    "mid",
    "label",
    "label_key",
    "source_version",
    "source_url",
    "hierarchy_url",
    "source_class",
    "openimages_parent_mids",
    "openimages_parent_labels",
    "openimages_child_mids",
    "openimages_child_labels",
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
    wn.config.data_directory = str(WN_DATA_DIR)
    nltk.data.path.insert(0, str(NLTK_DATA_DIR))

    SOURCE_LABELS_DIR.mkdir(parents=True, exist_ok=True)
    source_rows = _load_or_create_source_rows()
    prior_by_label_key = _load_prior_label_inventory(
        OBJECT_SOURCE_LABEL_INVENTORY,
        current_dataset="openimages",
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

    _write_tsv(OPENIMAGES_CANDIDATES, CANDIDATE_FIELDNAMES, candidate_rows)
    _write_tsv(
        OPENIMAGES_AMBIGUOUS,
        CANDIDATE_FIELDNAMES,
        [row for row in candidate_rows if _is_ambiguous_like(row)],
    )
    _write_tsv(
        OPENIMAGES_UNRESOLVED,
        CANDIDATE_FIELDNAMES,
        [row for row in candidate_rows if _is_unresolved_like(row)],
    )

    print(f"wrote={OPENIMAGES_SOURCE}")
    print(f"wrote={OPENIMAGES_CANDIDATES}")
    print(f"wrote={OPENIMAGES_AMBIGUOUS}")
    print(f"wrote={OPENIMAGES_UNRESOLVED}")
    for key, value in sorted(_summarize(candidate_rows).items()):
        print(f"{key}={value}")


def _load_or_create_source_rows() -> list[dict[str, str]]:
    if OPENIMAGES_SOURCE.exists():
        return _read_tsv(OPENIMAGES_SOURCE)

    label_rows = _download_class_description_rows()
    hierarchy = _download_hierarchy()
    parents_by_mid, children_by_mid = _hierarchy_edges(hierarchy)
    labels_by_mid = {row["mid"]: row["label"] for row in label_rows}

    rows = []
    for row in label_rows:
        mid = row["mid"]
        parent_mids = sorted(parents_by_mid.get(mid, set()))
        child_mids = sorted(children_by_mid.get(mid, set()))
        rows.append(
            {
                "dataset": "openimages",
                "category_id": mid,
                "mid": mid,
                "label": row["label"],
                "label_key": _surface_key(row["label"]),
                "source_version": OPENIMAGES_SOURCE_VERSION,
                "source_url": OPENIMAGES_CLASS_DESCRIPTIONS_URL,
                "hierarchy_url": OPENIMAGES_HIERARCHY_URL,
                "source_class": OPENIMAGES_SOURCE_CLASS,
                "openimages_parent_mids": "|".join(parent_mids),
                "openimages_parent_labels": "|".join(
                    labels_by_mid.get(parent_mid, "") for parent_mid in parent_mids
                ),
                "openimages_child_mids": "|".join(child_mids),
                "openimages_child_labels": "|".join(
                    labels_by_mid.get(child_mid, "") for child_mid in child_mids
                ),
            }
        )

    _write_tsv(OPENIMAGES_SOURCE, SOURCE_FIELDNAMES, rows)
    return rows


def _download_class_description_rows() -> list[dict[str, str]]:
    payload = urlopen(OPENIMAGES_CLASS_DESCRIPTIONS_URL, timeout=30).read().decode("utf-8")
    rows = []
    for mid, label in csv.reader(payload.splitlines()):
        normalized_label = " ".join(label.strip().split())
        rows.append({"mid": mid.strip(), "label": normalized_label})
    return rows


def _download_hierarchy() -> dict:
    if OPENIMAGES_HIERARCHY_RAW.exists():
        return json.loads(OPENIMAGES_HIERARCHY_RAW.read_text(encoding="utf-8"))

    payload = urlopen(OPENIMAGES_HIERARCHY_URL, timeout=30).read().decode("utf-8")
    with atomic_text_writer(OPENIMAGES_HIERARCHY_RAW) as handle:
        handle.write(payload)
    return json.loads(payload)


def _hierarchy_edges(hierarchy: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    parents_by_mid: dict[str, set[str]] = defaultdict(set)
    children_by_mid: dict[str, set[str]] = defaultdict(set)

    def walk(node: dict, parent_mid: str = "") -> None:
        mid = node.get("LabelName", "")
        if parent_mid and mid:
            parents_by_mid[mid].add(parent_mid)
            children_by_mid[parent_mid].add(mid)
        for child in node.get("Subcategory", []):
            walk(child, mid)

    walk(hierarchy)
    return parents_by_mid, children_by_mid


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
    selected_synset, selection_tag, wn30_tag, wn30_counts = _select_synset_without_direct_metadata(
        synsets=synsets,
        query=query,
        wn30_available=wn30_available,
    )
    selected_synset, selection_tag, objectness_class, objectness_gate = _apply_objectness_gate(
        selected_synset=selected_synset,
        selection_tag=selection_tag,
    )
    selected_synset, selection_tag, manual_decision, manual_note = (
        _apply_manual_openimages_label_decision(
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
    *,
    selected_synset: wn.Synset | None,
    synsets: list[wn.Synset],
) -> str:
    if selected_synset is not None:
        return "selected"
    if not synsets:
        return "unresolved"
    return "ambiguous"


def _apply_manual_openimages_label_decision(
    *,
    label: str,
    original_selection_status: str,
    selected_synset: wn.Synset | None,
    selection_tag: str,
    oewn: wn.Wordnet,
) -> tuple[wn.Synset | None, str, str, str]:
    if original_selection_status != "ambiguous":
        return selected_synset, selection_tag, "", ""

    decision = MANUAL_OPENIMAGES_LABEL_DECISIONS.get(label)
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
            decision.get("selection_tag", MANUAL_OPENIMAGES_REJECTED_TAG),
            manual_decision,
            decision["note"],
        )

    manual_synset = _synset_by_id(oewn, decision["synset"])
    if decision["status"] == "select":
        return (
            manual_synset,
            decision.get("selection_tag", MANUAL_OPENIMAGES_LABEL_REVIEW_TAG),
            f"select:{manual_synset.id}",
            decision["note"],
        )
    return selected_synset, selection_tag, "", ""


def _synset_by_id(oewn: wn.Wordnet, synset_id: str) -> wn.Synset:
    try:
        return oewn.synset(synset_id)
    except wn.Error as exc:
        raise ValueError(
            f"manual OpenImages decision references missing synset: {synset_id}"
        ) from exc


def _select_synset_without_direct_metadata(
    *,
    synsets: list[wn.Synset],
    query: str,
    wn30_available: bool,
) -> tuple[wn.Synset | None, str, str, str]:
    if not synsets:
        return None, "unresolved_no_oewn_noun_synset", "", ""
    if len(synsets) == 1:
        return synsets[0], "single_oewn_noun_synset", "", ""

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
        "canonical_selected_rows": sum(bool(row["canonical_surface"]) for row in rows),
        "parent_evidence_rows": sum(bool(row["parent_oewn_synsets"]) for row in rows),
    }


def _is_ambiguous_like(row: dict[str, str]) -> bool:
    return row["selection_status"] == "ambiguous"


def _is_unresolved_like(row: dict[str, str]) -> bool:
    return row["selection_status"] == "unresolved"


if __name__ == "__main__":
    main()
