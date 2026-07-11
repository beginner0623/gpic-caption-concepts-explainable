"""Build Visual Genome object-name to OEWN-2025+ synset candidate rows.

This script creates source-label candidate resources only. It does not update
active Stage 2 or Stage 5 lexicons.
"""

from __future__ import annotations

import csv
import json
import os
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

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
    _has_any_counts,
    _immediate_hypernym_parents,
    _is_mwe_candidate,
    _lookup_oewn_synsets,
    _mwe_candidate_status,
    _objectness_class,
    _select_by_wn30_lemma_count,
    _select_canonical_surface,
    _sense_key_from_oewn_sense_id,
    _surface_key,
)
from gpic_concepts_v1.atomic_io import atomic_text_writer


ROOT = Path(os.environ.get("GPIC_RUNTIME_ROOT", Path.cwd()))
NLTK_DATA_DIR = ROOT / "resources" / "nltk_data"
SOURCE_LABELS_DIR = ROOT / "resources" / "source_labels"
OBJECT_SOURCE_LABEL_INVENTORY = (
    SOURCE_LABELS_DIR / "object_source_label_synset_inventory.tsv"
)

VISUAL_GENOME_OBJECTS_ZIP = Path(
    os.environ.get(
        "VISUAL_GENOME_OBJECTS_ZIP",
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp\objects.json.zip",
    )
)
VISUAL_GENOME_OBJECTS_URL = (
    "https://homes.cs.washington.edu/~ranjay/visualgenome/data/dataset/objects.json.zip"
)
VISUAL_GENOME_SOURCE_VERSION = "visual_genome_objects_v1.4"
VISUAL_GENOME_SOURCE_CLASS = "VisualGenomeObjectName"

VISUAL_GENOME_SOURCE = SOURCE_LABELS_DIR / "visual_genome_objects_aggregate.tsv"
VISUAL_GENOME_CANDIDATES = (
    SOURCE_LABELS_DIR / "visual_genome_oewn2025plus_synset_candidates.tsv"
)
VISUAL_GENOME_AMBIGUOUS = (
    SOURCE_LABELS_DIR / "visual_genome_oewn2025plus_ambiguous.tsv"
)
VISUAL_GENOME_UNRESOLVED = (
    SOURCE_LABELS_DIR / "visual_genome_oewn2025plus_unresolved.tsv"
)
VISUAL_GENOME_MANUAL_DECISIONS = (
    SOURCE_LABELS_DIR
    / "visual_genome_ambiguous_manual_decisions_v14_complete_noun_mapping.tsv"
)
MANUAL_VISUAL_GENOME_LABEL_REVIEW_TAG = "manual_select"


SOURCE_FIELDNAMES = [
    "dataset",
    "category_id",
    "label",
    "label_key",
    "source_version",
    "source_url",
    "source_class",
    "vg_label_occurrences",
    "vg_image_count",
    "vg_surface_variants",
    "vg_nonempty_synset_occurrences",
    "vg_empty_synset_occurrences",
    "vg_unique_nonempty_synset_count",
    "vg_top_synset",
    "vg_top_synset_count",
    "vg_top_synset_tie",
    "vg_synset_counts",
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
    "vg_synset_matched_oewn_synsets",
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
        current_dataset="visual_genome",
    )
    manual_decisions = _load_visual_genome_manual_decisions(
        VISUAL_GENOME_MANUAL_DECISIONS
    )
    oewn = wn.Wordnet(OEWN_SPEC, expand="")
    morphy = Morphy(oewn)
    wn30_available = _check_wn30_available()

    candidate_rows = [
        _build_candidate_row(
            source_row=row,
            prior_by_label_key=prior_by_label_key,
            manual_decisions=manual_decisions,
            oewn=oewn,
            morphy=morphy,
            wn30_available=wn30_available,
        )
        for row in source_rows
    ]

    _write_tsv(VISUAL_GENOME_CANDIDATES, CANDIDATE_FIELDNAMES, candidate_rows)
    _write_tsv(
        VISUAL_GENOME_AMBIGUOUS,
        CANDIDATE_FIELDNAMES,
        [row for row in candidate_rows if _is_ambiguous_like(row)],
    )
    _write_tsv(
        VISUAL_GENOME_UNRESOLVED,
        CANDIDATE_FIELDNAMES,
        [row for row in candidate_rows if _is_unresolved_like(row)],
    )

    print(f"wrote={VISUAL_GENOME_SOURCE}")
    print(f"wrote={VISUAL_GENOME_CANDIDATES}")
    print(f"wrote={VISUAL_GENOME_AMBIGUOUS}")
    print(f"wrote={VISUAL_GENOME_UNRESOLVED}")
    for key, value in sorted(_summarize(candidate_rows).items()):
        print(f"{key}={value}")


