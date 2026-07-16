from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from gpic_concepts_v1.io_jsonl import write_jsonl
from run_mixed_caption_pipeline import (
    combine_caption_rows_in_caption_order,
    combine_stage3_records_in_caption_order,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine sentence/tag-list Stage 1 rows and Stage 3 records in caption order.",
    )
    parser.add_argument("--caption-records", required=True, type=Path)
    parser.add_argument("--sentence-rows", required=True, type=Path)
    parser.add_argument("--tag-rows", required=True, type=Path)
    parser.add_argument("--mixed-caption-rows", required=True, type=Path)
    parser.add_argument("--sentence-stage3", required=True, type=Path)
    parser.add_argument("--tag-stage3", required=True, type=Path)
    parser.add_argument("--stage3-output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mixed_caption_rows_summary = combine_caption_rows_in_caption_order(
        caption_records_path=args.caption_records,
        sentence_rows_path=args.sentence_rows,
        tag_rows_path=args.tag_rows,
        output_path=args.mixed_caption_rows,
    )
    combined_stage3_summary = combine_stage3_records_in_caption_order(
        caption_records_path=args.caption_records,
        sentence_stage3_path=args.sentence_stage3,
        tag_stage3_path=args.tag_stage3,
        output_path=args.stage3_output,
    )
    summary = {
        "mixed_caption_rows": mixed_caption_rows_summary,
        "combined_stage3": combined_stage3_summary,
    }
    write_jsonl(args.summary, [summary])
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
