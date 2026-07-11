"""Build canonical-surface decisions from the integrated source-label inventory.

This script reads the semantic source-label inventory and emits synset-level
canonical decisions. It does not create or update active pipeline lexicons.
"""

from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
from pathlib import Path

import wn
from wn.morphy import Morphy

from gpic_concepts_v1.atomic_io import atomic_text_writer


ROOT = Path(os.environ.get("GPIC_RUNTIME_ROOT", Path.cwd()))
SOURCE_LABELS_DIR = ROOT / "resources" / "source_labels"
WN_DATA_DIR = ROOT / "resources" / "wn_data"
OEWN_SPEC = "oewn:2025+"

INVENTORY = SOURCE_LABELS_DIR / "object_source_label_synset_inventory.tsv"
OUTPUT = SOURCE_LABELS_DIR / "object_synset_canonical_decisions.tsv"
AMBIGUOUS_OUTPUT = SOURCE_LABELS_DIR / "object_synset_canonical_ambiguous.tsv"
NGRAM_EVIDENCE = SOURCE_LABELS_DIR / "google_ngram_canonical_frequency_evidence.tsv"

FORMAL_LOOKUP_CASES_FOR_CANONICAL = {
    "exact",
    "separator_variant",
    "joined_variant",
    "morphy",
}

FIELDNAMES = [
    "selected_oewn_synset",
    "selected_oewn_lexfile",
    "canonical_surface",
    "canonical_label_key",
    "canonical_selection_tag",
    "canonical_candidate_lemmas",
    "canonical_candidate_lemma_counts",
    "google_ngram_candidate_surfaces",
    "google_ngram_candidate_mean_frequencies",
    "source_exact_candidate_lemmas",
    "source_labels",
    "source_label_keys",
    "source_datasets",
    "selected_queries",
    "selected_lookup_cases",
    "synset_lemmas",
    "parent_oewn_synsets",
    "parent_oewn_lexfiles",
    "parent_lemmas",
    "parent_selection_tags",
    "row_count",
    "decision_basis",
]


def main() -> None:
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

    ngram_evidence = _read_ngram_evidence(NGRAM_EVIDENCE)
    decisions = [
        _decide_group(synset_id, group_rows, ngram_evidence, morphy)
        for synset_id, group_rows in groups.items()
    ]
    decisions.sort(key=lambda row: (row["canonical_selection_tag"], row["selected_oewn_synset"]))
    ambiguous = [row for row in decisions if not row["canonical_surface"]]

    _write_tsv(OUTPUT, FIELDNAMES, decisions)
    _write_tsv(AMBIGUOUS_OUTPUT, FIELDNAMES, ambiguous)

    print(f"wrote={OUTPUT}")
    print(f"wrote={AMBIGUOUS_OUTPUT}")
    print(f"selected_inventory_rows={len(rows)}")
    print(f"selected_synset_groups={len(groups)}")
    print(f"canonical_decision_rows={len(decisions)}")
    print(f"canonical_selected_rows={sum(bool(row['canonical_surface']) for row in decisions)}")
    print(f"canonical_ambiguous_rows={len(ambiguous)}")
    for tag, count in sorted(_count_by(decisions, "canonical_selection_tag").items()):
        print(f"canonical_selection_tag[{tag}]={count}")


