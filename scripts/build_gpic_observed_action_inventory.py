from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.io_jsonl import iter_jsonl
from gpic_concepts_v1.stage4_extract_raw import (
    _ActionLookupResult,
    _ActionSpanCandidate,
    _action_candidate_priority,
    _action_candidates_from_token_record,
    _build_children_by_head,
    _load_object_lookup_runtime,
    _lookup_action_candidate,
    _normalize_query,
    _optional_text,
    _require_int,
    _token_text,
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
    caption_ids: set[str] = field(default_factory=set)
    surfaces: Counter[str] = field(default_factory=Counter)
    candidate_types: Counter[str] = field(default_factory=Counter)
    lookup: _ActionLookupResult | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a GPIC-observed action inventory from Stage 3 records.",
    )
    parser.add_argument("--input", required=True, help="Input stage3_records.jsonl")
    parser.add_argument("--output", required=True, help="Output observed action inventory TSV")
    parser.add_argument(
        "--needs-manual-output",
        help="Optional TSV containing only decision_status=needs_manual rows",
    )
    parser.add_argument("--summary", help="Optional summary JSON path")
    parser.add_argument("--limit", type=int, help="Optional maximum Stage 3 records to scan")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    action_lookup = _load_object_lookup_runtime()
    if action_lookup is None:
        raise SystemExit("OEWN runtime lookup is unavailable.")

    records = _limited_records(iter_jsonl(args.input), args.limit)
    rows, summary = build_action_inventory_rows(records, action_lookup=action_lookup)
    _write_tsv(Path(args.output), rows)
    if args.needs_manual_output:
        _write_tsv(
            Path(args.needs_manual_output),
            [row for row in rows if row["decision_status"] == "needs_manual"],
        )
    summary.update(
        {
            "input": args.input,
            "output": args.output,
            "needs_manual_output": args.needs_manual_output or "",
        }
    )
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def build_action_inventory_rows(
    records: Iterable[Mapping[str, Any]],
    *,
    action_lookup: Any,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    inventory: dict[str, ActionAccumulator] = {}
    caption_total = 0
    verb_token_total = 0

    for record in records:
        caption_total += 1
        caption_id = str(record.get("caption_id", ""))
        tokens = tuple(record.get("tokens", ()))
        children_by_head = _build_children_by_head(tokens)
        for token in tokens:
            if _optional_text(token, "pos") != "VERB":
                continue
            verb_token_total += 1
            candidate, lookup = _select_inventory_action_candidate(
                _action_candidates_from_token_record(token, children_by_head=children_by_head),
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

    rows = [_inventory_row(acc) for acc in inventory.values()]
    rows.sort(key=lambda row: (-int(row["count"]), row["span_key"]))
    summary = {
        "caption_total": caption_total,
        "verb_token_total": verb_token_total,
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
        "caption_count": str(len(acc.caption_ids)),
        "example_caption_ids": "|".join(sorted(acc.caption_ids)[:5]),
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


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(handle, FIELDNAMES, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
