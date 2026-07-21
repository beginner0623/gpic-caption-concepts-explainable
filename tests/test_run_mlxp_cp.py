from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_mlxp_cp.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_mlxp_cp", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load run_mlxp_cp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunMlxpCpTests(unittest.TestCase):
    def test_copy_resolves_single_running_pod_by_prefix(self) -> None:
        module = _load_module()

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "payload.zip"
            source.write_bytes(b"zip")
            with patch.object(module.subprocess, "run") as run_mock:
                resolver = unittest.mock.Mock()
                resolver.returncode = 0
                resolver.stdout = json.dumps(
                    {
                        "items": [
                            {
                                "metadata": {"name": "prod-rsv-snu14ksh-old"},
                                "status": {"phase": "Succeeded"},
                            },
                            {
                                "metadata": {"name": "prod-rsv-snu14ksh-current"},
                                "status": {"phase": "Running"},
                            },
                        ],
                    },
                ).encode("utf-8")
                resolver.stderr = b""
                wsl_preflight = unittest.mock.Mock()
                wsl_preflight.returncode = 0
                wsl_preflight.stdout = b"WSL_OK"
                wsl_preflight.stderr = b""
                pod_preflight = unittest.mock.Mock()
                pod_preflight.returncode = 0
                pod_preflight.stdout = json.dumps({"status": {"phase": "Running"}}).encode("utf-8")
                pod_preflight.stderr = b""
                wslpath = unittest.mock.Mock()
                wslpath.returncode = 0
                wslpath.stdout = b"/mnt/c/payload.zip\n"
                wslpath.stderr = b""
                kubectl_cp = unittest.mock.Mock()
                kubectl_cp.returncode = 0
                run_mock.side_effect = [resolver, wsl_preflight, pod_preflight, wslpath, kubectl_cp]

                self.assertEqual(
                    module.main(
                        [
                            str(source),
                            "/tmp/payload.zip",
                            "--pod-prefix",
                            "prod-rsv-snu14ksh-",
                        ],
                    ),
                    0,
                )

        command = run_mock.call_args_list[-1].args[0]
        self.assertIn("cp", command)
        self.assertIn("/mnt/c/payload.zip", command)
        self.assertIn("prod-rsv-snu14ksh-current:/tmp/payload.zip", command)

    def test_remote_destination_must_not_include_pod_name(self) -> None:
        module = _load_module()

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "payload.zip"
            source.write_bytes(b"zip")
            with self.assertRaisesRegex(SystemExit, "not pod:/path"):
                module.main([str(source), "pod:/tmp/payload.zip", "--pod", "pod"])


if __name__ == "__main__":
    unittest.main()
