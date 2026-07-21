from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SRC = ROOT / "src"
for path in (SCRIPT_DIR, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_patient_action_agent_triples_from_facts import (
    _action_mention_id,
    _flush_caption_roles,
    _role_fact_from_fact,
    _write_progress,
    write_triples_tsv,
)
from build_report_caption_index_from_stage5 import _collect_stage5_dirs
from gpic_concepts_v1.io_jsonl import to_jsonable
from gpic_concepts_v1.stage6_export_counts import (
    _CaptionGroupReader,
    _caption_facts,
    _coerce_canonical_edge,
    _coerce_canonical_mention,
    _iter_caption_groups,
)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build patient-action-agent triple counts from Stage 5 canonical "
            "mentions/edges without materializing Stage 6 facts.jsonl."
        ),
    )
    parser.add_argument("--output-tsv", required=True, type=Path)
    parser.add_argument("--stage5-dir", action="append", type=Path, default=[])
    parser.add_argument("--stage456-sharded-dir", type=Path)
    parser.add_argument("--progress-json", type=Path)
    parser.add_argument("--progress-every-captions", type=int, default=1000)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.output_tsv.exists() and not args.overwrite:
        raise SystemExit(f"output exists: {args.output_tsv}")
    stage5_dirs = _collect_stage5_dirs(
        explicit_stage5_dirs=args.stage5_dir,
        stage456_sharded_dir=args.stage456_sharded_dir,
    )
    if not stage5_dirs:
        raise SystemExit("no Stage 5 inputs supplied")

    started_at = time.time()
    accumulators, summary = build_triples_from_stage5_dirs(
        stage5_dirs,
        progress_json=args.progress_json,
        progress_every_captions=args.progress_every_captions,
        started_at=started_at,
    )
    write_triples_tsv(args.output_tsv, accumulators)
    summary.update(
        {
            "elapsed_seconds": round(time.time() - started_at, 3),
            "output_tsv": str(args.output_tsv),
            "triple_rows": len(accumulators),
        },
    )
    if args.progress_json:
        _write_progress(args.progress_json, {"phase": "complete", **summary})
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def build_triples_from_stage5_dirs(
    stage5_dirs: list[Path],
    *,
    progress_json: Path | None = None,
    progress_every_captions: int = 1000,
    started_at: float | None = None,
) -> tuple[dict[tuple[str, str, str], Any], dict[str, Any]]:
    started_at = time.time() if started_at is None else started_at
    accumulators: dict[tuple[str, str, str], Any] = {}
    caption_groups_processed = 0
    fact_total = 0
    event_role_rows = 0

    for stage5_dir in stage5_dirs:
        mentions_path = stage5_dir / "canonical_mentions.jsonl"
        edges_path = stage5_dir / "canonical_edges.jsonl"
        mention_groups = _iter_caption_groups(mentions_path, _coerce_canonical_mention)
        edge_groups = _CaptionGroupReader(edges_path, _coerce_canonical_edge)
        for caption_id, mentions in mention_groups:
            edges = edge_groups.take_if_caption(caption_id)
            roles_by_action: dict[str, dict[str, list[Any]]] = defaultdict(
                lambda: defaultdict(list),
            )
            for fact in _caption_facts(mentions, edges, start_index=fact_total):
                fact_total += 1
                if fact.fact_type != "event_role":
                    continue
                event_role_rows += 1
                fact_payload = to_jsonable(fact)
                role_fact = _role_fact_from_fact(fact_payload)
                action_mention_id = _action_mention_id(fact_payload)
                if role_fact is None or not action_mention_id:
                    continue
                roles_by_action[action_mention_id][role_fact.role].append(role_fact)
            _flush_caption_roles(roles_by_action, accumulators)

            caption_groups_processed += 1
            if (
                progress_json
                and caption_groups_processed % max(1, progress_every_captions) == 0
            ):
                _write_progress(
                    progress_json,
                    {
                        "phase": "streaming_stage5",
                        "caption_groups_processed": caption_groups_processed,
                        "event_role_rows": event_role_rows,
                        "fact_total": fact_total,
                        "stage5_dir": str(stage5_dir),
                        "triple_rows": len(accumulators),
                        "elapsed_seconds": round(time.time() - started_at, 3),
                    },
                )

        leftover_caption = edge_groups.peek_caption()
        if leftover_caption is not None:
            raise ValueError(
                "canonical_edges contains a caption with no matching canonical_mentions "
                "group or the files are not in the same caption order: "
                f"{leftover_caption!r}",
            )

    return accumulators, {
        "source_mode": "stage5_direct",
        "stage5_dirs": [str(path) for path in stage5_dirs],
        "caption_groups_processed": caption_groups_processed,
        "event_role_rows": event_role_rows,
        "fact_total": fact_total,
    }


if __name__ == "__main__":
    raise SystemExit(main())
