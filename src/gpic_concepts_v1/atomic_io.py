"""Atomic file-write helpers for generated artifacts."""

from __future__ import annotations

import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO


@contextmanager
def atomic_text_writer(
    path: Path,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
) -> Iterator[TextIO]:
    """Write a text file through a same-directory temp file, then replace."""

    debug = os.environ.get("GPIC_ATOMIC_IO_DEBUG") == "1"

    def debug_log(message: str) -> None:
        if debug:
            print(f"atomic_io_debug={message} path={path}", flush=True)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    debug_log("parent_ready")
    temp_path = _new_temp_path(path)
    force_fallback = os.environ.get("GPIC_ATOMIC_IO_FORCE_FALLBACK") == "1"
    if force_fallback:
        temp_path = _new_fallback_temp_path(path)

    try:
        debug_log("before_open_temp")
        handle = temp_path.open("x", encoding=encoding, newline=newline)
    except PermissionError as exc:
        temp_path.unlink(missing_ok=True)
        if force_fallback:
            raise
        if os.environ.get("GPIC_ATOMIC_IO_ALLOW_AUTO_FALLBACK") != "1":
            raise PermissionError(
                "cannot create same-directory atomic temp file; rerun the "
                "generated-artifact command with the correct writable workspace "
                "or approved outside-sandbox execution instead of falling back "
                "to a different temp directory"
            ) from exc
        debug_log(f"same_dir_temp_permission_error error={exc!r}")
        temp_path = _new_fallback_temp_path(path)
        handle = temp_path.open("x", encoding=encoding, newline=newline)

    try:
        with handle:
            debug_log(f"temp_opened temp={temp_path}")
            yield handle
            debug_log("after_yield_before_flush")
            handle.flush()
            debug_log("after_flush_before_fsync")
            os.fsync(handle.fileno())
            debug_log("after_fsync")
        debug_log(f"before_replace temp={temp_path}")
        os.replace(temp_path, path)
        debug_log("after_replace")
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _new_temp_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")


def _new_fallback_temp_path(path: Path) -> Path:
    root = Path(
        os.environ.get("GPIC_ATOMIC_TEMP_ROOT")
        or os.environ.get("GPIC_TEST_TEMP_ROOT")
        or r"C:\Users\Public\Documents\ESTsoft\CreatorTemp"
        or tempfile.gettempdir()
    )
    temp_dir = root / "gpic_atomic_io"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
