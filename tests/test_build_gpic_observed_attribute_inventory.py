import importlib.util
from pathlib import Path
import sys
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
            return object() if surface == "trash can" else None

        black_synset = FakeSynset("fake-black-a", "adj.all", ("black",))

        def attribute_lookup(surface: str):
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

        class ObjectLookup:
            canonical_surface = "top"
            canonical_label_key = "top"
            selected_synset = None
            query = "black top"

        def object_lookup(surface: str):
            return ObjectLookup() if surface == "black top" else None

        black_synset = FakeSynset("fake-black-a", "adj.all", ("black",))

        def attribute_lookup(surface: str):
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
            return object() if surface == "jerseys" else None

        maroon_synset = FakeSynset("fake-maroon-a", "adj.all", ("maroon",))

        def attribute_lookup(surface: str):
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
            return object() if surface == "car" else None

        def attribute_lookup(surface: str):
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
