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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_stage6_export_counts(
        Path(args.canonical_mentions),
        Path(args.canonical_edges),
        output_dir=Path(args.output_dir),
        summary_path=Path(args.summary) if args.summary else None,
        **memory_safety_kwargs(args),
    )
    print(summary)


if __name__ == "__main__":
    main()
