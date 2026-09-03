"""Simulation persistence adapter for AI00 Connector state and plans."""
from __future__ import annotations

import json
import secrets
import uuid

from backend.contracts.connector_execution_plan_v1 import (
    ConnectorExecutionPlanV1,
    ConnectorPlanOutcomeV1,
    canonical_hash,
)

from ..capabilities.connector_contracts import ConnectorHealth
from .connection import get_simulation_conn


class ConnectorRepositoryError(RuntimeError):
    pass


class SimulationConnectorRepository:
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


__all__ = ["ConnectorRepositoryError", "SimulationConnectorRepository"]
