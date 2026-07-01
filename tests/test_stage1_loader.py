import gzip
import json
from pathlib import Path
import tempfile
import unittest

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
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl.gz"
            caption_records_path = tmp_path / "caption_records.jsonl"
            sentence_rows_path = tmp_path / "sentence_rows.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            write_gz_jsonl(input_path, rows)

            summary = run_stage1_records(
                [input_path],
                caption_records_path=caption_records_path,
                sentence_rows_path=sentence_rows_path,
                summary_path=summary_path,
            )

            caption_records = list(iter_jsonl(caption_records_path))
            sentence_rows = list(iter_jsonl(sentence_rows_path))
            summary_rows = list(iter_jsonl(summary_path))

            self.assertEqual(summary["total"], 3)
            self.assertEqual(summary["caption_shape_counts"], {"sentence": 2, "tag_list": 1})
            self.assertEqual(summary["skipped_counts"], {"tag_list_deferred": 1})
            self.assertEqual(len(caption_records), 3)
            self.assertEqual(len(sentence_rows), 2)
            self.assertEqual({row["key"] for row in sentence_rows}, {"k1", "k3"})
            self.assertEqual(summary_rows[0]["caption_type_counts"]["tag"], 1)

    def test_limit_applies_across_inputs(self) -> None:
        rows = [
            {"key": "k1", "caption": "A dog.", "caption_type": "short"},
            {"key": "k2", "caption": "A cat.", "caption_type": "short"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
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


if __name__ == "__main__":
    unittest.main()
