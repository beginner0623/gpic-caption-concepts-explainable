"""Stage 3 spaCy linguistic annotation.

Stage 3 runs the documented spaCy model over Stage 2 protected sentence Docs
and records linguistic evidence. It does not create concepts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import JsonObject, JsonRecord, PIPELINE_VERSION
from gpic_concepts_v1.stage1 import make_caption_record_from_gpic_row
from gpic_concepts_v1.stage2_preprocess import (
    OBJECT_MWE_TOKEN_EXTENSION,
    ObjectMweEntry,
    ProtectedSpanRecord,
    Stage2DependencyError,
    Stage2InputError,
    ensure_stage2_extensions,
    load_object_mwes,
    protect_doc,
    spacy,
)

try:  # pragma: no cover - exercised when spaCy is installed.
    from spacy.language import Language
    from spacy.tokens import Doc, Token
except ModuleNotFoundError:  # pragma: no cover - keeps non-spaCy tests importable.
    Language = Any  # type: ignore[misc,assignment]
    Doc = Any  # type: ignore[misc,assignment]
    Token = Any  # type: ignore[misc,assignment]


DEFAULT_STAGE3_MODEL = "en_core_web_trf"
OBJECT_MWE_POS_CORRECTOR = "gpic_object_mwe_pos_corrector"

TAG_RULE_ID = "R6"
OBJECT_MWE_POS_RULE_ID = "R7"
PARSER_RULE_ID = "R8"
POS_MORPH_RULE_ID = "R9"
LEMMA_RULE_ID = "R10"
NOUN_CHUNK_RULE_ID = "R11"


class Stage3DependencyError(RuntimeError):
    """Raised when the configured spaCy model cannot be loaded."""


@dataclass(slots=True)
class Stage3Record(JsonRecord):
    caption_id: str
    caption: str
    model: str
    tokens: list[JsonObject]
    sentences: list[JsonObject]
    noun_chunks: list[JsonObject]
    protected_spans: list[JsonObject]
    stage: int = 3
    pipeline_version: str = PIPELINE_VERSION
    rule_ids: list[str] = field(default_factory=list)
    meta: JsonObject = field(default_factory=dict)


def register_object_mwe_pos_corrector() -> None:
    """Register R7 as a spaCy component once per Python process."""
    if spacy is None:
        raise Stage2DependencyError(
            "Stage 3 requires spaCy. Install/use the project environment."
        )
    ensure_stage2_extensions()
    if Language.has_factory(OBJECT_MWE_POS_CORRECTOR):
        return
    Language.component(OBJECT_MWE_POS_CORRECTOR)(_object_mwe_pos_corrector)


def make_stage3_nlp(model: str = DEFAULT_STAGE3_MODEL) -> Language:
    """Load the Stage 3 spaCy model and attach the R7 component."""
    if spacy is None:
        raise Stage2DependencyError(
            "Stage 3 requires spaCy. Install/use the project environment."
        )
    register_object_mwe_pos_corrector()
    try:
        nlp = spacy.load(model, disable=["ner"])
    except OSError as exc:
        raise Stage3DependencyError(
            f"Could not load spaCy model {model!r}. Run scripts/setup_env.ps1."
        ) from exc

    if OBJECT_MWE_POS_CORRECTOR not in nlp.pipe_names:
        if "parser" in nlp.pipe_names:
            nlp.add_pipe(OBJECT_MWE_POS_CORRECTOR, before="parser")
        else:
            nlp.add_pipe(OBJECT_MWE_POS_CORRECTOR, last=True)
    nlp.meta["gpic_model_id"] = model
    return nlp


def annotate_gpic_sentence_row(
    row: Mapping[str, Any],
    *,
    nlp: Language,
    object_mwes: Sequence[ObjectMweEntry] = (),
) -> Stage3Record:
    """Annotate one confirmed sentence GPIC row."""
    caption_record = make_caption_record_from_gpic_row(row)
    if caption_record.skipped or caption_record.caption_shape != "sentence":
        raise Stage2InputError("Stage 3 only accepts sentence captions")
    return annotate_text(
        caption_id=caption_record.caption_id,
        caption=caption_record.caption,
        nlp=nlp,
        object_mwes=object_mwes,
        meta=caption_record.meta,
    )


def annotate_text(
    *,
    caption_id: str,
    caption: str,
    nlp: Language,
    object_mwes: Sequence[ObjectMweEntry] = (),
    meta: Mapping[str, Any] | None = None,
) -> Stage3Record:
    """Apply Stage 2 protection and Stage 3 annotation to one sentence caption."""
    doc = nlp.make_doc(caption)
    doc, protected_spans, stage2_rule_ids = protect_doc(
        doc,
        nlp=nlp,
        object_mwes=object_mwes,
    )
    doc = _run_pipeline_components(nlp, doc)
    stage3_rule_ids = _stage3_rule_ids(protected_spans)

    return Stage3Record(
        caption_id=caption_id,
        caption=caption,
        model=nlp.meta.get("gpic_model_id", DEFAULT_STAGE3_MODEL),
        tokens=[_token_to_dict(token) for token in doc],
        sentences=[_sentence_to_dict(sent) for sent in doc.sents],
        noun_chunks=[_noun_chunk_to_dict(chunk) for chunk in doc.noun_chunks],
        protected_spans=[record.to_dict() for record in protected_spans],
        rule_ids=stage2_rule_ids + stage3_rule_ids,
        meta=dict(meta or {}),
    )


def run_stage3_annotate(
    input_path: str | Path,
    *,
    output_path: str | Path,
    object_mwes_path: str | Path,
    summary_path: str | Path | None = None,
    model: str = DEFAULT_STAGE3_MODEL,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run Stage 3 over Stage 1 sentence rows."""
    nlp = make_stage3_nlp(model)
    object_mwes = load_object_mwes(object_mwes_path)

    records: list[Stage3Record] = []
    span_counts: Counter[str] = Counter()
    token_total = 0
    noun_chunk_total = 0

    for index, row in enumerate(iter_jsonl(input_path)):
        if limit is not None and index >= limit:
            break
        record = annotate_gpic_sentence_row(row, nlp=nlp, object_mwes=object_mwes)
        records.append(record)
        token_total += len(record.tokens)
        noun_chunk_total += len(record.noun_chunks)
        for span in record.protected_spans:
            kind = span.get("kind")
            if isinstance(kind, str):
                span_counts[kind] += 1

    write_jsonl(output_path, records)
    summary = {
        "total": len(records),
        "model": model,
        "output_path": str(output_path),
        "object_mwe_lexicon_size": len(object_mwes),
        "token_total": token_total,
        "noun_chunk_total": noun_chunk_total,
        "protected_span_counts": dict(sorted(span_counts.items())),
    }
    if summary_path is not None:
        write_jsonl(summary_path, [summary])
    return summary


