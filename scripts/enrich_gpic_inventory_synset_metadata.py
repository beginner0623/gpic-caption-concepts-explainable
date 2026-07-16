from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import wn

from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.stage4_extract_raw import (
    OEWN_SPEC,
    WN_DATA_DIR,
    _objectness_gate_for_lexfile,
)


METADATA_COLUMNS = [
    "has_oewn_noun_synset",
    "oewn_synset_count",
    "selected_oewn_lexfile",
    "objectness_gate",
    "synset_lemmas",
    "all_oewn_synsets",
    "all_oewn_lexfiles",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh selected OEWN synset metadata in a GPIC object inventory TSV.",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows, fieldnames = _read_tsv(Path(args.input))
    fieldnames = _fieldnames_with_metadata_columns(fieldnames)

    wn.config.data_directory = str(WN_DATA_DIR)
    oewn = wn.Wordnet(OEWN_SPEC, expand="")

    refreshed_rows = 0
    changed_cells = 0
    lookup_errors: list[dict[str, str]] = []
    for row in rows:
        synset_id = row.get("selected_oewn_synset", "").strip()
        if not synset_id:
            continue
        try:
            synset = oewn.synset(synset_id)
        except Exception as exc:
            lookup_errors.append(
                {
                    "span_key": row.get("span_key", ""),
                    "selected_oewn_synset": synset_id,
                    "error": repr(exc),
                }
            )
            continue
        changed_cells += _refresh_row(row, synset=synset)
        refreshed_rows += 1

    _write_tsv(Path(args.output), rows, fieldnames)
    summary: dict[str, Any] = {
        "input": args.input,
        "output": args.output,
        "rows": len(rows),
        "selected_synset_rows": refreshed_rows,
        "changed_cells": changed_cells,
        "lookup_error_rows": len(lookup_errors),
        "lookup_errors": lookup_errors[:10],
    }
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if lookup_errors:
        raise SystemExit(f"selected synset metadata lookup errors: {len(lookup_errors)}")


def _refresh_row(row: dict[str, str], *, synset: Any) -> int:
    synset_id = str(synset.id)
    lexfile = synset.lexfile()
    lemmas = "|".join(synset.lemmas())
    all_synsets = row.get("all_oewn_synsets", "").strip() or synset_id
    all_lexfiles = row.get("all_oewn_lexfiles", "").strip() or f"{synset_id}:{lexfile}"
    updates = {
        "has_oewn_noun_synset": "true",
        "oewn_synset_count": row.get("oewn_synset_count", "").strip() or "1",
        "selected_oewn_lexfile": lexfile,
        "objectness_gate": _objectness_gate_for_lexfile(lexfile),
        "synset_lemmas": lemmas,
        "all_oewn_synsets": all_synsets,
        "all_oewn_lexfiles": all_lexfiles,
    }
    changed = 0
    for field, value in updates.items():
        if row.get(field, "") != value:
            row[field] = value
            changed += 1
    return changed


def _read_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _fieldnames_with_metadata_columns(fieldnames: list[str]) -> list[str]:
    output = list(fieldnames)
    for column in METADATA_COLUMNS:
        if column not in output:
            output.append(column)
    return output


def _write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
