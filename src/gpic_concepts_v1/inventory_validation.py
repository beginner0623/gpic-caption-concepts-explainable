from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path


FINAL_DECISION_STATUSES = frozenset(("chosen", "excluded"))
PENDING_DECISION_STATUS = "needs_manual"


def normalize_inventory_decision_status(row: Mapping[str, str]) -> str:
    """Normalize inventory decision status without silently accepting unknown values."""
    explicit = row.get("decision_status", "").strip()
    if explicit:
        if explicit in FINAL_DECISION_STATUSES or explicit == PENDING_DECISION_STATUS:
            return explicit
        if explicit == "selected":
            return "chosen"
        return PENDING_DECISION_STATUS

    legacy = row.get("extraction_status", "").strip() or row.get("selection_status", "").strip()
    return normalize_legacy_decision_status(legacy)


def normalize_legacy_decision_status(value: str) -> str:
    if value in FINAL_DECISION_STATUSES or value == PENDING_DECISION_STATUS:
        return value
    if value == "selected":
        return "chosen"
    if value in {"manual_required", "ambiguous"}:
        return PENDING_DECISION_STATUS
    if value in {"unresolved", "rejected"}:
        return "excluded"
    if value:
        return PENDING_DECISION_STATUS
    return ""


def final_manual_resolution_blockers(
    rows: Sequence[Mapping[str, str]],
    *,
    require_canonical_surface_for_selected_synset: bool = False,
) -> list[dict[str, str]]:
    """Return rows that are not ready for parent/canonical enrichment."""
    blockers: list[dict[str, str]] = []
    for row in rows:
        status = normalize_inventory_decision_status(row)
        reason = ""
        if status not in FINAL_DECISION_STATUSES:
            reason = "pending_manual_decision_status"
        elif status == "chosen" and _chosen_surface_correction_missing_synset(row):
            reason = "surface_correction_requires_synset_lookup"
        elif (
            require_canonical_surface_for_selected_synset
            and status == "chosen"
            and _selected_synset_missing_canonical_surface(row)
        ):
            reason = "selected_synset_missing_canonical_surface"
        if not reason:
            continue
        blockers.append(
            {
                "blocker_reason": reason,
                "observed_surface": row.get("observed_surface", ""),
                "span_key": row.get("span_key", ""),
                "decision_status": row.get("decision_status", ""),
                "normalized_decision_status": status,
                "decision_reason": row.get("decision_reason", ""),
                "selected_query": row.get("selected_query", ""),
                "selected_oewn_synset": row.get("selected_oewn_synset", ""),
                "canonical_surface": row.get("canonical_surface", ""),
                "synset_selection_tag": row.get("synset_selection_tag", ""),
            }
        )
    return blockers


def read_inventory_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def _selected_synset_missing_canonical_surface(row: Mapping[str, str]) -> bool:
    if not row.get("selected_oewn_synset", "").strip():
        return False
    if row.get("canonical_surface", "").strip():
        return False
    return True


def _chosen_surface_correction_missing_synset(row: Mapping[str, str]) -> bool:
    if row.get("selected_oewn_synset", "").strip():
        return False
    base_keys = {
        _surface_key(row.get("span_key", "")),
        _surface_key(row.get("observed_surface", "")),
    }
    base_keys.discard("")
    correction_values = (
        row.get("selected_query", ""),
        row.get("canonical_surface", ""),
    )
    for value in correction_values:
        key = _surface_key(value)
        if key and base_keys and key not in base_keys:
            return True
    return False


def _surface_key(value: str) -> str:
    return " ".join(value.strip().lower().split())
