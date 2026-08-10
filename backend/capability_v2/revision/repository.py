"""Persistence port and test-safe in-memory implementation for revisions."""
from __future__ import annotations

import threading
import json
from datetime import UTC, datetime
from copy import deepcopy
from typing import Callable, Protocol

from .models import (
    Branch, BranchRef, ChangeSet, ChangeSetRef, Commit, CommitRef, DiffRecord, DiffRef, LineageEdge,
    RepositoryRef, Snapshot,
)


class RepositoryExistsError(RuntimeError):
    pass


class RecordNotFoundError(LookupError):
    pass


class CompareAndSwapError(RuntimeError):
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__("branch head changed")
        self.expected = expected
        self.actual = actual


def _repo_key(ref: RepositoryRef) -> tuple[str, str]:
    return ref.tenant_id, ref.repository_id


def _branch_key(ref: BranchRef) -> tuple[str, str, str]:
    return ref.repository.tenant_id, ref.repository.repository_id, ref.name


class RevisionRepository(Protocol):
    def initialize(self, ref: RepositoryRef, branch: BranchRef, commit: Commit) -> Branch: ...
    def create_repository(self, ref: RepositoryRef) -> None: ...
    def repository_exists(self, ref: RepositoryRef) -> bool: ...
    def save_snapshot(self, tenant_id: str, snapshot: Snapshot) -> Snapshot: ...
    def get_snapshot(self, tenant_id: str, snapshot_id: str) -> Snapshot | None: ...
    def get_commit(self, commit_id: str) -> Commit | None: ...
    def create_branch(self, branch: Branch) -> None: ...
    def get_branch(self, ref: BranchRef) -> Branch | None: ...
    def append_commit(self, branch: BranchRef, commit: Commit, expected_head: str | None) -> Branch: ...
    def protect_branch(self, ref: BranchRef, approval_policy: str) -> Branch: ...
    def save_changeset(self, changeset: ChangeSet) -> ChangeSet: ...
    def get_changeset(self, ref: ChangeSetRef) -> ChangeSet | None: ...
    def save_diff(self, diff: DiffRecord) -> DiffRecord: ...
    def get_diff(self, ref: DiffRef) -> DiffRecord | None: ...
    def save_lineage(self, edge: LineageEdge) -> LineageEdge: ...
    def list_lineage(self, ref: CommitRef, direction: str) -> tuple[LineageEdge, ...]: ...


