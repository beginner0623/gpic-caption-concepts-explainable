from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from incident_gate import guarded_entrypoint


DEFAULT_NAMESPACE = "p-production"
DEFAULT_POD_ENV = "MLXP_POD"
DEFAULT_POD_PREFIX_ENV = "MLXP_POD_PREFIX"
DEFAULT_POD: str | None = None
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
    parser.add_argument(
        "--pod",
        default=DEFAULT_POD,
        help=f"Target MLXP pod. Required unless {DEFAULT_POD_ENV} is set.",
    )
    parser.add_argument(
        "--pod-prefix",
        default=None,
        help=(
            "Resolve the single currently Running pod whose name starts with this "
            f"prefix. Can also be set with {DEFAULT_POD_PREFIX_ENV}."
        ),
    )
    parser.add_argument("--kubectl", default=DEFAULT_KUBECTL)
    parser.add_argument(
        "--no-runtime-env",
        action="store_true",
        help="Do not prepend the GPIC MLXP runtime LD_LIBRARY_PATH guard.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    pod = _resolve_target_pod(
        explicit_pod=args.pod or os.environ.get(DEFAULT_POD_ENV),
        pod_prefix=args.pod_prefix or os.environ.get(DEFAULT_POD_PREFIX_ENV),
        namespace=args.namespace,
        kubectl=args.kubectl,
    )
    if not args.script.exists():
        raise SystemExit(f"missing script: {args.script}")
    payload = args.script.read_bytes()
    payload = _strip_utf_bom(payload)
    payload = _normalize_bash_newlines(payload)
    if not args.no_runtime_env:
        payload = _prepend_mlxp_runtime_env(payload)
    preflight_returncode = _preflight_wsl_access()
    if preflight_returncode != 0:
        return preflight_returncode
    pod_preflight_returncode = _preflight_pod_running(
        kubectl=args.kubectl,
        namespace=args.namespace,
        pod=pod,
    )
    if pod_preflight_returncode != 0:
        return pod_preflight_returncode
    command = [
        "wsl",
        "-e",
        args.kubectl,
        "-n",
        args.namespace,
        "exec",
        "-i",
        pod,
        "--",
        "bash",
        "-s",
    ]
    completed = subprocess.run(command, input=payload)
    return int(completed.returncode)


def _resolve_target_pod(
    *,
    explicit_pod: str | None,
    pod_prefix: str | None,
    namespace: str,
    kubectl: str,
) -> str:
    if explicit_pod:
        return explicit_pod
    if not pod_prefix:
        raise SystemExit(
            f"--pod is required unless {DEFAULT_POD_ENV} is set; "
            f"or use --pod-prefix/{DEFAULT_POD_PREFIX_ENV} to resolve the active pod"
        )
    return _resolve_running_pod_by_prefix(
        pod_prefix=pod_prefix,
        namespace=namespace,
        kubectl=kubectl,
    )


def _resolve_running_pod_by_prefix(*, pod_prefix: str, namespace: str, kubectl: str) -> str:
    command = [
        "wsl",
        "-e",
        kubectl,
        "-n",
        namespace,
        "get",
        "pods",
        "-o",
        "json",
    ]
    completed = subprocess.run(command, capture_output=True)
    if completed.returncode != 0:
        stderr = _decode_process_output(completed.stderr)
        stdout = _decode_process_output(completed.stdout)
        raise SystemExit(
            "failed to resolve MLXP pod prefix before remote command execution.\n"
            f"prefix={pod_prefix}\n"
            f"returncode={completed.returncode}\n"
            f"stdout={stdout[-1000:]}\n"
            f"stderr={stderr[-1000:]}"
        )
    try:
        payload = json.loads(_decode_process_output(completed.stdout))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"failed to parse kubectl pod list JSON: {exc}") from exc
    matches = [
        str(item.get("metadata", {}).get("name", ""))
        for item in payload.get("items", [])
        if str(item.get("metadata", {}).get("name", "")).startswith(pod_prefix)
        and item.get("status", {}).get("phase") == "Running"
    ]
    matches = sorted(name for name in matches if name)
    if not matches:
        raise SystemExit(f"no Running MLXP pod found with prefix: {pod_prefix}")
    if len(matches) > 1:
        raise SystemExit(
            "multiple Running MLXP pods match prefix; pass --pod explicitly: "
            + ", ".join(matches)
        )
    return matches[0]


def _preflight_wsl_access() -> int:
    """Fail clearly before sending a long MLXP command if WSL is unavailable."""
    command = ["wsl", "-e", "/bin/sh", "-lc", "printf WSL_OK"]
    completed = subprocess.run(command, capture_output=True)
    if completed.returncode == 0:
        return 0
    stderr = _decode_process_output(completed.stderr)
    stdout = _decode_process_output(completed.stdout)
    message = (
        "WSL preflight failed before MLXP command execution.\n"
        "This means the remote pod command was not started. In Codex desktop, "
        "WSL may require sandbox escalation; rerun the MLXP command with "
        "sandbox_permissions=require_escalated.\n"
        f"returncode={completed.returncode}\n"
        f"stdout={stdout[-1000:]}\n"
        f"stderr={stderr[-1000:]}\n"
    )
    sys.stderr.write(message)
    return int(completed.returncode)


def _preflight_pod_running(*, kubectl: str, namespace: str, pod: str) -> int:
    command = [
        "wsl",
        "-e",
        kubectl,
        "-n",
        namespace,
        "get",
        "pod",
        pod,
        "-o",
        "json",
    ]
    completed = subprocess.run(command, capture_output=True)
    stdout = _decode_process_output(completed.stdout)
    stderr = _decode_process_output(completed.stderr)
    if completed.returncode != 0:
        sys.stderr.write(
            "MLXP pod preflight failed before remote command execution.\n"
            "This means the remote script was not started. The pod name may be stale; "
            "use --pod-prefix or update MLXP_POD.\n"
            f"pod={pod}\n"
            f"returncode={completed.returncode}\n"
            f"stdout={stdout[-1000:]}\n"
            f"stderr={stderr[-1000:]}\n"
        )
        return int(completed.returncode)
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"failed to parse kubectl pod JSON for {pod}: {exc}\n")
        return 1
    phase = str(payload.get("status", {}).get("phase", ""))
    if phase != "Running":
        sys.stderr.write(
            "MLXP pod preflight failed before remote command execution.\n"
            f"pod={pod}\n"
            f"phase={phase}\n"
        )
        return 1
    return 0


def _decode_process_output(data: bytes | None) -> str:
    if not data:
        return ""
    sample = data[:80]
    if b"\x00" in sample:
        try:
            return data.decode("utf-16-le", errors="replace")
        except UnicodeError:
            pass
    return data.decode("utf-8", errors="replace")


def _strip_utf_bom(payload: bytes) -> bytes:
    for bom in (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff"):
        if payload.startswith(bom):
            return payload[len(bom) :]
    return payload


def _normalize_bash_newlines(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


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
