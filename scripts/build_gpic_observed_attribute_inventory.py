from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
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
    ATTRIBUTE_MODIFIER_DEPS,
    NLTK_DATA_DIR,
    OEWN_SPEC,
    WN_DATA_DIR,
    _chunk_tokens,
    _is_allowed_token_record_span_start,
    _normalize_query,
    _object_core_token_indices_from_token_records,
    _probe_object_surface,
    _require_int,
    _select_by_wn30_lemma_count,
    _token_record_span_lookup_surfaces,
    _token_record_span_text,
    _token_text,
    load_gpic_object_inventory,
    nltk,
    wn,
)

try:  # pragma: no cover - exercised when runtime OEWN dependencies exist.
    from wn.morphy import Morphy
except ModuleNotFoundError:  # pragma: no cover - keeps lightweight tests importable.
    Morphy = Any  # type: ignore[misc,assignment]


ATTRIBUTE_COMPATIBLE_LEXFILES = frozenset(
    (
        "adj.all",
        "adj.pert",
        "adj.ppl",
        "noun.attribute",
        "noun.shape",
        "noun.state",
        "noun.substance",
    )
)
CONDITIONAL_ATTRIBUTE_LEXFILES = frozenset(
    (
        "noun.Tops",
        "noun.act",
        "noun.animal",
        "noun.artifact",
        "noun.body",
        "noun.cognition",
        "noun.communication",
        "noun.event",
        "noun.food",
        "noun.group",
        "noun.location",
        "noun.object",
        "noun.person",
        "noun.phenomenon",
        "noun.plant",
        "noun.possession",
        "noun.process",
        "noun.quantity",
        "noun.relation",
        "noun.time",
        "verb.body",
        "verb.change",
        "verb.cognition",
        "verb.communication",
        "verb.competition",
        "verb.consumption",
        "verb.contact",
        "verb.creation",
        "verb.emotion",
        "verb.motion",
        "verb.perception",
        "verb.possession",
        "verb.social",
        "verb.stative",
        "verb.weather",
    )
)
HARD_CONFLICT_ATTRIBUTE_LEXFILES = frozenset(("adv.all", "noun.feeling", "noun.motive"))

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
    "has_oewn_attribute_synset",
    "oewn_synset_count",
    "selected_oewn_synset",
    "selected_oewn_lexfile",
    "attribute_gate",
    "synset_lemmas",
    "canonical_surface",
    "canonical_label_key",
    "canonical_selection_tag",
    "canonical_candidate_lemmas",
    "canonical_candidate_lemma_counts",
    "google_ngram_candidate_surfaces",
    "google_ngram_candidate_mean_frequencies",
    "attribute_parent",
    "attribute_parent_selection_tag",
    "all_oewn_synsets",
    "all_oewn_lexfiles",
    "synset_selection_tag",
    "wn30_lemma_counts",
    "decision_basis",
]

ATTRIBUTE_MORPHY_POS = ("a", "n", "v", "r")


@dataclass(frozen=True, slots=True)
class AttributeLookupResult:
    lookup_case: str
    query: str
    synsets: tuple[Any, ...]
    selected_synset: Any | None
    synset_selection_tag: str
    wn30_lemma_counts: str
    attribute_gate: str
    decision_status: str
    decision_reason: str


@dataclass(frozen=True, slots=True)
class _InventorySynset:
    id: str
    _lexfile: str
    _lemmas: tuple[str, ...]

    def lexfile(self) -> str:
        return self._lexfile

    def lemmas(self) -> list[str]:
        return list(self._lemmas)


@dataclass(slots=True)
class AttributeAccumulator:
    span_key: str
    count: int = 0
    caption_ids: set[str] = field(default_factory=set)
    surfaces: Counter[str] = field(default_factory=Counter)
    lookup: AttributeLookupResult | None = None


