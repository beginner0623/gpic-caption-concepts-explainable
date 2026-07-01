from pathlib import Path
import tempfile
import unittest

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.stage2_preprocess import (
    ObjectMweEntry,
    Stage2InputError,
    _is_mergeable_hyphen_parts,
    load_object_mwes,
    make_stage2_nlp,
    preprocess_gpic_sentence_row,
    preprocess_text,
    run_stage2_preprocess,
    spacy,
)


@unittest.skipIf(spacy is None, "spaCy is not installed in this Python environment")
class Stage2PreprocessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.nlp = make_stage2_nlp()

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

    def test_object_mwe_lexicon_phrase_is_merged(self) -> None:
        record = preprocess_text(
            caption_id="c2",
            caption="A traffic light stands near the road.",
            nlp=self.nlp,
            object_mwes=[
                ObjectMweEntry(
                    phrase="traffic light",
                    canonical="traffic_light",
                    source="test",
                )
            ],
        )

        token_texts = [token["text"] for token in record.tokens]
        object_mwe_spans = [
            span for span in record.protected_spans if span["kind"] == "object_mwe"
        ]

        self.assertIn("traffic light", token_texts)
        self.assertEqual(len(object_mwe_spans), 1)
        self.assertEqual(object_mwe_spans[0]["canonical"], "traffic_light")
        self.assertEqual(object_mwe_spans[0]["rule_id"], "R4")

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

    def test_header_only_object_mwe_lexicon_loads_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "object_mwes.tsv"
            path.write_text("phrase\tcanonical\tsource\tnotes\n", encoding="utf-8")

            self.assertEqual(load_object_mwes(path), [])

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
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "sentence_rows.jsonl"
            output_path = tmp_path / "stage2_records.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            lexicon_path = tmp_path / "object_mwes.tsv"
            write_jsonl(input_path, rows)
            lexicon_path.write_text(
                "phrase\tcanonical\tsource\tnotes\n"
                "traffic light\ttraffic_light\ttest\t\n",
                encoding="utf-8",
            )

            summary = run_stage2_preprocess(
                input_path,
                output_path=output_path,
                object_mwes_path=lexicon_path,
                summary_path=summary_path,
            )
            records = list(iter_jsonl(output_path))
            summary_rows = list(iter_jsonl(summary_path))

            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["object_mwe_lexicon_size"], 1)
            self.assertEqual(len(records), 2)
            self.assertEqual(summary_rows[0]["total"], 2)
            self.assertIn("quote", summary["protected_span_counts"])
            self.assertIn("object_mwe", summary["protected_span_counts"])


if __name__ == "__main__":
    unittest.main()
