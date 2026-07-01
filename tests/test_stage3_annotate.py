from pathlib import Path
import tempfile
import unittest

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.stage2_preprocess import ObjectMweEntry, Stage2InputError
from gpic_concepts_v1.stage3_annotate import (
    DEFAULT_STAGE3_MODEL,
    Stage3DependencyError,
    annotate_gpic_sentence_row,
    annotate_text,
    make_stage3_nlp,
    run_stage3_annotate,
    spacy,
)


def can_load_trf_model() -> bool:
    if spacy is None:
        return False
    try:
        spacy.load(DEFAULT_STAGE3_MODEL, disable=["ner"])
    except OSError:
        return False
    return True


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

    def test_object_mwe_pos_correction_marks_only_object_mwe_tokens(self) -> None:
        record = annotate_text(
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
        mwe_tokens = [token for token in record.tokens if token["text"] == "traffic light"]

        self.assertEqual(len(mwe_tokens), 1)
        self.assertTrue(mwe_tokens[0]["is_object_mwe"])
        self.assertEqual(mwe_tokens[0]["pos"], "NOUN")
        self.assertEqual(mwe_tokens[0]["tag"], "NN")
        self.assertIn("R7", record.rule_ids)

    def test_run_stage3_annotate_writes_records(self) -> None:
        rows = [
            {
                "key": "k1",
                "caption": "A dog sits on a bench.",
                "caption_type": "short",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "sentence_rows.jsonl"
            output_path = tmp_path / "stage3_records.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            lexicon_path = tmp_path / "object_mwes.tsv"
            write_jsonl(input_path, rows)
            lexicon_path.write_text("phrase\tcanonical\tsource\tnotes\n", encoding="utf-8")

            summary = run_stage3_annotate(
                input_path,
                output_path=output_path,
                object_mwes_path=lexicon_path,
                summary_path=summary_path,
            )
            records = list(iter_jsonl(output_path))
            summary_rows = list(iter_jsonl(summary_path))

            self.assertEqual(summary["total"], 1)
            self.assertGreater(summary["token_total"], 0)
            self.assertGreater(summary["noun_chunk_total"], 0)
            self.assertEqual(len(records), 1)
            self.assertEqual(summary_rows[0]["model"], DEFAULT_STAGE3_MODEL)


if __name__ == "__main__":
    unittest.main()
