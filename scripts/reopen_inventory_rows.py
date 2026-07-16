from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Mapping

from gpic_concepts_v1.atomic_io import atomic_text_writer


PRESERVE_FIELDS = (
    "decision_status",
    "decision_reason",
    "selected_lookup_case",
    "selected_query",
    "selected_oewn_synset",
    "selected_oewn_lexfile",
    "objectness_gate",
    "synset_lemmas",
    "parent_oewn_synsets",
    "parent_oewn_lexfiles",
    "parent_lemmas",
    "parent_selection_tag",
    "canonical_surface",
    "canonical_label_key",
    "canonical_selection_tag",
    "canonical_candidate_lemmas",
    "canonical_candidate_lemma_counts",
    "google_ngram_candidate_surfaces",
    "google_ngram_candidate_mean_frequencies",
    "all_oewn_synsets",
    "all_oewn_lexfiles",
    "synset_selection_tag",
    "wn30_lemma_counts",
)

CLEAR_FIELDS = (
    "selected_lookup_case",
    "selected_query",
    "selected_oewn_synset",
    "selected_oewn_lexfile",
    "objectness_gate",
    "synset_lemmas",
    "parent_oewn_synsets",
    "parent_oewn_lexfiles",
    "parent_lemmas",
    "parent_selection_tag",
    "canonical_surface",
    "canonical_label_key",
    "canonical_selection_tag",
    "canonical_candidate_lemmas",
    "canonical_candidate_lemma_counts",
    "google_ngram_candidate_surfaces",
    "google_ngram_candidate_mean_frequencies",
    "all_oewn_synsets",
    "all_oewn_lexfiles",
    "synset_selection_tag",
    "wn30_lemma_counts",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reopen selected inventory rows as needs_manual while preserving prior selected fields.",
    )
    parser.add_argument("--inventory", action="append", required=True)
    parser.add_argument("--decision", action="append", required=True, help="span_key=reason")
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--source", default="manual_reopen")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    decisions = _parse_decisions(args.decision)
    audit_rows: dict[str, dict[str, str]] = {}
    summaries = []
    for inventory in args.inventory:
        path = Path(inventory)
        rows, fieldnames = _read_tsv(path)
        fieldnames = _extend_fieldnames(fieldnames)
        reopened = []
        for row in rows:
            key = row.get("span_key", "")
            if key not in decisions:
                continue
            _reopen_row(row, reason=decisions[key], source=args.source)
            reopened.append(key)
            audit_rows[key] = dict(row)
        _write_tsv(path, rows, fieldnames)
        summaries.append({"path": str(path), "row_count": len(rows), "reopened": reopened})

    audit_path = Path(args.audit_output)
    audit = [audit_rows[key] for key in sorted(audit_rows)]
    _write_tsv(audit_path, audit, _audit_fieldnames(audit))
    print(
        json.dumps(
            {
                "audit_output": str(audit_path),
                "audit_rows": len(audit),
                "inventories": summaries,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _parse_decisions(values: list[str]) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for value in values:
        key, sep, reason = value.partition("=")
        key = key.strip()
        reason = reason.strip()
        if not sep or not key or not reason:
            raise ValueError(f"--decision must be span_key=reason: {value!r}")
        decisions[key] = reason
    return decisions


def _reopen_row(row: dict[str, str], *, reason: str, source: str) -> None:
    for field in PRESERVE_FIELDS:
        previous_field = f"previous_{field}"
        if not row.get(previous_field, ""):
            row[previous_field] = row.get(field, "")
    row["decision_status"] = "needs_manual"
    row["decision_reason"] = reason
    row["manual_reopen_reason"] = reason
    row["manual_reopen_source"] = source
    for field in CLEAR_FIELDS:
        if field in row:
            row[field] = ""


def _extend_fieldnames(fieldnames: list[str]) -> list[str]:
    output = list(fieldnames)
    for field in PRESERVE_FIELDS:
        previous = f"previous_{field}"
        if previous not in output:
            output.append(previous)
    for field in ("manual_reopen_reason", "manual_reopen_source"):
        if field not in output:
            output.append(field)
    return output


def _audit_fieldnames(rows: list[Mapping[str, str]]) -> list[str]:
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    return fieldnames


def _read_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
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


if __name__ == "__main__":
    main()
