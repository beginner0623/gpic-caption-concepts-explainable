import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


def _load_attribute_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_gpic_observed_attribute_inventory.py"
    spec = importlib.util.spec_from_file_location("build_gpic_observed_attribute_inventory", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


attribute_script = _load_attribute_script()


class FakeSynset:
    def __init__(self, synset_id: str, lexfile: str, lemmas: tuple[str, ...]) -> None:
        self.id = synset_id
        self._lexfile = lexfile
        self._lemmas = lemmas

    def lexfile(self) -> str:
        return self._lexfile

    def lemmas(self) -> list[str]:
        return list(self._lemmas)


class FakeObjectLookupResult:
    def __init__(
        self,
        query: str,
        *,
        canonical_surface: str = "",
        canonical_label_key: str = "",
    ) -> None:
        self.query = query
        self.synsets = (object(),)
        self.selected_synset = None
        self.canonical_surface = canonical_surface
        self.canonical_label_key = canonical_label_key


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
    }


def chunk(text: str, root_i: int, start: int, end: int) -> dict[str, object]:
    return {
        "text": text,
        "root_i": root_i,
        "root_text": text.split()[-1],
        "root_lemma": text.split()[-1].lower(),
        "root_pos": "NOUN",
        "root_tag": "NN",
        "root_dep": "ROOT",
        "root_head_i": root_i,
        "root_head_text": text.split()[-1],
        "token_start": start,
        "token_end": end,
        "char_start": start * 2,
        "char_end": end * 2,
    }


