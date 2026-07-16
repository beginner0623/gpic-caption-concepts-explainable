"""Refresh Google Books Ngram evidence for canonical inventory blockers."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from enrich_gpic_inventory_canonical import _surface_key
from gpic_concepts_v1.atomic_io import atomic_text_writer


YEAR_START = 2000
YEAR_END = 2019
CORPUS = 26
SMOOTHING = 0
CASE_INSENSITIVE = "true"
DEFAULT_CHUNK_SIZE = 80
REQUEST_SLEEP_SECONDS = 0.2
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-inventory", required=True)
    parser.add_argument("--ngram-evidence", required=True)
    parser.add_argument("--summary")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--request-sleep-seconds", type=float, default=REQUEST_SLEEP_SECONDS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.chunk_size < 1:
        raise SystemExit("--chunk-size must be >= 1")
    if args.request_sleep_seconds < 0:
        raise SystemExit("--request-sleep-seconds must be >= 0")

    canonical_rows, _ = _read_tsv(Path(args.canonical_inventory))
    evidence_path = Path(args.ngram_evidence)
    existing_rows = _read_existing_evidence_rows(evidence_path)
    tasks = _missing_evidence_tasks(canonical_rows, existing_rows)
    requested_surfaces = _ordered_unique(surface for _, surface in tasks)

    surface_results: dict[str, dict[str, str]] = {}
    chunks = list(_chunks(requested_surfaces, args.chunk_size))
    for index, surfaces in enumerate(chunks, start=1):
        surface_results.update(_query_surface_chunk(surfaces))
        if args.request_sleep_seconds > 0 and index < len(chunks):
            time.sleep(args.request_sleep_seconds)

    output_rows = dict(existing_rows)
    for synset_id, surface in tasks:
        key = _surface_key(surface)
        output_rows[(synset_id, key)] = {
            "selected_oewn_synset": synset_id,
            **surface_results.get(
                key,
                _error_result(surface=surface, url="", status="not_queried"),
            ),
        }

    evidence_rows = list(output_rows.values())
    evidence_rows.sort(key=lambda row: (row["selected_oewn_synset"], row["surface_key"]))
    _write_tsv(evidence_path, evidence_rows, FIELDNAMES)

    summary = {
        "canonical_inventory": str(args.canonical_inventory),
        "ngram_evidence": str(evidence_path),
        "canonical_rows": len(canonical_rows),
        "missing_evidence_tasks": len(tasks),
        "requested_unique_surfaces": len(requested_surfaces),
        "chunks": len(chunks),
        "written_evidence_rows": len(evidence_rows),
        "queried_status_counts": dict(
            sorted(Counter(row["status"] for row in surface_results.values()).items())
        ),
    }
    if args.summary:
        with atomic_text_writer(Path(args.summary)) as handle:
            handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _missing_evidence_tasks(
    rows: list[dict[str, str]],
    existing_rows: dict[tuple[str, str], dict[str, str]],
) -> list[tuple[str, str]]:
    tasks: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        tag = row.get("canonical_selection_tag", "")
        if "google_ngram_evidence_missing" not in tag:
            continue
        synset_id = row.get("selected_oewn_synset", "").strip()
        if not synset_id:
            continue
        for surface in _split_pipe(row.get("google_ngram_candidate_surfaces", "")):
            key = (synset_id, _surface_key(surface))
            if key in existing_rows or key in seen:
                continue
            seen.add(key)
            tasks.append((synset_id, surface))
    return tasks


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


def _records_by_surface_key(records: list[dict]) -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    for record in records:
        key = _surface_key(_strip_case_suffix(str(record.get("ngram", ""))))
        if not key:
            continue
        existing = by_key.get(key)
        if existing is None or _prefer_record(record, existing):
            by_key[key] = record
    return by_key


def _prefer_record(candidate: dict, current: dict) -> bool:
    candidate_is_all = str(candidate.get("ngram", "")).endswith(" (All)")
    current_is_all = str(current.get("ngram", "")).endswith(" (All)")
    return candidate_is_all and not current_is_all


def _strip_case_suffix(value: str) -> str:
    suffix = " (All)"
    return value[: -len(suffix)] if value.endswith(suffix) else value


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
    rows, _ = _read_tsv(path)
    output = {}
    for row in rows:
        synset_id = row.get("selected_oewn_synset", "")
        surface_key = row.get("surface_key", "")
        if synset_id and surface_key:
            output[(synset_id, surface_key)] = {field: row.get(field, "") for field in FIELDNAMES}
    return output


def _read_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def _write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _split_pipe(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def _ordered_unique(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = _surface_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


if __name__ == "__main__":
    main()
