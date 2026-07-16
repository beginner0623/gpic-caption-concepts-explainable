from pathlib import Path
import importlib.util
import json
import os
import tempfile
import unittest
import uuid


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "apply_action_manual_resolution.py"
    spec = importlib.util.spec_from_file_location("apply_action_manual_resolution", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplyActionManualResolutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = _load_script()

    def test_manual_decisions_replace_needs_manual_rows(self) -> None:
        tmp_path = _temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            full = tmp_path / "full.tsv"
            manual = tmp_path / "manual.tsv"
            output = tmp_path / "resolved.tsv"
            _write_tsv(
                full,
                [
                    {
                        "span_key": "shining",
                        "observed_surface": "shining",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_action_morphy_required",
                        "selected_lookup_case": "verb_head_morphy_ambiguous",
                        "selected_query": "shin|shine",
                        "all_oewn_synsets": "fake-shin-v|fake-shine-v",
                        "all_oewn_lexfiles": "verb.motion|verb.weather",
                        "selected_oewn_synset": "",
                        "selected_oewn_lexfile": "",
                        "synset_selection_tag": "ambiguous_morphy_multiple_oewn_hit_queries",
                        "wn30_lemma_counts": "",
                        "decision_basis": "gpic_observed_action_inventory",
                    }
                ],
            )
            _write_tsv(
                manual,
                [
                    {
                        "span_key": "shining",
                        "selected_query": "shine",
                        "selected_oewn_synset": "fake-shine-v",
                        "manual_decision_note": "selected shine query",
                    }
                ],
            )

            summary = self.script.apply_action_manual_resolution(
                full_inventory_path=full,
                manual_decisions_path=manual,
                output_path=output,
            )
            rows = _read_tsv(output)
            state = json.loads(
                output.with_name(f"{output.name}.pipeline_state.json").read_text(
                    encoding="utf-8"
                )
            )
        finally:
            _remove_tree(tmp_path)

        self.assertEqual(summary["overlaid_rows"], 1)
        self.assertEqual(rows[0]["decision_status"], "chosen")
        self.assertEqual(rows[0]["decision_reason"], "manual_action_synset_selected")
        self.assertEqual(rows[0]["selected_query"], "shine")
        self.assertEqual(rows[0]["selected_oewn_synset"], "fake-shine-v")
        self.assertEqual(rows[0]["selected_oewn_lexfile"], "verb.weather")
        self.assertEqual(rows[0]["synset_selection_tag"], "manual_select")
        self.assertEqual(state["artifact_type"], "gpic_observed_action_inventory")
        self.assertEqual(state["status"], "resolved")
        self.assertEqual(state["needs_manual_rows"], 0)
        self.assertTrue(state["manual_resolution_applied"])
        self.assertTrue(state["preposition_mwe_detection_before_action"])

    def test_missing_needs_manual_resolution_blocks(self) -> None:
        tmp_path = _temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            full = tmp_path / "full.tsv"
            manual = tmp_path / "manual.tsv"
            output = tmp_path / "resolved.tsv"
            _write_tsv(
                full,
                [
                    {"span_key": "deepening", "decision_status": "needs_manual"},
                    {"span_key": "shining", "decision_status": "needs_manual"},
                ],
            )
            _write_tsv(
                manual,
                [
                    {
                        "span_key": "shining",
                        "selected_query": "shine",
                        "selected_oewn_synset": "fake-shine-v",
                    }
                ],
            )

            with self.assertRaises(ValueError) as caught:
                self.script.apply_action_manual_resolution(
                    full_inventory_path=full,
                    manual_decisions_path=manual,
                    output_path=output,
                )
        finally:
            _remove_tree(tmp_path)

        self.assertIn("manual_resolution_key_mismatch", str(caught.exception))

    def test_review_style_manual_decision_selects_singular_morphy_query(self) -> None:
        tmp_path = _temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            full = tmp_path / "full.tsv"
            manual = tmp_path / "manual.tsv"
            output = tmp_path / "resolved.tsv"
            _write_tsv(
                full,
                [
                    {
                        "span_key": "installed",
                        "observed_surface": "installed",
                        "decision_status": "needs_manual",
                        "decision_reason": "manual_action_morphy_required",
                        "selected_lookup_case": "verb_head_morphy_ambiguous",
                        "selected_query": "instal|install",
                        "all_oewn_synsets": "fake-install-v|fake-other-v",
                        "all_oewn_lexfiles": "verb.contact|verb.change",
                        "selected_oewn_synset": "",
                        "selected_oewn_lexfile": "",
                        "synset_selection_tag": "ambiguous_morphy_multiple_oewn_hit_queries",
                        "synset_lemmas": "instal|install",
                        "wn30_lemma_counts": (
                            "instal:x:fake-install-v:instal%2:35:00:::instal.v.01:6"
                            "||install:x:fake-install-v:install%2:35:00:::install.v.01:28"
                        ),
                        "decision_basis": "gpic_observed_action_inventory",
                    }
                ],
            )
            _write_tsv(
                manual,
                [
                    {
                        "span_key": "installed",
                        "resolved_selected_oewn_synset": "fake-install-v",
                        "manual_note": "choose install query",
                    }
                ],
            )

            self.script.apply_action_manual_resolution(
                full_inventory_path=full,
                manual_decisions_path=manual,
                output_path=output,
            )
            rows = _read_tsv(output)
        finally:
            _remove_tree(tmp_path)

        self.assertEqual(rows[0]["decision_status"], "chosen")
        self.assertEqual(rows[0]["selected_query"], "install")
        self.assertEqual(rows[0]["selected_oewn_synset"], "fake-install-v")
        self.assertEqual(rows[0]["selected_oewn_lexfile"], "verb.contact")
        self.assertIn("manual_note=choose install query", rows[0]["wn30_lemma_counts"])


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    lines = ["\t".join(fieldnames)]
    for row in rows:
        lines.append("\t".join(row.get(field, "") for field in fieldnames))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_tsv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _temp_base() -> Path:
    roots = [
        os.environ.get("GPIC_TEST_TEMP_ROOT"),
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
        tempfile.gettempdir(),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root) / "gpic_apply_action_manual_resolution"
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f"{uuid.uuid4().hex}.tmp"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except PermissionError:
            continue
    raise PermissionError("no writable temp directory for action manual resolution tests")


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            child.rmdir()
    path.rmdir()


if __name__ == "__main__":
    unittest.main()
