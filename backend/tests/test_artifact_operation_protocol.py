from datetime import UTC, datetime, timedelta
from contextlib import contextmanager
import io
from pathlib import Path

import pytest

from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    OperationStatus,
    TenantIdentity,
)
from backend.capability_v2.artifacts import (
    ArtifactAuthorizationError,
    ArtifactIntegrityError,
    ArtifactService,
    InMemoryArtifactStore,
    InMemoryObjectStorage,
    SqlArtifactStore,
)
from backend.capability_v2.operations import (
    InMemoryOperationStore,
    OperationAuthorizationError,
    OperationService,
    SqlOperationStore,
    OperationTransitionError,
)


def identity(tenant: str = "tenant-a", user: str = "user-1") -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(
            user_id=user,
            authentication_method="test",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(tenant_id=tenant, membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.PLUGIN, consumer_id="plugin.example"),
    )


def test_artifact_hash_mismatch_is_rejected_and_session_is_not_finalized():
    storage = InMemoryObjectStorage()
    service = ArtifactService(InMemoryArtifactStore(), storage)
    session = service.create_upload(
        identity(), media_type="application/step", expected_sha256="0" * 64,
        expected_byte_size=3, resource_refs=("project:p1",),
    )
    with pytest.raises(ArtifactIntegrityError, match="sha256"):
        service.upload_stream(session.upload_id, identity(), io.BytesIO(b"cad"))

    with pytest.raises(ArtifactIntegrityError, match="not uploaded"):
        service.finalize(session.upload_id, identity(), reported_sha256="0" * 64)

    assert service.get_upload(session.upload_id, identity()).status == "pending"


def test_artifact_finalize_returns_immutable_ref_and_is_idempotent():
    storage = InMemoryObjectStorage()
    service = ArtifactService(InMemoryArtifactStore(), storage)
    digest = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    session = service.create_upload(
        identity(), media_type="application/octet-stream", expected_sha256=digest,
        expected_byte_size=3, resource_refs=("project:p1",),
    )
    service.upload_stream(session.upload_id, identity(), io.BytesIO(b"abc"))

    first = service.finalize(session.upload_id, identity(), reported_sha256=digest)
    second = service.finalize(session.upload_id, identity(), reported_sha256=digest)

    assert first == second
    assert first.sha256 == digest
    assert first.byte_size == 3
    assert service.authorize_download(first.artifact_id, identity()).object_key == session.object_key


def test_host_mediated_upload_verifies_stream_before_storage_write():
    storage = InMemoryObjectStorage()
    service = ArtifactService(InMemoryArtifactStore(), storage)
    digest = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    session = service.create_upload(
        identity(), media_type="application/octet-stream", expected_sha256=digest,
        expected_byte_size=3,
    )
    with pytest.raises(ArtifactIntegrityError, match="sha256"):
        service.upload_stream(session.upload_id, identity(), io.BytesIO(b"abd"))
    with pytest.raises(ArtifactIntegrityError, match="missing"):
        storage.stat(session.object_key)

    service.upload_stream(session.upload_id, identity(), io.BytesIO(b"abc"))
    assert service.finalize(session.upload_id, identity(), reported_sha256=digest).sha256 == digest


def test_ois_stream_upload_preserves_host_selected_object_key(monkeypatch):
    from backend.core import ois_storage

    class _Data:
        object_key = "capability-artifacts/tenant-a/upload_1"

    class _Response:
        data = _Data()

        @staticmethod
        def is_succeed():
            return True

    class _Client:
        def put_object(self, bucket, key, stream):
            assert bucket == "bucket-1"
            assert key == _Data.object_key
            assert stream.read() == b"abc"
            return _Response()

    monkeypatch.setattr(ois_storage, "is_enabled", lambda: True)
    monkeypatch.setattr(ois_storage, "_get_ois_config", lambda: {"identify": "bucket-1"})
    monkeypatch.setattr(ois_storage, "_make_client", lambda: (_Client(), None))
    assert ois_storage.put_immutable_stream(_Data.object_key, io.BytesIO(b"abc")) == _Data.object_key


def test_artifact_access_is_tenant_and_resource_scoped():
    storage = InMemoryObjectStorage()
    service = ArtifactService(InMemoryArtifactStore(), storage)
    session = service.create_upload(
        identity(), media_type="text/plain",
        expected_sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        expected_byte_size=3, resource_refs=("project:p1",),
    )
    service.upload_stream(session.upload_id, identity(), io.BytesIO(b"abc"))
    ref = service.finalize(session.upload_id, identity(), reported_sha256=session.expected_sha256)

    with pytest.raises(ArtifactAuthorizationError):
        service.authorize_download(ref.artifact_id, identity("tenant-b"))
    with pytest.raises(ArtifactAuthorizationError):
        service.authorize_download(ref.artifact_id, identity(user="user-2"))
    with pytest.raises(ArtifactAuthorizationError):
        service.authorize_download(ref.artifact_id, identity(), granted_resources=("project:p2",))
    assert service.authorize_download(
        ref.artifact_id, identity(), granted_resources=("project:p1",)
    ).artifact_ref == ref
    assert service.authorize_download(
        ref.artifact_id, identity(user="user-2"), granted_resources=("project:*",)
    ).artifact_ref == ref


def test_expired_upload_cannot_be_finalized():
    now = datetime(2026, 8, 10, tzinfo=UTC)
    storage = InMemoryObjectStorage()
    service = ArtifactService(InMemoryArtifactStore(), storage, clock=lambda: now)
    session = service.create_upload(
        identity(), media_type="text/plain",
        expected_sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        expected_byte_size=3, expires_in=timedelta(seconds=1),
    )
    storage.put(session.object_key, b"abc")
    service._clock = lambda: now + timedelta(seconds=2)
    with pytest.raises(ArtifactIntegrityError, match="expired"):
        service.finalize(session.upload_id, identity(), reported_sha256=session.expected_sha256)


