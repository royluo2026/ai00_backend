"""Simulation persistence adapter for AI00 Connector state and plans."""
from __future__ import annotations

import json
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import re
from typing import TYPE_CHECKING

from pymysql.err import IntegrityError

from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    ConnectorPlanOutcomeV1,
    canonical_hash,
)
from backend.contracts.connector_execution_plan_v2 import (
    PROTOCOL_V2, IDENTITY_PATTERN, ConnectorExecutionPlanV2,
    ConnectorPlanOutcomeV2, canonicalize_v2,
)

from ..domain.connector_pairing import BootstrapRecord, PairingError, PairingRecord
from .connection import get_simulation_conn

if TYPE_CHECKING:
    from ..capabilities.connector_contracts import ConnectorHealth


class ConnectorRepositoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeSession:
    device_id: str
    runtime_generation: int
    runtime_instance_id: str
    expires_at: datetime
    session_token: str = field(repr=False)


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True)
class ProjectionIntent:
    plan_id: str
    outcome_hash: str
    target_capability: str
    status: str


@dataclass(frozen=True)
class ProjectionLease:
    plan_id: str
    outcome_hash: str
    target_capability: str
    attempt: int
    owner: str


class SimulationConnectorRepository:
    # Device rows serialize all v2 writers. Never acquire a plan lock before
    # its device lock, including queueing, recovery, and takeover.
    @staticmethod
    def _locked_runtime(cursor, device_id: str) -> dict:
        cursor.execute(
            "SELECT * FROM workmanship_sim_connector_runtime_devices WHERE device_id=%s FOR UPDATE",
            (device_id,),
        )
        row = cursor.fetchone()
        if not row or row["protocol"] != PROTOCOL_V2 or row["status"] != "active":
            raise ConnectorRepositoryError("runtime_session_invalid")
        return row

    @classmethod
    def _authenticated_runtime(cls, cursor, device_id, generation, instance, token, now):
        row = cls._locked_runtime(cursor, device_id)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if (
            row["runtime_generation"] != generation
            or row["current_runtime_instance_id"] != instance
            or not secrets.compare_digest(row["session_token_hash"] or "", digest)
            or not row["session_expires_at"] or _utc(row["session_expires_at"]) <= _utc(now)
        ):
            raise ConnectorRepositoryError("runtime_session_invalid")
        return row

    @staticmethod
    def _has_unresolved_plans(cursor, device_id):
        cursor.execute(
            "SELECT plan_id FROM workmanship_sim_connector_runtime_plans WHERE device_id=%s "
            "AND status IN ('leased','executing','outcome_unknown','manual_review_required') LIMIT 1 FOR UPDATE",
            (device_id,),
        )
        if cursor.fetchone() is not None:
            return True
        cursor.execute(
            "SELECT plan_id FROM workmanship_sim_connector_plans WHERE connector_id=%s "
            "AND status IN ('leased','executing','outcome_unknown','manual_review_required') LIMIT 1 FOR UPDATE",
            (device_id,),
        )
        return cursor.fetchone() is not None

    @staticmethod
    def _runtime_audit(cursor, row, event, now, *, actor_id=None, reason=None, plan_id=None, outcome_hash=None,
                       recovery_instance_id=None, recovery_session_token_hash=None, outcome_json=None):
        cursor.execute(
            "INSERT INTO workmanship_sim_connector_runtime_audit "
            "(audit_id,protocol,device_id,runtime_generation,runtime_instance_id,session_token_hash,"
            "event_type,actor_id,reason,plan_id,outcome_hash,created_at,recovery_instance_id,recovery_session_token_hash,outcome_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (uuid.uuid4().hex, PROTOCOL_V2, row["device_id"], row["runtime_generation"],
             row["current_runtime_instance_id"], row["session_token_hash"], event,
             actor_id, reason, plan_id, outcome_hash, now, recovery_instance_id, recovery_session_token_hash, outcome_json),
        )

    @classmethod
    def _install_runtime_session(cls, cursor, row, generation, instance, now, expires_at, *, event, actor_id=None, reason=None):
        now, expires_at = _utc(now), _utc(expires_at)
        if not re.fullmatch(IDENTITY_PATTERN, instance):
            raise ConnectorRepositoryError("runtime_instance_invalid")
        if not 0 < (expires_at - now).total_seconds() <= 300:
            raise ConnectorRepositoryError("runtime_session_expiry_invalid")
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cursor.execute(
            "UPDATE workmanship_sim_connector_runtime_devices SET runtime_generation=%s,"
            "current_runtime_instance_id=%s,session_token_hash=%s,session_expires_at=%s,"
            "session_registered_at=%s,updated_at=%s WHERE device_id=%s AND protocol=%s "
            "AND runtime_generation=%s AND current_runtime_instance_id <=> %s AND session_token_hash <=> %s",
            (generation, instance, digest, expires_at, now, now, row["device_id"], PROTOCOL_V2,
             row["runtime_generation"], row["current_runtime_instance_id"], row["session_token_hash"]),
        )
        if cursor.rowcount != 1:
            raise ConnectorRepositoryError("runtime_session_conflict")
        current = {**row, "runtime_generation": generation, "current_runtime_instance_id": instance, "session_token_hash": digest}
        cls._runtime_audit(cursor, current, event, now, actor_id=actor_id, reason=reason)
        return RuntimeSession(row["device_id"], generation, instance, expires_at, token)

    def register_runtime_session(self, device_id, runtime_generation, runtime_instance_id, now, expires_at) -> RuntimeSession:
        """The caller authenticates the device credential before registration."""
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            row = self._locked_runtime(cursor, device_id)
            if row["runtime_generation"] != runtime_generation:
                raise ConnectorRepositoryError("runtime_generation_invalid")
            if row["session_expires_at"] and _utc(row["session_expires_at"]) > _utc(now):
                raise ConnectorRepositoryError("runtime_session_active")
            if self._has_unresolved_plans(cursor, device_id):
                raise ConnectorRepositoryError("runtime_plans_unresolved")
            return self._install_runtime_session(cursor, row, runtime_generation, runtime_instance_id,
                now, expires_at, event="session_registered")

    def force_takeover(self, device_id, expected_generation, new_generation, runtime_instance_id, now, expires_at,
                       *, expected_runtime_instance_id, expected_session_token_hash, actor_id, reason) -> RuntimeSession:
        """Called only behind the user-authenticated takeover Capability.

        The expected identity/hash is the provider's previously read snapshot,
        not an old process credential. A concurrent session change fences it.
        """
        if not actor_id or not reason or len(reason) > 1024:
            raise ConnectorRepositoryError("runtime_takeover_audit_required")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            row = self._locked_runtime(cursor, device_id)
            if row["runtime_generation"] != expected_generation or new_generation != expected_generation + 1:
                raise ConnectorRepositoryError("runtime_generation_invalid")
            if (row["current_runtime_instance_id"] != expected_runtime_instance_id
                    or row["session_token_hash"] != expected_session_token_hash):
                raise ConnectorRepositoryError("runtime_session_conflict")
            if self._has_unresolved_plans(cursor, device_id):
                raise ConnectorRepositoryError("runtime_plans_unresolved")
            return self._install_runtime_session(cursor, row, new_generation, runtime_instance_id,
                now, expires_at, event="force_takeover", actor_id=actor_id, reason=reason)

    def register_reconciliation_session(self, device_id, generation, recovery_instance_id, plan_id,
                                        token_hash, expires_at, *, now=None) -> dict:
        """Caller must validate device credential and signing proof first.

        The caller generates the secret and supplies only its SHA-256 hash.
        This session authorizes the named plan's probe/reconciliation only.
        """
        now = _utc(now or datetime.now(UTC))
        expires_at = _utc(expires_at)
        if not re.fullmatch(r"[0-9a-f]{64}", token_hash):
            raise ConnectorRepositoryError("reconciliation_token_hash_invalid")
        if not re.fullmatch(IDENTITY_PATTERN, recovery_instance_id):
            raise ConnectorRepositoryError("runtime_instance_invalid")
        if not 0 < (expires_at - now).total_seconds() <= 300:
            raise ConnectorRepositoryError("runtime_session_expiry_invalid")
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            row = self._locked_runtime(cursor, device_id)
            if row["runtime_generation"] != generation:
                raise ConnectorRepositoryError("runtime_generation_invalid")
            if not row["session_expires_at"] or _utc(row["session_expires_at"]) > now:
                raise ConnectorRepositoryError("runtime_session_active")
            cursor.execute(
                "SELECT plan_id FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s AND device_id=%s "
                "AND protocol=%s AND runtime_generation=%s AND runtime_instance_id=%s AND session_token_hash=%s "
                "AND status IN ('outcome_unknown','manual_review_required') FOR UPDATE",
                (plan_id, device_id, PROTOCOL_V2, generation, row["current_runtime_instance_id"], row["session_token_hash"]),
            )
            if cursor.fetchone() is None:
                raise ConnectorRepositoryError("plan_reconciliation_invalid")
            cursor.execute("SELECT * FROM workmanship_sim_connector_runtime_recovery_sessions WHERE device_id=%s FOR UPDATE", (device_id,))
            prior = cursor.fetchone()
            if prior and prior["consumed_at"] is None and _utc(prior["expires_at"]) > now:
                raise ConnectorRepositoryError("reconciliation_session_active")
            values = (PROTOCOL_V2, generation, row["current_runtime_instance_id"], row["session_token_hash"],
                      recovery_instance_id, plan_id, token_hash, expires_at, now)
            if prior:
                cursor.execute(
                    "UPDATE workmanship_sim_connector_runtime_recovery_sessions SET protocol=%s,runtime_generation=%s,"
                    "execution_instance_id=%s,execution_session_token_hash=%s,recovery_instance_id=%s,plan_id=%s,"
                    "token_hash=%s,expires_at=%s,created_at=%s,consumed_at=NULL WHERE device_id=%s "
                    "AND runtime_generation=%s AND recovery_instance_id=%s AND token_hash=%s",
                    (*values, device_id, prior["runtime_generation"], prior["recovery_instance_id"], prior["token_hash"]),
                )
            else:
                cursor.execute(
                    "INSERT INTO workmanship_sim_connector_runtime_recovery_sessions (protocol,runtime_generation,"
                    "execution_instance_id,execution_session_token_hash,recovery_instance_id,plan_id,token_hash,"
                    "expires_at,created_at,device_id,scope) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'plan_reconciliation')",
                    (*values, device_id),
                )
            if cursor.rowcount != 1:
                raise ConnectorRepositoryError("runtime_session_conflict")
            self._runtime_audit(cursor, row, "reconciliation_session_registered", now,
                plan_id=plan_id, recovery_instance_id=recovery_instance_id, recovery_session_token_hash=token_hash)
            return {"device_id": device_id, "runtime_generation": generation, "recovery_instance_id": recovery_instance_id,
                    "plan_id": plan_id, "scope": "plan_reconciliation", "expires_at": expires_at}

    @staticmethod
    def _authenticated_recovery(cursor, row, generation, instance, token, plan_id, now):
        cursor.execute("SELECT * FROM workmanship_sim_connector_runtime_recovery_sessions WHERE device_id=%s FOR UPDATE", (row["device_id"],))
        recovery = cursor.fetchone()
        if (not recovery or recovery["protocol"] != PROTOCOL_V2 or recovery["scope"] != "plan_reconciliation"
                or recovery["runtime_generation"] != generation or row["runtime_generation"] != generation
                or recovery["recovery_instance_id"] != instance or recovery["consumed_at"] is not None
                or _utc(recovery["expires_at"]) <= now
                or recovery["execution_instance_id"] != row["current_runtime_instance_id"]
                or recovery["execution_session_token_hash"] != row["session_token_hash"]
                or not secrets.compare_digest(recovery["token_hash"], hashlib.sha256(token.encode("utf-8")).hexdigest())):
            raise ConnectorRepositoryError("runtime_session_invalid")
        if recovery["plan_id"] != plan_id:
            raise ConnectorRepositoryError("plan_lease_invalid")
        return recovery

    def insert_v2_plan(self, plan: ConnectorExecutionPlanV2, session_token: str, now: datetime) -> None:
        now = _utc(now)
        plan = ConnectorExecutionPlanV2.model_validate(plan)
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            row = self._authenticated_runtime(cursor, plan.device_id, plan.runtime_generation,
                plan.runtime_instance_id, session_token, now)
            if row["tenant_gid"] != plan.tenant_id or _utc(plan.expires_at) <= _utc(now):
                raise ConnectorRepositoryError("plan_lease_invalid")
            cursor.execute(
                "SELECT plan_id,plan_hash FROM workmanship_sim_connector_runtime_plans "
                "WHERE plan_id=%s OR (device_id=%s AND idempotency_key=%s) FOR UPDATE",
                (plan.plan_id, plan.device_id, plan.idempotency_key),
            )
            current = cursor.fetchone()
            if current:
                if current["plan_id"] != plan.plan_id or current["plan_hash"] != plan.plan_hash:
                    raise ConnectorRepositoryError("idempotency_conflict")
                return
            cursor.execute(
                "INSERT INTO workmanship_sim_connector_runtime_plans "
                "(plan_id,protocol,device_id,runtime_generation,runtime_instance_id,session_token_hash,"
                "tenant_gid,actor_gid,idempotency_key,plan_hash,plan_json,status,expires_at,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s,%s)",
                (plan.plan_id, PROTOCOL_V2, plan.device_id, plan.runtime_generation, plan.runtime_instance_id,
                 row["session_token_hash"], plan.tenant_id, plan.actor_id, plan.idempotency_key, plan.plan_hash,
                 canonicalize_v2(plan).decode("utf-8"), _utc(plan.expires_at), now, now),
            )
            self._runtime_audit(cursor, row, "plan_queued", now, plan_id=plan.plan_id)

    def lease_v2_plan(self, device_id, runtime_generation, runtime_instance_id, session_token, now, lease_seconds=60):
        now = _utc(now)
        lease_seconds = max(1, min(int(lease_seconds), 300))
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            row = self._authenticated_runtime(cursor, device_id, runtime_generation, runtime_instance_id, session_token, now)
            identity = (device_id, PROTOCOL_V2, runtime_generation, runtime_instance_id, row["session_token_hash"])
            scope = "device_id=%s AND protocol=%s AND runtime_generation=%s AND runtime_instance_id=%s AND session_token_hash=%s"
            cursor.execute(
                "UPDATE workmanship_sim_connector_runtime_plans SET status='outcome_unknown',"
                "reconciliation_state='pending',updated_at=%s WHERE " + scope +
                " AND status IN ('leased','executing') AND lease_until<=%s", (now, *identity, now),
            )
            if cursor.rowcount:
                self._runtime_audit(cursor, row, "lease_expired", now)
            cursor.execute(
                "UPDATE workmanship_sim_connector_runtime_plans SET status='expired',updated_at=%s WHERE " + scope +
                " AND status='queued' AND expires_at<=%s", (now, *identity, now),
            )
            if self._has_unresolved_plans(cursor, device_id):
                return None
            cursor.execute(
                "SELECT plan_id,plan_json,expires_at FROM workmanship_sim_connector_runtime_plans WHERE " + scope +
                " AND status='queued' AND expires_at>%s ORDER BY created_at,plan_id LIMIT 1 FOR UPDATE", (*identity, now),
            )
            current = cursor.fetchone()
            if current is None:
                return None
            lease_id = "lease-" + secrets.token_hex(16)
            lease_until = min(now + timedelta(seconds=lease_seconds), _utc(row["session_expires_at"]), _utc(current["expires_at"]))
            cursor.execute(
                "UPDATE workmanship_sim_connector_runtime_plans SET status='leased',lease_id=%s,lease_until=%s,"
                "attempts=attempts+1,updated_at=%s WHERE plan_id=%s AND " + scope + " AND status='queued'",
                (lease_id, lease_until, now, current["plan_id"], *identity),
            )
            if cursor.rowcount != 1:
                raise ConnectorRepositoryError("plan_lease_invalid")
            self._runtime_audit(cursor, row, "plan_leased", now, plan_id=current["plan_id"])
            value = current["plan_json"]
            return {"lease_id": lease_id, "lease_until": lease_until, "plan": json.loads(value) if isinstance(value, str) else value}

    def complete_v2_plan(self, device_id, runtime_generation, runtime_instance_id, session_token,
                         outcome: ConnectorPlanOutcomeV2, now: datetime) -> None:
        self._write_v2_outcome(device_id, runtime_generation, runtime_instance_id, session_token, outcome, now, reconciled=False)

    def mark_reconciled(self, device_id, runtime_generation, runtime_instance_id, session_token,
                        outcome: ConnectorPlanOutcomeV2, now: datetime) -> None:
        self._write_v2_outcome(device_id, runtime_generation, runtime_instance_id, session_token, outcome, now, reconciled=True)

    def _write_v2_outcome(self, device_id, generation, instance, token, outcome, now, *, reconciled):
        """Signature and probe authorization are provider responsibilities.

        Storage still independently matches all lease, tenant, plan-hash and
        session pins before persisting either an outcome or reconciliation.
        """
        outcome = ConnectorPlanOutcomeV2.model_validate(outcome)
        encoded = canonicalize_v2(outcome).decode("utf-8")
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        now = _utc(now)
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            recovery = None
            if reconciled:
                row = self._locked_runtime(cursor, device_id)
                if row["session_expires_at"] and _utc(row["session_expires_at"]) <= now:
                    recovery = self._authenticated_recovery(cursor, row, generation, instance, token, outcome.plan_id, now)
                else:
                    row = self._authenticated_runtime(cursor, device_id, generation, instance, token, now)
            else:
                row = self._authenticated_runtime(cursor, device_id, generation, instance, token, now)
            execution_instance = row["current_runtime_instance_id"]
            if (outcome.device_id, outcome.runtime_generation, outcome.runtime_instance_id) != (device_id, generation, execution_instance):
                raise ConnectorRepositoryError("plan_lease_invalid")
            identity = (outcome.plan_id, device_id, PROTOCOL_V2, generation, execution_instance, row["session_token_hash"], outcome.lease_id)
            scope = "plan_id=%s AND device_id=%s AND protocol=%s AND runtime_generation=%s AND runtime_instance_id=%s AND session_token_hash=%s AND lease_id=%s"
            cursor.execute("SELECT * FROM workmanship_sim_connector_runtime_plans WHERE " + scope + " FOR UPDATE", identity)
            current = cursor.fetchone()
            if not current or current["plan_hash"] != outcome.plan_hash or current["tenant_gid"] != outcome.tenant_id:
                raise ConnectorRepositoryError("plan_lease_invalid")
            if current["outcome_hash"] == digest and (not reconciled or current["reconciled_at"] is not None):
                return
            if reconciled:
                if outcome.overall_status not in {"succeeded", "failed_without_effect", "manual_review_required"}:
                    raise ConnectorRepositoryError("reconciliation_result_invalid")
                uncertain = current["status"] in {"outcome_unknown", "manual_review_required"}
                expired = current["status"] in {"leased", "executing"} and _utc(current["lease_until"]) <= now
                if not uncertain and not expired:
                    raise ConnectorRepositoryError("plan_reconciliation_invalid")
                reconciliation_state = outcome.overall_status
            else:
                if current["outcome_hash"] is not None:
                    raise ConnectorRepositoryError("connector_outcome_conflict")
                if current["status"] not in {"leased", "executing"} or _utc(current["lease_until"]) <= now:
                    raise ConnectorRepositoryError("plan_lease_invalid")
                reconciliation_state = {"outcome_unknown": "pending", "manual_review_required": "manual_review_required"}.get(outcome.overall_status, "not_required")
            cursor.execute(
                "UPDATE workmanship_sim_connector_runtime_plans SET status=%s,outcome_json=%s,outcome_hash=%s,"
                "reconciliation_state=%s,reconciled_at=%s,updated_at=%s WHERE " + scope + " AND status=%s",
                (outcome.overall_status, encoded, digest, reconciliation_state, now if reconciled else None, now, *identity, current["status"]),
            )
            if cursor.rowcount != 1:
                raise ConnectorRepositoryError("plan_lease_invalid")
            self._runtime_audit(cursor, row, "plan_reconciled" if reconciled else "plan_outcome", now,
                plan_id=outcome.plan_id, outcome_hash=digest, recovery_instance_id=instance if recovery else None,
                recovery_session_token_hash=recovery["token_hash"] if recovery else None, outcome_json=encoded)
            if recovery and outcome.overall_status in {"succeeded", "failed_without_effect"}:
                cursor.execute(
                    "UPDATE workmanship_sim_connector_runtime_recovery_sessions SET consumed_at=%s WHERE device_id=%s "
                    "AND runtime_generation=%s AND recovery_instance_id=%s AND token_hash=%s AND plan_id=%s AND consumed_at IS NULL",
                    (now, device_id, generation, instance, recovery["token_hash"], outcome.plan_id),
                )
                if cursor.rowcount != 1:
                    raise ConnectorRepositoryError("runtime_session_conflict")

    def authenticate_connector(self, connector_id: str, token: str) -> dict:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT connector_id,owner_user_gid,team_gid,installation_id,token_hash,status "
                "FROM workmanship_sim_connector_bindings WHERE connector_id=%s LIMIT 1",
                (connector_id,),
            )
            row = cursor.fetchone()
        if (
            not row or row["status"] not in {"offline", "online"}
            or not secrets.compare_digest(str(row["token_hash"]), digest)
        ):
            raise PermissionError("invalid_connector_credentials")
        return row

    def can_use_connector(
        self, connector_id: str, *, user_gid: str, team_gid: str,
    ) -> bool:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM workmanship_sim_connector_bindings "
                "WHERE connector_id=%s AND owner_user_gid=%s "
                "AND (team_gid=%s OR team_gid IS NULL) "
                "AND status IN ('offline','online') LIMIT 1",
                (connector_id, user_gid, team_gid),
            )
            return cursor.fetchone() is not None

    def binding_for_user(self, user_gid: str, team_gid: str | None = None) -> dict | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            if team_gid is None:
                cursor.execute(
                    "SELECT connector_id,installation_id,team_gid,status,pending_pairing_id "
                    "FROM workmanship_sim_connector_bindings WHERE owner_user_gid=%s LIMIT 1",
                    (user_gid,),
                )
            else:
                cursor.execute(
                    "SELECT connector_id,installation_id,team_gid,status,pending_pairing_id "
                    "FROM workmanship_sim_connector_bindings "
                    "WHERE owner_user_gid=%s AND team_gid=%s LIMIT 1",
                    (user_gid, team_gid),
                )
            return cursor.fetchone()

    def get_health(self, connector_id: str) -> ConnectorHealth | None:
        from ..capabilities.connector_contracts import ConnectorHealth

        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT health_json FROM workmanship_sim_connector_health "
                "WHERE connector_id=%s LIMIT 1",
                (connector_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        value = row["health_json"]
        if isinstance(value, str):
            value = json.loads(value)
        return ConnectorHealth.model_validate(value)

    def save_health(self, connector_id: str, health: ConnectorHealth) -> None:
        data = health.model_dump(mode="json")
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = canonical_hash(data)
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO workmanship_sim_connector_health "
                    "(connector_id,bound_user_id,session_id,health_json,health_hash,reported_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                    "bound_user_id=VALUES(bound_user_id),session_id=VALUES(session_id),"
                    "health_json=VALUES(health_json),health_hash=VALUES(health_hash),"
                    "reported_at=VALUES(reported_at),updated_at=NOW(6)",
                    (connector_id, health.bound_user_id, health.session_id, encoded, digest, health.reported_at),
                )
                cursor.execute(
                    "INSERT INTO workmanship_sim_connector_heartbeat_audit "
                    "(gid,connector_id,health_hash,health_json,reported_at) VALUES (%s,%s,%s,%s,%s)",
                    ("connector-heartbeat-" + uuid.uuid4().hex, connector_id, digest, encoded, health.reported_at),
                )
                cursor.execute(
                    "UPDATE workmanship_sim_connector_bindings SET status='online',"
                    "runtime_version=%s,last_seen_at=%s,updated_at=NOW(6) "
                    "WHERE connector_id=%s AND owner_user_gid=%s AND status IN ('offline','online')",
                    (
                        health.connector_version, health.reported_at,
                        connector_id, health.bound_user_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConnectorRepositoryError("connector_binding_not_found")

    def insert_plan(self, plan: ConnectorExecutionPlanV1) -> None:
        encoded = json.dumps(
            plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT plan_hash FROM workmanship_sim_connector_plans WHERE plan_id=%s FOR UPDATE",
                    (plan.plan_id,),
                )
                current = cursor.fetchone()
                if current:
                    if current["plan_hash"] != plan.plan_hash:
                        raise ConnectorRepositoryError("idempotency_conflict")
                    return
                cursor.execute(
                    "INSERT INTO workmanship_sim_connector_plans "
                    "(plan_id,connector_id,tenant_gid,user_gid,plan_hash,plan_json,status,expires_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'queued',%s)",
                    (plan.plan_id, plan.device_id, plan.tenant_id, plan.user_id, plan.plan_hash, encoded, plan.expires_at),
                )

    def lease_plan(self, connector_id: str, lease_seconds: int = 60):
        lease_seconds = max(15, min(int(lease_seconds), 300))
        lease_id = "connector-lease-" + secrets.token_hex(16)
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT device_id FROM workmanship_sim_connector_runtime_devices WHERE device_id=%s FOR UPDATE",
                    (connector_id,),
                )
                if cursor.fetchone() is not None:
                    return None
                cursor.execute(
                    "UPDATE workmanship_sim_connector_plans SET status='outcome_unknown',updated_at=NOW(6) "
                    "WHERE connector_id=%s AND status='leased' AND lease_until<=UTC_TIMESTAMP(6)",
                    (connector_id,),
                )
                cursor.execute(
                    "UPDATE workmanship_sim_connector_plans SET status='expired',updated_at=NOW(6) "
                    "WHERE connector_id=%s AND status='queued' AND expires_at<=UTC_TIMESTAMP(6)",
                    (connector_id,),
                )
                cursor.execute(
                    "SELECT plan_id,plan_json FROM workmanship_sim_connector_plans "
                    "WHERE connector_id=%s AND status='queued' AND expires_at>UTC_TIMESTAMP(6) "
                    "ORDER BY created_at LIMIT 1 FOR UPDATE",
                    (connector_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                cursor.execute(
                    "UPDATE workmanship_sim_connector_plans SET status='leased',lease_id=%s,"
                    "lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL %s SECOND),attempts=attempts+1,updated_at=NOW(6) "
                    "WHERE plan_id=%s AND status='queued'",
                    (lease_id, lease_seconds, row["plan_id"]),
                )
        value = row["plan_json"]
        if isinstance(value, str):
            value = json.loads(value)
        return {"lease_id": lease_id, "plan": value}

    def get_plan(
        self, plan_id: str, *, connector_id: str, lease_id: str,
    ) -> ConnectorExecutionPlanV1:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT plan_json FROM workmanship_sim_connector_plans "
                "WHERE plan_id=%s AND connector_id=%s AND lease_id=%s AND ("
                "(status='leased' AND lease_until>UTC_TIMESTAMP(6) AND expires_at>UTC_TIMESTAMP(6)) OR "
                "(status IN ('completed','failed','cancelled','outcome_unknown') AND outcome_hash IS NOT NULL)"
                ") LIMIT 1",
                (plan_id, connector_id, lease_id),
            )
            row = cursor.fetchone()
        if not row:
            raise ConnectorRepositoryError("plan_lease_invalid")
        value = row["plan_json"]
        if isinstance(value, str):
            value = json.loads(value)
        return ConnectorExecutionPlanV1.model_validate(value)

    def get_plan_result(self, plan_id: str, user_gid: str, team_gid: str) -> dict | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT plan_id,status,outcome_json FROM workmanship_sim_connector_plans "
                "WHERE plan_id=%s AND user_gid=%s AND tenant_gid=%s LIMIT 1",
                (plan_id, user_gid, team_gid),
            )
            row = cursor.fetchone()
        if not row:
            return None
        outcome = row.get("outcome_json")
        if isinstance(outcome, str):
            outcome = json.loads(outcome)
        return {"operation_id": row["plan_id"], "status": row["status"], "outcome": outcome}

    def complete_plan(
        self, connector_id: str, plan_id: str, lease_id: str,
        outcome: ConnectorPlanOutcomeV1,
    ) -> None:
        data = outcome.model_dump(mode="json")
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = canonical_hash(data)
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT status,outcome_hash FROM workmanship_sim_connector_plans "
                    "WHERE plan_id=%s AND connector_id=%s AND lease_id=%s FOR UPDATE",
                    (plan_id, connector_id, lease_id),
                )
                current = cursor.fetchone()
                if not current:
                    raise ConnectorRepositoryError("plan_lease_invalid")
                if current["outcome_hash"] is not None:
                    if current["outcome_hash"] != digest:
                        raise ConnectorRepositoryError("idempotency_conflict")
                    return
                cursor.execute(
                    "UPDATE workmanship_sim_connector_plans SET status=%s,outcome_json=%s,"
                    "outcome_hash=%s,updated_at=NOW(6) WHERE plan_id=%s AND connector_id=%s "
                    "AND status='leased' AND lease_id=%s AND lease_until>UTC_TIMESTAMP(6)",
                    (outcome.status, encoded, digest, plan_id, connector_id, lease_id),
                )
                if cursor.rowcount != 1:
                    raise ConnectorRepositoryError("plan_lease_invalid")

    def complete_with_projection_intent(
        self, connector_id: str, plan_id: str, lease_id: str,
        outcome: ConnectorPlanOutcomeV1, target_capability: str,
    ) -> ProjectionIntent:
        """Persist the terminal outcome and its projection intent atomically."""
        data = outcome.model_dump(mode="json")
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = canonical_hash(data)
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT status,outcome_hash,outcome_json FROM workmanship_sim_connector_plans "
                    "WHERE plan_id=%s AND connector_id=%s AND lease_id=%s FOR UPDATE",
                    (plan_id, connector_id, lease_id),
                )
                current = cursor.fetchone()
                if not current:
                    raise ConnectorRepositoryError("plan_lease_invalid")
                if current["outcome_hash"] is not None:
                    if current["outcome_hash"] != digest:
                        raise ConnectorRepositoryError("connector_outcome_conflict")
                else:
                    cursor.execute(
                        "UPDATE workmanship_sim_connector_plans SET status=%s,outcome_json=%s,"
                        "outcome_hash=%s,updated_at=NOW(6) WHERE plan_id=%s AND connector_id=%s "
                        "AND status='leased' AND lease_id=%s AND lease_until>UTC_TIMESTAMP(6)",
                        (outcome.status, encoded, digest, plan_id, connector_id, lease_id),
                    )
                    if cursor.rowcount != 1:
                        raise ConnectorRepositoryError("plan_lease_invalid")
                cursor.execute(
                    "INSERT INTO workmanship_sim_connector_projection_outbox "
                    "(plan_id,outcome_hash,target_capability,attempt,status,next_retry_at) "
                    "VALUES (%s,%s,%s,0,'pending',NOW(6)) "
                    "ON DUPLICATE KEY UPDATE outcome_hash=VALUES(outcome_hash)",
                    (plan_id, digest, target_capability),
                )
        return ProjectionIntent(plan_id, digest, target_capability, "pending")

    def claim_projection(
        self, owner: str, lease_seconds: int = 60,
    ) -> ProjectionLease | None:
        if not owner:
            raise ConnectorRepositoryError("projection_owner_required")
        lease_seconds = max(15, min(int(lease_seconds), 300))
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT plan_id,outcome_hash,target_capability,attempt "
                    "FROM workmanship_sim_connector_projection_outbox "
                    "WHERE status IN ('pending','retryable_failed') "
                    "AND (next_retry_at IS NULL OR next_retry_at<=NOW(6)) "
                    "ORDER BY created_at LIMIT 1 FOR UPDATE"
                )
                row = cursor.fetchone()
                if not row:
                    return None
                cursor.execute(
                    "UPDATE workmanship_sim_connector_projection_outbox "
                    "SET status='projecting',lease_owner=%s,"
                    "lease_until=DATE_ADD(NOW(6),INTERVAL %s SECOND),"
                    "attempt=attempt+1,error_code=NULL,updated_at=NOW(6) "
                    "WHERE plan_id=%s AND outcome_hash=%s AND target_capability=%s "
                    "AND status IN ('pending','retryable_failed')",
                    (
                        owner, lease_seconds, row["plan_id"], row["outcome_hash"],
                        row["target_capability"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConnectorRepositoryError("projection_claim_conflict")
        return ProjectionLease(
            plan_id=row["plan_id"], outcome_hash=row["outcome_hash"],
            target_capability=row["target_capability"],
            attempt=int(row["attempt"]) + 1, owner=owner,
        )

    def read_projection_payload(
        self, lease: ProjectionLease,
    ) -> tuple[ConnectorExecutionPlanV1, ConnectorPlanOutcomeV1]:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT p.plan_json,p.outcome_json,p.outcome_hash "
                "FROM workmanship_sim_connector_plans p "
                "JOIN workmanship_sim_connector_projection_outbox o "
                "ON o.plan_id=p.plan_id AND o.outcome_hash=p.outcome_hash "
                "WHERE o.plan_id=%s AND o.outcome_hash=%s AND o.target_capability=%s "
                "AND o.status='projecting' AND o.lease_owner=%s "
                "AND o.lease_until>NOW(6) LIMIT 1",
                (
                    lease.plan_id, lease.outcome_hash, lease.target_capability,
                    lease.owner,
                ),
            )
            row = cursor.fetchone()
        if not row or row["outcome_hash"] != lease.outcome_hash:
            raise ConnectorRepositoryError("projection_lease_invalid")
        plan_value = row["plan_json"]
        outcome_value = row["outcome_json"]
        if isinstance(plan_value, str):
            plan_value = json.loads(plan_value)
        if isinstance(outcome_value, str):
            outcome_value = json.loads(outcome_value)
        return (
            ConnectorExecutionPlanV1.model_validate(plan_value),
            ConnectorPlanOutcomeV1.model_validate(outcome_value),
        )

    def finish_projection(self, plan_id: str, owner: str) -> None:
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE workmanship_sim_connector_projection_outbox "
                    "SET status='projected',projected_at=NOW(6),lease_owner=NULL,"
                    "lease_until=NULL,updated_at=NOW(6) "
                    "WHERE plan_id=%s AND status='projecting' AND lease_owner=%s "
                    "AND lease_until>NOW(6)",
                    (plan_id, owner),
                )
                if cursor.rowcount != 1:
                    raise ConnectorRepositoryError("projection_lease_invalid")

    def fail_projection(
        self, plan_id: str, owner: str, *, error_code: str, retryable: bool,
    ) -> None:
        status = "retryable_failed" if retryable else "reconciliation_required"
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE workmanship_sim_connector_projection_outbox "
                    "SET status=%s,error_code=%s,lease_owner=NULL,lease_until=NULL,"
                    "next_retry_at=IF(%s,DATE_ADD(NOW(6),INTERVAL 5 SECOND),NULL),"
                    "updated_at=NOW(6) WHERE plan_id=%s AND status='projecting' "
                    "AND lease_owner=%s AND lease_until>NOW(6)",
                    (status, error_code[:128], retryable, plan_id, owner),
                )
                if cursor.rowcount != 1:
                    raise ConnectorRepositoryError("projection_lease_invalid")

    def reclaim_stale_projections(self, now: datetime | None = None) -> int:
        cutoff = now or datetime.now(UTC)
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE workmanship_sim_connector_projection_outbox "
                    "SET status='retryable_failed',lease_owner=NULL,lease_until=NULL,"
                    "next_retry_at=%s,error_code='projection_lease_expired',updated_at=NOW(6) "
                    "WHERE status='projecting' AND lease_until<=%s",
                    (cutoff, cutoff),
                )
                return int(cursor.rowcount)


