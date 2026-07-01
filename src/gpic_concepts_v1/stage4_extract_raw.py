"""Stage 4 raw concept extraction.

Stage 4 consumes Stage 3 annotation records and creates raw mentions/edges
using only the documented v1 extraction rules R12-R18.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import JsonObject, RawEdge, RawMention, make_local_id

try:  # pragma: no cover - exercised when spaCy is installed.
    from spacy.tokens import Doc, Token
except ModuleNotFoundError:  # pragma: no cover - keeps non-spaCy tests importable.
    Doc = Any  # type: ignore[misc,assignment]
    Token = Any  # type: ignore[misc,assignment]


OBJECT_RULE_ID = "R12"
ATTRIBUTE_RULE_ID = "R13"
QUANTITY_RULE_ID = "R14"
ACTION_RULE_ID = "R15"
AGENT_RULE_ID = "R16"
PATIENT_RULE_ID = "R17"
RELATION_RULE_ID = "R18"

ATTRIBUTE_MODIFIER_DEPS = frozenset(("amod", "compound"))
QUANTITY_MODIFIER_DEPS = frozenset(("nummod",))
PATIENT_DEPS = frozenset(("obj", "dobj"))


@dataclass(slots=True)
class RawExtractionResult:
    raw_mentions: list[RawMention]
    raw_edges: list[RawEdge]


class _RawBuilder:
    def __init__(self, caption_id: str) -> None:
        self.caption_id = caption_id
        self.raw_mentions: list[RawMention] = []
        self.raw_edges: list[RawEdge] = []
        self.object_by_token: dict[int, str] = {}
        self.action_by_token: dict[int, str] = {}

    def add_mention(
        self,
        *,
        mention_type: str,
        text: str,
        lemma: str,
        rule_id: str,
        char_start: int | None,
        char_end: int | None,
        token_start: int | None,
        token_end: int | None,
        source_text: str | None,
        source_detail: Mapping[str, Any] | None = None,
    ) -> str:
        mention_id = make_local_id("m", len(self.raw_mentions))
        mention = RawMention(
            caption_id=self.caption_id,
            mention_id=mention_id,
            mention_type=mention_type,  # type: ignore[arg-type]
            text=text,
            lemma=lemma,
            rule_id=rule_id,
            char_start=char_start,
            char_end=char_end,
            token_start=token_start,
            token_end=token_end,
            source_text=source_text,
            source_detail=dict(source_detail or {}),
        )
        self.raw_mentions.append(mention)
        return mention_id

    def add_edge(
        self,
        *,
        edge_type: str,
        source_mention_id: str,
        target_mention_id: str,
        label: str,
        rule_id: str,
        evidence_text: str | None,
        source_detail: Mapping[str, Any] | None = None,
    ) -> str:
        edge_id = make_local_id("e", len(self.raw_edges))
        edge = RawEdge(
            caption_id=self.caption_id,
            edge_id=edge_id,
            edge_type=edge_type,  # type: ignore[arg-type]
            source_mention_id=source_mention_id,
            target_mention_id=target_mention_id,
            label=label,
            rule_id=rule_id,
            evidence_text=evidence_text,
            source_detail=dict(source_detail or {}),
        )
        self.raw_edges.append(edge)
        return edge_id


def extract_raw_concepts_from_stage3_record(
    stage3_record: Mapping[str, Any],
) -> RawExtractionResult:
    """Extract raw mentions and edges from one Stage 3 annotation record."""
    caption_id = _require_text(stage3_record, "caption_id")
    tokens = _require_list(stage3_record, "tokens")
    noun_chunks = _require_list(stage3_record, "noun_chunks")

    token_by_i = {_require_int(token, "i"): token for token in tokens}
    children_by_head = _build_children_by_head(tokens)
    builder = _RawBuilder(caption_id)

    _extract_objects_and_chunk_modifiers(
        builder,
        noun_chunks=noun_chunks,
        token_by_i=token_by_i,
    )
    _extract_actions(builder, tokens=tokens)
    _extract_event_roles(
        builder,
        tokens=tokens,
        children_by_head=children_by_head,
    )
    _extract_relations(
        builder,
        tokens=tokens,
        children_by_head=children_by_head,
    )

    return RawExtractionResult(
        raw_mentions=builder.raw_mentions,
        raw_edges=builder.raw_edges,
    )


def extract_raw_concepts_from_doc(caption_id: str, doc: Doc) -> RawExtractionResult:
    """Extract raw mentions and edges directly from an annotated spaCy Doc."""
    builder = _RawBuilder(caption_id)
    children_by_head = _build_doc_children_by_head(doc)

    _extract_doc_objects_and_chunk_modifiers(builder, doc=doc)
    _extract_doc_actions(builder, doc=doc)
    _extract_doc_event_roles(
        builder,
        doc=doc,
        children_by_head=children_by_head,
    )
    _extract_doc_relations(
        builder,
        doc=doc,
        children_by_head=children_by_head,
    )

    return RawExtractionResult(
        raw_mentions=builder.raw_mentions,
        raw_edges=builder.raw_edges,
    )


def run_stage4_extract_raw(
    input_path: str | Path,
    *,
    raw_mentions_path: str | Path,
    raw_edges_path: str | Path,
    summary_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run Stage 4 over Stage 3 JSONL records."""
    all_mentions: list[RawMention] = []
    all_edges: list[RawEdge] = []
    mention_counts: Counter[str] = Counter()
    edge_counts: Counter[str] = Counter()
    total = 0

    for index, record in enumerate(iter_jsonl(input_path)):
        if limit is not None and index >= limit:
            break
        result = extract_raw_concepts_from_stage3_record(record)
        total += 1
        all_mentions.extend(result.raw_mentions)
        all_edges.extend(result.raw_edges)
        mention_counts.update(mention.mention_type for mention in result.raw_mentions)
        edge_counts.update(edge.edge_type for edge in result.raw_edges)

    write_jsonl(raw_mentions_path, all_mentions)
    write_jsonl(raw_edges_path, all_edges)
    summary = {
        "total": total,
        "raw_mentions_path": str(raw_mentions_path),
        "raw_edges_path": str(raw_edges_path),
        "raw_mention_total": len(all_mentions),
        "raw_edge_total": len(all_edges),
        "mention_type_counts": dict(sorted(mention_counts.items())),
        "edge_type_counts": dict(sorted(edge_counts.items())),
    }
    if summary_path is not None:
        write_jsonl(summary_path, [summary])
    return summary


