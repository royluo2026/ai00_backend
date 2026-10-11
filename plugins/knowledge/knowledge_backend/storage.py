"""Knowledge object-storage port with one replaceable infrastructure adapter."""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from threading import Lock
from typing import Protocol

from backend.capability_v2.artifacts import OisImmutableObjectStorage


class KnowledgeObjectStore(Protocol):
    def put_immutable(self, object_key: str, data: bytes, media_type: str) -> dict | None: ...
    def get_immutable(self, object_key: str, expected_sha256: str) -> bytes | None: ...


_store: KnowledgeObjectStore = OisImmutableObjectStorage()
_read_cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()
_cache_lock = Lock()
_cache_bytes = 0
_CACHE_MAX_BYTES = 16 * 1024 * 1024
_CACHE_MAX_ITEMS = 128


def configure_object_store(store: KnowledgeObjectStore) -> None:
    global _store, _cache_bytes
    with _cache_lock:
        _store = store
        _read_cache.clear()
        _cache_bytes = 0


def put_immutable(object_key: str, data: bytes, media_type: str) -> dict | None:
    return _store.put_immutable(object_key, data, media_type)


def get_immutable(object_key: str, expected_sha256: str) -> bytes | None:
    global _cache_bytes
    key = (object_key, expected_sha256)
    with _cache_lock:
        cached = _read_cache.get(key)
        if cached is not None:
            _read_cache.move_to_end(key)
            return cached
        store = _store
    data = store.get_immutable(object_key, expected_sha256)
    # Cache verified immutable content only. Drafts, permissions and failures stay live.
    if data is not None and expected_sha256 and len(data) <= 1024 * 1024 and hashlib.sha256(data).hexdigest() == expected_sha256:
        with _cache_lock:
            if store is _store and key not in _read_cache:
                _read_cache[key] = data
                _cache_bytes += len(data)
                while len(_read_cache) > _CACHE_MAX_ITEMS or _cache_bytes > _CACHE_MAX_BYTES:
                    _, evicted = _read_cache.popitem(last=False)
                    _cache_bytes -= len(evicted)
    return data


def publish_proposal_markdown(proposal_gid: str, markdown: str) -> dict:
    data = markdown.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    object_key = f"knowledge/proposals/{proposal_gid}/document.{digest}.md"
    result = put_immutable(object_key, data, "text/markdown; charset=utf-8")
    if not result or result.get("object_key") != object_key or result.get("sha256") != digest:
        raise RuntimeError("Knowledge object storage is unavailable or failed verification")
    return {"ois_url": f"ois://{object_key}", "object_key": object_key, "sha256": digest}


__all__ = [
    "KnowledgeObjectStore", "configure_object_store", "get_immutable",
    "publish_proposal_markdown", "put_immutable",
]
