from __future__ import annotations

import argparse
import inspect
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from gpic_concepts_v1.cli_memory import memory_safety_kwargs
from gpic_concepts_v1.runtime_memory import MemorySafetyConfig, ProgressWriter
from gpic_concepts_v1.stage4_extract_raw import run_stage4_extract_raw
from gpic_concepts_v1.stage5_canonicalize import run_stage5_canonicalize
from gpic_concepts_v1.stage6_export_counts import run_stage6_export_counts


ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(script_name: str):
    path = ROOT / "scripts" / script_name
    module_name = "test_loaded_" + script_name.replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load script module: {script_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FormalStageMemorySafetyContractTest(unittest.TestCase):
    def test_formal_stage_functions_share_memory_guard_parameters(self) -> None:
        required = {
            "max_rss_gib",
            "memory_limit_gib",
            "rss_limit_fraction",
            "rss_reserve_gib",
            "progress_path",
        }
        for function in (
            run_stage4_extract_raw,
            run_stage5_canonicalize,
            run_stage6_export_counts,
        ):
            with self.subTest(function=function.__name__):
                self.assertTrue(required.issubset(inspect.signature(function).parameters))

    def test_formal_stage_runners_use_shared_memory_cli_helper(self) -> None:
        for script_name in (
            "run_stage4_extract_raw.py",
            "run_stage5_canonicalize.py",
            "run_stage6_export_counts.py",
        ):
            with self.subTest(script=script_name):
                text = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
                self.assertIn("add_memory_safety_args(parser", text)
                self.assertIn("memory_safety_kwargs(args)", text)
                self.assertNotIn("progress_path=", text)

    def test_formal_stage_runners_expose_progress_cli_argument(self) -> None:
        cases = (
            (
                "run_stage4_extract_raw.py",
                [
                    "run_stage4_extract_raw.py",
                    "--input",
                    "stage3.jsonl",
                    "--raw-mentions",
                    "raw_mentions.jsonl",
                    "--raw-edges",
                    "raw_edges.jsonl",
                    "--progress",
                    "progress.json",
                ],
            ),
            (
                "run_stage5_canonicalize.py",
                [
                    "run_stage5_canonicalize.py",
                    "--raw-mentions",
                    "raw_mentions.jsonl",
                    "--raw-edges",
                    "raw_edges.jsonl",
                    "--canonical-mentions",
                    "canonical_mentions.jsonl",
                    "--canonical-edges",
                    "canonical_edges.jsonl",
                    "--progress",
                    "progress.json",
                ],
            ),
            (
                "run_stage6_export_counts.py",
                [
                    "run_stage6_export_counts.py",
                    "--canonical-mentions",
                    "canonical_mentions.jsonl",
                    "--canonical-edges",
                    "canonical_edges.jsonl",
                    "--output-dir",
                    "stage6",
                    "--progress",
                    "progress.json",
                ],
            ),
        )
        for script_name, argv in cases:
            with self.subTest(script=script_name):
                module = _load_script_module(script_name)
                with patch.object(sys, "argv", argv):
                    args = module.parse_args()
                self.assertEqual(args.progress, "progress.json")

    def test_memory_safety_kwargs_owns_progress_path_conversion(self) -> None:
        args = argparse.Namespace(
            max_rss_gib=None,
            memory_limit_gib=None,
            rss_limit_fraction=0.75,
            rss_reserve_gib=16.0,
            progress="progress.json",
        )
        kwargs = memory_safety_kwargs(args)
        self.assertEqual(kwargs["progress_path"], Path("progress.json"))

    def test_mixed_pipeline_writes_stage_specific_progress_files(self) -> None:
        text = (ROOT / "scripts" / "run_mixed_caption_pipeline.py").read_text(
            encoding="utf-8",
        )
        for stage_dir in ("stage4_dir", "stage5_dir", "stage6_dir"):
            with self.subTest(stage_dir=stage_dir):
                self.assertIn(f'progress_path={stage_dir} / "progress.json"', text)
        self.assertIn("count_backend=stage6_count_backend", text)
        self.assertIn("sqlite_cache_rows=stage6_sqlite_cache_rows", text)
        self.assertIn("facts_output_mode=stage6_facts_output_mode", text)

    def test_memory_limit_uses_lower_fraction_or_reserve_limit(self) -> None:
        by_fraction = MemorySafetyConfig(
            memory_limit_gib=240,
            rss_limit_fraction=0.75,
            rss_reserve_gib=16,
        )
        self.assertEqual(by_fraction.effective_max_rss_gib, 180)

        by_reserve = MemorySafetyConfig(
            memory_limit_gib=240,
            rss_limit_fraction=0.95,
            rss_reserve_gib=40,
        )
        self.assertEqual(by_reserve.effective_max_rss_gib, 200)

    def test_progress_writer_records_memory_fields(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            progress_path = Path(root) / "progress.json"
            writer = ProgressWriter(
                progress_path,
                stage_name="stage-test",
                memory_config=MemorySafetyConfig(memory_limit_gib=32),
            )
            writer.write(status="running", phase="probe", note="ok")
            progress = json.loads(progress_path.read_text(encoding="utf-8"))

        self.assertEqual(progress["status"], "running")
        self.assertEqual(progress["stage"], "stage-test")
        self.assertEqual(progress["memory_limit_gib"], 32)
        self.assertEqual(progress["memory_limit_source"], "explicit")
        self.assertIn("current_rss_kib", progress)
        self.assertEqual(progress["memory_check_min_interval_seconds"], 1.0)

    def test_progress_memory_check_is_throttled_between_progress_writes(self) -> None:
        writer = ProgressWriter(
            None,
            stage_name="stage-test",
            memory_config=MemorySafetyConfig(
                memory_limit_gib=32,
                memory_check_min_interval_seconds=60.0,
            ),
        )
        with patch("gpic_concepts_v1.runtime_memory.current_rss_kib", return_value=1024) as rss:
            writer.check_memory(phase="probe")
            writer.check_memory(phase="probe")
            writer.check_memory(phase="probe", force=True)

        self.assertEqual(rss.call_count, 2)


if __name__ == "__main__":
    unittest.main()