def _extract_doc_objects_and_chunk_modifiers(
    builder: _RawBuilder,
    *,
    doc: Doc,
) -> None:
    for chunk in doc.noun_chunks:
        root = chunk.root
        root_i = root.i
        if root_i in builder.object_by_token:
            continue

        object_id = builder.add_mention(
            mention_type="object",
            text=root.text,
            lemma=_doc_token_lemma(root),
            rule_id=OBJECT_RULE_ID,
            char_start=root.idx,
            char_end=root.idx + len(root.text),
            token_start=root_i,
            token_end=root_i + 1,
            source_text=chunk.text,
            source_detail=_doc_chunk_root_detail(chunk),
        )
        builder.object_by_token[root_i] = object_id

        for token in chunk:
            token_i = token.i
            if token_i == root_i:
                continue
            if _is_doc_quantity_modifier(token):
                quantity_id = builder.add_mention(
                    mention_type="quantity",
                    text=token.text,
                    lemma=_doc_token_lemma(token),
                    rule_id=QUANTITY_RULE_ID,
                    char_start=token.idx,
                    char_end=token.idx + len(token.text),
                    token_start=token_i,
                    token_end=token_i + 1,
                    source_text=chunk.text,
                    source_detail=_doc_modifier_detail(token, root_i),
                )
                builder.add_edge(
                    edge_type="has_quantity",
                    source_mention_id=object_id,
                    target_mention_id=quantity_id,
                    label="has_quantity",
                    rule_id=QUANTITY_RULE_ID,
                    evidence_text=chunk.text,
                    source_detail={"root_i": root_i, "modifier_i": token_i},
                )
            elif _is_doc_attribute_modifier(token):
                attribute_id = builder.add_mention(
                    mention_type="attribute",
                    text=token.text,
                    lemma=_doc_token_lemma(token),
                    rule_id=ATTRIBUTE_RULE_ID,
                    char_start=token.idx,
                    char_end=token.idx + len(token.text),
                    token_start=token_i,
                    token_end=token_i + 1,
                    source_text=chunk.text,
                    source_detail=_doc_modifier_detail(token, root_i),
                )
                builder.add_edge(
                    edge_type="has_attribute",
                    source_mention_id=object_id,
                    target_mention_id=attribute_id,
                    label="has_attribute",
                    rule_id=ATTRIBUTE_RULE_ID,
                    evidence_text=chunk.text,
                    source_detail={"root_i": root_i, "modifier_i": token_i},
                )


