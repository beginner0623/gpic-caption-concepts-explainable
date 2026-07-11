"""Query Google Books Ngram frequencies for unresolved canonical candidates.

This creates source-label analysis evidence only. It does not update active
pipeline lexicons.
"""

from __future__ import annotations

import csv
import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from build_object_synset_canonical_decisions import (
    INVENTORY,
    NGRAM_EVIDENCE,
    _decide_group,
    _load_morphy,
    _ngram_candidate_surfaces,
    _read_tsv,
    _surface_key,
)
from gpic_concepts_v1.atomic_io import atomic_text_writer


YEAR_START = 2000
YEAR_END = 2019
CORPUS = 26
SMOOTHING = 0
CASE_INSENSITIVE = "true"
REQUEST_SLEEP_SECONDS = 0.2
DEFAULT_CHUNK_SIZE = 80

FIELDNAMES = [
    "selected_oewn_synset",
    "surface",
    "surface_key",
    "mean_frequency",
    "max_frequency",
    "nonzero_years",
    "year_start",
    "year_end",
    "corpus",
    "smoothing",
    "case_insensitive",
    "query_url",
    "status",
]


def main() -> None:
    args = _parse_args()
    morphy = _load_morphy()
    rows = [
        row
        for row in _read_tsv(INVENTORY)
        if row.get("selection_status") == "selected"
        and row.get("selected_oewn_synset")
    ]
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["selected_oewn_synset"]].append(row)

    output_path = args.output
    if args.limit_groups is not None and output_path == NGRAM_EVIDENCE:
        raise SystemExit("--limit-groups requires --output so a sample run does not overwrite the main evidence TSV")

    existing_rows_by_pair = _read_existing_evidence_rows(output_path) if args.reuse_existing else {}
    existing_evidence = {
        pair: float(row["mean_frequency"])
        for pair, row in existing_rows_by_pair.items()
        if _has_mean_frequency(row)
    }

    tasks: list[tuple[str, list[str]]] = []
    decision_evidence = existing_evidence if args.reuse_existing else {}
    for synset_id, group_rows in sorted(groups.items()):
        first_pass = _decide_group(synset_id, group_rows, decision_evidence, morphy)
        if first_pass["canonical_surface"]:
            continue
        candidates = _ngram_candidate_surfaces(
            rows=group_rows,
            candidate_lemmas=first_pass["canonical_candidate_lemmas"].split("|")
            if first_pass["canonical_candidate_lemmas"]
            else [],
        )
        if not candidates:
            continue
        tasks.append((synset_id, candidates))

    if args.limit_groups is not None:
        tasks = tasks[: args.limit_groups]

    requested_surfaces = _ordered_unique(
        surface
        for synset_id, surfaces in tasks
        for surface in surfaces
        if not args.reuse_existing or (synset_id, _surface_key(surface)) not in existing_evidence
    )
    chunks = list(_chunks(requested_surfaces, args.chunk_size))
    print(f"candidate_synset_groups={len(tasks)}", flush=True)
    print(f"requested_unique_surfaces={len(requested_surfaces)}", flush=True)
    print(f"chunk_size={args.chunk_size}", flush=True)
    print(f"chunks={len(chunks)}", flush=True)

    surface_results: dict[str, dict[str, str]] = {}
    for index, surfaces in enumerate(chunks, start=1):
        print(f"query_chunk={index}/{len(chunks)} surfaces={len(surfaces)}", flush=True)
        surface_results.update(_query_surface_chunk(surfaces))
        if args.request_sleep_seconds > 0 and index < len(chunks):
            time.sleep(args.request_sleep_seconds)

    output_rows_by_pair: dict[tuple[str, str], dict[str, str]] = dict(existing_rows_by_pair) if args.reuse_existing else {}
    for synset_id, surfaces in tasks:
        for surface in surfaces:
            key = _surface_key(surface)
            pair = (synset_id, key)
            if args.reuse_existing and pair in existing_evidence:
                continue
            result = surface_results.get(
                key,
                _error_result(surface=surface, url="", status="not_queried"),
            )
            output_rows_by_pair[pair] = {"selected_oewn_synset": synset_id, **result}

    evidence_rows = list(output_rows_by_pair.values())
    evidence_rows.sort(key=lambda row: (row["selected_oewn_synset"], row["surface_key"]))
    _write_tsv(output_path, FIELDNAMES, evidence_rows)

    print(f"wrote={output_path}")
    print(f"evidence_rows={len(evidence_rows)}")
    print(f"synset_groups={len({row['selected_oewn_synset'] for row in evidence_rows})}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=NGRAM_EVIDENCE)
    parser.add_argument("--limit-groups", type=int, default=None)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--request-sleep-seconds", type=float, default=REQUEST_SLEEP_SECONDS)
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Read existing output evidence and query only missing surface rows.",
    )
    args = parser.parse_args()
    if args.chunk_size < 1:
        raise SystemExit("--chunk-size must be >= 1")
    if args.limit_groups is not None and args.limit_groups < 1:
        raise SystemExit("--limit-groups must be >= 1")
    if args.request_sleep_seconds < 0:
        raise SystemExit("--request-sleep-seconds must be >= 0")
    return args