class InMemoryRevisionRepository:
    """A faithful CAS repository for unit tests and local development only."""

    def __init__(self) -> None:
        self._repositories: dict[tuple[str, str], RepositoryRef] = {}
        self._snapshots: dict[tuple[str, str], Snapshot] = {}
        self._commits: dict[str, Commit] = {}
        self._branches: dict[tuple[str, str, str], Branch] = {}
        self._lineage: dict[str, LineageEdge] = {}
        self._changesets: dict[tuple[str, str, str], ChangeSet] = {}
        self._diffs: dict[tuple[str, str, str], DiffRecord] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _copy(value):
        return value.__class__.model_validate(deepcopy(value.model_dump(mode="python")))

    def create_repository(self, ref: RepositoryRef) -> None:
        with self._lock:
            key = _repo_key(ref)
            if key in self._repositories:
                raise RepositoryExistsError("revision repository already exists")
            self._repositories[key] = self._copy(ref)

    def initialize(self, ref: RepositoryRef, branch: BranchRef, commit: Commit) -> Branch:
        with self._lock:
            repository_key = _repo_key(ref)
            branch_key = _branch_key(branch)
            if repository_key in self._repositories or branch_key in self._branches:
                raise RepositoryExistsError("revision repository already exists")
            if branch.repository != ref or commit.repository != ref or commit.parent_ids:
                raise ValueError("initial commit must be a root in the same repository")
            snapshot_key = (ref.tenant_id, commit.snapshot.snapshot_id)
            self._repositories[repository_key] = self._copy(ref)
            self._snapshots[snapshot_key] = self._copy(commit.snapshot)
            self._commits[commit.commit_id] = self._copy(commit)
            created = Branch(ref=branch, head_commit_id=commit.commit_id)
            self._branches[branch_key] = self._copy(created)
            return self._copy(created)

    def repository_exists(self, ref: RepositoryRef) -> bool:
        with self._lock:
            stored = self._repositories.get(_repo_key(ref))
            return stored == ref

    def save_snapshot(self, tenant_id: str, snapshot: Snapshot) -> Snapshot:
        with self._lock:
            key = (tenant_id, snapshot.snapshot_id)
            existing = self._snapshots.get(key)
            if existing is not None and existing.content_hash != snapshot.content_hash:
                raise RuntimeError("snapshot identifier collision")
            if existing is None:
                self._snapshots[key] = self._copy(snapshot)
            return self._copy(self._snapshots[key])

    def get_snapshot(self, tenant_id: str, snapshot_id: str) -> Snapshot | None:
        with self._lock:
            value = self._snapshots.get((tenant_id, snapshot_id))
            return self._copy(value) if value else None

    def get_commit(self, commit_id: str) -> Commit | None:
        with self._lock:
            value = self._commits.get(commit_id)
            return self._copy(value) if value else None

    def create_branch(self, branch: Branch) -> None:
        with self._lock:
            key = _branch_key(branch.ref)
            if key in self._branches:
                raise RepositoryExistsError("branch already exists")
            commit = self._commits.get(branch.head_commit_id)
            if commit is None or commit.repository != branch.ref.repository:
                raise RecordNotFoundError("branch head is outside repository")
            self._branches[key] = self._copy(branch)

    def get_branch(self, ref: BranchRef) -> Branch | None:
        with self._lock:
            value = self._branches.get(_branch_key(ref))
            return self._copy(value) if value else None

    def append_commit(self, branch: BranchRef, commit: Commit, expected_head: str | None) -> Branch:
        with self._lock:
            if commit.repository != branch.repository:
                raise RecordNotFoundError("commit is outside branch repository")
            if not commit.parent_ids or commit.parent_ids[0] != expected_head:
                raise ValueError("commit first parent must equal the expected branch head")
            key = _branch_key(branch)
            current = self._branches.get(key)
            actual = current.head_commit_id if current else ""
            if actual != (expected_head or ""):
                raise CompareAndSwapError(expected_head or "", actual)
            for parent_id in commit.parent_ids:
                parent = self._commits.get(parent_id)
                if parent is None or parent.repository != commit.repository:
                    raise RecordNotFoundError("commit parent is outside repository")
            existing = self._commits.get(commit.commit_id)
            if existing is not None and existing != commit:
                raise RuntimeError("commit identifier collision")
            snapshot_key = (commit.repository.tenant_id, commit.snapshot.snapshot_id)
            stored_snapshot = self._snapshots.get(snapshot_key)
            if stored_snapshot is not None and stored_snapshot.content_hash != commit.snapshot.content_hash:
                raise RuntimeError("snapshot identifier collision")
            self._snapshots[snapshot_key] = self._copy(commit.snapshot)
            self._commits[commit.commit_id] = self._copy(commit)
            next_branch = Branch(
                ref=branch,
                head_commit_id=commit.commit_id,
                protected=current.protected if current else False,
                approval_policy=current.approval_policy if current else None,
                version=(current.version + 1) if current else 1,
            )
            self._branches[key] = next_branch
            return self._copy(next_branch)

    def protect_branch(self, ref: BranchRef, approval_policy: str) -> Branch:
        with self._lock:
            key = _branch_key(ref)
            current = self._branches.get(key)
            if current is None:
                raise RecordNotFoundError("branch not found")
            updated = current.model_copy(update={
                "protected": True,
                "approval_policy": approval_policy,
                "version": current.version + 1,
            })
            self._branches[key] = self._copy(updated)
            return self._copy(updated)

    def save_changeset(self, changeset: ChangeSet) -> ChangeSet:
        with self._lock:
            base = self._commits.get(changeset.ref.base_commit_id)
            if base is None or base.repository != changeset.ref.repository:
                raise RecordNotFoundError("changeset base commit not found")
            key = (
                changeset.ref.repository.tenant_id,
                changeset.ref.repository.repository_id,
                changeset.ref.changeset_id,
            )
            existing = self._changesets.get(key)
            if existing is None:
                self._changesets[key] = self._copy(changeset)
            elif existing.model_dump(exclude={"created_at"}) != changeset.model_dump(exclude={"created_at"}):
                raise RuntimeError("changeset identifier collision")
            return self._copy(self._changesets[key])

    def get_changeset(self, ref: ChangeSetRef) -> ChangeSet | None:
        with self._lock:
            value = self._changesets.get((
                ref.repository.tenant_id, ref.repository.repository_id, ref.changeset_id,
            ))
            return self._copy(value) if value else None

    def save_diff(self, diff: DiffRecord) -> DiffRecord:
        with self._lock:
            for commit_id in (diff.ref.from_commit_id, diff.ref.to_commit_id):
                commit = self._commits.get(commit_id)
                if commit is None or commit.repository != diff.ref.repository:
                    raise RecordNotFoundError("diff commit not found")
            key = (diff.ref.repository.tenant_id, diff.ref.repository.repository_id, diff.ref.diff_id)
            existing = self._diffs.get(key)
            if existing is None:
                self._diffs[key] = self._copy(diff)
            elif existing != diff:
                raise RuntimeError("diff identifier collision")
            return self._copy(self._diffs[key])

    def get_diff(self, ref: DiffRef) -> DiffRecord | None:
        with self._lock:
            value = self._diffs.get((ref.repository.tenant_id, ref.repository.repository_id, ref.diff_id))
            return self._copy(value) if value else None

    def save_lineage(self, edge: LineageEdge) -> LineageEdge:
        with self._lock:
            for ref in (edge.upstream, edge.downstream):
                commit = self._commits.get(ref.commit_id)
                if commit is None or commit.ref != ref:
                    raise RecordNotFoundError("lineage endpoint not found")
            existing = self._lineage.get(edge.edge_id)
            if existing is None:
                self._lineage[edge.edge_id] = self._copy(edge)
            elif (
                existing.upstream,
                existing.downstream,
                existing.relation,
                existing.created_by,
            ) != (edge.upstream, edge.downstream, edge.relation, edge.created_by):
                raise RuntimeError("lineage identifier collision")
            return self._copy(self._lineage[edge.edge_id])

    def list_lineage(self, ref: CommitRef, direction: str) -> tuple[LineageEdge, ...]:
        if direction not in {"upstream", "downstream"}:
            raise ValueError("lineage direction must be upstream or downstream")
        with self._lock:
            if direction == "downstream":
                values = [edge for edge in self._lineage.values() if edge.upstream == ref]
            else:
                values = [edge for edge in self._lineage.values() if edge.downstream == ref]
            return tuple(self._copy(edge) for edge in sorted(values, key=lambda item: item.edge_id))


