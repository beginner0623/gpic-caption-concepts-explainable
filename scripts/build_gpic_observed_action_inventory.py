from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.io_jsonl import iter_jsonl
from gpic_concepts_v1.pipeline_state import (
    artifact_state_path,
    build_action_inventory_state,
    write_pipeline_state,
)
from gpic_concepts_v1.stage4_extract_raw import (
    _ActionLookupResult,
    _ActionSpanCandidate,
    _action_candidate_priority,
    _action_candidates_from_token_record,
    _action_lookup_result_from_inventory_row,
    _build_children_by_head,
    _find_preposition_mwe_matches_in_token_records,
    _load_object_lookup_runtime,
    _load_preposition_mwe_lookup_runtime,
    _lookup_action_candidate,
    _lookup_oewn_verb_synsets,
    _normalize_query,
    _optional_text,
    _require_int,
    _token_text,
    load_gpic_action_inventory,
    load_preposition_mwe_lexicon,
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
    "candidate_types",
    "selected_lookup_case",
    "selected_query",
    "has_oewn_verb_synset",
    "oewn_synset_count",
    "selected_oewn_synset",
    "selected_oewn_lexfile",
    "synset_lemmas",
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


@dataclass(slots=True)
class ActionAccumulator:
    span_key: str
    count: int = 0
    caption_count_base: int = 0
    caption_ids: set[str] = field(default_factory=set)
    caption_id_examples: set[str] = field(default_factory=set)
    surfaces: Counter[str] = field(default_factory=Counter)
    candidate_types: Counter[str] = field(default_factory=Counter)
    lookup: _ActionLookupResult | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a GPIC-observed action inventory from Stage 3 records.",
    )
    parser.add_argument("--input", required=True, help="Input stage3_records.jsonl")
    parser.add_argument(
        "--action-inventory",
        help=(
            "Optional prior resolved GPIC observed action inventory TSV. "
            "Final chosen/raw_fallback rows are reused by span_key before "
            "runtime OEWN lookup."
        ),
    )
    parser.add_argument("--output", required=True, help="Output observed action inventory TSV")
    parser.add_argument(
        "--preposition-mwe-lexicon",
        help=(
            "Optional active preposition MWE TSV. If omitted, uses "
            "resources/lexicons/preposition_mwes.tsv when it exists."
        ),
    )
    parser.add_argument(
        "--needs-manual-output",
        help="Optional TSV containing only decision_status=needs_manual rows",
    )
    parser.add_argument("--summary", help="Optional summary JSON path")
    parser.add_argument("--limit", type=int, help="Optional maximum Stage 3 records to scan")
    parser.add_argument(
        "--progress-output",
        help="Optional JSON path updated periodically while scanning Stage 3 records.",
    )
    parser.add_argument(
        "--progress-interval-records",
        type=int,
        default=5000,
        help="Record interval for progress JSON updates when --progress-output is set.",
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
        default=50000,
        help="Record interval for checkpoint JSON updates.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    progress_writer = (
        ActionInventoryProgressWriter(
            Path(args.progress_output),
            interval_records=args.progress_interval_records,
        )
        if args.progress_output
        else None
    )
    try:
        if progress_writer is not None:
            progress_writer.write(
                status="running",
                phase="load_runtime",
                input=args.input,
                output=args.output,
            )
        runtime_action_lookup = _load_object_lookup_runtime()
        if runtime_action_lookup is None:
            raise SystemExit("OEWN runtime lookup is unavailable.")
        action_lookup = _build_action_lookup(args.action_inventory, runtime_action_lookup)
        preposition_mwe_lookup = (
            load_preposition_mwe_lexicon(Path(args.preposition_mwe_lexicon))
            if args.preposition_mwe_lexicon
            else _load_preposition_mwe_lookup_runtime()
        )

        checkpoint_metadata = _checkpoint_metadata(args)
        checkpoint_state = (
            _load_checkpoint(Path(args.checkpoint_output), checkpoint_metadata)
            if args.resume_checkpoint and args.checkpoint_output
            else None
        )
        checkpoint_writer = (
            ActionInventoryCheckpointWriter(
                Path(args.checkpoint_output),
                metadata=checkpoint_metadata,
                interval_records=args.checkpoint_interval_records,
            )
            if args.checkpoint_output
            else None
        )
        resume_caption_total = checkpoint_state.caption_total if checkpoint_state else 0
        records = _resume_records(
            iter_jsonl(args.input),
            resume_caption_total=resume_caption_total,
            limit=args.limit,
        )
        rows, summary = build_action_inventory_rows(
            records,
            action_lookup=action_lookup,
            preposition_mwe_lookup=preposition_mwe_lookup,
            progress_writer=progress_writer,
            checkpoint_writer=checkpoint_writer,
            initial_inventory=checkpoint_state.inventory if checkpoint_state else None,
            initial_caption_total=resume_caption_total,
            initial_verb_token_total=checkpoint_state.verb_token_total
            if checkpoint_state
            else 0,
            initial_relation_mwe_match_total=checkpoint_state.relation_mwe_match_total
            if checkpoint_state
            else 0,
            initial_relation_mwe_consumed_token_total=checkpoint_state.relation_mwe_consumed_token_total
            if checkpoint_state
            else 0,
        )
        output_path = Path(args.output)
        _write_tsv(output_path, rows)
        if args.needs_manual_output:
            _write_tsv(
                Path(args.needs_manual_output),
                [row for row in rows if row["decision_status"] == "needs_manual"],
            )
        pipeline_state_path = artifact_state_path(output_path)
        pipeline_state = build_action_inventory_state(
            input_path=args.input,
            output_path=args.output,
            needs_manual_output=args.needs_manual_output or "",
            summary=summary,
        )
        write_pipeline_state(pipeline_state_path, pipeline_state)
        summary.update(
            {
                "input": args.input,
                "output": args.output,
                "needs_manual_output": args.needs_manual_output or "",
                "pipeline_state": str(pipeline_state_path),
                "progress_output": args.progress_output or "",
            }
        )
        if progress_writer is not None:
            progress_writer.write(status="completed", phase="complete", summary=summary)
        if checkpoint_writer is not None:
            checkpoint_writer.write_completed(summary=summary)
        if args.summary:
            with atomic_text_writer(Path(args.summary)) as handle:
                handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
                handle.write("\n")
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    except BaseException as exc:
        if progress_writer is not None:
            progress_writer.write(
                status="failed",
                phase="failed",
                input=args.input,
                output=args.output,
                error=repr(exc),
            )
        raise


