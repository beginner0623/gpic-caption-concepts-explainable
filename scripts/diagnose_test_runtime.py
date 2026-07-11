from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


GROUPS: dict[str, list[str]] = {
    "collect": ["--collect-only", "-q"],
    "light": [
        "-q",
        "--durations=0",
        "tests/test_schema.py",
        "tests/test_io_jsonl.py",
        "tests/test_stage1.py",
        "tests/test_stage1_loader.py",
        "tests/test_stage2_preprocess.py",
        "tests/test_stage4_extract_raw.py::Stage4ExtractRawTest",
        "tests/test_stage5_canonicalize.py",
        "tests/test_stage6_export_counts.py",
        "tests/test_benchmark_fast_pipeline.py",
    ],
    "stage3": [
        "-q",
        "--durations=0",
        "tests/test_stage3_annotate.py::Stage3AnnotateTest",
    ],
    "stage4-doc": [
        "-q",
        "--durations=0",
        "tests/test_stage4_extract_raw.py::Stage4DocDirectExtractionTest",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded pytest runtime probes without starting full tests."
    )
    parser.add_argument(
        "--group",
        choices=["collect", "light", "stage3", "stage4-doc"],
        default="collect",
    )
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    root = Path(__file__).absolute().parent.parent
    temp_root = test_temp_root(root)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = temp_root / f"test_runtime_{stamp}.summary.tsv"
    groups = [args.group]

    rows: list[dict[str, object]] = []
    for group in groups:
        rows.append(
            run_group(
                group=group,
                root=root,
                temp_root=temp_root,
                stamp=stamp,
                timeout_seconds=args.timeout_seconds,
            )
        )
        write_summary(summary_path, rows)

    print_table(rows)
    print(f"summary: {summary_path}")
    return 1 if any(row["exit_code"] not in (0, "0") for row in rows) else 0


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


def run_group(
    *,
    group: str,
    root: Path,
    temp_root: Path,
    stamp: str,
    timeout_seconds: int,
) -> dict[str, object]:
    stdout_path = temp_root / f"test_runtime_{stamp}_{group}.stdout.log"
    stderr_path = temp_root / f"test_runtime_{stamp}_{group}.stderr.log"
    command = [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider"] + GROUPS[group]
    env = os.environ.copy()
    env["TMP"] = str(temp_root)
    env["TEMP"] = str(temp_root)
    env["TMPDIR"] = str(temp_root)
    env["PYTHONUNBUFFERED"] = "1"

    started_at = datetime.now().isoformat(timespec="seconds")
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = time.perf_counter() - start
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        exit_code: int | str = completed.returncode
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        exit_code = "TIMEOUT"

    return {
        "group": group,
        "started_at": started_at,
        "elapsed_seconds": round(elapsed, 3),
        "timeout_seconds": timeout_seconds,
        "exit_code": exit_code,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }


def write_summary(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "group",
                "started_at",
                "elapsed_seconds",
                "timeout_seconds",
                "exit_code",
                "stdout",
                "stderr",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows: list[dict[str, object]]) -> None:
    print("group\telapsed_seconds\ttimeout_seconds\texit_code")
    for row in rows:
        print(
            f"{row['group']}\t{row['elapsed_seconds']}\t"
            f"{row['timeout_seconds']}\t{row['exit_code']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
