import importlib.util
from pathlib import Path
import sys
import unittest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "enrich_gpic_inventory_synset_metadata.py"
    spec = importlib.util.spec_from_file_location("enrich_gpic_inventory_synset_metadata", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


class FakeSynset:
    id = "oewn-glasses-n"

    def lexfile(self) -> str:
        return "noun.artifact"

    def lemmas(self) -> list[str]:
        return ["spectacles", "eyeglasses", "glasses"]


class EnrichGpicInventorySynsetMetadataTest(unittest.TestCase):
    def test_refresh_row_fills_selected_synset_metadata(self) -> None:
        row = {
            "span_key": "glasses",
            "selected_oewn_synset": "oewn-glasses-n",
            "selected_oewn_lexfile": "",
            "objectness_gate": "",
            "synset_lemmas": "",
            "all_oewn_synsets": "",
            "all_oewn_lexfiles": "",
        }

        changed = script._refresh_row(row, synset=FakeSynset())

        self.assertGreater(changed, 0)
        self.assertEqual(row["has_oewn_noun_synset"], "true")
        self.assertEqual(row["selected_oewn_lexfile"], "noun.artifact")
        self.assertEqual(row["objectness_gate"], "object_compatible")
        self.assertEqual(row["synset_lemmas"], "spectacles|eyeglasses|glasses")
        self.assertEqual(row["all_oewn_synsets"], "oewn-glasses-n")
        self.assertEqual(row["all_oewn_lexfiles"], "oewn-glasses-n:noun.artifact")


if __name__ == "__main__":
    unittest.main()