class GpicAttributeInventoryLookup:
    """Lookup prior attribute inventory rows by normalized observed surface."""

    def __init__(self, rows_by_key: Mapping[str, Mapping[str, str]]) -> None:
        self._rows_by_key = dict(rows_by_key)

    @classmethod
    def from_tsv(cls, path: str | Path) -> "GpicAttributeInventoryLookup":
        rows_by_key: dict[str, Mapping[str, str]] = {}
        with Path(path).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                span_key = row.get("span_key", "") or _normalize_query(
                    row.get("observed_surface", "")
                )
                if span_key and span_key not in rows_by_key:
                    rows_by_key[span_key] = dict(row)
        return cls(rows_by_key)

    def __call__(self, surface: str) -> AttributeLookupResult | None:
        row = self._rows_by_key.get(_normalize_query(surface))
        if row is None:
            return None
        synsets = _inventory_synsets(row)
        selected = _inventory_selected_synset(row, synsets)
        attribute_gate = row.get("attribute_gate", "")
        if selected is not None and not attribute_gate:
            attribute_gate = _attribute_gate_for_lexfile(selected.lexfile())
        decision_status = row.get("decision_status", "")
        if decision_status == "no_synset":
            decision_status = "chosen"
        if not decision_status:
            decision_status = _attribute_decision_status(
                selected_synset=selected,
                synsets=synsets,
                attribute_gate=attribute_gate,
            )
        decision_reason = row.get("decision_reason", "")
        if not decision_reason:
            decision_reason = _attribute_decision_reason(
                selected_synset=selected,
                synsets=synsets,
                attribute_gate=attribute_gate,
            )
        return AttributeLookupResult(
            row.get("selected_lookup_case", "inventory"),
            row.get("selected_query", surface),
            tuple(synsets),
            selected,
            row.get("synset_selection_tag", "inventory_selected_synset"),
            row.get("wn30_lemma_counts", ""),
            attribute_gate,
            decision_status,
            decision_reason,
        )


