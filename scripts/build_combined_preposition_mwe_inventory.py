"""Combine curated external preposition MWE source inventories.

This is an offline source-audit utility. It does not update active relation
lexicons or Stage 4 extraction behavior.
"""

from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
from pathlib import Path


BASE = Path("outputs/external_preposition_sources/candidate_tables")

TPP_KEEP = BASE / "tpp_litkowski_2002_appendix_preposition_mwe_inventory_clean.tsv"
TPP_DROP = BASE / "tpp_litkowski_2002_appendix_preposition_mwe_inventory_excluded.tsv"
PDEP = BASE / "pdep_preposition_inventory.tsv"
STREUSLE_PASTRIE_KEEP = (
    BASE / "streusle_pastrie_p_lexcat_preposition_mwe_candidates_clean.tsv"
)
STREUSLE_PASTRIE_DROP = (
    BASE / "streusle_pastrie_p_lexcat_preposition_mwe_candidates_excluded.tsv"
)
WIKTIONARY = Path(
    "outputs/wiktionary_prep_mwe_candidates/wiktionary_prep_mwe_candidates.tsv"
)

COMBINED_KEEP = BASE / "combined_preposition_mwe_inventory.tsv"
COMBINED_KEEP_SOURCE_ROWS = BASE / "combined_preposition_mwe_source_rows.tsv"
COMBINED_NON_PREP = BASE / "combined_non_preposition_mwe_inventory.tsv"
COMBINED_NON_PREP_SOURCE_ROWS = BASE / "combined_non_preposition_mwe_source_rows.tsv"
COMBINED_CONFLICTS = BASE / "combined_preposition_mwe_conflicts.tsv"

SOURCE_PRIORITY = {
    "TPP": 0,
    "PDEP": 1,
    "WIKTIONARY": 2,
    "STREUSLE": 3,
    "PASTRIE": 4,
}

# Explicit user-approved manual decision on 2026-07-10:
# drop every source-disagreement entry from the prep-MWE inventory.
MANUAL_CONFLICT_DROP_KEYS = {
    "a cut above",
    "bare of",
    "in memoriam",
    "little short of",
    "nothing short of",
    "preparatory to",
    "short for",
    "shot through with",
}
MANUAL_CONFLICT_DROP_REASON = "manual_conflict_drop: user approved dropping all source-disagreement entries"

MANUAL_DROP_REASONS = {
    "a matter of": "manual_drop: noun phrase fragment headed by matter, not a preposition MWE",
    "as if": "manual_drop: clause-introducing conjunction, not a preposition MWE",
    "at hand": "manual_drop: idiomatic PP/adverbial expression, not a preposition MWE",
    "for example": "manual_drop: discourse adverbial/prepositional phrase, not a preposition MWE",
    "from the ground up": "manual_drop: complete adverbial phrase meaning from the beginning, not a preposition MWE",
    "in my hands": "manual_drop: ordinary PP, not a preposition MWE",
    "in this day": "manual_drop: ordinary PP or annotation artifact, not a preposition MWE",
    "seeing as": "manual_drop: clause-introducing conjunction, not a preposition MWE",
    "the dickens": "manual_drop: Wiktionary/Kaikki bad prep entry; current Wiktionary has adverb/noun evidence, not preposition",
}

SURFACE_VARIANT_TARGETS = {
    "d t": "due to",
    "out ta": "out of",
    "rather then": "rather than",
}


def normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def token_count(text: str) -> int:
    return len([part for part in re.split(r"\s+", text.strip()) if part])


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        key = normalize_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value.strip())
    return out


def parse_counted_surface_variants(value: str) -> list[str]:
    surfaces = []
    for part in value.split("|"):
        item = part.strip()
        if not item:
            continue
        surface = item
        if ":" in item:
            maybe_surface, maybe_count = item.rsplit(":", 1)
            if maybe_count.strip().isdigit():
                surface = maybe_surface
        surface = surface.strip()
        if surface:
            surfaces.append(surface)
    return unique_preserve_order(surfaces)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    tmp = path.with_name(f".tmp_{path.name}")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def add_keep(rows: list[dict[str, str]], row: dict[str, str]) -> None:
    rows.append(row)


