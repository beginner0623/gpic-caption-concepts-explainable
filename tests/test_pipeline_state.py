from pathlib import Path
import os
import tempfile
import unittest
import uuid

from gpic_concepts_v1.pipeline_state import (
    PipelineStateError,
    artifact_state_path,
    build_action_inventory_state,
    require_action_inventory_sidecar_state,
    write_pipeline_state,
)


class PipelineStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_path = _temp_base() / uuid.uuid4().hex
        self.tmp_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        _remove_tree(self.tmp_path)

    def test_action_inventory_sidecar_state_requires_preposition_mwe_order_flags(self) -> None:
        inventory = self.tmp_path / "actions.tsv"
        inventory.write_text("", encoding="utf-8")
        state = build_action_inventory_state(
            input_path="stage3.jsonl",
            output_path=str(inventory),
            needs_manual_output="actions_needs_manual.tsv",
            summary={
                "decision_status_counts": {"chosen": 2},
                "relation_mwe_match_total": 3,
                "relation_mwe_consumed_token_total": 9,
            },
        )
        write_pipeline_state(artifact_state_path(inventory), state)

        loaded = require_action_inventory_sidecar_state(inventory)

        self.assertEqual(loaded["artifact_type"], "gpic_observed_action_inventory")
        self.assertTrue(loaded["action_inventory_preposition_mwe_aware"])
        self.assertEqual(loaded["relation_mwe_match_total"], 3)

    def test_action_inventory_sidecar_state_blocks_legacy_artifact(self) -> None:
        inventory = self.tmp_path / "actions.tsv"
        inventory.write_text("", encoding="utf-8")

        with self.assertRaisesRegex(PipelineStateError, "missing_pipeline_state"):
            require_action_inventory_sidecar_state(inventory)


def _temp_base() -> Path:
    roots = [
        os.environ.get("GPIC_TEST_TEMP_ROOT"),
        str(Path.cwd() / ".tmp_tests"),
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
        tempfile.gettempdir(),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root) / "pipeline_state"
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f"{uuid.uuid4().hex}.tmp"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except PermissionError:
            continue
    raise PermissionError("no writable temp directory for pipeline state tests")


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
