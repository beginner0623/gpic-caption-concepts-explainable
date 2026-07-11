"""Build Wiktionary/Wiktextract English preposition MWE candidates.

This is an offline source probe only. It does not update active relation
lexicons or Stage 4 extraction behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from gpic_concepts_v1.atomic_io import atomic_text_writer


DEFAULT_URL = (
    "https://kaikki.org/dictionary/English/pos-prep/"
    "kaikki.org-dictionary-English-by-pos-prep.jsonl"
)
SOURCE_PAGE_URL = "https://kaikki.org/dictionary/English/pos-prep/index.html"
SOURCE_CLASS = "WiktionaryEnglishPreposition"
SOURCE_VERSION = "kaikki_pos_prep_postprocessed_jsonl"


CANDIDATE_FIELDS = [
    "source",
    "source_version",
    "source_class",
    "surface",
    "surface_key",
    "token_count",
    "entry_count",
    "sense_count",
    "pos_values",
    "tags",
    "alt_of",
    "form_of",
    "categories",
    "glosses_sample",
    "source_url",
    "source_page_url",
    "candidate_status",
]

SENSE_FIELDS = [
    "source",
    "source_version",
    "source_class",
    "surface",
    "surface_key",
    "token_count",
    "entry_index",
    "sense_index",
    "entry_pos",
    "sense_id",
    "tags",
    "alt_of",
    "form_of",
    "categories",
    "raw_glosses",
    "glosses",
    "source_url",
    "source_page_url",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--output-dir",
        default="outputs/wiktionary_prep_mwe_candidates",
    )
    parser.add_argument(
        "--candidates-output",
        default=None,
        help="Unique surface-level TSV output path.",
    )
    parser.add_argument(
        "--senses-output",
        default=None,
        help="Sense-level TSV evidence output path.",
    )
    parser.add_argument("--summary", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    candidates_output = (
        Path(args.candidates_output)
        if args.candidates_output
        else output_dir / "wiktionary_prep_mwe_candidates.tsv"
    )
    senses_output = (
        Path(args.senses_output)
        if args.senses_output
        else output_dir / "wiktionary_prep_mwe_senses.tsv"
    )
    summary_output = (
        Path(args.summary)
        if args.summary
        else output_dir / "wiktionary_prep_mwe_summary.json"
    )

    stats: Counter[str] = Counter()
    aggregates: dict[str, dict[str, Any]] = {}
    sense_rows: list[dict[str, str]] = []

    with urllib.request.urlopen(args.url, timeout=60) as response:
        for entry_index, raw_line in enumerate(response, start=1):
            stats["jsonl_entries_read"] += 1
            if not raw_line.strip():
                continue
            entry = json.loads(raw_line.decode("utf-8"))
            if entry.get("lang_code") != "en":
                stats["non_english_entries_skipped"] += 1
                continue
            pos = str(entry.get("pos", ""))
            if pos != "prep":
                stats["non_prep_entries_skipped"] += 1
                continue
            stats["english_prep_entries"] += 1

            surface = _normalize_surface(str(entry.get("word", "")))
            token_count = _token_count(surface)
            if token_count < 2:
                stats["single_token_prep_entries_excluded"] += 1
                continue

            stats["mwe_prep_entries"] += 1
            surface_key = _surface_key(surface)
            aggregate = aggregates.setdefault(
                surface_key,
                {
                    "surface": surface,
                    "surface_key": surface_key,
                    "token_count": str(token_count),
                    "entry_count": 0,
                    "sense_count": 0,
                    "pos_values": Counter(),
                    "tags": Counter(),
                    "alt_of": Counter(),
                    "form_of": Counter(),
                    "categories": Counter(),
                    "glosses": [],
                },
            )
            aggregate["entry_count"] += 1
            aggregate["pos_values"][pos] += 1

            senses = entry.get("senses") or []
            for sense_index, sense in enumerate(senses, start=1):
                stats["mwe_prep_senses"] += 1
                aggregate["sense_count"] += 1
                tags = _string_list(sense.get("tags"))
                alt_of = _word_targets(sense.get("alt_of"))
                form_of = _word_targets(sense.get("form_of"))
                categories = _category_names(sense.get("categories"))
                glosses = _string_list(sense.get("glosses"))
                raw_glosses = _string_list(sense.get("raw_glosses"))

                aggregate["tags"].update(tags)
                aggregate["alt_of"].update(alt_of)
                aggregate["form_of"].update(form_of)
                aggregate["categories"].update(categories)
                for gloss in glosses:
                    if gloss and gloss not in aggregate["glosses"]:
                        aggregate["glosses"].append(gloss)

                sense_rows.append(
                    {
                        "source": "wiktionary",
                        "source_version": SOURCE_VERSION,
                        "source_class": SOURCE_CLASS,
                        "surface": surface,
                        "surface_key": surface_key,
                        "token_count": str(token_count),
                        "entry_index": str(entry_index),
                        "sense_index": str(sense_index),
                        "entry_pos": pos,
                        "sense_id": str(sense.get("id") or ""),
                        "tags": _join_sorted(tags),
                        "alt_of": _join_sorted(alt_of),
                        "form_of": _join_sorted(form_of),
                        "categories": _join_sorted(categories),
                        "raw_glosses": _join_preserve(raw_glosses),
                        "glosses": _join_preserve(glosses),
                        "source_url": args.url,
                        "source_page_url": SOURCE_PAGE_URL,
                    }
                )

    candidate_rows = [_candidate_row(aggregate, args.url) for aggregate in aggregates.values()]
    candidate_rows.sort(key=lambda row: (row["surface_key"], row["surface"]))
    sense_rows.sort(
        key=lambda row: (
            row["surface_key"],
            int(row["entry_index"]),
            int(row["sense_index"]),
        )
    )

    _write_tsv(candidates_output, CANDIDATE_FIELDS, candidate_rows)
    _write_tsv(senses_output, SENSE_FIELDS, sense_rows)

    summary = {
        "source_url": args.url,
        "source_page_url": SOURCE_PAGE_URL,
        "source_version": SOURCE_VERSION,
        "filter": {
            "lang_code": "en",
            "pos": "prep",
            "mwe_definition": "surface has at least two whitespace-delimited tokens",
        },
        "jsonl_entries_read": stats["jsonl_entries_read"],
        "english_prep_entries": stats["english_prep_entries"],
        "single_token_prep_entries_excluded": stats[
            "single_token_prep_entries_excluded"
        ],
        "mwe_prep_entries": stats["mwe_prep_entries"],
        "mwe_prep_senses": stats["mwe_prep_senses"],
        "unique_mwe_surfaces": len(candidate_rows),
        "candidate_output": str(candidates_output),
        "sense_output": str(senses_output),
    }
    with atomic_text_writer(summary_output) as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


def _candidate_row(aggregate: dict[str, Any], source_url: str) -> dict[str, str]:
    return {
        "source": "wiktionary",
        "source_version": SOURCE_VERSION,
        "source_class": SOURCE_CLASS,
        "surface": aggregate["surface"],
        "surface_key": aggregate["surface_key"],
        "token_count": aggregate["token_count"],
        "entry_count": str(aggregate["entry_count"]),
        "sense_count": str(aggregate["sense_count"]),
        "pos_values": _counter_join(aggregate["pos_values"]),
        "tags": _counter_join(aggregate["tags"]),
        "alt_of": _counter_join(aggregate["alt_of"]),
        "form_of": _counter_join(aggregate["form_of"]),
        "categories": _counter_join(aggregate["categories"]),
        "glosses_sample": _join_preserve(aggregate["glosses"][:5]),
        "source_url": source_url,
        "source_page_url": SOURCE_PAGE_URL,
        "candidate_status": "candidate",
    }


def _normalize_surface(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _surface_key(value: str) -> str:
    return _normalize_surface(value).lower()


def _token_count(value: str) -> int:
    normalized = _normalize_surface(value)
    if not normalized:
        return 0
    return len(normalized.split(" "))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _word_targets(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    targets = []
    for item in value:
        if isinstance(item, dict) and item.get("word"):
            targets.append(str(item["word"]))
    return targets


def _category_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def _counter_join(counter: Counter[str]) -> str:
    return "|".join(f"{key}:{count}" for key, count in sorted(counter.items()))


def _join_sorted(values: list[str]) -> str:
    return "|".join(sorted(set(values)))


def _join_preserve(values: list[str]) -> str:
    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return " || ".join(unique)


def _write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
