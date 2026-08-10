"""Tenant-scoped, integrity-checked artifact references for Capability V2."""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import BinaryIO, Callable, Literal, Protocol

from .contracts import ArtifactRef, ConsumerIdentity, FrozenModel


class ArtifactError(RuntimeError):
    pass


class ArtifactIntegrityError(ArtifactError):
    pass


class ArtifactAuthorizationError(ArtifactError):
    pass


class UploadSession(FrozenModel):
    upload_id: str
    tenant_id: str
    actor_id: str
    object_key: str
    media_type: str
    expected_sha256: str
    expected_byte_size: int
    resource_refs: tuple[str, ...] = ()
    status: Literal["pending", "uploaded", "completed", "expired"] = "pending"
    uploaded_sha256: str | None = None
    uploaded_byte_size: int | None = None
    artifact_id: str | None = None
    created_at: datetime
    expires_at: datetime


class ArtifactRecord(FrozenModel):
    artifact_ref: ArtifactRef
    tenant_id: str
    actor_id: str
    object_key: str
    resource_refs: tuple[str, ...] = ()
    created_at: datetime


class ArtifactStore(Protocol):
    def create_upload(self, session: UploadSession) -> UploadSession: ...
    def get_upload(self, upload_id: str) -> UploadSession: ...
    def mark_uploaded(self, upload_id: str, sha256: str, byte_size: int) -> UploadSession: ...
    def finalize(self, upload_id: str, record: ArtifactRecord) -> ArtifactRecord: ...
    def get_artifact(self, artifact_id: str) -> ArtifactRecord: ...


class ObjectStorage(Protocol):
    def put_stream(self, object_key: str, stream: BinaryIO) -> None: ...
    def stat(self, object_key: str) -> tuple[str, int]: ...


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put(self, object_key: str, data: bytes) -> None:
        self._objects[object_key] = bytes(data)

    def put_stream(self, object_key: str, stream: BinaryIO) -> None:
        self.put(object_key, stream.read())

    def stat(self, object_key: str) -> tuple[str, int]:
        try:
            data = self._objects[object_key]
        except KeyError as exc:
            raise ArtifactIntegrityError("artifact object is missing") from exc
        return hashlib.sha256(data).hexdigest(), len(data)


class OisObjectStorage:
    """OIS adapter that preserves host-generated immutable object keys."""

    def put_stream(self, object_key: str, stream: BinaryIO) -> None:
        from backend.core.ois_storage import put_immutable_stream

        uploaded_key = put_immutable_stream(object_key, stream)
        if uploaded_key != object_key:
            raise ArtifactError("object storage rejected immutable stream upload")

    def stat(self, object_key: str) -> tuple[str, int]:
        from backend.core.ois_storage import get_immutable

        data = get_immutable(object_key)
        if data is None:
            raise ArtifactIntegrityError("artifact object is missing")
        return hashlib.sha256(data).hexdigest(), len(data)


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._uploads: dict[str, UploadSession] = {}
        self._artifacts: dict[str, ArtifactRecord] = {}
        self._lock = threading.Lock()

    def create_upload(self, session: UploadSession) -> UploadSession:
        with self._lock:
            if session.upload_id in self._uploads:
                raise ArtifactError("upload_session_exists")
            self._uploads[session.upload_id] = session
            return session

    def get_upload(self, upload_id: str) -> UploadSession:
        with self._lock:
            try:
                return self._uploads[upload_id]
            except KeyError as exc:
                raise ArtifactError("upload_session_not_found") from exc

    def mark_uploaded(self, upload_id: str, sha256: str, byte_size: int) -> UploadSession:
        with self._lock:
            try:
                session = self._uploads[upload_id]
            except KeyError as exc:
                raise ArtifactError("upload_session_not_found") from exc
            if session.status == "uploaded":
                if (session.uploaded_sha256, session.uploaded_byte_size) != (sha256, byte_size):
                    raise ArtifactIntegrityError("upload metadata conflict")
                return session
            if session.status != "pending":
                raise ArtifactIntegrityError("upload session is not pending")
            uploaded = session.model_copy(update={
                "status": "uploaded", "uploaded_sha256": sha256,
                "uploaded_byte_size": byte_size,
            })
            self._uploads[upload_id] = uploaded
            return uploaded

    def finalize(self, upload_id: str, record: ArtifactRecord) -> ArtifactRecord:
        with self._lock:
            try:
                session = self._uploads[upload_id]
            except KeyError as exc:
                raise ArtifactError("upload_session_not_found") from exc
            if session.status == "completed":
                if session.artifact_id != record.artifact_ref.artifact_id:
                    raise ArtifactIntegrityError("upload already finalized with another artifact")
                return self._artifacts[session.artifact_id]
            if session.status != "uploaded":
                raise ArtifactIntegrityError("upload session is not uploaded")
            self._artifacts[record.artifact_ref.artifact_id] = record
            self._uploads[upload_id] = session.model_copy(update={
                "status": "completed", "artifact_id": record.artifact_ref.artifact_id,
            })
            return record

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        with self._lock:
            try:
                return self._artifacts[artifact_id]
            except KeyError as exc:
                raise ArtifactError("artifact_not_found") from exc


