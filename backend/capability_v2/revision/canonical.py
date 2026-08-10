"""Canonical JSON shared by revision identities, storage and verification."""
from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


def normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("revision content cannot contain NaN or infinity")
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("revision object keys must be strings")
            canonical_key = unicodedata.normalize("NFC", key)
            if canonical_key in normalized:
                raise ValueError("revision object contains duplicate normalized keys")
            normalized[canonical_key] = normalize_json(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [normalize_json(item) for item in value]
    raise TypeError(f"unsupported revision value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        normalize_json(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
