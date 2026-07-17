from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path


DEFAULT_NAMESPACE = "p-production"
DEFAULT_POD = "prod-rsv-snu14ksh-20260717-5d6540"
DEFAULT_KUBECTL = "/home/sohunkim/.local/bin/kubectl"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local bash script inside the MLXP pod through WSL kubectl. "
            "The script is sent as raw bytes to `bash -s`, avoiding PowerShell "
            "quoting, heredoc, and BOM issues."
        ),
    )
    parser.add_argument("script", type=Path)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--pod", default=DEFAULT_POD)
    parser.add_argument("--kubectl", default=DEFAULT_KUBECTL)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.script.exists():
        raise SystemExit(f"missing script: {args.script}")
    payload = args.script.read_bytes()
    payload = _strip_utf_bom(payload)
    command = [
        "wsl",
        "-e",
        args.kubectl,
        "-n",
        args.namespace,
        "exec",
        "-i",
        args.pod,
        "--",
        "bash",
        "-s",
    ]
    completed = subprocess.run(command, input=payload)
    return int(completed.returncode)


def _strip_utf_bom(payload: bytes) -> bytes:
    for bom in (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff"):
        if payload.startswith(bom):
            return payload[len(bom) :]
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
