"""AI00 Connector health, compatibility, and plan queue boundary."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import os
from typing import Literal

from pydantic import Field, model_validator

from backend.capability_v2.contracts import FrozenModel, OperationRef, OperationStatus
from backend.capability_v2.provider_contracts import (
    CapabilityContext, CapabilityOutput, CapabilityRisk, CapabilitySpec, EvidenceRef,
)
from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1, ConnectorPlanOutcomeV1, canonical_hash,
)
from backend.domain_ports.local_integration import HASH_PATTERN
from backend.domain_ports.local_integration import canonical_json_bytes
from backend.domain_ports.simulation_runtime import ConnectorOutcomePortProxy

from ..data.connection import get_device_conn


class ConnectorError(RuntimeError):
    pass


def sign_connector_plan_lease(
    plan: ConnectorExecutionPlanV1, key_id: str | None = None,
) -> dict[str, str]:
    configured_key_id = os.environ.get("AI00_CONNECTOR_PLAN_SIGNING_KEY_ID", "")
    secret = os.environ.get("AI00_CONNECTOR_PLAN_SIGNING_SECRET", "")
    if not configured_key_id or len(secret.encode("utf-8")) < 32:
        raise ConnectorError("connector_plan_signing_key_unavailable")
    if key_id is not None and key_id != configured_key_id:
        raise ConnectorError("connector_plan_signing_key_mismatch")
    digest = hmac.new(
        secret.encode("utf-8"),
        canonical_json_bytes(plan.model_dump(mode="json")),
        hashlib.sha256,
    ).hexdigest()
    return {"key_id": configured_key_id, "signature": "hmac-sha256:" + digest}


class AdapterOperation(FrozenModel):
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}@1$")
    contract_hash: str = Field(pattern=HASH_PATTERN)


class AdapterAdvertisement(FrozenModel):
    adapter_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    adapter_major: Literal[1]
    product_id: str = Field(min_length=1, max_length=128)
    product_version: str = Field(min_length=1, max_length=64)
    operations: tuple[AdapterOperation, ...] = Field(max_length=256)

    @model_validator(mode="after")
    def unique_operations(self) -> "AdapterAdvertisement":
        ids = [item.operation_id for item in self.operations]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_adapter_operation")
        return self


class ConnectorHealth(FrozenModel):
    connector_version: str = Field(min_length=1, max_length=64)
    protocol_versions: tuple[str, ...] = Field(max_length=16)
    bound_user_id: str = Field(min_length=1, max_length=191)
    session_id: str = Field(min_length=1, max_length=128)
    user_session_present: bool
    session_host_ready: bool
    system_awake: bool
    adapters: tuple[AdapterAdvertisement, ...] = Field(max_length=32)
    reported_at: datetime

    @model_validator(mode="after")
    def validate_advertisement(self) -> "ConnectorHealth":
        ids = [(item.adapter_id, item.adapter_major) for item in self.adapters]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_adapter")
        if self.reported_at.tzinfo is None or self.reported_at.utcoffset() is None:
            raise ValueError("reported_at must be timezone-aware")
        return self


def _version(value: str) -> tuple[int, ...]:
    try:
        parts = tuple(int(part) for part in value.split("."))
        return parts + (0,) * (4 - len(parts))
    except ValueError as exc:
        raise ConnectorError("connector_version_incompatible") from exc


def require_compatible(plan: ConnectorExecutionPlanV1, health: ConnectorHealth) -> None:
    if plan.protocol not in health.protocol_versions:
        raise ConnectorError("connector_version_incompatible")
    if plan.user_id != health.bound_user_id:
        raise ConnectorError("bound_user_mismatch")
    if not health.user_session_present or not health.session_host_ready:
        raise ConnectorError("interactive_session_missing")
    if not health.system_awake:
        raise ConnectorError("connector_offline")
    adapter = next(
        (
            item for item in health.adapters
            if item.adapter_id == plan.adapter_id and item.adapter_major == plan.adapter_major
        ),
        None,
    )
    if adapter is None:
        raise ConnectorError("adapter_unavailable")
    target = plan.target_product
    if (
        adapter.product_id != target.product_id
        or _version(adapter.product_version) < _version(target.minimum_version)
        or _version(adapter.product_version) >= _version(target.maximum_version_exclusive)
    ):
        raise ConnectorError("connector_version_incompatible")
    advertised = {item.operation_id: item.contract_hash for item in adapter.operations}
    for step in plan.steps:
        if advertised.get(step.operation_id) != step.contract_hash:
            raise ConnectorError("adapter_contract_mismatch")


class ConnectorControlPlane:
    def __init__(self, repository, *, outcome_port=None, clock=lambda: datetime.now(UTC)):
        self.repository = repository
        self.outcome_port = outcome_port
        self.clock = clock

    def record_heartbeat(
        self, device_id: str, expected_user_id: str, health: ConnectorHealth,
    ) -> None:
        if health.bound_user_id != expected_user_id:
            raise ConnectorError("bound_user_mismatch")
        current = self.repository.get_health(device_id)
        if (
            current is not None
            and current.reported_at > self.clock() - timedelta(minutes=2)
            and current.session_id != health.session_id
        ):
            raise ConnectorError("interactive_session_conflict")
        self.repository.save_health(device_id, health)

    def get_health(self, device_id: str, context: CapabilityContext) -> ConnectorHealth:
        health = self.repository.get_health(device_id)
        if health is None:
            raise ConnectorError("connector_offline")
        if health.bound_user_id != context.user_gid:
            raise ConnectorError("bound_user_mismatch")
        return health

    def queue_plan(
        self, plan: ConnectorExecutionPlanV1, context: CapabilityContext,
    ) -> OperationRef:
        if plan.user_id != context.user_gid or plan.tenant_id != context.team_gid:
            raise ConnectorError("plan_identity_mismatch")
        health = self.repository.get_health(plan.device_id)
        if health is None or health.reported_at <= self.clock() - timedelta(minutes=2):
            raise ConnectorError("connector_offline")
        require_compatible(plan, health)
        self.repository.insert_plan(plan)
        return OperationRef(operation_id=plan.plan_id, status=OperationStatus.ACCEPTED)

    def lease_plan(self, device_id: str, lease_seconds: int = 60):
        health = self.repository.get_health(device_id)
        if health is None or health.reported_at <= self.clock() - timedelta(minutes=2):
            raise ConnectorError("connector_offline")
        if not health.user_session_present or not health.session_host_ready:
            raise ConnectorError("interactive_session_missing")
        if not health.system_awake:
            raise ConnectorError("connector_offline")
        lease = self.repository.lease_plan(device_id, lease_seconds)
        if lease is None:
            return None
        plan = ConnectorExecutionPlanV1.model_validate(lease["plan"])
        return {**lease, **sign_connector_plan_lease(plan)}

    def complete_plan(
        self, device_id: str, plan_id: str, lease_id: str,
        outcome: ConnectorPlanOutcomeV1,
    ) -> None:
        if outcome.plan_id != plan_id:
            raise ConnectorError("plan_identity_mismatch")
        plan = self.repository.get_plan(plan_id, device_id=device_id, lease_id=lease_id)
        expected = [step.step_id for step in plan.steps]
        actual = [step.step_id for step in outcome.steps]
        if len(actual) != len(set(actual)) or any(step not in expected for step in actual):
            raise ConnectorError("plan_outcome_invalid")
        if outcome.status == "completed" and (
            actual != expected or any(step.status != "completed" for step in outcome.steps)
        ):
            raise ConnectorError("plan_outcome_invalid")
        self.repository.complete_plan(device_id, plan_id, lease_id, outcome)
        if self.outcome_port is not None:
            self.outcome_port.apply(plan, outcome)


class SqlConnectorRepository:
    def get_health(self, device_id: str) -> ConnectorHealth | None:
        with get_device_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT health_json FROM workmanship_device_connector_health "
                "WHERE device_gid=%s LIMIT 1",
                (device_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        value = row["health_json"]
        if isinstance(value, str):
            import json
            value = json.loads(value)
        return ConnectorHealth.model_validate(value)

    def save_health(self, device_id: str, health: ConnectorHealth) -> None:
        import json

        data = health.model_dump(mode="json")
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = canonical_hash(data)
        with get_device_conn() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO workmanship_device_connector_health "
                        "(device_gid,bound_user_id,session_id,health_json,health_hash,reported_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                        "bound_user_id=VALUES(bound_user_id),session_id=VALUES(session_id),"
                        "health_json=VALUES(health_json),health_hash=VALUES(health_hash),"
                        "reported_at=VALUES(reported_at),updated_at=NOW(6)",
                        (device_id, health.bound_user_id, health.session_id, encoded, digest, health.reported_at),
                    )
                    cursor.execute(
                        "INSERT INTO workmanship_device_connector_heartbeat_audit "
                        "(gid,device_gid,health_hash,health_json,reported_at) VALUES (%s,%s,%s,%s,%s)",
                        ("connector-heartbeat-" + __import__("uuid").uuid4().hex,
                         device_id, digest, encoded, health.reported_at),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def insert_plan(self, plan: ConnectorExecutionPlanV1) -> None:
        import json

        encoded = json.dumps(
            plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with get_device_conn() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT plan_hash FROM workmanship_device_connector_plans "
                        "WHERE plan_id=%s FOR UPDATE",
                        (plan.plan_id,),
                    )
                    current = cursor.fetchone()
                    if current:
                        if current["plan_hash"] != plan.plan_hash:
                            raise ConnectorError("idempotency_conflict")
                        return
                    cursor.execute(
                        "INSERT INTO workmanship_device_connector_plans "
                        "(plan_id,device_gid,tenant_gid,user_gid,plan_hash,plan_json,status,expires_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,'queued',%s)",
                        (plan.plan_id, plan.device_id, plan.tenant_id, plan.user_id,
                         plan.plan_hash, encoded, plan.expires_at),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def lease_plan(self, device_id: str, lease_seconds: int = 60):
        import json
        import secrets

        lease_seconds = max(15, min(int(lease_seconds), 300))
        lease_id = "connector-lease-" + secrets.token_hex(16)
        with get_device_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE workmanship_device_connector_plans SET status='outcome_unknown',"
                    "updated_at=NOW(6) WHERE device_gid=%s AND status='leased' AND lease_until<=NOW(6)",
                    (device_id,),
                )
                cursor.execute(
                    "UPDATE workmanship_device_connector_plans SET status='expired',updated_at=NOW(6) "
                    "WHERE device_gid=%s AND status='queued' AND expires_at<=NOW(6)",
                    (device_id,),
                )
                cursor.execute(
                    "SELECT plan_id,plan_json FROM workmanship_device_connector_plans "
                    "WHERE device_gid=%s AND status='queued' AND expires_at>NOW(6) "
                    "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED",
                    (device_id,),
                )
                row = cursor.fetchone()
                if not row:
                    conn.commit()
                    return None
                cursor.execute(
                    "UPDATE workmanship_device_connector_plans SET status='leased',lease_id=%s,"
                    "lease_until=DATE_ADD(NOW(6),INTERVAL %s SECOND),attempts=attempts+1,updated_at=NOW(6) "
                    "WHERE plan_id=%s AND status='queued'",
                    (lease_id, lease_seconds, row["plan_id"]),
                )
            conn.commit()
        value = row["plan_json"]
        if isinstance(value, str):
            value = json.loads(value)
        return {"lease_id": lease_id, "plan": value}

    def get_plan(self, plan_id: str, *, device_id: str, lease_id: str) -> ConnectorExecutionPlanV1:
        import json

        with get_device_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT plan_json FROM workmanship_device_connector_plans "
                "WHERE plan_id=%s AND device_gid=%s AND lease_id=%s AND ("
                "(status='leased' AND lease_until>NOW(6) AND expires_at>NOW(6)) OR "
                "(status IN ('completed','failed','cancelled','outcome_unknown') AND outcome_hash IS NOT NULL)"
                ") LIMIT 1",
                (plan_id, device_id, lease_id),
            )
            row = cursor.fetchone()
        if not row:
            raise ConnectorError("plan_lease_invalid")
        value = row["plan_json"]
        if isinstance(value, str):
            value = json.loads(value)
        return ConnectorExecutionPlanV1.model_validate(value)

    def complete_plan(
        self, device_id: str, plan_id: str, lease_id: str,
        outcome: ConnectorPlanOutcomeV1,
    ) -> None:
        import json

        data = outcome.model_dump(mode="json")
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = canonical_hash(data)
        with get_device_conn() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT status,outcome_hash FROM workmanship_device_connector_plans "
                        "WHERE plan_id=%s AND device_gid=%s AND lease_id=%s FOR UPDATE",
                        (plan_id, device_id, lease_id),
                    )
                    current = cursor.fetchone()
                    if not current:
                        raise ConnectorError("plan_lease_invalid")
                    if current["outcome_hash"] is not None:
                        if current["outcome_hash"] != digest:
                            raise ConnectorError("idempotency_conflict")
                        conn.commit()
                        return
                    cursor.execute(
                        "UPDATE workmanship_device_connector_plans SET status=%s,outcome_json=%s,"
                        "outcome_hash=%s,updated_at=NOW(6) WHERE plan_id=%s AND device_gid=%s "
                        "AND status='leased' AND lease_id=%s AND lease_until>NOW(6)",
                        (outcome.status, encoded, digest, plan_id, device_id, lease_id),
                    )
                    if cursor.rowcount != 1:
                        raise ConnectorError("plan_lease_invalid")
                conn.commit()
            except Exception:
                conn.rollback()
                raise


connector_control_plane = ConnectorControlPlane(
    SqlConnectorRepository(), outcome_port=ConnectorOutcomePortProxy(),
)


def record_connector_heartbeat(device_id: str, owner_user_id: str, health: ConnectorHealth) -> None:
    connector_control_plane.record_heartbeat(device_id, owner_user_id, health)


def queue_connector_plan(plan: ConnectorExecutionPlanV1, context: CapabilityContext) -> OperationRef:
    return connector_control_plane.queue_plan(plan, context)


def lease_connector_plan(device_id: str, lease_seconds: int = 60):
    return connector_control_plane.lease_plan(device_id, lease_seconds)


def complete_connector_plan(device_id, plan_id, lease_id, outcome):
    connector_control_plane.complete_plan(device_id, plan_id, lease_id, outcome)


def get_leased_connector_plan(device_id, plan_id, lease_id):
    return connector_control_plane.repository.get_plan(
        plan_id, device_id=device_id, lease_id=lease_id
    )


def register_connector_runtime_capabilities(registry, control_plane: ConnectorControlPlane) -> None:
    from .provider import register

    def get_health(payload, context):
        health = control_plane.get_health(payload["device_id"], context)
        data = health.model_dump(mode="json")
        return CapabilityOutput(data=data, evidence=(EvidenceRef(
            kind="device.connector.health",
            reference=f"connector-health:{payload['device_id']}",
            digest=canonical_hash(data),
        ),))

    def queue_plan(payload, context):
        plan = ConnectorExecutionPlanV1.model_validate(payload["plan"])
        operation = control_plane.queue_plan(plan, context)
        return CapabilityOutput(data=operation.model_dump(mode="json"), evidence=(EvidenceRef(
            kind="device.connector.plan",
            reference=f"connector-plan:{plan.plan_id}",
            digest=plan.plan_hash,
        ),))

    register(registry, CapabilitySpec(
        id="device.connector.health.get", owner="device", version=1,
        description="Read the latest authenticated AI00 Connector health advertisement.",
        use_when="A workflow must preflight one owned Connector and its adapters.",
        do_not_use_when="The caller needs to queue local work.",
        risk=CapabilityRisk.READ, confirmation="none", permissions=("agent.run",),
        input_schema={}, output_schema={}, tags=("device", "connector", "health"),
    ), get_health)
    register(registry, CapabilitySpec(
        id="device.connector.plan.queue", owner="device", version=1,
        description="Queue one immutable compatible ExecutionPlan for an owned AI00 Connector.",
        use_when="A governed workflow is ready to execute a version-pinned local plan.",
        do_not_use_when="Compatibility or user-session preflight has not passed.",
        risk=CapabilityRisk.WRITE, confirmation="user", permissions=("agent.run",),
        input_schema={}, output_schema={}, tags=("device", "connector", "plan"),
    ), queue_plan)


__all__ = [
    "AdapterAdvertisement", "AdapterOperation", "ConnectorControlPlane",
    "ConnectorError", "ConnectorHealth", "register_connector_runtime_capabilities",
    "SqlConnectorRepository", "complete_connector_plan", "connector_control_plane",
    "get_leased_connector_plan", "lease_connector_plan", "queue_connector_plan",
    "sign_connector_plan_lease",
    "record_connector_heartbeat", "require_compatible",
]
