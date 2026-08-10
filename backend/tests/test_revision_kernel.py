from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capability_v2.revision.diff import JsonDocumentAdapter
from backend.capability_v2.revision.models import Commit, RepositoryRef, Snapshot
from backend.capability_v2.revision.repository import (
    CompareAndSwapError,
    InMemoryRevisionRepository,
    SqlRevisionRepository,
)
from backend.capability_v2.revision.service import (
    BranchConflictError,
    InMemoryBranchApprovalVerifier,
    ProtectedBranchError,
    RevisionNotFoundError,
    RevisionService,
    SnapshotTooLargeError,
    ChangeSetTooLargeError,
)


GOLDEN = Path(__file__).parent / "golden" / "revision"


def _golden(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


@pytest.fixture
def service() -> RevisionService:
    return RevisionService(InMemoryRevisionRepository(), JsonDocumentAdapter())


@pytest.fixture
def repository() -> RepositoryRef:
    return RepositoryRef(
        tenant_id="tenant-a",
        repository_id="repo-routing-1",
        owner_domain="craft",
        resource_id="bop-routing-1",
    )


def _initialize(service: RevisionService, repository: RepositoryRef, content: dict):
    return service.initialize(
        repository=repository,
        branch="main",
        content=content,
        author_id="user-1",
        message="initial",
    )


def test_linear_history_is_immutable_and_content_addressed(service, repository):
    case = _golden("linear-history.json")
    first = _initialize(service, repository, case["snapshots"][0])
    second = service.commit(
        branch=first.branch,
        content=case["snapshots"][1],
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="rename operation",
    )
    third = service.commit(
        branch=first.branch,
        content=case["snapshots"][2],
        expected_head=second.commit.commit_id,
        author_id="user-2",
        message="set duration",
    )

    assert service.history(first.branch) == (
        third.commit.commit_id,
        second.commit.commit_id,
        first.commit.commit_id,
    )
    assert service.get_commit(first.commit.commit_id).snapshot.content == case["snapshots"][0]
    assert len({first.commit.commit_id, second.commit.commit_id, third.commit.commit_id}) == 3
    assert first.commit.content_hash.startswith("sha256:")


def test_same_normalized_snapshot_has_same_hash_across_key_order(service, repository):
    first = _initialize(service, repository, {"name": "工序", "meta": {"b": 2, "a": 1}})
    branch = service.create_branch(
        repository=repository,
        name="equivalent",
        from_commit=first.commit.commit_id,
    )
    second = service.commit(
        branch=branch,
        content={"meta": {"a": 1, "b": 2}, "name": "工序"},
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="canonical equivalent",
    )

    assert second.commit.content_hash == first.commit.content_hash
    assert second.commit.snapshot.snapshot_id == first.commit.snapshot.snapshot_id


def test_branch_update_requires_expected_head(service, repository):
    first = _initialize(service, repository, {"value": 1})
    service.commit(
        branch=first.branch,
        content={"value": 2},
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="winner",
    )

    with pytest.raises(BranchConflictError) as error:
        service.commit(
            branch=first.branch,
            content={"value": 3},
            expected_head=first.commit.commit_id,
            author_id="user-2",
            message="stale writer",
        )

    assert error.value.actual_head != first.commit.commit_id


def test_restore_creates_new_commit_without_rewriting_history(service, repository):
    first = _initialize(service, repository, {"value": 1})
    second = service.commit(
        branch=first.branch,
        content={"value": 2},
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="second",
    )
    original_hash = service.get_commit(first.commit.commit_id).content_hash

    restored = service.restore(
        branch=first.branch,
        source_commit=first.commit.commit_id,
        expected_head=second.commit.commit_id,
        author_id="user-1",
        message="restore first",
    )

    assert restored.commit.parent_ids == (second.commit.commit_id,)
    assert restored.commit.content_hash == original_hash
    assert service.get_commit(first.commit.commit_id).content_hash == original_hash
    assert service.history(first.branch) == (
        restored.commit.commit_id,
        second.commit.commit_id,
        first.commit.commit_id,
    )


def test_repository_and_commit_reads_are_tenant_scoped(service, repository):
    first = _initialize(service, repository, {"classified": True})
    other_tenant_ref = repository.model_copy(update={"tenant_id": "tenant-b"})

    with pytest.raises(RevisionNotFoundError):
        service.get_commit(first.commit.commit_id, repository=other_tenant_ref)


def test_structured_diff_reports_move_in_identity_array(service, repository):
    before = {"steps": [{"stable_gid": "cut", "name": "切割"}, {"stable_gid": "weld", "name": "焊接"}]}
    after = {"steps": [{"stable_gid": "weld", "name": "焊接"}, {"stable_gid": "cut", "name": "切割"}]}
    first = _initialize(service, repository, before)
    second = service.commit(
        branch=first.branch,
        content=after,
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="reorder",
    )

    diff = service.diff(repository, first.commit.commit_id, second.commit.commit_id)

    assert [(item.change_type, item.path, item.identity) for item in diff.changes] == [
        ("move", "/steps", "cut"),
        ("move", "/steps", "weld"),
    ]
    assert service.get_diff(diff.ref) == diff


def test_three_way_merge_preserves_independent_changes(service, repository):
    first = _initialize(service, repository, {"name": "A", "duration": 10})
    feature = service.create_branch(repository=repository, name="feature", from_commit=first.commit.commit_id)
    service.commit(
        branch=feature,
        content={"name": "B", "duration": 10},
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="rename",
    )
    main = service.commit(
        branch=first.branch,
        content={"name": "A", "duration": 20},
        expected_head=first.commit.commit_id,
        author_id="user-2",
        message="duration",
    )

    merged = service.merge(
        source=feature,
        target=first.branch,
        expected_target_head=main.commit.commit_id,
        author_id="user-3",
        message="merge feature",
    )

    assert merged.status == "merged"
    assert merged.conflicts == ()
    assert merged.commit is not None
    assert merged.commit.parent_ids == (main.commit.commit_id, service.head(feature).commit_id)
    assert merged.commit.snapshot.content == {"name": "B", "duration": 20}


def test_three_way_merge_returns_field_conflict_without_moving_target(service, repository):
    case = _golden("three-way-field-conflict.json")
    first = _initialize(service, repository, case["base"])
    feature = service.create_branch(repository=repository, name="feature", from_commit=first.commit.commit_id)
    feature_head = service.commit(
        branch=feature,
        content=case["theirs"],
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="feature edit",
    )
    main_head = service.commit(
        branch=first.branch,
        content=case["ours"],
        expected_head=first.commit.commit_id,
        author_id="user-2",
        message="main edit",
    )

    result = service.merge(
        source=feature,
        target=first.branch,
        expected_target_head=main_head.commit.commit_id,
        author_id="user-3",
        message="conflicting merge",
    )

    assert result.status == "conflicted"
    assert result.commit is None
    assert [item.model_dump(mode="json") for item in result.conflicts] == case["conflicts"]
    assert service.head(first.branch).commit_id == main_head.commit.commit_id
    assert service.head(feature).commit_id == feature_head.commit.commit_id


def test_protected_branch_requires_bound_approval_before_merge(service, repository):
    case = _golden("protected-branch-approval.json")
    first = _initialize(service, repository, {"value": 1})
    feature = service.create_branch(repository=repository, name="feature", from_commit=first.commit.commit_id)
    feature_head = service.commit(
        branch=feature,
        content={"value": 2},
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="change",
    )
    service.protect_branch(first.branch, approval_policy=case["approval_policy"])

    result = service.merge(
        source=feature,
        target=first.branch,
        expected_target_head=first.commit.commit_id,
        author_id="user-2",
        message="merge protected",
    )

    assert result.status == "approval_required"
    assert result.commit is None
    assert result.approval is not None
    assert result.approval.policy == case["approval_policy"]
    assert result.approval.target_head == first.commit.commit_id
    assert result.approval.source_head == feature_head.commit.commit_id
    assert service.head(first.branch).commit_id == first.commit.commit_id


def test_protected_branch_approval_is_bound_and_consumed_once(repository):
    approvals = InMemoryBranchApprovalVerifier()
    service = RevisionService(InMemoryRevisionRepository(), JsonDocumentAdapter(), approvals=approvals)
    first = _initialize(service, repository, {"value": 1})
    feature = service.create_branch(repository=repository, name="feature", from_commit=first.commit.commit_id)
    service.commit(
        branch=feature,
        content={"value": 2},
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="change",
    )
    service.protect_branch(first.branch, approval_policy="maintainer")
    challenge = service.merge(
        source=feature,
        target=first.branch,
        expected_target_head=first.commit.commit_id,
        author_id="user-2",
        message="merge protected",
    ).approval
    assert challenge is not None
    approval_reference = approvals.issue(challenge, approved_by="maintainer-1")

    merged = service.merge(
        source=feature,
        target=first.branch,
        expected_target_head=first.commit.commit_id,
        author_id="user-2",
        message="merge protected",
        approval_reference=approval_reference,
    )

    assert merged.status == "merged"
    with pytest.raises(BranchConflictError):
        service.merge(
            source=feature,
            target=first.branch,
            expected_target_head=first.commit.commit_id,
            author_id="user-2",
            message="replay approval",
            approval_reference=approval_reference,
        )


def test_protected_branch_rejects_direct_commit_and_restore(service, repository):
    first = _initialize(service, repository, {"value": 1})
    service.protect_branch(first.branch, approval_policy="maintainer")

    with pytest.raises(ProtectedBranchError):
        service.commit(
            branch=first.branch,
            content={"value": 2},
            expected_head=first.commit.commit_id,
            author_id="user-1",
            message="bypass merge review",
        )


def test_failed_initialization_does_not_reserve_repository(service, repository):
    with pytest.raises((TypeError, ValueError)):
        _initialize(service, repository, {"unsupported": object()})

    initialized = _initialize(service, repository, {"value": 1})

    assert service.head(initialized.branch).commit_id == initialized.commit.commit_id


def test_diff_requires_explicit_repository_scope(service, repository):
    first = _initialize(service, repository, {"value": 1})
    other_repo = repository.model_copy(update={"tenant_id": "tenant-b", "repository_id": "other"})

    with pytest.raises(RevisionNotFoundError):
        service.diff(other_repo, first.commit.commit_id, first.commit.commit_id)


def test_branch_names_and_cross_repository_parents_are_rejected(service, repository):
    first = _initialize(service, repository, {"value": 1})
    with pytest.raises(ValueError):
        service.create_branch(repository=repository, name="../main", from_commit=first.commit.commit_id)

    other = repository.model_copy(update={"repository_id": "repo-other", "resource_id": "other"})
    other_first = _initialize(service, other, {"value": 9})
    with pytest.raises(RevisionNotFoundError):
        service.create_branch(
            repository=repository,
            name="foreign",
            from_commit=other_first.commit.commit_id,
        )


def test_lineage_connects_stable_commit_refs_without_cross_domain_imports(service, repository):
    craft = _initialize(service, repository, {"route": "v1"})
    model_repo = RepositoryRef(
        tenant_id=repository.tenant_id,
        repository_id="repo-model-1",
        owner_domain="digital-model",
        resource_id="model-1",
    )
    model = _initialize(service, model_repo, {"assembly": "v4"})
    simulation_repo = RepositoryRef(
        tenant_id=repository.tenant_id,
        repository_id="repo-simulation-1",
        owner_domain="simulation",
        resource_id="run-1",
    )
    simulation = _initialize(service, simulation_repo, {"result": "artifact-1"})
    service.link_lineage(
        upstream=craft.commit.ref,
        downstream=model.commit.ref,
        relation="derived_from",
        created_by="user-1",
    )
    service.link_lineage(
        upstream=model.commit.ref,
        downstream=simulation.commit.ref,
        relation="consumed_by",
        created_by="user-1",
    )

    graph = service.lineage(craft.commit.ref, direction="downstream", max_depth=2)

    assert [edge.downstream.repository.owner_domain for edge in graph.edges] == [
        "digital-model",
        "simulation",
    ]
    assert graph.truncated is False


def test_lineage_rejects_cross_tenant_edges(service, repository):
    first = _initialize(service, repository, {"value": 1})
    other_repo = repository.model_copy(update={
        "tenant_id": "tenant-b",
        "repository_id": "repo-other-tenant",
        "resource_id": "other-tenant-resource",
    })
    other = _initialize(service, other_repo, {"value": 2})

    with pytest.raises(ValueError):
        service.link_lineage(
            upstream=first.commit.ref,
            downstream=other.commit.ref,
            relation="derived_from",
            created_by="user-1",
        )


class _SqlCursor:
    def __init__(self, connection):
        self.connection = connection
        self.response = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.connection.statements.append((" ".join(sql.split()), params))
        self.response = self.connection.responses.pop(0) if self.connection.responses else None
        self.rowcount = 1

    def fetchone(self):
        return self.response

    def fetchall(self):
        return self.response or []


class _SqlConnection:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.statements = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return _SqlCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_sql_repository_initializes_repository_snapshot_commit_and_branch_atomically(service, repository):
    outcome = _initialize(service, repository, {"value": 1})
    connection = _SqlConnection()
    sql = SqlRevisionRepository(lambda: connection)

    sql.initialize(repository, outcome.branch, outcome.commit)

    assert connection.committed is True
    assert connection.rolled_back is False
    assert connection.closed is True
    assert [statement.split()[0] for statement, _ in connection.statements] == [
        "INSERT", "INSERT", "INSERT", "INSERT"
    ]


def test_sql_repository_locks_and_rejects_stale_branch_before_writing(service, repository):
    outcome = _initialize(service, repository, {"value": 1})
    candidate = service.commit(
        branch=outcome.branch,
        content={"value": 2},
        expected_head=outcome.commit.commit_id,
        author_id="user-1",
        message="candidate",
    )
    connection = _SqlConnection(responses=[{
        "head_commit_id": "cmt_" + "f" * 40,
        "is_protected": 0,
        "approval_policy": None,
        "version": 2,
    }])
    sql = SqlRevisionRepository(lambda: connection)

    with pytest.raises(CompareAndSwapError, match="branch head changed"):
        sql.append_commit(outcome.branch, candidate.commit, outcome.commit.commit_id)

    assert connection.rolled_back is True
    assert connection.committed is False
    assert len(connection.statements) == 1
    assert "FOR UPDATE" in connection.statements[0][0]


def test_changeset_is_content_addressed_and_round_trips_through_adapter(service, repository):
    first = _initialize(service, repository, {
        "name": "route-a",
        "steps": [{"stable_gid": "cut", "duration": 10}, {"stable_gid": "weld", "duration": 20}],
    })
    proposed = {
        "name": "route-b",
        "steps": [{"stable_gid": "weld", "duration": 25}, {"stable_gid": "cut", "duration": 10}],
    }

    changeset = service.create_changeset(
        repository=repository,
        base_commit=first.commit.commit_id,
        proposed_content=proposed,
        created_by="user-1",
    )
    restored_changeset = service.get_changeset(changeset.ref)
    applied = service.apply_changeset(
        branch=first.branch,
        changeset=changeset.ref,
        expected_head=first.commit.commit_id,
        author_id="user-1",
        message="apply reviewed changes",
    )

    assert changeset.ref.changeset_id.startswith("chg_")
    assert restored_changeset == changeset
    assert applied.commit.snapshot.content == proposed
    assert service.diff(repository, first.commit.commit_id, applied.commit.commit_id).changes == changeset.changes


def test_changeset_cannot_be_applied_to_a_different_base(service, repository):
    first = _initialize(service, repository, {"value": 1})
    changeset = service.create_changeset(
        repository=repository,
        base_commit=first.commit.commit_id,
        proposed_content={"value": 2},
        created_by="user-1",
    )
    current = service.commit(
        branch=first.branch,
        content={"value": 3},
        expected_head=first.commit.commit_id,
        author_id="user-2",
        message="concurrent edit",
    )

    with pytest.raises(BranchConflictError):
        service.apply_changeset(
            branch=first.branch,
            changeset=changeset,
            expected_head=current.commit.commit_id,
            author_id="user-1",
            message="stale changeset",
        )


def test_snapshot_and_commit_records_reject_content_address_tampering(service, repository):
    outcome = _initialize(service, repository, {"value": 1})
    snapshot_data = outcome.commit.snapshot.model_dump(mode="python")
    snapshot_data["content"] = {"value": 999}
    with pytest.raises(ValueError, match="snapshot_content_hash_mismatch"):
        Snapshot.model_validate(snapshot_data)

    commit_data = outcome.commit.model_dump(mode="python")
    commit_data["message"] = "tampered after persistence"
    with pytest.raises(ValueError, match="commit_id_mismatch"):
        Commit.model_validate(commit_data)


def test_inline_snapshot_size_is_bounded_and_large_data_must_use_artifact_ref(repository):
    service = RevisionService(
        InMemoryRevisionRepository(), JsonDocumentAdapter(), max_snapshot_bytes=192,
    )

    with pytest.raises(SnapshotTooLargeError):
        _initialize(service, repository, {"inline_geometry": "x" * 256})

    outcome = _initialize(service, repository, {
        "geometry_artifact_ref": {"artifact_id": "artifact-1", "sha256": "a" * 64}
    })
    assert outcome.commit.snapshot.byte_size <= 192


def test_lineage_rejects_cycles(service, repository):
    first = _initialize(service, repository, {"value": 1})
    second_repo = repository.model_copy(update={"repository_id": "repo-second", "resource_id": "second"})
    second = _initialize(service, second_repo, {"value": 2})
    service.link_lineage(
        upstream=first.commit.ref,
        downstream=second.commit.ref,
        relation="derived_from",
        created_by="user-1",
    )

    with pytest.raises(ValueError, match="cycle"):
        service.link_lineage(
            upstream=second.commit.ref,
            downstream=first.commit.ref,
            relation="derived_from",
            created_by="user-1",
        )


def test_baseline_ref_is_repository_scoped(service, repository):
    first = _initialize(service, repository, {"value": 1})

    baseline = service.baseline(repository, first.commit.commit_id)

    assert baseline.repository == repository
    assert baseline.commit_id == first.commit.commit_id


def test_commit_change_count_is_bounded_for_synchronous_consumers(repository):
    service = RevisionService(
        InMemoryRevisionRepository(), JsonDocumentAdapter(), max_changes_per_commit=1,
    )
    first = _initialize(service, repository, {"a": 1, "b": 1})

    with pytest.raises(ChangeSetTooLargeError):
        service.commit(
            branch=first.branch,
            content={"a": 2, "b": 2},
            expected_head=first.commit.commit_id,
            author_id="user-1",
            message="too many synchronous changes",
        )
