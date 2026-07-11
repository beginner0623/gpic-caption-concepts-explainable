from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run pytest with a hard subprocess timeout."
    )
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args, pytest_args = parser.parse_known_args()

    pytest_args = list(pytest_args)
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    if not pytest_args:
        raise SystemExit("No pytest arguments were provided.")
    if args.timeout_seconds < 1:
        raise SystemExit("--timeout-seconds must be greater than zero.")

    root = Path(__file__).absolute().parent.parent
    temp_root = test_temp_root(root)
    env = os.environ.copy()
    env["TMP"] = str(temp_root)
    env["TEMP"] = str(temp_root)
    env["TMPDIR"] = str(temp_root)
    env["PYTHONUNBUFFERED"] = "1"

    command = [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider"] + pytest_args
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        if exc.stdout:
            print(exc.stdout, end="")
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        print(
            f"\nPYTEST_TIMEOUT: killed pytest after "
            f"{elapsed:.3f}s limit={args.timeout_seconds}s",
            file=sys.stderr,
        )
        return 124

    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def test_temp_root(root: Path) -> Path:
    configured = os.environ.get("GPIC_TEST_TEMP_ROOT")
    if configured:
        temp_root = Path(configured)
    else:
        creator_temp = Path(r"C:\Users\Public\Documents\ESTsoft\CreatorTemp")
        if creator_temp.exists():
            temp_root = creator_temp / "gpic-explainable-link-tests"
        else:
            temp_root = root.parent / ".gpic_tmp" / "gpic-explainable-link-tests"
    temp_root.mkdir(parents=True, exist_ok=True)
    return temp_root


if __name__ == "__main__":
    raise SystemExit(main())
