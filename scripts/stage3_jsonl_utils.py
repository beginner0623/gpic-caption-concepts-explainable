from __future__ import annotations

import json
import re
from collections.abc import Mapping


STAGE3_CAPTION_ID_PREFIX_RE = re.compile(
    r'^\s*\{\s*"caption_id"\s*:\s*"((?:[^"\\]|\\.)*)"'
)


def extract_stage3_caption_id_from_line(line: str, *, record_index: int) -> str:
    """Extract caption_id without fully parsing the common Stage 3 JSONL shape."""
    match = STAGE3_CAPTION_ID_PREFIX_RE.match(line)
    if match:
        return str(json.loads(f'"{match.group(1)}"')).strip()
    record = json.loads(line)
    if not isinstance(record, Mapping):
        raise ValueError(f"stage3_record_is_not_json_object_at_index={record_index}")
    return str(record.get("caption_id", "")).strip()