def _decide_group(
    synset_id: str,
    rows: list[dict[str, str]],
    ngram_evidence: dict[tuple[str, str], float],
    morphy: Morphy,
) -> dict[str, str]:
    lemmas = _ordered_unique(
        lemma
        for row in rows
        for lemma in _split_pipe(row.get("synset_lemmas", ""))
    )
    source_labels = _ordered_unique(row.get("source_label", "") for row in rows)
    source_label_keys = _ordered_unique(_surface_key(label) for label in source_labels if label)
    source_datasets = _ordered_unique(row.get("dataset", "") for row in rows)
    selected_queries = _ordered_unique(row.get("selected_query", "") for row in rows)
    selected_lookup_cases = _ordered_unique(row.get("selected_lookup_case", "") for row in rows)
    parent_oewn_synsets = _ordered_unique(
        parent
        for row in rows
        for parent in _split_pipe(row.get("parent_oewn_synsets", ""))
    )
    parent_oewn_lexfiles = _ordered_unique(
        parent
        for row in rows
        for parent in _split_pipe(row.get("parent_oewn_lexfiles", ""))
    )
    parent_lemmas = _ordered_unique(
        parent
        for row in rows
        for parent in _split_pipe(row.get("parent_lemmas", ""))
    )
    parent_selection_tags = _ordered_unique(
        row.get("parent_selection_tag", "") for row in rows
    )

    support_keys = set()
    for label in source_labels:
        support_keys.update(_source_surface_variant_keys(label, morphy))
    for row in rows:
        if (
            row.get("selected_lookup_case") in FORMAL_LOOKUP_CASES_FOR_CANONICAL
            and row.get("selected_query")
        ):
            support_keys.add(_surface_key(row["selected_query"]))

    candidate_lemmas = [lemma for lemma in lemmas if _surface_key(lemma) in support_keys]
    if not candidate_lemmas and len(lemmas) == 1:
        candidate_lemmas = lemmas[:]

    counts = _wn30_counts_by_surface(rows)
    count_rows = [(lemma, counts.get(_surface_key(lemma), -1)) for lemma in candidate_lemmas]
    ngram_candidates = _ngram_candidate_surfaces(
        rows=rows,
        candidate_lemmas=candidate_lemmas,
    )
    canonical, tag = _select_canonical(
        synset_id=synset_id,
        candidate_lemmas=candidate_lemmas,
        count_rows=count_rows,
        source_label_keys=set(source_label_keys),
        all_lemmas=lemmas,
        ngram_candidates=ngram_candidates,
        ngram_evidence=ngram_evidence,
    )
    source_exact_candidates = [
        lemma for lemma in candidate_lemmas if _surface_key(lemma) in set(source_label_keys)
    ]

    return {
        "selected_oewn_synset": synset_id,
        "selected_oewn_lexfile": _first_nonempty(row.get("selected_oewn_lexfile", "") for row in rows),
        "canonical_surface": canonical,
        "canonical_label_key": _surface_key(canonical) if canonical else "",
        "canonical_selection_tag": tag,
        "canonical_candidate_lemmas": "|".join(candidate_lemmas),
        "canonical_candidate_lemma_counts": "|".join(
            f"{lemma}:{count}" for lemma, count in count_rows
        ),
        "google_ngram_candidate_surfaces": "|".join(ngram_candidates),
        "google_ngram_candidate_mean_frequencies": "|".join(
            f"{surface}:{ngram_evidence.get((synset_id, _surface_key(surface)), -1):.12g}"
            for surface in ngram_candidates
        ),
        "source_exact_candidate_lemmas": "|".join(source_exact_candidates),
        "source_labels": "|".join(source_labels),
        "source_label_keys": "|".join(source_label_keys),
        "source_datasets": "|".join(source_datasets),
        "selected_queries": "|".join(selected_queries),
        "selected_lookup_cases": "|".join(selected_lookup_cases),
        "synset_lemmas": "|".join(lemmas),
        "parent_oewn_synsets": "|".join(parent_oewn_synsets),
        "parent_oewn_lexfiles": "|".join(parent_oewn_lexfiles),
        "parent_lemmas": "|".join(parent_lemmas),
        "parent_selection_tags": "|".join(parent_selection_tags),
        "row_count": str(len(rows)),
        "decision_basis": tag,
    }


def _load_morphy() -> Morphy:
    wn.config.data_directory = str(WN_DATA_DIR)
    return Morphy(wn.Wordnet(OEWN_SPEC, expand=""))


def _select_canonical(
    *,
    synset_id: str,
    candidate_lemmas: list[str],
    count_rows: list[tuple[str, int]],
    source_label_keys: set[str],
    all_lemmas: list[str],
    ngram_candidates: list[str],
    ngram_evidence: dict[tuple[str, str], float],
) -> tuple[str, str]:
    if not candidate_lemmas:
        if len(all_lemmas) == 1:
            return all_lemmas[0], "selected_single_synset_lemma_without_source_match"
        return "", "ambiguous_no_source_variant_or_lookup_matched_oewn_lemma"
    if len(candidate_lemmas) == 1:
        return candidate_lemmas[0], "selected_single_source_or_lookup_matched_synset_lemma"

    valid_rows = [(lemma, count) for lemma, count in count_rows if count >= 0]
    if valid_rows:
        max_count = max(count for _, count in valid_rows)
        winners = [lemma for lemma, count in valid_rows if count == max_count]
        if max_count > 0 and len(winners) == 1:
            return winners[0], "selected_by_wn30_lemma_count_unique_positive_max"

    exact_matches = [lemma for lemma in candidate_lemmas if _surface_key(lemma) in source_label_keys]
    if len(exact_matches) == 1:
        return exact_matches[0], "selected_by_unique_official_source_surface"
    if valid_rows:
        max_count = max(count for _, count in valid_rows)
        if max_count <= 0:
            return _select_by_google_ngram(
                synset_id=synset_id,
                ngram_candidates=ngram_candidates,
                ngram_evidence=ngram_evidence,
                fallback_tag="ambiguous_wn30_all_zero_or_missing",
            )
        return _select_by_google_ngram(
            synset_id=synset_id,
            ngram_candidates=ngram_candidates,
            ngram_evidence=ngram_evidence,
            fallback_tag="ambiguous_wn30_tie",
        )
    return _select_by_google_ngram(
        synset_id=synset_id,
        ngram_candidates=ngram_candidates,
        ngram_evidence=ngram_evidence,
        fallback_tag="ambiguous_wn30_mapping_missing",
    )


