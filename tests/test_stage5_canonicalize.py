from pathlib import Path
import os
import tempfile
import unittest
import uuid

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import RawEdge, RawMention
from gpic_concepts_v1.schema import MISSING_SOURCE_MENTION_ID
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
    source_detail: dict[str, object] | None = None,
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
        source_detail=source_detail or {},
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
    source_detail: dict[str, object] | None = None,
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
        source_detail=source_detail or {},
    )


class Stage5CanonicalizeTest(unittest.TestCase):
    def test_canonicalizes_mentions_and_preserves_edge_shape(self) -> None:
        lexicons = Stage5Lexicons(
            object_synonyms={"doggy": LexiconValue("dog", "test")},
            object_parents={"dog": (LexiconValue("animal", "test"),)},
            attribute_synonyms={"scarlet": LexiconValue("red", "test")},
            attribute_types={"red": LexiconValue("color_attribute", "test")},
            action_synonyms={"seated": LexiconValue("sit", "test")},
            action_types={"sit": LexiconValue("pose", "test")},
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

        self.assertEqual(canonical["m0"].canonical, "doggy")
        self.assertEqual(canonical["m0"].parent_concepts, [])
        self.assertEqual(canonical["m0"].canonical_rule_id, "R19")
        self.assertIsNone(canonical["m0"].parent_rule_id)
        self.assertEqual(canonical["m1"].canonical, "red")
        self.assertNotIn("attribute_type", canonical["m1"].canonical_detail)
        self.assertEqual(canonical["m2"].canonical, "two")
        self.assertEqual(canonical["m2"].canonical_rule_id, "R21")
        self.assertEqual(canonical["m3"].canonical, "sit")
        self.assertEqual(canonical["m3"].parent_concepts, [])
        self.assertIsNone(canonical["m3"].parent_rule_id)
        self.assertNotIn("action_type", canonical["m3"].canonical_detail)
        self.assertEqual(canonical["m4"].canonical_source, "raw_fallback")

        self.assertEqual(canonical_edges["e3"].canonical_label, "on")
        self.assertEqual(canonical_edges["e3"].canonical_rule_id, "R24")
        self.assertEqual(canonical_edges["e3"].source_mention_id, "m0")
        self.assertEqual(canonical_edges["e3"].target_mention_id, "m4")
        self.assertEqual(canonical_edges["e3"].source_canonical, "doggy")
        self.assertEqual(canonical_edges["e3"].target_canonical, "bench")
        self.assertIsNone(canonical_edges["e2"].canonical_rule_id)

    def test_object_selected_synset_metadata_is_preserved(self) -> None:
        lexicons = Stage5Lexicons(
            object_synonyms={},
            object_parents={},
            attribute_synonyms={},
            attribute_types={},
            action_synonyms={},
            action_types={},
        )
        mentions = [
            raw_mention(
                "m0",
                "object",
                "dogs",
                "dog",
                "R12",
                source_detail={
                    "selected_oewn_synset": "oewn-02086723-n",
                    "selected_oewn_lexfile": "noun.animal",
                    "canonical_surface": "dog",
                    "canonical_label_key": "dog",
                    "canonical_selection_tag": "selected_by_wn30_lemma_count_unique_positive_max",
                    "canonical_candidate_lemmas": ["dog"],
                    "canonical_candidate_lemma_counts": "dog:42",
                    "parent_oewn_synsets": ["oewn-02085998-n", "oewn-01317541-n"],
                    "parent_oewn_lexfiles": [
                        "oewn-02085998-n:noun.animal",
                        "oewn-01317541-n:noun.animal",
                    ],
                    "parent_lemmas": [
                        "oewn-02085998-n:canine;canid",
                        "oewn-01317541-n:domestic animal;domesticated animal",
                    ],
                    "parent_selection_tag": "selected_all_immediate_oewn_hypernyms",
                },
            ),
        ]

        result = canonicalize_raw_graph(mentions, [], lexicons=lexicons)
        mention = result.canonical_mentions[0]

        self.assertEqual(mention.canonical, "dog")
        self.assertEqual(mention.canonical_source, "gpic_observed_inventory")
        self.assertEqual(
            mention.canonical_detail["canonical_selection_tag"],
            "selected_by_wn30_lemma_count_unique_positive_max",
        )
        self.assertEqual(mention.canonical_detail["canonical_candidate_lemmas"], ["dog"])
        self.assertEqual(
            mention.canonical_detail["selected_oewn_synset"],
            "oewn-02086723-n",
        )
        self.assertEqual(mention.canonical_detail["selected_oewn_lexfile"], "noun.animal")
        self.assertEqual(
            mention.parent_concepts,
            ["canine; canid", "domestic animal; domesticated animal"],
        )
        self.assertEqual(mention.parent_rule_id, "R23")
        self.assertEqual(mention.parent_source, "selected_oewn_hypernym")
        self.assertEqual(
            mention.canonical_detail["parent_oewn_synsets"],
            ["oewn-02085998-n", "oewn-01317541-n"],
        )
        self.assertEqual(
            mention.canonical_detail["parent_lemmas"],
            [
                "oewn-02085998-n:canine;canid",
                "oewn-01317541-n:domestic animal;domesticated animal",
            ],
        )
        self.assertEqual(
            mention.canonical_detail["parent_selection_tag"],
            "selected_all_immediate_oewn_hypernyms",
        )

    def test_local_mention_ids_are_scoped_by_caption_id(self) -> None:
        lexicons = Stage5Lexicons(
            object_synonyms={},
            object_parents={},
            attribute_synonyms={},
            attribute_types={},
            action_synonyms={},
            action_types={},
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

    def test_preposition_mwe_relation_metadata_is_preserved(self) -> None:
        lexicons = Stage5Lexicons(
            object_synonyms={},
            object_parents={},
            attribute_synonyms={},
            attribute_types={},
            action_synonyms={},
            action_types={},
        )
        mentions = [
            raw_mention("m0", "object", "dog", "dog", "R12"),
            raw_mention("m1", "object", "house", "house", "R12"),
        ]
        edges = [
            raw_edge(
                "e0",
                "relation",
                "m0",
                "m1",
                "in front of",
                "R18.1",
                source_detail={
                    "relation_source": "preposition_mwe",
                    "raw_span_surface": "in front of",
                    "relation_components": ["in", "front", "of"],
                },
            ),
        ]

        result = canonicalize_raw_graph(mentions, edges, lexicons=lexicons)
        edge = result.canonical_edges[0]

        self.assertEqual(edge.canonical_label, "in front of")
        self.assertEqual(edge.canonical_rule_id, "R24")
        self.assertEqual(edge.canonical_detail["relation_source"], "preposition_mwe")
        self.assertEqual(edge.canonical_detail["relation_components"], ["in", "front", "of"])
        self.assertEqual(
            edge.canonical_detail["relation_canonical_policy"],
            "preposition_mwe_preserved",
        )

    def test_ambiguous_relation_candidate_metadata_is_preserved(self) -> None:
        lexicons = Stage5Lexicons(
            object_synonyms={},
            object_parents={},
            attribute_synonyms={},
            attribute_types={},
            action_synonyms={},
            action_types={},
        )
        mentions = [
            raw_mention("m0", "object", "dog", "dog", "R12"),
            raw_mention("m1", "object", "house", "house", "R12"),
        ]
        edges = [
            raw_edge(
                "e0",
                "ambiguous_relation_candidate",
                "m0",
                "m1",
                "in front of",
                "R18.1",
                source_detail={
                    "relation_source": "preposition_mwe",
                    "source_resolution": "head_direct_object_child",
                    "candidate_source_count": 2,
                    "relation_components": ["in", "front", "of"],
                },
            ),
        ]

        result = canonicalize_raw_graph(mentions, edges, lexicons=lexicons)
        edge = result.canonical_edges[0]

        self.assertEqual(edge.edge_type, "ambiguous_relation_candidate")
        self.assertEqual(edge.canonical_label, "in front of")
        self.assertEqual(edge.canonical_rule_id, "R24")
        self.assertEqual(edge.canonical_detail["candidate_source_count"], 2)
        self.assertEqual(
            edge.canonical_detail["relation_canonical_policy"],
            "preposition_mwe_preserved",
        )

    def test_missing_source_ambiguous_relation_candidate_is_preserved(self) -> None:
        lexicons = Stage5Lexicons(
            object_synonyms={},
            object_parents={},
            attribute_synonyms={},
            attribute_types={},
            action_synonyms={},
            action_types={},
        )
        mentions = [
            raw_mention("m0", "object", "wall", "wall", "R12"),
        ]
        edges = [
            raw_edge(
                "e0",
                "ambiguous_relation_candidate",
                MISSING_SOURCE_MENTION_ID,
                "m0",
                "in front of",
                "R18.1",
                source_detail={
                    "relation_source": "preposition_mwe",
                    "source_endpoint_status": "source_missing",
                    "target_endpoint_status": "target_resolved",
                    "candidate_source_count": 0,
                    "candidate_target_count": 1,
                    "relation_components": ["in", "front", "of"],
                },
            ),
        ]

        result = canonicalize_raw_graph(mentions, edges, lexicons=lexicons)
        edge = result.canonical_edges[0]

        self.assertEqual(edge.edge_type, "ambiguous_relation_candidate")
        self.assertEqual(edge.source_mention_id, MISSING_SOURCE_MENTION_ID)
        self.assertEqual(edge.source_canonical, "source_missing")
        self.assertEqual(edge.target_canonical, "wall")
        self.assertEqual(edge.canonical_detail["source_endpoint_status"], "source_missing")
        self.assertEqual(
            edge.canonical_detail["relation_canonical_policy"],
            "preposition_mwe_preserved",
        )

    def test_load_stage5_lexicons_and_run_writes_outputs(self) -> None:
        tmp_path = _stage5_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
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
            self.assertNotIn('": ', canonical_mentions_path.read_text(encoding="utf-8"))
            self.assertNotIn('": ', canonical_edges_path.read_text(encoding="utf-8"))
            self.assertEqual(list(iter_jsonl(summary_path))[0]["canonical_edge_total"], 1)

            loaded = load_stage5_lexicons(lexicon_dir)
            self.assertEqual(loaded.object_synonyms["doggy"].value, "dog")
            self.assertEqual(loaded.action_types["sit"].value, "pose")
        finally:
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            tmp_path.rmdir()


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
    (root / "action_types.tsv").write_text(
        "canonical\taction_type\tsource\tnotes\n"
        "sit\tpose\ttest\t\n",
        encoding="utf-8",
    )


def _stage5_temp_base() -> Path:
    roots = [
        os.environ.get("GPIC_TEST_TEMP_ROOT"),
        str(Path.cwd() / ".tmp_tests"),
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
        tempfile.gettempdir(),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root) / "stage5_canonicalize"
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f"{uuid.uuid4().hex}.tmp"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except PermissionError:
            continue
    raise PermissionError("no writable temp directory for stage5 tests")


if __name__ == "__main__":
    unittest.main()