AttributeLookup = Callable[[str], AttributeLookupResult | None]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a GPIC-observed attribute inventory from Stage 3 records.",
    )
    parser.add_argument("--input", required=True, help="Input stage3_records.jsonl")
    parser.add_argument(
        "--object-inventory",
        required=True,
        help="Resolved GPIC observed object inventory TSV used to find consumed object spans",
    )
    parser.add_argument(
        "--attribute-inventory",
        help="Optional prior attribute inventory TSV. Selected synsets in this file are reused.",
    )
    parser.add_argument("--output", required=True, help="Output observed attribute inventory TSV")
    parser.add_argument("--summary", help="Optional summary JSON path")
    parser.add_argument("--limit", type=int, help="Optional maximum Stage 3 records to scan")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    object_lookup = load_gpic_object_inventory(args.object_inventory)
    attribute_lookup = _build_attribute_lookup(args.attribute_inventory)

    records = _limited_records(iter_jsonl(args.input), args.limit)
    rows, summary = build_attribute_inventory_rows(
        records,
        object_lookup=object_lookup,
        attribute_lookup=attribute_lookup,
    )
    _write_tsv(Path(args.output), rows)
    summary.update({"input": args.input, "output": args.output})
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def build_attribute_inventory_rows(
    records: Iterable[Mapping[str, Any]],
    *,
    object_lookup: Any,
    attribute_lookup: AttributeLookup,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    inventory: dict[str, AttributeAccumulator] = {}
    caption_total = 0
    noun_chunk_total = 0
    attribute_candidate_total = 0

    for record in records:
        caption_total += 1
        caption_id = str(record.get("caption_id", ""))
        token_by_i = {_require_int(token, "i"): token for token in record.get("tokens", [])}
        for chunk in record.get("noun_chunks", []):
            noun_chunk_total += 1
            consumed = _selected_object_token_indices(chunk, token_by_i, object_lookup)
            if not consumed:
                continue
            for token in _chunk_tokens(chunk, token_by_i):
                token_i = _require_int(token, "i")
                if token_i in consumed:
                    continue
                if token.get("dep") not in ATTRIBUTE_MODIFIER_DEPS:
                    continue
                surface = _token_text(token)
                span_key = _normalize_query(surface)
                if not span_key:
                    continue
                attribute_candidate_total += 1
                acc = inventory.setdefault(span_key, AttributeAccumulator(span_key=span_key))
                acc.count += 1
                if caption_id:
                    acc.caption_ids.add(caption_id)
                acc.surfaces[surface] += 1
                lookup = attribute_lookup(surface)
                if acc.lookup is None or _lookup_rank(lookup) > _lookup_rank(acc.lookup):
                    acc.lookup = lookup

    rows = [_inventory_row(acc) for acc in inventory.values()]
    rows.sort(key=lambda row: (-int(row["count"]), row["span_key"]))
    summary = {
        "caption_total": caption_total,
        "noun_chunk_total": noun_chunk_total,
        "attribute_candidate_total": attribute_candidate_total,
        "inventory_rows": len(rows),
        "decision_status_counts": dict(Counter(row["decision_status"] for row in rows)),
        "decision_reason_counts": dict(Counter(row["decision_reason"] for row in rows)),
        "attribute_gate_counts": dict(Counter(row["attribute_gate"] for row in rows)),
    }
    return rows, summary


def _selected_object_token_indices(
    chunk: Mapping[str, Any],
    token_by_i: Mapping[int, Mapping[str, Any]],
    object_lookup: Any,
) -> set[int]:
    tokens = _chunk_tokens(chunk, token_by_i)
    if not tokens:
        return set()
    root_i = _require_int(chunk, "root_i")
    root_pos = next(
        (index for index, token in enumerate(tokens) if _require_int(token, "i") == root_i),
        None,
    )
    if root_pos is None:
        return set()
    for start_pos in range(0, root_pos + 1):
        span_tokens = tokens[start_pos : root_pos + 1]
        if len(span_tokens) > 1 and not _is_allowed_token_record_span_start(span_tokens[0]):
            continue
        lookup = _probe_object_surface(
            _token_record_span_lookup_surfaces(span_tokens),
            object_lookup,
        )
        if lookup is not None:
            return set(_object_core_token_indices_from_token_records(span_tokens, lookup))
    return set()


def _build_attribute_lookup(attribute_inventory_path: str | None) -> AttributeLookup:
    existing_lookup = (
        GpicAttributeInventoryLookup.from_tsv(attribute_inventory_path)
        if attribute_inventory_path
        else None
    )
    runtime_lookup = _load_attribute_lookup_runtime()

    def lookup(surface: str) -> AttributeLookupResult | None:
        existing = existing_lookup(surface) if existing_lookup is not None else None
        if existing is not None and existing.selected_synset is not None:
            return existing
        return runtime_lookup(surface)

    return lookup


def _load_attribute_lookup_runtime() -> AttributeLookup:
    if wn is None:
        raise RuntimeError("OEWN runtime lookup is unavailable; cannot build GPIC attribute inventory")
    wn.config.data_directory = str(WN_DATA_DIR)
    if nltk is not None:
        nltk.data.path.insert(0, str(NLTK_DATA_DIR))
    oewn = wn.Wordnet(OEWN_SPEC, expand="")
    morphy = Morphy(oewn)

    def lookup(surface: str) -> AttributeLookupResult | None:
        return _lookup_attribute_surface(surface, oewn=oewn, morphy=morphy)

    return lookup


def _lookup_attribute_surface(surface: str, *, oewn: Any, morphy: Any) -> AttributeLookupResult:
    exact = _normalize_query(surface)
    if exact:
        synsets = tuple(oewn.synsets(exact))
        if synsets:
            return _with_selected_attribute_synset("exact", exact, synsets)
    for case, query in _morphy_attribute_queries(exact, morphy):
        synsets = tuple(oewn.synsets(query))
        if synsets:
            return _with_selected_attribute_synset(case, query, synsets)
    return AttributeLookupResult(
        "unresolved",
        exact,
        (),
        None,
        "unresolved_no_oewn_attribute_synset",
        "",
        "",
        "chosen",
        "no_oewn_attribute_synset",
    )


def _morphy_attribute_queries(query: str, morphy: Any) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = []
    seen: set[str] = set()
    if not query:
        return queries
    for pos in ATTRIBUTE_MORPHY_POS:
        result = morphy(query, pos)
        lemmas = result.get(pos, set()) if result else set()
        for lemma in sorted(lemmas):
            normalized = _normalize_query(str(lemma))
            if normalized and normalized not in seen:
                queries.append((f"morphy_{pos}", normalized))
                seen.add(normalized)
    return queries


def _with_selected_attribute_synset(
    lookup_case: str,
    query: str,
    synsets: tuple[Any, ...],
) -> AttributeLookupResult:
    selected, tag, counts = _select_attribute_synset(list(synsets), query)
    attribute_gate = (
        _attribute_gate_for_lexfile(selected.lexfile()) if selected is not None else ""
    )
    return AttributeLookupResult(
        lookup_case,
        query,
        synsets,
        selected,
        tag,
        counts,
        attribute_gate,
        _attribute_decision_status(
            selected_synset=selected,
            synsets=synsets,
            attribute_gate=attribute_gate,
        ),
        _attribute_decision_reason(
            selected_synset=selected,
            synsets=synsets,
            attribute_gate=attribute_gate,
        ),
    )


def _select_attribute_synset(synsets: list[Any], query: str) -> tuple[Any | None, str, str]:
    if not synsets:
        return None, "unresolved_no_oewn_attribute_synset", ""
    if len(synsets) == 1:
        return synsets[0], "single_oewn_attribute_synset", ""

    compatible = [s for s in synsets if s.lexfile() in ATTRIBUTE_COMPATIBLE_LEXFILES]
    conditional = [s for s in synsets if s.lexfile() in CONDITIONAL_ATTRIBUTE_LEXFILES]
    other = [s for s in synsets if s not in compatible and s not in conditional]

    evidence: list[str] = []
    for group_name, group_synsets, stop_on_tie in (
        ("attribute_compatible", compatible, True),
        ("conditional", conditional, True),
        ("other", other, True),
    ):
        if not group_synsets:
            continue
        selected, tag, counts = _select_by_wn30_lemma_count(group_synsets, query)
        if counts:
            evidence.append(f"{group_name}:{counts}")
        if selected is not None:
            return selected, f"selected_by_wn30_{group_name}_lemma_count", "|".join(evidence)
        if stop_on_tie and tag == "wn30_tie":
            return None, f"ambiguous_{group_name}_wn30_tie", "|".join(evidence)

    return None, "ambiguous_wn30_all_zero_or_mapping_missing", "|".join(evidence)


def _attribute_gate_for_lexfile(lexfile: str) -> str:
    if lexfile in ATTRIBUTE_COMPATIBLE_LEXFILES:
        return "attribute_compatible"
    if lexfile in CONDITIONAL_ATTRIBUTE_LEXFILES:
        return "conditional"
    if lexfile in HARD_CONFLICT_ATTRIBUTE_LEXFILES or lexfile:
        return "hard_conflict"
    return ""


def _attribute_decision_status(
    *,
    selected_synset: Any | None,
    synsets: Sequence[Any],
    attribute_gate: str,
) -> str:
    if selected_synset is None:
        return "needs_manual" if synsets else "chosen"
    if attribute_gate == "attribute_compatible":
        return "chosen"
    return "needs_manual"


def _attribute_decision_reason(
    *,
    selected_synset: Any | None,
    synsets: Sequence[Any],
    attribute_gate: str,
) -> str:
    if selected_synset is None:
        return "manual_synset_required" if synsets else "no_oewn_attribute_synset"
    if attribute_gate == "attribute_compatible":
        return "selected_attribute_compatible"
    return "manual_attribute_gate_required"


def _inventory_synsets(row: Mapping[str, str]) -> tuple[_InventorySynset, ...]:
    synset_ids = _split_pipe(row.get("all_oewn_synsets", ""))
    lexfiles = _split_pipe(row.get("all_oewn_lexfiles", ""))
    if not synset_ids and row.get("selected_oewn_synset"):
        synset_ids = [row["selected_oewn_synset"]]
        lexfiles = [row.get("selected_oewn_lexfile", "")]
    selected_lemmas = tuple(_split_pipe(row.get("synset_lemmas", "")))
    synsets: list[_InventorySynset] = []
    for index, synset_id in enumerate(synset_ids):
        lexfile = lexfiles[index] if index < len(lexfiles) else ""
        lemmas = selected_lemmas if synset_id == row.get("selected_oewn_synset") else ()
        synsets.append(_InventorySynset(synset_id, lexfile, lemmas))
    return tuple(synsets)


def _inventory_selected_synset(
    row: Mapping[str, str],
    synsets: Sequence[_InventorySynset],
) -> _InventorySynset | None:
    selected_id = row.get("selected_oewn_synset", "")
    if not selected_id:
        return None
    for synset in synsets:
        if synset.id == selected_id:
            return synset
    return _InventorySynset(
        selected_id,
        row.get("selected_oewn_lexfile", ""),
        tuple(_split_pipe(row.get("synset_lemmas", ""))),
    )


def _inventory_row(acc: AttributeAccumulator) -> dict[str, str]:
    lookup = acc.lookup
    selected = lookup.selected_synset if lookup is not None else None
    return {
        "span_key": acc.span_key,
        "observed_surface": acc.surfaces.most_common(1)[0][0] if acc.surfaces else acc.span_key,
        "decision_status": lookup.decision_status if lookup is not None else "chosen",
        "decision_reason": lookup.decision_reason if lookup is not None else "no_oewn_attribute_synset",
        "count": str(acc.count),
        "caption_count": str(len(acc.caption_ids)),
        "example_caption_ids": "|".join(sorted(acc.caption_ids)[:5]),
        "example_surfaces": "|".join(surface for surface, _ in acc.surfaces.most_common(5)),
        "selected_lookup_case": lookup.lookup_case if lookup is not None else "unresolved",
        "selected_query": lookup.query if lookup is not None else "",
        "has_oewn_attribute_synset": "true" if lookup is not None and lookup.synsets else "false",
        "oewn_synset_count": str(len(lookup.synsets) if lookup is not None else 0),
        "selected_oewn_synset": selected.id if selected is not None else "",
        "selected_oewn_lexfile": selected.lexfile() if selected is not None else "",
        "attribute_gate": lookup.attribute_gate if lookup is not None else "",
        "synset_lemmas": "|".join(selected.lemmas()) if selected is not None else "",
        "canonical_surface": "",
        "canonical_label_key": "",
        "canonical_selection_tag": "",
        "canonical_candidate_lemmas": "",
        "canonical_candidate_lemma_counts": "",
        "google_ngram_candidate_surfaces": "",
        "google_ngram_candidate_mean_frequencies": "",
        "attribute_parent": "",
        "attribute_parent_selection_tag": "",
        "all_oewn_synsets": "|".join(s.id for s in lookup.synsets) if lookup is not None else "",
        "all_oewn_lexfiles": "|".join(s.lexfile() for s in lookup.synsets) if lookup is not None else "",
        "synset_selection_tag": lookup.synset_selection_tag
        if lookup is not None
        else "unresolved_no_oewn_attribute_synset",
        "wn30_lemma_counts": lookup.wn30_lemma_counts if lookup is not None else "",
        "decision_basis": "gpic_observed_attribute_inventory",
    }


def _lookup_rank(lookup: AttributeLookupResult | None) -> int:
    if lookup is None:
        return 0
    if lookup.selected_synset is not None:
        return 3
    if lookup.synsets:
        return 2
    return 1


def _limited_records(records: Iterable[Mapping[str, Any]], limit: int | None) -> Iterable[Mapping[str, Any]]:
    for index, record in enumerate(records):
        if limit is not None and index >= limit:
            break
        yield record


def _split_pipe(value: str) -> list[str]:
    return [part for part in value.split("|") if part]


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(handle, FIELDNAMES, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
