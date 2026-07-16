"""Stage 6 count export.

Stage 6 consumes Stage 5 canonical mentions and edges. It creates fact rows and
flat count tables only. It does not repair, infer, or rewrite graph structure.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import csv
from pathlib import Path
from typing import Any

from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import (
    CanonicalEdge,
    CanonicalMention,
    CountRow,
    FactRow,
    JsonObject,
    MISSING_SOURCE_MENTION_ID,
    MISSING_TARGET_MENTION_ID,
)


COUNT_RULE_ID = "R25"

RAW_MENTION_RULE_BY_TYPE = {
    "object": "R12",
    "attribute": "R13",
    "quantity": "R14",
    "action": "R15",
}


@dataclass(slots=True)
class CountExportResult:
    facts: list[FactRow]
    count_tables: dict[str, list[CountRow]]


def export_count_facts(
    canonical_mentions: Sequence[Mapping[str, Any] | CanonicalMention],
    canonical_edges: Sequence[Mapping[str, Any] | CanonicalEdge],
) -> CountExportResult:
    """Create Stage 6 facts and count tables from Stage 5 records."""
    mentions = [_coerce_canonical_mention(record) for record in canonical_mentions]
    edges = [_coerce_canonical_edge(record) for record in canonical_edges]
    mention_by_key = {
        (mention.caption_id, mention.mention_id): mention
        for mention in mentions
    }

    facts: list[FactRow] = []
    facts.extend(_entity_exists_facts(mentions, start_index=len(facts)))
    facts.extend(_attribute_exists_facts(mentions, start_index=len(facts)))
    facts.extend(_quantity_exists_facts(mentions, start_index=len(facts)))
    facts.extend(_object_parent_facts(mentions, start_index=len(facts)))
    facts.extend(_action_event_facts(mentions, start_index=len(facts)))
    facts.extend(_edge_facts(edges, mention_by_key, start_index=len(facts)))
    facts.extend(_ambiguous_relation_candidate_facts(edges, mention_by_key, start_index=len(facts)))
    facts.extend(_relation_component_facts(edges, start_index=len(facts)))
    facts.extend(_object_pair_facts(mentions, start_index=len(facts)))

    count_tables = {
        "object_counts.tsv": _aggregate_facts(
            facts,
            fact_type="entity_exists",
            table_key_prefix="object",
            value_fields=("object",),
            extra_value_fields=("parent_concepts", "parent_synset_ids"),
        ),
        "attribute_counts.tsv": _aggregate_facts(
            facts,
            fact_type="attribute_exists",
            table_key_prefix="attribute",
            value_fields=("attribute",),
        ),
        "quantity_counts.tsv": _aggregate_facts(
            facts,
            fact_type="quantity_exists",
            table_key_prefix="quantity",
            value_fields=("quantity",),
        ),
        "object_parent_counts.tsv": _aggregate_facts(
            facts,
            fact_type="object_parent",
            table_key_prefix="object_parent",
            value_fields=("object", "parent"),
            extra_value_fields=("parent_synset_id",),
        ),
        "object_attribute_pair_counts.tsv": _aggregate_facts(
            facts,
            fact_type="has_attribute",
            table_key_prefix="object_attribute_pair",
            value_fields=("object", "attribute"),
            extra_value_fields=("object_parent_concepts", "object_parent_synset_ids"),
        ),
        "object_quantity_pair_counts.tsv": _aggregate_facts(
            facts,
            fact_type="has_quantity",
            table_key_prefix="object_quantity_pair",
            value_fields=("object", "quantity"),
            extra_value_fields=("object_parent_concepts", "object_parent_synset_ids"),
        ),
        "action_counts.tsv": _aggregate_facts(
            facts,
            fact_type="action_event",
            table_key_prefix="action",
            value_fields=("action",),
        ),
        "agent_patient_pair_counts.tsv": _aggregate_facts(
            facts,
            fact_type="event_role",
            table_key_prefix="event_role",
            value_fields=("action", "role", "target"),
            extra_value_fields=(
                "target_parent_concepts",
                "target_parent_synset_ids",
                "raw_role",
                "voice_normalization",
            ),
        ),
        "relation_triple_counts.tsv": _aggregate_facts(
            facts,
            fact_type="relation",
            table_key_prefix="relation",
            value_fields=("source", "relation", "target"),
            extra_value_fields=(
                "source_parent_concepts",
                "source_parent_synset_ids",
                "target_parent_concepts",
                "target_parent_synset_ids",
            ),
        ),
        "relation_component_counts.tsv": _aggregate_facts(
            facts,
            fact_type="relation_component",
            table_key_prefix="relation_component",
            value_fields=("relation", "component_index", "component"),
        ),
        "ambiguous_relation_candidate_counts.tsv": _aggregate_facts(
            facts,
            fact_type="ambiguous_relation_candidate",
            table_key_prefix="ambiguous_relation_candidate",
            value_fields=("source_status", "relation", "target_status"),
            extra_value_fields=(
                "candidate_sources",
                "candidate_targets",
                "candidate_pair_count",
            ),
        ),
        "object_cooccurrence_pair_counts.tsv": _aggregate_facts(
            facts,
            fact_type="object_pair_in_caption",
            table_key_prefix="object_pair_in_caption",
            value_fields=("source_object", "target_object"),
            extra_value_fields=(
                "source_parent_concepts",
                "source_parent_synset_ids",
                "target_parent_concepts",
                "target_parent_synset_ids",
            ),
        ),
    }
    return CountExportResult(facts=facts, count_tables=count_tables)


def run_stage6_export_counts(
    canonical_mentions_path: str | Path,
    canonical_edges_path: str | Path,
    *,
    output_dir: str | Path,
    summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run Stage 6 and write facts plus TSV count tables."""
    mentions = list(iter_jsonl(canonical_mentions_path))
    edges = list(iter_jsonl(canonical_edges_path))
    result = export_count_facts(mentions, edges)

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    facts_path = output_root / "facts.jsonl"
    write_jsonl(facts_path, result.facts)

    table_paths: dict[str, str] = {}
    for file_name, rows in result.count_tables.items():
        path = output_root / file_name
        _write_count_table_tsv(path, rows)
        table_paths[file_name] = str(path)

    fact_type_counts: dict[str, int] = defaultdict(int)
    for fact in result.facts:
        fact_type_counts[fact.fact_type] += 1
    table_row_counts = {
        file_name: len(rows)
        for file_name, rows in sorted(result.count_tables.items())
    }
    summary = {
        "canonical_mentions_path": str(canonical_mentions_path),
        "canonical_edges_path": str(canonical_edges_path),
        "output_dir": str(output_root),
        "facts_path": str(facts_path),
        "fact_total": len(result.facts),
        "fact_type_counts": dict(sorted(fact_type_counts.items())),
        "table_paths": table_paths,
        "table_row_counts": table_row_counts,
    }
    if summary_path is not None:
        write_jsonl(summary_path, [summary])
    return summary


