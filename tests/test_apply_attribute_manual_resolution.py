import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "apply_attribute_manual_resolution.py"
    spec = importlib.util.spec_from_file_location("apply_attribute_manual_resolution", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


class ApplyAttributeManualResolutionTest(unittest.TestCase):
    def test_resolved_subset_replaces_needs_manual_rows_only(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            output = root / "merged.tsv"
            _write_tsv(
                full,
                [
                    {
                        "span_key": "white",
                        "observed_surface": "white",
                        "decision_status": "chosen",
                        "decision_reason": "selected_attribute_compatible",
                        "selected_oewn_synset": "oewn-white-a",
                        "canonical_surface": "",
                    },
                    {
                        "span_key": "several",
                        "observed_surface": "Several",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_synset_required",
                        "selected_oewn_synset": "",
                        "canonical_surface": "",
                    },
                ],
            )
            _write_tsv(
                resolved,
                [
                    {
                        "span_key": "several",
                        "observed_surface": "Several",
                        "decision_status": "accepted",
                        "decision_reason": "manual_selected_attribute_compatible_synset",
                        "selected_oewn_synset": "oewn-several-s",
                        "canonical_surface": "several",
                        "canonical_selection_tag": "manual_surface_preserved",
                        "manual_confidence": "medium",
                    },
                ],
                extra_fieldnames=["manual_confidence"],
            )

            summary = script.apply_attribute_manual_resolution(
                full_inventory_path=full,
                resolved_subset_path=resolved,
                output_path=output,
            )

            rows = _read_tsv(output)
            self.assertEqual(summary["overlaid_rows"], 1)
            self.assertEqual(summary["merged_decision_status_counts"], {"chosen": 2})
            self.assertEqual(rows[0]["span_key"], "white")
            self.assertEqual(rows[0]["canonical_surface"], "")
            self.assertEqual(rows[1]["span_key"], "several")
            self.assertEqual(rows[1]["decision_status"], "chosen")
            self.assertEqual(rows[1]["canonical_surface"], "")
            self.assertEqual(rows[1]["canonical_selection_tag"], "")
            self.assertEqual(rows[1]["manual_confidence"], "medium")

    def test_missing_needs_manual_resolution_blocks(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            _write_tsv(
                full,
                [
                    {"span_key": "several", "decision_status": "needs_manual"},
                    {"span_key": "overall", "decision_status": "needs_manual"},
                ],
            )
            _write_tsv(resolved, [{"span_key": "several", "decision_status": "chosen"}])

            with self.assertRaises(ValueError) as caught:
                script.apply_attribute_manual_resolution(
                    full_inventory_path=full,
                    resolved_subset_path=resolved,
                    output_path=root / "merged.tsv",
                )

            self.assertIn("manual_resolution_key_mismatch", str(caught.exception))
            self.assertIn("overall", str(caught.exception))


def _write_tsv(
    path: Path,
    rows: list[dict[str, str]],
    *,
    extra_fieldnames: list[str] | None = None,
) -> None:
    fieldnames = [
        "span_key",
        "observed_surface",
        "decision_status",
        "decision_reason",
        "selected_oewn_synset",
        "canonical_surface",
        "canonical_selection_tag",
    ]
    for field in extra_fieldnames or []:
        if field not in fieldnames:
            fieldnames.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _safe_temp_base() -> str:
    path = Path(__file__).absolute().parents[1] / ".tmp_tests" / "gpic_apply_attribute_manual_resolution"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


if __name__ == "__main__":
    unittest.main()
