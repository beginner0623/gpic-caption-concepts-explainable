from pathlib import Path
import tempfile
import unittest

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import RawEdge, RawMention
from gpic_concepts_v1.stage5_canonicalize import (
    LexiconValue,
    Stage5Lexicons,
    canonicalize_raw_graph,
    load_stage5_lexicons,
    run_stage5_canonicalize,
)


def raw_mention(
    mention_id: str,
    mention_type: str,
    text: str,
    lemma: str,
    rule_id: str,
    *,
    caption_id: str = "c1",
) -> RawMention:
    return RawMention(
        caption_id=caption_id,
        mention_id=mention_id,
        mention_type=mention_type,  # type: ignore[arg-type]
        text=text,
        lemma=lemma,
        rule_id=rule_id,
        char_start=None,
        char_end=None,
        token_start=None,
        token_end=None,
        source_text=text,
    )


def raw_edge(
    edge_id: str,
    edge_type: str,
    source: str,
    target: str,
    label: str,
    rule_id: str,
    *,
    caption_id: str = "c1",
) -> RawEdge:
    return RawEdge(
        caption_id=caption_id,
        edge_id=edge_id,
        edge_type=edge_type,  # type: ignore[arg-type]
        source_mention_id=source,
        target_mention_id=target,
        label=label,
        rule_id=rule_id,
        evidence_text=None,
    )


