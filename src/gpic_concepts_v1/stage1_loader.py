"""Stage 1 loader for confirmed GPIC caption JSONL files."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import CaptionRecord
from gpic_concepts_v1.stage1 import make_caption_record_from_gpic_row


def iter_stage1_records(
    input_paths: Iterable[str | Path],
    *,
    limit: int | None = None,
) -> Iterator[tuple[CaptionRecord, dict[str, Any]]]:
    """Yield Stage 1 records and source rows from GPIC JSONL files."""
    emitted = 0
    for path in input_paths:
        for row in iter_jsonl(path):
            record = make_caption_record_from_gpic_row(row)
            yield record, row
            emitted += 1
            if limit is not None and emitted >= limit:
                return


def build_stage1_summary(records: Iterable[CaptionRecord]) -> dict[str, Any]:
    """Build a simple coverage summary from Stage 1 CaptionRecord rows."""
    total = 0
    shape_counts: Counter[str] = Counter()
    skipped_counts: Counter[str] = Counter()
    caption_type_counts: Counter[str] = Counter()

    for record in records:
        total += 1
        shape_counts[record.caption_shape] += 1
        if record.skipped:
            skipped_counts[record.skip_reason or "unknown"] += 1
        caption_type = record.meta.get("caption_type")
        if isinstance(caption_type, str):
            caption_type_counts[caption_type] += 1

    return {
        "total": total,
        "caption_shape_counts": dict(sorted(shape_counts.items())),
        "skipped_counts": dict(sorted(skipped_counts.items())),
        "caption_type_counts": dict(sorted(caption_type_counts.items())),
    }


def run_stage1_records(
    input_paths: Iterable[str | Path],
    *,
    caption_records_path: str | Path,
    sentence_rows_path: str | Path | None = None,
    tag_rows_path: str | Path | None = None,
    summary_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run Stage 1 over GPIC JSONL files and write requested outputs."""
    pairs = list(iter_stage1_records(input_paths, limit=limit))
    records = [record for record, _row in pairs]
    sentence_rows = [
        row
        for record, row in pairs
        if record.caption_shape == "sentence" and not record.skipped
    ]
    tag_rows = [
        row
        for record, row in pairs
        if record.caption_shape == "tag_list" and not record.skipped
    ]
    summary = build_stage1_summary(records)
    summary["caption_records_path"] = str(caption_records_path)
    if sentence_rows_path is not None:
        summary["sentence_rows_path"] = str(sentence_rows_path)
    if tag_rows_path is not None:
        summary["tag_rows_path"] = str(tag_rows_path)

    write_jsonl(caption_records_path, records, sort_keys=False)
    if sentence_rows_path is not None:
        write_jsonl(sentence_rows_path, sentence_rows, sort_keys=False)
    if tag_rows_path is not None:
        write_jsonl(tag_rows_path, tag_rows, sort_keys=False)
    if summary_path is not None:
        write_jsonl(summary_path, [summary])

    return summary
