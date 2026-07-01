from __future__ import annotations

import argparse
from pathlib import Path

from gpic_concepts_v1.stage5_canonicalize import run_stage5_canonicalize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 5 canonicalization.")
    parser.add_argument("--raw-mentions", required=True, help="Stage 4 raw_mentions.jsonl")
    parser.add_argument("--raw-edges", required=True, help="Stage 4 raw_edges.jsonl")
    parser.add_argument(
        "--lexicon-dir",
        default="resources/lexicons",
        help="Directory containing Stage 5 TSV lexicons",
    )
    parser.add_argument(
        "--canonical-mentions",
        required=True,
        help="Output canonical_mentions.jsonl",
    )
    parser.add_argument(
        "--canonical-edges",
        required=True,
        help="Output canonical_edges.jsonl",
    )
    parser.add_argument("--summary", default=None, help="Optional summary JSONL path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_stage5_canonicalize(
        Path(args.raw_mentions),
        Path(args.raw_edges),
        lexicon_dir=Path(args.lexicon_dir),
        canonical_mentions_path=Path(args.canonical_mentions),
        canonical_edges_path=Path(args.canonical_edges),
        summary_path=Path(args.summary) if args.summary else None,
    )
    print(summary)


if __name__ == "__main__":
    main()