def _make_fact_row(
    *,
    caption_id: str,
    fact_index: int,
    fact_type: str,
    count_key: str,
    rule_ids: list[str],
    source_mention_ids: list[str],
    source_edge_ids: list[str],
    values: JsonObject,
) -> FactRow:
    # Stage 6 builds these fields from already validated records and constants.
    fact = object.__new__(FactRow)
    fact.caption_id = caption_id
    fact.fact_id = f"f{fact_index}"
    fact.fact_type = fact_type  # type: ignore[assignment]
    fact.count_key = count_key
    fact.rule_ids = rule_ids
    fact.source_mention_ids = source_mention_ids
    fact.source_edge_ids = source_edge_ids
    fact.values = values
    return fact


def _entity_exists_facts(
    mentions: Sequence[CanonicalMention],
    *,
    start_index: int,
) -> list[FactRow]:
    facts: list[FactRow] = []
    for mention in mentions:
        if mention.mention_type != "object":
            continue
        facts.append(
            _make_fact_row(
                caption_id=mention.caption_id,
                fact_index=start_index + len(facts),
                fact_type="entity_exists",
                count_key=f"entity_exists:{mention.canonical}",
                rule_ids=_mention_rule_ids(mention),
                source_mention_ids=[mention.mention_id],
                source_edge_ids=[],
                values={
                    "object": mention.canonical,
                    "parent_concepts": mention.parent_concepts,
                    "parent_synset_ids": _parent_synset_ids(mention),
                    "raw_variants": [_raw_variant(mention)],
                },
            ),
        )
    return facts