def _query_surface_chunk(surfaces: list[str]) -> dict[str, dict[str, str]]:
    url = _ngram_url(surfaces)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read().decode("utf-8")
        records = json.loads(payload)
    except Exception as exc:
        return {
            _surface_key(surface): _error_result(
                surface=surface,
                url=url,
                status=f"error:{type(exc).__name__}",
            )
            for surface in surfaces
        }

    by_key = _records_by_surface_key(records)
    rows = {}
    for surface in surfaces:
        key = _surface_key(surface)
        record = by_key.get(key)
        if not record:
            rows[key] = _error_result(surface=surface, url=url, status="missing")
            continue
        timeseries = [float(value) for value in record.get("timeseries", [])]
        if not timeseries:
            rows[key] = _error_result(surface=surface, url=url, status="empty_timeseries")
            continue
        rows[key] = {
            "surface": surface,
            "surface_key": key,
            "mean_frequency": f"{(sum(timeseries) / len(timeseries)):.12g}",
            "max_frequency": f"{max(timeseries):.12g}",
            "nonzero_years": str(sum(value > 0.0 for value in timeseries)),
            "year_start": str(YEAR_START),
            "year_end": str(YEAR_END),
            "corpus": str(CORPUS),
            "smoothing": str(SMOOTHING),
            "case_insensitive": CASE_INSENSITIVE,
            "query_url": url,
            "status": "ok",
        }
    return rows


def _ngram_url(surfaces: list[str]) -> str:
    params = {
        "content": ",".join(surfaces),
        "year_start": str(YEAR_START),
        "year_end": str(YEAR_END),
        "corpus": str(CORPUS),
        "smoothing": str(SMOOTHING),
        "case_insensitive": CASE_INSENSITIVE,
    }
    return "https://books.google.com/ngrams/json?" + urllib.parse.urlencode(params)


def _strip_case_suffix(ngram: str) -> str:
    suffix = " (All)"
    if ngram.endswith(suffix):
        return ngram[: -len(suffix)]
    return ngram


def _records_by_surface_key(records: list[dict]) -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    for record in records:
        raw_ngram = record.get("ngram", "")
        key = _surface_key(_strip_case_suffix(raw_ngram))
        if not key:
            continue
        existing = by_key.get(key)
        if existing is None or _prefer_record(record, existing):
            by_key[key] = record
    return by_key


def _prefer_record(candidate: dict, current: dict) -> bool:
    # With case_insensitive=true Google returns an "(All)" aggregate plus
    # individual case variants. The aggregate is the intended evidence row.
    candidate_is_all = str(candidate.get("ngram", "")).endswith(" (All)")
    current_is_all = str(current.get("ngram", "")).endswith(" (All)")
    return candidate_is_all and not current_is_all


def _error_result(*, surface: str, url: str, status: str) -> dict[str, str]:
    return {
        "surface": surface,
        "surface_key": _surface_key(surface),
        "mean_frequency": "",
        "max_frequency": "",
        "nonzero_years": "",
        "year_start": str(YEAR_START),
        "year_end": str(YEAR_END),
        "corpus": str(CORPUS),
        "smoothing": str(SMOOTHING),
        "case_insensitive": CASE_INSENSITIVE,
        "query_url": url,
        "status": status,
    }


def _read_existing_evidence_rows(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    rows = {}
    for row in _read_tsv(path):
        synset_id = row.get("selected_oewn_synset", "")
        surface_key = row.get("surface_key", "")
        if synset_id and surface_key:
            rows[(synset_id, surface_key)] = row
    return rows


def _has_mean_frequency(row: dict[str, str]) -> bool:
    try:
        float(row.get("mean_frequency", ""))
    except ValueError:
        return False
    return True


def _chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _ordered_unique(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
