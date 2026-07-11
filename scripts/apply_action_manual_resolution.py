from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.atomic_io import atomic_text_writer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Overlay resolved action manual decisions onto a full GPIC action inventory.",
    )
    parser.add_argument("--full-inventory", required=True)
    parser.add_argument("--manual-decisions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resolved-output")
    parser.add_argument("--summary")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = apply_action_manual_resolution(
        full_inventory_path=Path(args.full_inventory),
        manual_decisions_path=Path(args.manual_decisions),
        output_path=Path(args.output),
        resolved_output_path=Path(args.resolved_output) if args.resolved_output else None,
    )
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def apply_action_manual_resolution(
    *,
    full_inventory_path: Path,
    manual_decisions_path: Path,
    output_path: Path,
    resolved_output_path: Path | None = None,
) -> dict[str, object]:
    full_rows, fieldnames = _read_tsv(full_inventory_path)
    manual_rows, _ = _read_tsv(manual_decisions_path)
    if not fieldnames:
        raise ValueError(f"full inventory has no header: {full_inventory_path}")

    full_by_key = _unique_by_span_key(full_rows, "full inventory")
    manual_by_key = _unique_by_span_key(manual_rows, "manual decisions")
    missing = sorted(key for key in manual_by_key if key not in full_by_key)
    if missing:
        raise ValueError(
            "manual action decisions not found in full inventory: "
            + ", ".join(missing[:20])
        )

    needs_manual_keys = {
        row.get("span_key", "")
        for row in full_rows
        if row.get("decision_status", "").strip() == "needs_manual"
    }
    manual_keys = set(manual_by_key)
    if needs_manual_keys != manual_keys:
        raise ValueError(
            json.dumps(
                {
                    "status": "manual_resolution_key_mismatch",
                    "extra_manual_keys": sorted(manual_keys - needs_manual_keys)[:20],
                    "missing_needs_manual_keys": sorted(needs_manual_keys - manual_keys)[:20],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    merged_rows: list[dict[str, str]] = []
    resolved_rows: list[dict[str, str]] = []
    for row in full_rows:
        key = row.get("span_key", "")
        manual = manual_by_key.get(key)
        if manual is None:
            merged_rows.append(dict(row))
            continue
        replacement = _resolved_action_row(row, manual)
        merged_rows.append(replacement)
        resolved_rows.append(replacement)

    _write_tsv(output_path, merged_rows, fieldnames)
    if resolved_output_path is not None:
        _write_tsv(resolved_output_path, resolved_rows, fieldnames)

    return {
        "full_inventory": str(full_inventory_path),
        "manual_decisions": str(manual_decisions_path),
        "output": str(output_path),
        "resolved_output": str(resolved_output_path) if resolved_output_path else "",
        "full_rows": len(full_rows),
        "manual_decision_rows": len(manual_rows),
        "overlaid_rows": len(resolved_rows),
        "original_decision_status_counts": _count_by(full_rows, "decision_status"),
        "merged_decision_status_counts": _count_by(merged_rows, "decision_status"),
    }


def _resolved_action_row(
    row: Mapping[str, str],
    manual: Mapping[str, str],
) -> dict[str, str]:
    selected_synset_id = manual.get("selected_oewn_synset", "").strip()
    if not selected_synset_id:
        raise ValueError(f"manual action decision missing selected_oewn_synset: {manual}")
    all_synsets = _split_pipe(row.get("all_oewn_synsets", ""))
    if selected_synset_id not in all_synsets:
        raise ValueError(
            "manual action decision references synset outside current candidates: "
            f"{row.get('span_key', '')} -> {selected_synset_id}"
        )
    selected_query = manual.get("selected_query", "").strip() or row.get("selected_query", "")
    if "|" in selected_query:
        raise ValueError(
            f"manual action selected_query must be singular: {row.get('span_key', '')}"
        )
    selected_lexfile = _lexfile_for_synset(row, selected_synset_id)
    replacement = dict(row)
    replacement["decision_status"] = "chosen"
    replacement["decision_reason"] = "manual_action_synset_selected"
    replacement["selected_query"] = selected_query
    replacement["selected_oewn_synset"] = selected_synset_id
    replacement["selected_oewn_lexfile"] = selected_lexfile
    replacement["synset_selection_tag"] = "manual_select"
    replacement["decision_basis"] = "gpic_observed_action_inventory_manual_resolution"
    note = manual.get("manual_decision_note", "").strip()
    if note:
        replacement["wn30_lemma_counts"] = _append_note(
            row.get("wn30_lemma_counts", ""),
            f"manual_note={note}",
        )
    return replacement


def _lexfile_for_synset(row: Mapping[str, str], selected_synset_id: str) -> str:
    synset_ids = _split_pipe(row.get("all_oewn_synsets", ""))
    lexfiles = _split_pipe(row.get("all_oewn_lexfiles", ""))
    for index, synset_id in enumerate(synset_ids):
        if synset_id == selected_synset_id:
            return lexfiles[index] if index < len(lexfiles) else ""
    return ""


def _append_note(value: str, note: str) -> str:
    return f"{value}||{note}" if value else note


def _read_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def _write_tsv(path: Path, rows: list[Mapping[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _unique_by_span_key(
    rows: list[dict[str, str]],
    label: str,
) -> dict[str, dict[str, str]]:
    by_key: dict[str, dict[str, str]] = {}
    duplicates: set[str] = set()
    for row in rows:
        key = row.get("span_key", "")
        if not key:
            raise ValueError(f"{label} has a row without span_key")
        if key in by_key:
            duplicates.add(key)
        by_key[key] = row
    if duplicates:
        raise ValueError(f"{label} has duplicate span_key rows: {sorted(duplicates)[:20]}")
    return by_key


def _split_pipe(value: str) -> list[str]:
    return [part for part in value.split("|") if part]


def _count_by(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(row.get(field, "") for row in rows).items()))


if __name__ == "__main__":
    main()
