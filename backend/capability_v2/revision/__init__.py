"""Domain-neutral immutable revision, diff, merge and lineage kernel."""

from .diff import DomainRevisionAdapter, JsonDocumentAdapter
from .models import (
    BranchRef,
    Change,
    ChangeSet,
    ChangeSetRef,
    Commit,
    CommitRef,
    DiffRecord,
    DiffRef,
    MergeConflict,
    MergeResult,
    LineageEdge,
    LineageGraph,
    RepositoryRef,
    Snapshot,
    SnapshotRef,
)
from .repository import InMemoryRevisionRepository, RevisionRepository
from .service import RevisionService

__all__ = [
    "BranchRef", "Change", "ChangeSet", "ChangeSetRef", "Commit", "CommitRef",
    "DiffRecord", "DiffRef", "DomainRevisionAdapter", "InMemoryRevisionRepository",
    "JsonDocumentAdapter", "MergeConflict", "MergeResult", "RepositoryRef",
    "LineageEdge", "LineageGraph",
    "RevisionRepository", "RevisionService", "Snapshot", "SnapshotRef",
]