def add_non_prep(rows: list[dict[str, str]], row: dict[str, str]) -> None:
    rows.append(row)


def add_keep_or_manual_drop(
    keep_rows: list[dict[str, str]],
    non_prep_rows: list[dict[str, str]],
    row: dict[str, str],
) -> None:
    reason = MANUAL_DROP_REASONS.get(row["entry_key"])
    if not reason:
        add_keep(keep_rows, row)
        return
    dropped = dict(row)
    dropped["source_status"] = f"{row['source_status']}+manual_drop"
    dropped["source_reason"] = (
        f"{row['source_reason']}; {reason}" if row["source_reason"] else reason
    )
    dropped["exclusion_reason"] = reason
    add_non_prep(non_prep_rows, dropped)


def base_source_row(
    *,
    entry: str,
    source_family: str,
    source_file: str,
    source_status: str,
    source_type: str = "",
    source_reason: str = "",
    source_order: str = "",
    source_url: str = "",
    source_entry: str = "",
    source_extracted_entry: str = "",
    canonical_lemma: str = "",
    lookup_forms: str = "",
    surface_variants: str = "",
    review_flag: str = "",
    exclusion_reason: str = "",
) -> dict[str, str]:
    key = normalize_key(entry)
    return {
        "entry_key": key,
        "entry": entry,
        "token_count": str(token_count(entry)),
        "source_family": source_family,
        "source_file": source_file,
        "source_entry": source_entry or entry,
        "source_extracted_entry": source_extracted_entry,
        "source_status": source_status,
        "source_type": source_type,
        "source_reason": source_reason,
        "source_order": source_order,
        "source_url": source_url,
        "canonical_lemma": canonical_lemma or entry,
        "lookup_forms": lookup_forms or entry,
        "surface_variants": surface_variants or entry,
        "review_flag": review_flag,
        "exclusion_reason": exclusion_reason,
    }


def sort_source_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            row["entry_key"],
            SOURCE_PRIORITY.get(row["source_family"], 99),
            row["source_family"],
            row["source_entry"],
        ),
    )


def grouped_lookup_surfaces(surfaces: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for surface in surfaces:
        entry = SURFACE_VARIANT_TARGETS.get(normalize_key(surface), normalize_key(surface))
        grouped[entry].append(surface.strip())
    return {entry: unique_preserve_order(values) for entry, values in grouped.items()}


def combine_rows(rows: list[dict[str, str]], *, non_prep: bool) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["entry_key"]].append(row)

    combined = []
    for key in sorted(grouped):
        group = sort_source_rows(grouped[key])
        representative = group[0]
        sources = sorted({row["source_family"] for row in group}, key=lambda s: SOURCE_PRIORITY.get(s, 99))
        statuses = []
        types = []
        reasons = []
        entries = []
        orders = []
        urls = []
        canonical_lemmas = []
        lookup_forms = []
        surface_variants = []
        review_flags = []
        exclusion_reasons = []
        for row in group:
            statuses.append(f"{row['source_family']}:{row['source_status']}")
            if row["source_type"]:
                types.append(f"{row['source_family']}:{row['source_type']}")
            if row["source_reason"]:
                reasons.append(f"{row['source_family']}:{row['source_reason']}")
            entries.append(f"{row['source_family']}:{row['source_entry']}")
            if row["source_order"]:
                orders.append(f"{row['source_family']}:{row['source_order']}")
            if row["source_url"]:
                urls.append(f"{row['source_family']}:{row['source_url']}")
            if row["canonical_lemma"]:
                canonical_lemmas.append(f"{row['source_family']}:{row['canonical_lemma']}")
            if row["lookup_forms"]:
                lookup_forms.append(f"{row['source_family']}:{row['lookup_forms']}")
            if row["surface_variants"]:
                surface_variants.append(f"{row['source_family']}:{row['surface_variants']}")
            if row["review_flag"]:
                review_flags.append(f"{row['source_family']}:{row['review_flag']}")
            if row["exclusion_reason"]:
                exclusion_reasons.append(f"{row['source_family']}:{row['exclusion_reason']}")

        out = {
            "entry_key": key,
            "entry": representative["entry"],
            "token_count": representative["token_count"],
            "source_count": str(len(sources)),
            "source_row_count": str(len(group)),
            "sources": "|".join(sources),
            "source_entries": "|".join(entries),
            "source_statuses": "|".join(statuses),
            "source_types": "|".join(types),
            "source_reasons": "|".join(reasons),
            "source_orders": "|".join(orders),
            "source_urls": "|".join(urls),
            "canonical_lemmas": "|".join(canonical_lemmas),
            "lookup_forms": "|".join(lookup_forms),
            "surface_variants": "|".join(surface_variants),
            "review_flags": "|".join(review_flags),
        }
        if non_prep:
            out["exclusion_reasons"] = "|".join(exclusion_reasons)
        combined.append(out)
    return combined


