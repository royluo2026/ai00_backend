"""Tenant-scoped asynchronous operation state machine for Capability V2."""
from __future__ import annotations

import threading
import uuid
import json
from datetime import UTC, datetime
from typing import Callable, Protocol

from .contracts import ConsumerIdentity, FrozenModel, OperationRef, OperationStatus


class OperationError(RuntimeError):
    pass


class OperationTransitionError(OperationError):
    pass


class OperationAuthorizationError(OperationError):
    pass


class OperationRecord(FrozenModel):
    ref: OperationRef
    kind: str
    tenant_id: str
    actor_id: str
    consumer_id: str
    resource_refs: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None


class OperationStore(Protocol):
    def create(self, record: OperationRecord) -> OperationRecord: ...
    def get(self, operation_id: str) -> OperationRecord: ...
    def compare_and_swap(self, operation_id: str, expected_version: int,
                         replacement: OperationRecord) -> OperationRecord: ...


class InMemoryOperationStore:
    def __init__(self) -> None:
        self._records: dict[str, OperationRecord] = {}
        self._lock = threading.Lock()

    def create(self, record: OperationRecord) -> OperationRecord:
        with self._lock:
            if record.ref.operation_id in self._records:
                raise OperationError("operation_exists")
            self._records[record.ref.operation_id] = record
            return record

    def get(self, operation_id: str) -> OperationRecord:
        with self._lock:
            try:
                return self._records[operation_id]
            except KeyError as exc:
                raise OperationError("operation_not_found") from exc

    def compare_and_swap(self, operation_id: str, expected_version: int,
                         replacement: OperationRecord) -> OperationRecord:
        with self._lock:
            try:
                current = self._records[operation_id]
            except KeyError as exc:
                raise OperationError("operation_not_found") from exc
            if current.ref.version != expected_version:
                raise OperationTransitionError("operation version conflict")
            self._records[operation_id] = replacement
            return replacement


