"""Immutable public records for the revision kernel."""
from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any, Literal, Mapping

from pydantic import Field, model_validator

from backend.capability_v2.contracts import FrozenModel, IDENTITY_PATTERN
from .canonical import canonical_json_bytes


HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"
BRANCH_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$"


class RepositoryRef(FrozenModel):
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    repository_id: str = Field(pattern=IDENTITY_PATTERN)
    owner_domain: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    resource_id: str = Field(pattern=IDENTITY_PATTERN)


class BranchRef(FrozenModel):
    repository: RepositoryRef
    name: str = Field(pattern=BRANCH_PATTERN)

    @model_validator(mode="after")
    def safe_branch_name(self) -> "BranchRef":
        segments = self.name.split("/")
        if any(segment in {"", ".", ".."} for segment in segments):
            raise ValueError("branch name contains an unsafe path segment")
        return self


class SnapshotRef(FrozenModel):
    snapshot_id: str = Field(pattern=r"^snp_[0-9a-f]{32}$")
    content_hash: str = Field(pattern=HASH_PATTERN)
    byte_size: int = Field(ge=0)


class CommitRef(FrozenModel):
    repository: RepositoryRef
    commit_id: str = Field(pattern=r"^cmt_[0-9a-f]{40}$")
    content_hash: str = Field(pattern=HASH_PATTERN)


class ChangeSetRef(FrozenModel):
    repository: RepositoryRef
    changeset_id: str = Field(pattern=r"^chg_[0-9a-f]{32}$")
    base_commit_id: str = Field(pattern=r"^cmt_[0-9a-f]{40}$")


class DiffRef(FrozenModel):
    repository: RepositoryRef
    diff_id: str = Field(pattern=r"^dif_[0-9a-f]{32}$")
    from_commit_id: str = Field(pattern=r"^cmt_[0-9a-f]{40}$")
    to_commit_id: str = Field(pattern=r"^cmt_[0-9a-f]{40}$")


class BaselineRef(FrozenModel):
    repository: RepositoryRef
    commit_id: str = Field(pattern=r"^cmt_[0-9a-f]{40}$")


class Snapshot(FrozenModel):
    snapshot_id: str = Field(pattern=r"^snp_[0-9a-f]{32}$")
    content_hash: str = Field(pattern=HASH_PATTERN)
    byte_size: int = Field(ge=0)
    content: Mapping[str, Any]

    @model_validator(mode="after")
    def verify_content_address(self) -> "Snapshot":
        data = canonical_json_bytes(self.content)
        digest = hashlib.sha256(data).hexdigest()
        if self.content_hash != f"sha256:{digest}":
            raise ValueError("snapshot_content_hash_mismatch")
        if self.snapshot_id != f"snp_{digest[:32]}":
            raise ValueError("snapshot_id_mismatch")
        if self.byte_size != len(data):
            raise ValueError("snapshot_byte_size_mismatch")
        return self

    @property
    def ref(self) -> SnapshotRef:
        return SnapshotRef(
            snapshot_id=self.snapshot_id,
            content_hash=self.content_hash,
            byte_size=self.byte_size,
        )


class Commit(FrozenModel):
    commit_id: str = Field(pattern=r"^cmt_[0-9a-f]{40}$")
    repository: RepositoryRef
    parent_ids: tuple[str, ...] = Field(max_length=2)
    snapshot: Snapshot
    content_hash: str = Field(pattern=HASH_PATTERN)
    author_id: str = Field(pattern=IDENTITY_PATTERN)
    message: str = Field(min_length=1, max_length=2000)
    created_at: datetime

    @model_validator(mode="after")
    def valid_commit(self) -> "Commit":
        if len(self.parent_ids) != len(set(self.parent_ids)):
            raise ValueError("commit parents must be unique")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("commit created_at must be timezone-aware")
        if self.content_hash != self.snapshot.content_hash:
            raise ValueError("commit content hash must match its snapshot")
        document = {
            "format": "ai00.revision.commit.v1",
            "repository": self.repository.model_dump(mode="json"),
            "parents": list(self.parent_ids),
            "snapshot_id": self.snapshot.snapshot_id,
            "content_hash": self.snapshot.content_hash,
            "author_id": self.author_id,
            "message": self.message,
        }
        digest = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
        if self.commit_id != f"cmt_{digest[:40]}":
            raise ValueError("commit_id_mismatch")
        return self

    @property
    def ref(self) -> CommitRef:
        return CommitRef(
            repository=self.repository,
            commit_id=self.commit_id,
            content_hash=self.content_hash,
        )


class Branch(FrozenModel):
    ref: BranchRef
    head_commit_id: str = Field(pattern=r"^cmt_[0-9a-f]{40}$")
    protected: bool = False
    approval_policy: str | None = Field(default=None, max_length=128)
    version: int = Field(default=1, ge=1)


