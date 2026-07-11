import argparse
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


def _load_parent_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "enrich_gpic_inventory_parents.py"
    spec = importlib.util.spec_from_file_location("enrich_gpic_inventory_parents", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parent_script = _load_parent_script()


class EnrichGpicInventoryParentsTest(unittest.TestCase):
    def test_main_exits_before_parent_when_manual_resolution_pending(self) -> None:
        args = argparse.Namespace(
            input="input.tsv",
            output="output.tsv",
            summary=None,
        )
        rows = [
            {
                "observed_surface": "white feathers",
                "span_key": "white feathers",
                "decision_status": "chosen",
                "selected_query": "white feather",
                "selected_oewn_synset": "",
                "canonical_surface": "feather",
            }
        ]

        with (
            patch.object(parent_script, "parse_args", return_value=args),
            patch.object(
                parent_script,
                "_read_tsv",
                return_value=(rows, ["decision_status"]),
            ),
            patch.object(parent_script.wn, "Wordnet") as wordnet,
            patch("builtins.print"),
        ):
            with self.assertRaises(SystemExit) as caught:
                parent_script.main()

        self.assertIn("blocked_rows=1", str(caught.exception))
        wordnet.assert_not_called()


if __name__ == "__main__":
    unittest.main()
