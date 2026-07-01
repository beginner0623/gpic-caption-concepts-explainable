"""Stage 5 canonicalization.

Stage 5 consumes Stage 4 raw mentions and raw edges. It only applies the
documented v1 canonicalization rules R19-R24:

- object synonym lookup
- attribute synonym and type lookup
- quantity raw-preserving
- action synonym lookup
- parent concept lookup
- relation raw-preserving

It does not create new mentions, rewrite source/target IDs, resolve references,
or repair event roles.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import csv
from pathlib import Path
from typing import Any

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import (
    CanonicalEdge,
    CanonicalMention,
    JsonObject,
    RawEdge,
    RawMention,
)


OBJECT_CANON_RULE_ID = "R19"
ATTRIBUTE_CANON_RULE_ID = "R20"
QUANTITY_CANON_RULE_ID = "R21"
ACTION_CANON_RULE_ID = "R22"
PARENT_RULE_ID = "R23"
RELATION_CANON_RULE_ID = "R24"


@dataclass(frozen=True, slots=True)
class LexiconValue:
    value: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class Stage5Lexicons:
    object_synonyms: Mapping[str, LexiconValue]
    object_parents: Mapping[str, tuple[LexiconValue, ...]]
    attribute_synonyms: Mapping[str, LexiconValue]
    attribute_types: Mapping[str, LexiconValue]
    action_synonyms: Mapping[str, LexiconValue]
    action_parents: Mapping[str, tuple[LexiconValue, ...]]


@dataclass(slots=True)
class CanonicalizationResult:
    canonical_mentions: list[CanonicalMention]
    canonical_edges: list[CanonicalEdge]


def load_stage5_lexicons(lexicon_dir: str | Path) -> Stage5Lexicons:
    """Load explicit Stage 5 TSV lexicons."""
    root = Path(lexicon_dir)
    return Stage5Lexicons(
        object_synonyms=_load_value_map(root / "object_synonyms.tsv", "raw", "canonical"),
        object_parents=_load_multi_value_map(root / "object_parents.tsv", "canonical", "parent"),
        attribute_synonyms=_load_value_map(root / "attribute_synonyms.tsv", "raw", "canonical"),
        attribute_types=_load_value_map(root / "attribute_types.tsv", "canonical", "attribute_type"),
        action_synonyms=_load_value_map(root / "action_synonyms.tsv", "raw", "canonical"),
        action_parents=_load_multi_value_map(root / "action_parents.tsv", "canonical", "parent"),
    )


def canonicalize_raw_graph(
    raw_mentions: Sequence[Mapping[str, Any] | RawMention],
    raw_edges: Sequence[Mapping[str, Any] | RawEdge],
    *,
    lexicons: Stage5Lexicons,
) -> CanonicalizationResult:
    """Canonicalize raw Stage 4 mentions and edges without changing graph shape."""
    raw_mention_records = [_coerce_raw_mention(record) for record in raw_mentions]
    raw_edge_records = [_coerce_raw_edge(record) for record in raw_edges]

    canonical_mentions = [
        _canonicalize_mention(raw_mention, lexicons=lexicons)
        for raw_mention in raw_mention_records
    ]
    canonical_by_key = {
        (mention.caption_id, mention.mention_id): mention
        for mention in canonical_mentions
    }
    canonical_edges = [
        _canonicalize_edge(raw_edge, canonical_by_key=canonical_by_key)
        for raw_edge in raw_edge_records
    ]

    return CanonicalizationResult(
        canonical_mentions=canonical_mentions,
        canonical_edges=canonical_edges,
    )


def run_stage5_canonicalize(
    raw_mentions_path: str | Path,
    raw_edges_path: str | Path,
    *,
    lexicon_dir: str | Path,
    canonical_mentions_path: str | Path,
    canonical_edges_path: str | Path,
    summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run Stage 5 over Stage 4 JSONL files."""
    lexicons = load_stage5_lexicons(lexicon_dir)
    raw_mentions = list(iter_jsonl(raw_mentions_path))
    raw_edges = list(iter_jsonl(raw_edges_path))
    result = canonicalize_raw_graph(
        raw_mentions,
        raw_edges,
        lexicons=lexicons,
    )

    write_jsonl(canonical_mentions_path, result.canonical_mentions)
    write_jsonl(canonical_edges_path, result.canonical_edges)

    mention_counts: Counter[str] = Counter(
        mention.mention_type for mention in result.canonical_mentions
    )
    edge_counts: Counter[str] = Counter(edge.edge_type for edge in result.canonical_edges)
    canonical_source_counts: Counter[str] = Counter(
        mention.canonical_source for mention in result.canonical_mentions
    )
    parent_filled_counts: Counter[str] = Counter(
        "with_parent" if mention.parent_concepts else "without_parent"
        for mention in result.canonical_mentions
    )
    summary = {
        "raw_mentions_path": str(raw_mentions_path),
        "raw_edges_path": str(raw_edges_path),
        "canonical_mentions_path": str(canonical_mentions_path),
        "canonical_edges_path": str(canonical_edges_path),
        "canonical_mention_total": len(result.canonical_mentions),
        "canonical_edge_total": len(result.canonical_edges),
        "mention_type_counts": dict(sorted(mention_counts.items())),
        "edge_type_counts": dict(sorted(edge_counts.items())),
        "canonical_source_counts": dict(sorted(canonical_source_counts.items())),
        "parent_filled_counts": dict(sorted(parent_filled_counts.items())),
    }
    if summary_path is not None:
        write_jsonl(summary_path, [summary])
    return summary


