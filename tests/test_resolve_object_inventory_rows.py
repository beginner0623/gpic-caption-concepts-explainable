from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "resolve_object_inventory_rows.py"
    spec = importlib.util.spec_from_file_location("resolve_object_inventory_rows", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver = _load_script()


class ResolveObjectInventoryRowsTests(unittest.TestCase):
    def test_blocks_manual_canonical_override_when_ngram_evidence_is_missing(self) -> None:
        row = {
            "span_key": "corn cobs",
            "selected_oewn_synset": "oewn-08561700-n",
            "canonical_selection_tag": (
                "ambiguous_wn30_all_zero_or_missing_google_ngram_evidence_missing"
            ),
            "google_ngram_candidate_surfaces": "corncob|corn cob",
        }
        decision = {
            "span_key": "corn cobs",
            "selected_query": "corn cob",
            "selected_oewn_synset": "oewn-08561700-n",
            "canonical_surface": "corn cob",
            "reason": "manual_canonical_guess",
        }

        with self.assertRaises(ValueError) as caught:
            resolver._apply_decision(row, decision=decision, oewn=object(), source="test")

        message = str(caught.exception)
        self.assertIn("Google Ngram evidence is missing", message)
        self.assertIn("corncob|corn cob", message)
        self.assertNotIn("previous_canonical_selection_tag", row)


if __name__ == "__main__":
    unittest.main()
