from __future__ import annotations

import argparse
import os
import runpy
import sys
import threading
import time
from pathlib import Path


STAGE456_TIMEOUT_GUARDED_SCRIPTS = frozenset(
    {
        "run_mixed_caption_pipeline.py",
        "run_stage4_extract_raw.py",
        "run_stage5_canonicalize.py",
        "run_stage6_export_counts.py",
    }
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a Python script in-process with a hard os._exit timeout."
    )
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument(
        "--allow-stage456-timeout",
        action="store_true",
        help=(
            "Explicitly allow the hard timeout wrapper for Stage 4/5/6 scripts. "
            "Use only for deliberately bounded diagnostics, never production-scale runs."
        ),
    )
    parser.add_argument("script")
    args, script_args = parser.parse_known_args()

    if args.timeout_seconds < 1:
        raise SystemExit("--timeout-seconds must be greater than zero.")

    root = Path(__file__).absolute().parent.parent
    script_path = Path(args.script)
    if not script_path.is_absolute():
        script_path = root / script_path
    if not script_path.exists():
        raise SystemExit(f"script not found: {script_path}")
    _raise_if_forbidden_timeout_target(
        script_path,
        script_args,
        allow_stage456_timeout=args.allow_stage456_timeout,
    )

    temp_root = script_temp_root(root)
    os.environ["TMP"] = str(temp_root)
    os.environ["TEMP"] = str(temp_root)
    os.environ["TMPDIR"] = str(temp_root)
    os.environ["PYTHONUNBUFFERED"] = "1"

    start = time.perf_counter()
    timer = threading.Timer(
        args.timeout_seconds,
        timeout_exit,
        kwargs={
            "script": script_path,
            "start": start,
            "timeout_seconds": args.timeout_seconds,
        },
    )
    timer.daemon = True
    old_argv = sys.argv[:]
    try:
        timer.start()
        sys.argv = [str(script_path), *script_args]
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    finally:
        sys.argv = old_argv
        timer.cancel()
    return 0


def _raise_if_forbidden_timeout_target(
    script_path: Path,
    script_args: list[str],
    *,
    allow_stage456_timeout: bool = False,
) -> None:
    if allow_stage456_timeout:
        return
    if script_path.name not in STAGE456_TIMEOUT_GUARDED_SCRIPTS:
        return
    hint = ""
    if _has_explicit_small_limit(script_args):
        hint = (
            " If this is a deliberately bounded diagnostic, rerun with "
            "--allow-stage456-timeout."
        )
    raise SystemExit(
        "Refusing to run Stage 4/5/6 through the hard timeout wrapper: "
        f"{script_path.name}. Large Stage 4/5/6 jobs have no checkpoint/resume "
        "and must be launched through the monitored background-job path without "
        "a wall-clock kill timeout."
        + hint
    )


def _has_explicit_small_limit(script_args: list[str]) -> bool:
    for index, arg in enumerate(script_args):
        if arg == "--limit" and index + 1 < len(script_args):
            return _safe_int(script_args[index + 1]) is not None
        if arg.startswith("--limit="):
            return _safe_int(arg.split("=", 1)[1]) is not None
    return False


def _safe_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def timeout_exit(*, script: Path, start: float, timeout_seconds: int) -> None:
    elapsed = time.perf_counter() - start
    print(
        f"\nSCRIPT_TIMEOUT: killed {script} after "
        f"{elapsed:.3f}s limit={timeout_seconds}s",
        file=sys.stderr,
        flush=True,
    )
    os._exit(124)


def script_temp_root(root: Path) -> Path:
    configured = os.environ.get("GPIC_SCRIPT_TEMP_ROOT")
    if configured:
        temp_root = Path(configured)
    else:
        temp_root = root.parent / ".gpic_tmp" / "gpic-explainable-link-scripts"
    temp_root.mkdir(parents=True, exist_ok=True)
    return temp_root


if __name__ == "__main__":
    raise SystemExit(main())
