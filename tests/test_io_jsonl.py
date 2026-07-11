import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl


class JsonlIoTest(unittest.TestCase):
    def test_plain_jsonl_roundtrip(self) -> None:
        path = _io_temp_path("rows.jsonl")
        try:
            count = write_jsonl(path, [{"a": 1}, {"b": "x"}])

            self.assertEqual(count, 2)
            self.assertEqual(list(iter_jsonl(path)), [{"a": 1}, {"b": "x"}])
        finally:
            path.unlink(missing_ok=True)

    def test_gzip_jsonl_read(self) -> None:
        path = _io_temp_path("rows.jsonl.gz")
        try:
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write(json.dumps({"caption": "A dog."}))
                handle.write("\n")

            self.assertEqual(list(iter_jsonl(path)), [{"caption": "A dog."}])
        finally:
            path.unlink(missing_ok=True)


def _io_temp_path(name: str) -> Path:
    roots = [
        os.environ.get("GPIC_TEST_TEMP_ROOT"),
        str(Path.cwd() / ".tmp_tests"),
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
        tempfile.gettempdir(),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root) / "io_jsonl"
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f"{uuid.uuid4().hex}.tmp"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base / f"{uuid.uuid4().hex}_{name}"
        except PermissionError:
            continue
    raise PermissionError("no writable temp directory for io jsonl tests")


if __name__ == "__main__":
    unittest.main()
