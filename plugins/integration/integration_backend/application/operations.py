"""Durable, idempotent Integration operation state transitions."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal, Mapping

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.platform_sdk.ids import next_gid

from .ports import IncompleteOperation, OperationIdentityPort, OperationPersistencePort, RevisionConflict


OperationStatus = Literal["accepted", "succeeded", "failed", "outcome_unknown"]
_UNSET = object()


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
        record = self._candidate(
            capability_id=capability_id, payload=payload, owner_gid=owner_gid,
            team_gid=team_gid, idempotency_key=idempotency_key, result=result,
        )
        winner, replayed = self._store.claim_operation(record)
        return self._validated_claim(record, winner, replayed)

    def prepare(
        self, *, capability_id: str, payload: Mapping[str, Any], owner_gid: str,
        team_gid: str | None, idempotency_key: str,
    ) -> IntegrationOperation:
        return self._candidate(
            capability_id=capability_id, payload=payload, owner_gid=owner_gid,
            team_gid=team_gid, idempotency_key=idempotency_key, result=None,
        )

    def completed_record(
        self, record: IntegrationOperation, result: Mapping[str, Any]
    ) -> IntegrationOperation:
        return replace(
            record,
            status="succeeded",
            version=record.version + 1,
            result=dict(result),
            updated_at=self._identity.now(),
        )

    def validate_claim(
        self, candidate: IntegrationOperation, winner: IntegrationOperation, replayed: bool
    ) -> OperationClaim:
        return self._validated_claim(candidate, winner, replayed)

    def replay_import(
        self, *, capability_id: str, payload: Mapping[str, Any], owner_gid: str,
        team_gid: str | None, idempotency_key: str,
    ) -> OperationClaim | None:
        key = self._key(idempotency_key)
        try:
            existing = self._store.find_import_operation(owner_gid, capability_id, key)
        except IncompleteOperation as exc:
            raise CapabilityBusinessError(
                "idempotency_conflict", "The previous Integration import operation is incomplete"
            ) from exc
        if existing is None:
            return None
        candidate = replace(
            existing,
            team_gid=team_gid,
            payload_hash=self._payload_hash(payload),
        )
        return self._validated_claim(candidate, existing, True)

    def replay(
        self, *, capability_id: str, payload: Mapping[str, Any], owner_gid: str,
        team_gid: str | None, idempotency_key: str,
    ) -> OperationClaim | None:
        existing = self._store.find_operation(owner_gid, capability_id, self._key(idempotency_key))
        if existing is None:
            return None
        candidate = replace(existing, team_gid=team_gid, payload_hash=self._payload_hash(payload))
        return self._validated_claim(candidate, existing, True)

    def start_import(
        self, *, capability_id: str, payload: Mapping[str, Any], owner_gid: str,
        team_gid: str | None, idempotency_key: str, run: Mapping[str, Any],
    ) -> OperationClaim:
        run_id = str(run.get("run_id") or "").strip()
        if not run_id:
            raise CapabilityBusinessError("invalid_input", "Import run_id is required")
        record = self._candidate(
            capability_id=capability_id, payload=payload, owner_gid=owner_gid,
            team_gid=team_gid, idempotency_key=idempotency_key, result={"run_id": run_id},
        )
        try:
            winner, replayed = self._store.claim_import_operation(
                record, {**dict(run), "operation_id": record.operation_id}
            )
        except IncompleteOperation as exc:
            raise CapabilityBusinessError(
                "idempotency_conflict", "The previous Integration import operation is incomplete"
            ) from exc
        return self._validated_claim(record, winner, replayed)

    def _candidate(
        self, *, capability_id: str, payload: Mapping[str, Any], owner_gid: str,
        team_gid: str | None, idempotency_key: str, result: Mapping[str, Any] | None,
    ) -> IntegrationOperation:
        key = self._key(idempotency_key)
        payload_hash = self._payload_hash(payload)
        now = self._identity.now()
        return IntegrationOperation(
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

    @staticmethod
    def _key(idempotency_key: str) -> str:
        key = str(idempotency_key or "").strip()
        if not key:
            raise CapabilityBusinessError("invalid_input", "idempotency_key is required")
        return key

    @staticmethod
    def _payload_hash(payload: Mapping[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _validated_claim(
        candidate: IntegrationOperation, winner: IntegrationOperation, replayed: bool
    ) -> OperationClaim:
        if replayed and (
            winner.payload_hash != candidate.payload_hash
            or winner.team_gid != candidate.team_gid
            or winner.owner_gid != candidate.owner_gid
            or winner.capability_id != candidate.capability_id
        ):
            raise CapabilityBusinessError(
                "idempotency_conflict", "The idempotency key is bound to a different Integration request"
            )
        return OperationClaim(winner, replayed)

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
        owner_gid: str, team_gid: str | None,
        expected_version: int, result: Mapping[str, Any] | None = None,
        error_code: str | None = None,
    ) -> IntegrationOperation:
        record = self._store.get_operation(operation_id, owner_gid, team_gid)
        if record is None:
            raise CapabilityBusinessError("resource_not_found", "Integration operation does not exist")
        if record.version != expected_version:
            raise CapabilityBusinessError("version_conflict", "Integration operation revision changed")
        if status == "failed" and not error_code:
            raise CapabilityBusinessError("invalid_input", "Failed reconciliation requires error_code")
        return self._transition(
            record, status, result=dict(result or {}) if status == "succeeded" else _UNSET,
            error_code=error_code,
        )

    def _transition(
        self, record: IntegrationOperation, status: OperationStatus, *,
        result: dict[str, Any] | None | object = _UNSET, error_code: str | None = None,
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
        replacement_result = record.result
        if result is not _UNSET:
            replacement_result = dict(record.result or {})
            incoming = dict(result or {})
            if (
                replacement_result.get("run_id")
                and incoming.get("run_id")
                and incoming["run_id"] != replacement_result["run_id"]
            ):
                raise CapabilityBusinessError("invalid_input", "Integration import run identity is immutable")
            replacement_result.update(incoming)
        replacement = replace(
            record,
            status=status,
            version=record.version + 1,
            result=replacement_result,
            error_code=error_code,
            updated_at=self._identity.now(),
        )
        try:
            return self._store.transition_operation(
                record.operation_id, record.version, replacement, record.owner_gid, record.team_gid
            )
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
