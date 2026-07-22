from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CountRow:
    label: str
    raw_surfaces: str
    caption_count: int


@dataclass(frozen=True, slots=True)
class PairRow:
    entity: str
    attribute: str
    caption_count: int


@dataclass(frozen=True, slots=True)
class MatchResult:
    labels: tuple[str, ...]
    caption_count: int
    strategy: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare canary T5 concept counts against the lexicon report DB.",
    )
    parser.add_argument("--t5-counts-json", required=True, type=Path)
    parser.add_argument("--report-db", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    t5 = json.loads(args.t5_counts_json.read_text(encoding="utf-8"))
    with sqlite3.connect(args.report_db) as conn:
        conn.row_factory = sqlite3.Row
        object_rows = _load_count_rows(
            conn,
            table="objects",
            label_col="canonical_object",
            raw_col="object_raw_surfaces",
        )
        attribute_rows = _load_count_rows(
            conn,
            table="attributes",
            label_col="canonical_attribute",
            raw_col="attribute_raw_surfaces",
        )
        pair_rows = _load_pair_rows(conn)

    entity_counts: Mapping[str, int] = t5.get("entity_caption_counts", {})
    attribute_counts: Mapping[str, int] = t5.get("attribute_caption_counts", {})
    pair_counts: Mapping[str, int] = t5.get("entity_attribute_pair_caption_counts", {})

    object_matcher = LabelMatcher(object_rows, include_variants_with_exact=False)
    attribute_matcher = LabelMatcher(attribute_rows, include_variants_with_exact=True)
    pair_matcher = PairMatcher(pair_rows, object_matcher=object_matcher, attribute_matcher=attribute_matcher)

    lines: list[str] = [
        "# Canary170 T5 vs Lexicon Caption Count Comparison",
        "",
        f"- T5 records scanned: {t5.get('records_scanned', '')}",
        f"- T5 extraction seconds: {round(float(t5.get('elapsed_seconds', 0.0)), 3)}",
        "- Match order: exact canonical/raw, then normalized generated variants.",
        "",
        "## 1. Entity Caption Counts",
        "",
        "| entity | T5 caption_count | lexicon entity | lexicon caption_count | lexicon - T5 diff | match |",
        "|---|---:|---|---:|---:|---|",
    ]
    for entity in sorted(entity_counts, key=lambda key: (-int(entity_counts[key]), key)):
        t5_count = int(entity_counts.get(entity, 0))
        match = object_matcher.match(entity)
        lines.append(
            _table_row(
                [
                    entity,
                    _fmt_int(t5_count),
                    _join_labels(match.labels),
                    _fmt_int(match.caption_count),
                    _fmt_int(match.caption_count - t5_count),
                    match.strategy,
                ],
            ),
        )

    lines.extend(
        [
            "",
            "## 2. Attribute Caption Counts",
            "",
            "| T5 attribute | T5 caption_count | lexicon attribute | lexicon caption_count | lexicon - T5 diff | match |",
            "|---|---:|---|---:|---:|---|",
        ],
    )
    for attribute in sorted(attribute_counts, key=lambda key: (-int(attribute_counts[key]), key)):
        t5_count = int(attribute_counts.get(attribute, 0))
        match = attribute_matcher.match(attribute)
        lines.append(
            _table_row(
                [
                    attribute,
                    _fmt_int(t5_count),
                    _join_labels(match.labels),
                    _fmt_int(match.caption_count),
                    _fmt_int(match.caption_count - t5_count),
                    match.strategy,
                ],
            ),
        )

    lines.extend(
        [
            "",
            "## 3. Entity-Attribute Pair Caption Counts",
            "",
            "| entity | attribute | T5 caption_count | lexicon entity | lexicon attribute | lexicon caption_count | lexicon - T5 diff | match |",
            "|---|---|---:|---|---|---:|---:|---|",
        ],
    )
    sorted_pairs = sorted(pair_counts, key=lambda key: (-int(pair_counts[key]), key))
    for pair_key in sorted_pairs:
        entity, attribute = pair_key.split("\t", 1)
        t5_count = int(pair_counts.get(pair_key, 0))
        match = pair_matcher.match(entity, attribute)
        lines.append(
            _table_row(
                [
                    entity,
                    attribute,
                    _fmt_int(t5_count),
                    _join_labels(match.entity_labels),
                    _join_labels(match.attribute_labels),
                    _fmt_int(match.caption_count),
                    _fmt_int(match.caption_count - t5_count),
                    match.strategy,
                ],
            ),
        )

    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output_md": str(args.output_md)}, ensure_ascii=False))
    return 0


def _load_count_rows(
    conn: sqlite3.Connection,
    *,
    table: str,
    label_col: str,
    raw_col: str,
) -> list[CountRow]:
    rows = []
    for row in conn.execute(
        f"SELECT {label_col} AS label, {raw_col} AS raw_surfaces, caption_count FROM {table}",
    ):
        rows.append(
            CountRow(
                label=str(row["label"] or ""),
                raw_surfaces=str(row["raw_surfaces"] or ""),
                caption_count=int(row["caption_count"] or 0),
            ),
        )
    return rows


def _load_pair_rows(conn: sqlite3.Connection) -> list[PairRow]:
    rows = []
    for row in conn.execute(
        "SELECT object, attribute, caption_count FROM attribute_object_pairs",
    ):
        rows.append(
            PairRow(
                entity=str(row["object"] or ""),
                attribute=str(row["attribute"] or ""),
                caption_count=int(row["caption_count"] or 0),
            ),
        )
    return rows


class LabelMatcher:
    def __init__(self, rows: Iterable[CountRow], *, include_variants_with_exact: bool) -> None:
        self._include_variants_with_exact = include_variants_with_exact
        self._exact: dict[str, set[CountRow]] = defaultdict(set)
        for row in rows:
            for surface in _row_surfaces(row):
                norm = _norm(surface)
                if not norm:
                    continue
                self._exact[norm].add(row)

    def match(self, label: str) -> MatchResult:
        norm = _norm(label)
        exact_rows = self._exact.get(norm, set())
        if exact_rows and not self._include_variants_with_exact:
            return _match_result(exact_rows, "exact_canonical_or_raw")

        variant_rows: set[CountRow] = set()
        for key in _label_keys(norm):
            variant_rows.update(self._exact.get(key, set()))
        variant_rows = _filter_variant_rows(label, variant_rows)
        if exact_rows:
            combined_rows = set(exact_rows)
            combined_rows.update(variant_rows)
            strategy = "exact_canonical_or_raw"
            if variant_rows - exact_rows:
                strategy = "exact_plus_generated_variant"
            return _match_result(combined_rows, strategy)
        return _match_result(variant_rows, "generated_variant" if variant_rows else "missing")

    def labels_for(self, label: str) -> tuple[str, ...]:
        return self.match(label).labels


@dataclass(frozen=True, slots=True)
class PairMatchResult:
    entity_labels: tuple[str, ...]
    attribute_labels: tuple[str, ...]
    caption_count: int
    strategy: str


class PairMatcher:
    def __init__(
        self,
        rows: Iterable[PairRow],
        *,
        object_matcher: LabelMatcher,
        attribute_matcher: LabelMatcher,
    ) -> None:
        self._rows_by_pair: dict[tuple[str, str], list[PairRow]] = defaultdict(list)
        for row in rows:
            self._rows_by_pair[(_norm(row.entity), _norm(row.attribute))].append(row)
        self._object_matcher = object_matcher
        self._attribute_matcher = attribute_matcher

    def match(self, entity: str, attribute: str) -> PairMatchResult:
        entity_match = self._object_matcher.match(entity)
        attribute_match = self._attribute_matcher.match(attribute)
        total = 0
        entity_labels = entity_match.labels
        attribute_labels = attribute_match.labels
        for entity_label in entity_labels:
            for attribute_label in attribute_labels:
                for row in self._rows_by_pair.get((_norm(entity_label), _norm(attribute_label)), []):
                    total += row.caption_count
        if total:
            strategy = _combine_strategy(entity_match.strategy, attribute_match.strategy)
        elif not entity_labels or not attribute_labels:
            strategy = "missing"
        else:
            strategy = "no_pair_row_for_matched_labels"
        return PairMatchResult(
            entity_labels=entity_labels,
            attribute_labels=attribute_labels,
            caption_count=total,
            strategy=strategy,
        )


def _match_result(rows: Iterable[CountRow], strategy: str) -> MatchResult:
    unique = sorted(set(rows), key=lambda row: (-row.caption_count, _norm(row.label)))
    return MatchResult(
        labels=_display_labels(unique),
        caption_count=sum(row.caption_count for row in unique),
        strategy=strategy,
    )


def _filter_variant_rows(label: str, rows: Iterable[CountRow]) -> set[CountRow]:
    query_is_proper = _looks_like_proper_label(str(label or "").strip())
    filtered = set()
    for row in rows:
        candidate = _display_label(row.label)
        if _looks_like_proper_label(candidate) and not query_is_proper:
            continue
        filtered.add(row)
    return filtered


def _row_surfaces(row: CountRow) -> list[str]:
    surfaces = [row.label]
    surfaces.extend(part for part in row.raw_surfaces.split("|") if part)
    return surfaces


def _label_keys(label: str) -> set[str]:
    norm = _norm(label)
    keys = {norm}
    if not norm:
        return keys
    keys.update(_separator_variants(norm))
    for item in list(keys):
        keys.update(_inflection_variants(item))
        keys.update(_shape_variants(item))
    return {_norm(key) for key in keys if _norm(key)}


def _separator_variants(label: str) -> set[str]:
    variants = {label}
    variants.add(label.replace("_", " "))
    variants.add(label.replace("-", " "))
    variants.add(label.replace(" ", "-"))
    variants.add(label.replace(" - ", "-"))
    variants.add(label.replace(" - ", " "))
    return variants


def _inflection_variants(label: str) -> set[str]:
    variants = {label}
    words = label.split()
    if not words:
        return variants
    head = words[-1]
    stems = {head}
    if head.endswith("ied") and len(head) > 3:
        stems.add(head[:-3] + "y")
    if head.endswith("ed") and len(head) > 3:
        base = head[:-2]
        stems.add(base)
        if len(base) >= 2 and base[-1] == base[-2]:
            stems.add(base[:-1])
        stems.add(head[:-1])
    if head.endswith("ing") and len(head) > 4:
        base = head[:-3]
        stems.add(base)
        stems.add(base + "e")
        if len(base) >= 2 and base[-1] == base[-2]:
            stems.add(base[:-1])
    for stem in list(stems):
        forms = {stem + "ed", stem + "ing"}
        if stem.endswith("e"):
            forms.add(stem + "d")
            forms.add(stem[:-1] + "ing")
        if _is_cvc(stem):
            forms.add(stem + stem[-1] + "ed")
            forms.add(stem + stem[-1] + "ing")
        forms.update(_irregular_participle_forms(stem))
        for form in forms:
            variants.add(" ".join((*words[:-1], form)))
    if len(words) == 1:
        variants.update(stems)
    return variants


def _irregular_participle_forms(stem: str) -> set[str]:
    irregular = {
        "draw": {"drawn"},
    }
    forms = set(irregular.get(stem, set()))
    if "-" in stem:
        prefix, suffix = stem.rsplit("-", 1)
        for form in irregular.get(suffix, set()):
            forms.add(f"{prefix}-{form}")
    return forms


def _shape_variants(label: str) -> set[str]:
    variants = {label}
    if label.endswith(" - shape"):
        variants.add(label[: -len(" - shape")] + "-shaped")
    if label.endswith(" shape"):
        variants.add(label[: -len(" shape")] + "-shaped")
    if label.endswith("-shaped"):
        variants.add(label[: -len("-shaped")] + " shape")
        variants.add(label[: -len("-shaped")] + " - shape")
    return variants


def _is_cvc(stem: str) -> bool:
    if len(stem) < 3:
        return False
    vowels = set("aeiou")
    return stem[-1] not in vowels and stem[-2] in vowels and stem[-3] not in vowels and stem[-1] not in {"w", "x", "y"}


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.strip("\"'“”‘’")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("_", " ")
    return text


def _combine_strategy(entity_strategy: str, attribute_strategy: str) -> str:
    if entity_strategy == attribute_strategy == "exact_canonical_or_raw":
        return "exact_canonical_or_raw"
    return f"entity:{entity_strategy};attribute:{attribute_strategy}"


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _display_labels(rows: Iterable[CountRow]) -> tuple[str, ...]:
    seen = set()
    labels: list[str] = []
    for row in rows:
        label = _display_label(row.label)
        key = _norm(label)
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return tuple(labels)


def _display_label(label: str) -> str:
    return str(label or "").strip().strip("\"'“”‘’`")


def _looks_like_proper_label(label: str) -> bool:
    stripped = _display_label(label)
    if not stripped:
        return False
    letters = [char for char in stripped if char.isalpha()]
    if not letters:
        return False
    return any(char.isupper() for char in letters) and not stripped.isupper()


def _join_labels(labels: Iterable[str]) -> str:
    values = list(labels)
    return "<br>".join(values) if values else "MISSING"


def _table_row(values: Iterable[Any]) -> str:
    return "| " + " | ".join(_escape_md(value) for value in values) + " |"


def _escape_md(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


if __name__ == "__main__":
    raise SystemExit(main())
