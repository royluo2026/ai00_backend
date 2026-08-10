"""Durable outcome and audit-outbox contracts for Capability V2."""
from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime
from typing import Any, Callable, Literal, Mapping, Protocol

from .contracts import CapabilityResultV2, FrozenModel


class OutcomeConflict(RuntimeError):
    pass


class OutcomeRecord(FrozenModel):
    operation_id: str
    request_id: str
    idempotency_scope: str
    payload_hash: str
    capability_id: str
    major_version: int
    tenant_id: str
    consumer_scope: str
    actor_id: str
    consumer_type: str
    consumer_id: str
    consumer_instance_id: str | None = None
    policy_version: str
    status: Literal["started", "accepted", "completed", "failed", "outcome_unknown"]
    result: CapabilityResultV2 | None = None
    started_at: datetime
    completed_at: datetime | None = None


class AuditOutboxEvent(FrozenModel):
    event_id: str
    operation_id: str
    event_type: str = "capability.outcome"
    payload: Mapping[str, Any]
    created_at: datetime
    delivered_at: datetime | None = None


class OutcomeStore(Protocol):
    def begin(self, record: OutcomeRecord) -> OutcomeRecord: ...
    def complete(self, operation_id: str, result: CapabilityResultV2) -> OutcomeRecord: ...
    def get(self, operation_id: str) -> OutcomeRecord: ...
    def find_by_idempotency(self, scope: str) -> OutcomeRecord | None: ...
    def mark_unknown(self, operation_id: str, result: CapabilityResultV2) -> OutcomeRecord: ...


class InMemoryOutcomeStore:
    """Reference store with atomic outcome + audit outbox updates under one lock."""

    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._records: dict[str, OutcomeRecord] = {}
        self._by_idempotency: dict[str, str] = {}
        self._outbox: dict[str, AuditOutboxEvent] = {}
        self._lock = threading.Lock()

    def begin(self, record: OutcomeRecord) -> OutcomeRecord:
        with self._lock:
            existing_id = self._by_idempotency.get(record.idempotency_scope)
            if existing_id is not None:
                existing = self._records[existing_id]
                if existing.payload_hash != record.payload_hash:
                    raise OutcomeConflict("idempotency_payload_conflict")
                return existing
            self._records[record.operation_id] = record
            self._by_idempotency[record.idempotency_scope] = record.operation_id
            return record

    def complete(self, operation_id: str, result: CapabilityResultV2) -> OutcomeRecord:
        with self._lock:
            record = self._records.get(operation_id)
            if record is None:
                raise OutcomeConflict("outcome_not_found")
            if record.status != "started":
                if record.result == durable_result(result):
                    return record
                raise OutcomeConflict("outcome_already_final")
            durable = durable_result(result)
            status = "completed" if result.ok else "failed"
            completed = record.model_copy(update={
                "status": status,
                "result": durable,
                "completed_at": self._clock(),
            })
            event = AuditOutboxEvent(
                event_id=f"audit_{operation_id}",
                operation_id=operation_id,
                payload={
                    "capability_id": record.capability_id,
                    "major_version": record.major_version,
                    "request_id": record.request_id,
                    "tenant_id": record.tenant_id,
                    "consumer_scope": record.consumer_scope,
                    "actor_id": record.actor_id,
                    "consumer_type": record.consumer_type,
                    "consumer_id": record.consumer_id,
                    "consumer_instance_id": record.consumer_instance_id,
                    "policy_version": record.policy_version,
                    "payload_hash": record.payload_hash,
                    "status": status,
                },
                created_at=self._clock(),
            )
            self._records[operation_id] = completed
            self._outbox[event.event_id] = event
            return completed

    def get(self, operation_id: str) -> OutcomeRecord:
        with self._lock:
            record = self._records.get(operation_id)
            if record is None:
                raise OutcomeConflict("outcome_not_found")
            return record

    def find_by_idempotency(self, scope: str) -> OutcomeRecord | None:
        with self._lock:
            operation_id = self._by_idempotency.get(scope)
            return self._records.get(operation_id) if operation_id else None

    def mark_unknown(self, operation_id: str, result: CapabilityResultV2) -> OutcomeRecord:
        with self._lock:
            record = self._records.get(operation_id)
            if record is None:
                raise OutcomeConflict("outcome_not_found")
            unknown = record.model_copy(update={
                "status": "outcome_unknown", "result": durable_result(result),
                "completed_at": self._clock(),
            })
            self._records[operation_id] = unknown
            event = AuditOutboxEvent(
                event_id=f"audit_{operation_id}", operation_id=operation_id,
                payload={
                    "capability_id": record.capability_id,
                    "major_version": record.major_version,
                    "request_id": record.request_id,
                    "tenant_id": record.tenant_id,
                    "actor_id": record.actor_id,
                    "consumer_type": record.consumer_type,
                    "consumer_id": record.consumer_id,
                    "consumer_instance_id": record.consumer_instance_id,
                    "policy_version": record.policy_version,
                    "status": "outcome_unknown",
                    "payload_hash": record.payload_hash,
                },
                created_at=self._clock(),
            )
            self._outbox[event.event_id] = event
            return unknown

    def pending_audit_events(self) -> tuple[AuditOutboxEvent, ...]:
        with self._lock:
            return tuple(
                event for event in self._outbox.values() if event.delivered_at is None
            )

    def deliver_audit_outbox(self, sender: Callable[[AuditOutboxEvent], None]) -> int:
        delivered = 0
        for event in self.pending_audit_events():
            try:
                sender(event)
            except Exception:
                continue
            with self._lock:
                current = self._outbox.get(event.event_id)
                if current is not None and current.delivered_at is None:
                    self._outbox[event.event_id] = current.model_copy(
                        update={"delivered_at": self._clock()}
                    )
                    delivered += 1
        return delivered

    def snapshot(self) -> tuple[OutcomeRecord, ...]:
        with self._lock:
            return tuple(sorted(self._records.values(), key=lambda item: item.operation_id))


