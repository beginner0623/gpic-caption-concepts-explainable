"""Hardware-aware resource planning for pipeline runners."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
import os
from pathlib import Path
import subprocess
from typing import Any

from gpic_concepts_v1.runtime_memory import detect_cgroup_memory_limit_gib


_STAGE3_SENTENCE_WORKER_MEMORY_GIB = 16.0
_STAGE3_MAX_SENTENCE_WORKERS_PER_GPU = 8


@dataclass(frozen=True, slots=True)
class HardwareResources:
    cpu_cores: int
    cpu_source: str
    cpu_quota_cores: float | None
    affinity_cores: int | None
    os_cpu_count: int | None
    memory_limit_gib: float | None
    memory_limit_source: str
    gpu_devices: tuple[str, ...]
    gpu_source: str
    gpu_metadata: tuple[dict[str, str], ...]

    def to_summary(self) -> dict[str, Any]:
        return {
            "cpu_cores": self.cpu_cores,
            "cpu_source": self.cpu_source,
            "cpu_quota_cores": self.cpu_quota_cores,
            "affinity_cores": self.affinity_cores,
            "os_cpu_count": self.os_cpu_count,
            "memory_limit_gib": self.memory_limit_gib,
            "memory_limit_source": self.memory_limit_source,
            "gpu_count": len(self.gpu_devices),
            "gpu_devices": list(self.gpu_devices),
            "gpu_source": self.gpu_source,
            "gpu_metadata": list(self.gpu_metadata),
        }


@dataclass(frozen=True, slots=True)
class MixedPipelineResourcePlan:
    hardware: HardwareResources
    explicit_overrides: tuple[str, ...]
    cpu_fraction: float
    max_stage456_jobs: int | None
    stage6_facts_output_mode: str
    chosen: dict[str, Any]
    decisions: tuple[str, ...]

    def to_summary(self) -> dict[str, Any]:
        return {
            "auto_resources_enabled": True,
            "hardware": self.hardware.to_summary(),
            "explicit_overrides": list(self.explicit_overrides),
            "cpu_fraction": self.cpu_fraction,
            "max_stage456_jobs": self.max_stage456_jobs,
            "stage6_facts_output_mode": self.stage6_facts_output_mode,
            "chosen": dict(self.chosen),
            "decisions": list(self.decisions),
        }


def detect_hardware_resources() -> HardwareResources:
    cpu_quota_cores = detect_cgroup_cpu_quota_cores()
    affinity_cores = detect_process_affinity_cores()
    os_cpu_count = os.cpu_count()
    cpu_cores, cpu_source = choose_detected_cpu_cores(
        cpu_quota_cores=cpu_quota_cores,
        affinity_cores=affinity_cores,
        os_cpu_count=os_cpu_count,
    )
    memory_limit_gib = detect_cgroup_memory_limit_gib()
    gpu_metadata = collect_nvidia_smi_metadata()
    gpu_devices, gpu_source = detect_visible_gpu_devices(
        env=os.environ,
        gpu_metadata=gpu_metadata,
    )
    return HardwareResources(
        cpu_cores=cpu_cores,
        cpu_source=cpu_source,
        cpu_quota_cores=cpu_quota_cores,
        affinity_cores=affinity_cores,
        os_cpu_count=os_cpu_count,
        memory_limit_gib=memory_limit_gib,
        memory_limit_source="cgroup" if memory_limit_gib is not None else "unbounded_or_unavailable",
        gpu_devices=tuple(gpu_devices),
        gpu_source=gpu_source,
        gpu_metadata=tuple(gpu_metadata),
    )


def choose_detected_cpu_cores(
    *,
    cpu_quota_cores: float | None,
    affinity_cores: int | None,
    os_cpu_count: int | None,
) -> tuple[int, str]:
    quota_floor = max(1, math.floor(cpu_quota_cores)) if cpu_quota_cores is not None else None
    candidates: list[int] = []
    source_parts: list[str] = []
    if quota_floor is not None:
        candidates.append(quota_floor)
        source_parts.append("cgroup_cpu_quota")
    if affinity_cores is not None:
        candidates.append(affinity_cores)
        source_parts.append("process_affinity")
    if candidates:
        return max(1, min(candidates)), "+".join(source_parts)
    if os_cpu_count is not None and os_cpu_count > 0:
        return os_cpu_count, "os_cpu_count"
    return 1, "fallback_one_core"


def detect_cgroup_cpu_quota_cores() -> float | None:
    cpu_max = Path("/sys/fs/cgroup/cpu.max")
    if cpu_max.exists():
        parsed = _parse_cpu_max(cpu_max.read_text(encoding="utf-8", errors="replace"))
        if parsed is not None:
            return parsed
    quota_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if quota_path.exists() and period_path.exists():
        try:
            quota = int(quota_path.read_text(encoding="utf-8", errors="replace").strip())
            period = int(period_path.read_text(encoding="utf-8", errors="replace").strip())
        except ValueError:
            return None
        if quota > 0 and period > 0:
            return quota / period
    return None


def _parse_cpu_max(raw_value: str) -> float | None:
    parts = raw_value.strip().split()
    if len(parts) < 2 or parts[0] == "max":
        return None
    try:
        quota = int(parts[0])
        period = int(parts[1])
    except ValueError:
        return None
    if quota <= 0 or period <= 0:
        return None
    return quota / period


def detect_process_affinity_cores() -> int | None:
    sched_getaffinity = getattr(os, "sched_getaffinity", None)
    if sched_getaffinity is None:
        return None
    try:
        return len(sched_getaffinity(0))
    except OSError:
        return None


def detect_visible_gpu_devices(
    *,
    env: Mapping[str, str],
    gpu_metadata: list[dict[str, str]],
) -> tuple[list[str], str]:
    visible = env.get("CUDA_VISIBLE_DEVICES")
    if visible is not None:
        stripped = visible.strip()
        if stripped in {"", "-1", "NoDevFiles"}:
            return [], "CUDA_VISIBLE_DEVICES_empty"
        return [part.strip() for part in stripped.split(",") if part.strip()], "CUDA_VISIBLE_DEVICES"
    devices = [row.get("index", "").strip() for row in gpu_metadata if row.get("index", "").strip()]
    if devices:
        return devices, "nvidia_smi"
    return [], "none_detected"


def estimate_stage3_sentence_workers_per_gpu(memory_total_mib: int | None) -> int:
    if memory_total_mib is None or memory_total_mib <= 0:
        return 1
    worker_memory_mib = int(_STAGE3_SENTENCE_WORKER_MEMORY_GIB * 1024)
    workers = memory_total_mib // worker_memory_mib
    return max(1, min(_STAGE3_MAX_SENTENCE_WORKERS_PER_GPU, workers))


def choose_auto_stage3_sentence_shards(
    *,
    gpu_devices: list[str],
    gpu_metadata: tuple[dict[str, str], ...],
    cpu_jobs: int,
    stage3_tag_shards: int,
) -> tuple[int, str]:
    if not gpu_devices:
        return 1, "stage3_sentence_shards=existing_default"

    available_sentence_jobs = max(1, cpu_jobs - max(0, stage3_tag_shards))
    metadata_by_index = {
        row.get("index", "").strip(): row
        for row in gpu_metadata
        if row.get("index", "").strip()
    }
    per_gpu_workers: list[int] = []
    for ordinal, device in enumerate(gpu_devices):
        row = metadata_by_index.get(str(device).strip())
        if row is None and len(gpu_metadata) == len(gpu_devices):
            row = gpu_metadata[ordinal]
        per_gpu_workers.append(
            estimate_stage3_sentence_workers_per_gpu(
                _parse_int_field(row.get("memory_total_mib")) if row else None
            )
        )
    raw_sentence_shards = max(1, sum(per_gpu_workers))
    sentence_shards = min(raw_sentence_shards, available_sentence_jobs)
    decision = (
        "stage3_sentence_shards=gpu_memory_workers"
        f"(per_gpu={per_gpu_workers},cpu_limited={sentence_shards != raw_sentence_shards})"
    )
    return sentence_shards, decision


def _parse_int_field(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def collect_nvidia_smi_metadata(timeout_seconds: float = 5.0) -> list[dict[str, str]]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,driver_version,pstate,power.draw,power.limit,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    fields = [
        "index",
        "name",
        "driver_version",
        "pstate",
        "power_draw_w",
        "power_limit_w",
        "memory_used_mib",
        "memory_total_mib",
    ]
    rows: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != len(fields):
            continue
        rows.append(dict(zip(fields, parts, strict=True)))
    return rows


def choose_mixed_pipeline_resource_plan(
    *,
    hardware: HardwareResources,
    gpu_mode: str,
    stage3_sentence_shards: int,
    stage3_tag_shards: int,
    stage3_jobs: int | None,
    stage3_gpu_devices: list[str],
    stage456_shards: int,
    stage456_jobs: int | None,
    stage456_merge_jobs: int | None,
    stage6_facts_output_mode: str,
    explicit_overrides: set[str],
    cpu_fraction: float = 1.0,
    max_stage456_jobs: int | None = None,
) -> MixedPipelineResourcePlan:
    if gpu_mode not in {"none", "prefer", "require"}:
        raise ValueError("gpu_mode must be one of: none, prefer, require")
    if not 0 < cpu_fraction <= 1:
        raise ValueError("--auto-resource-cpu-fraction must be > 0 and <= 1")
    if max_stage456_jobs is not None and max_stage456_jobs < 1:
        raise ValueError("--auto-resource-max-stage456-jobs must be greater than zero")

    cpu_jobs = max(1, math.floor(hardware.cpu_cores * cpu_fraction))
    if max_stage456_jobs is not None:
        cpu_jobs = min(cpu_jobs, max_stage456_jobs)

    decisions: list[str] = []
    selected_gpu_devices = list(stage3_gpu_devices)
    if "stage3_gpu_devices" not in explicit_overrides:
        selected_gpu_devices = list(hardware.gpu_devices) if gpu_mode != "none" else []
        decisions.append("stage3_gpu_devices=detected_gpus" if selected_gpu_devices else "stage3_gpu_devices=empty")

    selected_stage3_tag_shards = stage3_tag_shards
    if "stage3_tag_shards" not in explicit_overrides:
        decisions.append("stage3_tag_shards=existing_default")

    selected_stage3_sentence_shards = stage3_sentence_shards
    if "stage3_sentence_shards" not in explicit_overrides:
        if gpu_mode != "none" and selected_gpu_devices:
            selected_stage3_sentence_shards, decision = choose_auto_stage3_sentence_shards(
                gpu_devices=selected_gpu_devices,
                gpu_metadata=hardware.gpu_metadata,
                cpu_jobs=cpu_jobs,
                stage3_tag_shards=selected_stage3_tag_shards,
            )
            decisions.append(decision)
        else:
            decisions.append("stage3_sentence_shards=existing_default")

    selected_stage3_jobs = stage3_jobs
    if "stage3_jobs" not in explicit_overrides:
        if selected_stage3_sentence_shards > 1 or selected_stage3_tag_shards > 1:
            stage3_shard_slots = selected_stage3_sentence_shards + selected_stage3_tag_shards
            selected_stage3_jobs = min(cpu_jobs, stage3_shard_slots)
            selected_stage3_jobs = max(1, selected_stage3_jobs)
            decisions.append("stage3_jobs=cpu_limited_stage3_shards")
        else:
            selected_stage3_jobs = None
            decisions.append("stage3_jobs=monolithic_unused")

    selected_stage456_shards = stage456_shards
    selected_stage456_jobs = stage456_jobs
    selected_stage456_merge_jobs = stage456_merge_jobs
    if stage6_facts_output_mode == "discard":
        if "stage456_jobs" not in explicit_overrides:
            selected_stage456_jobs = (
                selected_stage456_shards
                if "stage456_shards" in explicit_overrides
                else cpu_jobs
            )
            decisions.append(
                "stage456_jobs=explicit_shards"
                if "stage456_shards" in explicit_overrides
                else "stage456_jobs=cpu_quota_fraction"
            )
        if "stage456_shards" not in explicit_overrides:
            selected_stage456_shards = selected_stage456_jobs or cpu_jobs
            decisions.append("stage456_shards=stage456_jobs")
        if "stage456_merge_jobs" not in explicit_overrides:
            selected_stage456_merge_jobs = cpu_jobs
            decisions.append("stage456_merge_jobs=cpu_quota_fraction")
    else:
        decisions.append("stage456_auto_sharding_skipped_because_facts_are_written")
        if "stage456_merge_jobs" not in explicit_overrides:
            selected_stage456_merge_jobs = None
            decisions.append("stage456_merge_jobs=unused_without_sharding")

    chosen = {
        "stage3_sentence_shards": selected_stage3_sentence_shards,
        "stage3_tag_shards": selected_stage3_tag_shards,
        "stage3_jobs": selected_stage3_jobs,
        "stage3_gpu_devices": selected_gpu_devices,
        "stage456_shards": selected_stage456_shards,
        "stage456_jobs": selected_stage456_jobs,
        "stage456_merge_jobs": selected_stage456_merge_jobs,
    }
    return MixedPipelineResourcePlan(
        hardware=hardware,
        explicit_overrides=tuple(sorted(explicit_overrides)),
        cpu_fraction=cpu_fraction,
        max_stage456_jobs=max_stage456_jobs,
        stage6_facts_output_mode=stage6_facts_output_mode,
        chosen=chosen,
        decisions=tuple(decisions),
    )