class Change(FrozenModel):
    change_type: Literal["add", "remove", "replace", "move"]
    path: str = Field(pattern=r"^/(?:.*)?$")
    before: Any = None
    after: Any = None
    identity: str | None = Field(default=None, max_length=256)
    from_index: int | None = Field(default=None, ge=0)
    to_index: int | None = Field(default=None, ge=0)


class DiffRecord(FrozenModel):
    ref: DiffRef
    changes: tuple[Change, ...]

    @model_validator(mode="after")
    def verify_diff_id(self) -> "DiffRecord":
        document = {
            "format": "ai00.revision.diff.v1",
            "repository": self.ref.repository.model_dump(mode="json"),
            "from": self.ref.from_commit_id,
            "to": self.ref.to_commit_id,
            "changes": [item.model_dump(mode="json") for item in self.changes],
        }
        digest = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
        if self.ref.diff_id != f"dif_{digest[:32]}":
            raise ValueError("diff_id_mismatch")
        return self


class ChangeSet(FrozenModel):
    ref: ChangeSetRef
    changes: tuple[Change, ...]
    result_content_hash: str = Field(pattern=HASH_PATTERN)
    created_by: str = Field(pattern=IDENTITY_PATTERN)
    created_at: datetime

    @model_validator(mode="after")
    def changeset_time(self) -> "ChangeSet":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("changeset created_at must be timezone-aware")
        document = {
            "format": "ai00.revision.changeset.v1",
            "repository": self.ref.repository.model_dump(mode="json"),
            "base_commit": self.ref.base_commit_id,
            "changes": [item.model_dump(mode="json") for item in self.changes],
            "result_content_hash": self.result_content_hash,
            "created_by": self.created_by,
        }
        digest = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
        if self.ref.changeset_id != f"chg_{digest[:32]}":
            raise ValueError("changeset_id_mismatch")
        return self


class MergeConflict(FrozenModel):
    path: str = Field(pattern=r"^/(?:.*)?$")
    kind: str = Field(min_length=1, max_length=64)
    base: Any = None
    ours: Any = None
    theirs: Any = None


class BranchApprovalChallenge(FrozenModel):
    challenge_id: str = Field(pattern=r"^bra_[0-9a-f]{32}$")
    repository: RepositoryRef
    target_branch: str = Field(pattern=BRANCH_PATTERN)
    target_head: str = Field(pattern=r"^cmt_[0-9a-f]{40}$")
    source_head: str = Field(pattern=r"^cmt_[0-9a-f]{40}$")
    policy: str = Field(min_length=1, max_length=128)


class MergeResult(FrozenModel):
    status: Literal["merged", "conflicted", "approval_required"]
    commit: Commit | None = None
    conflicts: tuple[MergeConflict, ...] = ()
    approval: BranchApprovalChallenge | None = None

    @model_validator(mode="after")
    def result_shape(self) -> "MergeResult":
        if self.status == "merged" and (self.commit is None or self.conflicts or self.approval):
            raise ValueError("merged result requires only a commit")
        if self.status == "conflicted" and (not self.conflicts or self.commit or self.approval):
            raise ValueError("conflicted result requires only conflicts")
        if self.status == "approval_required" and (self.approval is None or self.commit or self.conflicts):
            raise ValueError("approval_required result requires only a challenge")
        return self


class CommitOutcome(FrozenModel):
    branch: BranchRef
    commit: Commit


class LineageEdge(FrozenModel):
    edge_id: str = Field(pattern=r"^lin_[0-9a-f]{32}$")
    upstream: CommitRef
    downstream: CommitRef
    relation: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    created_by: str = Field(pattern=IDENTITY_PATTERN)
    created_at: datetime

    @model_validator(mode="after")
    def lineage_contract(self) -> "LineageEdge":
        if self.upstream.repository.tenant_id != self.downstream.repository.tenant_id:
            raise ValueError("lineage cannot cross tenants")
        if self.upstream == self.downstream:
            raise ValueError("lineage cannot point to itself")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("lineage created_at must be timezone-aware")
        document = {
            "format": "ai00.revision.lineage.v1",
            "upstream": self.upstream.model_dump(mode="json"),
            "downstream": self.downstream.model_dump(mode="json"),
            "relation": self.relation,
            "created_by": self.created_by,
        }
        digest = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
        if self.edge_id != f"lin_{digest[:32]}":
            raise ValueError("lineage_edge_id_mismatch")
        return self


class LineageGraph(FrozenModel):
    root: CommitRef
    direction: Literal["upstream", "downstream"]
    edges: tuple[LineageEdge, ...]
    truncated: bool = False
