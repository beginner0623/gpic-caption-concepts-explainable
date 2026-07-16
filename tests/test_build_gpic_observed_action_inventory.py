from __future__ import annotations

import csv
import json
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest

from gpic_concepts_v1.stage4_extract_raw import _ActionLookupResult, _PrepositionMweEntry


def load_script_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_gpic_observed_action_inventory.py"
    spec = importlib.util.spec_from_file_location("build_gpic_observed_action_inventory", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load build_gpic_observed_action_inventory.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BuildGpicObservedActionInventoryTest(unittest.TestCase):
    def test_relation_mwe_tokens_are_excluded_from_action_inventory_candidates(self) -> None:
        module = load_script_module()
        entry = _PrepositionMweEntry(
            surface="in front of",
            token_keys=("in", "front", "of"),
            canonical_relation="in front of",
            relation_components=("in", "front", "of"),
            initial_relation_token_offset=0,
            final_adp_token_offset=2,
            source="test",
        )
        record = {
            "caption_id": "c1",
            "tokens": [
                {"i": 0, "text": "stand", "pos": "VERB", "dep": "ROOT", "tag": "VB", "head_i": 0},
                {"i": 1, "text": "in", "pos": "ADP", "dep": "prep", "tag": "IN", "head_i": 0},
                {"i": 2, "text": "front", "pos": "NOUN", "dep": "pobj", "tag": "NN", "head_i": 1},
                {"i": 3, "text": "of", "pos": "ADP", "dep": "prep", "tag": "IN", "head_i": 2},
                {"i": 4, "text": "wall", "pos": "NOUN", "dep": "pobj", "tag": "NN", "head_i": 3},
            ],
        }

        rows, summary = module.build_action_inventory_rows(
            [record],
            action_lookup=_fake_action_lookup,
            preposition_mwe_lookup=(entry,),
        )

        self.assertEqual(summary["relation_mwe_match_total"], 1)
        self.assertEqual(summary["relation_mwe_consumed_token_total"], 3)
        self.assertEqual([row["span_key"] for row in rows], ["stand"])
        self.assertEqual(rows[0]["decision_status"], "raw_fallback")

    def test_progress_writer_updates_during_record_scan(self) -> None:
        module = load_script_module()
        record = {
            "caption_id": "c1",
            "tokens": [
                {"i": 0, "text": "stand", "pos": "VERB", "dep": "ROOT", "tag": "VB", "head_i": 0},
            ],
        }
        with tempfile.TemporaryDirectory() as root:
            progress_path = Path(root) / "action_progress.json"
            progress_writer = module.ActionInventoryProgressWriter(
                progress_path,
                interval_records=1,
            )

            module.build_action_inventory_rows(
                [record],
                action_lookup=_fake_action_lookup,
                progress_writer=progress_writer,
            )

            progress = json.loads(progress_path.read_text(encoding="utf-8"))

        self.assertEqual(progress["status"], "running")
        self.assertEqual(progress["phase"], "scan_stage3_records")
        self.assertEqual(progress["caption_total"], 1)
        self.assertEqual(progress["verb_token_total"], 1)
        self.assertEqual(progress["inventory_rows_so_far"], 1)

    def test_checkpoint_resume_continues_counts_from_record_boundary(self) -> None:
        module = load_script_module()
        records = [
            {
                "caption_id": "c1",
                "tokens": [
                    {
                        "i": 0,
                        "text": "stand",
                        "pos": "VERB",
                        "dep": "ROOT",
                        "tag": "VB",
                        "head_i": 0,
                    },
                ],
            },
            {
                "caption_id": "c2",
                "tokens": [
                    {
                        "i": 0,
                        "text": "stand",
                        "pos": "VERB",
                        "dep": "ROOT",
                        "tag": "VB",
                        "head_i": 0,
                    },
                ],
            },
        ]
        metadata = {
            "input": "stage3.jsonl",
            "output": "action.tsv",
            "limit": "",
            "action_inventory": "",
            "preposition_mwe_lexicon": "",
        }

        with tempfile.TemporaryDirectory() as root:
            checkpoint_path = Path(root) / "action_checkpoint.json"
            checkpoint_writer = module.ActionInventoryCheckpointWriter(
                checkpoint_path,
                metadata=metadata,
                interval_records=1,
            )
            module.build_action_inventory_rows(
                records[:1],
                action_lookup=_fake_action_lookup,
                checkpoint_writer=checkpoint_writer,
            )

            checkpoint = module._load_checkpoint(checkpoint_path, metadata)
            self.assertIsNotNone(checkpoint)
            assert checkpoint is not None
            resumed_records = module._resume_records(
                records,
                resume_caption_total=checkpoint.caption_total,
                limit=None,
            )
            rows, summary = module.build_action_inventory_rows(
                resumed_records,
                action_lookup=_fake_action_lookup,
                initial_inventory=checkpoint.inventory,
                initial_caption_total=checkpoint.caption_total,
                initial_verb_token_total=checkpoint.verb_token_total,
                initial_relation_mwe_match_total=checkpoint.relation_mwe_match_total,
                initial_relation_mwe_consumed_token_total=checkpoint.relation_mwe_consumed_token_total,
            )

        self.assertEqual(summary["caption_total"], 2)
        self.assertEqual(summary["verb_token_total"], 2)
        self.assertEqual(rows[0]["span_key"], "stand")
        self.assertEqual(rows[0]["count"], "2")
        self.assertEqual(rows[0]["caption_count"], "2")
        self.assertEqual(rows[0]["example_caption_ids"], "c1|c2")

    def test_prior_action_inventory_reuses_unique_selected_query(self) -> None:
        module = load_script_module()
        with tempfile.TemporaryDirectory() as root:
            prior_path = Path(root) / "prior_action_inventory.tsv"
            _write_prior_inventory(
                prior_path,
                [
                    {
                        "span_key": "marked",
                        "selected_query": "mark",
                        "decision_status": "chosen",
                        "decision_reason": "manual_action_synset_selected",
                        "selected_lookup_case": "verb_head_morphy",
                        "selected_oewn_synset": "oewn-mark-v",
                        "selected_oewn_lexfile": "verb.contact",
                        "synset_lemmas": "mark",
                        "all_oewn_synsets": "oewn-mark-v|oewn-mark-other-v",
                        "all_oewn_lexfiles": "verb.contact|verb.communication",
                        "synset_selection_tag": "manual_action_synset_selected",
                        "wn30_lemma_counts": "",
                    },
                ],
            )
            original_lookup = module._lookup_oewn_verb_synsets
            try:
                module._lookup_oewn_verb_synsets = (
                    lambda surface, oewn, morphy: _fake_needs_manual_lookup("mark")
                )
                lookup = module._build_action_lookup(
                    str(prior_path),
                    {"oewn": object(), "morphy": object()},
                )
                result = lookup("mark")
            finally:
                module._lookup_oewn_verb_synsets = original_lookup

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.decision_status, "chosen")
        self.assertEqual(result.decision_reason, "prior_action_selected_query_reused")
        self.assertEqual(result.lookup_case, "exact_prior_selected_query")
        self.assertEqual(result.query, "mark")
        self.assertEqual(result.selected_synset.id, "oewn-mark-v")

    def test_prior_action_inventory_does_not_reuse_conflicting_selected_query(self) -> None:
        module = load_script_module()
        with tempfile.TemporaryDirectory() as root:
            prior_path = Path(root) / "prior_action_inventory.tsv"
            _write_prior_inventory(
                prior_path,
                [
                    {
                        "span_key": "marked",
                        "selected_query": "mark",
                        "decision_status": "chosen",
                        "decision_reason": "manual_action_synset_selected",
                        "selected_lookup_case": "verb_head_morphy",
                        "selected_oewn_synset": "oewn-mark-v",
                        "selected_oewn_lexfile": "verb.contact",
                        "synset_lemmas": "mark",
                        "all_oewn_synsets": "oewn-mark-v|oewn-mark-other-v",
                        "all_oewn_lexfiles": "verb.contact|verb.communication",
                        "synset_selection_tag": "manual_action_synset_selected",
                        "wn30_lemma_counts": "",
                    },
                    {
                        "span_key": "marking",
                        "selected_query": "mark",
                        "decision_status": "chosen",
                        "decision_reason": "manual_action_synset_selected",
                        "selected_lookup_case": "verb_head_morphy",
                        "selected_oewn_synset": "oewn-mark-other-v",
                        "selected_oewn_lexfile": "verb.communication",
                        "synset_lemmas": "mark",
                        "all_oewn_synsets": "oewn-mark-v|oewn-mark-other-v",
                        "all_oewn_lexfiles": "verb.contact|verb.communication",
                        "synset_selection_tag": "manual_action_synset_selected",
                        "wn30_lemma_counts": "",
                    },
                ],
            )
            original_lookup = module._lookup_oewn_verb_synsets
            try:
                module._lookup_oewn_verb_synsets = (
                    lambda surface, oewn, morphy: _fake_needs_manual_lookup("mark")
                )
                lookup = module._build_action_lookup(
                    str(prior_path),
                    {"oewn": object(), "morphy": object()},
                )
                result = lookup("mark")
            finally:
                module._lookup_oewn_verb_synsets = original_lookup

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.decision_status, "needs_manual")
        self.assertEqual(result.decision_reason, "manual_action_synset_required")


