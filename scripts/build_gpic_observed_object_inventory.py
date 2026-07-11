from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
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
    _ObjectLookupResult,
    _chunk_tokens,
    _decision_reason_for_selection,
    _decision_status_for_selection,
    _is_allowed_token_record_span_start,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a GPIC-observed object span inventory from Stage 3 records. "
            "This does not read COCO/LVIS/Objects365/OpenImages/Visual Genome."
        ),
    )
    parser.add_argument("--input", required=True, help="Input stage3_records.jsonl")
    parser.add_argument("--output", required=True, help="Output observed object inventory TSV")
    parser.add_argument("--summary", help="Optional summary JSON path")
    parser.add_argument("--limit", type=int, help="Optional maximum Stage 3 records to scan")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    object_lookup = _load_object_lookup_runtime()
    if object_lookup is None:
        raise RuntimeError("OEWN runtime lookup is unavailable; cannot build GPIC object inventory")

    inventory: dict[str, SpanAccumulator] = {}
    caption_total = 0
    noun_chunk_total = 0
    for index, record in enumerate(iter_jsonl(args.input)):
        if args.limit is not None and index >= args.limit:
            break
        caption_total += 1
        caption_id = str(record.get("caption_id", ""))
        token_by_i = {_require_int(token, "i"): token for token in record.get("tokens", [])}
        for chunk in record.get("noun_chunks", []):
            noun_chunk_total += 1
            surface, lookup = _select_inventory_span(chunk, token_by_i, object_lookup)
            if not surface:
                continue
            span_key = _normalize_query(surface)
            acc = inventory.setdefault(span_key, SpanAccumulator(span_key=span_key))
            acc.count += 1
            if caption_id:
                acc.caption_ids.add(caption_id)
            acc.surfaces[surface] += 1
            if acc.lookup is None or _lookup_rank(lookup) > _lookup_rank(acc.lookup):
                acc.lookup = lookup

    rows = [_inventory_row(acc) for acc in inventory.values()]
    rows.sort(key=lambda row: (-int(row["count"]), row["span_key"]))
    _write_tsv(Path(args.output), rows)

    summary = {
        "input": args.input,
        "output": args.output,
        "caption_total": caption_total,
        "noun_chunk_total": noun_chunk_total,
        "inventory_rows": len(rows),
        "decision_status_counts": dict(Counter(row["decision_status"] for row in rows)),
        "decision_reason_counts": dict(Counter(row["decision_reason"] for row in rows)),
    }
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _select_inventory_span(
    chunk: dict[str, Any],
    token_by_i: dict[int, dict[str, Any]],
    object_lookup: Any,
) -> tuple[str, _ObjectLookupResult | None]:
    tokens = _chunk_tokens(chunk, token_by_i)
    if not tokens:
        return "", None
    root_i = _require_int(chunk, "root_i")
    root_pos = next((index for index, token in enumerate(tokens) if _require_int(token, "i") == root_i), None)
    if root_pos is None:
        return "", None
    for start_pos in range(0, root_pos + 1):
        span_tokens = tokens[start_pos : root_pos + 1]
        if len(span_tokens) > 1 and not _is_allowed_token_record_span_start(span_tokens[0]):
            continue
        surfaces = _token_record_span_lookup_surfaces(span_tokens)
        lookup = _probe_object_surface(surfaces, object_lookup)
        if lookup is not None and lookup.synsets:
            return _token_record_span_text(span_tokens), lookup
    root_surface = _token_record_span_text(tokens[root_pos : root_pos + 1])
    return root_surface, None


def _lookup_rank(lookup: _ObjectLookupResult | None) -> int:
    if lookup is None:
        return 0
    if lookup.selected_synset is not None:
        return 2
    if lookup.synsets:
        return 1
    return 0


def _inventory_row(acc: SpanAccumulator) -> dict[str, str]:
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


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(handle, FIELDNAMES, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
