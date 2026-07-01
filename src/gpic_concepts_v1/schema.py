"""Output records for the v1 explainable caption-to-concept baseline.

This module defines data containers only. It does not perform extraction,
canonicalization, repair, or counting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Literal, TypeAlias


PIPELINE_VERSION = "v1_explainable"

CaptionShape: TypeAlias = Literal["sentence", "tag_list"]
Confidence: TypeAlias = Literal["high", "medium", "low"]
MentionType: TypeAlias = Literal["object", "attribute", "quantity", "action"]
EdgeType: TypeAlias = Literal["has_attribute", "has_quantity", "event_role", "relation"]
FactType: TypeAlias = Literal[
    "entity_exists",
    "has_attribute",
    "has_quantity",
    "action_event",
    "event_role",
    "relation",
    "object_pair_in_caption",
]
CanonicalSource: TypeAlias = Literal["lexicon", "raw_fallback"]
ParentSource: TypeAlias = Literal["lexicon"]
JsonObject: TypeAlias = dict[str, Any]


CAPTION_SHAPES = frozenset(("sentence", "tag_list"))
CONFIDENCES = frozenset(("high", "medium", "low"))
MENTION_TYPES = frozenset(("object", "attribute", "quantity", "action"))
EDGE_TYPES = frozenset(("has_attribute", "has_quantity", "event_role", "relation"))
FACT_TYPES = frozenset(
    (
        "entity_exists",
        "has_attribute",
        "has_quantity",
        "action_event",
        "event_role",
        "relation",
        "object_pair_in_caption",
    )
)
CANONICAL_SOURCES = frozenset(("lexicon", "raw_fallback"))
PARENT_SOURCES = frozenset(("lexicon",))


def make_local_id(prefix: Literal["m", "e", "f"], index: int) -> str:
    """Return a caption-local id such as m0, e0, or f0."""
    if prefix not in {"m", "e", "f"}:
        raise ValueError(f"unsupported id prefix: {prefix!r}")
    if not isinstance(index, int) or index < 0:
        raise ValueError(f"index must be a non-negative integer: {index!r}")
    return f"{prefix}{index}"


def make_global_id(caption_id: str, local_id: str) -> str:
    """Return a globally unique id using the documented caption-local id form."""
    _require_text("caption_id", caption_id)
    _require_text("local_id", local_id)
    return f"{caption_id}:{local_id}"


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{name} must be a non-empty string")


def _require_optional_text(name: str, value: str | None) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{name} must be a string or None")


def _require_choice(name: str, value: str, choices: frozenset[str]) -> None:
    if value not in choices:
        expected = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of {{{expected}}}: {value!r}")


def _require_bool(name: str, value: bool) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")


def _require_stage(name: str, value: int, expected: int) -> None:
    if value != expected:
        raise ValueError(f"{name} must be {expected}: {value!r}")


def _require_string_list(name: str, value: list[str]) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")


def _require_json_object(name: str, value: JsonObject) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dict")


def _require_local_id(name: str, value: str, prefix: str) -> None:
    _require_text(name, value)
    suffix = value[len(prefix) :]
    if not value.startswith(prefix) or not suffix.isdigit():
        raise ValueError(f"{name} must look like {prefix}0, {prefix}1, ...: {value!r}")


def _require_optional_int(name: str, value: int | None) -> None:
    if value is not None and not isinstance(value, int):
        raise ValueError(f"{name} must be an integer or None")


def _require_span(
    start_name: str,
    start: int | None,
    end_name: str,
    end: int | None,
) -> None:
    _require_optional_int(start_name, start)
    _require_optional_int(end_name, end)
    if start is None or end is None:
        return
    if start < 0 or end < 0 or end < start:
        raise ValueError(f"invalid span: {start_name}={start!r}, {end_name}={end!r}")


@dataclass(slots=True)
class JsonRecord:
    """Base mixin for JSONL-friendly records."""

    def to_dict(self) -> JsonObject:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass(slots=True)
class CaptionRecord(JsonRecord):
    caption_id: str
    caption: str
    caption_shape: CaptionShape
    skipped: bool
    skip_reason: str | None
    pipeline_version: str = PIPELINE_VERSION
    rule_ids: list[str] = field(default_factory=list)
    meta: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("caption_id", self.caption_id)
        if not isinstance(self.caption, str):
            raise ValueError("caption must be a string")
        _require_choice("caption_shape", self.caption_shape, CAPTION_SHAPES)
        _require_bool("skipped", self.skipped)
        _require_optional_text("skip_reason", self.skip_reason)
        _require_text("pipeline_version", self.pipeline_version)
        _require_string_list("rule_ids", self.rule_ids)
        _require_json_object("meta", self.meta)
        if self.caption_shape == "tag_list":
            if not self.skipped or self.skip_reason != "tag_list_deferred":
                raise ValueError("tag_list captions must be skipped with tag_list_deferred")


@dataclass(slots=True)
class RawMention(JsonRecord):
    caption_id: str
    mention_id: str
    mention_type: MentionType
    text: str
    lemma: str
    rule_id: str
    stage: int = 4
    confidence: Confidence = "high"
    char_start: int | None = None
    char_end: int | None = None
    token_start: int | None = None
    token_end: int | None = None
    source_text: str | None = None
    source_detail: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("caption_id", self.caption_id)
        _require_local_id("mention_id", self.mention_id, "m")
        _require_choice("mention_type", self.mention_type, MENTION_TYPES)
        _require_text("text", self.text)
        _require_text("lemma", self.lemma)
        _require_text("rule_id", self.rule_id)
        _require_stage("stage", self.stage, 4)
        _require_choice("confidence", self.confidence, CONFIDENCES)
        _require_span("char_start", self.char_start, "char_end", self.char_end)
        _require_span("token_start", self.token_start, "token_end", self.token_end)
        _require_optional_text("source_text", self.source_text)
        _require_json_object("source_detail", self.source_detail)


@dataclass(slots=True)
class RawEdge(JsonRecord):
    caption_id: str
    edge_id: str
    edge_type: EdgeType
    source_mention_id: str
    target_mention_id: str
    label: str
    rule_id: str
    stage: int = 4
    confidence: Confidence = "high"
    evidence_text: str | None = None
    source_detail: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("caption_id", self.caption_id)
        _require_local_id("edge_id", self.edge_id, "e")
        _require_choice("edge_type", self.edge_type, EDGE_TYPES)
        _require_local_id("source_mention_id", self.source_mention_id, "m")
        _require_local_id("target_mention_id", self.target_mention_id, "m")
        _require_text("label", self.label)
        _require_text("rule_id", self.rule_id)
        _require_stage("stage", self.stage, 4)
        _require_choice("confidence", self.confidence, CONFIDENCES)
        _require_optional_text("evidence_text", self.evidence_text)
        _require_json_object("source_detail", self.source_detail)


@dataclass(slots=True)
class CanonicalMention(JsonRecord):
    caption_id: str
    mention_id: str
    mention_type: MentionType
    raw_text: str
    raw_lemma: str
    canonical: str
    parent_concepts: list[str]
    canonical_rule_id: str
    parent_rule_id: str | None
    canonical_source: CanonicalSource
    parent_source: ParentSource | None
    confidence: Confidence = "high"
    canonical_detail: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("caption_id", self.caption_id)
        _require_local_id("mention_id", self.mention_id, "m")
        _require_choice("mention_type", self.mention_type, MENTION_TYPES)
        _require_text("raw_text", self.raw_text)
        _require_text("raw_lemma", self.raw_lemma)
        _require_text("canonical", self.canonical)
        _require_string_list("parent_concepts", self.parent_concepts)
        _require_text("canonical_rule_id", self.canonical_rule_id)
        _require_optional_text("parent_rule_id", self.parent_rule_id)
        _require_choice("canonical_source", self.canonical_source, CANONICAL_SOURCES)
        if self.parent_source is not None:
            _require_choice("parent_source", self.parent_source, PARENT_SOURCES)
        _require_choice("confidence", self.confidence, CONFIDENCES)
        _require_json_object("canonical_detail", self.canonical_detail)


@dataclass(slots=True)
class CanonicalEdge(JsonRecord):
    caption_id: str
    edge_id: str
    edge_type: EdgeType
    source_mention_id: str
    target_mention_id: str
    label: str
    canonical_label: str
    source_canonical: str
    target_canonical: str
    rule_id: str
    canonical_rule_id: str | None
    confidence: Confidence = "high"

    def __post_init__(self) -> None:
        _require_text("caption_id", self.caption_id)
        _require_local_id("edge_id", self.edge_id, "e")
        _require_choice("edge_type", self.edge_type, EDGE_TYPES)
        _require_local_id("source_mention_id", self.source_mention_id, "m")
        _require_local_id("target_mention_id", self.target_mention_id, "m")
        _require_text("label", self.label)
        _require_text("canonical_label", self.canonical_label)
        _require_text("source_canonical", self.source_canonical)
        _require_text("target_canonical", self.target_canonical)
        _require_text("rule_id", self.rule_id)
        _require_optional_text("canonical_rule_id", self.canonical_rule_id)
        _require_choice("confidence", self.confidence, CONFIDENCES)


@dataclass(slots=True)
class FactRow(JsonRecord):
    caption_id: str
    fact_id: str
    fact_type: FactType
    count_key: str
    rule_ids: list[str]
    source_mention_ids: list[str]
    source_edge_ids: list[str]
    values: JsonObject

    def __post_init__(self) -> None:
        _require_text("caption_id", self.caption_id)
        _require_local_id("fact_id", self.fact_id, "f")
        _require_choice("fact_type", self.fact_type, FACT_TYPES)
        _require_text("count_key", self.count_key)
        _require_string_list("rule_ids", self.rule_ids)
        _require_string_list("source_mention_ids", self.source_mention_ids)
        _require_string_list("source_edge_ids", self.source_edge_ids)
        for mention_id in self.source_mention_ids:
            _require_local_id("source_mention_ids item", mention_id, "m")
        for edge_id in self.source_edge_ids:
            _require_local_id("source_edge_ids item", edge_id, "e")
        _require_json_object("values", self.values)


@dataclass(slots=True)
class CountRow(JsonRecord):
    count_key: str
    count: int
    caption_count: int
    example_caption_ids: list[str] = field(default_factory=list)
    raw_variants: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    values: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("count_key", self.count_key)
        if not isinstance(self.count, int) or self.count < 0:
            raise ValueError("count must be a non-negative integer")
        if not isinstance(self.caption_count, int) or self.caption_count < 0:
            raise ValueError("caption_count must be a non-negative integer")
        _require_string_list("example_caption_ids", self.example_caption_ids)
        _require_string_list("raw_variants", self.raw_variants)
        _require_string_list("rule_ids", self.rule_ids)
        _require_json_object("values", self.values)