class SqlOutcomeStore:
    OUTCOME_TABLE = "workmanship_base_capability_outcomes"
    OUTBOX_TABLE = "workmanship_base_capability_audit_outbox"

    def __init__(self, connection_context_factory,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._connections = connection_context_factory
        self._clock = clock

    def begin(self, record: OutcomeRecord) -> OutcomeRecord:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {self.OUTCOME_TABLE} WHERE idempotency_scope=%s FOR UPDATE",
                    (record.idempotency_scope,),
                )
                row = cursor.fetchone()
                if row:
                    existing = _record_from_row(row)
                    if existing.payload_hash != record.payload_hash:
                        raise OutcomeConflict("idempotency_payload_conflict")
                    return existing
                cursor.execute(
                    f"INSERT INTO {self.OUTCOME_TABLE} "
                    "(operation_id,request_id,idempotency_scope,payload_hash,capability_id,major_version,"
                    "tenant_id,consumer_scope,actor_id,consumer_type,consumer_id,consumer_instance_id,"
                    "policy_version,status,result_json,started_at,completed_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        record.operation_id, record.request_id, record.idempotency_scope,
                        record.payload_hash, record.capability_id, record.major_version,
                        record.tenant_id, record.consumer_scope, record.actor_id,
                        record.consumer_type, record.consumer_id, record.consumer_instance_id,
                        record.policy_version,
                        record.status, None, record.started_at, None,
                    ),
                )
                return record

    def complete(self, operation_id: str, result: CapabilityResultV2) -> OutcomeRecord:
        with self._connections() as conn:
            return self.complete_in_transaction(conn, operation_id, result)

    def complete_in_transaction(self, conn, operation_id: str,
                                result: CapabilityResultV2) -> OutcomeRecord:
        """Enlist outcome and audit rows in a provider-owned database transaction."""
        with conn.cursor() as cursor:
            cursor.execute(
                    f"SELECT * FROM {self.OUTCOME_TABLE} WHERE operation_id=%s FOR UPDATE",
                    (operation_id,),
                )
            row = cursor.fetchone()
            if not row:
                raise OutcomeConflict("outcome_not_found")
            record = _record_from_row(row)
            if record.status != "started":
                if record.result == durable_result(result):
                    return record
                raise OutcomeConflict("outcome_already_final")
            status = "completed" if result.ok else "failed"
            completed_at = self._clock()
            durable = durable_result(result)
            result_json = json.dumps(durable.model_dump(mode="json"), ensure_ascii=False)
            cursor.execute(
                    f"UPDATE {self.OUTCOME_TABLE} SET status=%s,result_json=%s,completed_at=%s "
                    "WHERE operation_id=%s AND status='started'",
                    (status, result_json, completed_at, operation_id),
                )
            if cursor.rowcount != 1:
                raise OutcomeConflict("outcome_completion_race")
            payload = {
                "capability_id": record.capability_id, "major_version": record.major_version,
                "request_id": record.request_id, "tenant_id": record.tenant_id,
                "consumer_scope": record.consumer_scope, "policy_version": record.policy_version,
                "actor_id": record.actor_id, "consumer_type": record.consumer_type,
                "consumer_id": record.consumer_id,
                "consumer_instance_id": record.consumer_instance_id,
                "payload_hash": record.payload_hash, "status": status,
            }
            cursor.execute(
                    f"INSERT INTO {self.OUTBOX_TABLE} "
                    "(event_id,operation_id,event_type,payload_json,created_at) VALUES (%s,%s,%s,%s,%s)",
                    (
                        f"audit_{operation_id}", operation_id, "capability.outcome",
                        json.dumps(payload, ensure_ascii=False), completed_at,
                    ),
                )
            return record.model_copy(update={
                "status": status, "result": durable, "completed_at": completed_at,
            })

    def get(self, operation_id: str) -> OutcomeRecord:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {self.OUTCOME_TABLE} WHERE operation_id=%s", (operation_id,)
                )
                row = cursor.fetchone()
        if not row:
            raise OutcomeConflict("outcome_not_found")
        return _record_from_row(row)

    def find_by_idempotency(self, scope: str) -> OutcomeRecord | None:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {self.OUTCOME_TABLE} WHERE idempotency_scope=%s", (scope,)
                )
                row = cursor.fetchone()
        return _record_from_row(row) if row else None

    def mark_unknown(self, operation_id: str, result: CapabilityResultV2) -> OutcomeRecord:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                completed_at = self._clock()
                cursor.execute(
                    f"SELECT * FROM {self.OUTCOME_TABLE} WHERE operation_id=%s FOR UPDATE",
                    (operation_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise OutcomeConflict("outcome_not_found")
                record = _record_from_row(row)
                cursor.execute(
                    f"UPDATE {self.OUTCOME_TABLE} SET status='outcome_unknown',result_json=%s,"
                    "completed_at=%s WHERE operation_id=%s AND status='started'",
                    (
                        json.dumps(durable_result(result).model_dump(mode="json"), ensure_ascii=False),
                        completed_at, operation_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise OutcomeConflict("outcome_unknown_update_failed")
                cursor.execute(
                    f"INSERT INTO {self.OUTBOX_TABLE} "
                    "(event_id,operation_id,event_type,payload_json,created_at) VALUES (%s,%s,%s,%s,%s)",
                    (
                        f"audit_{operation_id}", operation_id, "capability.outcome",
                        json.dumps({
                            "operation_id": operation_id,
                            "capability_id": record.capability_id,
                            "major_version": record.major_version,
                            "request_id": record.request_id,
                            "tenant_id": record.tenant_id,
                            "actor_id": record.actor_id,
                            "consumer_type": record.consumer_type,
                            "consumer_id": record.consumer_id,
                            "consumer_instance_id": record.consumer_instance_id,
                            "policy_version": record.policy_version,
                            "payload_hash": record.payload_hash,
                            "status": "outcome_unknown",
                        }),
                        completed_at,
                    ),
                )
        return self.get(operation_id)

    def pending_audit_events(self, limit: int = 100) -> tuple[AuditOutboxEvent, ...]:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {self.OUTBOX_TABLE} WHERE delivered_at IS NULL "
                    "ORDER BY created_at LIMIT %s",
                    (max(1, min(limit, 1000)),),
                )
                rows = cursor.fetchall()
        return tuple(_audit_event_from_row(row) for row in rows)

    def deliver_audit_outbox(self, sender: Callable[[AuditOutboxEvent], None],
                             limit: int = 100) -> int:
        delivered = 0
        for event in self.pending_audit_events(limit):
            try:
                sender(event)
            except Exception as exc:
                error_code = type(exc).__name__[:128]
                with self._connections() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            f"UPDATE {self.OUTBOX_TABLE} SET attempt_count=attempt_count+1,"
                            "last_error_code=%s WHERE event_id=%s AND delivered_at IS NULL",
                            (error_code, event.event_id),
                        )
                continue
            with self._connections() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {self.OUTBOX_TABLE} SET delivered_at=%s,"
                        "attempt_count=attempt_count+1,last_error_code=NULL "
                        "WHERE event_id=%s AND delivered_at IS NULL",
                        (self._clock(), event.event_id),
                    )
                    delivered += int(cursor.rowcount == 1)
        return delivered


def _record_from_row(row: Mapping[str, Any]) -> OutcomeRecord:
    result = row.get("result_json")
    if isinstance(result, (bytes, bytearray)):
        result = result.decode("utf-8")
    if isinstance(result, str):
        result = json.loads(result)
    return OutcomeRecord(
        operation_id=row["operation_id"], request_id=row["request_id"],
        idempotency_scope=row["idempotency_scope"], payload_hash=row["payload_hash"],
        capability_id=row["capability_id"], major_version=int(row["major_version"]),
        tenant_id=row["tenant_id"], consumer_scope=row["consumer_scope"],
        actor_id=row["actor_id"], consumer_type=row["consumer_type"],
        consumer_id=row["consumer_id"], consumer_instance_id=row.get("consumer_instance_id"),
        policy_version=row["policy_version"], status=row["status"], result=result,
        started_at=_as_utc(row["started_at"]),
        completed_at=_as_utc(row.get("completed_at")),
    )


def _audit_event_from_row(row: Mapping[str, Any]) -> AuditOutboxEvent:
    payload = row.get("payload_json") or {}
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    return AuditOutboxEvent(
        event_id=row["event_id"], operation_id=row["operation_id"],
        event_type=row["event_type"], payload=payload, created_at=_as_utc(row["created_at"]),
        delivered_at=_as_utc(row.get("delivered_at")),
    )


def durable_result(result: CapabilityResultV2) -> CapabilityResultV2:
    """Persist only cross-domain-safe outcome metadata and immutable references."""
    error = result.error
    if error is not None:
        error = error.model_copy(update={
            "message": "Capability invocation failed.", "details": {}
        })
    evidence = tuple(
        item.model_copy(update={"summary": ""})
        for item in result.evidence
        if re.match(r"^[a-z][a-z0-9+.-]*:(?://|urn:)?", item.reference, re.IGNORECASE)
        and not re.match(r"^[A-Za-z]:[\\/]", item.reference)
    )
    return result.model_copy(update={
        "data": None, "error": error, "evidence": evidence, "warnings": (),
    })


def _as_utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "AuditOutboxEvent", "InMemoryOutcomeStore", "OutcomeConflict", "OutcomeRecord",
    "OutcomeStore", "SqlOutcomeStore", "durable_result",
]