class SqlArtifactStore:
    UPLOAD_TABLE = "workmanship_base_artifact_upload_sessions"
    ARTIFACT_TABLE = "workmanship_base_artifacts"

    def __init__(self, connection_context_factory) -> None:
        self._connections = connection_context_factory

    def create_upload(self, session: UploadSession) -> UploadSession:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.UPLOAD_TABLE} "
                    "(upload_id,tenant_id,actor_id,object_key,media_type,expected_sha256,"
                    "expected_byte_size,resource_refs_json,status,artifact_id,created_at,expires_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        session.upload_id, session.tenant_id, session.actor_id,
                        session.object_key, session.media_type, session.expected_sha256,
                        session.expected_byte_size, json.dumps(session.resource_refs),
                        session.status, session.artifact_id, session.created_at, session.expires_at,
                    ),
                )
        return session

    def get_upload(self, upload_id: str) -> UploadSession:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {self.UPLOAD_TABLE} WHERE upload_id=%s", (upload_id,)
                )
                row = cursor.fetchone()
        if not row:
            raise ArtifactError("upload_session_not_found")
        return _upload_from_row(row)

    def mark_uploaded(self, upload_id: str, sha256: str, byte_size: int) -> UploadSession:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {self.UPLOAD_TABLE} SET status='uploaded',uploaded_sha256=%s,"
                    "uploaded_byte_size=%s WHERE upload_id=%s AND status='pending'",
                    (sha256, byte_size, upload_id),
                )
                if cursor.rowcount != 1:
                    cursor.execute(
                        f"SELECT * FROM {self.UPLOAD_TABLE} WHERE upload_id=%s", (upload_id,)
                    )
                    row = cursor.fetchone()
                    if not row:
                        raise ArtifactError("upload_session_not_found")
                    existing = _upload_from_row(row)
                    if existing.status != "uploaded" or (
                        existing.uploaded_sha256, existing.uploaded_byte_size
                    ) != (sha256, byte_size):
                        raise ArtifactIntegrityError("upload metadata conflict")
                    return existing
        return self.get_upload(upload_id)

    def finalize(self, upload_id: str, record: ArtifactRecord) -> ArtifactRecord:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {self.UPLOAD_TABLE} WHERE upload_id=%s FOR UPDATE",
                    (upload_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise ArtifactError("upload_session_not_found")
                session = _upload_from_row(row)
                if session.status == "completed" and session.artifact_id:
                    cursor.execute(
                        f"SELECT * FROM {self.ARTIFACT_TABLE} WHERE artifact_id=%s",
                        (session.artifact_id,),
                    )
                    existing = cursor.fetchone()
                    if not existing:
                        raise ArtifactIntegrityError("completed upload has no artifact")
                    return _artifact_from_row(existing)
                if session.status != "uploaded":
                    raise ArtifactIntegrityError("upload session is not uploaded")
                ref = record.artifact_ref
                cursor.execute(
                    f"INSERT INTO {self.ARTIFACT_TABLE} "
                    "(artifact_id,tenant_id,actor_id,object_key,media_type,sha256,byte_size,"
                    "artifact_version,resource_refs_json,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        ref.artifact_id, record.tenant_id, record.actor_id, record.object_key,
                        ref.media_type, ref.sha256, ref.byte_size, ref.version,
                        json.dumps(record.resource_refs), record.created_at,
                    ),
                )
                cursor.execute(
                    f"UPDATE {self.UPLOAD_TABLE} SET status='completed',artifact_id=%s "
                    "WHERE upload_id=%s AND status='uploaded'",
                    (ref.artifact_id, upload_id),
                )
                if cursor.rowcount != 1:
                    raise ArtifactIntegrityError("upload finalization race")
        return record

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {self.ARTIFACT_TABLE} WHERE artifact_id=%s", (artifact_id,)
                )
                row = cursor.fetchone()
        if not row:
            raise ArtifactError("artifact_not_found")
        return _artifact_from_row(row)