class BuildGpicObservedAttributeInventoryTest(unittest.TestCase):
    def test_consumed_object_span_tokens_are_not_attribute_candidates(self) -> None:
        record = {
            "caption_id": "c1",
            "tokens": [
                token(0, "black", "black", "ADJ", "amod", 2, tag="JJ"),
                token(1, "trash", "trash", "NOUN", "compound", 2),
                token(2, "can", "can", "NOUN", "ROOT", 2),
            ],
            "noun_chunks": [chunk("black trash can", 2, 0, 3)],
        }

        def object_lookup(surface: str):
            return FakeObjectLookupResult(surface) if surface == "trash can" else None

        black_synset = FakeSynset("fake-black-a", "adj.all", ("black",))

        def attribute_lookup(
            surface: str,
            *,
            require_surface_query_conflict_check: bool = False,
        ):
            if surface != "black":
                return None
            return attribute_script.AttributeLookupResult(
                "exact",
                "black",
                (black_synset,),
                black_synset,
                "single_oewn_attribute_synset",
                "",
                "attribute_compatible",
                "chosen",
                "selected_attribute_compatible",
            )

        rows, summary = attribute_script.build_attribute_inventory_rows(
            [record],
            object_lookup=object_lookup,
            attribute_lookup=attribute_lookup,
        )

        self.assertEqual(summary["attribute_candidate_total"], 1)
        self.assertEqual([row["span_key"] for row in rows], ["black"])
        self.assertEqual(rows[0]["decision_status"], "chosen")
        self.assertEqual(rows[0]["selected_oewn_synset"], "fake-black-a")

    def test_object_lookup_span_modifier_remains_attribute_when_core_is_suffix(self) -> None:
        record = {
            "caption_id": "c1",
            "tokens": [
                token(0, "black", "black", "ADJ", "amod", 1, tag="JJ"),
                token(1, "top", "top", "NOUN", "ROOT", 1),
            ],
            "noun_chunks": [chunk("black top", 1, 0, 2)],
        }

        def object_lookup(surface: str):
            return (
                FakeObjectLookupResult(
                    surface,
                    canonical_surface="top",
                    canonical_label_key="top",
                )
                if surface == "black top"
                else None
            )

        black_synset = FakeSynset("fake-black-a", "adj.all", ("black",))

        def attribute_lookup(
            surface: str,
            *,
            require_surface_query_conflict_check: bool = False,
        ):
            if surface != "black":
                return None
            return attribute_script.AttributeLookupResult(
                "exact",
                "black",
                (black_synset,),
                black_synset,
                "single_oewn_attribute_synset",
                "",
                "attribute_compatible",
                "chosen",
                "selected_attribute_compatible",
            )

        rows, summary = attribute_script.build_attribute_inventory_rows(
            [record],
            object_lookup=object_lookup,
            attribute_lookup=attribute_lookup,
        )

        self.assertEqual(summary["attribute_candidate_total"], 1)
        self.assertEqual([row["span_key"] for row in rows], ["black"])

    def test_nmod_modifier_is_attribute_inventory_candidate(self) -> None:
        record = {
            "caption_id": "c1",
            "tokens": [
                token(0, "maroon", "maroon", "NOUN", "nmod", 1, tag="NN"),
                token(1, "jerseys", "jersey", "NOUN", "ROOT", 1, tag="NNS"),
            ],
            "noun_chunks": [chunk("maroon jerseys", 1, 0, 2)],
        }

        def object_lookup(surface: str):
            return FakeObjectLookupResult(surface) if surface == "jerseys" else None

        maroon_synset = FakeSynset("fake-maroon-a", "adj.all", ("maroon",))

        def attribute_lookup(
            surface: str,
            *,
            require_surface_query_conflict_check: bool = False,
        ):
            if surface != "maroon":
                return None
            return attribute_script.AttributeLookupResult(
                "exact",
                "maroon",
                (maroon_synset,),
                maroon_synset,
                "single_oewn_attribute_synset",
                "",
                "attribute_compatible",
                "chosen",
                "selected_attribute_compatible",
            )

        rows, summary = attribute_script.build_attribute_inventory_rows(
            [record],
            object_lookup=object_lookup,
            attribute_lookup=attribute_lookup,
        )

        self.assertEqual(summary["attribute_candidate_total"], 1)
        self.assertEqual([row["span_key"] for row in rows], ["maroon"])

    def test_progress_writer_updates_during_record_scan(self) -> None:
        record = {
            "caption_id": "c1",
            "tokens": [
                token(0, "black", "black", "ADJ", "amod", 1, tag="JJ"),
                token(1, "dog", "dog", "NOUN", "ROOT", 1),
            ],
            "noun_chunks": [chunk("black dog", 1, 0, 2)],
        }

        def object_lookup(surface: str):
            return FakeObjectLookupResult(surface) if surface == "dog" else None

        black_synset = FakeSynset("fake-black-a", "adj.all", ("black",))

        def attribute_lookup(
            surface: str,
            *,
            require_surface_query_conflict_check: bool = False,
        ):
            return attribute_script.AttributeLookupResult(
                "exact",
                surface,
                (black_synset,),
                black_synset,
                "single_oewn_attribute_synset",
                "",
                "attribute_compatible",
                "chosen",
                "selected_attribute_compatible",
            )

        with tempfile.TemporaryDirectory() as root:
            progress_path = Path(root) / "attribute_progress.json"
            rows, summary = attribute_script.build_attribute_inventory_rows(
                [record],
                object_lookup=object_lookup,
                attribute_lookup=attribute_lookup,
                progress_output=progress_path,
                progress_interval_records=1,
            )
            progress = json.loads(progress_path.read_text(encoding="utf-8"))

        self.assertEqual([row["span_key"] for row in rows], ["black"])
        self.assertEqual(summary["attribute_candidate_total"], 1)
        self.assertEqual(progress["artifact_type"], "gpic_observed_attribute_inventory_progress")
        self.assertEqual(progress["status"], "complete")
        self.assertEqual(progress["caption_total"], 1)
        self.assertEqual(progress["attribute_candidate_total"], 1)
        self.assertEqual(progress["inventory_rows"], 1)

    def test_no_synset_attribute_remains_countable_inventory_row(self) -> None:
        record = {
            "caption_id": "c2",
            "tokens": [
                token(0, "shiny", "shiny", "ADJ", "amod", 1, tag="JJ"),
                token(1, "car", "car", "NOUN", "ROOT", 1),
            ],
            "noun_chunks": [chunk("shiny car", 1, 0, 2)],
        }

        def object_lookup(surface: str):
            return FakeObjectLookupResult(surface) if surface == "car" else None

        def attribute_lookup(
            surface: str,
            *,
            require_surface_query_conflict_check: bool = False,
        ):
            return attribute_script.AttributeLookupResult(
                "unresolved",
                surface,
                (),
                None,
                "unresolved_no_oewn_attribute_synset",
                "",
                "",
                "chosen",
                "no_oewn_attribute_synset",
            )

        rows, _ = attribute_script.build_attribute_inventory_rows(
            [record],
            object_lookup=object_lookup,
            attribute_lookup=attribute_lookup,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["span_key"], "shiny")
        self.assertEqual(rows[0]["decision_status"], "chosen")
        self.assertEqual(rows[0]["has_oewn_attribute_synset"], "false")

    def test_prior_inventory_canonical_fields_are_preserved(self) -> None:
        record = {
            "caption_id": "c3",
            "tokens": [
                token(0, "green", "green", "ADJ", "amod", 1, tag="JJ"),
                token(1, "shirt", "shirt", "NOUN", "ROOT", 1),
            ],
            "noun_chunks": [chunk("green shirt", 1, 0, 2)],
        }

        def object_lookup(surface: str):
            return FakeObjectLookupResult(surface) if surface == "shirt" else None

        green_synset = FakeSynset("fake-green-a", "noun.attribute", ("green",))

        def attribute_lookup(
            surface: str,
            *,
            require_surface_query_conflict_check: bool = False,
        ):
            if surface != "green":
                return None
            return attribute_script.AttributeLookupResult(
                "exact",
                "green",
                (green_synset,),
                green_synset,
                "selected_by_wn30_attribute_compatible_lemma_count",
                "green:5",
                "attribute_compatible",
                "chosen",
                "selected_attribute_compatible",
                {
                    "canonical_surface": "green",
                    "canonical_label_key": "green",
                    "canonical_selection_tag": "selected_single_observed_variant_matched_synset_lemma",
                    "canonical_candidate_lemmas": "green",
                    "canonical_candidate_lemma_counts": "green:5",
                },
            )

        rows, summary = attribute_script.build_attribute_inventory_rows(
            [record],
            object_lookup=object_lookup,
            attribute_lookup=attribute_lookup,
        )

        self.assertEqual(summary["prior_reused_rows"], 1)
        self.assertEqual(summary["prior_selected_synset_reused_rows"], 1)
        self.assertEqual(summary["prior_canonical_reused_rows"], 1)
        self.assertEqual(rows[0]["canonical_surface"], "green")
        self.assertEqual(
            rows[0]["canonical_selection_tag"],
            "selected_single_observed_variant_matched_synset_lemma",
        )

    def test_prior_no_synset_final_row_is_reusable(self) -> None:
        lookup = attribute_script.GpicAttributeInventoryLookup(
            {
                "tyr": {
                    "span_key": "tyr",
                    "observed_surface": "TYR",
                    "decision_status": "chosen",
                    "decision_reason": "no_oewn_attribute_synset",
                    "selected_query": "tyr",
                    "selected_oewn_synset": "",
                    "canonical_surface": "",
                    "canonical_selection_tag": "not_applicable_no_selected_synset",
                }
            }
        )

        result = lookup("TYR")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.decision_status, "chosen")
        self.assertEqual(result.decision_reason, "no_oewn_attribute_synset")
        self.assertIsNone(result.selected_synset)
        self.assertIsNotNone(result.source_row)

    def test_prior_inventory_from_tsv_does_not_reuse_selected_query(self) -> None:
        prior_row = {
            "span_key": "sauteed",
            "observed_surface": "sautéed",
            "decision_status": "chosen",
            "decision_reason": "selected_attribute_compatible",
            "selected_lookup_case": "morphy_a",
            "selected_query": "sauteed",
            "selected_oewn_synset": "oewn-sauteed-s",
            "selected_oewn_lexfile": "adj.all",
            "attribute_gate": "attribute_compatible",
            "all_oewn_synsets": "oewn-sauteed-s",
            "all_oewn_lexfiles": "adj.all",
            "synset_lemmas": "saute|sauteed",
            "canonical_surface": "sauteed",
            "canonical_label_key": "sauteed",
            "canonical_selection_tag": "selected_by_diacritic_folded_observed_surface",
        }
        prior_lookup = attribute_script.GpicAttributeInventoryLookup({"sauteed": prior_row})

        self.assertFalse(hasattr(prior_lookup, "lookup_selected_query"))

    def test_checkpoint_resume_continues_counts_from_record_boundary(self) -> None:
        records = [
            {
                "caption_id": "c1",
                "tokens": [
                    token(0, "black", "black", "ADJ", "amod", 1, tag="JJ"),
                    token(1, "dog", "dog", "NOUN", "ROOT", 1),
                ],
                "noun_chunks": [chunk("black dog", 1, 0, 2)],
            },
            {
                "caption_id": "c2",
                "tokens": [
                    token(0, "black", "black", "ADJ", "amod", 1, tag="JJ"),
                    token(1, "cat", "cat", "NOUN", "ROOT", 1),
                ],
                "noun_chunks": [chunk("black cat", 1, 0, 2)],
            },
        ]

        def object_lookup(surface: str):
            return FakeObjectLookupResult(surface) if surface in {"dog", "cat"} else None

        black_synset = FakeSynset("fake-black-a", "adj.all", ("black",))

        def attribute_lookup(
            surface: str,
            *,
            require_surface_query_conflict_check: bool = False,
        ):
            if surface != "black":
                return None
            return attribute_script.AttributeLookupResult(
                "exact",
                "black",
                (black_synset,),
                black_synset,
                "single_oewn_attribute_synset",
                "",
                "attribute_compatible",
                "chosen",
                "selected_attribute_compatible",
            )

        with tempfile.TemporaryDirectory() as tmp:
            checkpoint_path = Path(tmp) / "attribute_checkpoint.json"
            metadata = {"input": "stage3.jsonl", "output": "attribute.tsv"}
            writer = attribute_script.AttributeInventoryCheckpointWriter(
                checkpoint_path,
                metadata=metadata,
                interval_records=1,
            )
            attribute_script.build_attribute_inventory_rows(
                records[:1],
                object_lookup=object_lookup,
                attribute_lookup=attribute_lookup,
                checkpoint_writer=writer,
            )
            checkpoint = attribute_script._load_checkpoint(checkpoint_path, metadata)
            self.assertIsNotNone(checkpoint)
            assert checkpoint is not None
            rows, summary = attribute_script.build_attribute_inventory_rows(
                records[1:],
                object_lookup=object_lookup,
                attribute_lookup=attribute_lookup,
                initial_inventory=checkpoint.inventory,
                initial_caption_total=checkpoint.caption_total,
                initial_noun_chunk_total=checkpoint.noun_chunk_total,
                initial_attribute_candidate_total=checkpoint.attribute_candidate_total,
            )

        self.assertEqual(summary["caption_total"], 2)
        self.assertEqual(rows[0]["span_key"], "black")
        self.assertEqual(rows[0]["count"], "2")
        self.assertEqual(rows[0]["caption_count"], "2")
        self.assertEqual(rows[0]["selected_oewn_synset"], "fake-black-a")

    def test_runtime_surface_query_conflict_requires_manual_without_prior(self) -> None:
        grounds_synset = FakeSynset("oewn-grounds-n", "noun.location", ("grounds",))
        ground_synset = FakeSynset("oewn-ground-n", "noun.object", ("ground",))

        class FakeOewn:
            def synsets(self, query: str):
                return {
                    "grounds": (grounds_synset,),
                    "ground": (ground_synset,),
                }.get(query, ())

        class FakeMorphy:
            def __call__(self, query: str, pos: str):
                if query == "grounds" and pos == "n":
                    return {"n": {"ground"}}
                return {pos: set()}

        result = attribute_script._lookup_attribute_surface(
            "grounds",
            oewn=FakeOewn(),
            morphy=FakeMorphy(),
            require_surface_query_conflict_check=True,
        )

        self.assertEqual(result.decision_status, "needs_manual")
        self.assertEqual(
            result.decision_reason,
            "manual_surface_query_conflict_required",
        )
        self.assertIsNone(result.selected_synset)
        self.assertEqual(result.query, "grounds|ground")
        self.assertEqual(
            [synset.id for synset in result.synsets],
            ["oewn-grounds-n", "oewn-ground-n"],
        )

    def test_runtime_exact_attribute_hit_skips_morphy_conflict_without_plural_flag(self) -> None:
        grounds_synset = FakeSynset("oewn-grounds-n", "noun.location", ("grounds",))
        ground_synset = FakeSynset("oewn-ground-n", "noun.object", ("ground",))

        class FakeOewn:
            def synsets(self, query: str):
                return {
                    "grounds": (grounds_synset,),
                    "ground": (ground_synset,),
                }.get(query, ())

        class FakeMorphy:
            def __call__(self, query: str, pos: str):
                if query == "grounds" and pos == "n":
                    return {"n": {"ground"}}
                return {pos: set()}

        result = attribute_script._lookup_attribute_surface(
            "grounds",
            oewn=FakeOewn(),
            morphy=FakeMorphy(),
        )

        self.assertEqual(result.decision_status, "needs_manual")
        self.assertEqual(result.decision_reason, "manual_attribute_gate_required")
        self.assertEqual(result.selected_synset, grounds_synset)
        self.assertEqual(result.query, "grounds")

    def test_automatic_surface_changed_attribute_prior_row_is_not_reusable(self) -> None:
        auto_row = {
            "span_key": "grounds",
            "observed_surface": "grounds",
            "decision_status": "chosen",
            "selected_query": "ground",
            "selected_oewn_synset": "oewn-ground-n",
            "canonical_surface": "ground",
        }
        manual_row = {
            **auto_row,
            "decision_basis": "manual_attribute_resolution",
        }

        self.assertTrue(attribute_script._is_automatic_surface_changed_prior_row(auto_row))
        self.assertFalse(attribute_script._is_automatic_surface_changed_prior_row(manual_row))

    def test_conditional_lexfile_requires_manual(self) -> None:
        synset = FakeSynset("fake-label-n", "noun.artifact", ("label",))

        lookup = attribute_script._with_selected_attribute_synset(
            "exact",
            "label",
            (synset,),
        )

        self.assertEqual(lookup.attribute_gate, "conditional")
        self.assertEqual(lookup.decision_status, "needs_manual")
        self.assertEqual(lookup.decision_reason, "manual_attribute_gate_required")

    def test_unselected_synset_candidates_are_needs_manual_not_ambiguous_status(self) -> None:
        synset = FakeSynset("fake-vague-a", "adj.all", ("vague",))

        status = attribute_script._attribute_decision_status(
            selected_synset=None,
            synsets=(synset,),
            attribute_gate="",
        )
        reason = attribute_script._attribute_decision_reason(
            selected_synset=None,
            synsets=(synset,),
            attribute_gate="",
        )

        self.assertEqual(status, "needs_manual")
        self.assertEqual(reason, "manual_synset_required")


if __name__ == "__main__":
    unittest.main()
