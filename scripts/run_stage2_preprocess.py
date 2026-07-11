from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.stage2_preprocess import run_stage2_preprocess


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run v1 Stage 2 preprocessing over Stage 1 sentence rows.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input sentence_rows.jsonl from Stage 1.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output stage2_records.jsonl path.",
    )
    parser.add_argument(
        "--summary",
        help="Optional output JSONL path for one Stage 2 summary row.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of sentence rows to process.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_stage2_preprocess(
        args.input,
        output_path=args.output,
        summary_path=args.summary,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