class SqlPairingRepository:
    @staticmethod
    def _bootstrap(row) -> BootstrapRecord | None:
        if not row:
            return None
        expires_at = row["expires_at"]
        return BootstrapRecord(
            bootstrap_id=row["bootstrap_id"], owner_user_gid=row["owner_user_gid"],
            team_gid=row["team_gid"], token_hash=row["token_hash"], status=row["status"],
            pairing_id=row.get("pairing_id"),
            expires_at=expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at,
            resource_version=int(row.get("resource_version", 1)),
        )

    @staticmethod
    def _record(row) -> PairingRecord | None:
        if not row:
            return None
        envelope = row.get("credential_envelope_json")
        if isinstance(envelope, str):
            envelope = json.loads(envelope)
        return PairingRecord(
            pairing_id=row["pairing_id"], user_code=row["user_code_display"],
            installation_id=row["installation_id"],
            verifier_hash=row["verifier_hash"], device_name=row["device_name"],
            runtime_version=row["runtime_version"],
            windows_sid_hash=row["windows_sid_hash"],
            masked_windows_user=row["masked_windows_user"],
            ephemeral_public_key=row["ephemeral_public_key"], status=row["status"],
            expires_at=row["expires_at"].replace(tzinfo=UTC) if row["expires_at"].tzinfo is None else row["expires_at"],
            resource_version=int(row["resource_version"]),
            approved_user_gid=row.get("approved_user_gid"), team_gid=row.get("team_gid"),
            connector_id=row.get("connector_id"),
            encrypted_envelope=(envelope or {}).get("ciphertext"),
            envelope_hash=row.get("credential_envelope_hash"),
            activation_challenge_hash=row.get("activation_challenge_hash"),
            activation_status=row.get("activation_status", "not_issued"),
        )

    @staticmethod
    def _insert_pairing(cursor, record: PairingRecord) -> None:
        nonce_hash = hashlib.sha256(
            f"{record.installation_id}:{record.pairing_id}".encode("utf-8")
        ).hexdigest()
        user_code_hash = hashlib.sha256(record.user_code.encode("utf-8")).hexdigest()
        cursor.execute(
            "INSERT INTO workmanship_sim_connector_pairings "
            "(pairing_id,installation_id,nonce_hash,verifier_hash,user_code_hash,user_code_display,"
            "device_name,runtime_version,windows_sid_hash,masked_windows_user,ephemeral_public_key,"
            "status,resource_version,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                record.pairing_id, record.installation_id, nonce_hash,
                record.verifier_hash, user_code_hash, record.user_code,
                record.device_name, record.runtime_version, record.windows_sid_hash,
                record.masked_windows_user, record.ephemeral_public_key,
                record.status, record.resource_version, record.expires_at,
            ),
        )

    def create_pairing(self, record: PairingRecord) -> None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            self._insert_pairing(cursor, record)

    def by_code(self, user_code: str) -> PairingRecord | None:
        digest = hashlib.sha256(user_code.encode("utf-8")).hexdigest()
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairings WHERE user_code_hash=%s LIMIT 1",
                (digest,),
            )
            return self._record(cursor.fetchone())

    def by_id(self, pairing_id: str) -> PairingRecord | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairings WHERE pairing_id=%s LIMIT 1",
                (pairing_id,),
            )
            return self._record(cursor.fetchone())

    def binding_for_user(self, user_gid: str, team_gid: str | None = None) -> dict | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            if team_gid is None:
                cursor.execute(
                    "SELECT connector_id,installation_id,team_gid,status,pending_pairing_id "
                    "FROM workmanship_sim_connector_bindings WHERE owner_user_gid=%s LIMIT 1",
                    (user_gid,),
                )
            else:
                cursor.execute(
                    "SELECT connector_id,installation_id,team_gid,status,pending_pairing_id "
                    "FROM workmanship_sim_connector_bindings "
                    "WHERE owner_user_gid=%s AND team_gid=%s LIMIT 1",
                    (user_gid, team_gid),
                )
            return cursor.fetchone()

    def create_bootstrap(self, record: BootstrapRecord) -> None:
        try:
            with get_simulation_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO workmanship_sim_connector_pairing_bootstraps "
                    "(bootstrap_id,owner_user_gid,team_gid,token_hash,status,expires_at,resource_version) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        record.bootstrap_id, record.owner_user_gid, record.team_gid,
                        record.token_hash, record.status, record.expires_at, record.resource_version,
                    ),
                )
        except IntegrityError as exc:
            raise PairingError("pairing_bootstrap_conflict") from exc

    def bootstrap_by_id(self, bootstrap_id: str) -> BootstrapRecord | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairing_bootstraps "
                "WHERE bootstrap_id=%s LIMIT 1", (bootstrap_id,),
            )
            return self._bootstrap(cursor.fetchone())

    def claim_bootstrap(self, token_hash: str, now: datetime) -> BootstrapRecord:
        with get_simulation_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM workmanship_sim_connector_pairing_bootstraps "
                    "WHERE token_hash=%s LIMIT 1 FOR UPDATE", (token_hash,),
                )
                record = self._bootstrap(cursor.fetchone())
                if record is None:
                    raise PairingError("pairing_bootstrap_not_found")
                if record.expires_at <= now:
                    cursor.execute(
                        "UPDATE workmanship_sim_connector_pairing_bootstraps SET status='expired',updated_at=NOW(6) "
                        "WHERE bootstrap_id=%s AND status NOT IN ('active','cancelled')",
                        (record.bootstrap_id,),
                    )
                    raise PairingError("pairing_bootstrap_expired")
                if record.status != "created":
                    raise PairingError("pairing_bootstrap_reused")
                cursor.execute(
                    "UPDATE workmanship_sim_connector_pairing_bootstraps SET status='claimed',resource_version=resource_version+1,"
                    "updated_at=NOW(6) WHERE bootstrap_id=%s AND status='created' AND resource_version=%s",
                    (record.bootstrap_id, record.resource_version),
                )
                if cursor.rowcount != 1:
                    raise PairingError("pairing_bootstrap_reused")
                return BootstrapRecord(
                    **{**record.__dict__, "status": "claimed", "resource_version": record.resource_version + 1},
                )

    def link_bootstrap_pairing(self, bootstrap_id: str, pairing_id: str) -> None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairing_bootstraps SET pairing_id=%s,updated_at=NOW(6) "
                "WHERE bootstrap_id=%s AND status='claimed' AND pairing_id IS NULL",
                (pairing_id, bootstrap_id),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_bootstrap_reused")

    def create_pairing_from_bootstrap(
        self, token_hash: str, now: datetime, record: PairingRecord,
    ) -> BootstrapRecord:
        try:
            with get_simulation_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM workmanship_sim_connector_pairing_bootstraps "
                    "WHERE token_hash=%s LIMIT 1 FOR UPDATE", (token_hash,),
                )
                bootstrap = self._bootstrap(cursor.fetchone())
                if bootstrap is None:
                    raise PairingError("pairing_bootstrap_not_found")
                if bootstrap.expires_at <= now:
                    raise PairingError("pairing_bootstrap_expired")
                if bootstrap.status != "created":
                    raise PairingError("pairing_bootstrap_reused")
                self._insert_pairing(cursor, record)
                cursor.execute(
                    "UPDATE workmanship_sim_connector_pairing_bootstraps SET status='claimed',pairing_id=%s,"
                    "resource_version=resource_version+1,updated_at=NOW(6) WHERE bootstrap_id=%s "
                    "AND status='created' AND resource_version=%s",
                    (record.pairing_id, bootstrap.bootstrap_id, bootstrap.resource_version),
                )
                if cursor.rowcount != 1:
                    raise PairingError("pairing_bootstrap_reused")
                return BootstrapRecord(**{
                    **bootstrap.__dict__, "status": "claimed", "pairing_id": record.pairing_id,
                    "resource_version": bootstrap.resource_version + 1,
                })
        except IntegrityError as exc:
            raise PairingError("pairing_identity_conflict") from exc

    def bootstrap_for_pairing(self, pairing_id: str) -> BootstrapRecord | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairing_bootstraps "
                "WHERE pairing_id=%s LIMIT 1", (pairing_id,),
            )
            return self._bootstrap(cursor.fetchone())

    def expire_bootstrap(self, bootstrap_id: str, expected_version: int) -> BootstrapRecord:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairing_bootstraps SET status='expired',"
                "resource_version=resource_version+1,updated_at=NOW(6) "
                "WHERE bootstrap_id=%s AND status='created' AND resource_version=%s",
                (bootstrap_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_bootstrap_version_conflict")
        record = self.bootstrap_by_id(bootstrap_id)
        if record is None:
            raise PairingError("pairing_bootstrap_not_found")
        return record

    def expire_pairing(self, pairing_id: str, expected_version: int) -> PairingRecord:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairings SET status='expired',"
                "resource_version=resource_version+1,updated_at=NOW(6) "
                "WHERE pairing_id=%s AND status IN ('pending','approved') AND resource_version=%s",
                (pairing_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_version_conflict")
        record = self.by_id(pairing_id)
        if record is None:
            raise PairingError("pairing_not_found")
        return record

    def cancel_bootstrap(
        self, bootstrap_id: str, owner_user_gid: str, team_gid: str, expected_version: int,
    ) -> BootstrapRecord:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairing_bootstraps "
                "WHERE bootstrap_id=%s LIMIT 1 FOR UPDATE", (bootstrap_id,),
            )
            existing = self._bootstrap(cursor.fetchone())
            if existing is None or existing.owner_user_gid != owner_user_gid or existing.team_gid != team_gid:
                raise PairingError("pairing_bootstrap_not_found")
            if existing.status == "active":
                raise PairingError("pairing_bootstrap_active")
            if existing.resource_version != expected_version or existing.status not in {"created", "claimed"}:
                raise PairingError("pairing_bootstrap_version_conflict")
            if existing.pairing_id:
                cursor.execute(
                    "SELECT * FROM workmanship_sim_connector_pairings WHERE pairing_id=%s FOR UPDATE",
                    (existing.pairing_id,),
                )
                pairing = self._record(cursor.fetchone())
                if pairing and pairing.status == "pending":
                    cursor.execute(
                        "UPDATE workmanship_sim_connector_pairings SET status='rejected',"
                        "resource_version=resource_version+1,updated_at=NOW(6) "
                        "WHERE pairing_id=%s AND status='pending'", (pairing.pairing_id,),
                    )
                    if cursor.rowcount != 1:
                        raise PairingError("pairing_version_conflict")
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairing_bootstraps SET status='cancelled',resource_version=resource_version+1,"
                "updated_at=NOW(6) WHERE bootstrap_id=%s AND owner_user_gid=%s AND team_gid=%s "
                "AND resource_version=%s AND status IN ('created','claimed')",
                (bootstrap_id, owner_user_gid, team_gid, expected_version),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_bootstrap_version_conflict")
            return BootstrapRecord(**{
                **existing.__dict__, "status": "cancelled",
                "resource_version": existing.resource_version + 1,
            })

    def approve_pairing(self, record: PairingRecord, *, expected_version: int) -> None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairing_bootstraps "
                "WHERE pairing_id=%s LIMIT 1 FOR UPDATE", (record.pairing_id,),
            )
            bootstrap = self._bootstrap(cursor.fetchone())
            if (
                bootstrap is None or bootstrap.status != "claimed"
                or bootstrap.owner_user_gid != record.approved_user_gid
                or bootstrap.team_gid != record.team_gid
            ):
                raise PairingError("pairing_bootstrap_version_conflict")
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairings WHERE pairing_id=%s FOR UPDATE",
                (record.pairing_id,),
            )
            current = self._record(cursor.fetchone())
            if current is None or current.status != "pending" or current.resource_version != expected_version:
                raise PairingError("pairing_version_conflict")
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairings SET status='approved',"
                "resource_version=%s,approved_user_gid=%s,team_gid=%s,approved_at=NOW(6),"
                "updated_at=NOW(6) WHERE pairing_id=%s AND status='pending' "
                "AND resource_version=%s",
                (
                    record.resource_version, record.approved_user_gid,
                    record.team_gid, record.pairing_id, expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_version_conflict")
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairing_bootstraps SET status='approved',"
                "resource_version=resource_version+1,updated_at=NOW(6) "
                "WHERE bootstrap_id=%s AND status='claimed' AND resource_version=%s",
                (bootstrap.bootstrap_id, bootstrap.resource_version),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_bootstrap_version_conflict")

    def issue_credential(self, record: PairingRecord, user_gid: str, binding: dict) -> PairingRecord:
        envelope_json = json.dumps(
            {"ciphertext": record.encrypted_envelope}, separators=(",", ":"),
        )
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairing_bootstraps "
                "WHERE pairing_id=%s LIMIT 1 FOR UPDATE", (record.pairing_id,),
            )
            bootstrap = self._bootstrap(cursor.fetchone())
            if bootstrap is None or bootstrap.status not in {"approved", "credential_issued", "active"}:
                raise PairingError("pairing_bootstrap_version_conflict")
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairings WHERE pairing_id=%s FOR UPDATE",
                (record.pairing_id,),
            )
            current = self._record(cursor.fetchone())
            if current is None:
                raise PairingError("pairing_not_found")
            if current.activation_status in {"credential_issued", "active"}:
                expected_bootstrap = "active" if current.activation_status == "active" else "credential_issued"
                if bootstrap.status != expected_bootstrap:
                    raise PairingError("pairing_bootstrap_version_conflict")
                return current
            cursor.execute(
                "SELECT connector_id,installation_id,team_gid,pending_pairing_id "
                "FROM workmanship_sim_connector_bindings "
                "WHERE owner_user_gid=%s FOR UPDATE",
                (user_gid,),
            )
            existing = cursor.fetchone()
            if existing and existing["installation_id"] != binding["installation_id"]:
                raise PairingError("connector_binding_conflict")
            if existing and existing["connector_id"] != binding["connector_id"]:
                raise PairingError("connector_binding_conflict")
            if existing and existing.get("team_gid") != binding.get("team_gid"):
                raise PairingError("connector_binding_conflict")
            if not existing:
                try:
                    cursor.execute(
                        "INSERT INTO workmanship_sim_connector_bindings "
                        "(connector_id,owner_user_gid,team_gid,installation_id,windows_sid_hash,display_name,"
                        "platform,runtime_version,token_hash,capabilities,status,pending_pairing_id) "
                        "VALUES (%s,%s,%s,%s,%s,%s,'windows',%s,%s,JSON_ARRAY('ai00.vismockup@1'),'pending_activation',%s)",
                        (
                            binding["connector_id"], user_gid, binding.get("team_gid"),
                            binding["installation_id"], binding["windows_sid_hash"],
                            binding["display_name"], binding["runtime_version"], binding["token_hash"],
                            record.pairing_id,
                        ),
                    )
                except IntegrityError as exc:
                    raise PairingError("connector_binding_conflict") from exc
            else:
                cursor.execute(
                    "UPDATE workmanship_sim_connector_bindings SET team_gid=%s,windows_sid_hash=%s,"
                    "display_name=%s,runtime_version=%s,token_hash=%s,status='pending_activation',pending_pairing_id=%s,"
                    "updated_at=NOW(6) WHERE connector_id=%s AND owner_user_gid=%s "
                    "AND installation_id=%s",
                    (
                        binding.get("team_gid"), binding["windows_sid_hash"], binding["display_name"],
                        binding["runtime_version"], binding["token_hash"], record.pairing_id,
                        binding["connector_id"], user_gid, binding["installation_id"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise PairingError("connector_binding_conflict")
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairings SET status='completing',resource_version=%s,"
                "connector_id=%s,credential_envelope_json=%s,credential_envelope_hash=%s,"
                "activation_challenge_hash=%s,activation_status='credential_issued',updated_at=NOW(6) "
                "WHERE pairing_id=%s AND status='approved' AND approved_user_gid=%s "
                "AND resource_version=%s",
                (
                    record.resource_version, record.connector_id, envelope_json,
                    record.envelope_hash, record.activation_challenge_hash, record.pairing_id, user_gid,
                    record.resource_version - 1,
                ),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_version_conflict")
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairing_bootstraps SET status='credential_issued',"
                "resource_version=resource_version+1,updated_at=NOW(6) "
                "WHERE bootstrap_id=%s AND status='approved' AND resource_version=%s",
                (bootstrap.bootstrap_id, bootstrap.resource_version),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_bootstrap_version_conflict")
            return record

    def activate_pairing(self, record: PairingRecord, *, expected_version: int) -> None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairing_bootstraps "
                "WHERE pairing_id=%s LIMIT 1 FOR UPDATE", (record.pairing_id,),
            )
            bootstrap = self._bootstrap(cursor.fetchone())
            if bootstrap is not None and bootstrap.status == "active":
                raise PairingError("pairing_version_conflict")
            if bootstrap is None or bootstrap.status != "credential_issued":
                raise PairingError("pairing_bootstrap_version_conflict")
            cursor.execute(
                "SELECT * FROM workmanship_sim_connector_pairings WHERE pairing_id=%s FOR UPDATE",
                (record.pairing_id,),
            )
            current = self._record(cursor.fetchone())
            if (
                current is None or current.connector_id != record.connector_id
                or current.activation_status != "credential_issued"
            ):
                raise PairingError("pairing_version_conflict")
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairings SET status='completed',activation_status='active',"
                "resource_version=%s,completed_at=NOW(6),activated_at=NOW(6),updated_at=NOW(6) "
                "WHERE pairing_id=%s AND connector_id=%s AND status='completing' "
                "AND activation_status='credential_issued' AND resource_version=%s",
                (expected_version + 1, record.pairing_id, record.connector_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_version_conflict")
            cursor.execute(
                "UPDATE workmanship_sim_connector_bindings SET status='offline',pending_pairing_id=NULL,activated_at=NOW(6),"
                "updated_at=NOW(6) WHERE connector_id=%s AND owner_user_gid=%s "
                "AND pending_pairing_id=%s AND status='pending_activation'",
                (record.connector_id, current.approved_user_gid, record.pairing_id),
            )
            if cursor.rowcount != 1:
                raise PairingError("connector_binding_conflict")
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairing_bootstraps SET status='active',"
                "resource_version=resource_version+1,updated_at=NOW(6) "
                "WHERE bootstrap_id=%s AND status='credential_issued' AND resource_version=%s",
                (bootstrap.bootstrap_id, bootstrap.resource_version),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_bootstrap_version_conflict")


__all__ = [
    "ConnectorRepositoryError", "ProjectionIntent", "ProjectionLease", "RuntimeSession",
    "SimulationConnectorRepository", "SqlPairingRepository",
]