def build() -> None:
    keep_rows: list[dict[str, str]] = []
    non_prep_rows: list[dict[str, str]] = []

    for row in read_tsv(TPP_KEEP):
        add_keep_or_manual_drop(
            keep_rows,
            non_prep_rows,
            base_source_row(
                entry=row["entry"],
                source_family="TPP",
                source_file=TPP_KEEP.name,
                source_status=row["manual_status"],
                source_type=row["manual_type"],
                source_reason=row["manual_reason"],
                source_order=row["inventory_order"],
                source_url=row["source_url"],
                source_entry=row["entry"],
                source_extracted_entry=row["source_extracted_entry"],
                review_flag="",
                exclusion_reason="",
            ),
        )

    for row in read_tsv(TPP_DROP):
        add_non_prep(
            non_prep_rows,
            base_source_row(
                entry=row["entry"],
                source_family="TPP",
                source_file=TPP_DROP.name,
                source_status=row["manual_status"],
                source_type=row["manual_type"],
                source_reason=row["manual_reason"],
                source_order=row["inventory_order"],
                source_url=row["source_url"],
                source_entry=row["entry"],
                source_extracted_entry=row["source_extracted_entry"],
                exclusion_reason=row["manual_type"],
            ),
        )

    for row in read_tsv(PDEP):
        entry = row["prep"]
        if row["mwe_candidate_status"] == "mwe_candidate":
            add_keep_or_manual_drop(
                keep_rows,
                non_prep_rows,
                base_source_row(
                    entry=entry,
                    source_family="PDEP",
                    source_file=PDEP.name,
                    source_status=row["mwe_candidate_status"],
                    source_type="pdep_multiword_preposition_entry",
                    source_reason=f"sense_count={row['sense_count']}",
                    source_order=row["prep_key"],
                    source_entry=entry,
                ),
            )
        else:
            add_non_prep(
                non_prep_rows,
                base_source_row(
                    entry=entry,
                    source_family="PDEP",
                    source_file=PDEP.name,
                    source_status=row["mwe_candidate_status"],
                    source_type="single_word_preposition_not_mwe",
                    source_reason=f"sense_count={row['sense_count']}",
                    source_order=row["prep_key"],
                    source_entry=entry,
                    exclusion_reason="single_word_preposition_not_mwe",
                ),
            )

    for row in read_tsv(STREUSLE_PASTRIE_KEEP):
        source = row["source"].upper()
        status = row["inventory_status"]
        surfaces = parse_counted_surface_variants(row["surface_variants"])
        grouped_surfaces = grouped_lookup_surfaces(surfaces or [row["lexlemma"]])
        for entry, entry_surfaces in grouped_surfaces.items():
            lookup_forms = "|".join(entry_surfaces)
            add_keep_or_manual_drop(
                keep_rows,
                non_prep_rows,
                base_source_row(
                    entry=entry,
                    source_family=source,
                    source_file=STREUSLE_PASTRIE_KEEP.name,
                    source_status=status,
                    source_type="p_lexcat_preposition_mwe_candidate",
                    source_reason=(
                        f"canonical_lemma={row['lexlemma']}; "
                        f"supersenses={row['supersenses']}; surfaces={row['surface_variants']}"
                    ),
                    source_order=row["lexlemma_key"],
                    source_entry=row["lexlemma"],
                    source_extracted_entry=lookup_forms,
                    canonical_lemma=row["lexlemma"],
                    lookup_forms=lookup_forms or entry,
                    surface_variants=row["surface_variants"],
                    review_flag=status if status != "keep" else "",
                ),
            )

    for row in read_tsv(STREUSLE_PASTRIE_DROP):
        source = row["source"].upper()
        surfaces = parse_counted_surface_variants(row.get("surface_variants", ""))
        entry = surfaces[0] if surfaces else row["lexlemma"]
        add_non_prep(
            non_prep_rows,
            base_source_row(
                entry=entry,
                source_family=source,
                source_file=STREUSLE_PASTRIE_DROP.name,
                source_status=row["inventory_status"],
                source_type="single_word_split_or_typo_artifact",
                source_reason=f"canonical_lemma={row['lexlemma']}; {row['review_note']}",
                source_order=row["lexlemma_key"],
                source_entry=row["lexlemma"],
                source_extracted_entry=entry,
                canonical_lemma=row["lexlemma"],
                lookup_forms="|".join(surfaces) if surfaces else entry,
                surface_variants=row.get("surface_variants", ""),
                exclusion_reason=row["inventory_status"],
            ),
        )

    for row in read_tsv(WIKTIONARY):
        review_flag = ""
        if (
            normalize_key(row["surface"]) == "the dickens"
            and "no-gloss" in row["tags"]
            and not row["glosses_sample"].strip()
        ):
            review_flag = "wiktionary_no_gloss_bad_entry_review"
        source_row = base_source_row(
            entry=row["surface"],
            source_family="WIKTIONARY",
            source_file=WIKTIONARY.as_posix(),
            source_status=row["candidate_status"],
            source_type="wiktionary_pos_prep_mwe_candidate",
            source_reason=(
                f"pos_values={row['pos_values']}; tags={row['tags']}; "
                f"gloss={row['glosses_sample']}"
            ),
            source_order=row["surface_key"],
            source_url=row["source_page_url"] or row["source_url"],
            source_entry=row["surface"],
            review_flag=review_flag,
        )
        if "misspelling" in row["tags"]:
            source_row["source_status"] = f"{row['candidate_status']}+excluded_misspelling"
            source_row["source_type"] = "wiktionary_misspelling_variant_not_lookup_form"
            source_row["exclusion_reason"] = "wiktionary_misspelling_variant_not_lookup_form"
            add_non_prep(non_prep_rows, source_row)
        else:
            add_keep_or_manual_drop(keep_rows, non_prep_rows, source_row)

    non_prep_keys = {row["entry_key"] for row in non_prep_rows}
    manual_drop_keys = set(MANUAL_CONFLICT_DROP_KEYS) | non_prep_keys
    manually_dropped_keep_rows = [row for row in keep_rows if row["entry_key"] in manual_drop_keys]
    keep_rows = [
        row for row in keep_rows if row["entry_key"] not in manual_drop_keys
    ]
    for row in manually_dropped_keep_rows:
        dropped = dict(row)
        dropped["source_status"] = f"{row['source_status']}+manual_conflict_drop"
        dropped["source_reason"] = (
            f"{row['source_reason']}; {MANUAL_CONFLICT_DROP_REASON}"
            if row["source_reason"]
            else MANUAL_CONFLICT_DROP_REASON
        )
        dropped["exclusion_reason"] = MANUAL_CONFLICT_DROP_REASON
        add_non_prep(non_prep_rows, dropped)

    keep_source_rows = sort_source_rows(keep_rows)
    non_prep_source_rows = sort_source_rows(non_prep_rows)
    combined_keep = combine_rows(keep_source_rows, non_prep=False)
    combined_non_prep = combine_rows(non_prep_source_rows, non_prep=True)
    keep_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    non_prep_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in keep_source_rows:
        keep_by_key[row["entry_key"]].append(row)
    for row in non_prep_source_rows:
        non_prep_by_key[row["entry_key"]].append(row)
    conflict_rows = []
    for key in sorted(set(keep_by_key) & set(non_prep_by_key)):
        keep_group = sort_source_rows(keep_by_key[key])
        non_group = sort_source_rows(non_prep_by_key[key])
        conflict_rows.append(
            {
                "entry_key": key,
                "entry": keep_group[0]["entry"],
                "prep_sources": "|".join(sorted({row["source_family"] for row in keep_group}, key=lambda s: SOURCE_PRIORITY.get(s, 99))),
                "non_prep_sources": "|".join(sorted({row["source_family"] for row in non_group}, key=lambda s: SOURCE_PRIORITY.get(s, 99))),
                "prep_source_statuses": "|".join(f"{row['source_family']}:{row['source_status']}" for row in keep_group),
                "non_prep_source_statuses": "|".join(f"{row['source_family']}:{row['source_status']}" for row in non_group),
                "prep_source_reasons": "|".join(f"{row['source_family']}:{row['source_reason']}" for row in keep_group if row["source_reason"]),
                "non_prep_source_reasons": "|".join(f"{row['source_family']}:{row['source_reason']}" for row in non_group if row["source_reason"]),
            }
        )

    source_fields = [
        "entry_key",
        "entry",
        "token_count",
        "source_family",
        "source_file",
        "source_entry",
        "source_extracted_entry",
        "source_status",
        "source_type",
        "source_reason",
        "source_order",
        "source_url",
        "canonical_lemma",
        "lookup_forms",
        "surface_variants",
        "review_flag",
        "exclusion_reason",
    ]
    combined_fields = [
        "entry_key",
        "entry",
        "token_count",
        "source_count",
        "source_row_count",
        "sources",
        "source_entries",
        "source_statuses",
        "source_types",
        "source_reasons",
        "source_orders",
        "source_urls",
        "canonical_lemmas",
        "lookup_forms",
        "surface_variants",
        "review_flags",
    ]
    non_prep_fields = [*combined_fields, "exclusion_reasons"]
    conflict_fields = [
        "entry_key",
        "entry",
        "prep_sources",
        "non_prep_sources",
        "prep_source_statuses",
        "non_prep_source_statuses",
        "prep_source_reasons",
        "non_prep_source_reasons",
    ]

    write_tsv(COMBINED_KEEP_SOURCE_ROWS, keep_source_rows, source_fields)
    write_tsv(COMBINED_NON_PREP_SOURCE_ROWS, non_prep_source_rows, source_fields)
    write_tsv(COMBINED_KEEP, combined_keep, combined_fields)
    write_tsv(COMBINED_NON_PREP, combined_non_prep, non_prep_fields)
    write_tsv(COMBINED_CONFLICTS, conflict_rows, conflict_fields)

    print("keep_source_rows", len(keep_source_rows))
    print("keep_unique", len(combined_keep))
    print("non_prep_source_rows", len(non_prep_source_rows))
    print("non_prep_unique", len(combined_non_prep))
    print("conflict_unique", len(conflict_rows))
    print("source_counts", {source: sum(row["source_family"] == source for row in keep_source_rows) for source in SOURCE_PRIORITY})
    print("non_prep_source_counts", {source: sum(row["source_family"] == source for row in non_prep_source_rows) for source in SOURCE_PRIORITY})


if __name__ == "__main__":
    build()
