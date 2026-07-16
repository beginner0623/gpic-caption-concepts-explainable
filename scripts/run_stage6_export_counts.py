from __future__ import annotations

import argparse
from pathlib import Path

from gpic_concepts_v1.cli_memory import add_memory_safety_args, memory_safety_kwargs
from gpic_concepts_v1.stage6_export_counts import run_stage6_export_counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 6 count export.")
    parser.add_argument(
        "--canonical-mentions",
        required=True,
        help="Stage 5 canonical_mentions.jsonl",
    )
    parser.add_argument(
        "--canonical-edges",
        required=True,
        help="Stage 5 canonical_edges.jsonl",
    )
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--summary", default=None, help="Optional summary JSONL path")
    add_memory_safety_args(parser, stage_name="Stage 6")
    parser.add_argument(
        "--count-backend",
        choices=("sqlite", "memory"),
        default="sqlite",
        help=(
            "Count accumulator backend. sqlite is the production-safe default; "
            "memory is only for bounded diagnostics."
        ),
    )
    parser.add_argument(
        "--sqlite-db",
        default=None,
        help=(
            "Optional SQLite accumulator database path. Defaults to "
            "<output-dir>/stage6_count_accumulators.sqlite3."
        ),
    )
    parser.add_argument(
        "--sqlite-cache-rows",
        type=int,
        default=50_000,
        help="Maximum unique count keys buffered in RAM before flushing to SQLite.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_stage6_export_counts(
        Path(args.canonical_mentions),
        Path(args.canonical_edges),
        output_dir=Path(args.output_dir),
        summary_path=Path(args.summary) if args.summary else None,
        **memory_safety_kwargs(args),
        count_backend=args.count_backend,
        sqlite_db_path=Path(args.sqlite_db) if args.sqlite_db else None,
        sqlite_cache_rows=args.sqlite_cache_rows,
    )
    print(summary)


if __name__ == "__main__":
    main()
