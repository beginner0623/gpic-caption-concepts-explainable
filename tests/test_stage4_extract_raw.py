from pathlib import Path
import tempfile
import unittest

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.stage4_extract_raw import (
    extract_raw_concepts_from_stage3_record,
    run_stage4_extract_raw,
)


def token(
    i: int,
    text: str,
    lemma: str,
    pos: str,
    dep: str,
    head_i: int,
    *,
    tag: str = "NN",
) -> dict[str, object]:
    return {
        "i": i,
        "text": text,
        "lemma": lemma,
        "pos": pos,
        "tag": tag,
        "morph": "",
        "dep": dep,
        "head_i": head_i,
        "head_text": "",
        "char_start": i * 2,
        "char_end": i * 2 + len(text),
        "whitespace": " ",
        "is_object_mwe": False,
    }


def chunk(
    text: str,
    root_i: int,
    start: int,
    end: int,
    root_text: str,
) -> dict[str, object]:
    return {
        "text": text,
        "root_i": root_i,
        "root_text": root_text,
        "root_lemma": root_text.lower(),
        "root_pos": "NOUN",
        "root_tag": "NN",
        "root_dep": "dep",
        "root_head_i": 0,
        "root_head_text": "",
        "token_start": start,
        "token_end": end,
        "char_start": start * 2,
        "char_end": end * 2,
    }


class Stage4ExtractRawTest(unittest.TestCase):
    def test_extracts_objects_attributes_quantity_action_and_roles(self) -> None:
        record = {
            "caption_id": "c1",
            "caption": "Two brown dogs chase a ball.",
            "tokens": [
                token(0, "Two", "two", "NUM", "nummod", 2, tag="CD"),
                token(1, "brown", "brown", "ADJ", "amod", 2, tag="JJ"),
                token(2, "dogs", "dog", "NOUN", "nsubj", 3, tag="NNS"),
                token(3, "chase", "chase", "VERB", "ROOT", 3, tag="VBP"),
                token(4, "a", "a", "DET", "det", 5, tag="DT"),
                token(5, "ball", "ball", "NOUN", "dobj", 3),
            ],
            "noun_chunks": [
                chunk("Two brown dogs", 2, 0, 3, "dogs"),
                chunk("a ball", 5, 4, 6, "ball"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(record)
        mentions = [mention.to_dict() for mention in result.raw_mentions]
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertEqual(
            [(m["mention_type"], m["lemma"], m["rule_id"]) for m in mentions],
            [
                ("object", "dog", "R12"),
                ("quantity", "two", "R14"),
                ("attribute", "brown", "R13"),
                ("object", "ball", "R12"),
                ("action", "chase", "R15"),
            ],
        )
        self.assertIn(("has_quantity", "has_quantity", "R14"), _edge_sig(edges))
        self.assertIn(("has_attribute", "has_attribute", "R13"), _edge_sig(edges))
        self.assertIn(("event_role", "agent", "R16"), _edge_sig(edges))
        self.assertIn(("event_role", "patient", "R17"), _edge_sig(edges))

    def test_prepositional_object_is_not_action_patient(self) -> None:
        record = {
            "caption_id": "c2",
            "caption": "A dog sits on a bench.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "dog", "dog", "NOUN", "nsubj", 2),
                token(2, "sits", "sit", "VERB", "ROOT", 2, tag="VBZ"),
                token(3, "on", "on", "ADP", "prep", 2, tag="IN"),
                token(4, "a", "a", "DET", "det", 5, tag="DT"),
                token(5, "bench", "bench", "NOUN", "pobj", 3),
            ],
            "noun_chunks": [
                chunk("A dog", 1, 0, 2, "dog"),
                chunk("a bench", 5, 4, 6, "bench"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(record)
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertIn(("event_role", "agent", "R16"), _edge_sig(edges))
        self.assertNotIn(("event_role", "patient", "R17"), _edge_sig(edges))
        self.assertNotIn(("relation", "on", "R18"), _edge_sig(edges))

    def test_relation_requires_adp_head_and_pobj_to_be_existing_objects(self) -> None:
        record = {
            "caption_id": "c3",
            "caption": "A dog with a collar.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "dog", "dog", "NOUN", "ROOT", 1),
                token(2, "with", "with", "ADP", "prep", 1, tag="IN"),
                token(3, "a", "a", "DET", "det", 4, tag="DT"),
                token(4, "collar", "collar", "NOUN", "pobj", 2),
            ],
            "noun_chunks": [
                chunk("A dog", 1, 0, 2, "dog"),
                chunk("a collar", 4, 3, 5, "collar"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(record)
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertIn(("relation", "with", "R18"), _edge_sig(edges))

    def test_nsubjpass_is_not_normalized_to_agent(self) -> None:
        record = {
            "caption_id": "c4",
            "caption": "A ball is held.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "ball", "ball", "NOUN", "nsubjpass", 3),
                token(2, "is", "be", "AUX", "auxpass", 3, tag="VBZ"),
                token(3, "held", "hold", "VERB", "ROOT", 3, tag="VBN"),
            ],
            "noun_chunks": [chunk("A ball", 1, 0, 2, "ball")],
        }

        result = extract_raw_concepts_from_stage3_record(record)
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertNotIn(("event_role", "agent", "R16"), _edge_sig(edges))

    def test_run_stage4_extract_raw_writes_outputs(self) -> None:
        record = {
            "caption_id": "c5",
            "caption": "A brown dog.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 2, tag="DT"),
                token(1, "brown", "brown", "ADJ", "amod", 2, tag="JJ"),
                token(2, "dog", "dog", "NOUN", "ROOT", 2),
            ],
            "noun_chunks": [chunk("A brown dog", 2, 0, 3, "dog")],
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "stage3_records.jsonl"
            raw_mentions_path = tmp_path / "raw_mentions.jsonl"
            raw_edges_path = tmp_path / "raw_edges.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            write_jsonl(input_path, [record])

            summary = run_stage4_extract_raw(
                input_path,
                raw_mentions_path=raw_mentions_path,
                raw_edges_path=raw_edges_path,
                summary_path=summary_path,
            )

            self.assertEqual(summary["total"], 1)
            self.assertEqual(summary["raw_mention_total"], 2)
            self.assertEqual(summary["raw_edge_total"], 1)
            self.assertEqual(len(list(iter_jsonl(raw_mentions_path))), 2)
            self.assertEqual(len(list(iter_jsonl(raw_edges_path))), 1)
            self.assertEqual(list(iter_jsonl(summary_path))[0]["raw_mention_total"], 2)


def _edge_sig(edges: list[dict[str, object]]) -> set[tuple[object, object, object]]:
    return {(edge["edge_type"], edge["label"], edge["rule_id"]) for edge in edges}


if __name__ == "__main__":
    unittest.main()
