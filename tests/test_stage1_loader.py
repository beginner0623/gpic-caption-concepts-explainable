import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from gpic_concepts_v1.io_jsonl import iter_jsonl
from gpic_concepts_v1.stage1_loader import run_stage1_records


def write_gz_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


class Stage1LoaderTest(unittest.TestCase):
    def test_run_stage1_records_writes_caption_records_and_sentence_rows(self) -> None:
        rows = [
            {
                "key": "k1",
                "caption": "A dog sits on a bench.",
                "caption_type": "short",
                "dataset_split": ["val"],
            },
            {
                "key": "k2",
                "caption": "dog, bench, outdoor",
                "caption_type": "tag",
                "dataset_split": ["val"],
            },
            {
                "key": "k3",
                "caption": "A longer caption with another sentence.",
                "caption_type": "medium",
                "dataset_split": ["val"],
            },
        ]
        tmp_path = _stage1_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = tmp_path / "input.jsonl.gz"
            caption_records_path = tmp_path / "caption_records.jsonl"
            sentence_rows_path = tmp_path / "sentence_rows.jsonl"
            tag_rows_path = tmp_path / "tag_rows.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            write_gz_jsonl(input_path, rows)

            summary = run_stage1_records(
                [input_path],
                caption_records_path=caption_records_path,
                sentence_rows_path=sentence_rows_path,
                tag_rows_path=tag_rows_path,
                summary_path=summary_path,
            )

            caption_records = list(iter_jsonl(caption_records_path))
            sentence_rows = list(iter_jsonl(sentence_rows_path))
            tag_rows = list(iter_jsonl(tag_rows_path))
            summary_rows = list(iter_jsonl(summary_path))

            self.assertEqual(summary["total"], 3)
            self.assertEqual(summary["caption_shape_counts"], {"sentence": 2, "tag_list": 1})
            self.assertEqual(summary["skipped_counts"], {})
            self.assertEqual(len(caption_records), 3)
            self.assertEqual(len(sentence_rows), 2)
            self.assertEqual(len(tag_rows), 1)
            self.assertEqual({row["key"] for row in sentence_rows}, {"k1", "k3"})
            self.assertEqual(tag_rows[0]["key"], "k2")
            self.assertEqual(summary_rows[0]["caption_type_counts"]["tag"], 1)
            self.assertEqual(summary_rows[0]["tag_rows_path"], str(tag_rows_path))
        finally:
            _remove_temp_tree(tmp_path)

    def test_limit_applies_across_inputs(self) -> None:
        rows = [
            {"key": "k1", "caption": "A dog.", "caption_type": "short"},
            {"key": "k2", "caption": "A cat.", "caption_type": "short"},
        ]
        tmp_path = _stage1_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = tmp_path / "input.jsonl.gz"
            output_path = tmp_path / "caption_records.jsonl"
            write_gz_jsonl(input_path, rows)

            summary = run_stage1_records(
                [input_path],
                caption_records_path=output_path,
                limit=1,
            )

            self.assertEqual(summary["total"], 1)
            self.assertEqual(len(list(iter_jsonl(output_path))), 1)
        finally:
            _remove_temp_tree(tmp_path)


def _stage1_temp_base() -> Path:
    roots = [
        os.environ.get("GPIC_TEST_TEMP_ROOT"),
        str(Path.cwd() / ".tmp_tests"),
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
        tempfile.gettempdir(),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root) / "stage1_loader"
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f"{uuid.uuid4().hex}.tmp"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except PermissionError:
            continue
    raise PermissionError("no writable temp directory for stage1 tests")


def _remove_temp_tree(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            child.rmdir()
    path.rmdir()


if __name__ == "__main__":
    unittest.main()
