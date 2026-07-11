from __future__ import annotations

import argparse
import os
import runpy
import sys
import threading
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a Python script in-process with a hard os._exit timeout."
    )
    parser.add_argument("--timeout-seconds", type=int, default=60)
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
