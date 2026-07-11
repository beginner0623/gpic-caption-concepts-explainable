"""Filter preposition relation candidates by Google Books Ngram evidence.

This is an offline source-audit utility. It reads a user-provided workbook,
queries Google Books Ngram for the candidate `term` surfaces, and writes audit
TSVs. It does not update active relation lexicons or Stage 4 extraction.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path


YEAR_START = 2000
YEAR_END = 2019
CORPUS = 26
SMOOTHING = 0
CASE_INSENSITIVE = "true"
DEFAULT_CHUNK_SIZE = 80
DEFAULT_SLEEP_SECONDS = 0.2


def main() -> None:
    args = parse_args()
    rows = read_xlsx_sheet(args.input_xlsx, args.sheet_name)
    if not rows:
        raise SystemExit(f"no rows found in sheet: {args.sheet_name}")
    if "term" not in rows[0]:
        raise SystemExit("input sheet must contain a 'term' column")

    terms = ordered_unique(normalize_space(row.get("term", "")) for row in rows)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "preposition_relation_candidates_no_mid_of_ngram_term_cache.jsonl"
    results: dict[str, dict[str, str]] = read_cache(cache_path)
    missing_terms = [
        term
        for term in terms
        if surface_key(term) not in results
        or results[surface_key(term)].get("status", "").startswith("error:")
    ]
    chunks = list(chunked(missing_terms, args.chunk_size))

    print(f"input_rows={len(rows)}", flush=True)
    print(f"unique_terms={len(terms)}", flush=True)
    print(f"cached_terms={len(results)}", flush=True)
    print(f"missing_terms={len(missing_terms)}", flush=True)
    print(f"chunk_size={args.chunk_size}", flush=True)
    print(f"chunks={len(chunks)}", flush=True)

    for index, terms_chunk in enumerate(chunks, start=1):
        print(f"query_chunk={index}/{len(chunks)} terms={len(terms_chunk)}", flush=True)
        chunk_results = query_terms(terms_chunk)
        results.update(chunk_results)
        append_cache(cache_path, chunk_results)
        if args.request_sleep_seconds > 0 and index < len(chunks):
            time.sleep(args.request_sleep_seconds)

    input_fields = list(rows[0].keys())
    evidence_fields = [
        *input_fields,
        "ngram_surface",
        "ngram_surface_key",
        "ngram_mean_frequency",
        "ngram_max_frequency",
        "ngram_nonzero_years",
        "ngram_year_start",
        "ngram_year_end",
        "ngram_corpus",
        "ngram_smoothing",
        "ngram_case_insensitive",
        "ngram_status",
        "ngram_found",
        "ngram_query_url",
    ]

    evidence_rows = []
    for row in rows:
        term = normalize_space(row.get("term", ""))
        result = results.get(surface_key(term), error_result(term, "", "not_queried"))
        found = is_found(result)
        evidence_rows.append(
            {
                **row,
                "ngram_surface": result["surface"],
                "ngram_surface_key": result["surface_key"],
                "ngram_mean_frequency": result["mean_frequency"],
                "ngram_max_frequency": result["max_frequency"],
                "ngram_nonzero_years": result["nonzero_years"],
                "ngram_year_start": result["year_start"],
                "ngram_year_end": result["year_end"],
                "ngram_corpus": result["corpus"],
                "ngram_smoothing": result["smoothing"],
                "ngram_case_insensitive": result["case_insensitive"],
                "ngram_status": result["status"],
                "ngram_found": "yes" if found else "no",
                "ngram_query_url": result["query_url"],
            }
        )

    found_rows = [row for row in evidence_rows if row["ngram_found"] == "yes"]
    found_rows.sort(
        key=lambda row: (
            -float(row["ngram_mean_frequency"] or 0.0),
            row["term_key"],
        )
    )

    summary = build_summary(rows, evidence_rows, found_rows, args)

    write_tsv(output_dir / "preposition_relation_candidates_no_mid_of_ngram_evidence.tsv", evidence_fields, evidence_rows)
    write_tsv(output_dir / "preposition_relation_candidates_no_mid_of_ngram_found.tsv", evidence_fields, found_rows)
    write_tsv(output_dir / "preposition_relation_candidates_no_mid_of_ngram_summary.tsv", ["metric", "value"], [{"metric": key, "value": str(value)} for key, value in summary.items()])
    write_json(output_dir / "preposition_relation_candidates_no_mid_of_ngram_summary.json", summary)

    print(f"wrote={output_dir}")
    print(f"found_rows={len(found_rows)}")
    print(f"all_evidence_rows={len(evidence_rows)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-xlsx", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sheet-name", default="Candidates")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--request-sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS)
    args = parser.parse_args()
    if args.chunk_size < 1:
        raise SystemExit("--chunk-size must be >= 1")
    if args.request_sleep_seconds < 0:
        raise SystemExit("--request-sleep-seconds must be >= 0")
    return args


def read_xlsx_sheet(path: Path, sheet_name: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as zf:
        shared_strings = read_shared_strings(zf)
        sheet_path = workbook_sheet_path(zf, sheet_name)
        values = read_sheet_values(zf, sheet_path, shared_strings)
    if not values:
        return []
    headers = [normalize_space(value) for value in values[0]]
    rows = []
    for raw in values[1:]:
        row = {header: raw[index] if index < len(raw) else "" for index, header in enumerate(headers)}
        if any(value for value in row.values()):
            rows.append(row)
    return rows


def read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for si in root.findall("x:si", ns):
        parts = [node.text or "" for node in si.findall(".//x:t", ns)]
        strings.append("".join(parts))
    return strings


def workbook_sheet_path(zf: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    workbook_ns = {
        "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("r:Relationship", rel_ns)
    }
    for sheet in workbook.findall(".//x:sheet", workbook_ns):
        if sheet.attrib.get("name") == sheet_name:
            rel_id = sheet.attrib[f"{{{workbook_ns['r']}}}id"]
            target = rel_targets[rel_id]
            return f"xl/{target}" if not target.startswith("/") else target.lstrip("/")
    raise SystemExit(f"sheet not found: {sheet_name}")


def read_sheet_values(zf: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(zf.read(sheet_path))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows = []
    for row in root.findall(".//x:sheetData/x:row", ns):
        values: list[str] = []
        for cell in row.findall("x:c", ns):
            index = column_index(cell.attrib.get("r", ""))
            while len(values) <= index:
                values.append("")
            values[index] = cell_value(cell, shared_strings, ns)
        rows.append(values)
    return rows


def cell_value(cell: ET.Element, shared_strings: list[str], ns: dict[str, str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", ns))
    value_node = cell.find("x:v", ns)
    value = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "s" and value:
        return shared_strings[int(value)]
    return value


def column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    total = 0
    for letter in letters:
        total = total * 26 + (ord(letter) - ord("A") + 1)
    return total - 1


def query_terms(terms: list[str]) -> dict[str, dict[str, str]]:
    url = ngram_url(terms)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read().decode("utf-8")
        records = json.loads(payload)
    except Exception as exc:
        return {
            surface_key(term): error_result(term, url, f"error:{type(exc).__name__}")
            for term in terms
        }

    by_key = records_by_surface_key(records)
    out = {}
    for term in terms:
        key = surface_key(term)
        record = by_key.get(key)
        if not record:
            out[key] = error_result(term, url, "missing")
            continue
        timeseries = [float(value) for value in record.get("timeseries", [])]
        if not timeseries:
            out[key] = error_result(term, url, "empty_timeseries")
            continue
        out[key] = {
            "surface": term,
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
    return out


def ngram_url(terms: list[str]) -> str:
    params = {
        "content": ",".join(terms),
        "year_start": str(YEAR_START),
        "year_end": str(YEAR_END),
        "corpus": str(CORPUS),
        "smoothing": str(SMOOTHING),
        "case_insensitive": CASE_INSENSITIVE,
    }
    return "https://books.google.com/ngrams/json?" + urllib.parse.urlencode(params)


def records_by_surface_key(records: list[dict]) -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    for record in records:
        raw = str(record.get("ngram", ""))
        key = surface_key(strip_case_suffix(raw))
        if not key:
            continue
        existing = by_key.get(key)
        if existing is None or prefer_record(record, existing):
            by_key[key] = record
    return by_key


def prefer_record(candidate: dict, current: dict) -> bool:
    candidate_is_all = str(candidate.get("ngram", "")).endswith(" (All)")
    current_is_all = str(current.get("ngram", "")).endswith(" (All)")
    return candidate_is_all and not current_is_all


def strip_case_suffix(ngram: str) -> str:
    suffix = " (All)"
    if ngram.endswith(suffix):
        return ngram[: -len(suffix)]
    return ngram


def is_found(row: dict[str, str]) -> bool:
    try:
        return row.get("status") == "ok" and float(row.get("max_frequency", "0")) > 0.0
    except ValueError:
        return False


def error_result(surface: str, url: str, status: str) -> dict[str, str]:
    return {
        "surface": surface,
        "surface_key": surface_key(surface),
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


def build_summary(
    input_rows: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
    found_rows: list[dict[str, str]],
    args: argparse.Namespace,
) -> dict[str, object]:
    status_counts = Counter(row["ngram_status"] for row in evidence_rows)
    pattern_counts = Counter(row.get("pattern", "") for row in found_rows)
    mid_type_counts = Counter(row.get("mid_type", "") for row in found_rows)
    return {
        "input_xlsx": str(args.input_xlsx),
        "input_sheet": args.sheet_name,
        "input_rows": len(input_rows),
        "unique_terms": len({row.get("term_key", "") for row in input_rows}),
        "found_rows": len(found_rows),
        "missing_or_not_found_rows": len(evidence_rows) - len(found_rows),
        "year_start": YEAR_START,
        "year_end": YEAR_END,
        "corpus": CORPUS,
        "smoothing": SMOOTHING,
        "case_insensitive": CASE_INSENSITIVE,
        "found_definition": "ngram_status == ok and ngram_max_frequency > 0",
        "ngram_status_counts": dict(sorted(status_counts.items())),
        "found_pattern_counts": dict(sorted(pattern_counts.items())),
        "found_mid_type_counts": dict(sorted(mid_type_counts.items())),
    }


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    tmp = path.with_name(f".tmp_{path.name}")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def write_json(path: Path, value: dict[str, object]) -> None:
    tmp = path.with_name(f".tmp_{path.name}")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_cache(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            key = row.get("surface_key", "")
            if key:
                rows[key] = row
    return rows


def append_cache(path: Path, rows: dict[str, dict[str, str]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for row in rows.values():
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def ordered_unique(values) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def chunked(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip())


def surface_key(value: str) -> str:
    return normalize_space(value).lower()


if __name__ == "__main__":
    main()