def _select_by_google_ngram(
    *,
    synset_id: str,
    ngram_candidates: list[str],
    ngram_evidence: dict[tuple[str, str], float],
    fallback_tag: str,
) -> tuple[str, str]:
    scored = [
        (surface, ngram_evidence.get((synset_id, _surface_key(surface)), -1.0))
        for surface in ngram_candidates
    ]
    valid = [(surface, score) for surface, score in scored if score >= 0.0]
    if len(valid) < 2:
        if len(valid) == 1 and valid[0][1] > 0.0:
            return valid[0][0], "selected_by_single_available_positive_google_ngram"
        if valid and len(ngram_candidates) == 1:
            return valid[0][0], "selected_single_google_ngram_candidate"
        return "", f"{fallback_tag}_google_ngram_evidence_missing"
    max_score = max(score for _, score in valid)
    if max_score <= 0.0:
        return "", f"{fallback_tag}_google_ngram_all_zero"
    winners = [surface for surface, score in valid if score == max_score]
    if len(winners) == 1:
        return winners[0], "selected_by_google_ngram_frequency_unique_max"
    return "", f"{fallback_tag}_google_ngram_tie"


def _ngram_candidate_surfaces(
    *,
    rows: list[dict[str, str]],
    candidate_lemmas: list[str],
) -> list[str]:
    del rows
    return _ordered_unique(_surface_key(lemma) for lemma in candidate_lemmas if lemma)


def _wn30_counts_by_surface(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for entry in _split_pipe(row.get("wn30_lemma_counts", "")):
            parsed = _parse_wn30_count_entry(entry)
            if parsed is None:
                continue
            lemma, count = parsed
            key = _surface_key(lemma)
            counts[key] = max(counts.get(key, count), count)
    return counts


def _parse_wn30_count_entry(entry: str) -> tuple[str, int] | None:
    if not entry or ":wn30_missing" in entry:
        return None
    try:
        body, count_text = entry.rsplit(":", 1)
        count = int(count_text)
    except ValueError:
        return None
    try:
        _, rest = body.split(":", 1)
        lemma_part = rest.split("%", 1)[0]
    except ValueError:
        return None
    if not lemma_part:
        return None
    return lemma_part.replace("_", " "), count


def _surface_key(text: str) -> str:
    # Keep distinct lemmas distinct. Underscore is treated as WordNet's space
    # representation, but hyphen and joined forms are not collapsed.
    normalized = text.strip().lower()
    normalized = normalized.translate(
        str.maketrans(
            {
                "’": "'",
                "‘": "'",
                "‛": "'",
                "＇": "'",
                "‐": "-",
                "‑": "-",
                "‒": "-",
                "–": "-",
                "—": "-",
                "―": "-",
                "−": "-",
            }
        )
    )
    normalized = normalized.replace("_", " ")
    # Google Ngram tokenizes some punctuation as separated tokens, e.g.
    # "men 's" and "ping - pong". Collapse punctuation spacing only when
    # punctuation is between word characters; do not merge plain spaces.
    normalized = re.sub(r"(?<=\w)\s*-\s*(?=\w)", "-", normalized)
    normalized = re.sub(r"(?<=\w)\s*'\s*(?=\w)", "'", normalized)
    return " ".join(normalized.split())


def _source_surface_variant_keys(label: str, morphy: Morphy) -> set[str]:
    exact = _surface_key(label)
    separator_variant = _surface_key(label.replace("-", " ").replace("_", " "))
    joined_variant = "".join(exact.replace("-", " ").split())
    keys = {key for key in {exact, separator_variant, joined_variant} if key}
    for query in sorted(keys):
        result = morphy(query, "n")
        noun_lemmas = result.get("n", set()) if result else set()
        for lemma in noun_lemmas:
            key = _surface_key(lemma)
            if key:
                keys.add(key)
    return keys


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]


def _read_ngram_evidence(path: Path) -> dict[tuple[str, str], float]:
    if not path.exists():
        return {}
    evidence: dict[tuple[str, str], float] = {}
    for row in _read_tsv(path):
        synset_id = row.get("selected_oewn_synset", "")
        surface_key = row.get("surface_key", "")
        try:
            mean_frequency = float(row.get("mean_frequency", ""))
        except ValueError:
            continue
        if synset_id and surface_key:
            evidence[(synset_id, surface_key)] = mean_frequency
    return evidence


def _write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with atomic_text_writer(path, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _split_pipe(value: str) -> list[str]:
    return [part for part in value.split("|") if part]


def _ordered_unique(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _first_nonempty(values) -> str:
    for value in values:
        if value:
            return value
    return ""


def _count_by(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row[key]] += 1
    return counts


if __name__ == "__main__":
    main()
