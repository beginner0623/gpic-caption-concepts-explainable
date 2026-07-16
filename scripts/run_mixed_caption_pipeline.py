from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_caption_concept_md import build_report, caption_id, group_by_caption
from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.inventory_bundle import load_inventory_bundle, merge_bundle_path
from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.pipeline_state import (
    PipelineStateError,
    build_mixed_formal_pipeline_state,
    output_dir_state_path,
    require_stage5_lexicon_bundle_state,
    write_pipeline_state,
)
from gpic_concepts_v1.stage1_loader import run_stage1_records
from gpic_concepts_v1.stage3_annotate import (
    DEFAULT_STAGE3_BATCH_SIZE,
    DEFAULT_STAGE3_MODEL,
    iter_stage3_records_from_rows,
    iter_stage3_tag_list_records_from_rows,
    make_stage3_nlp,
)
from gpic_concepts_v1.stage4_extract_raw import (
    _load_object_lookup_runtime,
    load_gpic_action_inventory,
    load_gpic_object_inventory,
    load_preposition_mwe_lexicon,
    run_stage4_extract_raw,
)
from gpic_concepts_v1.stage5_canonicalize import run_stage5_canonicalize
from gpic_concepts_v1.stage6_export_counts import run_stage6_export_counts
from run_stage4_extract_raw import (
    _raise_if_action_inventory_not_ready,
    _raise_if_object_inventory_not_ready,
)
from run_stage5_canonicalize import _raise_if_attribute_inventory_not_ready


