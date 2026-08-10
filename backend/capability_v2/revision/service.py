"""Application service for immutable history, branches, diff and merge."""
from __future__ import annotations

import hashlib
import secrets
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Callable, Mapping, Any, Protocol

from .canonical import canonical_json_bytes
from .diff import DomainRevisionAdapter
from .merge import three_way_merge
from .models import (
    Branch,
    BranchApprovalChallenge,
    BranchRef,
    BaselineRef,
    ChangeSet,
    ChangeSetRef,
    Commit,
    CommitOutcome,
    DiffRecord,
    DiffRef,
    LineageEdge,
    LineageGraph,
    MergeResult,
    RepositoryRef,
    Snapshot,
)
from .repository import (
    CompareAndSwapError,
    RecordNotFoundError,
    RepositoryExistsError,
    RevisionRepository,
)


class RevisionNotFoundError(LookupError):
    pass


class BranchConflictError(RuntimeError):
    def __init__(self, expected_head: str, actual_head: str) -> None:
        super().__init__("branch head changed; reload before retrying")
        self.expected_head = expected_head
        self.actual_head = actual_head


class ProtectedBranchError(RuntimeError):
    pass


class SnapshotTooLargeError(ValueError):
    pass


class ChangeSetTooLargeError(ValueError):
    pass


class BranchApprovalVerifier(Protocol):
    def consume(self, approval_reference: str, challenge: BranchApprovalChallenge) -> bool: ...


class DenyBranchApprovalVerifier:
    def consume(self, approval_reference: str, challenge: BranchApprovalChallenge) -> bool:
        return False


class InMemoryBranchApprovalVerifier:
    """One-time verifier for tests/local development; production injects the approval service."""

    def __init__(self) -> None:
        self._records: dict[str, BranchApprovalChallenge] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _hash(reference: str) -> str:
        return hashlib.sha256(reference.encode("utf-8")).hexdigest()

    def issue(self, challenge: BranchApprovalChallenge, *, approved_by: str) -> str:
        if not approved_by.strip():
            raise ValueError("approved_by is required")
        reference = f"bar_{secrets.token_urlsafe(32)}"
        with self._lock:
            self._records[self._hash(reference)] = challenge
        return reference

    def consume(self, approval_reference: str, challenge: BranchApprovalChallenge) -> bool:
        with self._lock:
            stored = self._records.pop(self._hash(approval_reference), None)
            return stored == challenge


