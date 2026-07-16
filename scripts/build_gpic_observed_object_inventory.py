from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.inventory_bundle import load_inventory_bundle, merge_bundle_path
from gpic_concepts_v1.inventory_validation import (
    final_manual_resolution_blockers,
    read_inventory_rows,
)
from gpic_concepts_v1.io_jsonl import iter_jsonl
from gpic_concepts_v1.stage4_extract_raw import (
    _ObjectLookupResult,
    _chunk_tokens,
    _decision_reason_for_selection,
    _decision_status_for_selection,
    _is_allowed_token_record_span_start,
    _is_plural_common_noun_token,
    _load_object_lookup_runtime,
    _normalize_query,
    _objectness_gate_for_lexfile,
    _probe_object_surface,
    _require_int,
    _token_record_span_lookup_surfaces,
    _token_record_span_text,
)


FIELDNAMES = [
    "span_key",
    "observed_surface",
    "decision_status",
    "decision_reason",
    "count",
    "caption_count",
    "example_caption_ids",
    "example_surfaces",
    "selected_lookup_case",
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
    "decision_basis",
]


@dataclass
class SpanAccumulator:
    span_key: str
    count: int = 0
    caption_ids: set[str] = field(default_factory=set)
    surfaces: Counter[str] = field(default_factory=Counter)
    lookup: _ObjectLookupResult | None = None
    prior_row: dict[str, str] | None = None
    prior_reuse_basis: str = ""


@dataclass(frozen=True, slots=True)
class ObjectInventoryCheckpointState:
    caption_total: int
    noun_chunk_total: int
    prior_reused_hits: int
    inventory: dict[str, SpanAccumulator]


@dataclass(slots=True)
class ObjectInventoryCheckpointWriter:
    path: Path
    metadata: Mapping[str, str]
    interval_records: int = 10000
    _last_caption_total: int = 0

    def __post_init__(self) -> None:
        if self.interval_records < 1:
            raise ValueError("checkpoint_interval_records must be greater than zero")

    def maybe_write(
        self,
        *,
        caption_total: int,
        noun_chunk_total: int,
        prior_reused_hits: int,
        inventory: Mapping[str, SpanAccumulator],
    ) -> None:
        if caption_total - self._last_caption_total < self.interval_records:
            return
        self._last_caption_total = caption_total
        self.write(
            status="running",
            caption_total=caption_total,
            noun_chunk_total=noun_chunk_total,
            prior_reused_hits=prior_reused_hits,
            inventory=inventory,
        )

    def write_completed(self, *, summary: Mapping[str, Any]) -> None:
        self.write(
            status="completed",
            caption_total=int(summary.get("caption_total") or 0),
            noun_chunk_total=int(summary.get("noun_chunk_total") or 0),
            prior_reused_hits=int(summary.get("prior_reused_first_hits") or 0),
            inventory={},
            summary=summary,
        )

    def write(
        self,
        *,
        status: str,
        caption_total: int,
        noun_chunk_total: int,
        prior_reused_hits: int,
        inventory: Mapping[str, SpanAccumulator],
        summary: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "schema_version": 1,
            "artifact_type": "gpic_observed_object_inventory_checkpoint",
            "status": status,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "metadata": dict(self.metadata),
            "caption_total": caption_total,
            "noun_chunk_total": noun_chunk_total,
            "prior_reused_hits": prior_reused_hits,
            "inventory": [_accumulator_checkpoint_row(acc) for acc in inventory.values()],
        }
        if summary is not None:
            payload["summary"] = dict(summary)
        with atomic_text_writer(self.path) as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