def _object_mwe_pos_corrector(doc: Doc) -> Doc:
    for token in doc:
        if token._.get(OBJECT_MWE_TOKEN_EXTENSION):
            token.tag_ = "NN"
            token.pos_ = "NOUN"
    return doc


def _run_pipeline_components(nlp: Language, doc: Doc) -> Doc:
    for _name, component in nlp.pipeline:
        doc = component(doc)
    return doc


def _stage3_rule_ids(protected_spans: Sequence[ProtectedSpanRecord]) -> list[str]:
    rule_ids = [TAG_RULE_ID, PARSER_RULE_ID, POS_MORPH_RULE_ID, LEMMA_RULE_ID, NOUN_CHUNK_RULE_ID]
    if any(span.kind == "object_mwe" for span in protected_spans):
        rule_ids.insert(1, OBJECT_MWE_POS_RULE_ID)
    return rule_ids


def _token_to_dict(token: Token) -> JsonObject:
    return {
        "i": token.i,
        "text": token.text,
        "lemma": token.lemma_,
        "pos": token.pos_,
        "tag": token.tag_,
        "morph": str(token.morph),
        "dep": token.dep_,
        "head_i": token.head.i,
        "head_text": token.head.text,
        "char_start": token.idx,
        "char_end": token.idx + len(token.text),
        "whitespace": token.whitespace_,
        "is_object_mwe": bool(token._.get(OBJECT_MWE_TOKEN_EXTENSION)),
    }


def _sentence_to_dict(sent: Any) -> JsonObject:
    return {
        "text": sent.text,
        "token_start": sent.start,
        "token_end": sent.end,
        "char_start": sent.start_char,
        "char_end": sent.end_char,
    }


def _noun_chunk_to_dict(chunk: Any) -> JsonObject:
    return {
        "text": chunk.text,
        "root_i": chunk.root.i,
        "root_text": chunk.root.text,
        "root_lemma": chunk.root.lemma_,
        "root_pos": chunk.root.pos_,
        "root_tag": chunk.root.tag_,
        "root_dep": chunk.root.dep_,
        "root_head_i": chunk.root.head.i,
        "root_head_text": chunk.root.head.text,
        "token_start": chunk.start,
        "token_end": chunk.end,
        "char_start": chunk.start_char,
        "char_end": chunk.end_char,
    }
