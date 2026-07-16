from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge resolved GPIC inventory TSVs into one reusable prior."
    )
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--conflicts-output", required=True)
    parser.add_argument(
        "--conflict-field",
        action="append",
        default=[],
        help="Field that must agree for duplicate span_key rows.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = merge_inventory_prior(
        input_paths=[Path(path) for path in args.input],
        output_path=Path(args.output),
        conflicts_output_path=Path(args.conflicts_output),
        conflict_fields=args.conflict_field,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if summary["conflicts"]:
        raise SystemExit(2)


def merge_inventory_prior(
    *,
    input_paths: list[Path],
    output_path: Path,
    conflicts_output_path: Path,
    conflict_fields: list[str],
) -> dict[str, Any]:
    rows_by_key: dict[str, dict[str, str]] = {}
    fieldnames: list[str] | None = None
    conflicts: list[dict[str, str]] = []

    for path in input_paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if fieldnames is None:
                fieldnames = list(reader.fieldnames or [])
            for row in reader:
                normalized = _span_key(row)
                if not normalized:
                    continue
                candidate = dict(row)
                candidate["_source_prior"] = path.as_posix()
                previous = rows_by_key.get(normalized)
                if previous is None:
                    rows_by_key[normalized] = candidate
                    continue
                diffs = _conflict_diffs(previous, candidate, conflict_fields)
                if diffs:
                    conflicts.append(
                        {
                            "span_key": normalized,
                            "first_source": previous.get("_source_prior", ""),
                            "second_source": candidate.get("_source_prior", ""),
                            "diffs": " | ".join(diffs),
                        }
                    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_fields = [field for field in (fieldnames or []) if field != "_source_prior"]
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            output_fields,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows_by_key.values():
            writer.writerow({field: row.get(field, "") for field in output_fields})
    os.replace(tmp_path, output_path)

    if conflicts:
        conflicts_output_path.parent.mkdir(parents=True, exist_ok=True)
        with conflicts_output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                ["span_key", "first_source", "second_source", "diffs"],
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(conflicts)
    elif conflicts_output_path.exists():
        conflicts_output_path.unlink()

    return {
        "inputs": [path.as_posix() for path in input_paths],
        "output": output_path.as_posix(),
        "rows": len(rows_by_key),
        "conflicts": len(conflicts),
        "conflicts_output": conflicts_output_path.as_posix() if conflicts else "",
    }


def _span_key(row: dict[str, str]) -> str:
    value = row.get("span_key", "") or row.get("observed_surface", "")
    return " ".join(value.strip().lower().split())


def _conflict_diffs(
    first: dict[str, str],
    second: dict[str, str],
    fields: list[str],
) -> list[str]:
    diffs: list[str] = []
    for field in fields:
        left = (first.get(field, "") or "").strip()
        right = (second.get(field, "") or "").strip()
        if left != right:
            diffs.append(f"{field}: {left!r} != {right!r}")
    return diffs


if __name__ == "__main__":
    main()
