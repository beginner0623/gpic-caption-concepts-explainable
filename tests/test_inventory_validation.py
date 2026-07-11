import unittest

from gpic_concepts_v1.inventory_validation import (
    final_manual_resolution_blockers,
    normalize_inventory_decision_status,
)


class InventoryValidationTest(unittest.TestCase):
    def test_unknown_explicit_decision_status_is_pending_manual(self) -> None:
        row = {"decision_status": "manual_required"}

        self.assertEqual(normalize_inventory_decision_status(row), "needs_manual")

    def test_chosen_surface_correction_without_synset_blocks(self) -> None:
        blockers = final_manual_resolution_blockers(
            [
                {
                    "span_key": "white feathers",
                    "observed_surface": "white feathers",
                    "decision_status": "chosen",
                    "selected_query": "white feather",
                    "selected_oewn_synset": "",
                    "canonical_surface": "feather",
                }
            ]
        )

        self.assertEqual(len(blockers), 1)
        self.assertEqual(
            blockers[0]["blocker_reason"],
            "surface_correction_requires_synset_lookup",
        )

    def test_chosen_no_synset_same_surface_does_not_block(self) -> None:
        blockers = final_manual_resolution_blockers(
            [
                {
                    "span_key": "unknown visual thing",
                    "observed_surface": "unknown visual thing",
                    "decision_status": "chosen",
                    "selected_query": "unknown visual thing",
                    "selected_oewn_synset": "",
                    "canonical_surface": "unknown visual thing",
                }
            ]
        )

        self.assertEqual(blockers, [])

    def test_selected_synset_without_canonical_surface_blocks_when_required(self) -> None:
        blockers = final_manual_resolution_blockers(
            [
                {
                    "span_key": "sun",
                    "observed_surface": "sun",
                    "decision_status": "chosen",
                    "selected_oewn_synset": "fake-sun-n",
                    "canonical_surface": "",
                }
            ],
            require_canonical_surface_for_selected_synset=True,
        )

        self.assertEqual(len(blockers), 1)
        self.assertEqual(
            blockers[0]["blocker_reason"],
            "selected_synset_missing_canonical_surface",
        )

    def test_excluded_no_synset_does_not_block(self) -> None:
        blockers = final_manual_resolution_blockers(
            [
                {
                    "span_key": "it",
                    "observed_surface": "it",
                    "decision_status": "excluded",
                    "selected_oewn_synset": "",
                }
            ]
        )

        self.assertEqual(blockers, [])


if __name__ == "__main__":
    unittest.main()
