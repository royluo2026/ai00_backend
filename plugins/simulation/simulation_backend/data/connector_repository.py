"""Simulation persistence adapter for AI00 Connector state and plans."""
from __future__ import annotations

import json
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    ConnectorPlanOutcomeV1,
    canonical_hash,
)

from ..capabilities.connector_contracts import ConnectorHealth
from ..domain.connector_pairing import PairingError, PairingRecord
from .connection import get_simulation_conn


class ConnectorRepositoryError(RuntimeError):
    pass


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
            not row or row["status"] == "revoked"
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
                "AND (team_gid=%s OR team_gid IS NULL) LIMIT 1",
                (connector_id, user_gid, team_gid),
            )
            return cursor.fetchone() is not None

    def get_health(self, connector_id: str) -> ConnectorHealth | None:
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
                    "WHERE connector_id=%s AND owner_user_gid=%s AND status<>'revoked'",
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
                    "UPDATE workmanship_sim_connector_plans SET status='outcome_unknown',updated_at=NOW(6) "
                    "WHERE connector_id=%s AND status='leased' AND lease_until<=NOW(6)",
                    (connector_id,),
                )
                cursor.execute(
                    "UPDATE workmanship_sim_connector_plans SET status='expired',updated_at=NOW(6) "
                    "WHERE connector_id=%s AND status='queued' AND expires_at<=NOW(6)",
                    (connector_id,),
                )
                cursor.execute(
                    "SELECT plan_id,plan_json FROM workmanship_sim_connector_plans "
                    "WHERE connector_id=%s AND status='queued' AND expires_at>NOW(6) "
                    "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED",
                    (connector_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                cursor.execute(
                    "UPDATE workmanship_sim_connector_plans SET status='leased',lease_id=%s,"
                    "lease_until=DATE_ADD(NOW(6),INTERVAL %s SECOND),attempts=attempts+1,updated_at=NOW(6) "
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
                "(status='leased' AND lease_until>NOW(6) AND expires_at>NOW(6)) OR "
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
                    "AND status='leased' AND lease_id=%s AND lease_until>NOW(6)",
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
                        "AND status='leased' AND lease_id=%s AND lease_until>NOW(6)",
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
                    "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
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
        )

    def create_pairing(self, record: PairingRecord) -> None:
        nonce_hash = hashlib.sha256(
            f"{record.installation_id}:{record.pairing_id}".encode("utf-8")
        ).hexdigest()
        user_code_hash = hashlib.sha256(record.user_code.encode("utf-8")).hexdigest()
        with get_simulation_conn() as conn, conn.cursor() as cursor:
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

    def binding_for_user(self, user_gid: str) -> dict | None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT connector_id,installation_id FROM workmanship_sim_connector_bindings "
                "WHERE owner_user_gid=%s LIMIT 1",
                (user_gid,),
            )
            return cursor.fetchone()

    def save_pairing(self, record: PairingRecord) -> None:
        envelope_json = (
            json.dumps({"ciphertext": record.encrypted_envelope}, separators=(",", ":"))
            if record.encrypted_envelope else None
        )
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairings SET status=%s,resource_version=%s,"
                "approved_user_gid=%s,team_gid=%s,connector_id=%s,credential_envelope_json=%s,"
                "credential_envelope_hash=%s,approved_at=IF(%s='approved',NOW(6),approved_at),"
                "completed_at=IF(%s='completed',NOW(6),completed_at),updated_at=NOW(6) "
                "WHERE pairing_id=%s",
                (
                    record.status, record.resource_version, record.approved_user_gid,
                    record.team_gid, record.connector_id, envelope_json,
                    record.envelope_hash, record.status, record.status, record.pairing_id,
                ),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_not_found")

    def approve_pairing(self, record: PairingRecord, *, expected_version: int) -> None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
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

    def complete_pairing(self, record: PairingRecord, user_gid: str, binding: dict) -> None:
        envelope_json = json.dumps(
            {"ciphertext": record.encrypted_envelope}, separators=(",", ":"),
        )
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_sim_connector_bindings "
                "(connector_id,owner_user_gid,team_gid,installation_id,windows_sid_hash,display_name,"
                "platform,runtime_version,token_hash,capabilities,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,'windows',%s,%s,JSON_ARRAY('ai00.vismockup@1'),'offline')",
                (
                    binding["connector_id"], user_gid, binding.get("team_gid"),
                    binding["installation_id"], binding["windows_sid_hash"],
                    binding["display_name"], binding["runtime_version"], binding["token_hash"],
                ),
            )
            cursor.execute(
                "UPDATE workmanship_sim_connector_pairings SET status='completed',resource_version=%s,"
                "connector_id=%s,credential_envelope_json=%s,credential_envelope_hash=%s,"
                "completed_at=NOW(6),updated_at=NOW(6) "
                "WHERE pairing_id=%s AND status='approved' AND approved_user_gid=%s "
                "AND resource_version=%s",
                (
                    record.resource_version, record.connector_id, envelope_json,
                    record.envelope_hash, record.pairing_id, user_gid,
                    record.resource_version - 1,
                ),
            )
            if cursor.rowcount != 1:
                raise PairingError("pairing_version_conflict")


__all__ = [
    "ConnectorRepositoryError", "ProjectionIntent", "ProjectionLease",
    "SimulationConnectorRepository", "SqlPairingRepository",
]
