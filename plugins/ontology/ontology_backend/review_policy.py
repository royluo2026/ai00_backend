"""Human review rules for publishing ontology proposal revisions."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def is_publishable(*, reviews: Sequence[Mapping[str, Any]], author_gid: str, content_sha256: str) -> bool:
    bound = [item for item in reviews if item.get("content_sha256") == content_sha256]
    if any(item.get("decision") in {"reject", "request_changes"} for item in bound):
        return False
    return any(item.get("decision") == "approve" and item.get("reviewer_gid") != author_gid for item in bound)
