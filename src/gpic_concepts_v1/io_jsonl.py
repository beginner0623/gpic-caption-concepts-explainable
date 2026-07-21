"""Small JSONL helpers for v1 pipeline files."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
import gzip
import json
from pathlib import Path
from typing import Any, TextIO


JsonObject = dict[str, Any]


@contextmanager
def open_text(path: str | Path, mode: str) -> Iterator[TextIO]:
    """Open plain text or gzip-compressed text based on file suffix."""
    path = Path(path)
    if "b" in mode:
        raise ValueError("open_text only supports text modes")
    if path.suffix == ".gz":
        with gzip.open(path, mode, encoding="utf-8") as handle:
            yield handle
        return
    with path.open(mode, encoding="utf-8") as handle:
        yield handle


def iter_jsonl(path: str | Path) -> Iterator[JsonObject]:
    """Yield JSON objects from a .jsonl or .jsonl.gz file."""
    with open_text(path, "rt") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number} is not a JSON object")
            yield value


def to_jsonable(record: object) -> JsonObject:
    """Convert a pipeline record or mapping to a JSON object."""
    if hasattr(record, "to_dict"):
        value = record.to_dict()
    elif is_dataclass(record):
        value = asdict(record)
    elif isinstance(record, Mapping):
        value = dict(record)
    else:
        raise TypeError(f"unsupported JSONL record type: {type(record).__name__}")
    if not isinstance(value, dict):
        raise TypeError("JSONL records must serialize to JSON objects")
    return value


def write_jsonl(
    path: str | Path,
    records: Iterable[object],
    *,
    sort_keys: bool = True,
    compact: bool = False,
) -> int:
    """Write records to .jsonl or .jsonl.gz and return row count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        sort_keys=sort_keys,
        separators=(",", ":") if compact else None,
    ).encode
    count = 0
    with open_text(path, "wt") as handle:
        for record in records:
            handle.write(encoder(to_jsonable(record)))
            handle.write("\n")
            count += 1
    return count