def _canonicalize_mention(
    raw: RawMention,
    *,
    lexicons: Stage5Lexicons,
) -> CanonicalMention:
    raw_label = _raw_label(raw)
    detail: JsonObject = {}

    if raw.mention_type == "object":
        canonical_rule_id = OBJECT_CANON_RULE_ID
        canonical, canonical_source = _lookup_or_fallback(
            raw_label,
            lexicons.object_synonyms,
        )
        parent_concepts, parent_source = _lookup_parents(canonical, lexicons.object_parents)
    elif raw.mention_type == "attribute":
        canonical_rule_id = ATTRIBUTE_CANON_RULE_ID
        canonical, canonical_source = _lookup_or_fallback(
            raw_label,
            lexicons.attribute_synonyms,
        )
        parent_concepts = []
        parent_source = None
        attribute_type = lexicons.attribute_types.get(_key(canonical))
        if attribute_type is not None:
            detail["attribute_type"] = attribute_type.value
            if attribute_type.source is not None:
                detail["attribute_type_source"] = attribute_type.source
    elif raw.mention_type == "quantity":
        canonical_rule_id = QUANTITY_CANON_RULE_ID
        canonical = raw_label
        canonical_source = "raw_fallback"
        parent_concepts = []
        parent_source = None
    elif raw.mention_type == "action":
        canonical_rule_id = ACTION_CANON_RULE_ID
        canonical, canonical_source = _lookup_or_fallback(
            raw_label,
            lexicons.action_synonyms,
        )
        parent_concepts, parent_source = _lookup_parents(canonical, lexicons.action_parents)
    else:
        raise ValueError(f"unsupported mention type: {raw.mention_type}")

    return CanonicalMention(
        caption_id=raw.caption_id,
        mention_id=raw.mention_id,
        mention_type=raw.mention_type,
        raw_text=raw.text,
        raw_lemma=raw.lemma,
        canonical=canonical,
        parent_concepts=parent_concepts,
        canonical_rule_id=canonical_rule_id,
        parent_rule_id=PARENT_RULE_ID if parent_concepts else None,
        canonical_source=canonical_source,  # type: ignore[arg-type]
        parent_source=parent_source,  # type: ignore[arg-type]
        confidence="high" if canonical_source == "lexicon" else "medium",
        canonical_detail=detail,
    )