@dataclass(slots=True)
class ActionInventoryProgressWriter:
    path: Path
    interval_records: int = 5000
    _started_at: float = field(init=False, repr=False)
    _last_caption_total: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.interval_records = max(1, self.interval_records)
        self._started_at = time.monotonic()
        self._last_caption_total = -self.interval_records

    def maybe_write(self, **payload: Any) -> None:
        caption_total = int(payload.get("caption_total") or 0)
        if caption_total - self._last_caption_total < self.interval_records:
            return
        self._last_caption_total = caption_total
        self.write(status="running", phase="scan_stage3_records", **payload)

    def write(
        self,
        *,
        status: str,
        phase: str,
        summary: Mapping[str, Any] | None = None,
        **payload: Any,
    ) -> None:
        progress = {
            "schema_version": 1,
            "artifact_type": "gpic_observed_action_inventory_progress",
            "status": status,
            "phase": phase,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - self._started_at, 3),
            **payload,
        }
        if summary is not None:
            progress.update(summary)
            progress["summary"] = summary
        with atomic_text_writer(self.path) as handle:
            handle.write(json.dumps(progress, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")


@dataclass(slots=True)
class ActionInventoryCheckpointState:
    caption_total: int
    verb_token_total: int
    relation_mwe_match_total: int
    relation_mwe_consumed_token_total: int
    inventory: dict[str, ActionAccumulator]


@dataclass(slots=True)
class ActionInventoryCheckpointWriter:
    path: Path
    metadata: Mapping[str, Any]
    interval_records: int = 50000
    _last_caption_total: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.interval_records = max(1, self.interval_records)
        self._last_caption_total = -self.interval_records

    def maybe_write(
        self,
        *,
        caption_total: int,
        verb_token_total: int,
        relation_mwe_match_total: int,
        relation_mwe_consumed_token_total: int,
        inventory: Mapping[str, ActionAccumulator],
    ) -> None:
        if caption_total - self._last_caption_total < self.interval_records:
            return
        self._last_caption_total = caption_total
        self.write(
            status="running",
            caption_total=caption_total,
            verb_token_total=verb_token_total,
            relation_mwe_match_total=relation_mwe_match_total,
            relation_mwe_consumed_token_total=relation_mwe_consumed_token_total,
            inventory=inventory,
        )

    def write_completed(self, *, summary: Mapping[str, Any]) -> None:
        self.write(
            status="completed",
            caption_total=int(summary.get("caption_total") or 0),
            verb_token_total=int(summary.get("verb_token_total") or 0),
            relation_mwe_match_total=int(summary.get("relation_mwe_match_total") or 0),
            relation_mwe_consumed_token_total=int(
                summary.get("relation_mwe_consumed_token_total") or 0
            ),
            inventory={},
            summary=summary,
        )

    def write(
        self,
        *,
        status: str,
        caption_total: int,
        verb_token_total: int,
        relation_mwe_match_total: int,
        relation_mwe_consumed_token_total: int,
        inventory: Mapping[str, ActionAccumulator],
        summary: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "schema_version": 1,
            "artifact_type": "gpic_observed_action_inventory_checkpoint",
            "status": status,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "metadata": dict(self.metadata),
            "caption_total": caption_total,
            "verb_token_total": verb_token_total,
            "relation_mwe_match_total": relation_mwe_match_total,
            "relation_mwe_consumed_token_total": relation_mwe_consumed_token_total,
            "inventory": [_accumulator_checkpoint_row(acc) for acc in inventory.values()],
        }
        if summary is not None:
            payload["summary"] = dict(summary)
        with atomic_text_writer(self.path) as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _checkpoint_metadata(args: argparse.Namespace) -> dict[str, str]:
    return {
        "input": str(Path(args.input)),
        "output": str(Path(args.output)),
        "limit": "" if args.limit is None else str(args.limit),
        "action_inventory": args.action_inventory or "",
        "preposition_mwe_lexicon": args.preposition_mwe_lexicon or "",
    }


def _load_checkpoint(
    path: Path,
    expected_metadata: Mapping[str, str],
) -> ActionInventoryCheckpointState | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("artifact_type") != "gpic_observed_action_inventory_checkpoint":
        raise SystemExit(f"invalid action inventory checkpoint: {path}")
    metadata = payload.get("metadata") or {}
    if dict(metadata) != dict(expected_metadata):
        raise SystemExit(
            "action inventory checkpoint metadata mismatch; remove the stale "
            f"checkpoint or use a matching command: {path}"
        )
    if payload.get("status") == "completed":
        return None
    return ActionInventoryCheckpointState(
        caption_total=int(payload.get("caption_total") or 0),
        verb_token_total=int(payload.get("verb_token_total") or 0),
        relation_mwe_match_total=int(payload.get("relation_mwe_match_total") or 0),
        relation_mwe_consumed_token_total=int(
            payload.get("relation_mwe_consumed_token_total") or 0
        ),
        inventory={
            acc.span_key: acc
            for acc in (
                _accumulator_from_checkpoint_row(row)
                for row in payload.get("inventory", [])
            )
        },
    )


def _accumulator_checkpoint_row(acc: ActionAccumulator) -> dict[str, Any]:
    return {
        "span_key": acc.span_key,
        "count": acc.count,
        "caption_count_base": _caption_count(acc),
        "caption_id_examples": _example_caption_ids(acc),
        "surfaces": dict(acc.surfaces),
        "candidate_types": dict(acc.candidate_types),
        "lookup_row": _inventory_row(acc),
    }


def _accumulator_from_checkpoint_row(row: Mapping[str, Any]) -> ActionAccumulator:
    lookup_row = {
        field: str((row.get("lookup_row") or {}).get(field, ""))
        for field in FIELDNAMES
    }
    lookup = None
    if lookup_row.get("selected_lookup_case") != "raw_fallback":
        lookup = _action_lookup_result_from_inventory_row(lookup_row)
    return ActionAccumulator(
        span_key=str(row.get("span_key", "")),
        count=int(row.get("count") or 0),
        caption_count_base=int(row.get("caption_count_base") or 0),
        caption_id_examples=set(str(item) for item in row.get("caption_id_examples", [])),
        surfaces=Counter({str(key): int(value) for key, value in row.get("surfaces", {}).items()}),
        candidate_types=Counter(
            {str(key): int(value) for key, value in row.get("candidate_types", {}).items()}
        ),
        lookup=lookup,
    )


def _build_action_lookup(
    action_inventory_path: str | None,
    runtime_action_lookup: Any,
) -> Any:
    prior_lookup = (
        load_gpic_action_inventory(action_inventory_path)
        if action_inventory_path
        else None
    )

    def lookup(surface: str) -> _ActionLookupResult | None:
        if prior_lookup is not None:
            prior = prior_lookup(surface)
            if prior is not None and _is_reusable_prior_action_lookup(prior):
                return prior
        runtime = _lookup_oewn_verb_synsets(
            surface,
            runtime_action_lookup["oewn"],
            runtime_action_lookup["morphy"],
        )
        if prior_lookup is not None:
            prior_by_query = _reuse_prior_selected_query_decision(
                runtime_lookup=runtime,
                prior_lookup=prior_lookup,
            )
            if prior_by_query is not None:
                return prior_by_query
        return runtime

    return lookup


def _reuse_prior_selected_query_decision(
    *,
    runtime_lookup: _ActionLookupResult,
    prior_lookup: Any,
) -> _ActionLookupResult | None:
    matches: list[tuple[str, _ActionLookupResult]] = []
    for query in _selected_query_reuse_candidates(runtime_lookup.query):
        prior = prior_lookup.lookup_selected_query(query)
        if prior is not None and _is_reusable_prior_action_lookup(prior):
            matches.append((query, prior))
    if not matches:
        return None

    selected_ids = {
        str(prior.selected_synset.id)
        for _, prior in matches
        if prior.selected_synset is not None
    }
    if len(selected_ids) != 1:
        return None
    selected_id = next(iter(selected_ids))
    selected = next(
        (synset for synset in runtime_lookup.synsets if str(synset.id) == selected_id),
        None,
    )
    if selected is None:
        return None
    selected_query = next(
        query
        for query, prior in matches
        if prior.selected_synset is not None
        and str(prior.selected_synset.id) == selected_id
    )
    return _ActionLookupResult(
        lookup_case=f"{runtime_lookup.lookup_case}_prior_selected_query",
        query=selected_query,
        synsets=runtime_lookup.synsets,
        selected_synset=selected,
        synset_selection_tag="selected_by_prior_action_selected_query",
        wn30_lemma_counts=runtime_lookup.wn30_lemma_counts,
        decision_status="chosen",
        decision_reason="prior_action_selected_query_reused",
    )


def _selected_query_reuse_candidates(query: str) -> tuple[str, ...]:
    return tuple(part for part in (_normalize_query(part) for part in query.split("|")) if part)


def _is_reusable_prior_action_lookup(lookup: _ActionLookupResult) -> bool:
    if lookup.decision_status == "chosen":
        return lookup.selected_synset is not None
    if lookup.decision_status == "raw_fallback":
        return lookup.selected_synset is None
    return False


def build_action_inventory_rows(
    records: Iterable[Mapping[str, Any]],
    *,
    action_lookup: Any,
    preposition_mwe_lookup: Any | None = None,
    progress_writer: ActionInventoryProgressWriter | None = None,
    checkpoint_writer: ActionInventoryCheckpointWriter | None = None,
    initial_inventory: Mapping[str, ActionAccumulator] | None = None,
    initial_caption_total: int = 0,
    initial_verb_token_total: int = 0,
    initial_relation_mwe_match_total: int = 0,
    initial_relation_mwe_consumed_token_total: int = 0,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    inventory: dict[str, ActionAccumulator] = dict(initial_inventory or {})
    caption_total = initial_caption_total
    verb_token_total = initial_verb_token_total
    relation_mwe_match_total = initial_relation_mwe_match_total
    relation_mwe_consumed_token_total = initial_relation_mwe_consumed_token_total

    for record in records:
        caption_total += 1
        caption_id = str(record.get("caption_id", ""))
        tokens = tuple(record.get("tokens", ()))
        children_by_head = _build_children_by_head(tokens)
        relation_mwe_matches = _find_preposition_mwe_matches_in_token_records(
            tokens,
            preposition_mwe_lookup,
        )
        relation_mwe_consumed_tokens = {
            token_i for match in relation_mwe_matches for token_i in match.token_indices
        }
        relation_mwe_match_total += len(relation_mwe_matches)
        relation_mwe_consumed_token_total += len(relation_mwe_consumed_tokens)
        for token in tokens:
            if _optional_text(token, "pos") != "VERB":
                continue
            verb_token_total += 1
            candidate, lookup = _select_inventory_action_candidate(
                _action_candidates_from_token_record(
                    token,
                    children_by_head=children_by_head,
                    excluded_token_indices=relation_mwe_consumed_tokens,
                ),
                action_lookup,
            )
            span_key = _normalize_query(candidate.text)
            if not span_key:
                continue
            acc = inventory.setdefault(span_key, ActionAccumulator(span_key=span_key))
            acc.count += 1
            if caption_id:
                acc.caption_ids.add(caption_id)
            acc.surfaces[candidate.text] += 1
            acc.candidate_types[candidate.candidate_type] += 1
            if acc.lookup is None or _lookup_rank(lookup) > _lookup_rank(acc.lookup):
                acc.lookup = lookup
        if progress_writer is not None:
            progress_writer.maybe_write(
                caption_total=caption_total,
                verb_token_total=verb_token_total,
                relation_mwe_match_total=relation_mwe_match_total,
                relation_mwe_consumed_token_total=relation_mwe_consumed_token_total,
                inventory_rows_so_far=len(inventory),
            )
        if checkpoint_writer is not None:
            checkpoint_writer.maybe_write(
                caption_total=caption_total,
                verb_token_total=verb_token_total,
                relation_mwe_match_total=relation_mwe_match_total,
                relation_mwe_consumed_token_total=relation_mwe_consumed_token_total,
                inventory=inventory,
            )

    rows = [_inventory_row(acc) for acc in inventory.values()]
    rows.sort(key=lambda row: (-int(row["count"]), row["span_key"]))
    summary = {
        "caption_total": caption_total,
        "verb_token_total": verb_token_total,
        "relation_mwe_match_total": relation_mwe_match_total,
        "relation_mwe_consumed_token_total": relation_mwe_consumed_token_total,
        "inventory_rows": len(rows),
        "decision_status_counts": dict(Counter(row["decision_status"] for row in rows)),
        "decision_reason_counts": dict(Counter(row["decision_reason"] for row in rows)),
        "candidate_type_counts": dict(
            Counter(
                part
                for row in rows
                for part in row["candidate_types"].split("|")
                if part
            )
        ),
    }
    return rows, summary


def _select_inventory_action_candidate(
    candidates: Sequence[_ActionSpanCandidate],
    action_lookup: Any,
) -> tuple[_ActionSpanCandidate, _ActionLookupResult | None]:
    if not candidates:
        raise ValueError("action candidate list must not be empty")
    valid: list[tuple[_ActionSpanCandidate, _ActionLookupResult]] = []
    for candidate in candidates:
        lookup = _lookup_action_candidate(candidate, action_lookup)
        if lookup is not None and lookup.synsets:
            valid.append((candidate, lookup))
    if not valid:
        return candidates[0], None
    return min(
        valid,
        key=lambda item: (
            -len(item[0].token_indices),
            _action_candidate_priority(item[0].candidate_type),
            item[0].token_indices,
        ),
    )


def _inventory_row(acc: ActionAccumulator) -> dict[str, str]:
    lookup = acc.lookup
    selected = lookup.selected_synset if lookup is not None else None
    decision_status = lookup.decision_status if lookup is not None else "raw_fallback"
    decision_reason = lookup.decision_reason if lookup is not None else "no_oewn_verb_synset"
    selected_query = lookup.query if lookup is not None and lookup.query else acc.span_key
    return {
        "span_key": acc.span_key,
        "observed_surface": _top_counter_key(acc.surfaces),
        "decision_status": decision_status,
        "decision_reason": decision_reason,
        "count": str(acc.count),
        "caption_count": str(_caption_count(acc)),
        "example_caption_ids": "|".join(_example_caption_ids(acc)),
        "example_surfaces": "|".join(_counter_keys(acc.surfaces, 5)),
        "candidate_types": "|".join(_counter_keys(acc.candidate_types, 10)),
        "selected_lookup_case": lookup.lookup_case if lookup is not None else "raw_fallback",
        "selected_query": selected_query,
        "has_oewn_verb_synset": "true" if lookup is not None and lookup.synsets else "false",
        "oewn_synset_count": str(len(lookup.synsets) if lookup is not None else 0),
        "selected_oewn_synset": selected.id if selected is not None else "",
        "selected_oewn_lexfile": selected.lexfile() if selected is not None else "",
        "synset_lemmas": "|".join(selected.lemmas()) if selected is not None else "",
        "canonical_surface": "",
        "canonical_label_key": "",
        "canonical_selection_tag": "",
        "canonical_candidate_lemmas": "",
        "canonical_candidate_lemma_counts": "",
        "google_ngram_candidate_surfaces": "",
        "google_ngram_candidate_mean_frequencies": "",
        "all_oewn_synsets": "|".join(s.id for s in lookup.synsets) if lookup is not None else "",
        "all_oewn_lexfiles": "|".join(s.lexfile() for s in lookup.synsets)
        if lookup is not None
        else "",
        "synset_selection_tag": lookup.synset_selection_tag
        if lookup is not None
        else "unresolved_no_oewn_verb_synset",
        "wn30_lemma_counts": lookup.wn30_lemma_counts if lookup is not None else "",
        "decision_basis": "gpic_observed_action_inventory",
    }


def _caption_count(acc: ActionAccumulator) -> int:
    return acc.caption_count_base + len(acc.caption_ids)


def _example_caption_ids(acc: ActionAccumulator) -> list[str]:
    return sorted(acc.caption_id_examples | acc.caption_ids)[:5]


def _lookup_rank(lookup: _ActionLookupResult | None) -> int:
    if lookup is None:
        return 0
    if lookup.selected_synset is not None:
        return 3
    if lookup.synsets:
        return 2
    return 1


def _counter_keys(counter: Counter[str], limit: int) -> list[str]:
    return [value for value, _ in counter.most_common(limit)]


def _top_counter_key(counter: Counter[str]) -> str:
    keys = _counter_keys(counter, 1)
    return keys[0] if keys else ""


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