def _action_event_facts(
    mentions: Sequence[CanonicalMention],
    *,
    start_index: int,
) -> list[FactRow]:
    facts: list[FactRow] = []
    for mention in mentions:
        if mention.mention_type != "action":
            continue
        facts.append(
            _make_fact_row(
                caption_id=mention.caption_id,
                fact_index=start_index + len(facts),
                fact_type="action_event",
                count_key=f"action_event:{mention.canonical}",
                rule_ids=_mention_rule_ids(mention),
                source_mention_ids=[mention.mention_id],
                source_edge_ids=[],
                values={
                    "action": mention.canonical,
                    "raw_variants": [_raw_variant(mention)],
                },
            ),
        )
    return facts


def _attribute_exists_facts(
    mentions: Sequence[CanonicalMention],
    *,
    start_index: int,
) -> list[FactRow]:
    facts: list[FactRow] = []
    for mention in mentions:
        if mention.mention_type != "attribute":
            continue
        facts.append(
            _make_fact_row(
                caption_id=mention.caption_id,
                fact_index=start_index + len(facts),
                fact_type="attribute_exists",
                count_key=f"attribute_exists:{mention.canonical}",
                rule_ids=_mention_rule_ids(mention),
                source_mention_ids=[mention.mention_id],
                source_edge_ids=[],
                values={
                    "attribute": mention.canonical,
                    "raw_variants": [_raw_variant(mention)],
                },
            ),
        )
    return facts


def _quantity_exists_facts(
    mentions: Sequence[CanonicalMention],
    *,
    start_index: int,
) -> list[FactRow]:
    facts: list[FactRow] = []
    for mention in mentions:
        if mention.mention_type != "quantity":
            continue
        facts.append(
            _make_fact_row(
                caption_id=mention.caption_id,
                fact_index=start_index + len(facts),
                fact_type="quantity_exists",
                count_key=f"quantity_exists:{mention.canonical}",
                rule_ids=_mention_rule_ids(mention),
                source_mention_ids=[mention.mention_id],
                source_edge_ids=[],
                values={
                    "quantity": mention.canonical,
                    "raw_variants": [_raw_variant(mention)],
                },
            ),
        )
    return facts


def _object_parent_facts(
    mentions: Sequence[CanonicalMention],
    *,
    start_index: int,
) -> list[FactRow]:
    facts: list[FactRow] = []
    for mention in mentions:
        if mention.mention_type != "object" or not mention.parent_concepts:
            continue
        parent_synset_ids = _parent_synset_ids(mention)
        for index, parent in enumerate(mention.parent_concepts):
            parent_synset_id = (
                parent_synset_ids[index] if index < len(parent_synset_ids) else ""
            )
            facts.append(
                _make_fact_row(
                    caption_id=mention.caption_id,
                    fact_index=start_index + len(facts),
                    fact_type="object_parent",
                    count_key=f"object_parent:{mention.canonical}:{parent}",
                    rule_ids=_mention_rule_ids(mention),
                    source_mention_ids=[mention.mention_id],
                    source_edge_ids=[],
                    values={
                        "object": mention.canonical,
                        "parent": parent,
                        "parent_synset_id": parent_synset_id,
                        "raw_variants": [_raw_variant(mention)],
                    },
                ),
            )
    return facts


