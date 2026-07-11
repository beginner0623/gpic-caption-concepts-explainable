"""Export active Stage 4 preposition MWE lexicon from reviewed inventory TSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import re
import sys

ROOT = Path(__file__).absolute().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpic_concepts_v1.atomic_io import atomic_text_writer


DEFAULT_INPUT = (
    ROOT
    / "outputs"
    / "external_preposition_sources"
    / "candidate_tables"
    / "combined_preposition_mwe_inventory.tsv"
)
DEFAULT_OUTPUT = ROOT / "resources" / "lexicons" / "preposition_mwes.tsv"
DEFAULT_NGRAM_INPUT = (
    ROOT
    / "outputs"
    / "external_preposition_sources"
    / "candidate_tables"
    / "preposition_relation_candidates_no_mid_of_ngram"
    / "preposition_relation_candidates_no_mid_of_ngram_found.tsv"
)


FIELDNAMES = [
    "surface",
    "token_sequence",
    "canonical_relation",
    "relation_components",
    "initial_relation_token_offset",
    "final_adp_token_offset",
    "source",
    "notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export active Stage 4 preposition MWE lexicon TSV.",
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Reviewed combined TSV.")
    parser.add_argument(
        "--ngram-input",
        default=str(DEFAULT_NGRAM_INPUT),
        help=(
            "Optional Google Ngram-filtered ADP...of relation pattern TSV. "
            "Use an empty string to skip it."
        ),
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output lexicon TSV.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    ngram_input_path = Path(args.ngram_input) if args.ngram_input else None
    output_path = Path(args.output)
    rows = _build_rows(input_path, ngram_input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(output_path, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {output_path}")


def _build_rows(input_path: Path, ngram_input_path: Path | None) -> list[dict[str, str]]:
    output: dict[tuple[str, str], dict[str, str]] = {}
    _add_reviewed_inventory_rows(output, input_path)
    if ngram_input_path is not None and ngram_input_path.exists():
        _add_ngram_relation_pattern_rows(output, ngram_input_path)
    return [output[key] for key in sorted(output)]


def _add_reviewed_inventory_rows(
    output: dict[tuple[str, str], dict[str, str]],
    input_path: Path,
) -> None:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
    for row in rows:
        canonical = _clean_surface(row.get("entry", "") or row.get("entry_key", ""))
        if not canonical:
            continue
        sources = row.get("sources", "")
        notes = _notes(row)
        for surface in _lookup_surfaces(row, canonical):
            _add_lexicon_row(output, surface=surface, canonical=canonical, source=sources, notes=notes)


def _add_ngram_relation_pattern_rows(
    output: dict[tuple[str, str], dict[str, str]],
    input_path: Path,
) -> None:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            if row.get("ngram_found", "").strip().lower() != "yes":
                continue
            if row.get("ngram_status", "").strip().lower() != "ok":
                continue
            surface = _clean_surface(row.get("term", ""))
            if not surface:
                continue
            notes = _ngram_notes(row)
            _add_lexicon_row(
                output,
                surface=surface,
                canonical=surface,
                source="GOOGLE_NGRAM_RELATION_PATTERN",
                notes=notes,
            )


def _add_lexicon_row(
    output: dict[tuple[str, str], dict[str, str]],
    *,
    surface: str,
    canonical: str,
    source: str,
    notes: str,
) -> None:
    tokens = surface.split()
    if len(tokens) < 2:
        return
    key = (surface, canonical)
    output.setdefault(
        key,
        {
            "surface": surface,
            "token_sequence": surface,
            "canonical_relation": canonical,
            "relation_components": "|".join(canonical.split()),
            "initial_relation_token_offset": "0",
            "final_adp_token_offset": str(len(tokens) - 1),
            "source": source,
            "notes": notes,
        },
    )


def _lookup_surfaces(row: dict[str, str], canonical: str) -> list[str]:
    surfaces: list[str] = []
    for column in ("lookup_forms", "surface_variants", "entry"):
        value = row.get(column, "")
        for item in _split_source_values(value):
            surface = _clean_surface(item)
            if surface:
                _append_unique(surfaces, surface)
    _append_unique(surfaces, canonical)
    return surfaces


def _split_source_values(value: str) -> list[str]:
    items: list[str] = []
    for part in value.split("|"):
        text = part.strip()
        if not text:
            continue
        if ":" in text:
            prefix, suffix = text.split(":", 1)
            if prefix.isupper() or prefix in {"TPP", "PDEP", "STREUSLE", "PASTRIE", "WIKTIONARY"}:
                text = suffix
        text = re.sub(r":\d+$", "", text)
        items.append(text)
    return items


def _clean_surface(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _notes(row: dict[str, str]) -> str:
    parts = []
    if row.get("review_flags"):
        parts.append(f"review_flags={row['review_flags']}")
    if row.get("source_count"):
        parts.append(f"source_count={row['source_count']}")
    if row.get("source_row_count"):
        parts.append(f"source_row_count={row['source_row_count']}")
    return "; ".join(parts)


def _ngram_notes(row: dict[str, str]) -> str:
    parts = [
        f"pattern={row.get('pattern', '')}",
        f"mid_type={row.get('mid_type', '')}",
        f"ngram_mean_frequency={row.get('ngram_mean_frequency', '')}",
        f"ngram_max_frequency={row.get('ngram_max_frequency', '')}",
        f"ngram_nonzero_years={row.get('ngram_nonzero_years', '')}",
        "ngram_years=2000-2019",
    ]
    return "; ".join(part for part in parts if not part.endswith("="))


if __name__ == "__main__":
    main()
