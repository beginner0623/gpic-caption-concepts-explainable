from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import unittest
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run unittest in-process with a hard os._exit timeout."
    )
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args, unittest_args = parser.parse_known_args()

    unittest_args = list(unittest_args)
    if unittest_args and unittest_args[0] == "--":
        unittest_args = unittest_args[1:]
    if not unittest_args:
        unittest_args = ["discover", "-s", "tests"]
    if args.timeout_seconds < 1:
        raise SystemExit("--timeout-seconds must be greater than zero.")

    root = Path(__file__).absolute().parent.parent
    temp_root = test_temp_root(root)
    os.environ["TMP"] = str(temp_root)
    os.environ["TEMP"] = str(temp_root)
    os.environ["TMPDIR"] = str(temp_root)
    os.environ["PYTHONUNBUFFERED"] = "1"

    start = time.perf_counter()
    timer = threading.Timer(
        args.timeout_seconds,
        timeout_exit,
        kwargs={"start": start, "timeout_seconds": args.timeout_seconds},
    )
    timer.daemon = True
    timer.start()
    try:
        program = unittest.main(
            module=None,
            argv=["unittest"] + unittest_args,
            exit=False,
        )
    finally:
        timer.cancel()

    return 0 if program.result.wasSuccessful() else 1


def timeout_exit(*, start: float, timeout_seconds: int) -> None:
    elapsed = time.perf_counter() - start
    print(
        f"\nUNITTEST_TIMEOUT: killed unittest after "
        f"{elapsed:.3f}s limit={timeout_seconds}s",
        file=sys.stderr,
        flush=True,
    )
    os._exit(124)


def test_temp_root(root: Path) -> Path:
    configured = os.environ.get("GPIC_TEST_TEMP_ROOT")
    if configured:
        temp_root = Path(configured)
    else:
        temp_root = root / "outputs" / ".test_tmp" / "gpic-explainable-link-tests"
    temp_root.mkdir(parents=True, exist_ok=True)
    return temp_root


if __name__ == "__main__":
    raise SystemExit(main())