def _edge_facts(
    edges: Sequence[CanonicalEdge],
    mention_by_key: Mapping[tuple[str, str], CanonicalMention],
    *,
    start_index: int,
) -> list[FactRow]:
    facts: list[FactRow] = []
    for edge in edges:
        if edge.edge_type == "ambiguous_relation_candidate":
            continue
        source = _require_mention(mention_by_key, edge.caption_id, edge.source_mention_id)
        target = _require_mention(mention_by_key, edge.caption_id, edge.target_mention_id)
        if edge.edge_type == "has_attribute":
            values = {
                "object": source.canonical,
                "attribute": target.canonical,
                "object_parent_concepts": source.parent_concepts,
                "object_parent_synset_ids": _parent_synset_ids(source),
            }
            count_key = f"has_attribute:{source.canonical}:{target.canonical}"
        elif edge.edge_type == "has_quantity":
            values = {
                "object": source.canonical,
                "quantity": target.canonical,
                "object_parent_concepts": source.parent_concepts,
                "object_parent_synset_ids": _parent_synset_ids(source),
            }
            count_key = f"has_quantity:{source.canonical}:{target.canonical}"
        elif edge.edge_type == "event_role":
            raw_role = edge.canonical_detail.get("raw_role")
            voice_normalization = edge.canonical_detail.get("voice_normalization")
            values = {
                "action": source.canonical,
                "role": edge.canonical_label,
                "target": target.canonical,
                "target_parent_concepts": target.parent_concepts,
                "target_parent_synset_ids": _parent_synset_ids(target),
                "raw_role": raw_role if isinstance(raw_role, str) and raw_role else edge.canonical_label,
                "voice_normalization": (
                    voice_normalization
                    if isinstance(voice_normalization, str) and voice_normalization
                    else "none"
                ),
            }
            count_key = f"event_role:{source.canonical}:{edge.canonical_label}:{target.canonical}"
        elif edge.edge_type == "relation":
            values = {
                "source": source.canonical,
                "relation": edge.canonical_label,
                "target": target.canonical,
                "source_parent_concepts": source.parent_concepts,
                "source_parent_synset_ids": _parent_synset_ids(source),
                "target_parent_concepts": target.parent_concepts,
                "target_parent_synset_ids": _parent_synset_ids(target),
            }
            count_key = f"relation:{source.canonical}:{edge.canonical_label}:{target.canonical}"
        else:
            raise ValueError(f"unsupported edge type: {edge.edge_type}")

        facts.append(
            _make_fact_row(
                caption_id=edge.caption_id,
                fact_index=start_index + len(facts),
                fact_type=edge.edge_type,
                count_key=count_key,
                rule_ids=_edge_rule_ids(edge, source, target),
                source_mention_ids=[edge.source_mention_id, edge.target_mention_id],
                source_edge_ids=[edge.edge_id],
                values=values,
            ),
        )
    return facts


