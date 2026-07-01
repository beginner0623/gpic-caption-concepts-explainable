import gzip
import json
from pathlib import Path
import tempfile
import unittest

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl


class JsonlIoTest(unittest.TestCase):
    def test_plain_jsonl_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            count = write_jsonl(path, [{"a": 1}, {"b": "x"}])

            self.assertEqual(count, 2)
            self.assertEqual(list(iter_jsonl(path)), [{"a": 1}, {"b": "x"}])

    def test_gzip_jsonl_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl.gz"
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write(json.dumps({"caption": "A dog."}))
                handle.write("\n")

            self.assertEqual(list(iter_jsonl(path)), [{"caption": "A dog."}])


if __name__ == "__main__":
    unittest.main()