DEFAULT_MAX_MONOLITHIC_STAGE456_CAPTIONS = 250_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the formal mixed sentence/tag-list v1 pipeline and export one "
            "shared Stage 6 count set."
        ),
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Input GPIC .jsonl or .jsonl.gz caption rows. Can be repeated.",
    )
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    parser.add_argument(
        "--inventory-bundle",
        help=(
            "Completed Stage 3.5 inventory bundle JSON. Supplies object, "
            "attribute, action, and Stage 5 lexicon paths together."
        ),
    )
    parser.add_argument(
        "--object-inventory",
        help="Resolved GPIC observed object inventory TSV.",
    )
    parser.add_argument(
        "--attribute-inventory",
        help="Resolved GPIC observed attribute inventory TSV.",
    )
    parser.add_argument(
        "--action-inventory",
        help=(
            "Resolved GPIC observed action inventory TSV. Required for "
            "formal Stage 4 extraction unless preview action lookup is "
            "explicitly enabled."
        ),
    )
    parser.add_argument(
        "--allow-runtime-action-lookup-preview",
        action="store_true",
        help=(
            "Preview/debug mode only: allow runtime OEWN verb lookup instead "
            "of a resolved action inventory."
        ),
    )
    parser.add_argument(
        "--preposition-mwe-lexicon",
        help=(
            "Optional active preposition MWE TSV. If omitted, Stage 4 uses "
            "resources/lexicons/preposition_mwes.tsv when it exists."
        ),
    )
    parser.add_argument(
        "--lexicon-dir",
        help="Directory containing Stage 5 TSV lexicons.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_STAGE3_MODEL,
        help=f"spaCy model name. Default: {DEFAULT_STAGE3_MODEL}",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_STAGE3_BATCH_SIZE,
        help=f"spaCy nlp.pipe batch size. Default: {DEFAULT_STAGE3_BATCH_SIZE}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of Stage 1 input rows across all inputs.",
    )
    parser.add_argument(
        "--md-report",
        help=(
            "Optional Markdown report path. Defaults to no report; Stage 6 "
            "count files are always produced."
        ),
    )
    parser.add_argument(
        "--md-limit",
        type=int,
        default=100,
        help="Maximum captions to include when --md-report is passed.",
    )
    parser.add_argument(
        "--md-start",
        type=int,
        default=0,
        help="Start offset for --md-report.",
    )
    parser.add_argument(
        "--max-object-pairs-per-caption",
        type=int,
        default=40,
        help="Maximum object co-occurrence pair rows shown per caption in --md-report.",
    )
    parser.add_argument(
        "--progress-output",
        help="Optional JSON path updated while formal mixed pipeline stages run.",
    )
    parser.add_argument(
        "--progress-interval-records",
        type=int,
        default=5000,
        help="Record interval for progress JSON updates during Stage 3 writes.",
    )
    parser.add_argument(
        "--max-monolithic-stage456-captions",
        type=int,
        default=DEFAULT_MAX_MONOLITHIC_STAGE456_CAPTIONS,
        help=(
            "Fail before monolithic Stage 4/5/6 when the Stage 1 caption count "
            "exceeds this value. 0 disables the guard. Default: 250000."
        ),
    )
    gpu_group = parser.add_mutually_exclusive_group()
    gpu_group.add_argument(
        "--prefer-gpu",
        action="store_true",
        help="Use spaCy GPU if CuPy/CUDA is available; continue on CPU otherwise.",
    )
    gpu_group.add_argument(
        "--require-gpu",
        action="store_true",
        help="Require spaCy GPU; fail early if CuPy/CUDA is unavailable.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    object_inventory, attribute_inventory, action_inventory, lexicon_dir = inventory_inputs_from_args(args)
    progress_output = Path(args.progress_output) if args.progress_output else None
    try:
        summary = run_mixed_caption_pipeline(
            input_paths=args.input,
            output_dir=Path(args.output_dir),
            object_inventory=object_inventory,
            attribute_inventory=attribute_inventory,
            action_inventory=action_inventory,
            allow_runtime_action_lookup_preview=args.allow_runtime_action_lookup_preview,
            preposition_mwe_lexicon=(
                Path(args.preposition_mwe_lexicon) if args.preposition_mwe_lexicon else None
            ),
            lexicon_dir=lexicon_dir,
            model=args.model,
            batch_size=args.batch_size,
            limit=args.limit,
            gpu_mode="require" if args.require_gpu else "prefer" if args.prefer_gpu else "none",
            md_report=Path(args.md_report) if args.md_report else None,
            md_start=args.md_start,
            md_limit=args.md_limit,
            max_object_pairs_per_caption=args.max_object_pairs_per_caption,
            progress_output=progress_output,
            progress_interval_records=args.progress_interval_records,
            max_monolithic_stage456_captions=args.max_monolithic_stage456_captions,
        )
    except BaseException as exc:
        if progress_output is not None:
            MixedPipelineProgressWriter(progress_output).write(
                status="failed",
                phase="failed",
                error=repr(exc),
                output_dir=args.output_dir,
            )
        raise
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def inventory_inputs_from_args(args: argparse.Namespace) -> tuple[Path, Path, Path | None, Path]:
    bundle = load_inventory_bundle(args.inventory_bundle) if args.inventory_bundle else None
    object_inventory = merge_bundle_path(
        field_name="object_inventory",
        explicit_path=args.object_inventory,
        bundled_path=bundle.object_inventory if bundle else None,
    )
    attribute_inventory = merge_bundle_path(
        field_name="attribute_inventory",
        explicit_path=args.attribute_inventory,
        bundled_path=bundle.attribute_inventory if bundle else None,
    )
    action_inventory = merge_bundle_path(
        field_name="action_inventory",
        explicit_path=args.action_inventory,
        bundled_path=bundle.action_inventory if bundle else None,
    )
    lexicon_dir = merge_bundle_path(
        field_name="lexicon_dir",
        explicit_path=args.lexicon_dir,
        bundled_path=bundle.lexicon_dir if bundle else None,
    )
    if object_inventory is None:
        raise ValueError("object_inventory is required unless --inventory-bundle is provided")
    if attribute_inventory is None:
        raise ValueError("attribute_inventory is required unless --inventory-bundle is provided")
    return object_inventory, attribute_inventory, action_inventory, lexicon_dir or Path("resources/lexicons")


class MixedPipelineProgressWriter:
    def __init__(self, path: Path, interval_records: int = 5000) -> None:
        self.path = Path(path)
        self.interval_records = interval_records
        self.interval_records = max(1, self.interval_records)
        self._started_at = time.perf_counter()
        self._last_stage_counts: dict[str, int] = {}

    def write(self, *, status: str, phase: str, **payload: Any) -> None:
        progress = {
            "schema_version": 1,
            "artifact_type": "mixed_formal_pipeline_progress",
            "status": status,
            "phase": phase,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.perf_counter() - self._started_at, 3),
            **payload,
        }
        with atomic_text_writer(self.path) as handle:
            handle.write(json.dumps(progress, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")

    def maybe_write_stage3(self, *, phase: str, total: int, **payload: Any) -> None:
        previous = self._last_stage_counts.get(phase, -self.interval_records)
        if total - previous < self.interval_records:
            return
        self._last_stage_counts[phase] = total
        self.write(
            status="running",
            phase=phase,
            stage3_records_written=total,
            **payload,
        )


def run_mixed_caption_pipeline(
    *,
    input_paths: Iterable[str | Path],
    output_dir: Path,
    object_inventory: Path,
    attribute_inventory: Path,
    action_inventory: Path | None = None,
    allow_runtime_action_lookup_preview: bool = False,
    preposition_mwe_lexicon: Path | None = None,
    lexicon_dir: Path = Path("resources/lexicons"),
    model: str = DEFAULT_STAGE3_MODEL,
    batch_size: int = DEFAULT_STAGE3_BATCH_SIZE,
    limit: int | None = None,
    gpu_mode: str = "none",
    md_report: Path | None = None,
    md_start: int = 0,
    md_limit: int = 100,
    max_object_pairs_per_caption: int = 40,
    progress_output: Path | None = None,
    progress_interval_records: int = 5000,
    max_monolithic_stage456_captions: int = DEFAULT_MAX_MONOLITHIC_STAGE456_CAPTIONS,
) -> dict[str, Any]:
    total_start = time.perf_counter()
    timing_seconds: dict[str, float] = {}
    progress_writer = (
        MixedPipelineProgressWriter(
            progress_output,
            interval_records=progress_interval_records,
        )
        if progress_output is not None
        else None
    )

    def mark_timing(name: str, start: float) -> None:
        timing_seconds[name] = round(time.perf_counter() - start, 6)

    def write_progress(phase: str, *, status: str = "running", **payload: Any) -> None:
        if progress_writer is not None:
            progress_writer.write(
                status=status,
                phase=phase,
                output_dir=str(output_dir),
                timing_seconds=timing_seconds,
                **payload,
            )

    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    if max_monolithic_stage456_captions < 0:
        raise ValueError("max_monolithic_stage456_captions must be >= 0")
    if action_inventory is None and not allow_runtime_action_lookup_preview:
        raise ValueError(
            "action_inventory is required for formal mixed pipeline Stage 4; "
            "set allow_runtime_action_lookup_preview=True only for preview/debug runs"
        )
    runtime_action_lookup_preview = action_inventory is None and allow_runtime_action_lookup_preview
    _raise_if_object_inventory_not_ready(object_inventory)
    if action_inventory is not None:
        _raise_if_action_inventory_not_ready(action_inventory)
    if not runtime_action_lookup_preview:
        try:
            require_stage5_lexicon_bundle_state(lexicon_dir)
        except PipelineStateError as exc:
            raise ValueError(
                "lexicon_dir is not ready for formal mixed pipeline Stage 5: "
                f"{exc}"
            ) from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    write_progress("start", input_paths=[str(path) for path in input_paths])

    stage1_dir = output_dir / "stage1"
    stage3_dir = output_dir / "stage3"
    stage4_dir = output_dir / "stage4"
    stage5_dir = output_dir / "stage5"
    stage6_dir = output_dir / "stage6"

    caption_records_path = stage1_dir / "caption_records.jsonl"
    sentence_rows_path = stage1_dir / "sentence_rows.jsonl"
    tag_rows_path = stage1_dir / "tag_rows.jsonl"
    mixed_caption_rows_path = stage1_dir / "caption_rows_mixed.jsonl"
    stage1_summary_path = stage1_dir / "summary.jsonl"
    stage_start = time.perf_counter()
    write_progress("stage1_records")
    stage1_summary = run_stage1_records(
        input_paths,
        caption_records_path=caption_records_path,
        sentence_rows_path=sentence_rows_path,
        tag_rows_path=tag_rows_path,
        summary_path=stage1_summary_path,
        limit=limit,
    )
    mark_timing("stage1_records", stage_start)
    write_progress("stage1_records_complete", stage1=stage1_summary)
    _raise_if_monolithic_stage456_too_large(
        caption_total=int(stage1_summary.get("total", 0) or 0),
        max_captions=max_monolithic_stage456_captions,
        output_dir=output_dir,
    )
    stage_start = time.perf_counter()
    write_progress("stage1_mixed_caption_rows")
    mixed_caption_rows_summary = combine_caption_rows_in_caption_order(
        caption_records_path=caption_records_path,
        sentence_rows_path=sentence_rows_path,
        tag_rows_path=tag_rows_path,
        output_path=mixed_caption_rows_path,
    )
    mark_timing("stage1_mixed_caption_rows", stage_start)
    write_progress("stage1_mixed_caption_rows_complete", stage1_mixed_caption_rows=mixed_caption_rows_summary)

    stage_start = time.perf_counter()
    write_progress("stage3_model_load")
    nlp = make_stage3_nlp(model, gpu_mode=gpu_mode)
    mark_timing("stage3_model_load", stage_start)
    write_progress("stage3_model_load_complete", gpu_mode=nlp.meta.get("gpic_gpu_mode", ""), gpu_enabled=bool(nlp.meta.get("gpic_gpu_enabled", False)))
    sentence_stage3_path = stage3_dir / "sentence_stage3_records.jsonl"
    tag_stage3_path = stage3_dir / "tag_list_stage3_records.jsonl"
    stage_start = time.perf_counter()
    write_progress("stage3_sentence")
    sentence_stage3_summary = _write_stage3_records(
        sentence_rows_path,
        output_path=sentence_stage3_path,
        nlp=nlp,
        caption_shape="sentence",
        model=model,
        batch_size=batch_size,
        progress_writer=progress_writer,
    )
    mark_timing("stage3_sentence", stage_start)
    write_progress("stage3_sentence_complete", stage3_sentence=sentence_stage3_summary)
    stage_start = time.perf_counter()
    write_progress("stage3_tag_list")
    tag_stage3_summary = _write_stage3_records(
        tag_rows_path,
        output_path=tag_stage3_path,
        nlp=nlp,
        caption_shape="tag_list",
        model=model,
        batch_size=batch_size,
        progress_writer=progress_writer,
    )
    mark_timing("stage3_tag_list", stage_start)
    write_progress("stage3_tag_list_complete", stage3_tag_list=tag_stage3_summary)

    combined_stage3_path = stage3_dir / "stage3_records.jsonl"
    stage_start = time.perf_counter()
    write_progress("stage3_combined")
    combined_stage3_summary = combine_stage3_records_in_caption_order(
        caption_records_path=caption_records_path,
        sentence_stage3_path=sentence_stage3_path,
        tag_stage3_path=tag_stage3_path,
        output_path=combined_stage3_path,
    )
    write_jsonl(stage3_dir / "summary.jsonl", [combined_stage3_summary])
    mark_timing("stage3_combined", stage_start)
    write_progress("stage3_combined_complete", stage3_combined=combined_stage3_summary)

    stage_start = time.perf_counter()
    write_progress("stage4_lookup_load")
    object_lookup = load_gpic_object_inventory(object_inventory)
    if action_inventory is not None:
        action_lookup = load_gpic_action_inventory(action_inventory)
        runtime_action_lookup_preview = False
    elif allow_runtime_action_lookup_preview:
        action_lookup = _load_object_lookup_runtime()
        runtime_action_lookup_preview = True
    preposition_mwe_lookup = (
        load_preposition_mwe_lexicon(preposition_mwe_lexicon)
        if preposition_mwe_lexicon is not None
        else None
    )
    mark_timing("stage4_lookup_load", stage_start)
    write_progress("stage4_lookup_load_complete")
    stage_start = time.perf_counter()
    write_progress("stage4_extract_raw")
    stage4_summary = run_stage4_extract_raw(
        combined_stage3_path,
        raw_mentions_path=stage4_dir / "raw_mentions.jsonl",
        raw_edges_path=stage4_dir / "raw_edges.jsonl",
        summary_path=stage4_dir / "summary.jsonl",
        object_lookup=object_lookup,
        action_lookup=action_lookup,
        preposition_mwe_lookup=preposition_mwe_lookup,
        progress_path=stage4_dir / "progress.json",
    )
    mark_timing("stage4_extract_raw", stage_start)
    write_progress("stage4_extract_raw_complete", stage4=stage4_summary)

    stage_start = time.perf_counter()
    write_progress("stage5_canonicalize")
    _raise_if_attribute_inventory_not_ready(attribute_inventory)
    stage5_summary = run_stage5_canonicalize(
        stage4_dir / "raw_mentions.jsonl",
        stage4_dir / "raw_edges.jsonl",
        lexicon_dir=lexicon_dir,
        canonical_mentions_path=stage5_dir / "canonical_mentions.jsonl",
        canonical_edges_path=stage5_dir / "canonical_edges.jsonl",
        summary_path=None,
        progress_path=stage5_dir / "progress.json",
    )
    stage5_summary["formal_attribute_inventory_gate"] = True
    write_jsonl(stage5_dir / "summary.jsonl", [stage5_summary])
    mark_timing("stage5_canonicalize", stage_start)
    write_progress("stage5_canonicalize_complete", stage5=stage5_summary)

    stage_start = time.perf_counter()
    write_progress("stage6_export_counts")
    stage6_summary = run_stage6_export_counts(
        stage5_dir / "canonical_mentions.jsonl",
        stage5_dir / "canonical_edges.jsonl",
        output_dir=stage6_dir,
        summary_path=stage6_dir / "summary.jsonl",
        progress_path=stage6_dir / "progress.json",
    )
    mark_timing("stage6_export_counts", stage_start)
    write_progress("stage6_export_counts_complete", stage6=stage6_summary)

    md_summary: dict[str, Any] | None = None
    if md_report is not None:
        stage_start = time.perf_counter()
        write_progress("md_report")
        md_summary = build_mixed_markdown_report(
            caption_rows_path=mixed_caption_rows_path,
            stage3_records_path=combined_stage3_path,
            canonical_mentions_path=stage5_dir / "canonical_mentions.jsonl",
            canonical_edges_path=stage5_dir / "canonical_edges.jsonl",
            facts_path=stage6_dir / "facts.jsonl",
            output_path=md_report,
            start=md_start,
            limit=md_limit,
            max_object_pairs_per_caption=max_object_pairs_per_caption,
        )
        mark_timing("md_report", stage_start)
        write_progress("md_report_complete", md_report=md_summary)

    timing_seconds["total_pipeline"] = round(time.perf_counter() - total_start, 6)
    total_captions = int(stage1_summary.get("total", 0) or 0)
    timing_throughput = {
        "captions_per_second_total_pipeline": (
            round(total_captions / timing_seconds["total_pipeline"], 6)
            if timing_seconds["total_pipeline"] > 0
            else 0.0
        )
    }

    summary = {
        "status": "completed",
        "output_dir": str(output_dir),
        "stage1": stage1_summary,
        "stage1_mixed_caption_rows": mixed_caption_rows_summary,
        "stage3_sentence": sentence_stage3_summary,
        "stage3_tag_list": tag_stage3_summary,
        "stage3_combined": combined_stage3_summary,
        "stage4": stage4_summary,
        "stage5": stage5_summary,
        "stage6": stage6_summary,
        "md_report": md_summary,
        "runtime_action_lookup_preview": runtime_action_lookup_preview,
        "timing_seconds": timing_seconds,
        "timing_throughput": timing_throughput,
    }
    pipeline_state_path = output_dir_state_path(output_dir)
    pipeline_state = build_mixed_formal_pipeline_state(
        output_dir=str(output_dir),
        object_inventory=str(object_inventory),
        attribute_inventory=str(attribute_inventory),
        action_inventory=str(action_inventory) if action_inventory is not None else None,
        lexicon_dir=str(lexicon_dir),
        runtime_action_lookup_preview=runtime_action_lookup_preview,
        stage_summaries=summary,
    )
    write_pipeline_state(pipeline_state_path, pipeline_state)
    summary["pipeline_state"] = str(pipeline_state_path)
    write_jsonl(output_dir / "mixed_pipeline_summary.jsonl", [summary])
    write_progress("complete", status="completed", summary=summary)
    return summary


def _raise_if_monolithic_stage456_too_large(
    *,
    caption_total: int,
    max_captions: int,
    output_dir: Path,
) -> None:
    if max_captions == 0 or caption_total <= max_captions:
        return
    raise RuntimeError(
        "monolithic Stage 4/5/6 is not safe for this caption volume: "
        f"caption_total={caption_total}, max_monolithic_stage456_captions={max_captions}, "
        f"output_dir={output_dir}. Use a chunked/streaming Stage 4/5/6 runner instead."
    )


def combine_caption_rows_in_caption_order(
    *,
    caption_records_path: Path,
    sentence_rows_path: Path,
    tag_rows_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    written = write_jsonl(
        output_path,
        _iter_caption_rows_in_caption_order(
            caption_records_path=caption_records_path,
            sentence_rows_path=sentence_rows_path,
            tag_rows_path=tag_rows_path,
        ),
    )
    shape_counts: Counter[str] = Counter()
    for row in iter_jsonl(output_path):
        caption_type = row.get("caption_type")
        if caption_type == "tag":
            shape_counts["tag_list"] += 1
        else:
            shape_counts["sentence"] += 1
    return {
        "total": written,
        "written": written,
        "output_path": str(output_path),
        "caption_shape_counts": dict(sorted(shape_counts.items())),
        "merge_policy": "caption_records_order",
    }


def _iter_caption_rows_in_caption_order(
    *,
    caption_records_path: Path,
    sentence_rows_path: Path,
    tag_rows_path: Path,
) -> Iterator[Mapping[str, Any]]:
    sentence_iter = iter(iter_jsonl(sentence_rows_path))
    tag_iter = iter(iter_jsonl(tag_rows_path))
    next_sentence = _next_or_none(sentence_iter)
    next_tag = _next_or_none(tag_iter)

    for caption_record in iter_jsonl(caption_records_path):
        if caption_record.get("skipped"):
            continue
        expected_id = _required_text(caption_record, "caption_id")
        shape = _required_text(caption_record, "caption_shape")
        if shape == "sentence":
            if next_sentence is None:
                raise ValueError(f"missing sentence row for {expected_id}")
            _raise_if_unexpected_row_id(next_sentence, expected_id, "sentence")
            yield next_sentence
            next_sentence = _next_or_none(sentence_iter)
        elif shape == "tag_list":
            if next_tag is None:
                raise ValueError(f"missing tag-list row for {expected_id}")
            _raise_if_unexpected_row_id(next_tag, expected_id, "tag_list")
            yield next_tag
            next_tag = _next_or_none(tag_iter)
        else:
            raise ValueError(f"unsupported caption_shape: {shape!r}")

    if next_sentence is not None:
        raise ValueError(
            f"extra sentence row after caption_records: {caption_id(next_sentence)}"
        )
    if next_tag is not None:
        raise ValueError(f"extra tag-list row after caption_records: {caption_id(next_tag)}")


def _write_stage3_records(
    input_path: Path,
    *,
    output_path: Path,
    nlp: Any,
    caption_shape: str,
    model: str,
    batch_size: int,
    progress_writer: MixedPipelineProgressWriter | None = None,
) -> dict[str, Any]:
    span_counts: Counter[str] = Counter()
    token_total = 0
    noun_chunk_total = 0
    tag_segment_total = 0
    total = 0

    def records() -> Iterator[Any]:
        nonlocal noun_chunk_total, tag_segment_total, token_total, total
        if caption_shape == "tag_list":
            iterator = iter_stage3_tag_list_records_from_rows(iter_jsonl(input_path), nlp=nlp)
        elif caption_shape == "sentence":
            iterator = iter_stage3_records_from_rows(
                iter_jsonl(input_path),
                nlp=nlp,
                batch_size=batch_size,
            )
        else:
            raise ValueError("caption_shape must be one of: sentence, tag_list")
        for record in iterator:
            total += 1
            token_total += len(record.tokens)
            noun_chunk_total += len(record.noun_chunks)
            tag_segment_total += len(record.tag_segments)
            for span in record.protected_spans:
                kind = span.get("kind")
                if isinstance(kind, str):
                    span_counts[kind] += 1
            if progress_writer is not None:
                progress_writer.maybe_write_stage3(
                    phase=f"stage3_{caption_shape}",
                    total=total,
                    caption_shape=caption_shape,
                    token_total=token_total,
                    noun_chunk_total=noun_chunk_total,
                    tag_segment_total=tag_segment_total,
                    output_path=str(output_path),
                )
            yield record

    written = write_jsonl(output_path, records())
    return {
        "total": total,
        "written": written,
        "model": model,
        "batch_size": batch_size,
        "caption_shape": caption_shape,
        "gpu_mode": nlp.meta.get("gpic_gpu_mode", ""),
        "gpu_enabled": bool(nlp.meta.get("gpic_gpu_enabled", False)),
        "output_path": str(output_path),
        "token_total": token_total,
        "noun_chunk_total": noun_chunk_total,
        "tag_segment_total": tag_segment_total,
        "protected_span_counts": dict(sorted(span_counts.items())),
    }


def combine_stage3_records_in_caption_order(
    *,
    caption_records_path: Path,
    sentence_stage3_path: Path,
    tag_stage3_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    written = write_jsonl(
        output_path,
        _iter_stage3_records_in_caption_order(
            caption_records_path=caption_records_path,
            sentence_stage3_path=sentence_stage3_path,
            tag_stage3_path=tag_stage3_path,
        ),
    )
    shape_counts: Counter[str] = Counter()
    for row in iter_jsonl(output_path):
        shape = _stage3_caption_shape(row)
        shape_counts[shape] += 1
    return {
        "total": written,
        "written": written,
        "output_path": str(output_path),
        "caption_shape_counts": dict(sorted(shape_counts.items())),
        "merge_policy": "caption_records_order",
    }


def _iter_stage3_records_in_caption_order(
    *,
    caption_records_path: Path,
    sentence_stage3_path: Path,
    tag_stage3_path: Path,
) -> Iterator[Mapping[str, Any]]:
    sentence_iter = iter(iter_jsonl(sentence_stage3_path))
    tag_iter = iter(iter_jsonl(tag_stage3_path))
    next_sentence = _next_or_none(sentence_iter)
    next_tag = _next_or_none(tag_iter)

    for caption_record in iter_jsonl(caption_records_path):
        if caption_record.get("skipped"):
            continue
        expected_id = _required_text(caption_record, "caption_id")
        shape = _required_text(caption_record, "caption_shape")
        if shape == "sentence":
            if next_sentence is None:
                raise ValueError(f"missing sentence Stage 3 record for {expected_id}")
            _raise_if_unexpected_caption_id(next_sentence, expected_id, "sentence")
            yield next_sentence
            next_sentence = _next_or_none(sentence_iter)
        elif shape == "tag_list":
            if next_tag is None:
                raise ValueError(f"missing tag-list Stage 3 record for {expected_id}")
            _raise_if_unexpected_caption_id(next_tag, expected_id, "tag_list")
            yield next_tag
            next_tag = _next_or_none(tag_iter)
        else:
            raise ValueError(f"unsupported caption_shape: {shape!r}")

    if next_sentence is not None:
        raise ValueError(
            f"extra sentence Stage 3 record after caption_records: "
            f"{next_sentence.get('caption_id')}"
        )
    if next_tag is not None:
        raise ValueError(
            f"extra tag-list Stage 3 record after caption_records: "
            f"{next_tag.get('caption_id')}"
        )


def _next_or_none(iterator: Iterator[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def _raise_if_unexpected_caption_id(
    stage3_record: Mapping[str, Any],
    expected_id: str,
    shape: str,
) -> None:
    actual_id = _required_text(stage3_record, "caption_id")
    if actual_id != expected_id:
        raise ValueError(
            f"{shape} Stage 3 order mismatch: expected {expected_id}, got {actual_id}"
        )


def _raise_if_unexpected_row_id(
    row: Mapping[str, Any],
    expected_id: str,
    shape: str,
) -> None:
    actual_id = caption_id(dict(row))
    if actual_id != expected_id:
        raise ValueError(f"{shape} row order mismatch: expected {expected_id}, got {actual_id}")


def _stage3_caption_shape(stage3_record: Mapping[str, Any]) -> str:
    meta = stage3_record.get("meta")
    if isinstance(meta, Mapping):
        value = meta.get("caption_shape")
        if isinstance(value, str) and value:
            return value
    value = stage3_record.get("caption_shape")
    if isinstance(value, str) and value:
        return value
    return "sentence"


def _required_text(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def build_mixed_markdown_report(
    *,
    caption_rows_path: Path,
    stage3_records_path: Path,
    canonical_mentions_path: Path,
    canonical_edges_path: Path,
    facts_path: Path,
    output_path: Path,
    start: int,
    limit: int,
    max_object_pairs_per_caption: int,
) -> dict[str, Any]:
    captions = list(iter_jsonl(caption_rows_path))[start : start + limit]
    caption_ids = [caption_id(row) for row in captions]
    caption_id_set = set(caption_ids)
    stage3_records = group_by_caption(
        row for row in iter_jsonl(stage3_records_path) if row["caption_id"] in caption_id_set
    )
    mentions = group_by_caption(
        row for row in iter_jsonl(canonical_mentions_path) if row["caption_id"] in caption_id_set
    )
    edges = group_by_caption(
        row for row in iter_jsonl(canonical_edges_path) if row["caption_id"] in caption_id_set
    )
    facts = group_by_caption(
        row for row in iter_jsonl(facts_path) if row["caption_id"] in caption_id_set
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_report(
            captions,
            stage3_records,
            mentions,
            edges,
            facts,
            start=start,
            max_object_pairs_per_caption=max_object_pairs_per_caption,
        ),
        encoding="utf-8",
    )
    return {
        "output": str(output_path),
        "caption_count": len(captions),
        "start": start,
        "limit": limit,
        "max_object_pairs_per_caption": max_object_pairs_per_caption,
        "stage3_records_included": True,
    }


if __name__ == "__main__":
    main()
