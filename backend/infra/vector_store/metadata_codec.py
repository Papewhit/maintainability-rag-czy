"""Encode Milvus metadata and normalize it for in-process consumers."""
from __future__ import annotations

import json
from typing import Any

MAX_ENTITY_TYPES_BYTES = 512


def decode_entity_types(value: Any) -> list[str]:
    """Return the canonical runtime ``list[str]`` representation.

    Milvus historically contains both dynamic-field arrays and VARCHAR JSON
    arrays. Unsupported or malformed values degrade to an empty list so bad
    metadata cannot break retrieval.
    """
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    if not isinstance(value, (list, tuple, set, frozenset)):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, (dict, list, tuple, set, frozenset)):
            continue
        normalized = str(item).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def encode_entity_types(value: Any) -> str:
    """Return the canonical compact JSON-string Milvus wire representation."""
    encoded = json.dumps(decode_entity_types(value), ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_ENTITY_TYPES_BYTES:
        raise ValueError(f"entity_types JSON exceeds {MAX_ENTITY_TYPES_BYTES} bytes")
    return encoded
