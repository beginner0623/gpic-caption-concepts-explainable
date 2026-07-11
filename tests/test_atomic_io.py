import tempfile
import unittest
import os
import uuid
from pathlib import Path

from gpic_concepts_v1.atomic_io import atomic_text_writer


class AtomicTextWriterTest(unittest.TestCase):
    def _make_temp_path(self) -> Path:
        roots = [
            os.environ.get("GPIC_TEST_TEMP_ROOT"),
            str(Path.cwd() / ".tmp_tests"),
            r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
            tempfile.gettempdir(),
        ]
        for root in roots:
            if not root:
                continue
            base = Path(root) / "atomic_io"
            try:
                base.mkdir(parents=True, exist_ok=True)
                probe = base / f"{uuid.uuid4().hex}.tmp"
                probe.write_text("", encoding="utf-8")
                probe.unlink(missing_ok=True)
                return base / f"atomic_io_{uuid.uuid4().hex}.tsv"
            except PermissionError:
                continue
        raise PermissionError("no writable temp directory for atomic io tests")

    def test_replaces_file_after_successful_write(self):
        path = self._make_temp_path()
        try:
            path.write_text("old\n", encoding="utf-8")

            with atomic_text_writer(path, newline="") as handle:
                handle.write("new\n")

            self.assertEqual(path.read_text(encoding="utf-8"), "new\n")
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])
        finally:
            path.unlink(missing_ok=True)

    def test_keeps_existing_file_when_write_fails(self):
        path = self._make_temp_path()
        try:
            path.write_text("old\n", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                with atomic_text_writer(path, newline="") as handle:
                    handle.write("partial\n")
                    raise RuntimeError("boom")

            self.assertEqual(path.read_text(encoding="utf-8"), "old\n")
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])
        finally:
            path.unlink(missing_ok=True)

    def test_can_use_configured_fallback_temp_root(self):
        path = self._make_temp_path()
        fallback_root = path.parent / f"fallback_{uuid.uuid4().hex}"
        old_force = os.environ.get("GPIC_ATOMIC_IO_FORCE_FALLBACK")
        old_root = os.environ.get("GPIC_ATOMIC_TEMP_ROOT")
        os.environ["GPIC_ATOMIC_IO_FORCE_FALLBACK"] = "1"
        os.environ["GPIC_ATOMIC_TEMP_ROOT"] = str(fallback_root)
        try:
            path.write_text("old\n", encoding="utf-8")

            with atomic_text_writer(path, newline="") as handle:
                handle.write("new\n")

            self.assertEqual(path.read_text(encoding="utf-8"), "new\n")
            self.assertEqual(list((fallback_root / "gpic_atomic_io").glob(f".{path.name}.*.tmp")), [])
        finally:
            if old_force is None:
                os.environ.pop("GPIC_ATOMIC_IO_FORCE_FALLBACK", None)
            else:
                os.environ["GPIC_ATOMIC_IO_FORCE_FALLBACK"] = old_force
            if old_root is None:
                os.environ.pop("GPIC_ATOMIC_TEMP_ROOT", None)
            else:
                os.environ["GPIC_ATOMIC_TEMP_ROOT"] = old_root
            path.unlink(missing_ok=True)
            for child in sorted(fallback_root.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            fallback_root.rmdir()


if __name__ == "__main__":
    unittest.main()
