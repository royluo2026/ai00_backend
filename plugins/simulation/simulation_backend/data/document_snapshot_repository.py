"""Persistence for confirmed Connector document snapshots."""
from __future__ import annotations

import json

from backend.capability_v2.provider_contracts import CapabilityContext

from ..application.capture_worker import SimulationWorkflowError
from .connection import get_simulation_conn


def _project(row):
    value = dict(row)
    raw = value.pop("snapshot_json", None)
    value["snapshot"] = json.loads(raw) if isinstance(raw, str) else raw
    value["failure_code"] = value.get("failure_code") or ""
    value["operation_ref"] = {
        "operation_id": value["plan_id"],
        "status": {
            "queued": "accepted", "completed": "completed", "failed": "failed",
            "outcome_unknown": "outcome_unknown",
        }[value["status"]],
        "version": 1,
    }
    return value


class DocumentSnapshotRepository:
    def can_read_request(self, request_id: str, *, user_gid: str, team_gid: str) -> bool:
        if not request_id or not user_gid or not team_gid:
            return False
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM workmanship_sim_document_snapshot_requests "
                "WHERE snapshot_request_id=%s AND (owner_gid=%s OR team_gid=%s) LIMIT 1",
                (request_id, user_gid, team_gid),
            )
            return cursor.fetchone() is not None

    def create_request(self, row, context: CapabilityContext):
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT snapshot_request_id,request_key,device_id,plan_id,status,snapshot_json,"
                "failure_code,owner_gid,team_gid FROM workmanship_sim_document_snapshot_requests "
                "WHERE owner_gid=%s AND team_gid<=>%s AND request_key=%s FOR UPDATE",
                (context.user_gid, context.team_gid, row["request_key"]),
            )
            current = cursor.fetchone()
            if current:
                if current["device_id"] != row["device_id"]:
                    raise SimulationWorkflowError("idempotency_conflict")
                return _project(current)
            cursor.execute(
                "INSERT INTO workmanship_sim_document_snapshot_requests "
                "(snapshot_request_id,request_key,device_id,plan_id,status,owner_gid,team_gid) "
                "VALUES (%s,%s,%s,%s,'queued',%s,%s)",
                (row["snapshot_request_id"], row["request_key"], row["device_id"], row["plan_id"],
                 context.user_gid, context.team_gid),
            )
        return dict(row)

    def get_request(self, request_id: str, context: CapabilityContext):
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT snapshot_request_id,request_key,device_id,plan_id,status,snapshot_json,"
                "failure_code,owner_gid,team_gid FROM workmanship_sim_document_snapshot_requests "
                "WHERE snapshot_request_id=%s AND (owner_gid=%s OR (%s IS NOT NULL AND team_gid=%s))",
                (request_id, context.user_gid, context.team_gid, context.team_gid),
            )
            row = cursor.fetchone()
        return _project(row) if row else None

    def complete_request(self, request_id: str, *, snapshot=None, status="completed", failure_code=""):
        encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if snapshot else None
        digest = snapshot.get("snapshot_hash") if snapshot else None
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT status,snapshot_hash FROM workmanship_sim_document_snapshot_requests "
                "WHERE snapshot_request_id=%s FOR UPDATE", (request_id,),
            )
            current = cursor.fetchone()
            if not current:
                raise SimulationWorkflowError("document_snapshot_not_found")
            if current["status"] == "completed":
                if current["snapshot_hash"] != digest:
                    raise SimulationWorkflowError("idempotency_conflict")
                return
            cursor.execute(
                "UPDATE workmanship_sim_document_snapshot_requests SET status=%s,snapshot_hash=%s,"
                "snapshot_json=%s,failure_code=%s,updated_at=NOW(6) WHERE snapshot_request_id=%s",
                (status, digest, encoded, failure_code or None, request_id),
            )


repository = DocumentSnapshotRepository()

__all__ = ["DocumentSnapshotRepository", "repository"]