@dataclass(frozen=True, slots=True)
class SpanSelection:
    surface: str
    lookup: _ObjectLookupResult | None = None
    prior_row: dict[str, str] | None = None
    prior_reuse_basis: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a GPIC-observed object span inventory from Stage 3 records. "
            "This does not read COCO/LVIS/Objects365/OpenImages/Visual Genome."
        ),
    )
    parser.add_argument("--input", required=True, help="Input stage3_records.jsonl")
    parser.add_argument(
        "--prior-inventory-bundle",
        help=(
            "Optional completed GPIC inventory bundle. When provided, the "
            "object inventory from the bundle is used as the reusable prior."
        ),
    )
    parser.add_argument(
        "--prior-object-inventory",
        help=(
            "Optional final GPIC observed object inventory TSV. Exact span_key "
            "matches reuse selected synset, canonical, and parent evidence."
        ),
    )
    parser.add_argument("--output", required=True, help="Output observed object inventory TSV")
    parser.add_argument("--summary", help="Optional summary JSON path")
    parser.add_argument("--limit", type=int, help="Optional maximum Stage 3 records to scan")
    parser.add_argument(
        "--progress-output",
        help="Optional JSON path updated while object inventory rows are built.",
    )
    parser.add_argument(
        "--progress-interval-records",
        type=int,
        default=10000,
        help="Caption interval for progress JSON updates. Default: 10000.",
    )
    parser.add_argument(
        "--checkpoint-output",
        help=(
            "Optional JSON checkpoint written during long scans. If used with "
            "--resume-checkpoint, an interrupted run resumes from this file."
        ),
    )
    parser.add_argument(
        "--resume-checkpoint",
        action="store_true",
        help="Resume from --checkpoint-output when it exists and metadata matches.",
    )
    parser.add_argument(
        "--checkpoint-interval-records",
        type=int,
        default=10000,
        help="Caption interval for checkpoint JSON updates. Default: 10000.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    object_lookup = _load_object_lookup_runtime()
    if object_lookup is None:
        raise RuntimeError("OEWN runtime lookup is unavailable; cannot build GPIC object inventory")

    prior_object_inventory = _prior_object_inventory_from_args(args)
    prior_rows_by_key = _load_reusable_prior_rows(prior_object_inventory)
    checkpoint_metadata = _checkpoint_metadata(args, prior_object_inventory)
    checkpoint_state = (
        _load_checkpoint(Path(args.checkpoint_output), checkpoint_metadata)
        if args.resume_checkpoint and args.checkpoint_output
        else None
    )
    checkpoint_writer = (
        ObjectInventoryCheckpointWriter(
            Path(args.checkpoint_output),
            metadata=checkpoint_metadata,
            interval_records=args.checkpoint_interval_records,
        )
        if args.checkpoint_output
        else None
    )
    resume_caption_total = checkpoint_state.caption_total if checkpoint_state else 0
    rows, summary = build_object_inventory_rows(
        _resume_records(
            iter_jsonl(args.input),
            resume_caption_total=resume_caption_total,
            limit=args.limit,
        ),
        object_lookup=object_lookup,
        prior_rows_by_key=prior_rows_by_key,
        progress_output=Path(args.progress_output) if args.progress_output else None,
        progress_interval_records=args.progress_interval_records,
        checkpoint_writer=checkpoint_writer,
        initial_inventory=checkpoint_state.inventory if checkpoint_state else None,
        initial_caption_total=resume_caption_total,
        initial_noun_chunk_total=checkpoint_state.noun_chunk_total if checkpoint_state else 0,
        initial_prior_reused_hits=checkpoint_state.prior_reused_hits
        if checkpoint_state
        else 0,
    )
    _write_tsv(Path(args.output), rows)

    summary.update(
        {
            "input": args.input,
            "output": args.output,
            "prior_inventory_bundle": args.prior_inventory_bundle or "",
            "prior_object_inventory": str(prior_object_inventory or ""),
            "prior_reusable_rows": len(prior_rows_by_key),
            "prior_reusable_selected_query_rows": 0,
        }
    )
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    if checkpoint_writer is not None:
        checkpoint_writer.write_completed(summary=summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _prior_object_inventory_from_args(args: argparse.Namespace) -> Path | None:
    bundle = load_inventory_bundle(args.prior_inventory_bundle) if args.prior_inventory_bundle else None
    return merge_bundle_path(
        field_name="object_inventory",
        explicit_path=args.prior_object_inventory,
        bundled_path=bundle.object_inventory if bundle else None,
    )


def build_object_inventory_rows(
    records: Iterable[Mapping[str, Any]],
    *,
    object_lookup: Any,
    prior_rows_by_key: Mapping[str, dict[str, str]] | None = None,
    progress_output: Path | None = None,
    progress_interval_records: int = 10000,
    checkpoint_writer: ObjectInventoryCheckpointWriter | None = None,
    initial_inventory: Mapping[str, SpanAccumulator] | None = None,
    initial_caption_total: int = 0,
    initial_noun_chunk_total: int = 0,
    initial_prior_reused_hits: int = 0,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if progress_interval_records < 1:
        raise ValueError("progress_interval_records must be greater than zero")
    prior_rows_by_key = prior_rows_by_key or {}
    inventory: dict[str, SpanAccumulator] = dict(initial_inventory or {})
    caption_total = initial_caption_total
    noun_chunk_total = initial_noun_chunk_total
    prior_reused_hits = initial_prior_reused_hits
    started = perf_counter()
    _write_progress(
        progress_output,
        status="running",
        phase="scan_stage3_records",
        caption_total=caption_total,
        noun_chunk_total=noun_chunk_total,
        inventory_rows=len(inventory),
        elapsed_seconds=round(perf_counter() - started, 3),
    )

    for record in records:
        caption_total += 1
        caption_id = str(record.get("caption_id", ""))
        token_by_i = {_require_int(token, "i"): token for token in record.get("tokens", [])}
        for chunk in record.get("noun_chunks", []):
            noun_chunk_total += 1
            selection = _select_inventory_span(
                chunk,
                token_by_i,
                object_lookup,
                prior_rows_by_key=prior_rows_by_key,
            )
            if not selection.surface:
                continue
            span_key = _normalize_query(selection.surface)
            acc = inventory.setdefault(span_key, SpanAccumulator(span_key=span_key))
            acc.count += 1
            if caption_id:
                acc.caption_ids.add(caption_id)
            acc.surfaces[selection.surface] += 1
            if selection.prior_row is not None and acc.prior_row is None:
                acc.prior_row = selection.prior_row
                acc.prior_reuse_basis = selection.prior_reuse_basis
                prior_reused_hits += 1
            if selection.prior_row is None and (
                acc.lookup is None or _lookup_rank(selection.lookup) > _lookup_rank(acc.lookup)
            ):
                acc.lookup = selection.lookup
        if caption_total == 1 or caption_total % progress_interval_records == 0:
            _write_progress(
                progress_output,
                status="running",
                phase="scan_stage3_records",
                caption_total=caption_total,
                noun_chunk_total=noun_chunk_total,
                inventory_rows=len(inventory),
                prior_reused_first_hits=prior_reused_hits,
                elapsed_seconds=round(perf_counter() - started, 3),
            )
        if checkpoint_writer is not None:
            checkpoint_writer.maybe_write(
                caption_total=caption_total,
                noun_chunk_total=noun_chunk_total,
                prior_reused_hits=prior_reused_hits,
                inventory=inventory,
            )

    rows = [_inventory_row(acc) for acc in inventory.values()]
    rows.sort(key=lambda row: (-int(row["count"]), row["span_key"]))
    summary = {
        "caption_total": caption_total,
        "noun_chunk_total": noun_chunk_total,
        "inventory_rows": len(rows),
        "prior_reused_rows": sum(
            1
            for acc in inventory.values()
            if acc.prior_row is not None and acc.prior_reuse_basis != "checkpoint_resume"
        ),
        "prior_selected_query_reused_rows": 0,
        "prior_reused_first_hits": prior_reused_hits,
        "decision_status_counts": dict(Counter(row["decision_status"] for row in rows)),
        "decision_reason_counts": dict(Counter(row["decision_reason"] for row in rows)),
    }
    _write_progress(
        progress_output,
        status="complete",
        phase="complete",
        caption_total=caption_total,
        noun_chunk_total=noun_chunk_total,
        inventory_rows=len(rows),
        prior_reused_rows=summary["prior_reused_rows"],
        decision_status_counts=summary["decision_status_counts"],
        decision_reason_counts=summary["decision_reason_counts"],
        elapsed_seconds=round(perf_counter() - started, 3),
    )
    return rows, summary


def _checkpoint_metadata(
    args: argparse.Namespace,
    prior_object_inventory: Path | None,
) -> dict[str, str]:
    return {
        "input": str(Path(args.input)),
        "output": str(Path(args.output)),
        "limit": "" if args.limit is None else str(args.limit),
        "prior_inventory_bundle": args.prior_inventory_bundle or "",
        "prior_object_inventory": str(prior_object_inventory or ""),
    }


def _load_checkpoint(
    path: Path,
    expected_metadata: Mapping[str, str],
) -> ObjectInventoryCheckpointState | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("artifact_type") != "gpic_observed_object_inventory_checkpoint":
        raise SystemExit(f"invalid object inventory checkpoint: {path}")
    metadata = payload.get("metadata") or {}
    if dict(metadata) != dict(expected_metadata):
        raise SystemExit(
            "object inventory checkpoint metadata mismatch; remove the stale "
            f"checkpoint or use a matching command: {path}"
        )
    if payload.get("status") == "completed":
        return None
    return ObjectInventoryCheckpointState(
        caption_total=int(payload.get("caption_total") or 0),
        noun_chunk_total=int(payload.get("noun_chunk_total") or 0),
        prior_reused_hits=int(payload.get("prior_reused_hits") or 0),
        inventory={
            acc.span_key: acc
            for acc in (
                _accumulator_from_checkpoint_row(row)
                for row in payload.get("inventory", [])
            )
        },
    )


def _accumulator_checkpoint_row(acc: SpanAccumulator) -> dict[str, Any]:
    return {
        "span_key": acc.span_key,
        "count": acc.count,
        "caption_ids": sorted(acc.caption_ids),
        "surfaces": dict(acc.surfaces),
        "prior_reuse_basis": acc.prior_reuse_basis,
        "lookup_row": _inventory_row(acc),
    }


def _accumulator_from_checkpoint_row(row: Mapping[str, Any]) -> SpanAccumulator:
    lookup_row = {
        field: str((row.get("lookup_row") or {}).get(field, ""))
        for field in FIELDNAMES
    }
    return SpanAccumulator(
        span_key=str(row.get("span_key", "")),
        count=int(row.get("count") or 0),
        caption_ids=set(str(item) for item in row.get("caption_ids", [])),
        surfaces=Counter({str(key): int(value) for key, value in row.get("surfaces", {}).items()}),
        prior_row=lookup_row,
        prior_reuse_basis=str(row.get("prior_reuse_basis") or "checkpoint_resume"),
    )


def _write_progress(path: Path | None, *, status: str, phase: str, **payload: Any) -> None:
    if path is None:
        return
    progress = {
        "schema_version": 1,
        "artifact_type": "gpic_observed_object_inventory_progress",
        "status": status,
        "phase": phase,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    with atomic_text_writer(path) as handle:
        handle.write(json.dumps(progress, ensure_ascii=False, indent=2, sort_keys=True))
        handle.write("\n")


def _select_inventory_span(
    chunk: dict[str, Any],
    token_by_i: dict[int, dict[str, Any]],
    object_lookup: Any,
    *,
    prior_rows_by_key: Mapping[str, dict[str, str]] | None = None,
) -> SpanSelection:
    prior_rows_by_key = prior_rows_by_key or {}
    tokens = _chunk_tokens(chunk, token_by_i)
    if not tokens:
        return SpanSelection("")
    root_i = _require_int(chunk, "root_i")
    root_pos = next((index for index, token in enumerate(tokens) if _require_int(token, "i") == root_i), None)
    if root_pos is None:
        return SpanSelection("")
    for start_pos in range(0, root_pos + 1):
        span_tokens = tokens[start_pos : root_pos + 1]
        if len(span_tokens) > 1 and not _is_allowed_token_record_span_start(span_tokens[0]):
            continue
        span_surface = _token_record_span_text(span_tokens)
        prior_row = prior_rows_by_key.get(_normalize_query(span_surface))
        if prior_row is not None:
            return SpanSelection(
                span_surface,
                prior_row=prior_row,
                prior_reuse_basis="prior_gpic_observed_object_inventory",
            )
        surfaces = _token_record_span_lookup_surfaces(span_tokens)
        lookup = _probe_object_surface(
            surfaces,
            object_lookup,
            require_manual_on_any_surface_changed_hit=_is_plural_common_noun_token(
                span_tokens[-1]
            ),
        )
        if lookup is not None and lookup.synsets:
            return SpanSelection(span_surface, lookup=lookup)
    root_surface = _token_record_span_text(tokens[root_pos : root_pos + 1])
    prior_row = prior_rows_by_key.get(_normalize_query(root_surface))
    if prior_row is not None:
        return SpanSelection(
            root_surface,
            prior_row=prior_row,
            prior_reuse_basis="prior_gpic_observed_object_inventory",
        )
    return SpanSelection(root_surface)


def _lookup_rank(lookup: _ObjectLookupResult | None) -> int:
    if lookup is None:
        return 0
    if lookup.decision_status == "needs_manual":
        return 3
    if lookup.selected_synset is not None:
        return 2
    if lookup.synsets:
        return 1
    return 0


def _inventory_row(acc: SpanAccumulator) -> dict[str, str]:
    if acc.prior_row is not None:
        return _inventory_row_from_prior(acc)
    lookup = acc.lookup
    selected = lookup.selected_synset if lookup is not None else None
    objectness_gate = _objectness_gate_for_lexfile(selected.lexfile()) if selected is not None else ""
    decision_status = lookup.decision_status if lookup is not None else ""
    if not decision_status:
        decision_status = _decision_status_for_selection(
            selected_synset=selected,
            synsets=lookup.synsets if lookup is not None else (),
            objectness_gate=objectness_gate,
        )
    decision_reason = lookup.decision_reason if lookup is not None else ""
    if not decision_reason:
        decision_reason = _decision_reason_for_selection(
            selected_synset=selected,
            synsets=lookup.synsets if lookup is not None else (),
            objectness_gate=objectness_gate,
        )
    return {
        "span_key": acc.span_key,
        "observed_surface": acc.surfaces.most_common(1)[0][0] if acc.surfaces else acc.span_key,
        "decision_status": decision_status,
        "decision_reason": decision_reason,
        "count": str(acc.count),
        "caption_count": str(len(acc.caption_ids)),
        "example_caption_ids": "|".join(sorted(acc.caption_ids)[:5]),
        "example_surfaces": "|".join(surface for surface, _ in acc.surfaces.most_common(5)),
        "selected_lookup_case": lookup.lookup_case if lookup is not None else "unresolved",
        "selected_query": lookup.query if lookup is not None else "",
        "has_oewn_noun_synset": "true" if lookup is not None and lookup.synsets else "false",
        "oewn_synset_count": str(len(lookup.synsets) if lookup is not None else 0),
        "selected_oewn_synset": selected.id if selected is not None else "",
        "selected_oewn_lexfile": selected.lexfile() if selected is not None else "",
        "objectness_gate": objectness_gate,
        "synset_lemmas": "|".join(selected.lemmas()) if selected is not None else "",
        "parent_oewn_synsets": "|".join(lookup.parent_oewn_synsets)
        if lookup is not None
        else "",
        "parent_oewn_lexfiles": "|".join(lookup.parent_oewn_lexfiles)
        if lookup is not None
        else "",
        "parent_lemmas": "|".join(lookup.parent_lemmas) if lookup is not None else "",
        "parent_selection_tag": lookup.parent_selection_tag if lookup is not None else "",
        "canonical_surface": "",
        "canonical_label_key": "",
        "canonical_selection_tag": "",
        "canonical_candidate_lemmas": "",
        "canonical_candidate_lemma_counts": "",
        "google_ngram_candidate_surfaces": "",
        "google_ngram_candidate_mean_frequencies": "",
        "all_oewn_synsets": "|".join(synset.id for synset in lookup.synsets) if lookup is not None else "",
        "all_oewn_lexfiles": "|".join(synset.lexfile() for synset in lookup.synsets) if lookup is not None else "",
        "synset_selection_tag": lookup.synset_selection_tag if lookup is not None else "unresolved_no_oewn_noun_synset",
        "wn30_lemma_counts": lookup.wn30_lemma_counts if lookup is not None else "",
        "decision_basis": "gpic_observed_caption_span_inventory",
    }



def _inventory_row_from_prior(acc: SpanAccumulator) -> dict[str, str]:
    row = {field: acc.prior_row.get(field, "") for field in FIELDNAMES} if acc.prior_row else {}
    row.update(
        {
            "span_key": acc.span_key,
            "observed_surface": acc.surfaces.most_common(1)[0][0] if acc.surfaces else acc.span_key,
            "count": str(acc.count),
            "caption_count": str(len(acc.caption_ids)),
            "example_caption_ids": "|".join(sorted(acc.caption_ids)[:5]),
            "example_surfaces": "|".join(surface for surface, _ in acc.surfaces.most_common(5)),
        }
    )
    prior_basis = row.get("decision_basis", "").strip()
    reuse_basis = acc.prior_reuse_basis or "prior_gpic_observed_object_inventory"
    if reuse_basis == "checkpoint_resume":
        row["decision_basis"] = prior_basis
    elif prior_basis and reuse_basis not in prior_basis.split("|"):
        row["decision_basis"] = f"{prior_basis}|{reuse_basis}"
    elif not prior_basis:
        row["decision_basis"] = reuse_basis
    return {field: row.get(field, "") for field in FIELDNAMES}


def _load_reusable_prior_rows(path: str | None) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    rows_by_key: dict[str, dict[str, str]] = {}
    for row in read_inventory_rows(path):
        span_key = row.get("span_key", "") or _normalize_query(row.get("observed_surface", ""))
        if not span_key or span_key in rows_by_key:
            continue
        if not _is_reusable_prior_row(row):
            continue
        rows_by_key[span_key] = dict(row)
    return rows_by_key


def _is_reusable_prior_row(row: Mapping[str, str]) -> bool:
    if final_manual_resolution_blockers(
        [row],
        require_canonical_surface_for_selected_synset=True,
    ):
        return False
    if _is_automatic_surface_changed_prior_row(row):
        return False
    return True


def _is_automatic_surface_changed_prior_row(row: Mapping[str, str]) -> bool:
    span_key = _normalize_query(row.get("span_key", "") or row.get("observed_surface", ""))
    selected_query = _normalize_query(row.get("selected_query", ""))
    if not span_key or not selected_query or span_key == selected_query:
        return False
    return not _has_manual_decision_evidence(row)


def _has_manual_decision_evidence(row: Mapping[str, str]) -> bool:
    evidence_fields = (
        "decision_basis",
        "synset_selection_tag",
        "decision_reason",
        "manual_resolution_type",
        "source_detail",
    )
    return any("manual" in row.get(field, "").lower() for field in evidence_fields)


def _limited_records(
    records: Iterable[Mapping[str, Any]],
    limit: int | None,
) -> Iterable[Mapping[str, Any]]:
    for index, record in enumerate(records):
        if limit is not None and index >= limit:
            break
        yield record


def _resume_records(
    records: Iterable[Mapping[str, Any]],
    *,
    resume_caption_total: int,
    limit: int | None,
) -> Iterable[Mapping[str, Any]]:
    for index, record in enumerate(records):
        if index < resume_caption_total:
            continue
        if limit is not None and index >= limit:
            break
        yield record


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(handle, FIELDNAMES, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
