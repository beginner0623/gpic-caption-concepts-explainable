"""Shared CLI options for memory-safe large pipeline stages."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def add_memory_safety_args(parser: argparse.ArgumentParser, *, stage_name: str) -> None:
    parser.add_argument(
        "--max-rss-gib",
        type=float,
        default=None,
        help=(
            "Optional explicit process RSS safety limit in GiB. Overrides the "
            "memory-limit/fraction/reserve calculation."
        ),
    )
    parser.add_argument(
        "--memory-limit-gib",
        type=float,
        default=None,
        help=(
            f"Optional container/pod memory limit in GiB. When omitted, {stage_name} "
            "tries to read the active cgroup memory limit."
        ),
    )
    parser.add_argument(
        "--rss-limit-fraction",
        type=float,
        default=0.75,
        help=f"Fraction of the memory limit allowed for {stage_name} RSS.",
    )
    parser.add_argument(
        "--rss-reserve-gib",
        type=float,
        default=16.0,
        help="Minimum memory headroom in GiB to leave under the memory limit.",
    )
    parser.add_argument(
        "--progress",
        default=None,
        help=f"Optional single JSON progress/checkpoint path updated during {stage_name}.",
    )


def memory_safety_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "max_rss_gib": args.max_rss_gib,
        "memory_limit_gib": args.memory_limit_gib,
        "rss_limit_fraction": args.rss_limit_fraction,
        "rss_reserve_gib": args.rss_reserve_gib,
        "progress_path": Path(args.progress) if args.progress else None,
    }
