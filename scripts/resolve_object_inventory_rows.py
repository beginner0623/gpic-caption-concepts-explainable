from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Mapping

import wn

from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.stage4_extract_raw import (
    OBJECT_COMPATIBLE_LEXFILES,
    CONDITIONAL_OBJECT_LEXFILES,
    OEWN_SPEC,
    WN_DATA_DIR,
)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply explicit object inventory row decisions by span_key.",
    )
    parser.add_argument("--inventory", action="append", required=True)
    parser.add_argument(
        "--decision",
        action="append",
        required=True,
        help=(
            "span_key=>selected_query=>selected_oewn_synset=>canonical_surface=>reason. "
            "Use an empty selected_oewn_synset for an explicit no-synset canonical fallback."
        ),
    )
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--source", default="manual_resolution")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    decisions = [_parse_decision(value) for value in args.decision]
    decisions_by_key = {decision["span_key"]: decision for decision in decisions}

    wn.config.data_directory = str(WN_DATA_DIR)
    oewn = wn.Wordnet(OEWN_SPEC, expand="")

    audit_rows: dict[str, dict[str, str]] = {}
    summaries = []
    for inventory in args.inventory:
        path = Path(inventory)
        rows, fieldnames = _read_tsv(path)
        fieldnames = _extend_fieldnames(fieldnames)
        resolved = []
        for row in rows:
            key = row.get("span_key", "")
            decision = decisions_by_key.get(key)
            if decision is None:
                continue
            _apply_decision(row, decision=decision, oewn=oewn, source=args.source)
            resolved.append(key)
            audit_rows[key] = dict(row)
        missing = sorted(set(decisions_by_key) - set(resolved))
        if missing:
            raise ValueError(f"decision rows not found in {path}: {missing}")
        _write_tsv(path, rows, fieldnames)
        summaries.append({"path": str(path), "row_count": len(rows), "resolved": resolved})

    audit = [audit_rows[key] for key in sorted(audit_rows)]
    _write_tsv(Path(args.audit_output), audit, _audit_fieldnames(audit))
    print(
        json.dumps(
            {
                "audit_output": args.audit_output,
                "audit_rows": len(audit),
                "inventories": summaries,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _parse_decision(value: str) -> dict[str, str]:
    parts = [part.strip() for part in value.split("=>")]
    if len(parts) != 5:
        raise ValueError(f"--decision must have 5 fields separated by =>: {value!r}")
    span_key, selected_query, selected_synset, canonical_surface, reason = parts
    if not span_key or not selected_query or not canonical_surface or not reason:
        raise ValueError(f"--decision has an empty required field: {value!r}")
    return {
        "span_key": span_key,
        "selected_query": selected_query,
        "selected_oewn_synset": selected_synset,
        "canonical_surface": canonical_surface,
        "reason": reason,
    }


def _apply_decision(
    row: dict[str, str],
    *,
    decision: Mapping[str, str],
    oewn: wn.Wordnet,
    source: str,
) -> None:
    _raise_if_manual_canonical_would_bypass_missing_ngram(row, decision)

    for field in PRESERVE_FIELDS:
        previous = f"previous_{field}"
        if not row.get(previous, ""):
            row[previous] = row.get(field, "")

    selected_synset_id = decision["selected_oewn_synset"]
    selected_query = decision["selected_query"]
    canonical_surface = decision["canonical_surface"]
    reason = decision["reason"]

    row["decision_status"] = "chosen"
    row["decision_reason"] = reason
    row["selected_lookup_case"] = "manual"
    row["selected_query"] = selected_query
    row["selected_oewn_synset"] = selected_synset_id
    row["canonical_surface"] = canonical_surface
    row["canonical_label_key"] = _surface_key(canonical_surface)
    row["manual_resolution_source"] = source
    row["manual_resolution_note"] = reason

    if selected_synset_id:
        synset = oewn.synset(selected_synset_id)
        parents = list(synset.hypernyms())
        row["has_oewn_noun_synset"] = "true"
        row["oewn_synset_count"] = "1"
        row["selected_oewn_lexfile"] = synset.lexfile()
        row["objectness_gate"] = _objectness_gate(synset.lexfile())
        row["synset_lemmas"] = "|".join(synset.lemmas())
        row["all_oewn_synsets"] = selected_synset_id
        row["all_oewn_lexfiles"] = f"{selected_synset_id}:{synset.lexfile()}"
        row["synset_selection_tag"] = "manual_select"
        row["parent_oewn_synsets"] = "|".join(parent.id for parent in parents)
        row["parent_oewn_lexfiles"] = "|".join(
            f"{parent.id}:{parent.lexfile()}" for parent in parents
        )
        row["parent_lemmas"] = "|".join(
            f"{parent.id}:{';'.join(parent.lemmas())}" for parent in parents
        )
        row["parent_selection_tag"] = (
            "selected_all_immediate_oewn_hypernyms"
            if parents
            else "no_immediate_oewn_hypernym"
        )
        row["canonical_selection_tag"] = "manual_selected_canonical"
        row["manual_resolution_type"] = "selected_oewn_synset"
    else:
        row["has_oewn_noun_synset"] = "false"
        row["oewn_synset_count"] = "0"
        row["selected_oewn_lexfile"] = ""
        row["objectness_gate"] = ""
        row["synset_lemmas"] = ""
        row["all_oewn_synsets"] = ""
        row["all_oewn_lexfiles"] = ""
        row["synset_selection_tag"] = "manual_no_selected_synset"
        row["parent_oewn_synsets"] = ""
        row["parent_oewn_lexfiles"] = ""
        row["parent_lemmas"] = ""
        row["parent_selection_tag"] = ""
        row["canonical_selection_tag"] = "manual_no_synset_head_canonical"
        row["manual_resolution_type"] = "canonical_head_no_selected_synset"

    row["canonical_candidate_lemmas"] = ""
    row["canonical_candidate_lemma_counts"] = ""
    row["google_ngram_candidate_surfaces"] = ""
    row["google_ngram_candidate_mean_frequencies"] = ""
    row["wn30_lemma_counts"] = ""


def _raise_if_manual_canonical_would_bypass_missing_ngram(
    row: Mapping[str, str],
    decision: Mapping[str, str],
) -> None:
    tag = row.get("canonical_selection_tag", "").strip()
    if "google_ngram_evidence_missing" not in tag:
        return
    span_key = row.get("span_key", "").strip() or decision.get("span_key", "").strip()
    candidates = row.get("google_ngram_candidate_surfaces", "").strip()
    synset = row.get("selected_oewn_synset", "").strip() or decision.get(
        "selected_oewn_synset", ""
    ).strip()
    raise ValueError(
        "Manual canonical override is blocked because Google Ngram evidence is missing. "
        "Query Google Ngram with the candidate surfaces, append the evidence rows to "
        "resources/source_labels/google_ngram_canonical_frequency_evidence.tsv, then rerun "
        "scripts/enrich_gpic_inventory_canonical.py. "
        f"span_key={span_key!r}; selected_oewn_synset={synset!r}; "
        f"canonical_selection_tag={tag!r}; google_ngram_candidate_surfaces={candidates!r}"
    )


def _objectness_gate(lexfile: str) -> str:
    if lexfile in OBJECT_COMPATIBLE_LEXFILES:
        return "object_compatible"
    if lexfile in CONDITIONAL_OBJECT_LEXFILES:
        return "conditional"
    return "hard_conflict"


def _surface_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _extend_fieldnames(fieldnames: list[str]) -> list[str]:
    output = list(fieldnames)
    for field in PRESERVE_FIELDS:
        previous = f"previous_{field}"
        if previous not in output:
            output.append(previous)
    for field in ("manual_resolution_source", "manual_resolution_note", "manual_resolution_type"):
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