def _extract_doc_actions(
    builder: _RawBuilder,
    *,
    doc: Doc,
) -> None:
    for token in doc:
        if token.pos_ != "VERB":
            continue
        action_id = builder.add_mention(
            mention_type="action",
            text=token.text,
            lemma=_doc_token_lemma(token),
            rule_id=ACTION_RULE_ID,
            char_start=token.idx,
            char_end=token.idx + len(token.text),
            token_start=token.i,
            token_end=token.i + 1,
            source_text=token.text,
            source_detail=_doc_token_detail(token),
        )
        builder.action_by_token[token.i] = action_id


def _extract_doc_event_roles(
    builder: _RawBuilder,
    *,
    doc: Doc,
    children_by_head: Mapping[int, Sequence[Token]],
) -> None:
    for token in doc:
        action_id = builder.action_by_token.get(token.i)
        if action_id is None:
            continue
        for child in children_by_head.get(token.i, ()):
            target_id = builder.object_by_token.get(child.i)
            if target_id is None:
                continue
            if child.dep_ == "nsubj":
                builder.add_edge(
                    edge_type="event_role",
                    source_mention_id=action_id,
                    target_mention_id=target_id,
                    label="agent",
                    rule_id=AGENT_RULE_ID,
                    evidence_text=f"{child.text} -> {token.text}",
                    source_detail={"dep": child.dep_, "action_i": token.i, "target_i": child.i},
                )
            elif child.dep_ in PATIENT_DEPS:
                builder.add_edge(
                    edge_type="event_role",
                    source_mention_id=action_id,
                    target_mention_id=target_id,
                    label="patient",
                    rule_id=PATIENT_RULE_ID,
                    evidence_text=f"{token.text} -> {child.text}",
                    source_detail={"dep": child.dep_, "action_i": token.i, "target_i": child.i},
                )


def _extract_doc_relations(
    builder: _RawBuilder,
    *,
    doc: Doc,
    children_by_head: Mapping[int, Sequence[Token]],
) -> None:
    for token in doc:
        if token.pos_ != "ADP":
            continue
        source_id = builder.object_by_token.get(token.head.i)
        if source_id is None:
            continue
        for child in children_by_head.get(token.i, ()):
            if child.dep_ != "pobj":
                continue
            target_id = builder.object_by_token.get(child.i)
            if target_id is None:
                continue
            builder.add_edge(
                edge_type="relation",
                source_mention_id=source_id,
                target_mention_id=target_id,
                label=_doc_token_lemma(token),
                rule_id=RELATION_RULE_ID,
                evidence_text=f"{token.text} -> {child.text}",
                source_detail={
                    "prep_i": token.i,
                    "source_i": token.head.i,
                    "target_i": child.i,
                    "target_dep": "pobj",
                },
            )


def _extract_objects_and_chunk_modifiers(
    builder: _RawBuilder,
    *,
    noun_chunks: Sequence[Mapping[str, Any]],
    token_by_i: Mapping[int, Mapping[str, Any]],
) -> None:
    for chunk in noun_chunks:
        root_i = _require_int(chunk, "root_i")
        root = token_by_i.get(root_i)
        if root is None or root_i in builder.object_by_token:
            continue

        object_id = builder.add_mention(
            mention_type="object",
            text=_token_text(root),
            lemma=_token_lemma(root),
            rule_id=OBJECT_RULE_ID,
            char_start=_optional_int(root, "char_start"),
            char_end=_optional_int(root, "char_end"),
            token_start=root_i,
            token_end=root_i + 1,
            source_text=_optional_text(chunk, "text"),
            source_detail=_chunk_root_detail(chunk),
        )
        builder.object_by_token[root_i] = object_id

        for token in _chunk_tokens(chunk, token_by_i):
            token_i = _require_int(token, "i")
            if token_i == root_i:
                continue
            if _is_quantity_modifier(token):
                quantity_id = builder.add_mention(
                    mention_type="quantity",
                    text=_token_text(token),
                    lemma=_token_lemma(token),
                    rule_id=QUANTITY_RULE_ID,
                    char_start=_optional_int(token, "char_start"),
                    char_end=_optional_int(token, "char_end"),
                    token_start=token_i,
                    token_end=token_i + 1,
                    source_text=_optional_text(chunk, "text"),
                    source_detail=_modifier_detail(token, root_i),
                )
                builder.add_edge(
                    edge_type="has_quantity",
                    source_mention_id=object_id,
                    target_mention_id=quantity_id,
                    label="has_quantity",
                    rule_id=QUANTITY_RULE_ID,
                    evidence_text=_optional_text(chunk, "text"),
                    source_detail={"root_i": root_i, "modifier_i": token_i},
                )
            elif _is_attribute_modifier(token):
                attribute_id = builder.add_mention(
                    mention_type="attribute",
                    text=_token_text(token),
                    lemma=_token_lemma(token),
                    rule_id=ATTRIBUTE_RULE_ID,
                    char_start=_optional_int(token, "char_start"),
                    char_end=_optional_int(token, "char_end"),
                    token_start=token_i,
                    token_end=token_i + 1,
                    source_text=_optional_text(chunk, "text"),
                    source_detail=_modifier_detail(token, root_i),
                )
                builder.add_edge(
                    edge_type="has_attribute",
                    source_mention_id=object_id,
                    target_mention_id=attribute_id,
                    label="has_attribute",
                    rule_id=ATTRIBUTE_RULE_ID,
                    evidence_text=_optional_text(chunk, "text"),
                    source_detail={"root_i": root_i, "modifier_i": token_i},
                )


