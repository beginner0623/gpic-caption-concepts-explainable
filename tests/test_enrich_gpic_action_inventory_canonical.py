from pathlib import Path
import importlib.util
import unittest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "enrich_gpic_action_inventory_canonical.py"
    spec = importlib.util.spec_from_file_location("enrich_gpic_action_inventory_canonical", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EnrichGpicActionInventoryCanonicalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = _load_script()

    def test_action_canonical_blocks_pending_manual_rows(self) -> None:
        blockers = self.script._action_canonical_blockers(
            [
                {
                    "span_key": "shining",
                    "observed_surface": "shining",
                    "decision_status": "needs_manual",
                    "selected_query": "shin|shine",
                }
            ]
        )

        self.assertEqual(len(blockers), 1)
        self.assertEqual(
            blockers[0]["blocker_reason"],
            "pending_action_manual_decision_status",
        )

    def test_action_canonical_allows_raw_fallback_without_synset(self) -> None:
        blockers = self.script._action_canonical_blockers(
            [
                {
                    "span_key": "high-fives",
                    "observed_surface": "high-fives",
                    "decision_status": "raw_fallback",
                    "selected_oewn_synset": "",
                }
            ]
        )

        self.assertEqual(blockers, [])

    def test_action_canonical_uses_verb_morphy_variant(self) -> None:
        row = {
            "span_key": "shining",
            "observed_surface": "shining",
            "example_surfaces": "shining",
            "selected_query": "shine",
            "selected_oewn_synset": "fake-shine-v",
        }
        decision = self.script._decide_canonical(
            row,
            synset=FakeSynset(["shine"]),
            morphy=FakeMorphy({"shining": {"v": {"shine"}}}),
            ngram_evidence={},
            morphy_pos=self.script.ACTION_CANONICAL_MORPHY_POS,
        )

        self.assertEqual(decision["canonical_surface"], "shine")
        self.assertEqual(
            decision["canonical_selection_tag"],
            "selected_single_observed_variant_matched_synset_lemma",
        )


class FakeSynset:
    def __init__(self, lemmas: list[str]) -> None:
        self._lemmas = lemmas

    def lemmas(self) -> list[str]:
        return self._lemmas

    def senses(self) -> list[object]:
        return []


class FakeMorphy:
    def __init__(self, result_by_query: dict[str, dict[str, set[str]]]) -> None:
        self._result_by_query = result_by_query

    def __call__(self, query: str, pos: str) -> dict[str, set[str]]:
        return self._result_by_query.get(query, {})


if __name__ == "__main__":
    unittest.main()