class RevisionService:
    def __init__(
        self,
        repository: RevisionRepository,
        adapter: DomainRevisionAdapter,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        approvals: BranchApprovalVerifier | None = None,
        max_snapshot_bytes: int = 4 * 1024 * 1024,
        max_changes_per_commit: int = 10000,
    ) -> None:
        if max_snapshot_bytes < 64:
            raise ValueError("max_snapshot_bytes must be at least 64")
        if max_changes_per_commit < 1 or max_changes_per_commit > 100000:
            raise ValueError("max_changes_per_commit must be between 1 and 100000")
        self._repository = repository
        self._adapter = adapter
        self._clock = clock
        self._approvals = approvals or DenyBranchApprovalVerifier()
        self._max_snapshot_bytes = max_snapshot_bytes
        self._max_changes_per_commit = max_changes_per_commit

    def _bounded_changes(self, before, after):
        changes = self._adapter.diff(before, after)
        if len(changes) > self._max_changes_per_commit:
            raise ChangeSetTooLargeError(
                "synchronous revision exceeds change-count policy; use an asynchronous Operation"
            )
        return changes

    @staticmethod
    def _digest(value: Any) -> str:
        return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

    def _snapshot(self, content: Mapping[str, Any]) -> Snapshot:
        normalized = self._adapter.normalize(content)
        data = canonical_json_bytes(normalized)
        if len(data) > self._max_snapshot_bytes:
            raise SnapshotTooLargeError(
                "inline revision snapshot exceeds policy; store large data as ArtifactRef"
            )
        digest = hashlib.sha256(data).hexdigest()
        return Snapshot(
            snapshot_id=f"snp_{digest[:32]}",
            content_hash=f"sha256:{digest}",
            byte_size=len(data),
            content=normalized,
        )

    def _commit_record(
        self,
        *,
        repository: RepositoryRef,
        parents: tuple[str, ...],
        snapshot: Snapshot,
        author_id: str,
        message: str,
    ) -> Commit:
        document = {
            "format": "ai00.revision.commit.v1",
            "repository": repository.model_dump(mode="json"),
            "parents": list(parents),
            "snapshot_id": snapshot.snapshot_id,
            "content_hash": snapshot.content_hash,
            "author_id": author_id,
            "message": message.strip(),
        }
        digest = self._digest(document)
        return Commit(
            commit_id=f"cmt_{digest[:40]}",
            repository=repository,
            parent_ids=parents,
            snapshot=snapshot,
            content_hash=snapshot.content_hash,
            author_id=author_id,
            message=message.strip(),
            created_at=self._clock(),
        )

    def initialize(
        self,
        *,
        repository: RepositoryRef,
        branch: str,
        content: Mapping[str, Any],
        author_id: str,
        message: str,
    ) -> CommitOutcome:
        branch_ref = BranchRef(repository=repository, name=branch)
        snapshot = self._snapshot(content)
        commit = self._commit_record(
            repository=repository,
            parents=(),
            snapshot=snapshot,
            author_id=author_id,
            message=message,
        )
        self._repository.initialize(repository, branch_ref, commit)
        return CommitOutcome(branch=branch_ref, commit=commit)

    def create_branch(self, *, repository: RepositoryRef, name: str, from_commit: str) -> BranchRef:
        ref = BranchRef(repository=repository, name=name)
        commit = self.get_commit(from_commit, repository=repository)
        try:
            self._repository.create_branch(Branch(ref=ref, head_commit_id=commit.commit_id))
        except (RecordNotFoundError, RepositoryExistsError) as exc:
            raise RevisionNotFoundError(str(exc)) from exc
        return ref

    def commit(
        self,
        *,
        branch: BranchRef,
        content: Mapping[str, Any],
        expected_head: str,
        author_id: str,
        message: str,
        additional_parent: str | None = None,
    ) -> CommitOutcome:
        return self._write_commit(
            branch=branch,
            content=content,
            expected_head=expected_head,
            author_id=author_id,
            message=message,
            additional_parent=additional_parent,
            allow_protected=False,
        )

    def _write_commit(
        self,
        *,
        branch: BranchRef,
        content: Mapping[str, Any],
        expected_head: str,
        author_id: str,
        message: str,
        additional_parent: str | None,
        allow_protected: bool,
    ) -> CommitOutcome:
        branch_record = self._repository.get_branch(branch)
        if branch_record is None:
            raise RevisionNotFoundError("branch not found")
        if branch_record.protected and not allow_protected:
            raise ProtectedBranchError("protected branch accepts only an approved merge")
        current = self.get_commit(expected_head, repository=branch.repository)
        self._adapter.validate_changeset(current.snapshot.content, content)
        self._bounded_changes(current.snapshot.content, content)
        snapshot = self._snapshot(content)
        parents = (expected_head,) if additional_parent is None else (expected_head, additional_parent)
        if additional_parent is not None:
            self.get_commit(additional_parent, repository=branch.repository)
        commit = self._commit_record(
            repository=branch.repository,
            parents=parents,
            snapshot=snapshot,
            author_id=author_id,
            message=message,
        )
        try:
            self._repository.append_commit(branch, commit, expected_head)
        except CompareAndSwapError as exc:
            raise BranchConflictError(exc.expected, exc.actual) from exc
        except RecordNotFoundError as exc:
            raise RevisionNotFoundError(str(exc)) from exc
        return CommitOutcome(branch=branch, commit=commit)

    def restore(
        self,
        *,
        branch: BranchRef,
        source_commit: str,
        expected_head: str,
        author_id: str,
        message: str,
    ) -> CommitOutcome:
        source = self.get_commit(source_commit, repository=branch.repository)
        return self.commit(
            branch=branch,
            content=source.snapshot.content,
            expected_head=expected_head,
            author_id=author_id,
            message=message,
        )

    def get_commit(self, commit_id: str, *, repository: RepositoryRef | None = None) -> Commit:
        commit = self._repository.get_commit(commit_id)
        if commit is None or (repository is not None and commit.repository != repository):
            raise RevisionNotFoundError("commit not found in repository scope")
        return commit

    def baseline(self, repository: RepositoryRef, commit_id: str) -> BaselineRef:
        self.get_commit(commit_id, repository=repository)
        return BaselineRef(repository=repository, commit_id=commit_id)

    def head(self, branch: BranchRef) -> Commit:
        record = self._repository.get_branch(branch)
        if record is None:
            raise RevisionNotFoundError("branch not found")
        return self.get_commit(record.head_commit_id, repository=branch.repository)

    def history(self, branch: BranchRef, *, limit: int = 1000) -> tuple[str, ...]:
        if limit < 1 or limit > 10000:
            raise ValueError("history limit must be between 1 and 10000")
        result: list[str] = []
        commit = self.head(branch)
        while len(result) < limit:
            result.append(commit.commit_id)
            if not commit.parent_ids:
                break
            commit = self.get_commit(commit.parent_ids[0], repository=branch.repository)
        return tuple(result)

    def diff(self, repository: RepositoryRef, from_commit: str, to_commit: str) -> DiffRecord:
        before = self.get_commit(from_commit, repository=repository)
        after = self.get_commit(to_commit, repository=repository)
        changes = self._bounded_changes(before.snapshot.content, after.snapshot.content)
        digest = self._digest({
            "format": "ai00.revision.diff.v1",
            "repository": before.repository.model_dump(mode="json"),
            "from": from_commit,
            "to": to_commit,
            "changes": [item.model_dump(mode="json") for item in changes],
        })
        diff = DiffRecord(
            ref=DiffRef(
                repository=before.repository,
                diff_id=f"dif_{digest[:32]}",
                from_commit_id=from_commit,
                to_commit_id=to_commit,
            ),
            changes=changes,
        )
        try:
            return self._repository.save_diff(diff)
        except RecordNotFoundError as exc:
            raise RevisionNotFoundError(str(exc)) from exc

    def get_diff(self, ref: DiffRef) -> DiffRecord:
        diff = self._repository.get_diff(ref)
        if diff is None:
            raise RevisionNotFoundError("diff not found in repository scope")
        return diff

    def create_changeset(
        self,
        *,
        repository: RepositoryRef,
        base_commit: str,
        proposed_content: Mapping[str, Any],
        created_by: str,
    ) -> ChangeSet:
        base = self.get_commit(base_commit, repository=repository)
        proposed = self._adapter.normalize(proposed_content)
        self._adapter.validate_changeset(base.snapshot.content, proposed)
        changes = self._bounded_changes(base.snapshot.content, proposed)
        result_digest = hashlib.sha256(canonical_json_bytes(proposed)).hexdigest()
        document = {
            "format": "ai00.revision.changeset.v1",
            "repository": repository.model_dump(mode="json"),
            "base_commit": base_commit,
            "changes": [item.model_dump(mode="json") for item in changes],
            "result_content_hash": f"sha256:{result_digest}",
            "created_by": created_by,
        }
        digest = self._digest(document)
        changeset = ChangeSet(
            ref=ChangeSetRef(
                repository=repository,
                changeset_id=f"chg_{digest[:32]}",
                base_commit_id=base_commit,
            ),
            changes=changes,
            result_content_hash=f"sha256:{result_digest}",
            created_by=created_by,
            created_at=self._clock(),
        )
        try:
            return self._repository.save_changeset(changeset)
        except RecordNotFoundError as exc:
            raise RevisionNotFoundError(str(exc)) from exc

    def get_changeset(self, ref: ChangeSetRef) -> ChangeSet:
        changeset = self._repository.get_changeset(ref)
        if changeset is None:
            raise RevisionNotFoundError("changeset not found in repository scope")
        return changeset

    def apply_changeset(
        self,
        *,
        branch: BranchRef,
        changeset: ChangeSet | ChangeSetRef,
        expected_head: str,
        author_id: str,
        message: str,
    ) -> CommitOutcome:
        resolved = self.get_changeset(changeset) if isinstance(changeset, ChangeSetRef) else changeset
        if resolved.ref.repository != branch.repository:
            raise ValueError("changeset belongs to a different repository")
        if resolved.ref.base_commit_id != expected_head:
            raise BranchConflictError(resolved.ref.base_commit_id, expected_head)
        base = self.get_commit(expected_head, repository=branch.repository)
        content = self._adapter.apply_changeset(base.snapshot.content, resolved.changes)
        digest = hashlib.sha256(canonical_json_bytes(content)).hexdigest()
        if f"sha256:{digest}" != resolved.result_content_hash:
            raise ValueError("changeset result hash mismatch")
        return self.commit(
            branch=branch,
            content=content,
            expected_head=expected_head,
            author_id=author_id,
            message=message,
        )

    def protect_branch(self, branch: BranchRef, *, approval_policy: str) -> None:
        policy = approval_policy.strip()
        if not policy:
            raise ValueError("approval policy is required")
        try:
            self._repository.protect_branch(branch, policy)
        except RecordNotFoundError as exc:
            raise RevisionNotFoundError(str(exc)) from exc

    def _ancestors(self, start: Commit) -> dict[str, int]:
        distances: dict[str, int] = {}
        queue = deque([(start, 0)])
        while queue:
            commit, distance = queue.popleft()
            if commit.commit_id in distances and distances[commit.commit_id] <= distance:
                continue
            distances[commit.commit_id] = distance
            for parent in commit.parent_ids:
                queue.append((self.get_commit(parent, repository=start.repository), distance + 1))
        return distances

    def _merge_base(self, ours: Commit, theirs: Commit) -> Commit:
        ours_ancestors = self._ancestors(ours)
        theirs_ancestors = self._ancestors(theirs)
        common = set(ours_ancestors) & set(theirs_ancestors)
        if not common:
            raise RevisionNotFoundError("branches have no common ancestor")
        commit_id = min(common, key=lambda item: (max(ours_ancestors[item], theirs_ancestors[item]), ours_ancestors[item] + theirs_ancestors[item], item))
        return self.get_commit(commit_id, repository=ours.repository)

    def merge(
        self,
        *,
        source: BranchRef,
        target: BranchRef,
        expected_target_head: str,
        author_id: str,
        message: str,
        approval_reference: str | None = None,
    ) -> MergeResult:
        if source.repository != target.repository:
            raise ValueError("cannot merge across repositories")
        source_head = self.head(source)
        target_head = self.head(target)
        if target_head.commit_id != expected_target_head:
            raise BranchConflictError(expected_target_head, target_head.commit_id)
        base = self._merge_base(target_head, source_head)
        merged_content, conflicts = three_way_merge(
            base.snapshot.content,
            target_head.snapshot.content,
            source_head.snapshot.content,
            self._adapter,
        )
        if conflicts:
            return MergeResult(status="conflicted", conflicts=conflicts)
        assert merged_content is not None
        target_record = self._repository.get_branch(target)
        assert target_record is not None
        if target_record.protected:
            document = {
                "repository": target.repository.model_dump(mode="json"),
                "target_branch": target.name,
                "target_head": target_head.commit_id,
                "source_head": source_head.commit_id,
                "policy": target_record.approval_policy,
            }
            challenge = BranchApprovalChallenge(
                challenge_id=f"bra_{self._digest(document)[:32]}",
                repository=target.repository,
                target_branch=target.name,
                target_head=target_head.commit_id,
                source_head=source_head.commit_id,
                policy=target_record.approval_policy or "maintainer",
            )
            if approval_reference is None or not self._approvals.consume(approval_reference, challenge):
                return MergeResult(status="approval_required", approval=challenge)
        outcome = self._write_commit(
            branch=target,
            content=merged_content,
            expected_head=expected_target_head,
            additional_parent=source_head.commit_id,
            author_id=author_id,
            message=message,
            allow_protected=True,
        )
        return MergeResult(status="merged", commit=outcome.commit)

    def link_lineage(
        self,
        *,
        upstream,
        downstream,
        relation: str,
        created_by: str,
    ) -> LineageEdge:
        if upstream.repository.tenant_id != downstream.repository.tenant_id:
            raise ValueError("lineage cannot cross tenants")
        self.get_commit(upstream.commit_id, repository=upstream.repository)
        self.get_commit(downstream.commit_id, repository=downstream.repository)
        self._assert_lineage_acyclic(upstream, downstream)
        document = {
            "format": "ai00.revision.lineage.v1",
            "upstream": upstream.model_dump(mode="json"),
            "downstream": downstream.model_dump(mode="json"),
            "relation": relation,
            "created_by": created_by,
        }
        edge = LineageEdge(
            edge_id=f"lin_{self._digest(document)[:32]}",
            upstream=upstream,
            downstream=downstream,
            relation=relation,
            created_by=created_by,
            created_at=self._clock(),
        )
        try:
            return self._repository.save_lineage(edge)
        except RecordNotFoundError as exc:
            raise RevisionNotFoundError(str(exc)) from exc

    def _assert_lineage_acyclic(self, upstream, downstream) -> None:
        queue = deque([downstream])
        visited: set[tuple[str, str, str]] = set()
        examined_edges = 0
        while queue:
            current = queue.popleft()
            key = (
                current.repository.tenant_id,
                current.repository.repository_id,
                current.commit_id,
            )
            if key in visited:
                continue
            visited.add(key)
            if current == upstream:
                raise ValueError("lineage edge would create a cycle")
            for edge in self._repository.list_lineage(current, "downstream"):
                examined_edges += 1
                if examined_edges > 10000:
                    raise ValueError("lineage graph exceeds safe cycle-check bound")
                queue.append(edge.downstream)

    def lineage(
        self,
        root,
        *,
        direction: str,
        max_depth: int = 5,
        max_edges: int = 500,
    ) -> LineageGraph:
        if direction not in {"upstream", "downstream"}:
            raise ValueError("lineage direction must be upstream or downstream")
        if max_depth < 1 or max_depth > 20:
            raise ValueError("lineage max_depth must be between 1 and 20")
        if max_edges < 1 or max_edges > 1000:
            raise ValueError("lineage max_edges must be between 1 and 1000")
        self.get_commit(root.commit_id, repository=root.repository)
        queue = deque([(root, 0)])
        visited_nodes = {f"{root.repository.tenant_id}:{root.repository.repository_id}:{root.commit_id}"}
        visited_edges: set[str] = set()
        edges: list[LineageEdge] = []
        truncated = False
        while queue:
            current, depth = queue.popleft()
            direct = self._repository.list_lineage(current, direction)
            if depth >= max_depth:
                truncated = truncated or bool(direct)
                continue
            for edge in direct:
                if edge.edge_id in visited_edges:
                    continue
                if len(edges) >= max_edges:
                    truncated = True
                    queue.clear()
                    break
                visited_edges.add(edge.edge_id)
                edges.append(edge)
                next_ref = edge.downstream if direction == "downstream" else edge.upstream
                node_key = f"{next_ref.repository.tenant_id}:{next_ref.repository.repository_id}:{next_ref.commit_id}"
                if node_key not in visited_nodes:
                    visited_nodes.add(node_key)
                    queue.append((next_ref, depth + 1))
        return LineageGraph(root=root, direction=direction, edges=tuple(edges), truncated=truncated)