def _extract_actions(
    builder: _RawBuilder,
    *,
    tokens: Sequence[Mapping[str, Any]],
) -> None:
    for token in tokens:
        if _optional_text(token, "pos") != "VERB":
            continue
        token_i = _require_int(token, "i")
        action_id = builder.add_mention(
            mention_type="action",
            text=_token_text(token),
            lemma=_token_lemma(token),
            rule_id=ACTION_RULE_ID,
            char_start=_optional_int(token, "char_start"),
            char_end=_optional_int(token, "char_end"),
            token_start=token_i,
            token_end=token_i + 1,
            source_text=_token_text(token),
            source_detail=_token_detail(token),
        )
        builder.action_by_token[token_i] = action_id


def _extract_event_roles(
    builder: _RawBuilder,
    *,
    tokens: Sequence[Mapping[str, Any]],
    children_by_head: Mapping[int, Sequence[Mapping[str, Any]]],
) -> None:
    for token in tokens:
        token_i = _require_int(token, "i")
        action_id = builder.action_by_token.get(token_i)
        if action_id is None:
            continue
        for child in children_by_head.get(token_i, ()):
            child_i = _require_int(child, "i")
            target_id = builder.object_by_token.get(child_i)
            if target_id is None:
                continue
            dep = _optional_text(child, "dep")
            if dep == "nsubj":
                builder.add_edge(
                    edge_type="event_role",
                    source_mention_id=action_id,
                    target_mention_id=target_id,
                    label="agent",
                    rule_id=AGENT_RULE_ID,
                    evidence_text=f"{_token_text(child)} -> {_token_text(token)}",
                    source_detail={"dep": dep, "action_i": token_i, "target_i": child_i},
                )
            elif dep in PATIENT_DEPS:
                builder.add_edge(
                    edge_type="event_role",
                    source_mention_id=action_id,
                    target_mention_id=target_id,
                    label="patient",
                    rule_id=PATIENT_RULE_ID,
                    evidence_text=f"{_token_text(token)} -> {_token_text(child)}",
                    source_detail={"dep": dep, "action_i": token_i, "target_i": child_i},
                )


def _extract_relations(
    builder: _RawBuilder,
    *,
    tokens: Sequence[Mapping[str, Any]],
    children_by_head: Mapping[int, Sequence[Mapping[str, Any]]],
) -> None:
    for token in tokens:
        if _optional_text(token, "pos") != "ADP":
            continue
        prep_i = _require_int(token, "i")
        source_id = builder.object_by_token.get(_require_int(token, "head_i"))
        if source_id is None:
            continue
        for child in children_by_head.get(prep_i, ()):
            if _optional_text(child, "dep") != "pobj":
                continue
            child_i = _require_int(child, "i")
            target_id = builder.object_by_token.get(child_i)
            if target_id is None:
                continue
            builder.add_edge(
                edge_type="relation",
                source_mention_id=source_id,
                target_mention_id=target_id,
                label=_token_lemma(token),
                rule_id=RELATION_RULE_ID,
                evidence_text=f"{_token_text(token)} -> {_token_text(child)}",
                source_detail={
                    "prep_i": prep_i,
                    "source_i": _require_int(token, "head_i"),
                    "target_i": child_i,
                    "target_dep": "pobj",
                },
            )