def _load_or_create_source_rows() -> list[dict[str, str]]:
    if VISUAL_GENOME_SOURCE.exists():
        return _read_tsv(VISUAL_GENOME_SOURCE)

    rows = _aggregate_visual_genome_objects(VISUAL_GENOME_OBJECTS_ZIP)
    _write_tsv(VISUAL_GENOME_SOURCE, SOURCE_FIELDNAMES, rows)
    return rows


def _aggregate_visual_genome_objects(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Visual Genome objects zip not found: {path}. "
            "Set VISUAL_GENOME_OBJECTS_ZIP to the local objects.json.zip path."
        )

    aggregates: dict[str, _VGAggregate] = {}
    with zipfile.ZipFile(path) as archive:
        json_names = [name for name in archive.namelist() if name.endswith(".json")]
        if len(json_names) != 1:
            raise ValueError(f"unexpected Visual Genome zip contents: {archive.namelist()}")
        with archive.open(json_names[0]) as handle:
            dataset = json.load(handle)

    for image_row in dataset:
        image_id = str(image_row.get("image_id", "")).strip()
        for object_row in image_row.get("objects", []):
            names = object_row.get("names") or []
            if not names and object_row.get("name"):
                names = [object_row["name"]]
            synsets = [
                str(item).strip()
                for item in object_row.get("synsets", [])
                if str(item).strip()
            ]
            for name in names:
                label = _normalize_label(str(name))
                if not label:
                    continue
                label_key = _surface_key(label)
                aggregate = aggregates.setdefault(label_key, _VGAggregate(label_key))
                aggregate.add(label=label, image_id=image_id, synsets=synsets)

    rows: list[dict[str, str]] = []
    for index, aggregate in enumerate(
        sorted(aggregates.values(), key=lambda item: item.label_key),
        start=1,
    ):
        rows.append(aggregate.to_source_row(category_id=f"vg_label_{index:06d}"))
    return rows


