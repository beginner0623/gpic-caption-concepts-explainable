"""Rebuild only Stage 6 relation_component_counts.tsv from canonical edges.

This is intentionally narrower than a full Stage 6 rerun. It streams
canonical_edges.jsonl, rebuilds relation-component counts, and optionally
updates the matching summary.jsonl fields. It does not rewrite facts.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from build_interactive_count_report import _create_view_table
from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.io_jsonl import iter_jsonl
from gpic_concepts_v1.schema import CountRow
from gpic_concepts_v1.stage6_export_counts import (
    COUNT_RULE_ID,
    _coerce_canonical_edge,
    _edge_only_rule_ids,
    _edge_raw_variant,
    _relation_components,
    _write_count_table_tsv,
)


@dataclass(slots=True)
class Bucket:
    count: int = 0
    caption_ids: set[str] = field(default_factory=set)
    raw_variants: set[str] = field(default_factory=set)
    rule_ids: set[str] = field(default_factory=set)


def rebuild_relation_component_counts(
    canonical_edges_path: Path,
    output_path: Path,
    *,
    summary_path: Path | None = None,
    facts_relation_component_count: int | None = None,
    report_db_path: Path | None = None,
) -> dict[str, Any]:
    buckets: dict[tuple[str, int, str], Bucket] = {}
    relation_edges = 0
    component_facts = 0

    for record in iter_jsonl(canonical_edges_path):
        edge = _coerce_canonical_edge(record)
        if edge.edge_type != "relation":
            continue
        relation_edges += 1
        raw_variant = _edge_raw_variant(edge)
        rule_ids = set(_edge_only_rule_ids(edge))
        rule_ids.add(COUNT_RULE_ID)
        for index, component in enumerate(_relation_components(edge)):
            key = (edge.canonical_label, index, component)
            bucket = buckets.setdefault(key, Bucket())
            bucket.count += 1
            bucket.caption_ids.add(edge.caption_id)
            bucket.raw_variants.add(raw_variant)
            bucket.rule_ids.update(rule_ids)
            component_facts += 1

    rows = [
        CountRow(
            count_key=f"relation_component:{relation}:{index}:{component}",
            count=bucket.count,
            caption_count=len(bucket.caption_ids),
            example_caption_ids=sorted(bucket.caption_ids)[:5],
            raw_variants=sorted(bucket.raw_variants),
            rule_ids=sorted(bucket.rule_ids),
            values={
                "relation": relation,
                "component_index": str(index),
                "component": component,
            },
        )
        for (relation, index, component), bucket in buckets.items()
    ]
    rows.sort(key=lambda row: (-row.count, row.count_key))
    _write_count_table_tsv(output_path, rows)
    report_rows = _report_rows_from_buckets(buckets)

    result = {
        "canonical_edges_path": str(canonical_edges_path),
        "output_path": str(output_path),
        "relation_edges": relation_edges,
        "relation_component_fact_count": component_facts,
        "relation_component_row_count": len(rows),
    }
    if summary_path is not None:
        _update_summary(
            summary_path,
            relation_component_fact_count=component_facts,
            relation_component_row_count=len(rows),
            facts_relation_component_count=facts_relation_component_count,
        )
        result["summary_path"] = str(summary_path)
    if report_db_path is not None:
        _replace_report_relation_component_view(report_db_path, report_rows)
        result["report_db_path"] = str(report_db_path)
    return result


def _report_rows_from_buckets(
    buckets: dict[tuple[str, int, str], Bucket],
) -> list[dict[str, Any]]:
    rows = [
        {
            "relation": relation,
            "component_index": str(index),
            "component": component,
            "count": bucket.count,
            "caption_count": len(bucket.caption_ids),
            "example_caption_ids": "|".join(sorted(bucket.caption_ids)[:5]),
            "_caption_ids": "|".join(sorted(bucket.caption_ids)),
        }
        for (relation, index, component), bucket in buckets.items()
    ]
    return sorted(
        rows,
        key=lambda row: (
            -int(row.get("count", 0)),
            json.dumps(row, ensure_ascii=False, sort_keys=True),
        ),
    )


def _replace_report_relation_component_view(
    db_path: Path,
    rows: list[dict[str, Any]],
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS relation_components")
        _create_view_table(conn, "relation_components", rows)
        metadata_row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'views'",
        ).fetchone()
        if metadata_row is not None:
            views = json.loads(str(metadata_row[0]))
            for view in views:
                if isinstance(view, dict) and view.get("name") == "relation_components":
                    view["row_count"] = len(rows)
            conn.execute(
                "UPDATE metadata SET value = ? WHERE key = 'views'",
                (json.dumps(views, ensure_ascii=False),),
            )
        conn.commit()


def _update_summary(
    summary_path: Path,
    *,
    relation_component_fact_count: int,
    relation_component_row_count: int,
    facts_relation_component_count: int | None,
) -> None:
    records: list[dict[str, Any]] = []
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    value = json.loads(stripped)
                    if not isinstance(value, dict):
                        raise ValueError(f"summary record is not an object: {summary_path}")
                    records.append(value)
    if not records:
        records.append({})

    summary = records[0]
    fact_type_counts = summary.setdefault("fact_type_counts", {})
    if facts_relation_component_count is not None:
        previous = int(fact_type_counts.get("relation_component", 0) or 0)
        fact_type_counts["relation_component"] = facts_relation_component_count
        if "fact_total" in summary:
            summary["fact_total"] = (
                int(summary["fact_total"])
                - previous
                + facts_relation_component_count
            )
    table_row_counts = summary.setdefault("table_row_counts", {})
    table_row_counts["relation_component_counts.tsv"] = relation_component_row_count
    summary["relation_component_counts_rebuild"] = {
        "facts_jsonl_rewritten": False,
        "note": (
            "relation_component_counts.tsv was rebuilt from canonical_edges.jsonl "
            "without rewriting facts.jsonl"
        ),
        "relation_component_fact_count_if_regenerated": relation_component_fact_count,
        "relation_component_row_count": relation_component_row_count,
    }

    with atomic_text_writer(summary_path) as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-edges", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--report-db", type=Path)
    parser.add_argument(
        "--facts-relation-component-count",
        type=int,
        help=(
            "Existing facts.jsonl relation_component count to preserve in summary "
            "when facts.jsonl is not rewritten."
        ),
    )
    args = parser.parse_args()

    result = rebuild_relation_component_counts(
        args.canonical_edges,
        args.output,
        summary_path=args.summary,
        facts_relation_component_count=args.facts_relation_component_count,
        report_db_path=args.report_db,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
