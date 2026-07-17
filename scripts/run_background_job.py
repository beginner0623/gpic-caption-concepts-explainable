from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from incident_gate import (
    RUN_TOKEN_ENV,
    STATE_DIR_ENV,
    assert_pipeline_clear,
    create_incident,
)


CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Start or inspect a detached repository job without PowerShell "
            "Start-Process or cmd.exe start."
        )
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--cwd", required=True)
    start.add_argument("--stdout", required=True)
    start.add_argument("--stderr", required=True)
    start.add_argument("--pid-file", required=True)
    start.add_argument("--name", default="")
    start.add_argument("--overwrite-logs", action="store_true")
    start.add_argument("job_args", nargs=argparse.REMAINDER)

    status = subparsers.add_parser("status")
    status.add_argument("--pid-file", required=True)
    status.add_argument("--progress-output")

    watch = subparsers.add_parser("watch")
    watch.add_argument("--pid-file", required=True)
    watch.add_argument("--interval-seconds", type=int, default=60)
    watch.add_argument("--max-seconds", type=int, default=3600)
    watch.add_argument("--expect-output")
    watch.add_argument("--progress-output")

    adopt = subparsers.add_parser("adopt")
    adopt.add_argument("--pid", type=int, required=True)
    adopt.add_argument("--pid-file", required=True)
    adopt.add_argument("--name", default="")
    adopt.add_argument("--cwd", required=True)
    adopt.add_argument("--stdout", default="")
    adopt.add_argument("--stderr", default="")
    adopt.add_argument("--job-command", default="")

    args = parser.parse_args()
    if args.action == "start":
        return start_job(args)
    if args.action == "status":
        return status_job(args)
    if args.action == "watch":
        return watch_job(args)
    if args.action == "adopt":
        return adopt_job(args)
    raise AssertionError(args.action)


def start_job(args: argparse.Namespace) -> int:
    job_args = list(args.job_args)
    if job_args and job_args[0] == "--":
        job_args = job_args[1:]
    if not job_args:
        raise SystemExit("start requires a command after --")

    cwd = Path(args.cwd).resolve()
    if not cwd.exists():
        raise SystemExit(f"cwd does not exist: {cwd}")
    state_dir = cwd / ".pipeline_state"
    assert_pipeline_clear(state_dir=state_dir)

    incident_runner = Path(__file__).with_name("incident_gate.py").resolve()
    guarded_job_args = [
        sys.executable,
        str(incident_runner),
        "--state-dir",
        str(state_dir),
        "run",
        "--name",
        args.name or Path(job_args[0]).name,
        "--",
        *job_args,
    ]
    child_env = os.environ.copy()
    child_env.pop(RUN_TOKEN_ENV, None)
    child_env[STATE_DIR_ENV] = str(state_dir)

    stdout_path = Path(args.stdout).resolve()
    stderr_path = Path(args.stderr).resolve()
    pid_path = Path(args.pid_file).resolve()
    for path in (stdout_path, stderr_path, pid_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    mode = "w" if args.overwrite_logs else "a"
    with stdout_path.open(mode, encoding="utf-8") as stdout, stderr_path.open(
        mode, encoding="utf-8"
    ) as stderr:
        flags = 0
        if os.name == "nt":
            flags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        try:
            process = subprocess.Popen(
                guarded_job_args,
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
                close_fds=True,
                env=child_env,
            )
        except BaseException as exc:
            create_incident(
                failure_type="background_launch_failure",
                summary=f"Failed to launch detached job: {args.name or job_args[0]}",
                details={
                    "cwd": str(cwd),
                    "command": job_args,
                    "exception": repr(exc),
                },
                state_dir=state_dir,
            )
            raise

    record = {
        "name": args.name,
        "pid": process.pid,
        "cwd": str(cwd),
        "command": job_args,
        "guarded_command": guarded_job_args,
        "pipeline_state_dir": str(state_dir),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json_atomic(pid_path, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


def status_job(args: argparse.Namespace) -> int:
    pid_path = Path(args.pid_file).resolve()
    if not pid_path.exists():
        print(json.dumps({"status": "missing_pid_file", "pid_file": str(pid_path)}))
        return 2
    record = json.loads(pid_path.read_text(encoding="utf-8"))
    pid = int(record["pid"])
    record["running"] = process_is_running(pid)
    if args.progress_output:
        record["progress"] = read_progress_snapshot(Path(args.progress_output))
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


def watch_job(args: argparse.Namespace) -> int:
    if args.interval_seconds < 1:
        raise SystemExit("--interval-seconds must be >= 1")
    if args.max_seconds < 1:
        raise SystemExit("--max-seconds must be >= 1")
    pid_path = Path(args.pid_file).resolve()
    if not pid_path.exists():
        print(json.dumps({"status": "missing_pid_file", "pid_file": str(pid_path)}))
        return 2

    started = time.monotonic()
    last_record: dict | None = None
    while True:
        record = json.loads(pid_path.read_text(encoding="utf-8"))
        pid = int(record["pid"])
        running = process_is_running(pid)
        output_exists = bool(args.expect_output and Path(args.expect_output).exists())
        last_record = {
            **record,
            "running": running,
            "expect_output": args.expect_output or "",
            "expect_output_exists": output_exists,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        if args.progress_output:
            last_record["progress"] = read_progress_snapshot(Path(args.progress_output))
        if not running or output_exists:
            print(json.dumps(last_record, ensure_ascii=False, sort_keys=True))
            return 0
        if time.monotonic() - started >= args.max_seconds:
            last_record["status"] = "watch_timeout"
            print(json.dumps(last_record, ensure_ascii=False, sort_keys=True))
            return 124
        time.sleep(args.interval_seconds)


def adopt_job(args: argparse.Namespace) -> int:
    if not process_is_running(args.pid):
        raise SystemExit(f"pid is not running: {args.pid}")
    pid_path = Path(args.pid_file).resolve()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "name": args.name,
        "pid": args.pid,
        "cwd": str(Path(args.cwd).resolve()),
        "command": args.job_command,
        "stdout": args.stdout,
        "stderr": args.stderr,
        "started_at_utc": "",
        "adopted_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json_atomic(pid_path, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


def process_is_running(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def write_json_atomic(path: Path, payload: dict) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def read_progress_snapshot(path: Path) -> dict:
    resolved = path.resolve()
    if not resolved.exists():
        return {
            "progress_output": str(resolved),
            "progress_file_status": "missing",
        }
    try:
        progress = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "progress_output": str(resolved),
            "progress_file_status": "unreadable",
            "error": repr(exc),
        }
    if isinstance(progress, dict):
        progress.setdefault("progress_output", str(resolved))
        progress.setdefault("progress_file_status", "ok")
        return progress
    return {
        "progress_output": str(resolved),
        "progress_file_status": "invalid_json_shape",
    }


if __name__ == "__main__":
    raise SystemExit(main())
