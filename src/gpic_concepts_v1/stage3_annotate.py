"""Stage 3 spaCy linguistic annotation.

Stage 3 runs the documented spaCy model over Stage 2 protected sentence Docs
and records linguistic evidence. It does not create concepts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
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
DEFAULT_STAGE3_BATCH_SIZE = 128
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


@dataclass(slots=True)
class _PreparedStage3Doc:
    caption_id: str
    caption: str
    doc: Doc
    protected_spans: list[ProtectedSpanRecord]
    stage2_rule_ids: list[str]
    meta: JsonObject


@dataclass(slots=True)
class AnnotatedStage3Doc:
    """Annotated spaCy Doc plus the Stage 1/2 metadata needed by fast runners."""

    caption_id: str
    caption: str
    doc: Doc
    protected_spans: list[ProtectedSpanRecord]
    rule_ids: list[str]
    meta: JsonObject


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


def make_stage3_nlp(
    model: str = DEFAULT_STAGE3_MODEL,
    *,
    gpu_mode: str = "none",
) -> Language:
    """Load the Stage 3 spaCy model and attach the R7 component."""
    if spacy is None:
        raise Stage2DependencyError(
            "Stage 3 requires spaCy. Install/use the project environment."
        )
    gpu_info = _configure_spacy_gpu(gpu_mode)
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
    nlp.meta["gpic_gpu_mode"] = gpu_info["gpu_mode"]
    nlp.meta["gpic_gpu_enabled"] = gpu_info["gpu_enabled"]
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
    prepared = _prepare_stage3_doc(
        caption_id=caption_id,
        caption=caption,
        nlp=nlp,
        object_mwes=object_mwes,
        meta=meta,
    )
    doc = _run_pipeline_components(nlp, prepared.doc)
    return _stage3_record_from_doc(prepared, doc, nlp=nlp)


def run_stage3_annotate(
    input_path: str | Path,
    *,
    output_path: str | Path,
    object_mwes_path: str | Path,
    summary_path: str | Path | None = None,
    model: str = DEFAULT_STAGE3_MODEL,
    limit: int | None = None,
    batch_size: int = DEFAULT_STAGE3_BATCH_SIZE,
    gpu_mode: str = "none",
) -> dict[str, Any]:
    """Run Stage 3 over Stage 1 sentence rows."""
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    nlp = make_stage3_nlp(model, gpu_mode=gpu_mode)
    object_mwes = load_object_mwes(object_mwes_path)

    span_counts: Counter[str] = Counter()
    token_total = 0
    noun_chunk_total = 0
    total = 0

    def iter_records() -> Any:
        nonlocal noun_chunk_total, token_total, total
        for record in iter_stage3_records_from_rows(
            iter_jsonl(input_path),
            nlp=nlp,
            object_mwes=object_mwes,
            batch_size=batch_size,
            limit=limit,
        ):
            total += 1
            token_total += len(record.tokens)
            noun_chunk_total += len(record.noun_chunks)
            for span in record.protected_spans:
                kind = span.get("kind")
                if isinstance(kind, str):
                    span_counts[kind] += 1
            yield record

    written = write_jsonl(output_path, iter_records())
    summary = {
        "total": total,
        "written": written,
        "model": model,
        "batch_size": batch_size,
        "gpu_mode": nlp.meta.get("gpic_gpu_mode", gpu_mode),
        "gpu_enabled": bool(nlp.meta.get("gpic_gpu_enabled", False)),
        "output_path": str(output_path),
        "object_mwe_lexicon_size": len(object_mwes),
        "token_total": token_total,
        "noun_chunk_total": noun_chunk_total,
        "protected_span_counts": dict(sorted(span_counts.items())),
    }
    if summary_path is not None:
        write_jsonl(summary_path, [summary])
    return summary


def iter_stage3_records_from_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    nlp: Language,
    object_mwes: Sequence[ObjectMweEntry] = (),
    batch_size: int = DEFAULT_STAGE3_BATCH_SIZE,
    limit: int | None = None,
) -> Iterator[Stage3Record]:
    """Yield Stage 3 records from Stage 1 sentence rows using batched nlp.pipe."""
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    pending: list[_PreparedStage3Doc] = []

    def flush_pending() -> Iterator[Stage3Record]:
        docs = [item.doc for item in pending]
        for prepared, doc in zip(
            pending,
            nlp.pipe(docs, batch_size=batch_size),
            strict=True,
        ):
            yield _stage3_record_from_doc(prepared, doc, nlp=nlp)

    for index, row in enumerate(rows):
        if limit is not None and index >= limit:
            break
        caption_record = make_caption_record_from_gpic_row(row)
        if caption_record.skipped or caption_record.caption_shape != "sentence":
            raise Stage2InputError("Stage 3 only accepts sentence captions")
        pending.append(
            _prepare_stage3_doc(
                caption_id=caption_record.caption_id,
                caption=caption_record.caption,
                nlp=nlp,
                object_mwes=object_mwes,
                meta=caption_record.meta,
            )
        )
        if len(pending) >= batch_size:
            yield from flush_pending()
            pending.clear()

    if pending:
        yield from flush_pending()


def iter_annotated_docs_from_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    nlp: Language,
    object_mwes: Sequence[ObjectMweEntry] = (),
    batch_size: int = DEFAULT_STAGE3_BATCH_SIZE,
    limit: int | None = None,
) -> Iterator[AnnotatedStage3Doc]:
    """Yield annotated spaCy Docs without serializing the Stage 3 evidence table."""
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    pending: list[_PreparedStage3Doc] = []

    def flush_pending() -> Iterator[AnnotatedStage3Doc]:
        docs = [item.doc for item in pending]
        for prepared, doc in zip(
            pending,
            nlp.pipe(docs, batch_size=batch_size),
            strict=True,
        ):
            yield AnnotatedStage3Doc(
                caption_id=prepared.caption_id,
                caption=prepared.caption,
                doc=doc,
                protected_spans=prepared.protected_spans,
                rule_ids=prepared.stage2_rule_ids + _stage3_rule_ids(prepared.protected_spans),
                meta=dict(prepared.meta),
            )

    for index, row in enumerate(rows):
        if limit is not None and index >= limit:
            break
        caption_record = make_caption_record_from_gpic_row(row)
        if caption_record.skipped or caption_record.caption_shape != "sentence":
            raise Stage2InputError("Stage 3 only accepts sentence captions")
        pending.append(
            _prepare_stage3_doc(
                caption_id=caption_record.caption_id,
                caption=caption_record.caption,
                nlp=nlp,
                object_mwes=object_mwes,
                meta=caption_record.meta,
            )
        )
        if len(pending) >= batch_size:
            yield from flush_pending()
            pending.clear()

    if pending:
        yield from flush_pending()


def _object_mwe_pos_corrector(doc: Doc) -> Doc:
    for token in doc:
        if token._.get(OBJECT_MWE_TOKEN_EXTENSION):
            token.tag_ = "NN"
            token.pos_ = "NOUN"
    return doc


def _configure_spacy_gpu(gpu_mode: str) -> JsonObject:
    normalized = gpu_mode.lower()
    if normalized not in {"none", "prefer", "require"}:
        raise ValueError("gpu_mode must be one of: none, prefer, require")
    if normalized == "none":
        return {"gpu_mode": "none", "gpu_enabled": False}
    if spacy is None:
        raise Stage2DependencyError(
            "Stage 3 requires spaCy. Install/use the project environment."
        )
    if normalized == "prefer":
        return {"gpu_mode": "prefer", "gpu_enabled": bool(spacy.prefer_gpu())}
    try:
        spacy.require_gpu()
    except Exception as exc:  # pragma: no cover - depends on local CUDA/CuPy setup.
        raise Stage3DependencyError(
            "Could not activate spaCy GPU. Install a CuPy build matching CUDA, "
            "or rerun without --require-gpu."
        ) from exc
    return {"gpu_mode": "require", "gpu_enabled": True}


def _prepare_stage3_doc(
    *,
    caption_id: str,
    caption: str,
    nlp: Language,
    object_mwes: Sequence[ObjectMweEntry] = (),
    meta: Mapping[str, Any] | None = None,
) -> _PreparedStage3Doc:
    doc = nlp.make_doc(caption)
    doc, protected_spans, stage2_rule_ids = protect_doc(
        doc,
        nlp=nlp,
        object_mwes=object_mwes,
    )
    return _PreparedStage3Doc(
        caption_id=caption_id,
        caption=caption,
        doc=doc,
        protected_spans=protected_spans,
        stage2_rule_ids=stage2_rule_ids,
        meta=dict(meta or {}),
    )


def _stage3_record_from_doc(
    prepared: _PreparedStage3Doc,
    doc: Doc,
    *,
    nlp: Language,
) -> Stage3Record:
    stage3_rule_ids = _stage3_rule_ids(prepared.protected_spans)
    return Stage3Record(
        caption_id=prepared.caption_id,
        caption=prepared.caption,
        model=nlp.meta.get("gpic_model_id", DEFAULT_STAGE3_MODEL),
        tokens=[_token_to_dict(token) for token in doc],
        sentences=[_sentence_to_dict(sent) for sent in doc.sents],
        noun_chunks=[_noun_chunk_to_dict(chunk) for chunk in doc.noun_chunks],
        protected_spans=[record.to_dict() for record in prepared.protected_spans],
        rule_ids=prepared.stage2_rule_ids + stage3_rule_ids,
        meta=dict(prepared.meta),
    )


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