def _json_value(value):
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    return json.loads(value) if isinstance(value, str) else value


def _mapping(row, columns: tuple[str, ...]):
    return row if isinstance(row, dict) else dict(zip(columns, row, strict=True))


class SqlRevisionRepository:
    """OceanBase persistence with immutable rows and transactional branch CAS."""

    REPOSITORIES = "workmanship_base_revision_repositories"
    SNAPSHOTS = "workmanship_base_revision_snapshots"
    COMMITS = "workmanship_base_revision_commits"
    PARENTS = "workmanship_base_revision_commit_parents"
    BRANCHES = "workmanship_base_revision_branches"
    LINEAGE = "workmanship_base_revision_lineage_edges"
    CHANGESETS = "workmanship_base_revision_changesets"

    def __init__(self, connection_factory: Callable):
        self._connection_factory = connection_factory

    @staticmethod
    def _insert_snapshot(cursor, tenant_id: str, snapshot: Snapshot, created_at: datetime) -> None:
        cursor.execute(
            f"INSERT IGNORE INTO {SqlRevisionRepository.SNAPSHOTS} "
            "(tenant_id, snapshot_id, content_hash, byte_size, content_json, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (tenant_id, snapshot.snapshot_id, snapshot.content_hash, snapshot.byte_size,
             json.dumps(snapshot.content, ensure_ascii=False, sort_keys=True, separators=(",", ":")), created_at),
        )

    @staticmethod
    def _insert_commit(cursor, commit: Commit) -> None:
        cursor.execute(
            f"INSERT IGNORE INTO {SqlRevisionRepository.COMMITS} "
            "(tenant_id, repository_id, commit_id, snapshot_id, content_hash, author_id, message, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (commit.repository.tenant_id, commit.repository.repository_id, commit.commit_id,
             commit.snapshot.snapshot_id, commit.content_hash, commit.author_id, commit.message, commit.created_at),
        )
        for order, parent_id in enumerate(commit.parent_ids):
            cursor.execute(
                f"INSERT IGNORE INTO {SqlRevisionRepository.PARENTS} "
                "(tenant_id, repository_id, commit_id, parent_commit_id, parent_order) "
                "VALUES (%s, %s, %s, %s, %s)",
                (commit.repository.tenant_id, commit.repository.repository_id,
                 commit.commit_id, parent_id, order),
            )

    def initialize(self, ref: RepositoryRef, branch: BranchRef, commit: Commit) -> Branch:
        if branch.repository != ref or commit.repository != ref or commit.parent_ids:
            raise ValueError("initial commit must be a root in the same repository")
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.REPOSITORIES} "
                    "(tenant_id, repository_id, owner_domain, resource_id, created_at) VALUES (%s, %s, %s, %s, %s)",
                    (ref.tenant_id, ref.repository_id, ref.owner_domain, ref.resource_id, commit.created_at),
                )
                self._insert_snapshot(cursor, ref.tenant_id, commit.snapshot, commit.created_at)
                self._insert_commit(cursor, commit)
                cursor.execute(
                    f"INSERT INTO {self.BRANCHES} "
                    "(tenant_id, repository_id, branch_name, head_commit_id, is_protected, approval_policy, version, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, 0, NULL, 1, %s, %s)",
                    (ref.tenant_id, ref.repository_id, branch.name, commit.commit_id,
                     commit.created_at, commit.created_at),
                )
            conn.commit()
            return Branch(ref=branch, head_commit_id=commit.commit_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_repository(self, ref: RepositoryRef) -> None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.REPOSITORIES} "
                    "(tenant_id, repository_id, owner_domain, resource_id, created_at) VALUES (%s, %s, %s, %s, %s)",
                    (ref.tenant_id, ref.repository_id, ref.owner_domain, ref.resource_id, datetime.now(UTC)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def repository_exists(self, ref: RepositoryRef) -> bool:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT owner_domain, resource_id FROM {self.REPOSITORIES} WHERE tenant_id=%s AND repository_id=%s",
                    (ref.tenant_id, ref.repository_id),
                )
                row = cursor.fetchone()
            if row is None:
                return False
            value = _mapping(row, ("owner_domain", "resource_id"))
            return value["owner_domain"] == ref.owner_domain and value["resource_id"] == ref.resource_id
        finally:
            conn.close()

    def save_snapshot(self, tenant_id: str, snapshot: Snapshot) -> Snapshot:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                self._insert_snapshot(cursor, tenant_id, snapshot, datetime.now(UTC))
            conn.commit()
            return snapshot
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_snapshot(self, tenant_id: str, snapshot_id: str) -> Snapshot | None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT snapshot_id, content_hash, byte_size, content_json FROM {self.SNAPSHOTS} "
                    "WHERE tenant_id=%s AND snapshot_id=%s",
                    (tenant_id, snapshot_id),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            value = _mapping(row, ("snapshot_id", "content_hash", "byte_size", "content_json"))
            return Snapshot(
                snapshot_id=value["snapshot_id"], content_hash=value["content_hash"],
                byte_size=value["byte_size"], content=_json_value(value["content_json"]),
            )
        finally:
            conn.close()

    def get_commit(self, commit_id: str) -> Commit | None:
        conn = self._connection_factory()
        columns = (
            "tenant_id", "repository_id", "owner_domain", "resource_id", "commit_id",
            "snapshot_id", "content_hash", "byte_size", "content_json", "author_id", "message", "created_at",
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT c.tenant_id, c.repository_id, r.owner_domain, r.resource_id, c.commit_id, "
                    "c.snapshot_id, c.content_hash, s.byte_size, s.content_json, c.author_id, c.message, c.created_at "
                    f"FROM {self.COMMITS} c JOIN {self.REPOSITORIES} r ON r.tenant_id=c.tenant_id AND r.repository_id=c.repository_id "
                    f"JOIN {self.SNAPSHOTS} s ON s.tenant_id=c.tenant_id AND s.snapshot_id=c.snapshot_id "
                    "WHERE c.commit_id=%s",
                    (commit_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                value = _mapping(row, columns)
                cursor.execute(
                    f"SELECT parent_commit_id FROM {self.PARENTS} "
                    "WHERE tenant_id=%s AND repository_id=%s AND commit_id=%s ORDER BY parent_order",
                    (value["tenant_id"], value["repository_id"], commit_id),
                )
                parent_rows = cursor.fetchall()
            parents = tuple(
                item["parent_commit_id"] if isinstance(item, dict) else item[0]
                for item in parent_rows
            )
            repository = RepositoryRef(
                tenant_id=value["tenant_id"], repository_id=value["repository_id"],
                owner_domain=value["owner_domain"], resource_id=value["resource_id"],
            )
            snapshot = Snapshot(
                snapshot_id=value["snapshot_id"], content_hash=value["content_hash"],
                byte_size=value["byte_size"], content=_json_value(value["content_json"]),
            )
            return Commit(
                commit_id=value["commit_id"], repository=repository, parent_ids=parents,
                snapshot=snapshot, content_hash=value["content_hash"], author_id=value["author_id"],
                message=value["message"], created_at=value["created_at"],
            )
        finally:
            conn.close()

    def create_branch(self, branch: Branch) -> None:
        now = datetime.now(UTC)
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.BRANCHES} "
                    "(tenant_id, repository_id, branch_name, head_commit_id, is_protected, approval_policy, version, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (branch.ref.repository.tenant_id, branch.ref.repository.repository_id, branch.ref.name,
                     branch.head_commit_id, int(branch.protected), branch.approval_policy, branch.version, now, now),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_branch(self, ref: BranchRef) -> Branch | None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT head_commit_id, is_protected, approval_policy, version FROM {self.BRANCHES} "
                    "WHERE tenant_id=%s AND repository_id=%s AND branch_name=%s",
                    (ref.repository.tenant_id, ref.repository.repository_id, ref.name),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            value = _mapping(row, ("head_commit_id", "is_protected", "approval_policy", "version"))
            return Branch(
                ref=ref, head_commit_id=value["head_commit_id"], protected=bool(value["is_protected"]),
                approval_policy=value["approval_policy"], version=value["version"],
            )
        finally:
            conn.close()

    def append_commit(self, branch: BranchRef, commit: Commit, expected_head: str | None) -> Branch:
        if commit.repository != branch.repository:
            raise RecordNotFoundError("commit is outside branch repository")
        if not commit.parent_ids or commit.parent_ids[0] != expected_head:
            raise ValueError("commit first parent must equal the expected branch head")
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT head_commit_id, is_protected, approval_policy, version FROM {self.BRANCHES} "
                    "WHERE tenant_id=%s AND repository_id=%s AND branch_name=%s FOR UPDATE",
                    (branch.repository.tenant_id, branch.repository.repository_id, branch.name),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFoundError("branch not found")
                current = _mapping(row, ("head_commit_id", "is_protected", "approval_policy", "version"))
                if current["head_commit_id"] != (expected_head or ""):
                    raise CompareAndSwapError(expected_head or "", current["head_commit_id"])
                self._insert_snapshot(cursor, branch.repository.tenant_id, commit.snapshot, commit.created_at)
                self._insert_commit(cursor, commit)
                cursor.execute(
                    f"UPDATE {self.BRANCHES} SET head_commit_id=%s, version=version+1, updated_at=%s "
                    "WHERE tenant_id=%s AND repository_id=%s AND branch_name=%s AND version=%s",
                    (commit.commit_id, commit.created_at, branch.repository.tenant_id,
                     branch.repository.repository_id, branch.name, current["version"]),
                )
            conn.commit()
            return Branch(
                ref=branch, head_commit_id=commit.commit_id, protected=bool(current["is_protected"]),
                approval_policy=current["approval_policy"], version=current["version"] + 1,
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def protect_branch(self, ref: BranchRef, approval_policy: str) -> Branch:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT head_commit_id, version FROM {self.BRANCHES} "
                    "WHERE tenant_id=%s AND repository_id=%s AND branch_name=%s FOR UPDATE",
                    (ref.repository.tenant_id, ref.repository.repository_id, ref.name),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RecordNotFoundError("branch not found")
                current = _mapping(row, ("head_commit_id", "version"))
                cursor.execute(
                    f"UPDATE {self.BRANCHES} SET is_protected=1, approval_policy=%s, version=version+1, updated_at=%s "
                    "WHERE tenant_id=%s AND repository_id=%s AND branch_name=%s AND version=%s",
                    (approval_policy, datetime.now(UTC), ref.repository.tenant_id,
                     ref.repository.repository_id, ref.name, current["version"]),
                )
            conn.commit()
            return Branch(ref=ref, head_commit_id=current["head_commit_id"], protected=True,
                          approval_policy=approval_policy, version=current["version"] + 1)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_changeset(self, changeset: ChangeSet) -> ChangeSet:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT IGNORE INTO {self.CHANGESETS} "
                    "(tenant_id, repository_id, changeset_id, base_commit_id, changes_json, result_content_hash, created_by, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (changeset.ref.repository.tenant_id, changeset.ref.repository.repository_id,
                     changeset.ref.changeset_id, changeset.ref.base_commit_id,
                     json.dumps([item.model_dump(mode="json") for item in changeset.changes], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                     changeset.result_content_hash, changeset.created_by, changeset.created_at),
                )
            conn.commit()
            return changeset
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_changeset(self, ref: ChangeSetRef) -> ChangeSet | None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT changes_json, result_content_hash, created_by, created_at FROM {self.CHANGESETS} "
                    "WHERE tenant_id=%s AND repository_id=%s AND changeset_id=%s",
                    (ref.repository.tenant_id, ref.repository.repository_id, ref.changeset_id),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            value = _mapping(row, ("changes_json", "result_content_hash", "created_by", "created_at"))
            return ChangeSet(
                ref=ref, changes=tuple(_json_value(value["changes_json"])),
                result_content_hash=value["result_content_hash"],
                created_by=value["created_by"], created_at=value["created_at"],
            )
        finally:
            conn.close()

    def save_diff(self, diff: DiffRecord) -> DiffRecord:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT IGNORE INTO workmanship_base_revision_diffs "
                    "(tenant_id, repository_id, diff_id, from_commit_id, to_commit_id, changes_json, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (diff.ref.repository.tenant_id, diff.ref.repository.repository_id, diff.ref.diff_id,
                     diff.ref.from_commit_id, diff.ref.to_commit_id,
                     json.dumps([item.model_dump(mode="json") for item in diff.changes], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                     datetime.now(UTC)),
                )
            conn.commit()
            return diff
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_diff(self, ref: DiffRef) -> DiffRecord | None:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT changes_json FROM workmanship_base_revision_diffs "
                    "WHERE tenant_id=%s AND repository_id=%s AND diff_id=%s AND from_commit_id=%s AND to_commit_id=%s",
                    (ref.repository.tenant_id, ref.repository.repository_id, ref.diff_id,
                     ref.from_commit_id, ref.to_commit_id),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            value = _mapping(row, ("changes_json",))
            return DiffRecord(ref=ref, changes=tuple(_json_value(value["changes_json"])))
        finally:
            conn.close()

    def save_lineage(self, edge: LineageEdge) -> LineageEdge:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.LINEAGE} "
                    "(tenant_id, edge_id, upstream_repository_id, upstream_commit_id, downstream_repository_id, "
                    "downstream_commit_id, relation_type, created_by, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (edge.upstream.repository.tenant_id, edge.edge_id, edge.upstream.repository.repository_id,
                     edge.upstream.commit_id, edge.downstream.repository.repository_id, edge.downstream.commit_id,
                     edge.relation, edge.created_by, edge.created_at),
                )
            conn.commit()
            return edge
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_lineage(self, ref: CommitRef, direction: str) -> tuple[LineageEdge, ...]:
        if direction not in {"upstream", "downstream"}:
            raise ValueError("lineage direction must be upstream or downstream")
        endpoint_column = "upstream" if direction == "downstream" else "downstream"
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT e.edge_id, e.relation_type, e.created_by, e.created_at, "
                    "e.upstream_repository_id, e.upstream_commit_id, ur.owner_domain AS upstream_owner_domain, "
                    "ur.resource_id AS upstream_resource_id, uc.content_hash AS upstream_content_hash, "
                    "e.downstream_repository_id, e.downstream_commit_id, dr.owner_domain AS downstream_owner_domain, "
                    "dr.resource_id AS downstream_resource_id, dc.content_hash AS downstream_content_hash "
                    f"FROM {self.LINEAGE} e "
                    f"JOIN {self.REPOSITORIES} ur ON ur.tenant_id=e.tenant_id AND ur.repository_id=e.upstream_repository_id "
                    f"JOIN {self.REPOSITORIES} dr ON dr.tenant_id=e.tenant_id AND dr.repository_id=e.downstream_repository_id "
                    f"JOIN {self.COMMITS} uc ON uc.tenant_id=e.tenant_id AND uc.repository_id=e.upstream_repository_id AND uc.commit_id=e.upstream_commit_id "
                    f"JOIN {self.COMMITS} dc ON dc.tenant_id=e.tenant_id AND dc.repository_id=e.downstream_repository_id AND dc.commit_id=e.downstream_commit_id "
                    f"WHERE e.tenant_id=%s AND e.{endpoint_column}_repository_id=%s AND e.{endpoint_column}_commit_id=%s "
                    "ORDER BY e.edge_id",
                    (ref.repository.tenant_id, ref.repository.repository_id, ref.commit_id),
                )
                rows = cursor.fetchall()
            result = []
            for row in rows:
                value = row if isinstance(row, dict) else dict(row)
                upstream_repo = RepositoryRef(
                    tenant_id=ref.repository.tenant_id, repository_id=value["upstream_repository_id"],
                    owner_domain=value["upstream_owner_domain"], resource_id=value["upstream_resource_id"],
                )
                downstream_repo = RepositoryRef(
                    tenant_id=ref.repository.tenant_id, repository_id=value["downstream_repository_id"],
                    owner_domain=value["downstream_owner_domain"], resource_id=value["downstream_resource_id"],
                )
                result.append(LineageEdge(
                    edge_id=value["edge_id"],
                    upstream=CommitRef(repository=upstream_repo, commit_id=value["upstream_commit_id"], content_hash=value["upstream_content_hash"]),
                    downstream=CommitRef(repository=downstream_repo, commit_id=value["downstream_commit_id"], content_hash=value["downstream_content_hash"]),
                    relation=value["relation_type"], created_by=value["created_by"], created_at=value["created_at"],
                ))
            return tuple(result)
        finally:
            conn.close()
