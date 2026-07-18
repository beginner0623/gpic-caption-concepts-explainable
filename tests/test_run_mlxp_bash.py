from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_mlxp_bash.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_mlxp_bash", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load run_mlxp_bash.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunMlxpBashTests(unittest.TestCase):
    def test_strip_utf_bom(self) -> None:
        module = _load_module()

        self.assertEqual(module._strip_utf_bom(b"\xef\xbb\xbfset -eu\n"), b"set -eu\n")

    def test_runtime_env_guard_is_prepended(self) -> None:
        module = _load_module()

        payload = module._prepend_mlxp_runtime_env(b"set -eu\necho ok\n")

        self.assertIn(b"LD_LIBRARY_PATH", payload)
        self.assertIn(b"/root/work/gpic-linux-env/bin/python", payload)
        self.assertTrue(payload.endswith(b"set -eu\necho ok\n"))


if __name__ == "__main__":
    unittest.main()
