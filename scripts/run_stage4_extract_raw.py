from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.stage4_extract_raw import run_stage4_extract_raw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run v1 Stage 4 raw concept extraction over Stage 3 records.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input stage3_records.jsonl.",
    )
    parser.add_argument(
        "--raw-mentions",
        required=True,
        help="Output raw_mentions.jsonl path.",
    )
    parser.add_argument(
        "--raw-edges",
        required=True,
        help="Output raw_edges.jsonl path.",
    )
    parser.add_argument(
        "--summary",
        help="Optional output JSONL path for one Stage 4 summary row.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of Stage 3 rows to process.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_stage4_extract_raw(
        args.input,
        raw_mentions_path=args.raw_mentions,
        raw_edges_path=args.raw_edges,
        summary_path=args.summary,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
