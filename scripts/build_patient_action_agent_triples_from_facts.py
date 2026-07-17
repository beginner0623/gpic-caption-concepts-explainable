from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TripleAccumulator:
    count: int = 0
    caption_count: int = 0
    last_caption_id: str | None = None
    example_caption_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RoleFact:
    action: str
    role: str
    target: str
    caption_id: str


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build exact patient-action-agent triple counts by streaming Stage 6 "
            "facts.jsonl event_role rows."
        ),
    )
    parser.add_argument("--facts-jsonl", required=True, type=Path)
    parser.add_argument("--output-tsv", required=True, type=Path)
    parser.add_argument("--progress-json", type=Path)
    parser.add_argument("--progress-every", type=int, default=1_000_000)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.output_tsv.exists() and not args.overwrite:
        raise SystemExit(f"output exists: {args.output_tsv}")

    accumulators = build_triples_from_facts(
        args.facts_jsonl,
        progress_json=args.progress_json,
        progress_every=args.progress_every,
    )
    write_triples_tsv(args.output_tsv, accumulators)
    if args.progress_json:
        _write_progress(
            args.progress_json,
            {
                "phase": "complete",
                "triple_rows": len(accumulators),
                "output_tsv": str(args.output_tsv),
            },
        )
    print(
        json.dumps(
            {
                "facts_jsonl": str(args.facts_jsonl),
                "output_tsv": str(args.output_tsv),
                "triple_rows": len(accumulators),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    return 0


def build_triples_from_facts(
    facts_jsonl: Path,
    *,
    progress_json: Path | None = None,
    progress_every: int = 1_000_000,
) -> dict[tuple[str, str, str], TripleAccumulator]:
    accumulators: dict[tuple[str, str, str], TripleAccumulator] = {}
    current_caption_id: str | None = None
    current_roles_by_action: dict[str, dict[str, list[RoleFact]]] = defaultdict(
        lambda: defaultdict(list),
    )
    rows_read = 0
    event_role_rows = 0

    for fact in _iter_jsonl(facts_jsonl):
        rows_read += 1
        if fact.get("fact_type") != "event_role":
            continue
        event_role_rows += 1
        role_fact = _role_fact_from_fact(fact)
        if role_fact is None:
            continue
        action_mention_id = _action_mention_id(fact)
        if not action_mention_id:
            continue
        if current_caption_id is None:
            current_caption_id = role_fact.caption_id
        if role_fact.caption_id != current_caption_id:
            _flush_caption_roles(current_roles_by_action, accumulators)
            current_roles_by_action = defaultdict(lambda: defaultdict(list))
            current_caption_id = role_fact.caption_id
        current_roles_by_action[action_mention_id][role_fact.role].append(role_fact)
        if progress_json and rows_read % max(1, progress_every) == 0:
            _write_progress(
                progress_json,
                {
                    "phase": "streaming_facts",
                    "rows_read": rows_read,
                    "event_role_rows": event_role_rows,
                    "triple_rows": len(accumulators),
                },
            )

    if current_roles_by_action:
        _flush_caption_roles(current_roles_by_action, accumulators)
    return accumulators


def _role_fact_from_fact(fact: Mapping[str, Any]) -> RoleFact | None:
    values = fact.get("values")
    if not isinstance(values, Mapping):
        return None
    action = str(values.get("action") or "")
    role = str(values.get("role") or "")
    target = str(values.get("target") or "")
    caption_id = str(fact.get("caption_id") or "")
    if not action or role not in {"agent", "patient"} or not target or not caption_id:
        return None
    return RoleFact(action=action, role=role, target=target, caption_id=caption_id)


def _action_mention_id(fact: Mapping[str, Any]) -> str:
    source_mention_ids = fact.get("source_mention_ids")
    if isinstance(source_mention_ids, list) and source_mention_ids:
        return str(source_mention_ids[0])
    return ""


def _flush_action_roles(
    roles: Mapping[str, list[RoleFact]],
    accumulators: dict[tuple[str, str, str], TripleAccumulator],
) -> None:
    agents = roles.get("agent", [])
    patients = roles.get("patient", [])
    if not agents or not patients:
        return
    for patient in patients:
        for agent in agents:
            key = (patient.target, patient.action, agent.target)
            acc = accumulators.setdefault(key, TripleAccumulator())
            acc.count += 1
            if acc.last_caption_id != patient.caption_id:
                acc.caption_count += 1
                acc.last_caption_id = patient.caption_id
            _accumulate_example_caption_id(acc.example_caption_ids, patient.caption_id)


def _flush_caption_roles(
    roles_by_action: Mapping[str, Mapping[str, list[RoleFact]]],
    accumulators: dict[tuple[str, str, str], TripleAccumulator],
) -> None:
    for roles in roles_by_action.values():
        _flush_action_roles(roles, accumulators)


def write_triples_tsv(
    output_tsv: Path,
    accumulators: Mapping[tuple[str, str, str], TripleAccumulator],
) -> None:
    output_tsv.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_tsv.with_name(output_tsv.name + ".tmp")
    fieldnames = [
        "patient_object",
        "action",
        "agent_object",
        "count",
        "caption_count",
        "example_caption_ids",
    ]
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for (patient, action, agent), acc in sorted(
            accumulators.items(),
            key=lambda item: (-item[1].count, item[0]),
        ):
            writer.writerow(
                {
                    "patient_object": patient,
                    "action": action,
                    "agent_object": agent,
                    "count": acc.count,
                    "caption_count": acc.caption_count,
                    "example_caption_ids": "|".join(acc.example_caption_ids),
                },
            )
    os.replace(tmp_path, output_tsv)


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _accumulate_example_caption_id(example_caption_ids: list[str], caption_id: str) -> None:
    if caption_id in example_caption_ids:
        return
    example_caption_ids.append(caption_id)
    example_caption_ids.sort()
    del example_caption_ids[5:]


def _write_progress(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, path)


if __name__ == "__main__":
    raise SystemExit(main())
