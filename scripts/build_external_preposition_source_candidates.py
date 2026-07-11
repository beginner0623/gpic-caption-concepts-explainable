"""Build offline candidate tables from external preposition resources.

This script is a source probe only. It does not update active relation
lexicons or Stage 4 extraction behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from gpic_concepts_v1.atomic_io import atomic_text_writer


SOURCE_ROOT = Path("outputs/external_preposition_sources")
OUTPUT_DIR = SOURCE_ROOT / "candidate_tables"

STREUSLE_FILES = [
    ("train", SOURCE_ROOT / "streusle/train/streusle.ud_train.json"),
    ("dev", SOURCE_ROOT / "streusle/dev/streusle.ud_dev.json"),
    ("test", SOURCE_ROOT / "streusle/test/streusle.ud_test.json"),
]
PASTRIE_FILES = [("all", SOURCE_ROOT / "pastrie/pastrie.json")]
PDEP_PREPCNTS = SOURCE_ROOT / "pdep_ca4pdep/data/subs/prepcnts.csv"
PDEP_SENSE_SUBS = SOURCE_ROOT / "pdep_ca4pdep/data/subs/sense-subs.csv"
TPP_FEATS = SOURCE_ROOT / "pdep_ca4pdep/data/featsTPP.txt"

PREP_LIKE_LEXCATS = {"P", "PP", "INF.P"}

MWE_OCCURRENCE_FIELDS = [
    "source",
    "source_file",
    "split",
    "sent_id",
    "expression_kind",
    "expression_id",
    "lexlemma",
    "lexlemma_key",
    "lexcat",
    "ss",
    "ss2",
    "toknums",
    "token_words",
    "token_upos",
    "surface",
    "contains_adp",
    "has_p_supersense",
    "candidate_basis",
    "text",
]

MWE_CANDIDATE_FIELDS = [
    "source",
    "lexlemma",
    "lexlemma_key",
    "occurrence_count",
    "split_counts",
    "expression_kinds",
    "lexcats",
    "supersenses",
    "surface_variants",
    "contains_adp_count",
    "has_p_supersense_count",
    "candidate_basis",
    "example_sent_ids",
    "example_texts",
]

PDEP_FIELDS = [
    "source",
    "prep",
    "prep_key",
    "token_count",
    "sense_count",
    "mwe_candidate_status",
]

PDEP_SENSE_FIELDS = [
    "source",
    "prep",
    "prep_key",
    "token_count",
    "sense",
    "opreps",
    "oprep_count",
    "oprep_mwe_count",
    "mwe_candidate_status",
]

TPP_FIELDS = [
    "source",
    "prep",
    "prep_key",
    "token_count",
    "sense_count",
    "feature_line_count",
    "significant_feature_count",
    "mwe_candidate_status",
]

COMBINED_FIELDS = [
    "source",
    "surface",
    "surface_key",
    "evidence_count",
    "source_detail",
    "candidate_basis",
    "source_table",
]

MANIFEST_FIELDS = [
    "source",
    "path",
    "exists",
    "size_bytes",
    "kind",
    "note",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=str(SOURCE_ROOT))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    source_root = Path(args.source_root)
    output_dir = Path(args.output_dir)

    streusle_occurrences = _extract_json_mwes(
        "streusle",
        [
            ("train", source_root / "streusle/train/streusle.ud_train.json"),
            ("dev", source_root / "streusle/dev/streusle.ud_dev.json"),
            ("test", source_root / "streusle/test/streusle.ud_test.json"),
        ],
        include_all_mwes=False,
    )
    pastrie_occurrences = _extract_json_mwes(
        "pastrie",
        [("all", source_root / "pastrie/pastrie.json")],
        include_all_mwes=True,
    )

    streusle_candidates = _aggregate_mwe_candidates(streusle_occurrences)
    pastrie_candidates = _aggregate_mwe_candidates(pastrie_occurrences)

    pdep_rows = _read_pdep_prepcnts(source_root / "pdep_ca4pdep/data/subs/prepcnts.csv")
    pdep_sense_rows = _read_pdep_sense_subs(
        source_root / "pdep_ca4pdep/data/subs/sense-subs.csv"
    )
    tpp_rows = _read_tpp_feature_summary(source_root / "pdep_ca4pdep/data/featsTPP.txt")
    manifest_rows = _build_manifest(source_root)
    combined_rows = _build_combined_candidates(
        streusle_candidates,
        pastrie_candidates,
        pdep_rows,
        tpp_rows,
    )

    _write_tsv(output_dir / "streusle_preposition_mwe_occurrences.tsv", MWE_OCCURRENCE_FIELDS, streusle_occurrences)
    _write_tsv(output_dir / "streusle_preposition_mwe_candidates.tsv", MWE_CANDIDATE_FIELDS, streusle_candidates)
    _write_tsv(output_dir / "pastrie_preposition_mwe_occurrences.tsv", MWE_OCCURRENCE_FIELDS, pastrie_occurrences)
    _write_tsv(output_dir / "pastrie_preposition_mwe_candidates.tsv", MWE_CANDIDATE_FIELDS, pastrie_candidates)
    _write_tsv(output_dir / "pdep_preposition_inventory.tsv", PDEP_FIELDS, pdep_rows)
    _write_tsv(output_dir / "pdep_sense_substitutes.tsv", PDEP_SENSE_FIELDS, pdep_sense_rows)
    _write_tsv(output_dir / "tpp_feature_preposition_summary.tsv", TPP_FIELDS, tpp_rows)
    _write_tsv(output_dir / "external_preposition_mwe_candidates_combined.tsv", COMBINED_FIELDS, combined_rows)
    _write_tsv(output_dir / "external_preposition_source_manifest.tsv", MANIFEST_FIELDS, manifest_rows)

    summary = {
        "source_root": str(source_root),
        "output_dir": str(output_dir),
        "streusle_occurrences": len(streusle_occurrences),
        "streusle_unique_candidates": len(streusle_candidates),
        "pastrie_occurrences": len(pastrie_occurrences),
        "pastrie_unique_candidates": len(pastrie_candidates),
        "pdep_prepositions": len(pdep_rows),
        "pdep_mwe_prepositions": sum(1 for row in pdep_rows if row["mwe_candidate_status"] == "mwe_candidate"),
        "pdep_sense_rows": len(pdep_sense_rows),
        "tpp_feature_prepositions": len(tpp_rows),
        "tpp_feature_mwe_prepositions": sum(1 for row in tpp_rows if row["mwe_candidate_status"] == "mwe_candidate"),
        "combined_mwe_candidates": len(combined_rows),
        "tpp_inventory_status": "not_retrieved",
        "tpp_feature_summary_scope": (
            "ca4pdep featsTPP.txt contains feature-summary rows for 44 "
            "single-token prepositions; it is not the original TPP "
            "373-preposition inventory."
        ),
        "tpp_note": (
            "Do not interpret tpp_feature_mwe_prepositions=0 as evidence that "
            "TPP has no phrasal prepositions. It only describes the retrieved "
            "ca4pdep featsTPP.txt feature-summary artifact."
        ),
    }
    with atomic_text_writer(output_dir / "external_preposition_source_summary.json") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


def _extract_json_mwes(
    source: str,
    files: list[tuple[str, Path]],
    *,
    include_all_mwes: bool,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for split, path in files:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for sent in data:
            toks = {int(tok["#"]): tok for tok in sent.get("toks", []) if isinstance(tok.get("#"), int)}
            for kind in ("smwes", "wmwes"):
                expressions = sent.get(kind) or {}
                for expression_id, expression in expressions.items():
                    row = _mwe_occurrence_row(
                        source=source,
                        source_file=str(path),
                        split=split,
                        sent=sent,
                        expression_kind=kind,
                        expression_id=str(expression_id),
                        expression=expression,
                        toks=toks,
                    )
                    if not row:
                        continue
                    if include_all_mwes or _is_preposition_related(row):
                        rows.append(row)
    rows.sort(key=lambda row: (row["source"], row["split"], row["sent_id"], row["expression_kind"], row["expression_id"]))
    return rows


def _mwe_occurrence_row(
    *,
    source: str,
    source_file: str,
    split: str,
    sent: dict[str, Any],
    expression_kind: str,
    expression_id: str,
    expression: dict[str, Any],
    toks: dict[int, dict[str, Any]],
) -> dict[str, str] | None:
    lexlemma = _normalize_space(str(expression.get("lexlemma") or ""))
    toknums = [int(toknum) for toknum in expression.get("toknums") or []]
    token_words = [str(toks[toknum].get("word", "")) for toknum in toknums if toknum in toks]
    token_upos = [str(toks[toknum].get("upos", "")) for toknum in toknums if toknum in toks]
    if _token_count(lexlemma) < 2 and len(toknums) < 2:
        return None

    lexcat = str(expression.get("lexcat") or "")
    ss = str(expression.get("ss") or "")
    ss2 = str(expression.get("ss2") or "")
    contains_adp = any(upos == "ADP" for upos in token_upos)
    has_p_supersense = ss.startswith("p.") or ss2.startswith("p.")
    basis = _candidate_basis(lexcat, contains_adp, has_p_supersense)

    return {
        "source": source,
        "source_file": source_file,
        "split": split,
        "sent_id": str(sent.get("sent_id") or ""),
        "expression_kind": expression_kind,
        "expression_id": expression_id,
        "lexlemma": lexlemma,
        "lexlemma_key": _surface_key(lexlemma),
        "lexcat": lexcat,
        "ss": ss,
        "ss2": ss2,
        "toknums": " ".join(str(toknum) for toknum in toknums),
        "token_words": " ".join(token_words),
        "token_upos": " ".join(token_upos),
        "surface": _normalize_space(" ".join(token_words)),
        "contains_adp": _bool_text(contains_adp),
        "has_p_supersense": _bool_text(has_p_supersense),
        "candidate_basis": basis,
        "text": _normalize_space(str(sent.get("text") or "")),
    }


def _is_preposition_related(row: dict[str, str]) -> bool:
    return row["candidate_basis"] != "not_preposition_related"


def _candidate_basis(lexcat: str, contains_adp: bool, has_p_supersense: bool) -> str:
    bases = []
    if lexcat in PREP_LIKE_LEXCATS:
        bases.append("prep_lexcat")
    if contains_adp:
        bases.append("contains_adp_token")
    if has_p_supersense:
        bases.append("p_supersense")
    return "|".join(bases) if bases else "not_preposition_related"


def _aggregate_mwe_candidates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["source"], row["lexlemma_key"])].append(row)

    output: list[dict[str, str]] = []
    for (source, _key), group in grouped.items():
        first = group[0]
        split_counts = Counter(row["split"] for row in group)
        expression_kinds = Counter(row["expression_kind"] for row in group)
        lexcats = Counter(row["lexcat"] for row in group if row["lexcat"])
        supersenses = Counter(
            value
            for row in group
            for value in (row["ss"], row["ss2"])
            if value
        )
        surface_variants = Counter(row["surface"] for row in group if row["surface"])
        bases = Counter(
            basis
            for row in group
            for basis in row["candidate_basis"].split("|")
            if basis
        )
        output.append(
            {
                "source": source,
                "lexlemma": first["lexlemma"],
                "lexlemma_key": first["lexlemma_key"],
                "occurrence_count": str(len(group)),
                "split_counts": _counter_join(split_counts),
                "expression_kinds": _counter_join(expression_kinds),
                "lexcats": _counter_join(lexcats),
                "supersenses": _counter_join(supersenses),
                "surface_variants": _counter_join(surface_variants),
                "contains_adp_count": str(sum(row["contains_adp"] == "true" for row in group)),
                "has_p_supersense_count": str(sum(row["has_p_supersense"] == "true" for row in group)),
                "candidate_basis": _counter_join(bases),
                "example_sent_ids": " | ".join(_unique(row["sent_id"] for row in group)[:5]),
                "example_texts": " || ".join(_unique(row["text"] for row in group)[:3]),
            }
        )
    output.sort(key=lambda row: (-int(row["occurrence_count"]), row["source"], row["lexlemma_key"]))
    return output


def _read_pdep_prepcnts(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            prep = _normalize_space(row["prep"])
            token_count = _token_count(prep)
            rows.append(
                {
                    "source": "pdep_ca4pdep_prepcnts",
                    "prep": prep,
                    "prep_key": _surface_key(prep),
                    "token_count": str(token_count),
                    "sense_count": str(row["cnt"]),
                    "mwe_candidate_status": "mwe_candidate" if token_count >= 2 else "single_token",
                }
            )
    rows.sort(key=lambda row: (row["mwe_candidate_status"] != "mwe_candidate", row["prep_key"]))
    return rows


def _read_pdep_sense_subs(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            prep = _normalize_space(row["prep"])
            opreps = _normalize_space(row.get("opreps", ""))
            oprep_parts = [part.strip() for part in opreps.split("/") if part.strip()]
            oprep_mwe_count = sum(1 for part in oprep_parts if _token_count(part) >= 2)
            token_count = _token_count(prep)
            rows.append(
                {
                    "source": "pdep_ca4pdep_sense_subs",
                    "prep": prep,
                    "prep_key": _surface_key(prep),
                    "token_count": str(token_count),
                    "sense": str(row["sense"]),
                    "opreps": opreps,
                    "oprep_count": str(len(oprep_parts)),
                    "oprep_mwe_count": str(oprep_mwe_count),
                    "mwe_candidate_status": "mwe_candidate" if token_count >= 2 else "single_token",
                }
            )
    rows.sort(key=lambda row: (row["prep_key"], row["sense"]))
    return rows


def _read_tpp_feature_summary(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    pattern = re.compile(
        r"^(?P<prep>.+?)\.chisq : (?P<senses>\d+) senses, "
        r"(?P<lines>\d+) lines, (?P<significant>\d+) significant$"
    )
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        prep = _normalize_space(match.group("prep"))
        token_count = _token_count(prep)
        rows.append(
            {
                "source": "tpp_ca4pdep_feature_summary",
                "prep": prep,
                "prep_key": _surface_key(prep),
                "token_count": str(token_count),
                "sense_count": match.group("senses"),
                "feature_line_count": match.group("lines"),
                "significant_feature_count": match.group("significant"),
                "mwe_candidate_status": "mwe_candidate" if token_count >= 2 else "single_token",
            }
        )
    rows.sort(key=lambda row: (row["mwe_candidate_status"] != "mwe_candidate", row["prep_key"]))
    return rows


def _build_combined_candidates(
    streusle_candidates: list[dict[str, str]],
    pastrie_candidates: list[dict[str, str]],
    pdep_rows: list[dict[str, str]],
    tpp_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for candidate in streusle_candidates:
        rows.append(
            {
                "source": "streusle",
                "surface": candidate["lexlemma"],
                "surface_key": candidate["lexlemma_key"],
                "evidence_count": candidate["occurrence_count"],
                "source_detail": f"lexcats={candidate['lexcats']}; supersenses={candidate['supersenses']}",
                "candidate_basis": candidate["candidate_basis"],
                "source_table": "streusle_preposition_mwe_candidates.tsv",
            }
        )
    for candidate in pastrie_candidates:
        if candidate["candidate_basis"] == "not_preposition_related:{}".format(candidate["occurrence_count"]):
            continue
        rows.append(
            {
                "source": "pastrie",
                "surface": candidate["lexlemma"],
                "surface_key": candidate["lexlemma_key"],
                "evidence_count": candidate["occurrence_count"],
                "source_detail": f"lexcats={candidate['lexcats']}; supersenses={candidate['supersenses']}",
                "candidate_basis": candidate["candidate_basis"],
                "source_table": "pastrie_preposition_mwe_candidates.tsv",
            }
        )
    for candidate in pdep_rows:
        if candidate["mwe_candidate_status"] != "mwe_candidate":
            continue
        rows.append(
            {
                "source": "pdep",
                "surface": candidate["prep"],
                "surface_key": candidate["prep_key"],
                "evidence_count": candidate["sense_count"],
                "source_detail": f"sense_count={candidate['sense_count']}",
                "candidate_basis": "pdep_multiword_preposition_entry",
                "source_table": "pdep_preposition_inventory.tsv",
            }
        )
    for candidate in tpp_rows:
        if candidate["mwe_candidate_status"] != "mwe_candidate":
            continue
        rows.append(
            {
                "source": "tpp",
                "surface": candidate["prep"],
                "surface_key": candidate["prep_key"],
                "evidence_count": candidate["sense_count"],
                "source_detail": (
                    f"sense_count={candidate['sense_count']}; "
                    f"significant_features={candidate['significant_feature_count']}"
                ),
                "candidate_basis": "tpp_feature_summary_multiword_preposition",
                "source_table": "tpp_feature_preposition_summary.tsv",
            }
        )
    rows.sort(key=lambda row: (row["surface_key"], row["source"]))
    return rows


def _build_manifest(source_root: Path) -> list[dict[str, str]]:
    targets = [
        ("streusle", source_root / "streusle", "git_clone", "STREUSLE source repository"),
        ("pastrie", source_root / "pastrie", "git_clone", "PASTRIE source repository"),
        ("pdep", source_root / "pdep_ca4pdep", "git_clone", "ca4pdep repository with PDEP-derived tables"),
        ("pdep", source_root / "pdep_ca4pdep/data/subs/prepcnts.csv", "csv", "PDEP prep sense counts"),
        ("pdep", source_root / "pdep_ca4pdep/data/subs/sense-subs.csv", "csv", "PDEP sense substitutes"),
        (
            "tpp",
            source_root / "pdep_ca4pdep/data/featsTPP.txt",
            "text",
            "TPP feature summary bundled in ca4pdep; not the original TPP inventory",
        ),
    ]
    rows = []
    for source, path, kind, note in targets:
        exists = path.exists()
        size = path.stat().st_size if exists and path.is_file() else 0
        rows.append(
            {
                "source": source,
                "path": str(path),
                "exists": _bool_text(exists),
                "size_bytes": str(size),
                "kind": kind,
                "note": note,
            }
        )
    return rows


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


def _normalize_space(value: object) -> str:
    if value is None:
        return ""
    value = str(value)
    return re.sub(r"\s+", " ", value.strip())


def _surface_key(value: str) -> str:
    return _normalize_space(value).lower()


def _token_count(value: str) -> int:
    value = _normalize_space(value)
    if not value:
        return 0
    return len(value.split(" "))


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _counter_join(counter: Counter[str]) -> str:
    return "|".join(f"{key}:{count}" for key, count in sorted(counter.items()))


def _unique(values: Any) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(str(value))
    return output


if __name__ == "__main__":
    raise SystemExit(main())
