from pathlib import Path
import importlib.util
import os
import tempfile
import unittest
import uuid

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.stage2_preprocess import Stage2InputError
from gpic_concepts_v1.stage3_annotate import (
    DEFAULT_STAGE3_MODEL,
    Stage3DependencyError,
    Stage3Timing,
    annotate_gpic_sentence_row,
    annotate_gpic_tag_list_row,
    annotate_text,
    iter_annotated_docs_from_rows,
    make_stage3_nlp,
    run_stage3_annotate,
    spacy,
)


def can_load_trf_model() -> bool:
    if spacy is None:
        return False
    return importlib.util.find_spec(DEFAULT_STAGE3_MODEL) is not None


@unittest.skipUnless(can_load_trf_model(), "en_core_web_trf is not installed")
class Stage3AnnotateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.nlp = make_stage3_nlp()

    def test_annotation_generates_linguistic_evidence_only(self) -> None:
        record = annotate_text(
            caption_id="c1",
            caption="A brown dog sits on a wooden bench.",
            nlp=self.nlp,
        )
        record_dict = record.to_dict()

        self.assertEqual(record.stage, 3)
        self.assertIn("R6", record.rule_ids)
        self.assertIn("R8", record.rule_ids)
        self.assertGreater(len(record.tokens), 0)
        self.assertGreater(len(record.noun_chunks), 0)
        self.assertNotIn("raw_mentions", record_dict)
        self.assertNotIn("raw_edges", record_dict)

    def test_tag_list_row_is_rejected_by_stage3(self) -> None:
        row = {
            "key": "k1",
            "caption": "brown boot, brick wall, display",
            "caption_type": "tag",
        }

        with self.assertRaises(Stage2InputError):
            annotate_gpic_sentence_row(row, nlp=self.nlp)

    def test_tag_list_row_is_annotated_by_segment(self) -> None:
        row = {
            "key": "k-tag",
            "caption": "brown boot, brick wall, display",
            "caption_type": "tag",
        }

        record = annotate_gpic_tag_list_row(row, nlp=self.nlp)

        self.assertEqual(record.meta["caption_shape"], "tag_list")
        self.assertEqual([segment["text"] for segment in record.tag_segments], ["brown boot", "brick wall", "display"])
        self.assertEqual(record.tag_segments[0]["char_start"], 0)
        self.assertEqual(record.tag_segments[1]["char_start"], len("brown boot, "))
        self.assertGreater(len(record.tokens), 0)
        self.assertGreaterEqual(len(record.noun_chunks), 1)

    def test_object_mwe_pos_correction_is_not_part_of_stage3(self) -> None:
        record = annotate_text(
            caption_id="c2",
            caption="A traffic light stands near the road.",
            nlp=self.nlp,
        )
        mwe_tokens = [token for token in record.tokens if token["text"] == "traffic light"]
        traffic = [token for token in record.tokens if token["text"] == "traffic"]
        light = [token for token in record.tokens if token["text"] == "light"]

        self.assertEqual(mwe_tokens, [])
        self.assertEqual(len(traffic), 1)
        self.assertEqual(len(light), 1)
        self.assertNotIn("R7", record.rule_ids)

    def test_iter_annotated_docs_records_stage2_and_stage3_timing(self) -> None:
        rows = [
            {
                "key": "k1",
                "caption": "A dog sits on a bench.",
                "caption_type": "short",
            }
        ]
        timing = Stage3Timing()

        docs = list(
            iter_annotated_docs_from_rows(
                rows,
                nlp=self.nlp,
                batch_size=1,
                timing=timing,
            )
        )

        self.assertEqual(len(docs), 1)
        self.assertEqual(timing.stage2_doc_count, 1)
        self.assertEqual(timing.stage3_doc_count, 1)
        self.assertEqual(timing.stage3_batch_count, 1)
        self.assertGreaterEqual(timing.stage2_seconds, 0.0)
        self.assertGreater(timing.stage3_seconds, 0.0)

    def test_run_stage3_annotate_writes_records(self) -> None:
        rows = [
            {
                "key": "k1",
                "caption": "A dog sits on a bench.",
                "caption_type": "short",
            }
        ]
        tmp_path = _stage3_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = tmp_path / "sentence_rows.jsonl"
            output_path = tmp_path / "stage3_records.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            write_jsonl(input_path, rows)

            summary = run_stage3_annotate(
                input_path,
                output_path=output_path,
                summary_path=summary_path,
            )
            records = list(iter_jsonl(output_path))
            summary_rows = list(iter_jsonl(summary_path))

            self.assertEqual(summary["total"], 1)
            self.assertGreater(summary["token_total"], 0)
            self.assertGreater(summary["noun_chunk_total"], 0)
            self.assertEqual(len(records), 1)
            self.assertEqual(summary_rows[0]["model"], DEFAULT_STAGE3_MODEL)
            self.assertIn("timing_seconds", summary)
            self.assertIn("model_load", summary["timing_seconds"])
            self.assertIn("spacy_pipe", summary["timing_seconds"])
            self.assertIn("record_build_json_write_overhead", summary["timing_seconds"])
            self.assertEqual(summary["timing_counts"]["profile_scope"], "sentence_stage2_spacy_record_write")
            self.assertEqual(summary["timing_counts"]["stage2_doc_count"], 1)
            self.assertEqual(summary["timing_counts"]["stage3_doc_count"], 1)
        finally:
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            tmp_path.rmdir()

    def test_run_stage3_annotate_writes_tag_list_records(self) -> None:
        rows = [
            {
                "key": "k1",
                "caption": "brown boot, brick wall, display",
                "caption_type": "tag",
            }
        ]
        tmp_path = _stage3_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = tmp_path / "tag_rows.jsonl"
            output_path = tmp_path / "stage3_tag_records.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            write_jsonl(input_path, rows)

            summary = run_stage3_annotate(
                input_path,
                output_path=output_path,
                summary_path=summary_path,
                caption_shape="tag_list",
            )
            records = list(iter_jsonl(output_path))

            self.assertEqual(summary["total"], 1)
            self.assertEqual(summary["caption_shape"], "tag_list")
            self.assertEqual(summary["tag_segment_total"], 3)
            self.assertIn("timing_seconds", summary)
            self.assertEqual(summary["timing_counts"]["profile_scope"], "tag_list_total_only")
            self.assertEqual(len(records[0]["tag_segments"]), 3)
        finally:
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            tmp_path.rmdir()


def _stage3_temp_base() -> Path:
    roots = [
        os.environ.get("GPIC_TEST_TEMP_ROOT"),
        str(Path.cwd() / ".tmp_tests"),
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
        tempfile.gettempdir(),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root) / "stage3_annotate"
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f"{uuid.uuid4().hex}.tmp"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except PermissionError:
            continue
    raise PermissionError("no writable temp directory for stage3 tests")


if __name__ == "__main__":
    unittest.main()
