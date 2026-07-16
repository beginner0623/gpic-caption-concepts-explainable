import json
import unittest

from gpic_concepts_v1.schema import (
    PIPELINE_VERSION,
    CanonicalEdge,
    CanonicalMention,
    CaptionRecord,
    CountRow,
    FactRow,
    MISSING_SOURCE_MENTION_ID,
    RawEdge,
    RawMention,
    make_global_id,
    make_local_id,
)


class SchemaTest(unittest.TestCase):
    def test_caption_record_sentence(self) -> None:
        record = CaptionRecord(
            caption_id="000001",
            caption="A brown dog sits on a wooden bench.",
            caption_shape="sentence",
            skipped=False,
            skip_reason=None,
            rule_ids=["R1"],
        )

        self.assertEqual(record.pipeline_version, PIPELINE_VERSION)
        self.assertEqual(record.to_dict()["caption_shape"], "sentence")
        self.assertEqual(json.loads(record.to_json())["caption_id"], "000001")

    def test_caption_record_tag_list_can_be_routed(self) -> None:
        record = CaptionRecord(
            caption_id="000002",
            caption="brown boot, brick wall, display",
            caption_shape="tag_list",
            skipped=False,
            skip_reason=None,
            rule_ids=["R1", "R1.1"],
        )

        self.assertEqual(record.caption_shape, "tag_list")
        self.assertFalse(record.skipped)

    def test_raw_records(self) -> None:
        mention = RawMention(
            caption_id="000001",
            mention_id="m0",
            mention_type="object",
            text="dog",
            lemma="dog",
            rule_id="R12",
            char_start=8,
            char_end=11,
            token_start=2,
            token_end=3,
            source_text="A brown dog",
            source_detail={"pos": "NOUN", "dep": "nsubj"},
        )
        edge = RawEdge(
            caption_id="000001",
            edge_id="e0",
            edge_type="event_role",
            source_mention_id="m1",
            target_mention_id="m0",
            label="agent",
            rule_id="R16",
            evidence_text="dog -> sits",
        )

        self.assertEqual(mention.stage, 4)
        self.assertEqual(edge.source_mention_id, "m1")

    def test_canonical_records(self) -> None:
        mention = CanonicalMention(
            caption_id="000001",
            mention_id="m0",
            mention_type="object",
            raw_text="dogs",
            raw_lemma="dog",
            canonical="dog",
            parent_concepts=["animal"],
            canonical_rule_id="R19",
            parent_rule_id="R23",
            canonical_source="lexicon",
            parent_source="lexicon",
        )
        edge = CanonicalEdge(
            caption_id="000001",
            edge_id="e0",
            edge_type="relation",
            source_mention_id="m0",
            target_mention_id="m1",
            label="on",
            canonical_label="on",
            source_canonical="dog",
            target_canonical="bench",
            rule_id="R18",
            canonical_rule_id="R24",
        )

        self.assertEqual(mention.parent_concepts, ["animal"])
        self.assertEqual(edge.canonical_label, "on")

    def test_missing_endpoint_ids_are_only_for_ambiguous_relation_candidates(self) -> None:
        raw_edge = RawEdge(
            caption_id="000001",
            edge_id="e0",
            edge_type="ambiguous_relation_candidate",
            source_mention_id=MISSING_SOURCE_MENTION_ID,
            target_mention_id="m0",
            label="in front of",
            rule_id="R18.1",
        )
        canonical_edge = CanonicalEdge(
            caption_id="000001",
            edge_id="e0",
            edge_type="ambiguous_relation_candidate",
            source_mention_id=MISSING_SOURCE_MENTION_ID,
            target_mention_id="m0",
            label="in front of",
            canonical_label="in front of",
            source_canonical="source_missing",
            target_canonical="wall",
            rule_id="R18.1",
            canonical_rule_id="R24",
        )

        self.assertEqual(raw_edge.source_mention_id, MISSING_SOURCE_MENTION_ID)
        self.assertEqual(canonical_edge.source_canonical, "source_missing")
        with self.assertRaises(ValueError):
            RawEdge(
                caption_id="000001",
                edge_id="e1",
                edge_type="relation",
                source_mention_id=MISSING_SOURCE_MENTION_ID,
                target_mention_id="m0",
                label="in front of",
                rule_id="R18.1",
            )

    def test_fact_and_count_rows(self) -> None:
        fact = FactRow(
            caption_id="000001",
            fact_id="f0",
            fact_type="entity_exists",
            count_key="entity_exists:dog",
            rule_ids=["R12", "R19", "R23"],
            source_mention_ids=["m0"],
            source_edge_ids=[],
            values={"object": "dog", "parent_concepts": ["animal"]},
        )
        count = CountRow(
            count_key="entity_exists:dog",
            count=2,
            caption_count=2,
            example_caption_ids=["000001", "000003"],
            raw_variants=["dog", "dogs"],
            rule_ids=["R12"],
            values={"object": "dog"},
        )

        self.assertEqual(fact.fact_id, "f0")
        self.assertEqual(count.count, 2)

    def test_id_helpers(self) -> None:
        self.assertEqual(make_local_id("m", 3), "m3")
        self.assertEqual(make_global_id("000001", "m3"), "000001:m3")
        with self.assertRaises(ValueError):
            make_local_id("m", -1)


if __name__ == "__main__":
    unittest.main()
