import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest


def _load_object_inventory_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_gpic_observed_object_inventory.py"
    spec = importlib.util.spec_from_file_location("build_gpic_observed_object_inventory", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


object_script = _load_object_inventory_script()


class FakeSynset:
    def __init__(self, synset_id: str, lexfile: str, lemmas: tuple[str, ...]) -> None:
        self.id = synset_id
        self._lexfile = lexfile
        self._lemmas = lemmas

    def lexfile(self) -> str:
        return self._lexfile

    def lemmas(self) -> list[str]:
        return list(self._lemmas)


def token(i: int, text: str, lemma: str, pos: str, dep: str, head_i: int, *, tag: str = "NN") -> dict[str, object]:
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


class BuildGpicObservedObjectInventoryTest(unittest.TestCase):
    def test_prior_inventory_row_reuses_resolved_synset_canonical_and_parents(self) -> None:
        record = {
            "caption_id": "current-caption",
            "tokens": [token(0, "book", "book", "NOUN", "ROOT", 0)],
            "noun_chunks": [chunk("book", 0, 0, 1)],
        }
        prior_row = {
            "span_key": "book",
            "observed_surface": "book",
            "decision_status": "chosen",
            "decision_reason": "selected_object_compatible",
            "count": "99",
            "caption_count": "88",
            "example_caption_ids": "old-caption",
            "example_surfaces": "book",
            "selected_lookup_case": "prior_exact",
            "selected_query": "book",
            "has_oewn_noun_synset": "true",
            "oewn_synset_count": "1",
            "selected_oewn_synset": "oewn-test-book-n",
            "selected_oewn_lexfile": "noun.communication",
            "objectness_gate": "conditional",
            "synset_lemmas": "book",
            "parent_oewn_synsets": "oewn-parent-n",
            "parent_oewn_lexfiles": "noun.communication",
            "parent_lemmas": "publication",
            "parent_selection_tag": "immediate_hypernym_all",
            "canonical_surface": "book",
            "canonical_label_key": "book",
            "canonical_selection_tag": "prior_canonical",
            "decision_basis": "gpic_observed_caption_span_inventory",
        }

        def object_lookup(surface: str):
            raise AssertionError("prior row should prevent runtime lookup for exact span_key")

        rows, summary = object_script.build_object_inventory_rows(
            [record],
            object_lookup=object_lookup,
            prior_rows_by_key={"book": prior_row},
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["decision_status"], "chosen")
        self.assertEqual(row["selected_oewn_synset"], "oewn-test-book-n")
        self.assertEqual(row["canonical_surface"], "book")
        self.assertEqual(row["parent_lemmas"], "publication")
        self.assertEqual(row["count"], "1")
        self.assertEqual(row["caption_count"], "1")
        self.assertEqual(row["example_caption_ids"], "current-caption")
        self.assertIn("prior_gpic_observed_object_inventory", row["decision_basis"])
        self.assertEqual(summary["prior_reused_rows"], 1)

    def test_unresolved_prior_row_is_not_reusable(self) -> None:
        pending = {"span_key": "book", "decision_status": "needs_manual"}
        selected_missing_canonical = {
            "span_key": "book",
            "decision_status": "chosen",
            "selected_oewn_synset": "oewn-test-book-n",
            "canonical_surface": "",
        }
        excluded = {"span_key": "book", "decision_status": "excluded"}

        self.assertFalse(object_script._is_reusable_prior_row(pending))
        self.assertFalse(object_script._is_reusable_prior_row(selected_missing_canonical))
        self.assertTrue(object_script._is_reusable_prior_row(excluded))

    def test_prior_inventory_span_is_checked_before_oewn_longest_hit(self) -> None:
        record = {
            "caption_id": "c-street-light",
            "tokens": [
                token(0, "street", "street", "NOUN", "compound", 1),
                token(1, "light", "light", "NOUN", "ROOT", 1),
            ],
            "noun_chunks": [chunk("street light", 1, 0, 2)],
        }
        prior_row = {
            "span_key": "street light",
            "observed_surface": "street light",
            "decision_status": "chosen",
            "decision_reason": "selected_object_compatible",
            "selected_oewn_synset": "oewn-test-street-light-n",
            "selected_oewn_lexfile": "noun.artifact",
            "canonical_surface": "streetlight",
            "canonical_label_key": "streetlight",
        }

        def object_lookup(surface: str):
            raise AssertionError("prior MWE span should be reused before OEWN probing")

        rows, _summary = object_script.build_object_inventory_rows(
            [record],
            object_lookup=object_lookup,
            prior_rows_by_key={"street light": prior_row},
        )

        self.assertEqual([row["span_key"] for row in rows], ["street light"])
        self.assertEqual(rows[0]["selected_oewn_synset"], "oewn-test-street-light-n")
        self.assertEqual(rows[0]["canonical_surface"], "streetlight")

    def test_prior_inventory_does_not_reuse_selected_query_after_runtime_lookup(self) -> None:
        record = {
            "caption_id": "c-books",
            "tokens": [token(0, "books", "book", "NOUN", "ROOT", 0, tag="NNS")],
            "noun_chunks": [chunk("books", 0, 0, 1)],
        }
        prior_row = {
            "span_key": "book",
            "observed_surface": "book",
            "decision_status": "chosen",
            "decision_reason": "selected_object_compatible",
            "selected_lookup_case": "exact",
            "selected_query": "book",
            "selected_oewn_synset": "oewn-test-book-n",
            "selected_oewn_lexfile": "noun.artifact",
            "objectness_gate": "object_compatible",
            "synset_lemmas": "book",
            "canonical_surface": "book",
            "canonical_label_key": "book",
            "canonical_selection_tag": "prior_canonical",
        }
        book_synset = FakeSynset("oewn-test-book-n", "noun.artifact", ("book",))

        def object_lookup(surface: str):
            if surface == "book":
                return object_script._ObjectLookupResult(
                    lookup_case="last_word_lemma",
                    query="book",
                    synsets=(book_synset,),
                    selected_synset=book_synset,
                    synset_selection_tag="single_oewn_noun_synset",
                    wn30_lemma_counts="",
                    objectness_gate="object_compatible",
                    decision_status="chosen",
                    decision_reason="selected_object_compatible",
                )
            return None

        rows, summary = object_script.build_object_inventory_rows(
            [record],
            object_lookup=object_lookup,
            prior_rows_by_key={"book": prior_row},
        )

        self.assertEqual(rows[0]["span_key"], "books")
        self.assertEqual(rows[0]["selected_oewn_synset"], "oewn-test-book-n")
        self.assertEqual(rows[0]["canonical_surface"], "")
        self.assertNotIn(
            "prior_gpic_observed_object_inventory_selected_query",
            rows[0]["decision_basis"],
        )
        self.assertEqual(summary["prior_reused_rows"], 0)
        self.assertEqual(summary["prior_selected_query_reused_rows"], 0)

    def test_runtime_surface_query_conflict_requires_manual_without_prior(self) -> None:
        record = {
            "caption_id": "c-glasses",
            "tokens": [token(0, "glasses", "glass", "NOUN", "ROOT", 0, tag="NNS")],
            "noun_chunks": [chunk("glasses", 0, 0, 1)],
        }
        glasses_synset = FakeSynset("oewn-glasses-n", "noun.artifact", ("glasses",))
        glass_synset = FakeSynset("oewn-glass-n", "noun.substance", ("glass",))

        def object_lookup(surface: str):
            if surface == "glasses":
                return object_script._ObjectLookupResult(
                    lookup_case="exact",
                    query="glasses",
                    synsets=(glasses_synset,),
                    selected_synset=glasses_synset,
                    synset_selection_tag="single_oewn_noun_synset",
                    wn30_lemma_counts="",
                    objectness_gate="object_compatible",
                    decision_status="chosen",
                    decision_reason="selected_object_compatible",
                )
            if surface == "glass":
                return object_script._ObjectLookupResult(
                    lookup_case="last_word_lemma",
                    query="glass",
                    synsets=(glass_synset,),
                    selected_synset=glass_synset,
                    synset_selection_tag="single_oewn_noun_synset",
                    wn30_lemma_counts="",
                    objectness_gate="object_compatible",
                    decision_status="chosen",
                    decision_reason="selected_object_compatible",
                )
            return None

        rows, _summary = object_script.build_object_inventory_rows(
            [record],
            object_lookup=object_lookup,
        )

        self.assertEqual(rows[0]["span_key"], "glasses")
        self.assertEqual(rows[0]["decision_status"], "needs_manual")
        self.assertEqual(
            rows[0]["decision_reason"],
            "manual_surface_query_conflict_required",
        )
        self.assertEqual(rows[0]["selected_oewn_synset"], "")
        self.assertEqual(rows[0]["selected_query"], "glasses|glass")
        self.assertEqual(rows[0]["all_oewn_synsets"], "oewn-glasses-n|oewn-glass-n")

    def test_plural_exact_hit_with_ambiguous_base_hit_requires_manual(self) -> None:
        record = {
            "caption_id": "c-colors",
            "tokens": [token(0, "colors", "color", "NOUN", "ROOT", 0, tag="NNS")],
            "noun_chunks": [chunk("colors", 0, 0, 1)],
        }
        colors_synset = FakeSynset("oewn-colors-n", "noun.artifact", ("colors",))
        color_attribute_synset = FakeSynset("oewn-color-attribute-n", "noun.attribute", ("color",))
        color_substance_synset = FakeSynset("oewn-color-substance-n", "noun.substance", ("color",))

        def object_lookup(surface: str):
            if surface == "colors":
                return object_script._ObjectLookupResult(
                    lookup_case="exact",
                    query="colors",
                    synsets=(colors_synset,),
                    selected_synset=colors_synset,
                    synset_selection_tag="single_oewn_noun_synset",
                    wn30_lemma_counts="",
                    objectness_gate="object_compatible",
                    decision_status="chosen",
                    decision_reason="selected_object_compatible",
                )
            if surface == "color":
                return object_script._ObjectLookupResult(
                    lookup_case="exact",
                    query="color",
                    synsets=(color_attribute_synset, color_substance_synset),
                    selected_synset=None,
                    synset_selection_tag="ambiguous_wn30_all_zero",
                    wn30_lemma_counts="oewn-color-attribute-n:0|oewn-color-substance-n:0",
                    objectness_gate="",
                    decision_status="needs_manual",
                    decision_reason="manual_synset_required",
                )
            return None

        rows, _summary = object_script.build_object_inventory_rows(
            [record],
            object_lookup=object_lookup,
        )

        self.assertEqual(rows[0]["span_key"], "colors")
        self.assertEqual(rows[0]["decision_status"], "needs_manual")
        self.assertEqual(
            rows[0]["decision_reason"],
            "manual_surface_query_conflict_required",
        )
        self.assertEqual(rows[0]["selected_lookup_case"], "plural_surface_query_conflict")
        self.assertEqual(rows[0]["selected_oewn_synset"], "")
        self.assertEqual(rows[0]["selected_query"], "colors|color")
        self.assertEqual(
            rows[0]["all_oewn_synsets"],
            "oewn-colors-n|oewn-color-attribute-n|oewn-color-substance-n",
        )

    def test_automatic_surface_changed_prior_row_is_not_reusable(self) -> None:
        auto_row = {
            "span_key": "glasses",
            "observed_surface": "glasses",
            "decision_status": "chosen",
            "selected_query": "glass",
            "selected_oewn_synset": "oewn-glass-n",
            "canonical_surface": "glass",
        }
        manual_row = {
            **auto_row,
            "decision_basis": "manual_object_resolution",
        }

        self.assertFalse(object_script._is_reusable_prior_row(auto_row))
        self.assertTrue(object_script._is_reusable_prior_row(manual_row))

    def test_checkpoint_resume_continues_counts_from_record_boundary(self) -> None:
        records = [
            {
                "caption_id": "c1",
                "tokens": [token(0, "dog", "dog", "NOUN", "ROOT", 0)],
                "noun_chunks": [chunk("dog", 0, 0, 1)],
            },
            {
                "caption_id": "c2",
                "tokens": [token(0, "dog", "dog", "NOUN", "ROOT", 0)],
                "noun_chunks": [chunk("dog", 0, 0, 1)],
            },
        ]
        dog_synset = FakeSynset("oewn-dog-n", "noun.animal", ("dog",))

        def object_lookup(surface: str):
            if surface != "dog":
                return None
            return object_script._ObjectLookupResult(
                lookup_case="exact",
                query="dog",
                synsets=(dog_synset,),
                selected_synset=dog_synset,
                synset_selection_tag="single_oewn_noun_synset",
                wn30_lemma_counts="",
                objectness_gate="object_compatible",
                decision_status="chosen",
                decision_reason="selected_object_compatible",
            )

        with tempfile.TemporaryDirectory() as tmp:
            checkpoint_path = Path(tmp) / "object_checkpoint.json"
            metadata = {"input": "stage3.jsonl", "output": "object.tsv"}
            writer = object_script.ObjectInventoryCheckpointWriter(
                checkpoint_path,
                metadata=metadata,
                interval_records=1,
            )
            object_script.build_object_inventory_rows(
                records[:1],
                object_lookup=object_lookup,
                checkpoint_writer=writer,
            )
            checkpoint = object_script._load_checkpoint(checkpoint_path, metadata)
            self.assertIsNotNone(checkpoint)
            assert checkpoint is not None
            rows, summary = object_script.build_object_inventory_rows(
                records[1:],
                object_lookup=object_lookup,
                initial_inventory=checkpoint.inventory,
                initial_caption_total=checkpoint.caption_total,
                initial_noun_chunk_total=checkpoint.noun_chunk_total,
                initial_prior_reused_hits=checkpoint.prior_reused_hits,
            )

        self.assertEqual(summary["caption_total"], 2)
        self.assertEqual(rows[0]["span_key"], "dog")
        self.assertEqual(rows[0]["count"], "2")
        self.assertEqual(rows[0]["caption_count"], "2")
        self.assertEqual(rows[0]["selected_oewn_synset"], "oewn-dog-n")

    def test_prior_bundle_supplies_object_inventory_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "inventory_bundle.json"
            object_path = root / "object_inventory.tsv"
            bundle_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "gpic_inventory_bundle",
                        "status": "complete",
                        "object_inventory": str(object_path),
                        "attribute_inventory": str(root / "attribute_inventory.tsv"),
                        "action_inventory": str(root / "action_inventory.tsv"),
                        "lexicon_dir": str(root / "lexicons"),
                    },
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                prior_inventory_bundle=str(bundle_path),
                prior_object_inventory=None,
            )

            self.assertEqual(
                object_script._prior_object_inventory_from_args(args),
                object_path,
            )

    def test_prior_bundle_mismatch_blocks_explicit_object_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "inventory_bundle.json"
            object_path = root / "object_inventory.tsv"
            bundle_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "gpic_inventory_bundle",
                        "status": "complete",
                        "object_inventory": str(object_path),
                        "attribute_inventory": str(root / "attribute_inventory.tsv"),
                        "action_inventory": str(root / "action_inventory.tsv"),
                        "lexicon_dir": str(root / "lexicons"),
                    },
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                prior_inventory_bundle=str(bundle_path),
                prior_object_inventory=str(root / "other_object_inventory.tsv"),
            )

            with self.assertRaisesRegex(ValueError, "inventory_bundle_path_mismatch"):
                object_script._prior_object_inventory_from_args(args)


if __name__ == "__main__":
    unittest.main()
