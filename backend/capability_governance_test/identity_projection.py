"""Stable logical and major identity projection for immutable snapshots."""
from __future__ import annotations

from .models import SnapshotDocument, SnapshotRecord


def project_snapshot(store: object, document: SnapshotDocument) -> SnapshotRecord:
    """Persist one immutable document through the supplied governance store."""
    importer = getattr(store, "import_snapshot", None)
    if not callable(importer):
        raise TypeError("store must implement import_snapshot(document)")
    return importer(document)


__all__ = ["project_snapshot"]
