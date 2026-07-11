import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_fast_pipeline import (
    _iter_length_bucketed_rows,
    _parse_nvidia_smi_csv,
    _parse_optional_float,
)


class BenchmarkFastPipelineTest(unittest.TestCase):
    def test_parse_optional_float_handles_nvidia_na_values(self) -> None:
        self.assertIsNone(_parse_optional_float("N/A"))
        self.assertIsNone(_parse_optional_float("[N/A]"))
        self.assertEqual(_parse_optional_float("175.00"), 175.0)

    def test_parse_nvidia_smi_csv_records_power_limit(self) -> None:
        stdout = (
            "NVIDIA GeForce RTX 5080 Laptop GPU, 592.01, P8, "
            "4.00, 175.00, 0, 74, 16303, 46\n"
        )

        metadata = _parse_nvidia_smi_csv(stdout)

        self.assertEqual(metadata["gpu_name"], "NVIDIA GeForce RTX 5080 Laptop GPU")
        self.assertEqual(metadata["driver_version"], "592.01")
        self.assertEqual(metadata["pstate"], "P8")
        self.assertEqual(metadata["power_draw_w"], 4.0)
        self.assertEqual(metadata["power_limit_w"], 175.0)
        self.assertEqual(metadata["utilization_gpu_percent"], 0.0)
        self.assertEqual(metadata["memory_used_mib"], 74.0)
        self.assertEqual(metadata["memory_total_mib"], 16303.0)
        self.assertEqual(metadata["temperature_gpu_c"], 46.0)

    def test_length_bucketed_rows_sorts_only_within_bucket(self) -> None:
        rows = [
            {"caption": "dddd"},
            {"caption": "b"},
            {"caption": "ccc"},
            {"caption": "aa"},
        ]

        bucketed = list(_iter_length_bucketed_rows(rows, bucket_size=2))

        self.assertEqual([row["caption"] for row in bucketed], ["b", "dddd", "aa", "ccc"])

    def test_length_bucketed_rows_respects_limit(self) -> None:
        rows = [
            {"caption": "dddd"},
            {"caption": "b"},
            {"caption": "ccc"},
            {"caption": "aa"},
        ]

        bucketed = list(_iter_length_bucketed_rows(rows, bucket_size=2, limit=3))

        self.assertEqual([row["caption"] for row in bucketed], ["b", "dddd", "ccc"])


if __name__ == "__main__":
    unittest.main()
