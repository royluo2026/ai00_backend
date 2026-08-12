"""Knowledge object-storage port with one replaceable infrastructure adapter."""
from __future__ import annotations

import hashlib
from typing import Protocol

from backend.capability_v2.artifacts import OisImmutableObjectStorage


class KnowledgeObjectStore(Protocol):
    def put_immutable(self, object_key: str, data: bytes, media_type: str) -> dict | None: ...
    def get_immutable(self, object_key: str, expected_sha256: str) -> bytes | None: ...


_store: KnowledgeObjectStore = OisImmutableObjectStorage()


def configure_object_store(store: KnowledgeObjectStore) -> None:
    global _store
    _store = store


def put_immutable(object_key: str, data: bytes, media_type: str) -> dict | None:
    return _store.put_immutable(object_key, data, media_type)


def get_immutable(object_key: str, expected_sha256: str) -> bytes | None:
    return _store.get_immutable(object_key, expected_sha256)


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
