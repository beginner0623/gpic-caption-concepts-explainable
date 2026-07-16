from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.atomic_io import atomic_text_writer
from gpic_concepts_v1.io_jsonl import iter_jsonl
from gpic_concepts_v1.stage4_extract_raw import (
    _chunk_tokens,
    _is_allowed_token_record_span_start,
    _is_plural_common_noun_token,
    _normalize_query,
    _require_int,
    _token_record_span_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create an object prior TSV with plural-head observed span rows removed. "
            "The source prior is not modified."
        )
    )
    parser.add_argument("--stage3-records", required=True)
    parser.add_argument("--prior-object-inventory", required=True)
    parser.add_argument("--output-filtered-prior", required=True)
    parser.add_argument("--removed-output", required=True)
    parser.add_argument("--summary", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plural_span_keys = collect_plural_head_span_keys(iter_jsonl(args.stage3_records))
    kept_rows, removed_rows, fieldnames = filter_prior_rows(
        Path(args.prior_object_inventory),
        plural_span_keys,
    )
    write_tsv(Path(args.output_filtered_prior), kept_rows, fieldnames)
    write_tsv(Path(args.removed_output), removed_rows, fieldnames)
    summary = {
        "stage3_records": args.stage3_records,
        "prior_object_inventory": args.prior_object_inventory,
        "output_filtered_prior": args.output_filtered_prior,
        "removed_output": args.removed_output,
        "plural_span_key_count": len(plural_span_keys),
        "prior_rows_kept": len(kept_rows),
        "prior_rows_removed": len(removed_rows),
        "removed_examples": [row.get("span_key", "") for row in removed_rows[:25]],
    }
    with atomic_text_writer(Path(args.summary)) as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def collect_plural_head_span_keys(records: Iterable[Mapping[str, Any]]) -> set[str]:
    span_keys: set[str] = set()
    for record in records:
        token_by_i = {_require_int(token, "i"): token for token in record.get("tokens", [])}
        for chunk in record.get("noun_chunks", []):
            tokens = _chunk_tokens(chunk, token_by_i)
            if not tokens:
                continue
            root_i = _require_int(chunk, "root_i")
            root_pos = next(
                (
                    index
                    for index, token in enumerate(tokens)
                    if _require_int(token, "i") == root_i
                ),
                None,
            )
            if root_pos is None:
                continue
            root = tokens[root_pos]
            if not _is_plural_common_noun_token(root):
                continue
            for start_pos in range(0, root_pos + 1):
                span_tokens = tokens[start_pos : root_pos + 1]
                if len(span_tokens) > 1 and not _is_allowed_token_record_span_start(
                    span_tokens[0]
                ):
                    continue
                span_key = _normalize_query(_token_record_span_text(span_tokens))
                if span_key:
                    span_keys.add(span_key)
    return span_keys


def filter_prior_rows(
    prior_path: Path,
    plural_span_keys: set[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    with prior_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        kept_rows: list[dict[str, str]] = []
        removed_rows: list[dict[str, str]] = []
        for row in reader:
            span_key = _normalize_query(row.get("span_key", ""))
            if span_key in plural_span_keys:
                removed_rows.append(dict(row))
            else:
                kept_rows.append(dict(row))
    return kept_rows, removed_rows, fieldnames


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
