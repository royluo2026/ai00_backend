"""Deterministic ontology release serialization and hashing."""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from .models import OBJECT_KINDS

FORMAT = "ai00.ontology.release.v1"


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("ontology values cannot contain NaN or infinity")
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("ontology object keys must be strings")
            result[unicodedata.normalize("NFC", key)] = _normalize(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [_normalize(item) for item in value]
    raise TypeError(f"unsupported ontology value: {type(value).__name__}")


def normalize_release_objects(objects: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(objects, bytes | str) or not isinstance(objects, Sequence):
        raise TypeError("objects must be an array")
    normalized: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for raw in objects:
        if not isinstance(raw, Mapping):
            raise TypeError("each ontology object must be an object")
        item = _normalize(raw)
        kind = str(item.get("kind") or "").strip().lower()
        stable_gid = str(item.get("stable_gid") or "").strip()
        if kind not in OBJECT_KINDS:
            raise ValueError(f"unsupported ontology object kind: {kind or '<empty>'}")
        if not stable_gid or len(stable_gid) > 128:
            raise ValueError("stable_gid is required and must be at most 128 characters")
        identity = (kind, stable_gid)
        if identity in identities:
            raise ValueError(f"duplicate ontology object identity: {kind}/{stable_gid}")
        identities.add(identity)
        item["kind"] = kind
        item["stable_gid"] = stable_gid
        normalized.append(item)
    normalized.sort(key=lambda item: (item["kind"], item["stable_gid"]))
    return normalized


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(_normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonicalize_release(objects: Sequence[Mapping[str, Any]]) -> tuple[bytes, str]:
    data = canonical_json_bytes({"format": FORMAT, "objects": normalize_release_objects(objects)})
    return data, hashlib.sha256(data).hexdigest()
