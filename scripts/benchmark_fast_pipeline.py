from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.io_jsonl import iter_jsonl
from gpic_concepts_v1.stage2_preprocess import load_object_mwes
from gpic_concepts_v1.stage3_annotate import (
    DEFAULT_STAGE3_BATCH_SIZE,
    DEFAULT_STAGE3_MODEL,
    iter_annotated_docs_from_rows,
    iter_stage3_records_from_rows,
    make_stage3_nlp,
)
from gpic_concepts_v1.stage4_extract_raw import (
    extract_raw_concepts_from_doc,
    extract_raw_concepts_from_stage3_record,
)
from gpic_concepts_v1.stage5_canonicalize import (
    canonicalize_raw_graph,
    load_stage5_lexicons,
)
from gpic_concepts_v1.stage6_export_counts import export_count_facts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark the v1 sentence pipeline in one process without writing "
            "intermediate Stage 3-5 JSONL files."
        ),
    )
    parser.add_argument("--input", required=True, help="Stage 1 sentence_rows.jsonl")
    parser.add_argument(
        "--object-mwes",
        required=True,
        help="Object MWE TSV lexicon path.",
    )
    parser.add_argument(
        "--lexicon-dir",
        default="resources/lexicons",
        help="Directory containing Stage 5 TSV lexicons.",
    )
    parser.add_argument(
        "--summary",
        help="Optional path for one JSON summary file.",
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
        help="Optional maximum number of sentence rows to process.",
    )
    parser.add_argument(
        "--raw-extraction-mode",
        choices=("stage3-record", "doc-direct"),
        default="stage3-record",
        help=(
            "stage3-record preserves the original Stage 3 evidence-table round trip. "
            "doc-direct applies the same Stage 4 rules directly to annotated spaCy Docs."
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
    gpu_mode = "require" if args.require_gpu else "prefer" if args.prefer_gpu else "none"

    setup_start = perf_counter()
    nlp = make_stage3_nlp(args.model, gpu_mode=gpu_mode)
    object_mwes = load_object_mwes(args.object_mwes)
    lexicons = load_stage5_lexicons(args.lexicon_dir)
    setup_seconds = perf_counter() - setup_start

    stage3_stage4_start = perf_counter()
    raw_mentions = []
    raw_edges = []
    sentence_count = 0
    if args.raw_extraction_mode == "doc-direct":
        for annotated in iter_annotated_docs_from_rows(
            iter_jsonl(args.input),
            nlp=nlp,
            object_mwes=object_mwes,
            batch_size=args.batch_size,
            limit=args.limit,
        ):
            sentence_count += 1
            result = extract_raw_concepts_from_doc(annotated.caption_id, annotated.doc)
            raw_mentions.extend(result.raw_mentions)
            raw_edges.extend(result.raw_edges)
    else:
        for stage3_record in iter_stage3_records_from_rows(
            iter_jsonl(args.input),
            nlp=nlp,
            object_mwes=object_mwes,
            batch_size=args.batch_size,
            limit=args.limit,
        ):
            sentence_count += 1
            result = extract_raw_concepts_from_stage3_record(stage3_record.to_dict())
            raw_mentions.extend(result.raw_mentions)
            raw_edges.extend(result.raw_edges)
    stage3_stage4_seconds = perf_counter() - stage3_stage4_start

    stage5_start = perf_counter()
    canonical = canonicalize_raw_graph(raw_mentions, raw_edges, lexicons=lexicons)
    stage5_seconds = perf_counter() - stage5_start

    stage6_start = perf_counter()
    counts = export_count_facts(canonical.canonical_mentions, canonical.canonical_edges)
    stage6_seconds = perf_counter() - stage6_start

    processing_seconds = stage3_stage4_seconds + stage5_seconds + stage6_seconds
    total_seconds = setup_seconds + processing_seconds
    table_row_counts = {
        file_name: len(rows)
        for file_name, rows in sorted(counts.count_tables.items())
    }
    fact_type_counts: dict[str, int] = {}
    for fact in counts.facts:
        fact_type_counts[fact.fact_type] = fact_type_counts.get(fact.fact_type, 0) + 1

    summary = {
        "input_path": args.input,
        "sentence_count": sentence_count,
        "model": args.model,
        "batch_size": args.batch_size,
        "raw_extraction_mode": args.raw_extraction_mode,
        "gpu_mode": nlp.meta.get("gpic_gpu_mode", gpu_mode),
        "gpu_enabled": bool(nlp.meta.get("gpic_gpu_enabled", False)),
        "object_mwe_lexicon_size": len(object_mwes),
        "raw_mention_total": len(raw_mentions),
        "raw_edge_total": len(raw_edges),
        "canonical_mention_total": len(canonical.canonical_mentions),
        "canonical_edge_total": len(canonical.canonical_edges),
        "fact_total": len(counts.facts),
        "fact_type_counts": dict(sorted(fact_type_counts.items())),
        "table_row_counts": table_row_counts,
        "setup_seconds": setup_seconds,
        "stage3_stage4_seconds": stage3_stage4_seconds,
        "stage5_seconds": stage5_seconds,
        "stage6_seconds": stage6_seconds,
        "processing_seconds": processing_seconds,
        "total_seconds": total_seconds,
        "processing_captions_per_second": (
            sentence_count / processing_seconds if processing_seconds else 0.0
        ),
        "total_captions_per_second": (
            sentence_count / total_seconds if total_seconds else 0.0
        ),
    }

    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
