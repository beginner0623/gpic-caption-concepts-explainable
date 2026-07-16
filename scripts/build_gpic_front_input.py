from __future__ import annotations

import argparse
import gzip
import json
import os
import time
from pathlib import Path

from gpic_concepts_v1.atomic_io import atomic_text_writer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a front-sequential GPIC input JSONL.GZ from sorted split shards. "
            "Merged helper files are ignored."
        )
    )
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--limit", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument(
        "--pattern",
        default="gpic_train_*.jsonl.gz",
        help="Shard filename glob. Default: gpic_train_*.jsonl.gz",
    )
    parser.add_argument(
        "--policy",
        default="GPIC-Nano train front sequential rows from sorted train shard files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be positive")

    source_dir = args.source_dir
    shards = [
        path
        for path in sorted(source_dir.glob(args.pattern), key=lambda item: item.name)
        if "_merged_" not in path.name
    ]
    if not shards:
        raise SystemExit(f"no shards matched: {source_dir / args.pattern}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    temp_output = args.output.with_name(
        f".{args.output.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )

    started = time.perf_counter()
    records = 0
    used_shards: list[list[object]] = []
    try:
        with gzip.open(temp_output, "wt", encoding="utf-8", newline="") as out_handle:
            for shard in shards:
                shard_records = 0
                with gzip.open(shard, "rt", encoding="utf-8") as in_handle:
                    for line in in_handle:
                        if not line.strip():
                            continue
                        out_handle.write(line)
                        records += 1
                        shard_records += 1
                        if records >= args.limit:
                            break
                if shard_records:
                    used_shards.append([shard.name, shard_records])
                if records >= args.limit:
                    break
        if records < args.limit:
            raise RuntimeError(
                f"only {records} records available before source shards ended; "
                f"requested {args.limit}"
            )
        os.replace(temp_output, args.output)
    except Exception:
        temp_output.unlink(missing_ok=True)
        raise

    summary = {
        "output": str(args.output),
        "records": records,
        "used_shards": used_shards,
        "seconds": round(time.perf_counter() - started, 3),
        "policy": args.policy,
        "source_dir": str(source_dir),
        "pattern": args.pattern,
    }
    with atomic_text_writer(args.summary) as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