def _ambiguous_relation_candidate_facts(
    edges: Sequence[CanonicalEdge],
    mention_by_key: Mapping[tuple[str, str], CanonicalMention],
    *,
    start_index: int,
) -> list[FactRow]:
    grouped_edges: dict[tuple[str, str, tuple[str, ...]], list[CanonicalEdge]] = defaultdict(list)
    for edge in edges:
        if edge.edge_type != "ambiguous_relation_candidate":
            continue
        matched_token_indices = _matched_token_indices_key(edge)
        key = (edge.caption_id, edge.canonical_label, matched_token_indices)
        grouped_edges[key].append(edge)

    facts: list[FactRow] = []
    for (caption_id, relation, _matched_token_indices), group in sorted(grouped_edges.items()):
        candidate_sources: set[str] = set()
        candidate_targets: set[str] = set()
        source_mention_ids: set[str] = set()
        rule_ids: set[str] = set()
        source_missing = False
        target_missing = False
        for edge in group:
            rule_ids.update(_edge_only_rule_ids(edge))
            if edge.source_mention_id == MISSING_SOURCE_MENTION_ID:
                source_missing = True
                candidate_sources.add("source_missing")
            else:
                source = _require_mention(mention_by_key, edge.caption_id, edge.source_mention_id)
                candidate_sources.add(source.canonical)
                source_mention_ids.add(edge.source_mention_id)
                rule_ids.update(source_mention_rule_ids_without_parent(source))
                if source.parent_rule_id is not None:
                    rule_ids.add(source.parent_rule_id)
            if edge.target_mention_id == MISSING_TARGET_MENTION_ID:
                target_missing = True
                candidate_targets.add("target_missing")
            else:
                target = _require_mention(mention_by_key, edge.caption_id, edge.target_mention_id)
                candidate_targets.add(target.canonical)
                source_mention_ids.add(edge.target_mention_id)
                rule_ids.update(source_mention_rule_ids_without_parent(target))
                if target.parent_rule_id is not None:
                    rule_ids.add(target.parent_rule_id)

        source_status = _relation_candidate_status(
            candidate_sources,
            missing=source_missing,
            endpoint_name="source",
        )
        target_status = _relation_candidate_status(
            candidate_targets,
            missing=target_missing,
            endpoint_name="target",
        )
        facts.append(
            _make_fact_row(
                caption_id=caption_id,
                fact_index=start_index + len(facts),
                fact_type="ambiguous_relation_candidate",
                count_key=(
                    "ambiguous_relation_candidate:"
                    f"{source_status}:{relation}:{target_status}"
                ),
                rule_ids=sorted(rule_ids),
                source_mention_ids=sorted(source_mention_ids),
                source_edge_ids=sorted(edge.edge_id for edge in group),
                values={
                    "source_status": source_status,
                    "relation": relation,
                    "target_status": target_status,
                    "candidate_sources": sorted(candidate_sources),
                    "candidate_targets": sorted(candidate_targets),
                    "candidate_pair_count": str(len(group)),
                    "raw_variants": sorted({_edge_raw_variant(edge) for edge in group}),
                },
            ),
        )
    return facts


def _relation_candidate_status(
    candidates: set[str],
    *,
    missing: bool,
    endpoint_name: str,
) -> str:
    if missing:
        return f"{endpoint_name}_missing"
    if len(candidates) > 1:
        return f"{endpoint_name}_ambiguous"
    return f"{endpoint_name}_resolved"


def _matched_token_indices_key(edge: CanonicalEdge) -> tuple[str, ...]:
    value = edge.canonical_detail.get("matched_token_indices")
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    return (edge.edge_id,)


def _relation_component_facts(
    edges: Sequence[CanonicalEdge],
    *,
    start_index: int,
) -> list[FactRow]:
    facts: list[FactRow] = []
    for edge in edges:
        if edge.edge_type != "relation":
            continue
        components = _relation_components(edge)
        raw_variant = _edge_raw_variant(edge)
        for index, component in enumerate(components):
            facts.append(
                _make_fact_row(
                    caption_id=edge.caption_id,
                    fact_index=start_index + len(facts),
                    fact_type="relation_component",
                    count_key=(
                        "relation_component:"
                        f"{edge.canonical_label}:{index}:{component}"
                    ),
                    rule_ids=_edge_only_rule_ids(edge),
                    source_mention_ids=[edge.source_mention_id, edge.target_mention_id],
                    source_edge_ids=[edge.edge_id],
                    values={
                        "relation": edge.canonical_label,
                        "component_index": str(index),
                        "component": component,
                        "raw_variants": [raw_variant],
                    },
                ),
            )
    return facts


def _relation_components(edge: CanonicalEdge) -> list[str]:
    components = edge.canonical_detail.get("relation_components")
    if isinstance(components, list):
        return [
            str(component).strip().lower()
            for component in components
            if str(component).strip()
        ]
    return [
        component
        for component in edge.canonical_label.strip().lower().split()
        if component
    ]