class ArtifactService:
    def __init__(self, store: ArtifactStore, storage: ObjectStorage, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._store = store
        self._storage = storage
        self._clock = clock

    def create_upload(
        self,
        requested_by: ConsumerIdentity,
        *,
        media_type: str,
        expected_sha256: str,
        expected_byte_size: int,
        resource_refs: tuple[str, ...] = (),
        expires_in: timedelta = timedelta(minutes=15),
    ) -> UploadSession:
        if not _valid_sha256(expected_sha256):
            raise ArtifactIntegrityError("expected_sha256 must be lowercase SHA-256")
        if expected_byte_size < 0:
            raise ArtifactIntegrityError("expected_byte_size cannot be negative")
        if not media_type or len(media_type) > 255:
            raise ArtifactIntegrityError("invalid media_type")
        if expires_in <= timedelta(0) or expires_in > timedelta(hours=24):
            raise ArtifactIntegrityError("invalid upload expiry")
        upload_id = f"upload_{uuid.uuid4().hex}"
        now = self._clock()
        session = UploadSession(
            upload_id=upload_id,
            tenant_id=requested_by.tenant.tenant_id,
            actor_id=_actor_id(requested_by),
            object_key=f"capability-artifacts/{requested_by.tenant.tenant_id}/{upload_id}",
            media_type=media_type,
            expected_sha256=expected_sha256,
            expected_byte_size=expected_byte_size,
            resource_refs=tuple(sorted(set(resource_refs))),
            created_at=now,
            expires_at=now + expires_in,
        )
        return self._store.create_upload(session)

    def upload_stream(self, upload_id: str, requested_by: ConsumerIdentity,
                      stream: BinaryIO) -> None:
        """Copy a client stream to the host-selected key after size/hash verification."""
        import tempfile

        session = self._store.get_upload(upload_id)
        _authorize(session.tenant_id, session.actor_id, session.resource_refs, requested_by, ())
        if session.status != "pending" or self._clock() >= session.expires_at:
            raise ArtifactIntegrityError("upload session expired or closed")
        digest = hashlib.sha256()
        size = 0
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as verified:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > session.expected_byte_size:
                    raise ArtifactIntegrityError("uploaded object exceeds expected byte size")
                digest.update(chunk)
                verified.write(chunk)
            if size != session.expected_byte_size:
                raise ArtifactIntegrityError("uploaded object byte size mismatch")
            if digest.hexdigest() != session.expected_sha256:
                raise ArtifactIntegrityError("uploaded object sha256 mismatch")
            verified.seek(0)
            self._storage.put_stream(session.object_key, verified)
        self._store.mark_uploaded(upload_id, digest.hexdigest(), size)

    def get_upload(self, upload_id: str, requested_by: ConsumerIdentity) -> UploadSession:
        session = self._store.get_upload(upload_id)
        _authorize(session.tenant_id, session.actor_id, session.resource_refs, requested_by, ())
        return session

    def finalize(self, upload_id: str, requested_by: ConsumerIdentity, *,
                 reported_sha256: str) -> ArtifactRef:
        session = self._store.get_upload(upload_id)
        _authorize(session.tenant_id, session.actor_id, session.resource_refs, requested_by, ())
        if session.status == "completed" and session.artifact_id:
            return self._store.get_artifact(session.artifact_id).artifact_ref
        if self._clock() >= session.expires_at:
            raise ArtifactIntegrityError("upload session expired")
        if reported_sha256 != session.expected_sha256:
            raise ArtifactIntegrityError("reported sha256 differs from upload contract")
        if session.status != "uploaded":
            raise ArtifactIntegrityError("upload session is not uploaded")
        actual_sha256 = session.uploaded_sha256 or ""
        actual_size = session.uploaded_byte_size
        if actual_sha256 != session.expected_sha256:
            raise ArtifactIntegrityError("uploaded object sha256 mismatch")
        if actual_size != session.expected_byte_size:
            raise ArtifactIntegrityError("uploaded object byte size mismatch")
        artifact_id = f"artifact_{uuid.uuid5(uuid.NAMESPACE_URL, session.upload_id).hex}"
        ref = ArtifactRef(
            artifact_id=artifact_id,
            media_type=session.media_type,
            sha256=actual_sha256,
            byte_size=actual_size,
        )
        record = ArtifactRecord(
            artifact_ref=ref,
            tenant_id=session.tenant_id,
            actor_id=session.actor_id,
            object_key=session.object_key,
            resource_refs=session.resource_refs,
            created_at=self._clock(),
        )
        return self._store.finalize(upload_id, record).artifact_ref

    def authorize_download(
        self,
        artifact_id: str,
        requested_by: ConsumerIdentity,
        *,
        granted_resources: tuple[str, ...] = (),
    ) -> ArtifactRecord:
        record = self._store.get_artifact(artifact_id)
        _authorize(
            record.tenant_id, record.actor_id, record.resource_refs,
            requested_by, granted_resources,
        )
        return record


def _actor_id(identity: ConsumerIdentity) -> str:
    return identity.actor.user_id or identity.actor.service_id or ""


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and value == value.lower() and all(c in "0123456789abcdef" for c in value)


def _json_tuple(value) -> tuple[str, ...]:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        value = json.loads(value)
    return tuple(value or ())


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _upload_from_row(row) -> UploadSession:
    return UploadSession(
        upload_id=row["upload_id"], tenant_id=row["tenant_id"], actor_id=row["actor_id"],
        object_key=row["object_key"], media_type=row["media_type"],
        expected_sha256=row["expected_sha256"],
        expected_byte_size=int(row["expected_byte_size"]),
        resource_refs=_json_tuple(row.get("resource_refs_json")), status=row["status"],
        uploaded_sha256=row.get("uploaded_sha256"),
        uploaded_byte_size=(
            int(row["uploaded_byte_size"]) if row.get("uploaded_byte_size") is not None else None
        ),
        artifact_id=row.get("artifact_id"), created_at=_as_utc(row["created_at"]),
        expires_at=_as_utc(row["expires_at"]),
    )


def _artifact_from_row(row) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_ref=ArtifactRef(
            artifact_id=row["artifact_id"], media_type=row["media_type"],
            sha256=row["sha256"], byte_size=int(row["byte_size"]),
            version=int(row["artifact_version"]),
        ),
        tenant_id=row["tenant_id"], actor_id=row["actor_id"], object_key=row["object_key"],
        resource_refs=_json_tuple(row.get("resource_refs_json")),
        created_at=_as_utc(row["created_at"]),
    )


