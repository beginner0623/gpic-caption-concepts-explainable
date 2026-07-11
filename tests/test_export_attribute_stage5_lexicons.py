import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "export_attribute_stage5_lexicons.py"
    spec = importlib.util.spec_from_file_location("export_attribute_stage5_lexicons", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


class ExportAttributeStage5LexiconsTest(unittest.TestCase):
    def test_excluded_rows_do_not_export_canonical_synonym(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            inventory = root / "typed.tsv"
            output_dir = root / "lexicons"
            _write_inventory(
                inventory,
                [
                    {
                        "span_key": "scarlet",
                        "observed_surface": "scarlet",
                        "decision_status": "chosen",
                        "decision_reason": "selected_attribute_compatible",
                        "canonical_surface": "red",
                        "canonical_selection_tag": "selected_by_wn30",
                        "attribute_type": "color_attribute",
                        "attribute_type_selection_tag": "manual",
                    },
                    {
                        "span_key": "tyr",
                        "observed_surface": "TYR",
                        "decision_status": "excluded",
                        "decision_reason": "manual_excluded_brand_modifier",
                        "canonical_surface": "tyr",
                        "canonical_selection_tag": "manual_surface_canonical",
                        "attribute_type": "brand_text_modifier_attribute",
                        "attribute_type_selection_tag": "manual",
                    },
                    {
                        "span_key": "sparkly",
                        "observed_surface": "sparkly",
                        "decision_status": "chosen",
                        "decision_reason": "no_oewn_attribute_synset",
                        "selected_oewn_synset": "",
                        "canonical_surface": "",
                        "canonical_selection_tag": "not_applicable_no_selected_synset",
                        "attribute_type": "visual_attribute",
                        "attribute_type_selection_tag": "manual",
                    },
                ],
            )

            summary = script.export_attribute_stage5_lexicons(
                attribute_inventory_path=inventory,
                output_dir=output_dir,
                base_lexicon_dir=None,
            )

            synonyms = _read_tsv(output_dir / "attribute_synonyms.tsv")
            types = _read_tsv(output_dir / "attribute_types.tsv")

            self.assertEqual(summary["chosen_synonym_rows_added"], 1)
            self.assertEqual(summary["ignored_excluded_canonical_rows"], 1)
            self.assertEqual(summary["attribute_type_rows"], 0)
            self.assertEqual(summary["attribute_type_rows_deferred"], 3)
            self.assertEqual(
                synonyms,
                [
                    {
                        "raw": "scarlet",
                        "canonical": "red",
                        "source": "gpic_observed_attribute_inventory",
                        "notes": (
                            "export_tag=chosen_canonical_synonym; "
                            "decision_status=chosen; "
                            "canonical_selection_tag=selected_by_wn30; "
                            "decision_reason=selected_attribute_compatible"
                        ),
                    }
                ],
            )
            self.assertEqual(types, [])

    def test_action_canonical_inventory_exports_action_synonyms(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            attribute_inventory = root / "attributes.tsv"
            action_inventory = root / "actions.tsv"
            output_dir = root / "lexicons"
            _write_inventory(attribute_inventory, [])
            _write_action_inventory(
                action_inventory,
                [
                    {
                        "span_key": "shining",
                        "observed_surface": "shining",
                        "decision_status": "chosen",
                        "decision_reason": "manual_action_synset_selected",
                        "selected_oewn_synset": "oewn-02771882-v",
                        "canonical_surface": "shine",
                        "canonical_selection_tag": "selected_single_observed_variant_matched_synset_lemma",
                    },
                    {
                        "span_key": "ROSE",
                        "observed_surface": "ROSE",
                        "decision_status": "raw_fallback",
                        "decision_reason": "no_oewn_verb_synset",
                        "selected_oewn_synset": "",
                        "canonical_surface": "",
                        "canonical_selection_tag": "not_applicable_raw_fallback_no_selected_synset",
                    },
                ],
            )

            summary = script.export_attribute_stage5_lexicons(
                attribute_inventory_path=attribute_inventory,
                action_canonical_inventory_path=action_inventory,
                output_dir=output_dir,
                base_lexicon_dir=None,
            )

            actions = _read_tsv(output_dir / "action_synonyms.tsv")

            self.assertEqual(summary["action_synonym_rows_added"], 1)
            self.assertEqual(summary["action_raw_fallback_rows_skipped"], 1)
            self.assertEqual(
                actions,
                [
                    {
                        "raw": "shining",
                        "canonical": "shine",
                        "source": "gpic_observed_action_inventory",
                        "notes": (
                            "export_tag=chosen_action_canonical_synonym; "
                            "decision_status=chosen; "
                            "canonical_selection_tag=selected_single_observed_variant_matched_synset_lemma; "
                            "decision_reason=manual_action_synset_selected"
                        ),
                    }
                ],
            )


def _write_inventory(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "span_key",
        "observed_surface",
        "decision_status",
        "decision_reason",
        "canonical_surface",
        "canonical_selection_tag",
        "selected_oewn_synset",
        "attribute_type",
        "attribute_type_selection_tag",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _write_action_inventory(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "span_key",
        "observed_surface",
        "decision_status",
        "decision_reason",
        "selected_oewn_synset",
        "canonical_surface",
        "canonical_selection_tag",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _safe_temp_base() -> str:
    path = Path(__file__).absolute().parents[1] / ".tmp_tests" / "gpic_export_attribute_stage5_lexicons"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


if __name__ == "__main__":
    unittest.main()