def _canonicalize_edge(
    raw: RawEdge,
    *,
    canonical_by_key: Mapping[tuple[str, str], CanonicalMention],
) -> CanonicalEdge:
    source = _require_canonical_mention(
        canonical_by_key,
        raw.caption_id,
        raw.source_mention_id,
    )
    target = _require_canonical_mention(
        canonical_by_key,
        raw.caption_id,
        raw.target_mention_id,
    )
    canonical_rule_id = RELATION_CANON_RULE_ID if raw.edge_type == "relation" else None

    return CanonicalEdge(
        caption_id=raw.caption_id,
        edge_id=raw.edge_id,
        edge_type=raw.edge_type,
        source_mention_id=raw.source_mention_id,
        target_mention_id=raw.target_mention_id,
        label=raw.label,
        canonical_label=raw.label,
        source_canonical=source.canonical,
        target_canonical=target.canonical,
        rule_id=raw.rule_id,
        canonical_rule_id=canonical_rule_id,
        confidence=raw.confidence,
    )


def _lookup_or_fallback(
    raw_label: str,
    lookup: Mapping[str, LexiconValue],
) -> tuple[str, str]:
    entry = lookup.get(_key(raw_label))
    if entry is not None:
        return entry.value, "lexicon"
    return raw_label, "raw_fallback"


def _lookup_parents(
    canonical: str,
    lookup: Mapping[str, tuple[LexiconValue, ...]],
) -> tuple[list[str], str | None]:
    entries = lookup.get(_key(canonical), ())
    if not entries:
        return [], None
    return [entry.value for entry in entries], "lexicon"


def _raw_label(raw: RawMention) -> str:
    label = raw.lemma.strip() if raw.lemma.strip() else raw.text.strip().lower()
    if not label:
        raise ValueError(f"raw mention {raw.mention_id} has no label")
    return label


def _key(value: str) -> str:
    return value.strip().lower()


def _load_value_map(path: Path, key_column: str, value_column: str) -> dict[str, LexiconValue]:
    rows = _read_tsv(path)
    values: dict[str, LexiconValue] = {}
    for row in rows:
        key = _key(_require_cell(row, key_column, path))
        value = _require_cell(row, value_column, path).strip()
        if key == "" or value == "":
            continue
        if key in values:
            raise ValueError(f"duplicate key {key!r} in {path}")
        values[key] = LexiconValue(value=value, source=_optional_cell(row, "source"))
    return values


def _load_multi_value_map(
    path: Path,
    key_column: str,
    value_column: str,
) -> dict[str, tuple[LexiconValue, ...]]:
    rows = _read_tsv(path)
    values: dict[str, list[LexiconValue]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = _key(_require_cell(row, key_column, path))
        value = _require_cell(row, value_column, path).strip()
        if key == "" or value == "":
            continue
        marker = (key, value)
        if marker in seen:
            raise ValueError(f"duplicate key/value {marker!r} in {path}")
        seen.add(marker)
        values.setdefault(key, []).append(
            LexiconValue(value=value, source=_optional_cell(row, "source")),
        )
    return {key: tuple(items) for key, items in values.items()}


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            return []
        return [dict(row) for row in reader]


def _require_cell(row: Mapping[str, str], column: str, path: Path) -> str:
    value = row.get(column)
    if value is None:
        raise ValueError(f"{path} is missing required column {column!r}")
    return value


def _optional_cell(row: Mapping[str, str], column: str) -> str | None:
    value = row.get(column)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _coerce_raw_mention(record: Mapping[str, Any] | RawMention) -> RawMention:
    if isinstance(record, RawMention):
        return record
    return RawMention(**dict(record))


def _coerce_raw_edge(record: Mapping[str, Any] | RawEdge) -> RawEdge:
    if isinstance(record, RawEdge):
        return record
    return RawEdge(**dict(record))


def _require_canonical_mention(
    canonical_by_key: Mapping[tuple[str, str], CanonicalMention],
    caption_id: str,
    mention_id: str,
) -> CanonicalMention:
    mention = canonical_by_key.get((caption_id, mention_id))
    if mention is None:
        raise ValueError(
            f"edge endpoint {(caption_id, mention_id)!r} has no canonical mention",
        )
    return mention
