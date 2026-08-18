"""Canonical, portable hashes for immutable governance documents."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any


def _normalise(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _normalise(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple | list):
        return [_normalise(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((_normalise(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    return value


def canonical_json(value: Any) -> str:
    """Serialize a value deterministically before it becomes an immutable hash."""
    return json.dumps(_normalise(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def descriptor_fingerprint(descriptor: Mapping[str, Any]) -> str:
    return canonical_fingerprint(descriptor)


__all__ = ["canonical_fingerprint", "canonical_json", "descriptor_fingerprint"]