def _object_pair_facts(
    mentions: Sequence[CanonicalMention],
    *,
    start_index: int,
) -> list[FactRow]:
    objects_by_caption: dict[str, dict[str, list[CanonicalMention]]] = defaultdict(dict)
    for mention in mentions:
        if mention.mention_type != "object":
            continue
        objects_by_caption[mention.caption_id].setdefault(mention.canonical, []).append(mention)

    facts: list[FactRow] = []
    for caption_id in sorted(objects_by_caption):
        object_map = objects_by_caption[caption_id]
        canonical_objects = sorted(object_map)
        mention_ids_by_object = {
            canonical: [mention.mention_id for mention in object_mentions]
            for canonical, object_mentions in object_map.items()
        }
        rule_ids_by_object = {
            canonical: {
                rule_id
                for mention in object_mentions
                for rule_id in _mention_rule_ids(mention)
            }
            for canonical, object_mentions in object_map.items()
        }
        parent_concepts_by_object = {
            canonical: sorted(
                {
                    parent
                    for mention in object_mentions
                    for parent in mention.parent_concepts
                },
            )
            for canonical, object_mentions in object_map.items()
        }
        parent_synset_ids_by_object = {
            canonical: sorted(
                {
                    parent_synset_id
                    for mention in object_mentions
                    for parent_synset_id in _parent_synset_ids(mention)
                },
            )
            for canonical, object_mentions in object_map.items()
        }
        for source_object in canonical_objects:
            for target_object in canonical_objects:
                if source_object == target_object:
                    continue
                rule_ids = sorted(
                    rule_ids_by_object[source_object]
                    | rule_ids_by_object[target_object]
                    | {COUNT_RULE_ID},
                )
                facts.append(
                    _make_fact_row(
                        caption_id=caption_id,
                        fact_index=start_index + len(facts),
                        fact_type="object_pair_in_caption",
                        count_key=(
                            "object_pair_in_caption:"
                            f"{source_object}:{target_object}"
                        ),
                        rule_ids=rule_ids,
                        source_mention_ids=(
                            mention_ids_by_object[source_object]
                            + mention_ids_by_object[target_object]
                        ),
                        source_edge_ids=[],
                        values={
                            "source_object": source_object,
                            "target_object": target_object,
                            "source_parent_concepts": parent_concepts_by_object[source_object],
                            "source_parent_synset_ids": parent_synset_ids_by_object[source_object],
                            "target_parent_concepts": parent_concepts_by_object[target_object],
                            "target_parent_synset_ids": parent_synset_ids_by_object[target_object],
                        },
                    ),
                )
    return facts


def _aggregate_facts(
    facts: Sequence[FactRow],
    *,
    fact_type: str,
    table_key_prefix: str,
    value_fields: Sequence[str],
    extra_value_fields: Sequence[str] = (),
) -> list[CountRow]:
    buckets: dict[tuple[str, ...], list[FactRow]] = defaultdict(list)
    for fact in facts:
        if fact.fact_type != fact_type:
            continue
        key_values = tuple(str(fact.values[field]) for field in value_fields)
        buckets[key_values].append(fact)

    rows: list[CountRow] = []
    for key_values in sorted(buckets):
        bucket = buckets[key_values]
        values = {
            field: value
            for field, value in zip(value_fields, key_values, strict=True)
        }
        for field in extra_value_fields:
            values[field] = _collect_value_field(bucket, field)
        count_key = ":".join((table_key_prefix, *key_values))
        rows.append(
            CountRow(
                count_key=count_key,
                count=len(bucket),
                caption_count=len({fact.caption_id for fact in bucket}),
                example_caption_ids=sorted({fact.caption_id for fact in bucket})[:5],
                raw_variants=_collect_raw_variants(bucket),
                rule_ids=_collect_rule_ids(bucket),
                values=values,
            ),
        )
    rows.sort(key=lambda row: (-row.count, row.count_key))
    return rows


def _collect_value_field(facts: Iterable[FactRow], field: str) -> str:
    values: set[str] = set()
    for fact in facts:
        value = fact.values.get(field)
        if isinstance(value, list):
            values.update(str(item) for item in value if str(item))
        elif value is not None:
            text = str(value)
            if text:
                values.add(text)
    return "|".join(sorted(values))


def _write_count_table_tsv(path: Path, rows: Sequence[CountRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value_fields = _value_fields(rows)
    fieldnames = [
        "count_key",
        *value_fields,
        "count",
        "caption_count",
        "example_caption_ids",
        "raw_variants",
        "rule_ids",
    ]
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "count_key": row.count_key,
                    **{field: row.values.get(field, "") for field in value_fields},
                    "count": row.count,
                    "caption_count": row.caption_count,
                    "example_caption_ids": "|".join(row.example_caption_ids),
                    "raw_variants": "|".join(row.raw_variants),
                    "rule_ids": "|".join(row.rule_ids),
                },
            )