class _VGAggregate:
    def __init__(self, label_key: str) -> None:
        self.label_key = label_key
        self.surface_counts: Counter[str] = Counter()
        self.synset_counts: Counter[str] = Counter()
        self.empty_synset_occurrences = 0
        self.image_ids: set[str] = set()

    def add(self, *, label: str, image_id: str, synsets: list[str]) -> None:
        self.surface_counts[label] += 1
        if image_id:
            self.image_ids.add(image_id)
        if synsets:
            for synset in synsets:
                self.synset_counts[synset] += 1
        else:
            self.empty_synset_occurrences += 1

    def to_source_row(self, *, category_id: str) -> dict[str, str]:
        top_synsets = self._top_synsets()
        top_synset = top_synsets[0] if len(top_synsets) == 1 else ""
        top_count = self.synset_counts[top_synset] if top_synset else 0
        return {
            "dataset": "visual_genome",
            "category_id": category_id,
            "label": self._representative_label(),
            "label_key": self.label_key,
            "source_version": VISUAL_GENOME_SOURCE_VERSION,
            "source_url": VISUAL_GENOME_OBJECTS_URL,
            "source_class": VISUAL_GENOME_SOURCE_CLASS,
            "vg_label_occurrences": str(sum(self.surface_counts.values())),
            "vg_image_count": str(len(self.image_ids)),
            "vg_surface_variants": "|".join(
                f"{surface}:{count}"
                for surface, count in sorted(
                    self.surface_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:20]
            ),
            "vg_nonempty_synset_occurrences": str(sum(self.synset_counts.values())),
            "vg_empty_synset_occurrences": str(self.empty_synset_occurrences),
            "vg_unique_nonempty_synset_count": str(len(self.synset_counts)),
            "vg_top_synset": top_synset,
            "vg_top_synset_count": str(top_count),
            "vg_top_synset_tie": _bool(len(top_synsets) > 1),
            "vg_synset_counts": "|".join(
                f"{synset}:{count}"
                for synset, count in sorted(
                    self.synset_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
        }

    def _representative_label(self) -> str:
        return sorted(
            self.surface_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0][0]

    def _top_synsets(self) -> list[str]:
        if not self.synset_counts:
            return []
        max_count = max(self.synset_counts.values())
        return sorted(
            synset for synset, count in self.synset_counts.items() if count == max_count
        )


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


def _load_visual_genome_manual_decisions(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    decisions: dict[str, dict[str, str]] = {}
    for row in _read_tsv(path):
        label_key = row.get("label_key", "")
        decision = row.get("manual_decision_for_codex", "")
        if not label_key or not decision:
            continue
        if not decision.startswith("select:oewn-") or not decision.endswith("-n"):
            raise ValueError(
                f"invalid Visual Genome manual decision for {label_key!r}: {decision!r}"
            )
        selected_synset_id = decision.split(":", 1)[1]
        previous = decisions.get(label_key)
        if previous and previous["selected_oewn_synset"] != selected_synset_id:
            raise ValueError(f"conflicting Visual Genome manual decision for {label_key!r}")
        decisions[label_key] = {
            "selected_oewn_synset": selected_synset_id,
            "decision_tag": row.get("decision_tag", ""),
            "confidence": row.get("confidence", ""),
            "decision_file_version": row.get("decision_file_version", ""),
            "decision_policy": row.get("decision_policy", ""),
            "decision_note": row.get("decision_note", ""),
        }
    return decisions


def _build_candidate_row(
    *,
    source_row: dict[str, str],
    prior_by_label_key: dict[str, list[dict[str, str]]],
    manual_decisions: dict[str, dict[str, str]],
    oewn: wn.Wordnet,
    morphy: Morphy,
    wn30_available: bool,
) -> dict[str, str]:
    duplicate_rows = prior_by_label_key.get(source_row["label_key"])
    if duplicate_rows:
        return _build_duplicate_row(source_row, duplicate_rows)
    return _build_new_lookup_row(
        source_row, manual_decisions, oewn, morphy, wn30_available
    )


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
    manual_decisions: dict[str, dict[str, str]],
    oewn: wn.Wordnet,
    morphy: Morphy,
    wn30_available: bool,
) -> dict[str, str]:
    label = source_row["label"]
    lookup_case, query, synsets = _lookup_oewn_synsets(label=label, oewn=oewn, morphy=morphy)
    selected_synset, selection_tag, wn30_tag, wn30_counts, vg_matches = (
        _select_synset_with_visual_genome_metadata(
            synsets=synsets,
            query=query,
            vg_top_synset=source_row["vg_top_synset"],
            vg_top_synset_tie=source_row["vg_top_synset_tie"] == "true",
            vg_nonempty_synset_count=int(source_row["vg_unique_nonempty_synset_count"] or "0"),
            wn30_available=wn30_available,
        )
    )
    selected_synset, selection_tag, objectness_class, objectness_gate = _apply_objectness_gate(
        selected_synset=selected_synset,
        selection_tag=selection_tag,
    )
    manual_decision = ""
    manual_note = ""
    manual_row = manual_decisions.get(source_row["label_key"])
    if manual_row:
        selected_synset = _manual_synset_from_current_candidates(
            label=label,
            manual_row=manual_row,
            synsets=synsets,
        )
        selection_tag = MANUAL_VISUAL_GENOME_LABEL_REVIEW_TAG
        objectness_class = _objectness_class(selected_synset.lexfile() or "")
        objectness_gate = "manual_override"
        manual_decision = f"select:{selected_synset.id}"
        manual_note = _manual_visual_genome_note(manual_row)
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
        "vg_synset_matched_oewn_synsets": "|".join(synset.id for synset in vg_matches),
        "synset_selection_tag": selection_tag,
        "decision_basis": selection_tag,
    }


def _manual_synset_from_current_candidates(
    *,
    label: str,
    manual_row: dict[str, str],
    synsets: list[wn.Synset],
) -> wn.Synset:
    selected_synset_id = manual_row["selected_oewn_synset"]
    for synset in synsets:
        if synset.id == selected_synset_id:
            return synset
    raise ValueError(
        f"manual Visual Genome decision for {label!r} references synset outside "
        f"current OEWN lookup candidates: {selected_synset_id}"
    )


def _manual_visual_genome_note(manual_row: dict[str, str]) -> str:
    pieces = [
        "user-approved Visual Genome v14 noun mapping",
        f"decision_tag={manual_row.get('decision_tag', '')}",
        f"confidence={manual_row.get('confidence', '')}",
        f"decision_file_version={manual_row.get('decision_file_version', '')}",
    ]
    if manual_row.get("decision_note"):
        pieces.append(f"decision_note={manual_row['decision_note']}")
    return "; ".join(piece for piece in pieces if piece and not piece.endswith("="))


def _select_synset_with_visual_genome_metadata(
    *,
    synsets: list[wn.Synset],
    query: str,
    vg_top_synset: str,
    vg_top_synset_tie: bool,
    vg_nonempty_synset_count: int,
    wn30_available: bool,
) -> tuple[wn.Synset | None, str, str, str, list[wn.Synset]]:
    if not synsets:
        return None, "unresolved_no_oewn_noun_synset", "", "", []
    if len(synsets) == 1:
        return synsets[0], "single_oewn_noun_synset", "", "", []

    if vg_top_synset_tie:
        return None, "ambiguous_visual_genome_top_synset_tie", "", "", []

    if vg_top_synset:
        vg_matches = [
            synset for synset in synsets if vg_top_synset in _wn30_synset_names(synset)
        ]
        if len(vg_matches) == 1:
            return (
                vg_matches[0],
                "selected_by_visual_genome_top_synset_metadata",
                "",
                "",
                vg_matches,
            )
        if len(vg_matches) > 1:
            selected, wn30_tag, counts = _select_by_wn30_lemma_count(
                vg_matches, query, wn30_available
            )
            if selected is not None:
                return (
                    selected,
                    "selected_by_wn30_lemma_count_after_visual_genome_top_synset_metadata",
                    wn30_tag,
                    counts,
                    vg_matches,
                )
            return (
                None,
                f"ambiguous_after_visual_genome_top_synset_metadata_{wn30_tag}",
                wn30_tag,
                counts,
                vg_matches,
            )
        return (
            None,
            "ambiguous_visual_genome_top_synset_not_in_oewn_lookup_candidates",
            "",
            "",
            [],
        )

    if vg_nonempty_synset_count > 0:
        return None, "ambiguous_visual_genome_synset_metadata_without_unique_top", "", "", []

    selected, wn30_tag, counts = _select_without_dataset_metadata(
        synsets=synsets,
        query=query,
        wn30_available=wn30_available,
    )
    if selected is not None:
        return (
            selected,
            "selected_by_fallback_without_visual_genome_synset_metadata",
            wn30_tag,
            counts,
            [],
        )
    return None, f"ambiguous_no_visual_genome_synset_metadata_{wn30_tag}", wn30_tag, counts, []


def _select_without_dataset_metadata(
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


def _normalize_label(text: str) -> str:
    return " ".join(text.strip().split())


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
        "vg_rows_with_nonempty_synset_metadata": sum(
            int(row["vg_unique_nonempty_synset_count"] or "0") > 0 for row in rows
        ),
        "vg_top_synset_tie_rows": sum(row["vg_top_synset_tie"] == "true" for row in rows),
        "selected_by_visual_genome_top_synset_metadata_rows": sum(
            row["synset_selection_tag"] == "selected_by_visual_genome_top_synset_metadata"
            for row in rows
        ),
        "manual_visual_genome_selected_rows": sum(
            row["synset_selection_tag"] == MANUAL_VISUAL_GENOME_LABEL_REVIEW_TAG
            for row in rows
        ),
        "visual_genome_top_synset_not_in_lookup_candidate_rows": sum(
            "visual_genome_top_synset_not_in_oewn_lookup_candidates"
            in row["synset_selection_tag"]
            for row in rows
        ),
    }


def _is_ambiguous_like(row: dict[str, str]) -> bool:
    return row["selection_status"] == "ambiguous"


def _is_unresolved_like(row: dict[str, str]) -> bool:
    return row["selection_status"] == "unresolved"


if __name__ == "__main__":
    main()
