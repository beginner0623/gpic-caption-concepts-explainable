from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.stage1_loader import run_stage1_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run v1 Stage 1 over GPIC JSONL or JSONL.GZ caption rows.",
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Input .jsonl or .jsonl.gz file. Can be repeated.",
    )
    parser.add_argument(
        "--caption-records",
        required=True,
        help="Output caption_records.jsonl path.",
    )
    parser.add_argument(
        "--sentence-rows",
        help="Optional output JSONL path for rows with caption_shape=sentence.",
    )
    parser.add_argument(
        "--tag-rows",
        help="Optional output JSONL path for rows with caption_shape=tag_list.",
    )
    parser.add_argument(
        "--summary",
        help="Optional output JSONL path for one Stage 1 summary row.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of rows to process across all inputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_stage1_records(
        args.input,
        caption_records_path=args.caption_records,
        sentence_rows_path=args.sentence_rows,
        tag_rows_path=args.tag_rows,
        summary_path=args.summary,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
