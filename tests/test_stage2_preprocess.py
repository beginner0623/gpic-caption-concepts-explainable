from pathlib import Path
import os
import tempfile
import unittest
import uuid

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.stage2_preprocess import (
    DEFAULT_STAGE2_TOKENIZER_MODEL,
    Stage2InputError,
    _is_mergeable_hyphen_parts,
    make_stage2_nlp,
    preprocess_gpic_sentence_row,
    preprocess_text,
    run_stage2_preprocess,
    spacy,
)


def _stage2_temp_base() -> Path:
    roots = [
        os.environ.get("GPIC_TEST_TEMP_ROOT"),
        str(Path.cwd() / ".tmp_tests"),
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
        tempfile.gettempdir(),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root) / "stage2_preprocess"
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f"{uuid.uuid4().hex}.tmp"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except PermissionError:
            continue
    raise PermissionError("no writable temp directory for stage2 tests")


def _stage2_temp_path(name: str) -> Path:
    return _stage2_temp_base() / f"{uuid.uuid4().hex}_{name}"


@unittest.skipIf(spacy is None, "spaCy is not installed in this Python environment")
class Stage2PreprocessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.nlp = make_stage2_nlp()

    def test_stage2_uses_trf_tokenizer_without_pipeline_components(self) -> None:
        self.assertEqual(self.nlp.meta.get("lang"), "en")
        self.assertEqual(
            self.nlp.meta.get("name"),
            DEFAULT_STAGE2_TOKENIZER_MODEL.removeprefix("en_"),
        )
        self.assertEqual(self.nlp.pipe_names, [])

    def test_quote_span_is_merged_without_placeholder(self) -> None:
        record = preprocess_text(
            caption_id="c1",
            caption='A stone sign reads "MILE 0".',
            nlp=self.nlp,
        )

        token_texts = [token["text"] for token in record.tokens]
        quote_spans = [span for span in record.protected_spans if span["kind"] == "quote"]

        self.assertIn('"MILE 0"', token_texts)
        self.assertEqual(len(quote_spans), 1)
        self.assertEqual(quote_spans[0]["rule_id"], "R3")
        self.assertNotIn("the quoted text", token_texts)

    def test_object_mwe_lexicon_is_ignored_by_stage2(self) -> None:
        record = preprocess_text(
            caption_id="c2",
            caption="A traffic light stands near the road.",
            nlp=self.nlp,
        )

        token_texts = [token["text"] for token in record.tokens]
        object_mwe_spans = [
            span for span in record.protected_spans if span["kind"] == "object_mwe"
        ]

        self.assertIn("traffic", token_texts)
        self.assertIn("light", token_texts)
        self.assertNotIn("traffic light", token_texts)
        self.assertEqual(object_mwe_spans, [])

    def test_hyphen_helper_rejects_numeric_ranges(self) -> None:
        self.assertTrue(_is_mergeable_hyphen_parts(["bare", "shouldered"]))
        self.assertTrue(_is_mergeable_hyphen_parts(["x", "ray"]))
        self.assertFalse(_is_mergeable_hyphen_parts(["3", "4"]))
        self.assertFalse(_is_mergeable_hyphen_parts(["a", "b"]))

    def test_tag_list_row_is_rejected_by_stage2(self) -> None:
        row = {
            "key": "k1",
            "caption": "brown boot, brick wall, display",
            "caption_type": "tag",
        }

        with self.assertRaises(Stage2InputError):
            preprocess_gpic_sentence_row(row, nlp=self.nlp)

    def test_run_stage2_preprocess_writes_records(self) -> None:
        rows = [
            {
                "key": "k1",
                "caption": 'A sign reads "OPEN".',
                "caption_type": "short",
            },
            {
                "key": "k2",
                "caption": "A traffic light glows.",
                "caption_type": "short",
            },
        ]
        prefix = uuid.uuid4().hex
        base = _stage2_temp_base()
        input_path = base / f"{prefix}_sentence_rows.jsonl"
        output_path = base / f"{prefix}_stage2_records.jsonl"
        summary_path = base / f"{prefix}_summary.jsonl"
        try:
            write_jsonl(input_path, rows)

            summary = run_stage2_preprocess(
                input_path,
                output_path=output_path,
                summary_path=summary_path,
            )
            records = list(iter_jsonl(output_path))
            summary_rows = list(iter_jsonl(summary_path))

            self.assertEqual(summary["total"], 2)
            self.assertEqual(len(records), 2)
            self.assertEqual(summary_rows[0]["total"], 2)
            self.assertIn("quote", summary["protected_span_counts"])
            self.assertNotIn("object_mwe", summary["protected_span_counts"])
        finally:
            for path in (input_path, output_path, summary_path):
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
