from pathlib import Path
import csv
import tempfile
import unittest

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import CanonicalEdge, CanonicalMention
from gpic_concepts_v1.stage6_export_counts import (
    export_count_facts,
    run_stage6_export_counts,
)


def mention(
    caption_id: str,
    mention_id: str,
    mention_type: str,
    canonical: str,
    canonical_rule_id: str,
    *,
    raw_text: str | None = None,
    raw_lemma: str | None = None,
    parent_concepts: list[str] | None = None,
    parent_rule_id: str | None = None,
    canonical_detail: dict[str, object] | None = None,
) -> CanonicalMention:
    return CanonicalMention(
        caption_id=caption_id,
        mention_id=mention_id,
        mention_type=mention_type,  # type: ignore[arg-type]
        raw_text=raw_text or canonical,
        raw_lemma=raw_lemma or canonical,
        canonical=canonical,
        parent_concepts=parent_concepts or [],
        canonical_rule_id=canonical_rule_id,
        parent_rule_id=parent_rule_id,
        canonical_source="raw_fallback",
        parent_source="lexicon" if parent_rule_id else None,
        canonical_detail=canonical_detail or {},
    )


def edge(
    caption_id: str,
    edge_id: str,
    edge_type: str,
    source: str,
    target: str,
    label: str,
    rule_id: str,
    *,
    canonical_rule_id: str | None = None,
) -> CanonicalEdge:
    return CanonicalEdge(
        caption_id=caption_id,
        edge_id=edge_id,
        edge_type=edge_type,  # type: ignore[arg-type]
        source_mention_id=source,
        target_mention_id=target,
        label=label,
        canonical_label=label,
        source_canonical="unused",
        target_canonical="unused",
        rule_id=rule_id,
        canonical_rule_id=canonical_rule_id,
    )


class Stage6ExportCountsTest(unittest.TestCase):
    def test_exports_facts_and_count_tables(self) -> None:
        mentions = [
            mention(
                "c1",
                "m0",
                "object",
                "dog",
                "R19",
                raw_text="dogs",
                raw_lemma="dog",
                parent_concepts=["animal"],
                parent_rule_id="R23",
            ),
            mention(
                "c1",
                "m1",
                "attribute",
                "red",
                "R20",
                canonical_detail={"attribute_type": "color_attribute"},
            ),
            mention("c1", "m2", "quantity", "two", "R21"),
            mention(
                "c1",
                "m3",
                "action",
                "sit",
                "R22",
                raw_text="sits",
                raw_lemma="sit",
                parent_concepts=["body_pose_action"],
                parent_rule_id="R23",
            ),
            mention("c1", "m4", "object", "bench", "R19"),
            mention("c2", "m0", "object", "cat", "R19"),
            mention("c2", "m1", "object", "mat", "R19"),
        ]
        edges = [
            edge("c1", "e0", "has_attribute", "m0", "m1", "has_attribute", "R13"),
            edge("c1", "e1", "has_quantity", "m0", "m2", "has_quantity", "R14"),
            edge("c1", "e2", "event_role", "m3", "m0", "agent", "R16"),
            edge("c1", "e3", "relation", "m0", "m4", "on", "R18", canonical_rule_id="R24"),
            edge("c2", "e0", "relation", "m0", "m1", "on", "R18", canonical_rule_id="R24"),
        ]

        result = export_count_facts(mentions, edges)
        fact_types = [fact.fact_type for fact in result.facts]
        self.assertEqual(fact_types.count("entity_exists"), 4)
        self.assertEqual(fact_types.count("action_event"), 1)
        self.assertEqual(fact_types.count("has_attribute"), 1)
        self.assertEqual(fact_types.count("has_quantity"), 1)
        self.assertEqual(fact_types.count("event_role"), 1)
        self.assertEqual(fact_types.count("relation"), 2)
        self.assertEqual(fact_types.count("object_pair_in_caption"), 4)

        relation_rows = result.count_tables["relation_triple_counts.tsv"]
        relation_keys = {row.count_key for row in relation_rows}
        self.assertIn("relation:dog:on:bench", relation_keys)
        self.assertIn("relation:cat:on:mat", relation_keys)

        attribute_rows = result.count_tables["attribute_counts.tsv"]
        self.assertEqual(attribute_rows[0].count_key, "attribute:red")
        pair_rows = result.count_tables["object_cooccurrence_pair_counts.tsv"]
        pair_keys = {row.count_key for row in pair_rows}
        self.assertIn("object_pair_in_caption:dog:bench", pair_keys)
        self.assertIn("object_pair_in_caption:bench:dog", pair_keys)

    def test_run_stage6_writes_facts_and_tsv_tables(self) -> None:
        mentions = [
            mention("c1", "m0", "object", "dog", "R19"),
            mention("c1", "m1", "object", "bench", "R19"),
            mention("c1", "m2", "action", "sit", "R22"),
        ]
        edges = [
            edge("c1", "e0", "event_role", "m2", "m0", "agent", "R16"),
            edge("c1", "e1", "relation", "m0", "m1", "on", "R18", canonical_rule_id="R24"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            canonical_mentions_path = tmp_path / "canonical_mentions.jsonl"
            canonical_edges_path = tmp_path / "canonical_edges.jsonl"
            output_dir = tmp_path / "stage6"
            summary_path = tmp_path / "summary.jsonl"
            write_jsonl(canonical_mentions_path, mentions)
            write_jsonl(canonical_edges_path, edges)

            summary = run_stage6_export_counts(
                canonical_mentions_path,
                canonical_edges_path,
                output_dir=output_dir,
                summary_path=summary_path,
            )

            self.assertTrue((output_dir / "facts.jsonl").exists())
            self.assertTrue((output_dir / "object_counts.tsv").exists())
            self.assertTrue((output_dir / "relation_triple_counts.tsv").exists())
            self.assertEqual(summary["fact_type_counts"]["relation"], 1)
            self.assertEqual(len(list(iter_jsonl(output_dir / "facts.jsonl"))), summary["fact_total"])
            self.assertEqual(list(iter_jsonl(summary_path))[0]["fact_total"], summary["fact_total"])

            with (output_dir / "object_counts.tsv").open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(rows[0]["count"], "1")


if __name__ == "__main__":
    unittest.main()