class SqlOperationStore:
    TABLE = "workmanship_base_capability_operations"

    def __init__(self, connection_context_factory) -> None:
        self._connections = connection_context_factory

    def create(self, record: OperationRecord) -> OperationRecord:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.TABLE} "
                    "(operation_id,kind,tenant_id,actor_id,consumer_id,resource_refs_json,"
                    "status,operation_version,error_code,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        record.ref.operation_id, record.kind, record.tenant_id, record.actor_id,
                        record.consumer_id, json.dumps(record.resource_refs),
                        record.ref.status.value, record.ref.version, record.error_code,
                        record.created_at, record.updated_at,
                    ),
                )
        return record

    def get(self, operation_id: str) -> OperationRecord:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM {self.TABLE} WHERE operation_id=%s", (operation_id,))
                row = cursor.fetchone()
        if not row:
            raise OperationError("operation_not_found")
        return _operation_from_row(row)

    def compare_and_swap(self, operation_id: str, expected_version: int,
                         replacement: OperationRecord) -> OperationRecord:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {self.TABLE} SET status=%s,operation_version=%s,error_code=%s,"
                    "updated_at=%s WHERE operation_id=%s AND operation_version=%s",
                    (
                        replacement.ref.status.value, replacement.ref.version,
                        replacement.error_code, replacement.updated_at,
                        operation_id, expected_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise OperationTransitionError("operation version conflict")
        return replacement


_TRANSITIONS: dict[OperationStatus, frozenset[OperationStatus]] = {
    OperationStatus.ACCEPTED: frozenset({
        OperationStatus.CLAIMED, OperationStatus.CANCELLED, OperationStatus.FAILED,
    }),
    OperationStatus.CLAIMED: frozenset({
        OperationStatus.PREPARING, OperationStatus.CANCELLED, OperationStatus.FAILED,
    }),
    OperationStatus.PREPARING: frozenset({
        OperationStatus.RUNNING, OperationStatus.CANCELLED, OperationStatus.FAILED,
    }),
    OperationStatus.RUNNING: frozenset({
        OperationStatus.POST_PROCESSING, OperationStatus.CANCELLED,
        OperationStatus.FAILED, OperationStatus.OUTCOME_UNKNOWN,
    }),
    OperationStatus.POST_PROCESSING: frozenset({
        OperationStatus.COMPLETED, OperationStatus.FAILED,
        OperationStatus.OUTCOME_UNKNOWN,
    }),
    OperationStatus.OUTCOME_UNKNOWN: frozenset({
        OperationStatus.COMPLETED, OperationStatus.FAILED, OperationStatus.CANCELLED,
    }),
    OperationStatus.COMPLETED: frozenset(),
    OperationStatus.FAILED: frozenset(),
    OperationStatus.CANCELLED: frozenset(),
}


class OperationService:
    def __init__(self, store: OperationStore, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._store = store
        self._clock = clock

    def create(self, *, kind: str, requested_by: ConsumerIdentity,
               resource_refs: tuple[str, ...] = ()) -> OperationRef:
        if not kind or len(kind) > 128:
            raise OperationError("invalid operation kind")
        now = self._clock()
        ref = OperationRef(
            operation_id=f"operation_{uuid.uuid4().hex}",
            status=OperationStatus.ACCEPTED,
        )
        record = OperationRecord(
            ref=ref,
            kind=kind,
            tenant_id=requested_by.tenant.tenant_id,
            actor_id=_actor_id(requested_by),
            consumer_id=requested_by.consumer.consumer_id,
            resource_refs=tuple(sorted(set(resource_refs))),
            created_at=now,
            updated_at=now,
        )
        return self._store.create(record).ref

    def transition(
        self,
        operation_id: str,
        status: OperationStatus,
        *,
        expected_version: int,
        requested_by: ConsumerIdentity,
        error_code: str | None = None,
        granted_resources: tuple[str, ...] = (),
    ) -> OperationRef:
        record = self.get_authorized(
            operation_id, requested_by, granted_resources=granted_resources
        )
        current = record.ref.status
        if status not in _TRANSITIONS[current]:
            raise OperationTransitionError(
                f"invalid operation transition: {current.value} -> {status.value}"
            )
        if status is OperationStatus.FAILED and not error_code:
            raise OperationTransitionError("failed operation requires error_code")
        replacement = record.model_copy(update={
            "ref": record.ref.model_copy(update={
                "status": status, "version": record.ref.version + 1,
            }),
            "updated_at": self._clock(),
            "error_code": error_code,
        })
        return self._store.compare_and_swap(
            operation_id, expected_version, replacement
        ).ref

    def get_authorized(
        self,
        operation_id: str,
        requested_by: ConsumerIdentity,
        *,
        granted_resources: tuple[str, ...] = (),
    ) -> OperationRecord:
        record = self._store.get(operation_id)
        if record.tenant_id != requested_by.tenant.tenant_id:
            raise OperationAuthorizationError("operation belongs to another tenant")
        same_actor = record.actor_id == _actor_id(requested_by)
        if not same_actor and not granted_resources:
            raise OperationAuthorizationError("operation access requires owner or resource grant")
        if not record.resource_refs and not same_actor:
            raise OperationAuthorizationError("private operation belongs to another actor")
        if granted_resources and not _scopes_allow(granted_resources, record.resource_refs):
            raise OperationAuthorizationError("operation resource scope is not granted")
        return record


def _actor_id(identity: ConsumerIdentity) -> str:
    return identity.actor.user_id or identity.actor.service_id or ""


def _scopes_allow(granted: tuple[str, ...], requested: tuple[str, ...]) -> bool:
    return all(
        "*" in granted or ref in granted or f"{ref.split(':', 1)[0]}:*" in granted
        for ref in requested
    )


def _operation_from_row(row) -> OperationRecord:
    refs = row.get("resource_refs_json") or []
    if isinstance(refs, (bytes, bytearray)):
        refs = refs.decode("utf-8")
    if isinstance(refs, str):
        refs = json.loads(refs)
    created_at = row["created_at"]
    updated_at = row["updated_at"]
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return OperationRecord(
        ref=OperationRef(
            operation_id=row["operation_id"], status=OperationStatus(row["status"]),
            version=int(row["operation_version"]),
        ),
        kind=row["kind"], tenant_id=row["tenant_id"], actor_id=row["actor_id"],
        consumer_id=row["consumer_id"], resource_refs=tuple(refs),
        created_at=created_at, updated_at=updated_at, error_code=row.get("error_code"),
    )


__all__ = [
    "InMemoryOperationStore", "OperationAuthorizationError", "OperationError",
    "OperationRecord", "OperationService", "OperationStore", "OperationTransitionError",
    "SqlOperationStore",
]
