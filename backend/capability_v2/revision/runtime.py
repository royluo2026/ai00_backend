"""Formal-runtime composition for the Base-owned Revision repository."""
from __future__ import annotations

from functools import lru_cache

from backend.db.connection import acquire_connection

from .diff import JsonDocumentAdapter
from .repository import SqlRevisionRepository
from .service import RevisionService


@lru_cache(maxsize=1)
def get_default_revision_service() -> RevisionService:
    return RevisionService(
        SqlRevisionRepository(acquire_connection),
        JsonDocumentAdapter(),
    )


__all__ = ["get_default_revision_service"]
