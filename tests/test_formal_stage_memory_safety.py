from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from gpic_concepts_v1.runtime_memory import MemorySafetyConfig
from gpic_concepts_v1.stage4_extract_raw import run_stage4_extract_raw
from gpic_concepts_v1.stage5_canonicalize import run_stage5_canonicalize
from gpic_concepts_v1.stage6_export_counts import run_stage6_export_counts


ROOT = Path(__file__).resolve().parents[1]


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

    def test_mixed_pipeline_writes_stage_specific_progress_files(self) -> None:
        text = (ROOT / "scripts" / "run_mixed_caption_pipeline.py").read_text(
            encoding="utf-8",
        )
        for stage_dir in ("stage4_dir", "stage5_dir", "stage6_dir"):
            with self.subTest(stage_dir=stage_dir):
                self.assertIn(f'progress_path={stage_dir} / "progress.json"', text)

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


if __name__ == "__main__":
    unittest.main()
