"""Approval, idempotency, rate and outcome coordination for Capability V2."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

from .contracts import CapabilityDescriptorV2, CapabilityResultV2, FrozenModel, InvocationEnvelope
from .outcomes import OutcomeConflict, OutcomeRecord, OutcomeStore


class ReliabilityError(RuntimeError):
    pass


class ApprovalChallenge(FrozenModel):
    approval_id: str
    token_hash: str
    capability_id: str
    major_version: int
    catalog_release: str
    consumer_fingerprint: str
    resource_refs: tuple[str, ...]
    policy_version: str
    confirmation_policy: str
    payload_hash: str
    expires_at: datetime
    consumed_at: datetime | None = None


class IssuedApproval(FrozenModel):
    token: str
    challenge: ApprovalChallenge


class ApprovalStore(Protocol):
    def save(self, challenge: ApprovalChallenge) -> None: ...
    def consume(self, token_hash: str, expected: ApprovalChallenge) -> bool: ...


class InvocationLease(FrozenModel):
    operation_id: str
    outcome: OutcomeRecord
    replay_result: CapabilityResultV2 | None = None


@dataclass(frozen=True)
class TransactionalCapabilityOutput:
    """Provider output carrying an open transaction for atomic outcome enlistment."""
    data: object
    transaction: object
    evidence: tuple[object, ...] = ()


class RateLimiter(Protocol):
    def consume(self, scope: str, cost: int) -> bool: ...


class InMemoryApprovalStore:
    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._records: dict[str, ApprovalChallenge] = {}
        self._lock = threading.Lock()

    def save(self, challenge: ApprovalChallenge) -> None:
        with self._lock:
            if challenge.token_hash in self._records:
                raise ReliabilityError("approval_token_exists")
            self._records[challenge.token_hash] = challenge

    def consume(self, token_hash: str, expected: ApprovalChallenge) -> bool:
        with self._lock:
            current = self._records.get(token_hash)
            if current is None or current.consumed_at is not None or current.expires_at <= self._clock():
                return False
            comparable = (
                "capability_id", "major_version", "catalog_release", "consumer_fingerprint", "resource_refs",
                "policy_version", "payload_hash",
                "confirmation_policy",
            )
            if any(getattr(current, name) != getattr(expected, name) for name in comparable):
                return False
            self._records[token_hash] = current.model_copy(update={"consumed_at": self._clock()})
            return True


class SqlApprovalStore:
    TABLE = "workmanship_base_capability_approvals"

    def __init__(self, connection_context_factory,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._connections = connection_context_factory
        self._clock = clock

    def save(self, challenge: ApprovalChallenge) -> None:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {self.TABLE} "
                    "(approval_id,token_hash,capability_id,major_version,catalog_release,consumer_fingerprint,"
                    "resource_refs_json,policy_version,confirmation_policy,payload_hash,"
                    "expires_at,consumed_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        challenge.approval_id, challenge.token_hash, challenge.capability_id,
                        challenge.major_version, challenge.catalog_release, challenge.consumer_fingerprint,
                        json.dumps(challenge.resource_refs), challenge.policy_version,
                        challenge.confirmation_policy,
                        challenge.payload_hash, challenge.expires_at, challenge.consumed_at,
                    ),
                )

    def consume(self, token_hash: str, expected: ApprovalChallenge) -> bool:
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {self.TABLE} WHERE token_hash=%s FOR UPDATE",
                    (token_hash,),
                )
                row = cursor.fetchone()
                expires_at = _as_utc(row["expires_at"]) if row else None
                if not row or row.get("consumed_at") is not None or expires_at <= self._clock():
                    return False
                refs = row.get("resource_refs_json") or []
                if isinstance(refs, (bytes, bytearray)):
                    refs = refs.decode("utf-8")
                if isinstance(refs, str):
                    refs = json.loads(refs)
                actual = (
                    row["capability_id"], int(row["major_version"]), row["catalog_release"],
                    row["consumer_fingerprint"], tuple(refs), row["policy_version"],
                    row["payload_hash"], row["confirmation_policy"],
                )
                wanted = (
                    expected.capability_id, expected.major_version, expected.catalog_release,
                    expected.consumer_fingerprint, expected.resource_refs,
                    expected.policy_version, expected.payload_hash, expected.confirmation_policy,
                )
                if actual != wanted:
                    return False
                cursor.execute(
                    f"UPDATE {self.TABLE} SET consumed_at=%s "
                    "WHERE approval_id=%s AND consumed_at IS NULL",
                    (self._clock(), row["approval_id"]),
                )
                return cursor.rowcount == 1


class ApprovalService:
    def __init__(self, store: ApprovalStore,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._store = store
        self._clock = clock

    def issue(self, descriptor: CapabilityDescriptorV2, envelope: InvocationEnvelope, *,
              resource_refs: tuple[str, ...], policy_version: str,
              ttl_seconds: int = 300) -> IssuedApproval:
        if descriptor.confirmation_policy == "dual":
            raise ReliabilityError("dual_approval_workflow_required")
        if descriptor.confirmation_policy == "admin" and not (
            set(envelope.identity.tenant.active_roles)
            & {"super_admin", "team_admin", "system_admin"}
        ):
            raise ReliabilityError("admin_approval_required")
        # InvocationEnvelope approval references must start with an alphanumeric
        # character; token_urlsafe may otherwise randomly start with '-' or '_'.
        token = f"apr_{secrets.token_urlsafe(32)}"
        challenge = self._challenge(
            token, descriptor, envelope, resource_refs, policy_version,
            expires_at=self._clock() + timedelta(seconds=ttl_seconds),
        )
        self._store.save(challenge)
        return IssuedApproval(token=token, challenge=challenge)

    def consume(self, token: str, descriptor: CapabilityDescriptorV2,
                envelope: InvocationEnvelope, *, resource_refs: tuple[str, ...],
                policy_version: str) -> bool:
        if not token:
            return False
        expected = self._challenge(
            token, descriptor, envelope, resource_refs, policy_version,
            expires_at=self._clock() + timedelta(seconds=1),
        )
        return self._store.consume(_secret_hash(token), expected)

    @staticmethod
    def _challenge(token, descriptor, envelope, resource_refs, policy_version,
                   *, expires_at) -> ApprovalChallenge:
        token_hash = _secret_hash(token)
        return ApprovalChallenge(
            approval_id=f"approval_{token_hash[:24]}",
            token_hash=token_hash,
            capability_id=descriptor.id,
            major_version=descriptor.major_version,
            catalog_release=envelope.catalog_release,
            consumer_fingerprint=consumer_fingerprint(envelope),
            resource_refs=tuple(sorted(resource_refs)),
            policy_version=policy_version,
            confirmation_policy=descriptor.confirmation_policy,
            payload_hash=normalized_payload_hash(envelope.payload),
            expires_at=expires_at,
        )


class InMemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int = 60,
                 clock: Callable[[], float] = time.time) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._usage: dict[str, deque[tuple[float, int]]] = {}
        self._lock = threading.Lock()

    def consume(self, scope: str, cost: int) -> bool:
        now = self._clock()
        with self._lock:
            events = self._usage.setdefault(scope, deque())
            while events and events[0][0] <= now - self.window_seconds:
                events.popleft()
            if sum(item[1] for item in events) + cost > self.limit:
                return False
            events.append((now, cost))
            return True


class SqlRateLimiter:
    TABLE = "workmanship_base_capability_rate_windows"

    def __init__(self, connection_context_factory, *, limit: int, window_seconds: int = 60,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._connections = connection_context_factory
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock

    def consume(self, scope: str, cost: int) -> bool:
        now = self._clock()
        epoch = int(now.timestamp())
        window_epoch = epoch - (epoch % self.window_seconds)
        window_start = datetime.fromtimestamp(window_epoch, tz=UTC)
        expires_at = window_start + timedelta(seconds=self.window_seconds * 2)
        scope_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        with self._connections() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT cost_used FROM {self.TABLE} "
                    "WHERE scope_hash=%s AND window_started_at=%s FOR UPDATE",
                    (scope_hash, window_start),
                )
                row = cursor.fetchone()
                used = int(row["cost_used"]) if row else 0
                if used + cost > self.limit:
                    return False
                if row:
                    cursor.execute(
                        f"UPDATE {self.TABLE} SET cost_used=%s,expires_at=%s "
                        "WHERE scope_hash=%s AND window_started_at=%s",
                        (used + cost, expires_at, scope_hash, window_start),
                    )
                else:
                    cursor.execute(
                        f"INSERT INTO {self.TABLE} "
                        "(scope_hash,window_started_at,cost_used,expires_at) VALUES (%s,%s,%s,%s)",
                        (scope_hash, window_start, cost, expires_at),
                    )
                return True


class ReliabilityCoordinator:
    def __init__(self, store: OutcomeStore, rate_limiter: RateLimiter,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._store = store
        self._rate_limiter = rate_limiter
        self._clock = clock

    def replay(self, envelope: InvocationEnvelope) -> CapabilityResultV2 | None:
        existing = self._store.find_by_idempotency(idempotency_scope(envelope))
        if existing is None:
            return None
        if existing.payload_hash != normalized_payload_hash(envelope.payload):
            raise ReliabilityError("idempotency_payload_conflict")
        if existing.result is None:
            raise ReliabilityError("idempotency_in_progress")
        return existing.result

    def begin(self, envelope: InvocationEnvelope, descriptor: CapabilityDescriptorV2,
              *, policy_version: str) -> InvocationLease:
        if descriptor.idempotency_policy == "required" and not envelope.idempotency_key:
            raise ReliabilityError("idempotency_key_required")
        if not self._rate_limiter.consume(consumer_fingerprint(envelope), descriptor.rate_limit_cost):
            raise ReliabilityError("rate_limit_exceeded")
        scope = idempotency_scope(envelope)
        operation_id = f"op_{uuid.uuid4().hex}"
        record = OutcomeRecord(
            operation_id=operation_id,
            request_id=envelope.request_id,
            idempotency_scope=scope,
            payload_hash=normalized_payload_hash(envelope.payload),
            capability_id=envelope.capability_id,
            major_version=envelope.major_version,
            tenant_id=envelope.identity.tenant.tenant_id,
            consumer_scope=consumer_fingerprint(envelope),
            actor_id=(envelope.identity.actor.user_id or envelope.identity.actor.service_id or ""),
            consumer_type=envelope.identity.consumer.type.value,
            consumer_id=envelope.identity.consumer.consumer_id,
            consumer_instance_id=(
                envelope.identity.consumer.agent_run_id
                or envelope.identity.consumer.mount_session_id
                or envelope.identity.consumer.installation_id
            ),
            policy_version=policy_version,
            status="started",
            started_at=self._clock(),
        )
        try:
            actual = self._store.begin(record)
        except OutcomeConflict as exc:
            raise ReliabilityError(str(exc)) from exc
        if actual.operation_id != operation_id:
            if actual.result is None:
                raise ReliabilityError("idempotency_in_progress")
            return InvocationLease(
                operation_id=actual.operation_id,
                outcome=actual,
                replay_result=actual.result,
            )
        return InvocationLease(operation_id=operation_id, outcome=actual)

    def complete(self, lease: InvocationLease, result: CapabilityResultV2,
                 transaction=None, *, preserve_projected_data: bool = False) -> OutcomeRecord:
        try:
            if transaction is not None and hasattr(self._store, "complete_in_transaction"):
                if not preserve_projected_data:
                    return self._store.complete_in_transaction(
                        transaction, lease.operation_id, result
                    )
                return self._store.complete_in_transaction(
                    transaction, lease.operation_id, result,
                    preserve_projected_data=preserve_projected_data,
                )
            if not preserve_projected_data:
                return self._store.complete(lease.operation_id, result)
            return self._store.complete(
                lease.operation_id, result,
                preserve_projected_data=preserve_projected_data,
            )
        except OutcomeConflict as exc:
            raise ReliabilityError(str(exc)) from exc

    def mark_unknown(self, lease: InvocationLease,
                     result: CapabilityResultV2) -> OutcomeRecord:
        try:
            return self._store.mark_unknown(lease.operation_id, result)
        except OutcomeConflict as exc:
            raise ReliabilityError(str(exc)) from exc

    def reconcile_committed(
        self, operation_id: str, result: CapabilityResultV2,
    ) -> OutcomeRecord:
        """Idempotently converge a provider-committed eventual write."""
        try:
            record = self._store.get(operation_id)
            if (
                record.capability_id != result.capability_id
                or record.major_version != result.major_version
                or record.request_id != result.correlation.request_id
            ):
                raise ReliabilityError("outcome_identity_mismatch")
            return self._store.reconcile_completed(operation_id, result)
        except OutcomeConflict as exc:
            raise ReliabilityError(str(exc)) from exc


def normalized_payload_hash(payload) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def consumer_fingerprint(envelope: InvocationEnvelope) -> str:
    identity = envelope.identity
    consumer = identity.consumer
    actor = identity.actor.user_id or identity.actor.service_id
    document = {
        "actor": actor,
        "tenant": identity.tenant.tenant_id,
        "type": consumer.type.value,
        "id": consumer.consumer_id,
        "version": consumer.consumer_version,
        "installation": consumer.installation_id,
        "mount": consumer.mount_session_id,
        "agent_run": consumer.agent_run_id,
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "consumer:" + hashlib.sha256(encoded).hexdigest()


def idempotency_scope(envelope: InvocationEnvelope) -> str:
    key = envelope.idempotency_key or envelope.request_id
    material = (
        f"{envelope.identity.tenant.tenant_id}|{consumer_fingerprint(envelope)}|"
        f"{envelope.catalog_release}|{envelope.capability_id}|{envelope.major_version}|{key}"
    )
    return "idem:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _secret_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def transactional_provider(handler):
    """Declare that a provider returns an open transaction for strong writes."""
    setattr(handler, "__capability_transactional__", True)
    return handler


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "ApprovalChallenge", "ApprovalService", "InMemoryApprovalStore", "InMemoryRateLimiter",
    "InvocationLease", "IssuedApproval", "ReliabilityCoordinator", "ReliabilityError",
    "SqlApprovalStore", "SqlRateLimiter",
    "TransactionalCapabilityOutput",
    "transactional_provider",
    "consumer_fingerprint", "idempotency_scope", "normalized_payload_hash",
]
