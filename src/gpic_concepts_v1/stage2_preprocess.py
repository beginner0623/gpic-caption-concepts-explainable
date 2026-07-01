"""Stage 2 spaCy preprocessing.

Stage 2 only tokenizes sentence captions and protects spans that must remain
single tokens for later annotation. It does not create concepts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import JsonObject, JsonRecord, PIPELINE_VERSION
from gpic_concepts_v1.stage1 import make_caption_record_from_gpic_row

try:  # pragma: no cover - exercised when spaCy is installed.
    import spacy
    from spacy.language import Language
    from spacy.matcher import PhraseMatcher
    from spacy.tokens import Doc, Span, Token
    from spacy.util import filter_spans
except ModuleNotFoundError as exc:  # pragma: no cover - keeps non-spaCy tests importable.
    spacy = None
    Language = Any  # type: ignore[misc,assignment]
    PhraseMatcher = Any  # type: ignore[misc,assignment]
    Doc = Any  # type: ignore[misc,assignment]
    Span = Any  # type: ignore[misc,assignment]
    Token = Any  # type: ignore[misc,assignment]
    filter_spans = None
    SPACY_IMPORT_ERROR = exc
else:
    SPACY_IMPORT_ERROR = None


OBJECT_MWE_RULE_ID = "R4"
QUOTE_RULE_ID = "R3"
HYPHEN_RULE_ID = "R5"
TOKENIZATION_RULE_ID = "R2"
OBJECT_MWE_TOKEN_EXTENSION = "gpic_object_mwe"


class Stage2InputError(ValueError):
    """Raised when Stage 2 receives a row outside its v1 boundary."""


class Stage2DependencyError(RuntimeError):
    """Raised when spaCy is required but unavailable."""


@dataclass(slots=True)
class ObjectMweEntry:
    phrase: str
    canonical: str
    source: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.phrase, str) or self.phrase.strip() == "":
            raise ValueError("object MWE phrase must be a non-empty string")
        if not isinstance(self.canonical, str) or self.canonical.strip() == "":
            raise ValueError("object MWE canonical must be a non-empty string")
        self.phrase = self.phrase.strip()
        self.canonical = self.canonical.strip()


@dataclass(slots=True)
class ProtectedSpanRecord(JsonRecord):
    kind: str
    text: str
    rule_id: str
    char_start: int
    char_end: int
    token_start: int | None = None
    token_end: int | None = None
    canonical: str | None = None
    source: str | None = None


@dataclass(slots=True)
class Stage2Record(JsonRecord):
    caption_id: str
    caption: str
    tokens: list[JsonObject]
    protected_spans: list[JsonObject]
    stage: int = 2
    pipeline_version: str = PIPELINE_VERSION
    rule_ids: list[str] = field(default_factory=list)
    meta: JsonObject = field(default_factory=dict)


def require_spacy() -> None:
    """Fail clearly when Stage 2 is run without spaCy installed."""
    if spacy is None:
        raise Stage2DependencyError(
            "Stage 2 requires spaCy. Install/use a Python environment with spaCy."
        ) from SPACY_IMPORT_ERROR


def make_stage2_nlp() -> Language:
    """Create the tokenizer-only English spaCy object used by Stage 2."""
    require_spacy()
    return spacy.blank("en")


def ensure_stage2_extensions() -> None:
    """Register spaCy extensions used to carry Stage 2 metadata forward."""
    require_spacy()
    if not Token.has_extension(OBJECT_MWE_TOKEN_EXTENSION):
        Token.set_extension(OBJECT_MWE_TOKEN_EXTENSION, default=False)


def load_object_mwes(path: str | Path) -> list[ObjectMweEntry]:
    """Load the explicit object MWE lexicon used by R4.

    The file may be header-only. No object MWE is inferred from GPIC data here.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("rt", encoding="utf-8", newline="") as handle:
        filtered_lines = (
            line for line in handle if line.strip() and not line.lstrip().startswith("#")
        )
        reader = csv.DictReader(filtered_lines, delimiter="\t")
        if reader.fieldnames is None:
            return []
        if "phrase" not in reader.fieldnames:
            raise ValueError("object MWE lexicon must contain a 'phrase' column")

        entries: list[ObjectMweEntry] = []
        for row in reader:
            phrase = (row.get("phrase") or "").strip()
            if not phrase:
                continue
            canonical = (row.get("canonical") or phrase).strip()
            entries.append(
                ObjectMweEntry(
                    phrase=phrase,
                    canonical=canonical,
                    source=(row.get("source") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                )
            )
        return entries


def preprocess_gpic_sentence_row(
    row: Mapping[str, Any],
    *,
    nlp: Language,
    object_mwes: Sequence[ObjectMweEntry] = (),
) -> Stage2Record:
    """Preprocess one confirmed sentence GPIC row.

    Tag-list rows are rejected here because Stage 1 is responsible for skipping
    them before Stage 2.
    """
    caption_record = make_caption_record_from_gpic_row(row)
    if caption_record.skipped or caption_record.caption_shape != "sentence":
        raise Stage2InputError("Stage 2 only accepts sentence captions")
    return preprocess_text(
        caption_id=caption_record.caption_id,
        caption=caption_record.caption,
        nlp=nlp,
        object_mwes=object_mwes,
        meta=caption_record.meta,
    )


def preprocess_text(
    *,
    caption_id: str,
    caption: str,
    nlp: Language,
    object_mwes: Sequence[ObjectMweEntry] = (),
    meta: Mapping[str, Any] | None = None,
) -> Stage2Record:
    """Apply R2-R5 to one sentence caption and return inspection metadata."""
    require_spacy()
    doc = nlp.make_doc(caption)
    doc, span_records, rule_ids = protect_doc(doc, nlp=nlp, object_mwes=object_mwes)

    return Stage2Record(
        caption_id=caption_id,
        caption=caption,
        tokens=[_token_to_dict(token) for token in doc],
        protected_spans=[record.to_dict() for record in span_records],
        rule_ids=rule_ids,
        meta=dict(meta or {}),
    )


def protect_doc(
    doc: Doc,
    *,
    nlp: Language,
    object_mwes: Sequence[ObjectMweEntry] = (),
) -> tuple[Doc, list[ProtectedSpanRecord], list[str]]:
    """Apply R2-R5 span protection to an already tokenized Doc."""
    ensure_stage2_extensions()
    span_records: list[ProtectedSpanRecord] = []
    rule_ids = [TOKENIZATION_RULE_ID]

    doc, quote_records = _merge_quote_spans(doc)
    if quote_records:
        rule_ids.append(QUOTE_RULE_ID)
        span_records.extend(quote_records)

    doc, mwe_records = _merge_object_mwe_spans(doc, nlp=nlp, object_mwes=object_mwes)
    if mwe_records:
        rule_ids.append(OBJECT_MWE_RULE_ID)
        span_records.extend(mwe_records)

    doc, hyphen_records = _merge_hyphen_word_spans(doc)
    if hyphen_records:
        rule_ids.append(HYPHEN_RULE_ID)
        span_records.extend(hyphen_records)

    _attach_final_token_spans(doc, span_records)
    return doc, span_records, rule_ids


def run_stage2_preprocess(
    input_path: str | Path,
    *,
    output_path: str | Path,
    object_mwes_path: str | Path,
    summary_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run Stage 2 over sentence rows produced by Stage 1."""
    nlp = make_stage2_nlp()
    object_mwes = load_object_mwes(object_mwes_path)

    records: list[Stage2Record] = []
    span_counts: Counter[str] = Counter()
    for index, row in enumerate(iter_jsonl(input_path)):
        if limit is not None and index >= limit:
            break
        record = preprocess_gpic_sentence_row(row, nlp=nlp, object_mwes=object_mwes)
        records.append(record)
        for span in record.protected_spans:
            kind = span.get("kind")
            if isinstance(kind, str):
                span_counts[kind] += 1

    write_jsonl(output_path, records)
    summary = {
        "total": len(records),
        "output_path": str(output_path),
        "object_mwe_lexicon_size": len(object_mwes),
        "protected_span_counts": dict(sorted(span_counts.items())),
    }
    if summary_path is not None:
        write_jsonl(summary_path, [summary])
    return summary


def _merge_quote_spans(doc: Doc) -> tuple[Doc, list[ProtectedSpanRecord]]:
    spans = _find_quote_spans(doc)
    return _merge_and_record(doc, spans, kind="quote", rule_id=QUOTE_RULE_ID)


def _find_quote_spans(doc: Doc) -> list[Span]:
    spans: list[Span] = []
    straight_start: int | None = None
    curly_start: int | None = None

    for token in doc:
        text = token.text
        if text == '"':
            if straight_start is None:
                straight_start = token.i
            else:
                spans.append(doc[straight_start : token.i + 1])
                straight_start = None
        elif text == "“":
            curly_start = token.i
        elif text == "”" and curly_start is not None:
            spans.append(doc[curly_start : token.i + 1])
            curly_start = None

    return spans


def _merge_object_mwe_spans(
    doc: Doc,
    *,
    nlp: Language,
    object_mwes: Sequence[ObjectMweEntry],
) -> tuple[Doc, list[ProtectedSpanRecord]]:
    if not object_mwes:
        return doc, []

    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    matcher.add("OBJECT_MWE", [nlp.make_doc(entry.phrase) for entry in object_mwes])
    entries_by_phrase = {
        _normalize_phrase(entry.phrase): entry
        for entry in object_mwes
    }

    spans = [doc[start:end] for _match_id, start, end in matcher(doc)]
    spans = filter_spans(spans)
    records: list[ProtectedSpanRecord] = []
    for span in spans:
        entry = entries_by_phrase.get(_normalize_phrase(span.text))
        records.append(
            ProtectedSpanRecord(
                kind="object_mwe",
                text=span.text,
                rule_id=OBJECT_MWE_RULE_ID,
                char_start=span.start_char,
                char_end=span.end_char,
                canonical=entry.canonical if entry is not None else _normalize_phrase(span.text),
                source=entry.source if entry is not None else None,
            )
        )

    with doc.retokenize() as retokenizer:
        for span in spans:
            retokenizer.merge(span)
    _mark_object_mwe_tokens(doc, records)
    return doc, records


def _merge_hyphen_word_spans(doc: Doc) -> tuple[Doc, list[ProtectedSpanRecord]]:
    spans = _find_hyphen_word_spans(doc)
    return _merge_and_record(doc, spans, kind="hyphen_word", rule_id=HYPHEN_RULE_ID)


def _find_hyphen_word_spans(doc: Doc) -> list[Span]:
    spans: list[Span] = []
    i = 0
    while i < len(doc):
        if not _is_hyphen_part(doc[i].text):
            i += 1
            continue

        parts = [doc[i].text]
        end = i + 1
        j = i
        while (
            j + 2 < len(doc)
            and doc[j + 1].text == "-"
            and doc[j].whitespace_ == ""
            and doc[j + 1].whitespace_ == ""
            and _is_hyphen_part(doc[j + 2].text)
        ):
            parts.append(doc[j + 2].text)
            end = j + 3
            j += 2

        if _is_mergeable_hyphen_parts(parts):
            spans.append(doc[i:end])
            i = end
        else:
            i += 1

    return spans


def _merge_and_record(
    doc: Doc,
    spans: Iterable[Span],
    *,
    kind: str,
    rule_id: str,
) -> tuple[Doc, list[ProtectedSpanRecord]]:
    filtered = filter_spans(list(spans))
    records = [
        ProtectedSpanRecord(
            kind=kind,
            text=span.text,
            rule_id=rule_id,
            char_start=span.start_char,
            char_end=span.end_char,
        )
        for span in filtered
    ]
    with doc.retokenize() as retokenizer:
        for span in filtered:
            retokenizer.merge(span)
    return doc, records


def _attach_final_token_spans(doc: Doc, records: Sequence[ProtectedSpanRecord]) -> None:
    for record in records:
        for token in doc:
            if token.idx == record.char_start and token.idx + len(token.text) == record.char_end:
                record.token_start = token.i
                record.token_end = token.i + 1
                break


def _mark_object_mwe_tokens(doc: Doc, records: Sequence[ProtectedSpanRecord]) -> None:
    ensure_stage2_extensions()
    for record in records:
        for token in doc:
            if token.idx == record.char_start and token.idx + len(token.text) == record.char_end:
                token._.set(OBJECT_MWE_TOKEN_EXTENSION, True)
                break


def _token_to_dict(token: Any) -> JsonObject:
    return {
        "i": token.i,
        "text": token.text,
        "lower": token.lower_,
        "char_start": token.idx,
        "char_end": token.idx + len(token.text),
        "whitespace": token.whitespace_,
    }


def _normalize_phrase(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _is_hyphen_part(text: str) -> bool:
    return text.isalnum() and any(char.isalpha() for char in text)


def _is_mergeable_hyphen_parts(parts: Sequence[str]) -> bool:
    return (
        len(parts) >= 2
        and all(_is_hyphen_part(part) for part in parts)
        and any(len(part) >= 2 for part in parts)
    )
