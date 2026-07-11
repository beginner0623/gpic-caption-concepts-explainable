"""Build the cumulative source-label to OEWN synset inventory.

This script combines dataset-specific candidate TSVs into one cumulative
inventory. It does not select canonical surfaces, does not build active
lexicons, and does not rewrite extraction rules.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path

from gpic_concepts_v1.atomic_io import atomic_text_writer


ROOT = Path(os.environ.get("GPIC_RUNTIME_ROOT", Path.cwd()))
SOURCE_LABELS_DIR = ROOT / "resources" / "source_labels"

INPUTS = [
    SOURCE_LABELS_DIR / "coco_oewn2025plus_synset_candidates.tsv",
    SOURCE_LABELS_DIR / "objects365_oewn2025plus_synset_candidates.tsv",
    SOURCE_LABELS_DIR / "openimages_oewn2025plus_synset_candidates.tsv",
    SOURCE_LABELS_DIR / "lvis_oewn2025plus_synset_candidates.tsv",
    SOURCE_LABELS_DIR / "visual_genome_oewn2025plus_synset_candidates.tsv",
]

OUTPUT = SOURCE_LABELS_DIR / "object_source_label_synset_inventory.tsv"
DUPLICATE_OUTPUT = SOURCE_LABELS_DIR / "object_source_label_duplicates.tsv"
CONFLICT_OUTPUT = SOURCE_LABELS_DIR / "object_source_label_synset_conflicts.tsv"

INVENTORY_FIELDNAMES = [
    "dataset",
    "source_label",
    "source_label_key",
    "source_category_id",
    "source_category_group",
    "source_version",
    "source_file",
    "selection_status",
    "duplicate_existing_label_key",
    "duplicate_existing_datasets",
    "duplicate_existing_labels",
    "duplicate_existing_selected_oewn_synsets",
    "is_mwe_candidate",
    "mwe_candidate_status",
    "wordnet_source",
    "wordnet_version",
    "wordnet_lexicon_id",
    "selected_lookup_case",
    "selected_query",
    "has_oewn_noun_synset",
    "oewn_synset_count",
    "selected_oewn_synset",
    "selected_oewn_lexfile",
    "synset_lemmas",
    "parent_oewn_synsets",
    "parent_oewn_lexfiles",
    "parent_lemmas",
    "parent_selection_tag",
    "all_oewn_synsets",
    "all_oewn_lexfiles",
    "selected_oewn_objectness_class",
    "objectness_gate",
    "manual_decision",
    "manual_decision_note",
    "wn30_selection_tag",
    "wn30_lemma_counts",
    "synset_selection_tag",
    "decision_basis",
]

CONFLICT_FIELDNAMES = [
    "source_label_key",
    "datasets",
    "source_labels",
    "selected_oewn_synsets",
    "rows",
]


def main() -> None:
    rows: list[dict[str, str]] = []
    for path in INPUTS:
        if not path.exists():
            continue
        rows.extend(_inventory_rows(path))

    semantic_rows = [
        row for row in rows if row["selection_status"] != "duplicate_existing_label_key"
    ]
    duplicate_rows = [
        row for row in rows if row["selection_status"] == "duplicate_existing_label_key"
    ]

    semantic_rows.sort(
        key=lambda row: (
            row["source_label_key"],
            row["dataset"],
            row["source_category_id"],
            row["source_label"],
        )
    )
    duplicate_rows.sort(
        key=lambda row: (
            row["source_label_key"],
            row["dataset"],
            row["source_category_id"],
            row["source_label"],
        )
    )
    conflicts = _conflict_rows(semantic_rows)

    _write_tsv(OUTPUT, INVENTORY_FIELDNAMES, semantic_rows)
    _write_tsv(DUPLICATE_OUTPUT, INVENTORY_FIELDNAMES, duplicate_rows)
    _write_tsv(CONFLICT_OUTPUT, CONFLICT_FIELDNAMES, conflicts)

    print(f"wrote={OUTPUT}")
    print(f"wrote={DUPLICATE_OUTPUT}")
    print(f"wrote={CONFLICT_OUTPUT}")
    print(f"semantic_inventory_rows={len(semantic_rows)}")
    print(f"duplicate_rows={len(duplicate_rows)}")
    print(f"source_occurrence_rows={len(rows)}")
    print(f"conflict_label_keys={len(conflicts)}")
    for dataset, count in sorted(_counts(semantic_rows, "dataset").items()):
        print(f"dataset_rows[{dataset}]={count}")
    for status, count in sorted(_counts(semantic_rows, "selection_status").items()):
        print(f"status_rows[{status}]={count}")


def _inventory_rows(path: Path) -> list[dict[str, str]]:
    return [_normalize_row(path, row) for row in _read_tsv(path)]


def _normalize_row(path: Path, row: dict[str, str]) -> dict[str, str]:
    label = row.get("label", "")
    return {
        "dataset": row.get("dataset", ""),
        "source_label": label,
        "source_label_key": row.get("label_key") or _label_key(label),
        "source_category_id": row.get("category_id") or row.get("category_index", ""),
        "source_category_group": row.get("supercategory") or row.get("source_class", ""),
        "source_version": row.get("source_version", ""),
        "source_file": path.name,
        "selection_status": _selection_status(row),
        "duplicate_existing_label_key": row.get("duplicate_existing_label_key", ""),
        "duplicate_existing_datasets": row.get("duplicate_existing_datasets", ""),
        "duplicate_existing_labels": row.get("duplicate_existing_labels", ""),
        "duplicate_existing_selected_oewn_synsets": row.get(
            "duplicate_existing_selected_oewn_synsets", ""
        ),
        "is_mwe_candidate": row.get("is_mwe_candidate", ""),
        "mwe_candidate_status": row.get("mwe_candidate_status", ""),
        "wordnet_source": row.get("wordnet_source", ""),
        "wordnet_version": row.get("wordnet_version", ""),
        "wordnet_lexicon_id": row.get("wordnet_lexicon_id", ""),
        "selected_lookup_case": row.get("selected_lookup_case", ""),
        "selected_query": row.get("selected_query", ""),
        "has_oewn_noun_synset": row.get("has_oewn_noun_synset", ""),
        "oewn_synset_count": row.get("oewn_synset_count", ""),
        "selected_oewn_synset": row.get("selected_oewn_synset", ""),
        "selected_oewn_lexfile": row.get("selected_oewn_lexfile", ""),
        "synset_lemmas": row.get("synset_lemmas", ""),
        "parent_oewn_synsets": row.get("parent_oewn_synsets", ""),
        "parent_oewn_lexfiles": row.get("parent_oewn_lexfiles", ""),
        "parent_lemmas": row.get("parent_lemmas", ""),
        "parent_selection_tag": row.get("parent_selection_tag", ""),
        "all_oewn_synsets": row.get("all_oewn_synsets", ""),
        "all_oewn_lexfiles": row.get("all_oewn_lexfiles", ""),
        "selected_oewn_objectness_class": row.get("selected_oewn_objectness_class", ""),
        "objectness_gate": row.get("objectness_gate", ""),
        "manual_decision": row.get("manual_decision", ""),
        "manual_decision_note": row.get("manual_decision_note", ""),
        "wn30_selection_tag": row.get("wn30_selection_tag", ""),
        "wn30_lemma_counts": row.get("wn30_lemma_counts", ""),
        "synset_selection_tag": row.get("synset_selection_tag", ""),
        "decision_basis": row.get("decision_basis", ""),
    }


def _selection_status(row: dict[str, str]) -> str:
    if row.get("selection_status"):
        return row["selection_status"]
    if row.get("manual_decision", "").startswith("reject"):
        return "rejected"
    if row.get("selected_oewn_synset"):
        return "selected"
    if row.get("has_oewn_noun_synset") == "false":
        return "unresolved"
    return "ambiguous"


def _conflict_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["selected_oewn_synset"]:
            by_key[row["source_label_key"]].append(row)

    conflicts: list[dict[str, str]] = []
    for label_key, key_rows in by_key.items():
        synsets = sorted({row["selected_oewn_synset"] for row in key_rows})
        if len(synsets) <= 1:
            continue
        conflicts.append(
            {
                "source_label_key": label_key,
                "datasets": "|".join(sorted({row["dataset"] for row in key_rows})),
                "source_labels": "|".join(
                    sorted({row["source_label"] for row in key_rows})
                ),
                "selected_oewn_synsets": "|".join(synsets),
                "rows": "|".join(
                    f"{row['dataset']}:{row['source_category_id']}:{row['selected_oewn_synset']}"
                    for row in key_rows
                ),
            }
        )
    conflicts.sort(key=lambda row: row["source_label_key"])
    return conflicts


def _counts(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row[key]] += 1
    return counts


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


def _label_key(label: str) -> str:
    return " ".join(label.strip().lower().split())


if __name__ == "__main__":
    main()
