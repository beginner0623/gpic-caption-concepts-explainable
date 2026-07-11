import argparse
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


def _load_attribute_canonical_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "enrich_gpic_attribute_inventory_canonical.py"
    spec = importlib.util.spec_from_file_location("enrich_gpic_attribute_inventory_canonical", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


attribute_canonical_script = _load_attribute_canonical_script()


class EnrichGpicAttributeInventoryCanonicalTest(unittest.TestCase):
    def test_needs_manual_rows_block_before_oewn_load(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            ngram_evidence=None,
            ambiguous_output="ambiguous.tsv",
            summary=None,
        )
        rows = [
            {
                "observed_surface": "wooden",
                "span_key": "wooden",
                "decision_status": "needs_manual",
                "decision_reason": "manual_attribute_gate_required",
                "selected_query": "wooden",
                "selected_oewn_synset": "fake-wooden-a",
                "attribute_gate": "conditional",
            }
        ]

        with (
            patch.object(attribute_canonical_script, "parse_args", return_value=args),
            patch.object(
                attribute_canonical_script,
                "_read_tsv",
                return_value=(rows, ["decision_status"]),
            ),
            patch.object(attribute_canonical_script.wn, "Wordnet") as wordnet,
            patch("builtins.print"),
        ):
            with self.assertRaises(SystemExit) as caught:
                attribute_canonical_script.main()

        self.assertIn("blocked_rows=1", str(caught.exception))
        wordnet.assert_not_called()

    def test_no_synset_rows_are_marked_not_applicable(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            ngram_evidence=None,
            ambiguous_output="ambiguous.tsv",
            summary=None,
        )
        rows = [
            {
                "observed_surface": "sparkly",
                "span_key": "sparkly",
                "decision_status": "chosen",
                "decision_reason": "no_oewn_attribute_synset",
                "selected_query": "sparkly",
                "selected_oewn_synset": "",
            }
        ]
        fake_oewn = Mock()

        with (
            patch.object(attribute_canonical_script, "parse_args", return_value=args),
            patch.object(
                attribute_canonical_script,
                "_read_tsv",
                return_value=(rows, ["decision_status", "selected_oewn_synset"]),
            ),
            patch.object(attribute_canonical_script, "_write_tsv") as write_tsv,
            patch.object(attribute_canonical_script.wn, "Wordnet", return_value=fake_oewn),
            patch.object(attribute_canonical_script, "Morphy", return_value=object()),
            patch("builtins.print"),
        ):
            attribute_canonical_script.main()

        self.assertEqual(rows[0]["canonical_selection_tag"], "not_applicable_no_selected_synset")
        fake_oewn.synset.assert_not_called()
        self.assertEqual(write_tsv.call_count, 2)

    def test_attribute_canonical_uses_attribute_morphy_pos(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            ngram_evidence=None,
            ambiguous_output="ambiguous.tsv",
            summary=None,
        )
        rows = [{"decision_status": "chosen", "selected_oewn_synset": "fake-striped-a"}]
        fake_oewn = Mock()
        fake_oewn.synset.return_value = object()

        with (
            patch.object(attribute_canonical_script, "parse_args", return_value=args),
            patch.object(
                attribute_canonical_script,
                "_read_tsv",
                return_value=(rows, ["decision_status", "selected_oewn_synset"]),
            ),
            patch.object(attribute_canonical_script, "_write_tsv"),
            patch.object(attribute_canonical_script.wn, "Wordnet", return_value=fake_oewn),
            patch.object(attribute_canonical_script, "Morphy", return_value=object()),
            patch.object(
                attribute_canonical_script,
                "_decide_canonical",
                return_value={
                    "canonical_surface": "striped",
                    "canonical_label_key": "striped",
                    "canonical_selection_tag": "selected_single_observed_variant_matched_synset_lemma",
                    "canonical_candidate_lemmas": "striped",
                    "canonical_candidate_lemma_counts": "striped:0",
                    "google_ngram_candidate_surfaces": "",
                    "google_ngram_candidate_mean_frequencies": "",
                },
            ) as decide,
            patch("builtins.print"),
        ):
            attribute_canonical_script.main()

        self.assertEqual(decide.call_args.kwargs["morphy_pos"], ("a", "n", "v", "r"))

    def test_manual_canonical_fields_are_ignored_and_recomputed(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            ngram_evidence=None,
            ambiguous_output="ambiguous.tsv",
            summary=None,
        )
        rows = [
            {
                "decision_status": "chosen",
                "selected_oewn_synset": "fake-dark-a",
                "canonical_surface": "manual-dark",
                "canonical_label_key": "manual-dark",
                "canonical_selection_tag": "manual_surface_canonical",
            }
        ]
        fake_oewn = Mock()
        fake_oewn.synset.return_value = object()

        with (
            patch.object(attribute_canonical_script, "parse_args", return_value=args),
            patch.object(
                attribute_canonical_script,
                "_read_tsv",
                return_value=(rows, ["decision_status", "selected_oewn_synset"]),
            ),
            patch.object(attribute_canonical_script, "_write_tsv"),
            patch.object(attribute_canonical_script.wn, "Wordnet", return_value=fake_oewn),
            patch.object(attribute_canonical_script, "Morphy", return_value=object()),
            patch.object(
                attribute_canonical_script,
                "_decide_canonical",
                return_value={
                    "canonical_surface": "dark",
                    "canonical_label_key": "dark",
                    "canonical_selection_tag": "selected_single_observed_variant_matched_synset_lemma",
                    "canonical_candidate_lemmas": "dark",
                    "canonical_candidate_lemma_counts": "dark:0",
                    "google_ngram_candidate_surfaces": "",
                    "google_ngram_candidate_mean_frequencies": "",
                },
            ) as decide,
            patch("builtins.print"),
        ):
            attribute_canonical_script.main()

        decide.assert_called_once()
        self.assertEqual(rows[0]["canonical_surface"], "dark")
        self.assertEqual(
            rows[0]["canonical_selection_tag"],
            "selected_single_observed_variant_matched_synset_lemma",
        )

    def test_excluded_rows_clear_manual_canonical_surface(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            ngram_evidence=None,
            ambiguous_output="ambiguous.tsv",
            summary=None,
        )
        rows = [
            {
                "observed_surface": "Several",
                "span_key": "several",
                "decision_status": "excluded",
                "decision_reason": "manual_excluded_quantity_like_modifier_count_included",
                "selected_oewn_synset": "fake-several-a",
                "canonical_surface": "several",
                "canonical_label_key": "several",
                "canonical_selection_tag": "manual_surface_canonical",
            }
        ]
        fake_oewn = Mock()

        with (
            patch.object(attribute_canonical_script, "parse_args", return_value=args),
            patch.object(
                attribute_canonical_script,
                "_read_tsv",
                return_value=(rows, ["decision_status", "selected_oewn_synset"]),
            ),
            patch.object(attribute_canonical_script, "_write_tsv") as write_tsv,
            patch.object(attribute_canonical_script.wn, "Wordnet", return_value=fake_oewn),
            patch.object(attribute_canonical_script, "Morphy", return_value=object()),
            patch.object(attribute_canonical_script, "_decide_canonical") as decide,
            patch("builtins.print"),
        ):
            attribute_canonical_script.main()

        fake_oewn.synset.assert_not_called()
        decide.assert_not_called()
        self.assertEqual(rows[0]["canonical_surface"], "")
        self.assertEqual(rows[0]["canonical_label_key"], "")
        self.assertEqual(rows[0]["canonical_selection_tag"], "not_applicable_excluded")
        self.assertEqual(write_tsv.call_count, 2)

    def test_chosen_manual_row_without_synset_stays_chosen_without_canonical(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            ngram_evidence=None,
            ambiguous_output="ambiguous.tsv",
            summary=None,
        )
        rows = [
            {
                "observed_surface": "TYR",
                "span_key": "tyr",
                "decision_status": "chosen",
                "decision_reason": "manual_chosen_oewn_false_positive_brand_modifier_no_synset",
                "selected_oewn_synset": "",
                "canonical_surface": "tyr",
                "canonical_label_key": "tyr",
                "canonical_selection_tag": "manual_surface_canonical",
            }
        ]
        fake_oewn = Mock()

        with (
            patch.object(attribute_canonical_script, "parse_args", return_value=args),
            patch.object(
                attribute_canonical_script,
                "_read_tsv",
                return_value=(rows, ["decision_status", "selected_oewn_synset"]),
            ),
            patch.object(attribute_canonical_script, "_write_tsv") as write_tsv,
            patch.object(attribute_canonical_script.wn, "Wordnet", return_value=fake_oewn),
            patch.object(attribute_canonical_script, "Morphy", return_value=object()),
            patch.object(attribute_canonical_script, "_decide_canonical") as decide,
            patch("builtins.print"),
        ):
            attribute_canonical_script.main()

        fake_oewn.synset.assert_not_called()
        decide.assert_not_called()
        self.assertEqual(rows[0]["decision_status"], "chosen")
        self.assertEqual(
            rows[0]["decision_reason"],
            "manual_chosen_oewn_false_positive_brand_modifier_no_synset",
        )
        self.assertEqual(rows[0]["canonical_surface"], "")
        self.assertEqual(rows[0]["canonical_label_key"], "")
        self.assertEqual(rows[0]["canonical_selection_tag"], "not_applicable_no_selected_synset")
        self.assertEqual(write_tsv.call_count, 2)


if __name__ == "__main__":
    unittest.main()
