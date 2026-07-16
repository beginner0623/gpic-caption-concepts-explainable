import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "apply_object_manual_resolution.py"
    spec = importlib.util.spec_from_file_location("apply_object_manual_resolution", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


class ApplyObjectManualResolutionTest(unittest.TestCase):
    def test_accept_status_becomes_chosen_and_canonical_is_cleared(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            output = root / "merged.tsv"
            _write_tsv(
                full,
                [
                    {
                        "span_key": "dog",
                        "observed_surface": "dog",
                        "decision_status": "chosen",
                        "decision_reason": "selected_object_compatible",
                        "selected_oewn_synset": "oewn-dog-n",
                        "canonical_surface": "dog",
                    },
                    {
                        "span_key": "light",
                        "observed_surface": "light",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_objectness_required",
                        "selected_oewn_synset": "oewn-old-light-n",
                        "canonical_surface": "",
                    },
                ],
            )
            _write_tsv(
                resolved,
                [
                    {
                        "span_key": "light",
                        "observed_surface": "light",
                        "decision_status": "accepted",
                        "decision_reason": "manual_accept_by_synset_presence_rule",
                        "selected_oewn_synset": "oewn-light-n",
                        "canonical_surface": "manual-ignored",
                        "manual_confidence": "medium",
                    },
                ],
                extra_fieldnames=["manual_confidence"],
            )

            summary = script.apply_object_manual_resolution(
                full_inventory_path=full,
                resolved_subset_path=resolved,
                output_path=output,
            )

            rows = _read_tsv(output)
            self.assertEqual(summary["overlaid_rows"], 1)
            self.assertEqual(summary["merged_decision_status_counts"], {"chosen": 2})
            self.assertEqual(rows[0]["span_key"], "dog")
            self.assertEqual(rows[0]["canonical_surface"], "dog")
            self.assertEqual(rows[1]["span_key"], "light")
            self.assertEqual(rows[1]["decision_status"], "chosen")
            self.assertEqual(rows[1]["selected_oewn_synset"], "oewn-light-n")
            self.assertEqual(rows[1]["canonical_surface"], "")
            self.assertEqual(rows[1]["manual_confidence"], "medium")

    def test_head_correction_relooks_up_selected_query(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            output = root / "merged.tsv"
            _write_tsv(
                full,
                [
                    {
                        "span_key": "black shirt",
                        "observed_surface": "black shirt",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_joined_variant_required",
                        "selected_query": "blackshirt",
                        "selected_oewn_synset": "bad-blackshirt",
                    },
                ],
                extra_fieldnames=["selected_query", "selected_lookup_case", "objectness_gate"],
            )
            _write_tsv(
                resolved,
                [
                    {
                        "span_key": "black shirt",
                        "observed_surface": "black shirt",
                        "decision_status": "accepted",
                        "decision_reason": "manual_accept_canonical_head_modifier_removed",
                        "selected_lookup_case": "manual_modifier_removed_head",
                        "selected_query": "shirt",
                        "selected_oewn_synset": "",
                        "canonical_surface": "shirt",
                        "manual_resolution_type": "canonical_head_no_selected_synset",
                    },
                ],
                extra_fieldnames=[
                    "selected_query",
                    "selected_lookup_case",
                    "objectness_gate",
                    "manual_resolution_type",
                ],
            )

            summary = script.apply_object_manual_resolution(
                full_inventory_path=full,
                resolved_subset_path=resolved,
                output_path=output,
                head_lookup=lambda query: {
                    "selected_lookup_case": "exact",
                    "selected_query": query,
                    "has_oewn_noun_synset": "true",
                    "oewn_synset_count": "1",
                    "selected_oewn_synset": "oewn-shirt-n",
                    "selected_oewn_lexfile": "noun.artifact",
                    "objectness_gate": "object_compatible",
                    "synset_lemmas": "shirt",
                    "decision_status": "chosen",
                    "decision_reason": "manual_head_query_selected_oewn_synset",
                },
            )

            rows = _read_tsv(output)
            self.assertEqual(summary["head_relookup_rows"], 1)
            self.assertEqual(summary["head_relookup_needs_manual_rows"], 0)
            self.assertEqual(rows[0]["decision_status"], "chosen")
            self.assertEqual(rows[0]["selected_lookup_case"], "exact")
            self.assertEqual(rows[0]["selected_query"], "shirt")
            self.assertEqual(rows[0]["selected_oewn_synset"], "oewn-shirt-n")
            self.assertEqual(rows[0]["canonical_surface"], "")

    def test_excluded_manual_row_does_not_require_selected_synset(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            output = root / "merged.tsv"
            _write_tsv(
                full,
                [
                    {
                        "span_key": "day",
                        "observed_surface": "day",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_objectness_required",
                        "selected_oewn_synset": "oewn-day-n",
                        "canonical_surface": "",
                    },
                ],
                extra_fieldnames=["synset_selection_tag", "selected_query"],
            )
            _write_tsv(
                resolved,
                [
                    {
                        "span_key": "day",
                        "observed_surface": "day",
                        "decision_status": "excluded",
                        "decision_reason": "manual_rejected_time_unit_or_temporal_label_not_visual_object",
                        "selected_query": "day",
                        "selected_oewn_synset": "",
                        "canonical_surface": "",
                    },
                ],
                extra_fieldnames=["synset_selection_tag", "selected_query"],
            )

            summary = script.apply_object_manual_resolution(
                full_inventory_path=full,
                resolved_subset_path=resolved,
                output_path=output,
            )

            rows = _read_tsv(output)
            self.assertEqual(summary["merged_decision_status_counts"], {"excluded": 1})
            self.assertEqual(rows[0]["decision_status"], "excluded")
            self.assertEqual(rows[0]["selected_oewn_synset"], "")
            self.assertEqual(rows[0]["canonical_surface"], "")
            self.assertEqual(rows[0]["synset_selection_tag"], "manual_rejected")

    def test_head_correction_can_remain_needs_manual_after_relookup(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            output = root / "merged.tsv"
            _write_tsv(
                full,
                [{"span_key": "round table", "decision_status": "needs_manual"}],
                extra_fieldnames=["selected_query", "decision_reason"],
            )
            _write_tsv(
                resolved,
                [
                    {
                        "span_key": "round table",
                        "decision_status": "accepted",
                        "decision_reason": "manual_accept_canonical_head_modifier_removed",
                        "selected_query": "table",
                        "selected_oewn_synset": "",
                        "manual_resolution_type": "canonical_head_no_selected_synset",
                    },
                ],
                extra_fieldnames=["selected_query", "manual_resolution_type"],
            )

            summary = script.apply_object_manual_resolution(
                full_inventory_path=full,
                resolved_subset_path=resolved,
                output_path=output,
                head_lookup=lambda query: {
                    "selected_lookup_case": "exact",
                    "selected_query": query,
                    "has_oewn_noun_synset": "true",
                    "oewn_synset_count": "6",
                    "selected_oewn_synset": "oewn-table-group-n",
                    "selected_oewn_lexfile": "noun.group",
                    "objectness_gate": "conditional",
                    "decision_status": "needs_manual",
                    "decision_reason": "manual_head_query_synset_required",
                },
            )

            rows = _read_tsv(output)
            self.assertEqual(summary["head_relookup_needs_manual_rows"], 1)
            self.assertEqual(rows[0]["decision_status"], "needs_manual")
            self.assertEqual(rows[0]["selected_query"], "table")

    def test_surface_rewrite_uses_replacement_span_synset(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            output = root / "merged.tsv"
            _write_tsv(
                full,
                [
                    {
                        "span_key": "black top",
                        "observed_surface": "black top",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_joined_variant_required",
                        "selected_lookup_case": "joined_variant",
                        "selected_query": "blacktop",
                        "selected_oewn_synset": "",
                        "canonical_surface": "",
                        "decision_basis": "gpic_observed_caption_span_inventory",
                    },
                    {
                        "span_key": "top",
                        "observed_surface": "top",
                        "decision_status": "chosen",
                        "decision_reason": "manual_synset_artifact_or_garment",
                        "selected_lookup_case": "exact",
                        "selected_query": "top",
                        "selected_oewn_synset": "oewn-top-n",
                        "selected_oewn_lexfile": "noun.artifact",
                        "objectness_gate": "object_compatible",
                        "synset_lemmas": "top",
                        "canonical_surface": "top",
                        "decision_basis": "gpic_observed_caption_span_inventory",
                    },
                ],
                extra_fieldnames=[
                    "selected_lookup_case",
                    "selected_query",
                    "selected_oewn_lexfile",
                    "objectness_gate",
                    "synset_lemmas",
                    "decision_basis",
                ],
            )
            _write_tsv(
                resolved,
                [
                    {
                        "span_key": "black top",
                        "observed_surface": "black top",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_surface_rewrite_only",
                        "selected_oewn_synset": "",
                        "canonical_surface": "",
                        "manual_action": "surface_rewrite_only",
                        "replacement_span_key": "top",
                        "replacement_observed_surface": "top",
                        "replacement_selected_query": "",
                    },
                ],
                extra_fieldnames=[
                    "manual_action",
                    "replacement_span_key",
                    "replacement_observed_surface",
                    "replacement_selected_query",
                ],
            )

            summary = script.apply_object_manual_resolution(
                full_inventory_path=full,
                resolved_subset_path=resolved,
                output_path=output,
            )

            rows = _read_tsv(output)
            self.assertEqual(summary["surface_rewrite_rows"], 1)
            self.assertEqual(summary["surface_rewrite_needs_manual_rows"], 0)
            self.assertEqual(rows[0]["span_key"], "black top")
            self.assertEqual(rows[0]["decision_status"], "chosen")
            self.assertEqual(rows[0]["decision_reason"], "manual_surface_rewrite_to_replacement_span")
            self.assertEqual(rows[0]["selected_lookup_case"], "manual_surface_rewrite_to_replacement_span")
            self.assertEqual(rows[0]["selected_query"], "top")
            self.assertEqual(rows[0]["selected_oewn_synset"], "oewn-top-n")
            self.assertEqual(rows[0]["synset_lemmas"], "top")
            self.assertEqual(rows[0]["canonical_surface"], "")
            self.assertIn("manual_surface_rewrite_to_replacement_span", rows[0]["decision_basis"])

    def test_surface_rewrite_relooks_up_missing_replacement_span(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            output = root / "merged.tsv"
            _write_tsv(
                full,
                [
                    {
                        "span_key": "corn cobs",
                        "observed_surface": "corn cobs",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_surface_query_conflict_required",
                        "selected_lookup_case": "plural_surface_query_conflict",
                        "selected_query": "corn cobs|corn cob",
                        "selected_oewn_synset": "",
                        "decision_basis": "gpic_observed_caption_span_inventory",
                    },
                ],
                extra_fieldnames=[
                    "selected_lookup_case",
                    "selected_query",
                    "decision_basis",
                ],
            )
            _write_tsv(
                resolved,
                [
                    {
                        "span_key": "corn cobs",
                        "observed_surface": "corn cobs",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_surface_rewrite_only",
                        "manual_action": "surface_rewrite_only",
                        "replacement_span_key": "cobs",
                    },
                ],
                extra_fieldnames=["manual_action", "replacement_span_key"],
            )

            summary = script.apply_object_manual_resolution(
                full_inventory_path=full,
                resolved_subset_path=resolved,
                output_path=output,
                head_lookup=lambda query: {
                    "selected_lookup_case": "exact",
                    "selected_query": query,
                    "has_oewn_noun_synset": "true",
                    "oewn_synset_count": "1",
                    "selected_oewn_synset": "oewn-cobs-n",
                    "selected_oewn_lexfile": "noun.artifact",
                    "objectness_gate": "object_compatible",
                    "synset_lemmas": "cob",
                    "decision_status": "chosen",
                    "decision_reason": "selected_object_compatible",
                },
            )

            rows = _read_tsv(output)
            self.assertEqual(summary["surface_rewrite_rows"], 1)
            self.assertEqual(summary["surface_rewrite_needs_manual_rows"], 0)
            self.assertEqual(rows[0]["decision_status"], "chosen")
            self.assertEqual(rows[0]["decision_reason"], "manual_surface_rewrite_to_replacement_span")
            self.assertEqual(rows[0]["selected_query"], "cobs")
            self.assertEqual(rows[0]["selected_oewn_synset"], "oewn-cobs-n")

    def test_surface_rewrite_uses_replacement_decision_from_same_feedback(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            output = root / "merged.tsv"
            _write_tsv(
                full,
                [
                    {
                        "span_key": "white lines",
                        "observed_surface": "white lines",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_surface_query_conflict_required",
                    },
                    {
                        "span_key": "lines",
                        "observed_surface": "lines",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_surface_query_conflict_required",
                    },
                ],
                extra_fieldnames=["selected_query", "selected_oewn_synset"],
            )
            _write_tsv(
                resolved,
                [
                    {
                        "span_key": "lines",
                        "observed_surface": "lines",
                        "decision_status": "chosen",
                        "decision_reason": "manual_plural_recheck_synset_selected",
                        "selected_query": "line",
                        "selected_oewn_synset": "oewn-line-n",
                    },
                    {
                        "span_key": "white lines",
                        "observed_surface": "white lines",
                        "manual_action": "surface_rewrite_only",
                        "replacement_span_key": "lines",
                    },
                ],
                extra_fieldnames=[
                    "selected_query",
                    "selected_oewn_synset",
                    "manual_action",
                    "replacement_span_key",
                ],
            )

            summary = script.apply_object_manual_resolution(
                full_inventory_path=full,
                resolved_subset_path=resolved,
                output_path=output,
            )

            rows = _read_tsv(output)
            by_key = {row["span_key"]: row for row in rows}
            self.assertEqual(summary["surface_rewrite_needs_manual_rows"], 0)
            self.assertEqual(by_key["white lines"]["decision_status"], "chosen")
            self.assertEqual(by_key["white lines"]["selected_query"], "line")
            self.assertEqual(by_key["white lines"]["selected_oewn_synset"], "oewn-line-n")

    def test_missing_needs_manual_resolution_blocks(self) -> None:
        with tempfile.TemporaryDirectory(dir=_safe_temp_base()) as tmp:
            root = Path(tmp)
            full = root / "full.tsv"
            resolved = root / "resolved.tsv"
            _write_tsv(
                full,
                [
                    {"span_key": "light", "decision_status": "needs_manual"},
                    {"span_key": "church", "decision_status": "needs_manual"},
                ],
            )
            _write_tsv(resolved, [{"span_key": "light", "decision_status": "accepted"}])

            with self.assertRaises(ValueError) as caught:
                script.apply_object_manual_resolution(
                    full_inventory_path=full,
                    resolved_subset_path=resolved,
                    output_path=root / "merged.tsv",
                )

            self.assertIn("manual_resolution_key_mismatch", str(caught.exception))
            self.assertIn("church", str(caught.exception))


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
    path = Path(__file__).absolute().parents[1] / ".tmp_tests" / "gpic_apply_object_manual_resolution"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


if __name__ == "__main__":
    unittest.main()