def _authorize(tenant_id: str, actor_id: str, resource_refs: tuple[str, ...],
               identity: ConsumerIdentity, granted_resources: tuple[str, ...]) -> None:
    if identity.tenant.tenant_id != tenant_id:
        raise ArtifactAuthorizationError("artifact belongs to another tenant")
    same_actor = _actor_id(identity) == actor_id
    if not same_actor and not granted_resources:
        raise ArtifactAuthorizationError("artifact access requires owner or resource grant")
    if not resource_refs and not same_actor:
        raise ArtifactAuthorizationError("private artifact belongs to another actor")
    if granted_resources and not _scopes_allow(granted_resources, resource_refs):
        raise ArtifactAuthorizationError("artifact resource scope is not granted")


def _scopes_allow(granted: tuple[str, ...], requested: tuple[str, ...]) -> bool:
    return all(
        "*" in granted or ref in granted or f"{ref.split(':', 1)[0]}:*" in granted
        for ref in requested
    )


__all__ = [
    "ArtifactAuthorizationError", "ArtifactError", "ArtifactIntegrityError",
    "ArtifactRecord", "ArtifactService", "ArtifactStore", "InMemoryArtifactStore",
    "InMemoryObjectStorage", "ObjectStorage", "OisObjectStorage", "SqlArtifactStore",
    "UploadSession",
]