def _value_fields(rows: Sequence[CountRow]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for field in row.values:
            if field not in fields:
                fields.append(field)
    return fields


def _mention_rule_ids(mention: CanonicalMention) -> list[str]:
    rule_ids = [
        RAW_MENTION_RULE_BY_TYPE[mention.mention_type],
        mention.canonical_rule_id,
    ]
    if mention.parent_rule_id is not None:
        rule_ids.append(mention.parent_rule_id)
    return _unique_sorted(rule_ids)


def _edge_rule_ids(
    edge: CanonicalEdge,
    source: CanonicalMention,
    target: CanonicalMention,
) -> list[str]:
    rule_ids = [
        edge.rule_id,
        *source_mention_rule_ids_without_parent(source),
        *source_mention_rule_ids_without_parent(target),
    ]
    if edge.canonical_rule_id is not None:
        rule_ids.append(edge.canonical_rule_id)
    if source.parent_rule_id is not None:
        rule_ids.append(source.parent_rule_id)
    if target.parent_rule_id is not None:
        rule_ids.append(target.parent_rule_id)
    return _unique_sorted(rule_ids)


def _edge_only_rule_ids(edge: CanonicalEdge) -> list[str]:
    rule_ids = [edge.rule_id]
    if edge.canonical_rule_id is not None:
        rule_ids.append(edge.canonical_rule_id)
    return _unique_sorted(rule_ids)


def source_mention_rule_ids_without_parent(mention: CanonicalMention) -> list[str]:
    return [
        RAW_MENTION_RULE_BY_TYPE[mention.mention_type],
        mention.canonical_rule_id,
    ]


def _collect_raw_variants(facts: Iterable[FactRow]) -> list[str]:
    variants: set[str] = set()
    for fact in facts:
        value = fact.values.get("raw_variants")
        if isinstance(value, list):
            variants.update(str(item) for item in value if str(item))
    return sorted(variants)


def _collect_rule_ids(facts: Iterable[FactRow]) -> list[str]:
    rule_ids: set[str] = set()
    for fact in facts:
        rule_ids.update(fact.rule_ids)
        rule_ids.add(COUNT_RULE_ID)
    return sorted(rule_ids)


def _raw_variant(mention: CanonicalMention) -> str:
    raw_text = mention.raw_text.strip().lower()
    if raw_text:
        return raw_text
    return mention.raw_lemma.strip().lower()


def _edge_raw_variant(edge: CanonicalEdge) -> str:
    raw_span = edge.canonical_detail.get("raw_span_surface")
    if isinstance(raw_span, str) and raw_span.strip():
        return raw_span.strip().lower()
    return edge.label.strip().lower()


def _parent_synset_ids(mention: CanonicalMention) -> list[str]:
    value = mention.canonical_detail.get("parent_oewn_synsets")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    if isinstance(value, tuple):
        return [item for item in value if isinstance(item, str) and item]
    if isinstance(value, str) and value:
        return [item for item in value.split("|") if item]
    return []


def _unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def _coerce_canonical_mention(
    record: Mapping[str, Any] | CanonicalMention,
) -> CanonicalMention:
    if isinstance(record, CanonicalMention):
        return record
    return CanonicalMention(**dict(record))


def _coerce_canonical_edge(
    record: Mapping[str, Any] | CanonicalEdge,
) -> CanonicalEdge:
    if isinstance(record, CanonicalEdge):
        return record
    return CanonicalEdge(**dict(record))


def _require_mention(
    mention_by_key: Mapping[tuple[str, str], CanonicalMention],
    caption_id: str,
    mention_id: str,
) -> CanonicalMention:
    mention = mention_by_key.get((caption_id, mention_id))
    if mention is None:
        raise ValueError(
            f"edge endpoint {(caption_id, mention_id)!r} has no canonical mention",
        )
    return mention