class Stage5CanonicalizeTest(unittest.TestCase):
    def test_canonicalizes_mentions_and_preserves_edge_shape(self) -> None:
        lexicons = Stage5Lexicons(
            object_synonyms={"doggy": LexiconValue("dog", "test")},
            object_parents={"dog": (LexiconValue("animal", "test"),)},
            attribute_synonyms={"scarlet": LexiconValue("red", "test")},
            attribute_types={"red": LexiconValue("color_attribute", "test")},
            action_synonyms={"seated": LexiconValue("sit", "test")},
            action_parents={"sit": (LexiconValue("body_pose_action", "test"),)},
        )
        mentions = [
            raw_mention("m0", "object", "doggy", "doggy", "R12"),
            raw_mention("m1", "attribute", "scarlet", "scarlet", "R13"),
            raw_mention("m2", "quantity", "Two", "two", "R14"),
            raw_mention("m3", "action", "seated", "seated", "R15"),
            raw_mention("m4", "object", "bench", "bench", "R12"),
        ]
        edges = [
            raw_edge("e0", "has_attribute", "m0", "m1", "has_attribute", "R13"),
            raw_edge("e1", "has_quantity", "m0", "m2", "has_quantity", "R14"),
            raw_edge("e2", "event_role", "m3", "m0", "agent", "R16"),
            raw_edge("e3", "relation", "m0", "m4", "on", "R18"),
        ]

        result = canonicalize_raw_graph(mentions, edges, lexicons=lexicons)
        canonical = {mention.mention_id: mention for mention in result.canonical_mentions}
        canonical_edges = {edge.edge_id: edge for edge in result.canonical_edges}

        self.assertEqual(canonical["m0"].canonical, "dog")
        self.assertEqual(canonical["m0"].parent_concepts, ["animal"])
        self.assertEqual(canonical["m0"].canonical_rule_id, "R19")
        self.assertEqual(canonical["m0"].parent_rule_id, "R23")
        self.assertEqual(canonical["m1"].canonical, "red")
        self.assertEqual(canonical["m1"].canonical_detail["attribute_type"], "color_attribute")
        self.assertEqual(canonical["m2"].canonical, "two")
        self.assertEqual(canonical["m2"].canonical_rule_id, "R21")
        self.assertEqual(canonical["m3"].canonical, "sit")
        self.assertEqual(canonical["m3"].parent_concepts, ["body_pose_action"])
        self.assertEqual(canonical["m4"].canonical_source, "raw_fallback")

        self.assertEqual(canonical_edges["e3"].canonical_label, "on")
        self.assertEqual(canonical_edges["e3"].canonical_rule_id, "R24")
        self.assertEqual(canonical_edges["e3"].source_mention_id, "m0")
        self.assertEqual(canonical_edges["e3"].target_mention_id, "m4")
        self.assertEqual(canonical_edges["e3"].source_canonical, "dog")
        self.assertEqual(canonical_edges["e3"].target_canonical, "bench")
        self.assertIsNone(canonical_edges["e2"].canonical_rule_id)

    def test_local_mention_ids_are_scoped_by_caption_id(self) -> None:
        lexicons = Stage5Lexicons(
            object_synonyms={},
            object_parents={},
            attribute_synonyms={},
            attribute_types={},
            action_synonyms={},
            action_parents={},
        )
        mentions = [
            raw_mention("m0", "object", "dog", "dog", "R12", caption_id="c1"),
            raw_mention("m1", "object", "bench", "bench", "R12", caption_id="c1"),
            raw_mention("m0", "object", "cat", "cat", "R12", caption_id="c2"),
            raw_mention("m1", "object", "sofa", "sofa", "R12", caption_id="c2"),
        ]
        edges = [
            raw_edge("e0", "relation", "m0", "m1", "on", "R18", caption_id="c1"),
            raw_edge("e0", "relation", "m0", "m1", "on", "R18", caption_id="c2"),
        ]

        result = canonicalize_raw_graph(mentions, edges, lexicons=lexicons)
        by_caption = {(edge.caption_id, edge.edge_id): edge for edge in result.canonical_edges}

        self.assertEqual(by_caption[("c1", "e0")].source_canonical, "dog")
        self.assertEqual(by_caption[("c1", "e0")].target_canonical, "bench")
        self.assertEqual(by_caption[("c2", "e0")].source_canonical, "cat")
        self.assertEqual(by_caption[("c2", "e0")].target_canonical, "sofa")

    def test_load_stage5_lexicons_and_run_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lexicon_dir = tmp_path / "lexicons"
            lexicon_dir.mkdir()
            _write_lexicons(lexicon_dir)

            raw_mentions_path = tmp_path / "raw_mentions.jsonl"
            raw_edges_path = tmp_path / "raw_edges.jsonl"
            canonical_mentions_path = tmp_path / "canonical_mentions.jsonl"
            canonical_edges_path = tmp_path / "canonical_edges.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            write_jsonl(
                raw_mentions_path,
                [
                    raw_mention("m0", "object", "dogs", "doggy", "R12"),
                    raw_mention("m1", "action", "seated", "seated", "R15"),
                ],
            )
            write_jsonl(
                raw_edges_path,
                [raw_edge("e0", "event_role", "m1", "m0", "agent", "R16")],
            )

            summary = run_stage5_canonicalize(
                raw_mentions_path,
                raw_edges_path,
                lexicon_dir=lexicon_dir,
                canonical_mentions_path=canonical_mentions_path,
                canonical_edges_path=canonical_edges_path,
                summary_path=summary_path,
            )

            self.assertEqual(summary["canonical_mention_total"], 2)
            self.assertEqual(summary["canonical_edge_total"], 1)
            self.assertEqual(len(list(iter_jsonl(canonical_mentions_path))), 2)
            self.assertEqual(len(list(iter_jsonl(canonical_edges_path))), 1)
            self.assertEqual(list(iter_jsonl(summary_path))[0]["canonical_edge_total"], 1)

            loaded = load_stage5_lexicons(lexicon_dir)
            self.assertEqual(loaded.object_synonyms["doggy"].value, "dog")
            self.assertEqual(loaded.action_parents["sit"][0].value, "body_pose_action")


def _write_lexicons(root: Path) -> None:
    (root / "object_synonyms.tsv").write_text(
        "raw\tcanonical\tsource\tnotes\n"
        "doggy\tdog\ttest\t\n",
        encoding="utf-8",
    )
    (root / "object_parents.tsv").write_text(
        "canonical\tparent\tsource\tnotes\n"
        "dog\tanimal\ttest\t\n",
        encoding="utf-8",
    )
    (root / "attribute_synonyms.tsv").write_text(
        "raw\tcanonical\tsource\tnotes\n",
        encoding="utf-8",
    )
    (root / "attribute_types.tsv").write_text(
        "canonical\tattribute_type\tsource\tnotes\n",
        encoding="utf-8",
    )
    (root / "action_synonyms.tsv").write_text(
        "raw\tcanonical\tsource\tnotes\n"
        "seated\tsit\ttest\t\n",
        encoding="utf-8",
    )
    (root / "action_parents.tsv").write_text(
        "canonical\tparent\tsource\tnotes\n"
        "sit\tbody_pose_action\ttest\t\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
