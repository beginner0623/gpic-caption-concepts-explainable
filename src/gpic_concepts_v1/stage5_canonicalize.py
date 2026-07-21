"""Stage 5 canonicalization.

Stage 5 consumes Stage 4 raw mentions and raw edges. It only applies the
documented v1 canonicalization rules R19-R24:

- object selected-synset canonical surface when GPIC inventory provides it,
  otherwise raw-surface fallback
- attribute synonym lookup
- quantity raw-preserving
- action synonym lookup
- object parent concepts from selected OEWN immediate hypernym evidence
- no action parent concepts until an action-parent lexicon is built
- relation raw-preserving for single-ADP labels, while preserving Stage 4
  preposition MWE relation labels and metadata

It does not create new mentions, rewrite source/target IDs, resolve references,
or repair event roles.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Any

from gpic_concepts_v1.io_jsonl import iter_jsonl, open_text, to_jsonable, write_jsonl
from gpic_concepts_v1.runtime_memory import MemorySafetyConfig, ProgressWriter
from gpic_concepts_v1.schema import (
    CanonicalEdge,
    CanonicalMention,
    JsonObject,
    MISSING_SOURCE_MENTION_ID,
    MISSING_TARGET_MENTION_ID,
    RawEdge,
    RawMention,
)


OBJECT_CANON_RULE_ID = "R19"
ATTRIBUTE_CANON_RULE_ID = "R20"
QUANTITY_CANON_RULE_ID = "R21"
ACTION_CANON_RULE_ID = "R22"
PARENT_RULE_ID = "R23"
RELATION_CANON_RULE_ID = "R24"


@dataclass(frozen=True, slots=True)
class LexiconValue:
    value: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class Stage5Lexicons:
    object_synonyms: Mapping[str, LexiconValue]
    object_parents: Mapping[str, tuple[LexiconValue, ...]]
    attribute_synonyms: Mapping[str, LexiconValue]
    attribute_types: Mapping[str, LexiconValue]
    action_synonyms: Mapping[str, LexiconValue]
    action_types: Mapping[str, LexiconValue]


@dataclass(slots=True)
class CanonicalizationResult:
    canonical_mentions: list[CanonicalMention]
    canonical_edges: list[CanonicalEdge]


def load_stage5_lexicons(lexicon_dir: str | Path) -> Stage5Lexicons:
    """Load explicit Stage 5 TSV lexicons."""
    root = Path(lexicon_dir)
    return Stage5Lexicons(
        object_synonyms=_load_value_map(root / "object_synonyms.tsv", "raw", "canonical"),
        object_parents=_load_multi_value_map(root / "object_parents.tsv", "canonical", "parent"),
        attribute_synonyms=_load_value_map(root / "attribute_synonyms.tsv", "raw", "canonical"),
        attribute_types=_load_value_map(root / "attribute_types.tsv", "canonical", "attribute_type"),
        action_synonyms=_load_value_map(root / "action_synonyms.tsv", "raw", "canonical"),
        action_types=_load_value_map(root / "action_types.tsv", "canonical", "action_type"),
    )


def canonicalize_raw_graph(
    raw_mentions: Sequence[Mapping[str, Any] | RawMention],
    raw_edges: Sequence[Mapping[str, Any] | RawEdge],
    *,
    lexicons: Stage5Lexicons,
) -> CanonicalizationResult:
    """Canonicalize raw Stage 4 mentions and edges without changing graph shape."""
    raw_mention_records = [_coerce_raw_mention(record) for record in raw_mentions]
    raw_edge_records = [_coerce_raw_edge(record) for record in raw_edges]

    canonical_mentions = [
        _canonicalize_mention(raw_mention, lexicons=lexicons)
        for raw_mention in raw_mention_records
    ]
    canonical_by_key = {
        (mention.caption_id, mention.mention_id): mention
        for mention in canonical_mentions
    }
    canonical_edges = [
        _canonicalize_edge(raw_edge, canonical_by_key=canonical_by_key)
        for raw_edge in raw_edge_records
    ]

    return CanonicalizationResult(
        canonical_mentions=canonical_mentions,
        canonical_edges=canonical_edges,
    )


def run_stage5_canonicalize(
    raw_mentions_path: str | Path,
    raw_edges_path: str | Path,
    *,
    lexicon_dir: str | Path,
    canonical_mentions_path: str | Path,
    canonical_edges_path: str | Path,
    summary_path: str | Path | None = None,
    max_rss_gib: float | None = None,
    memory_limit_gib: float | None = None,
    rss_limit_fraction: float = 0.75,
    rss_reserve_gib: float = 16.0,
    progress_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run Stage 5 over Stage 4 JSONL files."""
    lexicons = load_stage5_lexicons(lexicon_dir)
    canonical_mentions_output = Path(canonical_mentions_path)
    canonical_edges_output = Path(canonical_edges_path)
    canonical_mentions_output.parent.mkdir(parents=True, exist_ok=True)
    canonical_edges_output.parent.mkdir(parents=True, exist_ok=True)
    memory_config = MemorySafetyConfig(
        max_rss_gib=max_rss_gib,
        memory_limit_gib=memory_limit_gib,
        rss_limit_fraction=rss_limit_fraction,
        rss_reserve_gib=rss_reserve_gib,
    )
    progress = ProgressWriter(
        progress_path,
        stage_name="stage5",
        memory_config=memory_config,
    )
    canonical_by_key: dict[tuple[str, str], CanonicalMention] = {}
    mention_counts: Counter[str] = Counter()
    edge_counts: Counter[str] = Counter()
    canonical_source_counts: Counter[str] = Counter()
    parent_filled_counts: Counter[str] = Counter()
    canonical_mention_total = 0
    canonical_edge_total = 0
    progress.write(
        status="running",
        phase="stage5_canonicalize_mentions",
        note="started",
        metrics={
            "canonical_mention_total": canonical_mention_total,
            "canonical_edge_total": canonical_edge_total,
            "mention_type_counts": dict(sorted(mention_counts.items())),
            "edge_type_counts": dict(sorted(edge_counts.items())),
        },
        outputs={
            "canonical_mentions": canonical_mentions_output,
            "canonical_edges": canonical_edges_output,
        },
    )

    compact_encoder = json.JSONEncoder(
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode

    try:
        with open_text(canonical_mentions_output, "wt") as handle:
            for raw_record in iter_jsonl(raw_mentions_path):
                progress.check_memory(
                    phase="stage5_canonicalize_mentions",
                    metrics={"canonical_mention_total": canonical_mention_total},
                )
                raw_mention = _coerce_raw_mention(raw_record)
                mention = _canonicalize_mention(raw_mention, lexicons=lexicons)
                handle.write(compact_encoder(to_jsonable(mention)))
                handle.write("\n")
                canonical_by_key[(mention.caption_id, mention.mention_id)] = mention
                canonical_mention_total += 1
                mention_counts[mention.mention_type] += 1
                canonical_source_counts[mention.canonical_source] += 1
                parent_filled_counts[
                    "with_parent" if mention.parent_concepts else "without_parent"
                ] += 1
                if canonical_mention_total % 1000 == 0:
                    progress.write(
                        status="running",
                        phase="stage5_canonicalize_mentions",
                        note="canonicalizing_mentions",
                        metrics={
                            "canonical_mention_total": canonical_mention_total,
                            "canonical_edge_total": canonical_edge_total,
                            "mention_type_counts": dict(sorted(mention_counts.items())),
                            "edge_type_counts": dict(sorted(edge_counts.items())),
                        },
                        outputs={
                            "canonical_mentions": canonical_mentions_output,
                            "canonical_edges": canonical_edges_output,
                        },
                    )
        progress.write(
            status="running",
            phase="stage5_canonicalize_edges",
            note="mentions_complete",
            metrics={
                "canonical_mention_total": canonical_mention_total,
                "canonical_edge_total": canonical_edge_total,
                "mention_type_counts": dict(sorted(mention_counts.items())),
                "edge_type_counts": dict(sorted(edge_counts.items())),
            },
            outputs={
                "canonical_mentions": canonical_mentions_output,
                "canonical_edges": canonical_edges_output,
            },
        )
        with open_text(canonical_edges_output, "wt") as handle:
            for raw_record in iter_jsonl(raw_edges_path):
                progress.check_memory(
                    phase="stage5_canonicalize_edges",
                    metrics={"canonical_edge_total": canonical_edge_total},
                )
                raw_edge = _coerce_raw_edge(raw_record)
                edge = _canonicalize_edge(raw_edge, canonical_by_key=canonical_by_key)
                handle.write(compact_encoder(to_jsonable(edge)))
                handle.write("\n")
                canonical_edge_total += 1
                edge_counts[edge.edge_type] += 1
                if canonical_edge_total % 1000 == 0:
                    progress.write(
                        status="running",
                        phase="stage5_canonicalize_edges",
                        note="canonicalizing_edges",
                        metrics={
                            "canonical_mention_total": canonical_mention_total,
                            "canonical_edge_total": canonical_edge_total,
                            "mention_type_counts": dict(sorted(mention_counts.items())),
                            "edge_type_counts": dict(sorted(edge_counts.items())),
                        },
                        outputs={
                            "canonical_mentions": canonical_mentions_output,
                            "canonical_edges": canonical_edges_output,
                        },
                    )
    except Exception as exc:
        progress.write(
            status="failed",
            phase="stage5_canonicalize",
            note=f"{type(exc).__name__}: {exc}",
            metrics={
                "canonical_mention_total": canonical_mention_total,
                "canonical_edge_total": canonical_edge_total,
                "mention_type_counts": dict(sorted(mention_counts.items())),
                "edge_type_counts": dict(sorted(edge_counts.items())),
            },
            outputs={
                "canonical_mentions": canonical_mentions_output,
                "canonical_edges": canonical_edges_output,
            },
        )
        raise

    summary = {
        "raw_mentions_path": str(raw_mentions_path),
        "raw_edges_path": str(raw_edges_path),
        "canonical_mentions_path": str(canonical_mentions_output),
        "canonical_edges_path": str(canonical_edges_output),
        "canonical_mention_total": canonical_mention_total,
        "canonical_edge_total": canonical_edge_total,
        "mention_type_counts": dict(sorted(mention_counts.items())),
        "edge_type_counts": dict(sorted(edge_counts.items())),
        "canonical_source_counts": dict(sorted(canonical_source_counts.items())),
        "parent_filled_counts": dict(sorted(parent_filled_counts.items())),
        "memory_limit_gib": memory_config.resolved_memory_limit_gib,
        "memory_limit_source": memory_config.memory_limit_source,
        "rss_limit_fraction": rss_limit_fraction,
        "rss_reserve_gib": rss_reserve_gib,
        "max_rss_gib": memory_config.effective_max_rss_gib,
    }
    if summary_path is not None:
        write_jsonl(summary_path, [summary])
    progress.write(
        status="complete",
        phase="stage5_complete",
        note="complete",
        metrics={
            "canonical_mention_total": canonical_mention_total,
            "canonical_edge_total": canonical_edge_total,
            "mention_type_counts": dict(sorted(mention_counts.items())),
            "edge_type_counts": dict(sorted(edge_counts.items())),
        },
        outputs={
            "canonical_mentions": canonical_mentions_output,
            "canonical_edges": canonical_edges_output,
        },
        summary=summary,
    )
    return summary


def _canonicalize_mention(
    raw: RawMention,
    *,
    lexicons: Stage5Lexicons,
) -> CanonicalMention:
    raw_label = _raw_label(raw)
    detail: JsonObject = {}

    if raw.mention_type == "object":
        canonical_rule_id = OBJECT_CANON_RULE_ID
        canonical = raw_label
        canonical_source = "raw_fallback"
        inventory_canonical = raw.source_detail.get("canonical_surface")
        if isinstance(inventory_canonical, str) and inventory_canonical:
            canonical = inventory_canonical
            canonical_source = "gpic_observed_inventory"
            detail["canonical_selection_tag"] = raw.source_detail.get(
                "canonical_selection_tag",
                "",
            )
            canonical_label_key = raw.source_detail.get("canonical_label_key")
            if isinstance(canonical_label_key, str) and canonical_label_key:
                detail["canonical_label_key"] = canonical_label_key
        canonical_candidate_lemmas = _source_detail_list(
            raw.source_detail,
            "canonical_candidate_lemmas",
        )
        if canonical_candidate_lemmas:
            detail["canonical_candidate_lemmas"] = canonical_candidate_lemmas
        canonical_candidate_counts = raw.source_detail.get("canonical_candidate_lemma_counts")
        if isinstance(canonical_candidate_counts, str) and canonical_candidate_counts:
            detail["canonical_candidate_lemma_counts"] = canonical_candidate_counts
        ngram_surfaces = _source_detail_list(
            raw.source_detail,
            "google_ngram_candidate_surfaces",
        )
        if ngram_surfaces:
            detail["google_ngram_candidate_surfaces"] = ngram_surfaces
        ngram_frequencies = raw.source_detail.get("google_ngram_candidate_mean_frequencies")
        if isinstance(ngram_frequencies, str) and ngram_frequencies:
            detail["google_ngram_candidate_mean_frequencies"] = ngram_frequencies
        parent_synset_ids = _source_detail_list(raw.source_detail, "parent_oewn_synsets")
        parent_source = "selected_oewn_hypernym" if parent_synset_ids else None
        selected_synset = raw.source_detail.get("selected_oewn_synset")
        if isinstance(selected_synset, str) and selected_synset:
            detail["selected_oewn_synset"] = selected_synset
            selected_lexfile = raw.source_detail.get("selected_oewn_lexfile")
            if isinstance(selected_lexfile, str) and selected_lexfile:
                detail["selected_oewn_lexfile"] = selected_lexfile
        parent_lexfiles = _source_detail_list(raw.source_detail, "parent_oewn_lexfiles")
        parent_lemmas = _source_detail_list(raw.source_detail, "parent_lemmas")
        parent_concepts = _parent_display_labels(parent_lemmas, parent_synset_ids)
        parent_selection_tag = raw.source_detail.get("parent_selection_tag")
        if parent_synset_ids:
            detail["parent_oewn_synsets"] = parent_synset_ids
        if parent_lexfiles:
            detail["parent_oewn_lexfiles"] = parent_lexfiles
        if parent_lemmas:
            detail["parent_lemmas"] = parent_lemmas
        if isinstance(parent_selection_tag, str) and parent_selection_tag:
            detail["parent_selection_tag"] = parent_selection_tag
    elif raw.mention_type == "attribute":
        canonical_rule_id = ATTRIBUTE_CANON_RULE_ID
        canonical, canonical_source = _lookup_or_fallback(
            raw_label,
            lexicons.attribute_synonyms,
        )
        parent_concepts = []
        parent_source = None
    elif raw.mention_type == "quantity":
        canonical_rule_id = QUANTITY_CANON_RULE_ID
        canonical = raw_label
        canonical_source = "raw_fallback"
        parent_concepts = []
        parent_source = None
    elif raw.mention_type == "action":
        canonical_rule_id = ACTION_CANON_RULE_ID
        canonical, canonical_source = _lookup_or_fallback(
            raw_label,
            lexicons.action_synonyms,
        )
        parent_concepts = []
        parent_source = None
    else:
        raise ValueError(f"unsupported mention type: {raw.mention_type}")

    return CanonicalMention(
        caption_id=raw.caption_id,
        mention_id=raw.mention_id,
        mention_type=raw.mention_type,
        raw_text=raw.text,
        raw_lemma=raw.lemma,
        canonical=canonical,
        parent_concepts=parent_concepts,
        canonical_rule_id=canonical_rule_id,
        parent_rule_id=PARENT_RULE_ID if parent_concepts else None,
        canonical_source=canonical_source,  # type: ignore[arg-type]
        parent_source=parent_source,  # type: ignore[arg-type]
        confidence="high" if canonical_source != "raw_fallback" else "medium",
        canonical_detail=detail,
    )


def _canonicalize_edge(
    raw: RawEdge,
    *,
    canonical_by_key: Mapping[tuple[str, str], CanonicalMention],
) -> CanonicalEdge:
    source = _canonical_mention_or_missing(
        canonical_by_key,
        raw.caption_id,
        raw.source_mention_id,
    )
    target = _canonical_mention_or_missing(
        canonical_by_key,
        raw.caption_id,
        raw.target_mention_id,
    )
    relation_like = raw.edge_type in {"relation", "ambiguous_relation_candidate"}
    canonical_rule_id = RELATION_CANON_RULE_ID if relation_like else None
    detail = dict(raw.source_detail)
    if relation_like:
        detail["relation_canonical_policy"] = (
            "preposition_mwe_preserved"
            if detail.get("relation_source") == "preposition_mwe"
            else "single_adp_raw_preserving"
        )
    if source is None:
        detail.setdefault("source_endpoint_status", "source_missing")
    if target is None:
        detail.setdefault("target_endpoint_status", "target_missing")

    return CanonicalEdge(
        caption_id=raw.caption_id,
        edge_id=raw.edge_id,
        edge_type=raw.edge_type,
        source_mention_id=raw.source_mention_id,
        target_mention_id=raw.target_mention_id,
        label=raw.label,
        canonical_label=raw.label,
        source_canonical=source.canonical if source is not None else "source_missing",
        target_canonical=target.canonical if target is not None else "target_missing",
        rule_id=raw.rule_id,
        canonical_rule_id=canonical_rule_id,
        confidence=raw.confidence,
        canonical_detail=detail,
    )


def _lookup_or_fallback(
    raw_label: str,
    lookup: Mapping[str, LexiconValue],
) -> tuple[str, str]:
    entry = lookup.get(_key(raw_label))
    if entry is not None:
        return entry.value, "lexicon"
    return raw_label, "raw_fallback"


def _lookup_parents(
    canonical: str,
    lookup: Mapping[str, tuple[LexiconValue, ...]],
) -> tuple[list[str], str | None]:
    entries = lookup.get(_key(canonical), ())
    if not entries:
        return [], None
    return [entry.value for entry in entries], "lexicon"


def _source_detail_list(source_detail: Mapping[str, Any], key: str) -> list[str]:
    value = source_detail.get(key)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    if isinstance(value, tuple):
        return [item for item in value if isinstance(item, str) and item]
    if isinstance(value, str) and value:
        return [item for item in value.split("|") if item]
    return []


def _parent_display_labels(parent_lemmas: Sequence[str], parent_synset_ids: Sequence[str]) -> list[str]:
    labels: list[str] = []
    for value in parent_lemmas:
        _, separator, label = value.partition(":")
        display = label if separator else value
        display = "; ".join(part.strip() for part in display.split(";") if part.strip())
        if display:
            labels.append(display)
    return labels if labels else list(parent_synset_ids)


def _raw_label(raw: RawMention) -> str:
    label = raw.text.strip().lower()
    if not label:
        raise ValueError(f"raw mention {raw.mention_id} has no label")
    return label


def _key(value: str) -> str:
    return value.strip().lower()


def _load_value_map(path: Path, key_column: str, value_column: str) -> dict[str, LexiconValue]:
    rows = _read_tsv(path)
    values: dict[str, LexiconValue] = {}
    for row in rows:
        key = _key(_require_cell(row, key_column, path))
        value = _require_cell(row, value_column, path).strip()
        if key == "" or value == "":
            continue
        if key in values:
            raise ValueError(f"duplicate key {key!r} in {path}")
        values[key] = LexiconValue(value=value, source=_optional_cell(row, "source"))
    return values


def _load_multi_value_map(
    path: Path,
    key_column: str,
    value_column: str,
) -> dict[str, tuple[LexiconValue, ...]]:
    rows = _read_tsv(path)
    values: dict[str, list[LexiconValue]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = _key(_require_cell(row, key_column, path))
        value = _require_cell(row, value_column, path).strip()
        if key == "" or value == "":
            continue
        marker = (key, value)
        if marker in seen:
            raise ValueError(f"duplicate key/value {marker!r} in {path}")
        seen.add(marker)
        values.setdefault(key, []).append(
            LexiconValue(value=value, source=_optional_cell(row, "source")),
        )
    return {key: tuple(items) for key, items in values.items()}


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            return []
        return [dict(row) for row in reader]


def _require_cell(row: Mapping[str, str], column: str, path: Path) -> str:
    value = row.get(column)
    if value is None:
        raise ValueError(f"{path} is missing required column {column!r}")
    return value


def _optional_cell(row: Mapping[str, str], column: str) -> str | None:
    value = row.get(column)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _coerce_raw_mention(record: Mapping[str, Any] | RawMention) -> RawMention:
    if isinstance(record, RawMention):
        return record
    return RawMention(**dict(record))


def _coerce_raw_edge(record: Mapping[str, Any] | RawEdge) -> RawEdge:
    if isinstance(record, RawEdge):
        return record
    return RawEdge(**dict(record))


def _require_canonical_mention(
    canonical_by_key: Mapping[tuple[str, str], CanonicalMention],
    caption_id: str,
    mention_id: str,
) -> CanonicalMention:
    mention = canonical_by_key.get((caption_id, mention_id))
    if mention is None:
        raise ValueError(
            f"edge endpoint {(caption_id, mention_id)!r} has no canonical mention",
        )
    return mention


def _canonical_mention_or_missing(
    canonical_by_key: Mapping[tuple[str, str], CanonicalMention],
    caption_id: str,
    mention_id: str,
) -> CanonicalMention | None:
    if mention_id in {MISSING_SOURCE_MENTION_ID, MISSING_TARGET_MENTION_ID}:
        return None
    return _require_canonical_mention(canonical_by_key, caption_id, mention_id)