def _build_children_by_head(
    tokens: Sequence[Mapping[str, Any]],
) -> dict[int, list[Mapping[str, Any]]]:
    children_by_head: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for token in tokens:
        token_i = _require_int(token, "i")
        head_i = _require_int(token, "head_i")
        if token_i != head_i:
            children_by_head[head_i].append(token)
    return children_by_head


def _build_doc_children_by_head(doc: Doc) -> dict[int, list[Token]]:
    children_by_head: dict[int, list[Token]] = defaultdict(list)
    for token in doc:
        if token.i != token.head.i:
            children_by_head[token.head.i].append(token)
    return children_by_head


def _chunk_tokens(
    chunk: Mapping[str, Any],
    token_by_i: Mapping[int, Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    start = _require_int(chunk, "token_start")
    end = _require_int(chunk, "token_end")
    return [token_by_i[i] for i in range(start, end) if i in token_by_i]


def _is_attribute_modifier(token: Mapping[str, Any]) -> bool:
    return _optional_text(token, "dep") in ATTRIBUTE_MODIFIER_DEPS


def _is_quantity_modifier(token: Mapping[str, Any]) -> bool:
    return (
        _optional_text(token, "dep") in QUANTITY_MODIFIER_DEPS
        or _optional_text(token, "pos") == "NUM"
    )


def _is_doc_attribute_modifier(token: Token) -> bool:
    return token.dep_ in ATTRIBUTE_MODIFIER_DEPS


def _is_doc_quantity_modifier(token: Token) -> bool:
    return token.dep_ in QUANTITY_MODIFIER_DEPS or token.pos_ == "NUM"


def _chunk_root_detail(chunk: Mapping[str, Any]) -> JsonObject:
    return {
        "root_i": _optional_int(chunk, "root_i"),
        "root_pos": _optional_text(chunk, "root_pos"),
        "root_tag": _optional_text(chunk, "root_tag"),
        "root_dep": _optional_text(chunk, "root_dep"),
        "root_head_i": _optional_int(chunk, "root_head_i"),
        "root_head_text": _optional_text(chunk, "root_head_text"),
    }


def _modifier_detail(token: Mapping[str, Any], root_i: int) -> JsonObject:
    detail = _token_detail(token)
    detail["root_i"] = root_i
    return detail


def _token_detail(token: Mapping[str, Any]) -> JsonObject:
    return {
        "i": _optional_int(token, "i"),
        "pos": _optional_text(token, "pos"),
        "tag": _optional_text(token, "tag"),
        "dep": _optional_text(token, "dep"),
        "head_i": _optional_int(token, "head_i"),
        "head_text": _optional_text(token, "head_text"),
    }


def _doc_chunk_root_detail(chunk: Any) -> JsonObject:
    return {
        "root_i": chunk.root.i,
        "root_pos": chunk.root.pos_,
        "root_tag": chunk.root.tag_,
        "root_dep": chunk.root.dep_,
        "root_head_i": chunk.root.head.i,
        "root_head_text": chunk.root.head.text,
    }


def _doc_modifier_detail(token: Token, root_i: int) -> JsonObject:
    detail = _doc_token_detail(token)
    detail["root_i"] = root_i
    return detail


def _doc_token_detail(token: Token) -> JsonObject:
    return {
        "i": token.i,
        "pos": token.pos_,
        "tag": token.tag_,
        "dep": token.dep_,
        "head_i": token.head.i,
        "head_text": token.head.text,
    }


def _token_text(token: Mapping[str, Any]) -> str:
    value = _optional_text(token, "text")
    if value is None or value == "":
        raise ValueError("token text must be a non-empty string")
    return value


def _token_lemma(token: Mapping[str, Any]) -> str:
    lemma = _optional_text(token, "lemma")
    if lemma:
        return lemma
    lower = _optional_text(token, "lower")
    if lower:
        return lower
    return _token_text(token).lower()


def _doc_token_lemma(token: Token) -> str:
    if token.lemma_:
        return token.lemma_
    return token.text.lower()


def _require_text(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_int(record: Mapping[str, Any], key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _require_list(record: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = record.get(key)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{key} must be a list of objects")
    return value


def _optional_text(record: Mapping[str, Any], key: str) -> str | None:
    value = record.get(key)
    return value if isinstance(value, str) else None


def _optional_int(record: Mapping[str, Any], key: str) -> int | None:
    value = record.get(key)
    return value if isinstance(value, int) else None
