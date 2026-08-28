"""Durable, idempotent Integration operation state transitions."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal, Mapping

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.ids import next_gid

from .ports import OperationIdentityPort, OperationPersistencePort, RevisionConflict


OperationStatus = Literal["accepted", "succeeded", "failed", "outcome_unknown"]


@dataclass(frozen=True)
class IntegrationOperation:
    operation_id: str
    owner_gid: str
    team_gid: str | None
    capability_id: str
    idempotency_key: str
    payload_hash: str
    status: OperationStatus
    version: int
    result: dict[str, Any] | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class OperationClaim:
    record: IntegrationOperation
    replayed: bool


class SystemOperationIdentity:
    def new_id(self, kind: str) -> str:
        return f"{kind}-{next_gid()}"

    def now(self) -> datetime:
        return datetime.now(UTC)


class IntegrationOperations:
    def __init__(
        self, store: OperationPersistencePort, *, identity: OperationIdentityPort | None = None
    ) -> None:
        self._store = store
        self._identity = identity or SystemOperationIdentity()

    def new_id(self, kind: str) -> str:
        return self._identity.new_id(kind)

    def start(
        self, *, capability_id: str, payload: Mapping[str, Any], owner_gid: str,
        team_gid: str | None, idempotency_key: str, result: Mapping[str, Any] | None = None,
    ) -> OperationClaim:
        key = str(idempotency_key or "").strip()
        if not key:
            raise CapabilityBusinessError("invalid_input", "idempotency_key is required")
        payload_hash = hashlib.sha256(
            json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        existing = self._store.find_operation(owner_gid, capability_id, key)
        if existing is not None:
            if existing.payload_hash != payload_hash or existing.team_gid != team_gid:
                raise CapabilityBusinessError(
                    "idempotency_conflict", "The idempotency key is bound to a different Integration request"
                )
            return OperationClaim(existing, True)
        now = self._identity.now()
        record = IntegrationOperation(
            operation_id=self._identity.new_id("operation"),
            owner_gid=owner_gid,
            team_gid=team_gid,
            capability_id=capability_id,
            idempotency_key=key,
            payload_hash=payload_hash,
            status="accepted",
            version=1,
            result=dict(result) if result is not None else None,
            error_code=None,
            created_at=now,
            updated_at=now,
        )
        return OperationClaim(self._store.create_operation(record), False)

    def succeeded(
        self, record: IntegrationOperation, result: Mapping[str, Any]
    ) -> IntegrationOperation:
        return self._transition(record, "succeeded", result=dict(result))

    def failed(self, record: IntegrationOperation, *, error_code: str) -> IntegrationOperation:
        return self._transition(record, "failed", error_code=error_code)

    def outcome_unknown(
        self, record: IntegrationOperation, *, error_code: str
    ) -> IntegrationOperation:
        return self._transition(record, "outcome_unknown", error_code=error_code)

    def reconcile(
        self, operation_id: str, status: Literal["succeeded", "failed"], *,
        expected_version: int, result: Mapping[str, Any] | None = None,
        error_code: str | None = None,
    ) -> IntegrationOperation:
        record = self._store.get_operation(operation_id)
        if record is None:
            raise CapabilityBusinessError("resource_not_found", "Integration operation does not exist")
        if record.version != expected_version:
            raise CapabilityBusinessError("version_conflict", "Integration operation revision changed")
        if status == "failed" and not error_code:
            raise CapabilityBusinessError("invalid_input", "Failed reconciliation requires error_code")
        return self._transition(record, status, result=dict(result or {}) if status == "succeeded" else None, error_code=error_code)

    def _transition(
        self, record: IntegrationOperation, status: OperationStatus, *,
        result: dict[str, Any] | None = None, error_code: str | None = None,
    ) -> IntegrationOperation:
        allowed = {
            "accepted": {"succeeded", "failed", "outcome_unknown"},
            "outcome_unknown": {"succeeded", "failed"},
            "succeeded": set(),
            "failed": set(),
        }
        if status not in allowed[record.status]:
            raise CapabilityBusinessError(
                "version_conflict", f"Invalid Integration operation transition: {record.status} -> {status}"
            )
        replacement = replace(
            record,
            status=status,
            version=record.version + 1,
            result=result,
            error_code=error_code,
            updated_at=self._identity.now(),
        )
        try:
            return self._store.transition_operation(record.operation_id, record.version, replacement)
        except RevisionConflict as exc:
            raise CapabilityBusinessError("version_conflict", "Integration operation revision changed") from exc


def operation_ref(record: IntegrationOperation) -> dict[str, Any]:
    return {
        "operation_id": record.operation_id,
        "status": record.status,
        "version": record.version,
    }


__all__ = [
    "IntegrationOperation",
    "IntegrationOperations",
    "OperationClaim",
    "OperationStatus",
    "SystemOperationIdentity",
    "operation_ref",
]
