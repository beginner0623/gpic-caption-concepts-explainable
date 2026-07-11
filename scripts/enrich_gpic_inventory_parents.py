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
from gpic_concepts_v1.inventory_validation import final_manual_resolution_blockers
from gpic_concepts_v1.stage4_extract_raw import OEWN_SPEC, WN_DATA_DIR


PARENT_COLUMNS = [
    "parent_oewn_synsets",
    "parent_oewn_lexfiles",
    "parent_lemmas",
    "parent_selection_tag",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add selected-synset immediate hypernym parent evidence to a GPIC object inventory TSV.",
    )
    parser.add_argument("--input", required=True, help="Input GPIC observed object inventory TSV")
    parser.add_argument("--output", required=True, help="Output inventory TSV with parent columns")
    parser.add_argument("--summary", help="Optional JSON summary path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows, fieldnames = _read_tsv(Path(args.input))
    fieldnames = _fieldnames_with_parent_columns(fieldnames)
    _raise_if_manual_resolution_pending(args, rows)

    wn.config.data_directory = str(WN_DATA_DIR)
    oewn = wn.Wordnet(OEWN_SPEC, expand="")

    filled = 0
    empty = 0
    missing_synset = 0
    lookup_errors: list[dict[str, str]] = []
    for row in rows:
        synset_id = row.get("selected_oewn_synset", "").strip()
        if not synset_id:
            _clear_parent_columns(row)
            missing_synset += 1
            continue
        try:
            synset = oewn.synset(synset_id)
        except Exception as exc:
            _clear_parent_columns(row)
            lookup_errors.append({"selected_oewn_synset": synset_id, "error": repr(exc)})
            continue
        parents = list(synset.hypernyms())
        if parents:
            row["parent_oewn_synsets"] = "|".join(parent.id for parent in parents)
            row["parent_oewn_lexfiles"] = "|".join(
                f"{parent.id}:{parent.lexfile()}" for parent in parents
            )
            row["parent_lemmas"] = "|".join(
                f"{parent.id}:{';'.join(parent.lemmas())}" for parent in parents
            )
            row["parent_selection_tag"] = "selected_all_immediate_oewn_hypernyms"
            filled += 1
        else:
            _clear_parent_columns(row)
            row["parent_selection_tag"] = "no_immediate_oewn_hypernym"
            empty += 1

    _write_tsv(Path(args.output), rows, fieldnames)
    summary: dict[str, Any] = {
        "input": args.input,
        "output": args.output,
        "rows": len(rows),
        "selected_synset_missing_rows": missing_synset,
        "parent_filled_rows": filled,
        "parent_empty_rows": empty,
        "parent_lookup_error_rows": len(lookup_errors),
        "parent_lookup_errors": lookup_errors[:10],
    }
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _raise_if_manual_resolution_pending(
    args: argparse.Namespace,
    rows: list[dict[str, str]],
) -> None:
    blockers = final_manual_resolution_blockers(rows)
    if not blockers:
        return
    summary: dict[str, Any] = {
        "input": args.input,
        "output": args.output,
        "rows": len(rows),
        "status": "blocked_manual_resolution_before_parent",
        "blocked_rows": len(blockers),
        "blocked_examples": blockers[:10],
    }
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    raise SystemExit(
        "manual resolution required before parent enrichment: "
        f"blocked_rows={len(blockers)}"
    )


def _read_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        return [dict(row) for row in reader], fieldnames


def _fieldnames_with_parent_columns(fieldnames: list[str]) -> list[str]:
    existing = [field for field in fieldnames if field not in PARENT_COLUMNS]
    try:
        insert_at = existing.index("synset_lemmas") + 1
    except ValueError:
        insert_at = len(existing)
    return existing[:insert_at] + PARENT_COLUMNS + existing[insert_at:]


def _clear_parent_columns(row: dict[str, str]) -> None:
    for column in PARENT_COLUMNS:
        row[column] = ""


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
