from pathlib import Path
import importlib.util
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
        finally:
            _remove_tree(tmp_path)

        self.assertEqual(summary["overlaid_rows"], 1)
        self.assertEqual(rows[0]["decision_status"], "chosen")
        self.assertEqual(rows[0]["decision_reason"], "manual_action_synset_selected")
        self.assertEqual(rows[0]["selected_query"], "shine")
        self.assertEqual(rows[0]["selected_oewn_synset"], "fake-shine-v")
        self.assertEqual(rows[0]["selected_oewn_lexfile"], "verb.weather")
        self.assertEqual(rows[0]["synset_selection_tag"], "manual_select")

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
