import unittest

from gpic_concepts_v1.runtime_resources import (
    HardwareResources,
    choose_auto_stage3_sentence_shards,
    choose_detected_cpu_cores,
    choose_mixed_pipeline_resource_plan,
    detect_visible_gpu_devices,
    estimate_stage3_sentence_workers_per_gpu,
)


class RuntimeResourcesTest(unittest.TestCase):
    def test_cpu_detection_uses_cgroup_quota_inside_affinity(self) -> None:
        cores, source = choose_detected_cpu_cores(
            cpu_quota_cores=28.0,
            affinity_cores=64,
            os_cpu_count=128,
        )

        self.assertEqual(cores, 28)
        self.assertEqual(source, "cgroup_cpu_quota+process_affinity")

    def test_gpu_detection_prefers_cuda_visible_devices(self) -> None:
        devices, source = detect_visible_gpu_devices(
            env={"CUDA_VISIBLE_DEVICES": "2, 5"},
            gpu_metadata=[{"index": "0"}, {"index": "1"}],
        )

        self.assertEqual(devices, ["2", "5"])
        self.assertEqual(source, "CUDA_VISIBLE_DEVICES")

    def test_gpu_detection_falls_back_to_nvidia_smi_metadata(self) -> None:
        devices, source = detect_visible_gpu_devices(
            env={},
            gpu_metadata=[{"index": "0"}, {"index": "1"}],
        )

        self.assertEqual(devices, ["0", "1"])
        self.assertEqual(source, "nvidia_smi")

    def test_stage3_workers_per_gpu_are_memory_limited_and_capped(self) -> None:
        self.assertEqual(estimate_stage3_sentence_workers_per_gpu(None), 1)
        self.assertEqual(estimate_stage3_sentence_workers_per_gpu(24 * 1024), 1)
        self.assertEqual(estimate_stage3_sentence_workers_per_gpu(48 * 1024), 3)
        self.assertEqual(estimate_stage3_sentence_workers_per_gpu(141 * 1024), 8)

    def test_stage3_sentence_shards_use_gpu_memory_and_cpu_limit(self) -> None:
        shards, decision = choose_auto_stage3_sentence_shards(
            gpu_devices=["0", "1"],
            gpu_metadata=(
                {"index": "0", "memory_total_mib": str(141 * 1024)},
                {"index": "1", "memory_total_mib": str(141 * 1024)},
            ),
            cpu_jobs=28,
            stage3_tag_shards=1,
        )

        self.assertEqual(shards, 16)
        self.assertIn("stage3_sentence_shards=gpu_memory_workers", decision)

    def test_mixed_pipeline_auto_plan_uses_gpu_memory_and_cpu_fraction(self) -> None:
        plan = choose_mixed_pipeline_resource_plan(
            hardware=_hardware(
                cpu_cores=28,
                gpu_devices=("0", "1"),
                gpu_memory_mib=141 * 1024,
            ),
            gpu_mode="require",
            stage3_sentence_shards=1,
            stage3_tag_shards=1,
            stage3_jobs=None,
            stage3_gpu_devices=[],
            stage456_shards=1,
            stage456_jobs=None,
            stage456_merge_jobs=1,
            stage6_facts_output_mode="discard",
            explicit_overrides=set(),
            cpu_fraction=0.5,
        )

        chosen = plan.chosen
        self.assertEqual(chosen["stage3_sentence_shards"], 13)
        self.assertEqual(chosen["stage3_gpu_devices"], ["0", "1"])
        self.assertEqual(chosen["stage3_jobs"], 14)
        self.assertEqual(chosen["stage456_shards"], 14)
        self.assertEqual(chosen["stage456_jobs"], 14)
        self.assertEqual(chosen["stage456_merge_jobs"], 14)
        self.assertIn("stage3_jobs=cpu_limited_stage3_shards", plan.decisions)

    def test_mixed_pipeline_auto_plan_matches_two_h200_benchmark_shape(self) -> None:
        plan = choose_mixed_pipeline_resource_plan(
            hardware=_hardware(
                cpu_cores=28,
                gpu_devices=("0", "1"),
                gpu_memory_mib=141 * 1024,
            ),
            gpu_mode="require",
            stage3_sentence_shards=1,
            stage3_tag_shards=1,
            stage3_jobs=None,
            stage3_gpu_devices=[],
            stage456_shards=1,
            stage456_jobs=None,
            stage456_merge_jobs=1,
            stage6_facts_output_mode="discard",
            explicit_overrides=set(),
            cpu_fraction=1.0,
        )

        chosen = plan.chosen
        self.assertEqual(chosen["stage3_sentence_shards"], 16)
        self.assertEqual(chosen["stage3_tag_shards"], 1)
        self.assertEqual(chosen["stage3_jobs"], 17)
        self.assertIn(
            "stage3_sentence_shards=gpu_memory_workers(per_gpu=[8, 8],cpu_limited=False)",
            plan.decisions,
        )

    def test_mixed_pipeline_auto_plan_limits_stage3_jobs_by_cpu(self) -> None:
        plan = choose_mixed_pipeline_resource_plan(
            hardware=_hardware(
                cpu_cores=2,
                gpu_devices=("0", "1", "2", "3"),
                gpu_memory_mib=141 * 1024,
            ),
            gpu_mode="require",
            stage3_sentence_shards=1,
            stage3_tag_shards=1,
            stage3_jobs=None,
            stage3_gpu_devices=[],
            stage456_shards=1,
            stage456_jobs=None,
            stage456_merge_jobs=1,
            stage6_facts_output_mode="discard",
            explicit_overrides=set(),
            cpu_fraction=1.0,
        )

        chosen = plan.chosen
        self.assertEqual(chosen["stage3_sentence_shards"], 1)
        self.assertIsNone(chosen["stage3_jobs"])

    def test_mixed_pipeline_auto_plan_respects_explicit_values(self) -> None:
        plan = choose_mixed_pipeline_resource_plan(
            hardware=_hardware(cpu_cores=28, gpu_devices=("0", "1")),
            gpu_mode="require",
            stage3_sentence_shards=4,
            stage3_tag_shards=1,
            stage3_jobs=3,
            stage3_gpu_devices=["7"],
            stage456_shards=8,
            stage456_jobs=6,
            stage456_merge_jobs=5,
            stage6_facts_output_mode="discard",
            explicit_overrides={
                "stage3_sentence_shards",
                "stage3_jobs",
                "stage3_gpu_devices",
                "stage456_shards",
                "stage456_jobs",
                "stage456_merge_jobs",
            },
            cpu_fraction=1.0,
        )

        chosen = plan.chosen
        self.assertEqual(chosen["stage3_sentence_shards"], 4)
        self.assertEqual(chosen["stage3_gpu_devices"], ["7"])
        self.assertEqual(chosen["stage3_jobs"], 3)
        self.assertEqual(chosen["stage456_shards"], 8)
        self.assertEqual(chosen["stage456_jobs"], 6)
        self.assertEqual(chosen["stage456_merge_jobs"], 5)

    def test_mixed_pipeline_auto_plan_defaults_jobs_to_explicit_stage456_shards(self) -> None:
        plan = choose_mixed_pipeline_resource_plan(
            hardware=_hardware(cpu_cores=28, gpu_devices=("0", "1")),
            gpu_mode="require",
            stage3_sentence_shards=1,
            stage3_tag_shards=1,
            stage3_jobs=None,
            stage3_gpu_devices=[],
            stage456_shards=8,
            stage456_jobs=None,
            stage456_merge_jobs=1,
            stage6_facts_output_mode="discard",
            explicit_overrides={"stage456_shards"},
            cpu_fraction=1.0,
        )

        self.assertEqual(plan.chosen["stage456_shards"], 8)
        self.assertEqual(plan.chosen["stage456_jobs"], 8)
        self.assertEqual(plan.chosen["stage456_merge_jobs"], 28)

    def test_mixed_pipeline_auto_plan_keeps_stage456_monolithic_when_facts_are_written(self) -> None:
        plan = choose_mixed_pipeline_resource_plan(
            hardware=_hardware(cpu_cores=28, gpu_devices=("0", "1")),
            gpu_mode="require",
            stage3_sentence_shards=1,
            stage3_tag_shards=1,
            stage3_jobs=None,
            stage3_gpu_devices=[],
            stage456_shards=1,
            stage456_jobs=None,
            stage456_merge_jobs=1,
            stage6_facts_output_mode="write",
            explicit_overrides=set(),
            cpu_fraction=1.0,
        )

        self.assertEqual(plan.chosen["stage456_shards"], 1)
        self.assertIsNone(plan.chosen["stage456_jobs"])
        self.assertIsNone(plan.chosen["stage456_merge_jobs"])
        self.assertIn("stage456_auto_sharding_skipped_because_facts_are_written", plan.decisions)


def _hardware(
    *,
    cpu_cores: int,
    gpu_devices: tuple[str, ...],
    gpu_memory_mib: int | None = None,
) -> HardwareResources:
    return HardwareResources(
        cpu_cores=cpu_cores,
        cpu_source="test",
        cpu_quota_cores=float(cpu_cores),
        affinity_cores=cpu_cores,
        os_cpu_count=cpu_cores,
        memory_limit_gib=480.0,
        memory_limit_source="test",
        gpu_devices=gpu_devices,
        gpu_source="test",
        gpu_metadata=tuple(
            {
                "index": device,
                **(
                    {"memory_total_mib": str(gpu_memory_mib)}
                    if gpu_memory_mib is not None
                    else {}
                ),
            }
            for device in gpu_devices
        ),
    )


if __name__ == "__main__":
    unittest.main()