def test_operation_cannot_skip_from_accepted_to_completed_without_policy():
    service = OperationService(InMemoryOperationStore())
    op = service.create(kind="device.command", requested_by=identity(), resource_refs=("device:d1",))
    with pytest.raises(OperationTransitionError):
        service.transition(
            op.operation_id, OperationStatus.COMPLETED,
            expected_version=op.version, requested_by=identity(),
        )


def test_operation_transition_uses_cas_and_preserves_terminal_state():
    service = OperationService(InMemoryOperationStore())
    op = service.create(kind="simulation.run", requested_by=identity())
    claimed = service.transition(
        op.operation_id, OperationStatus.CLAIMED,
        expected_version=1, requested_by=identity(),
    )
    with pytest.raises(OperationTransitionError, match="version"):
        service.transition(
            op.operation_id, OperationStatus.PREPARING,
            expected_version=1, requested_by=identity(),
        )
    preparing = service.transition(
        op.operation_id, OperationStatus.PREPARING,
        expected_version=claimed.version, requested_by=identity(),
    )
    running = service.transition(
        op.operation_id, OperationStatus.RUNNING,
        expected_version=preparing.version, requested_by=identity(),
    )
    post = service.transition(
        op.operation_id, OperationStatus.POST_PROCESSING,
        expected_version=running.version, requested_by=identity(),
    )
    completed = service.transition(
        op.operation_id, OperationStatus.COMPLETED,
        expected_version=post.version, requested_by=identity(),
    )
    with pytest.raises(OperationTransitionError):
        service.transition(
            op.operation_id, OperationStatus.FAILED,
            expected_version=completed.version, requested_by=identity(),
        )


def test_operation_read_and_transition_are_tenant_scoped():
    service = OperationService(InMemoryOperationStore())
    op = service.create(
        kind="device.command", requested_by=identity(), resource_refs=("device:d1",)
    )
    with pytest.raises(OperationAuthorizationError):
        service.get_authorized(op.operation_id, identity("tenant-b"))
    with pytest.raises(OperationAuthorizationError):
        service.get_authorized(op.operation_id, identity(user="user-2"))
    with pytest.raises(OperationAuthorizationError):
        service.get_authorized(
            op.operation_id, identity(), granted_resources=("device:d2",)
        )
    assert service.get_authorized(
        op.operation_id, identity(), granted_resources=("device:d1",)
    ).ref.operation_id == op.operation_id
    assert service.get_authorized(
        op.operation_id, identity(user="user-2"), granted_resources=("*",)
    ).ref.operation_id == op.operation_id
    claimed = service.transition(
        op.operation_id, OperationStatus.CLAIMED, expected_version=op.version,
        requested_by=identity(user="worker-1"), granted_resources=("device:d1",),
    )
    assert claimed.status is OperationStatus.CLAIMED


class _Cursor:
    def __init__(self):
        self.statements = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.statements.append((" ".join(sql.split()), params))


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _connections(cursor):
    @contextmanager
    def factory():
        yield _Connection(cursor)
    return factory


def test_sql_stores_persist_tenant_resource_and_cas_metadata():
    artifact_cursor = _Cursor()
    artifact_service = ArtifactService(
        SqlArtifactStore(_connections(artifact_cursor)), InMemoryObjectStorage()
    )
    artifact_service.create_upload(
        identity(), media_type="text/plain", expected_sha256="a" * 64,
        expected_byte_size=4, resource_refs=("project:p1",),
    )
    upload_sql, upload_params = artifact_cursor.statements[0]
    assert "tenant_id" in upload_sql and "resource_refs_json" in upload_sql
    assert "project:p1" in upload_params[7]

    operation_cursor = _Cursor()
    operation_service = OperationService(SqlOperationStore(_connections(operation_cursor)))
    operation_service.create(
        kind="simulation.run", requested_by=identity(), resource_refs=("project:p1",)
    )
    operation_sql, operation_params = operation_cursor.statements[0]
    assert "operation_version" in operation_sql and "resource_refs_json" in operation_sql
    assert "project:p1" in operation_params[5]


def test_artifact_operation_migration_is_base_owned_and_contains_required_indexes():
    root = Path(__file__).resolve().parents[2]
    path = root / "backend/db/migrations/202608100004_base_artifacts_and_operations.sql"
    sql = path.read_text(encoding="utf-8").lower()
    assert "workmanship_base_artifact_upload_sessions" in sql
    assert "workmanship_base_artifacts" in sql
    assert "workmanship_base_capability_operations" in sql
    assert "unique key uq_base_artifact_object" in sql
    assert "operation_version" in sql


def test_artifact_and_operation_http_adapters_expose_only_governed_routes():
    from fastapi import FastAPI
    from backend.routers.capability_artifacts import router as artifact_router
    from backend.routers.capability_operations import router as operation_router

    app = FastAPI()
    app.include_router(artifact_router)
    app.include_router(operation_router)
    paths = app.openapi()["paths"]
    assert "/api/v2/capability-artifacts/uploads" in paths
    assert "/api/v2/capability-artifacts/uploads/{upload_id}/content" in paths
    assert "/api/v2/capability-artifacts/uploads/{upload_id}:finalize" in paths
    assert list(paths["/api/v2/capability-operations/{operation_id}"]) == ["get"]
