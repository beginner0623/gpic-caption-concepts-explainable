from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.inventory_validation import (
    final_manual_resolution_blockers,
    read_inventory_rows,
)
from gpic_concepts_v1.cli_memory import add_memory_safety_args, memory_safety_kwargs
from gpic_concepts_v1.io_jsonl import write_jsonl
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
    parser.add_argument(
        "--attribute-inventory",
        help=(
            "Resolved GPIC observed attribute inventory TSV. Required for formal "
            "Stage 5 runs unless --allow-unresolved-attribute-preview is used."
        ),
    )
    parser.add_argument(
        "--allow-unresolved-attribute-preview",
        action="store_true",
        help=(
            "Preview/debug mode only: allow Stage 5 to run without a completed "
            "attribute inventory gate. Output must not be treated as formal."
        ),
    )
    add_memory_safety_args(parser, stage_name="Stage 5")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.allow_unresolved_attribute_preview:
        preview_mode = True
    elif args.attribute_inventory:
        preview_mode = False
        _raise_if_attribute_inventory_not_ready(Path(args.attribute_inventory))
    else:
        raise SystemExit(
            "--attribute-inventory is required for formal Stage 5 canonicalization. "
            "Use --allow-unresolved-attribute-preview only for preview/debug runs."
        )
    summary = run_stage5_canonicalize(
        Path(args.raw_mentions),
        Path(args.raw_edges),
        lexicon_dir=Path(args.lexicon_dir),
        canonical_mentions_path=Path(args.canonical_mentions),
        canonical_edges_path=Path(args.canonical_edges),
        summary_path=None,
        **memory_safety_kwargs(args),
    )
    summary["formal_attribute_inventory_gate"] = not preview_mode
    if preview_mode:
        summary["preview_warning"] = "unresolved_attribute_inventory_preview"
    if args.summary:
        write_jsonl(Path(args.summary), [summary])
    print(summary)


def _raise_if_attribute_inventory_not_ready(path: Path) -> None:
    rows = read_inventory_rows(path)
    blockers = final_manual_resolution_blockers(
        rows,
        require_canonical_surface_for_selected_synset=True,
    )
    if not blockers:
        return
    raise SystemExit(
        json.dumps(
            {
                "status": "blocked_attribute_inventory_before_stage5",
                "attribute_inventory": str(path),
                "rows": len(rows),
                "blocked_rows": len(blockers),
                "blocked_examples": blockers[:10],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
