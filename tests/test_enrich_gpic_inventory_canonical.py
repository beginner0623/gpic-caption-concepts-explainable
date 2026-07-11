import argparse
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


def _load_canonical_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "enrich_gpic_inventory_canonical.py"
    spec = importlib.util.spec_from_file_location("enrich_gpic_inventory_canonical", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


canonical_script = _load_canonical_script()


class EnrichGpicInventoryCanonicalTest(unittest.TestCase):
    def test_surface_key_folds_diacritics_for_canonical_matching(self) -> None:
        self.assertEqual(canonical_script._surface_key("café"), "cafe")

    def test_main_exits_before_canonical_when_needs_manual_rows_remain(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            ngram_evidence=None,
            ambiguous_output="ambiguous.tsv",
            summary=None,
        )
        rows = [
            {
                "observed_surface": "jersey",
                "span_key": "jersey",
                "decision_status": "needs_manual",
                "decision_reason": "manual_synset_required",
                "selected_query": "jersey",
                "selected_oewn_synset": "",
                "synset_selection_tag": "ambiguous_wn30_all_zero",
            }
        ]

        with (
            patch.object(canonical_script, "parse_args", return_value=args),
            patch.object(
                canonical_script,
                "_read_tsv",
                return_value=(rows, ["decision_status"]),
            ),
            patch.object(canonical_script.wn, "Wordnet") as wordnet,
            patch("builtins.print"),
        ):
            with self.assertRaises(SystemExit) as caught:
                canonical_script.main()

        self.assertIn("blocked_rows=1", str(caught.exception))
        wordnet.assert_not_called()

    def test_main_exits_when_surface_correction_has_no_selected_synset(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            ngram_evidence=None,
            ambiguous_output="ambiguous.tsv",
            summary=None,
        )
        rows = [
            {
                "observed_surface": "white feathers",
                "span_key": "white feathers",
                "decision_status": "chosen",
                "decision_reason": "manual_joined_head_correction_synset_missing",
                "selected_query": "white feather",
                "selected_oewn_synset": "",
                "canonical_surface": "feather",
            }
        ]

        with (
            patch.object(canonical_script, "parse_args", return_value=args),
            patch.object(
                canonical_script,
                "_read_tsv",
                return_value=(rows, ["decision_status"]),
            ),
            patch.object(canonical_script.wn, "Wordnet") as wordnet,
            patch("builtins.print"),
        ):
            with self.assertRaises(SystemExit) as caught:
                canonical_script.main()

        self.assertIn("blocked_rows=1", str(caught.exception))
        wordnet.assert_not_called()

    def test_main_exits_nonzero_when_canonical_ambiguity_remains(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            ngram_evidence=None,
            ambiguous_output="ambiguous.tsv",
            summary=None,
        )
        rows = [{"decision_status": "chosen", "selected_oewn_synset": "fake-synset-n"}]
        fake_oewn = Mock()
        fake_oewn.synset.return_value = object()

        with (
            patch.object(canonical_script, "parse_args", return_value=args),
            patch.object(
                canonical_script,
                "_read_tsv",
                return_value=(rows, ["selected_oewn_synset"]),
            ),
            patch.object(canonical_script, "_write_tsv") as write_tsv,
            patch.object(canonical_script.wn, "Wordnet", return_value=fake_oewn),
            patch.object(canonical_script, "Morphy", return_value=object()),
            patch("builtins.print"),
            patch.object(
                canonical_script,
                "_decide_canonical",
                return_value={
                    "canonical_surface": "",
                    "canonical_label_key": "",
                    "canonical_selection_tag": "ambiguous_google_ngram_tie",
                    "canonical_candidate_lemmas": "sun|Sun",
                    "canonical_candidate_lemma_counts": "sun:1|Sun:1",
                    "google_ngram_candidate_surfaces": "sun|Sun",
                    "google_ngram_candidate_mean_frequencies": "sun:1|Sun:1",
                },
            ),
        ):
            with self.assertRaises(SystemExit) as caught:
                canonical_script.main()

        self.assertIn("canonical_ambiguous_rows=1", str(caught.exception))
        self.assertEqual(write_tsv.call_count, 2)


if __name__ == "__main__":
    unittest.main()