class FakeSynset:
    def __init__(
        self,
        synset_id: str = "fake-stand-in-v",
        lexfile: str = "verb.stative",
        lemma: str = "stand_in",
    ) -> None:
        self.id = synset_id
        self._lexfile = lexfile
        self._lemma = lemma

    def lexfile(self) -> str:
        return self._lexfile

    def lemmas(self) -> list[str]:
        return [self._lemma]


def _fake_action_lookup(surface: str):
    if surface != "stand in":
        return None
    synset = FakeSynset()
    return _ActionLookupResult(
        lookup_case="exact",
        query="stand in",
        synsets=(synset,),
        selected_synset=synset,
        synset_selection_tag="test_selected",
        wn30_lemma_counts="",
        decision_status="chosen",
        decision_reason="selected_verb_synset",
    )


def _fake_needs_manual_lookup(query: str) -> _ActionLookupResult:
    synsets = (
        FakeSynset("oewn-mark-v", "verb.contact", "mark"),
        FakeSynset("oewn-mark-other-v", "verb.communication", "mark"),
    )
    return _ActionLookupResult(
        lookup_case="exact",
        query=query,
        synsets=synsets,
        selected_synset=None,
        synset_selection_tag="ambiguous_wn30_tie",
        wn30_lemma_counts="",
        decision_status="needs_manual",
        decision_reason="manual_action_synset_required",
    )


def _write_prior_inventory(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "span_key",
        "selected_query",
        "decision_status",
        "decision_reason",
        "selected_lookup_case",
        "selected_oewn_synset",
        "selected_oewn_lexfile",
        "synset_lemmas",
        "all_oewn_synsets",
        "all_oewn_lexfiles",
        "synset_selection_tag",
        "wn30_lemma_counts",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
