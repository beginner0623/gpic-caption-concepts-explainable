from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
from typing import Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.stage4_extract_raw import (
    NLTK_DATA_DIR,
    OEWN_SPEC,
    WN_DATA_DIR,
    _lookup_oewn_synsets,
)

import nltk
import wn
from wn.morphy import Morphy


CANONICAL_FIELDS = frozenset(
    (
        "canonical_surface",
        "canonical_label_key",
        "canonical_selection_tag",
        "canonical_candidate_lemmas",
        "canonical_candidate_lemma_counts",
        "google_ngram_candidate_surfaces",
        "google_ngram_candidate_mean_frequencies",
    )
)

REWRITE_SOURCE_FIELDS = frozenset(
    (
        "selected_query",
        "has_oewn_noun_synset",
        "oewn_synset_count",
        "selected_oewn_synset",
        "selected_oewn_lexfile",
        "objectness_gate",
        "synset_lemmas",
        "parent_oewn_synsets",
        "parent_oewn_lexfiles",
        "parent_lemmas",
        "parent_selection_tag",
        "all_oewn_synsets",
        "all_oewn_lexfiles",
        "synset_selection_tag",
        "wn30_lemma_counts",
    )
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Overlay resolved object manual decisions onto a full GPIC object inventory.",
    )
    parser.add_argument("--full-inventory", required=True)
    parser.add_argument("--resolved-subset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resolved-copy")
    parser.add_argument("--summary")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = apply_object_manual_resolution(
        full_inventory_path=Path(args.full_inventory),
        resolved_subset_path=Path(args.resolved_subset),
        output_path=Path(args.output),
        resolved_copy_path=Path(args.resolved_copy) if args.resolved_copy else None,
    )
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def apply_object_manual_resolution(
    *,
    full_inventory_path: Path,
    resolved_subset_path: Path,
    output_path: Path,
    resolved_copy_path: Path | None = None,
    head_lookup: Callable[[str], dict[str, str]] | None = None,
) -> dict[str, object]:
    full_rows, full_fieldnames = _read_tsv(full_inventory_path)
    resolved_rows, resolved_fieldnames = _read_tsv(resolved_subset_path)
    if not full_fieldnames:
        raise ValueError(f"full inventory has no header: {full_inventory_path}")

    full_by_key = _unique_by_span_key(full_rows, "full inventory")
    resolved_by_key = _unique_by_span_key(resolved_rows, "resolved subset")
    replacement_source_by_key = {
        **full_by_key,
        **{
            key: value
            for key, value in resolved_by_key.items()
            if not _is_surface_rewrite_only(value)
        },
    }
    missing = sorted(key for key in resolved_by_key if key not in full_by_key)
    if missing:
        raise ValueError(
            "resolved rows not found in full inventory: " + ", ".join(missing[:20])
        )

    needs_manual_keys = {
        row.get("span_key", "")
        for row in full_rows
        if row.get("decision_status", "").strip() == "needs_manual"
    }
    resolved_keys = set(resolved_by_key)
    if needs_manual_keys != resolved_keys:
        raise ValueError(
            json.dumps(
                {
                    "status": "manual_resolution_key_mismatch",
                    "extra_resolved_keys": sorted(resolved_keys - needs_manual_keys)[:20],
                    "missing_needs_manual_keys": sorted(needs_manual_keys - resolved_keys)[:20],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    fieldnames = _merged_fieldnames(full_fieldnames, resolved_fieldnames)
    runtime_head_lookup = head_lookup
    merged_rows: list[dict[str, str]] = []
    resolved_output_rows: list[dict[str, str]] = []
    head_relookup_rows = 0
    head_relookup_needs_manual_rows = 0
    surface_rewrite_rows = 0
    surface_rewrite_needs_manual_rows = 0
    for row in full_rows:
        key = row.get("span_key", "")
        resolved = resolved_by_key.get(key)
        if resolved is None:
            merged_rows.append({field: row.get(field, "") for field in fieldnames})
            continue
        if _is_surface_rewrite_only(resolved):
            if (
                _normalize_replacement_key(resolved) not in full_by_key
                and runtime_head_lookup is None
            ):
                runtime_head_lookup = _build_head_lookup()
            replacement = _surface_rewrite_object_row(
                row,
                resolved,
                replacement_source_by_key,
                fieldnames,
                head_lookup=runtime_head_lookup,
            )
            surface_rewrite_rows += 1
            if replacement.get("decision_status") == "needs_manual":
                surface_rewrite_needs_manual_rows += 1
        else:
            if _needs_head_relookup(resolved) and runtime_head_lookup is None:
                runtime_head_lookup = _build_head_lookup()
            replacement = _resolved_object_row(
                row,
                resolved,
                fieldnames,
                head_lookup=runtime_head_lookup,
            )
        if _needs_head_relookup(resolved) and not _is_surface_rewrite_only(resolved):
            head_relookup_rows += 1
            if replacement.get("decision_status") == "needs_manual":
                head_relookup_needs_manual_rows += 1
        merged_rows.append(replacement)
        resolved_output_rows.append(replacement)

    _write_tsv(output_path, merged_rows, fieldnames)
    if resolved_copy_path is not None:
        _write_tsv(resolved_copy_path, resolved_output_rows, fieldnames)

    return {
        "full_inventory": str(full_inventory_path),
        "resolved_subset": str(resolved_subset_path),
        "output": str(output_path),
        "resolved_copy": str(resolved_copy_path) if resolved_copy_path else "",
        "full_rows": len(full_rows),
        "resolved_rows": len(resolved_rows),
        "overlaid_rows": len(resolved_output_rows),
        "original_decision_status_counts": _count_by(full_rows, "decision_status"),
        "resolved_decision_status_counts": _count_by(resolved_rows, "decision_status"),
        "merged_decision_status_counts": _count_by(merged_rows, "decision_status"),
        "merged_empty_selected_synset_rows": sum(
            1 for row in merged_rows if not row.get("selected_oewn_synset", "").strip()
        ),
        "merged_empty_canonical_surface_rows": sum(
            1 for row in merged_rows if not row.get("canonical_surface", "").strip()
        ),
        "head_relookup_rows": head_relookup_rows,
        "head_relookup_needs_manual_rows": head_relookup_needs_manual_rows,
        "surface_rewrite_rows": surface_rewrite_rows,
        "surface_rewrite_needs_manual_rows": surface_rewrite_needs_manual_rows,
    }


def _surface_rewrite_object_row(
    row: Mapping[str, str],
    resolved: Mapping[str, str],
    full_by_key: Mapping[str, Mapping[str, str]],
    fieldnames: list[str],
    *,
    head_lookup: Callable[[str], dict[str, str]] | None,
) -> dict[str, str]:
    replacement_key = _normalize_replacement_key(resolved)
    if not replacement_key:
        raise ValueError(f"surface rewrite row missing replacement span key: {resolved}")
    replacement_source = full_by_key.get(replacement_key)
    replacement_lookup: dict[str, str] | None = None
    if replacement_source is None:
        if head_lookup is None:
            raise ValueError(
                f"surface rewrite replacement row not found in full inventory: {replacement_key}"
            )
        replacement_lookup = head_lookup(replacement_key)

    output = {field: row.get(field, "") for field in fieldnames}
    for field in fieldnames:
        if field in CANONICAL_FIELDS:
            output[field] = ""
        elif field in resolved and field.startswith(("manual_", "replacement_")):
            output[field] = resolved.get(field, "")

    for field in REWRITE_SOURCE_FIELDS:
        if field in fieldnames:
            output[field] = (
                replacement_source.get(field, "")
                if replacement_source is not None
                else (replacement_lookup or {}).get(field, "")
            )

    source_status = (
        replacement_source.get("decision_status", "").strip()
        if replacement_source is not None
        else (replacement_lookup or {}).get("decision_status", "").strip()
    )
    selected_synset = (
        replacement_source.get("selected_oewn_synset", "").strip()
        if replacement_source is not None
        else (replacement_lookup or {}).get("selected_oewn_synset", "").strip()
    )
    if source_status == "chosen" and selected_synset:
        output["decision_status"] = "chosen"
        output["decision_reason"] = "manual_surface_rewrite_to_replacement_span"
    elif source_status == "excluded":
        output["decision_status"] = "excluded"
        output["decision_reason"] = "manual_surface_rewrite_to_excluded_replacement_span"
    else:
        output["decision_status"] = "needs_manual"
        output["decision_reason"] = "manual_surface_rewrite_replacement_needs_manual"

    if "selected_lookup_case" in fieldnames:
        output["selected_lookup_case"] = (
            "manual_surface_rewrite_to_replacement_span"
            if output["decision_status"] == "chosen"
            else (replacement_lookup or {}).get("selected_lookup_case", "")
        )
    if "selected_query" in fieldnames and not output.get("selected_query", "").strip():
        output["selected_query"] = (
            replacement_source.get("span_key", replacement_key)
            if replacement_source is not None
            else (replacement_lookup or {}).get("selected_query", replacement_key)
        )
    if "decision_basis" in fieldnames:
        output["decision_basis"] = _append_decision_basis(
            row.get("decision_basis", ""),
            "manual_surface_rewrite_to_replacement_span",
        )
    return output


def _is_surface_rewrite_only(resolved: Mapping[str, str]) -> bool:
    return (
        resolved.get("manual_action", "").strip() == "surface_rewrite_only"
        or bool(resolved.get("replacement_span_key", "").strip())
    )


def _normalize_replacement_key(resolved: Mapping[str, str]) -> str:
    return _surface_key(
        resolved.get("replacement_span_key", "")
        or resolved.get("replacement_selected_query", "")
        or resolved.get("replacement_observed_surface", "")
    )


def _append_decision_basis(current: str, addition: str) -> str:
    parts = [part for part in current.split("|") if part]
    if addition not in parts:
        parts.append(addition)
    return "|".join(parts)


def _surface_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _resolved_object_row(
    row: Mapping[str, str],
    resolved: Mapping[str, str],
    fieldnames: list[str],
    *,
    head_lookup: Callable[[str], dict[str, str]] | None,
) -> dict[str, str]:
    replacement = {field: row.get(field, "") for field in fieldnames}
    for field in fieldnames:
        if field in CANONICAL_FIELDS:
            replacement[field] = ""
            continue
        if field == "decision_status":
            replacement[field] = _normalize_resolved_status(resolved.get(field, ""))
            continue
        replacement[field] = resolved.get(field, row.get(field, ""))
    if _needs_head_relookup(resolved):
        query = (
            resolved.get("selected_query", "").strip()
            or resolved.get("canonical_surface", "").strip()
        )
        if not query:
            raise ValueError(f"resolved object head correction missing selected_query: {resolved}")
        if head_lookup is None:
            raise ValueError(f"resolved object head correction missing lookup runtime: {resolved}")
        lookup_fields = head_lookup(query)
        for field, value in lookup_fields.items():
            if field in fieldnames:
                replacement[field] = value
        replacement["selected_query"] = lookup_fields.get("selected_query", query)
        replacement["decision_status"] = lookup_fields.get("decision_status", "needs_manual")
        replacement["decision_reason"] = lookup_fields.get(
            "decision_reason",
            "manual_head_query_synset_required",
        )
    elif replacement.get("decision_status", "").strip() == "excluded":
        for field in CANONICAL_FIELDS | REWRITE_SOURCE_FIELDS:
            if field in replacement:
                replacement[field] = ""
        replacement["synset_selection_tag"] = (
            resolved.get("synset_selection_tag", "").strip() or "manual_rejected"
        )
    elif not resolved.get("selected_oewn_synset", "").strip():
        raise ValueError(f"resolved object row missing selected_oewn_synset: {resolved}")
    return replacement


def _needs_head_relookup(resolved: Mapping[str, str]) -> bool:
    if resolved.get("selected_oewn_synset", "").strip():
        return False
    manual_type = resolved.get("manual_resolution_type", "").strip()
    reason = resolved.get("decision_reason", "").strip()
    lookup_case = resolved.get("selected_lookup_case", "").strip()
    return (
        manual_type == "canonical_head_no_selected_synset"
        or reason == "manual_accept_canonical_head_modifier_removed"
        or lookup_case == "manual_modifier_removed_head"
    )


def _build_head_lookup() -> Callable[[str], dict[str, str]]:
    wn.config.data_directory = str(WN_DATA_DIR)
    nltk.data.path.insert(0, str(NLTK_DATA_DIR))
    oewn = wn.Wordnet(OEWN_SPEC, expand="")
    morphy = Morphy(oewn)

    def lookup(query: str) -> dict[str, str]:
        result = _lookup_oewn_synsets(query, oewn, morphy)
        selected = result.selected_synset
        return {
            "selected_lookup_case": result.lookup_case,
            "selected_query": result.query or query,
            "has_oewn_noun_synset": "true" if result.synsets else "false",
            "oewn_synset_count": str(len(result.synsets)),
            "selected_oewn_synset": selected.id if selected is not None else "",
            "selected_oewn_lexfile": selected.lexfile() if selected is not None else "",
            "objectness_gate": result.objectness_gate,
            "synset_lemmas": "|".join(selected.lemmas()) if selected is not None else "",
            "parent_oewn_synsets": "|".join(result.parent_oewn_synsets),
            "parent_oewn_lexfiles": "|".join(result.parent_oewn_lexfiles),
            "parent_lemmas": "|".join(result.parent_lemmas),
            "parent_selection_tag": result.parent_selection_tag,
            "all_oewn_synsets": "|".join(synset.id for synset in result.synsets),
            "all_oewn_lexfiles": "|".join(
                f"{synset.id}:{synset.lexfile()}" for synset in result.synsets
            ),
            "synset_selection_tag": result.synset_selection_tag,
            "wn30_lemma_counts": result.wn30_lemma_counts,
            "decision_status": result.decision_status,
            "decision_reason": (
                "manual_head_query_synset_required"
                if result.decision_status == "needs_manual"
                else "manual_head_query_selected_oewn_synset"
            ),
        }

    return lookup


def _normalize_resolved_status(value: str) -> str:
    status = value.strip()
    if status in {"accepted", "chosen", "selected"}:
        return "chosen"
    if status in {"excluded", "needs_manual"}:
        return status
    raise ValueError(f"unsupported resolved object decision_status: {value!r}")


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


def _merged_fieldnames(
    full_fieldnames: list[str],
    resolved_fieldnames: list[str],
) -> list[str]:
    fieldnames = list(full_fieldnames)
    for field in resolved_fieldnames:
        if field not in fieldnames:
            fieldnames.append(field)
    return fieldnames


def _count_by(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(row.get(field, "") for row in rows).items()))


if __name__ == "__main__":
    main()
