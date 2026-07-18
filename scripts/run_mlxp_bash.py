from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from incident_gate import guarded_entrypoint


DEFAULT_NAMESPACE = "p-production"
DEFAULT_POD = "prod-rsv-snu14ksh-20260717-5d6540"
DEFAULT_KUBECTL = "/home/sohunkim/.local/bin/kubectl"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local bash script inside the MLXP pod through WSL kubectl. "
            "The script is sent as raw bytes to `bash -s`, avoiding PowerShell "
            "quoting, heredoc, and BOM issues. The runner also prepends the "
            "standard MLXP Python runtime library path guard unless disabled."
        ),
    )
    parser.add_argument("script", type=Path)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--pod", default=DEFAULT_POD)
    parser.add_argument("--kubectl", default=DEFAULT_KUBECTL)
    parser.add_argument(
        "--no-runtime-env",
        action="store_true",
        help="Do not prepend the GPIC MLXP runtime LD_LIBRARY_PATH guard.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.script.exists():
        raise SystemExit(f"missing script: {args.script}")
    payload = args.script.read_bytes()
    payload = _strip_utf_bom(payload)
    if not args.no_runtime_env:
        payload = _prepend_mlxp_runtime_env(payload)
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


def _prepend_mlxp_runtime_env(payload: bytes) -> bytes:
    prologue = b"""# GPIC MLXP runtime guard: expose CUDA libraries installed by NVIDIA wheels.
if [ -x /root/work/gpic-linux-env/bin/python ]; then
  _gpic_cuda_libs=$(/root/work/gpic-linux-env/bin/python - <<'PY' 2>/dev/null || true
from pathlib import Path
try:
    import nvidia
except Exception:
    raise SystemExit(0)
root = Path(nvidia.__file__).resolve().parent
print(":".join(str(path) for path in sorted(root.glob("*/lib")) if path.is_dir()))
PY
)
  if [ -n "${_gpic_cuda_libs:-}" ]; then
    export LD_LIBRARY_PATH="${_gpic_cuda_libs}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  fi
  unset _gpic_cuda_libs
fi

"""
    return prologue + payload


if __name__ == "__main__":
    raise SystemExit(guarded_entrypoint("mlxp_remote_command", main))
