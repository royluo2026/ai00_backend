"""Simulation-owned persistence for selective BOP publication sagas."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from backend.platform_sdk.ids import next_gid

from .connection import get_simulation_conn


class PublishRepositoryError(RuntimeError):
    pass


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class PublishRepository:
    def create_plan(
        self, *, workspace_gid: str, environment_version_gid: str, tenant_gid: str,
        owner_gid: str, base_bop_version_gid: str, base_bop_revision: int,
        plan: Mapping[str, Any], idempotency_key: str,
    ) -> dict[str, Any]:
        publish_plan_gid = str(next_gid())
        payload = _json(dict(plan))
        selection_hash = hashlib.sha256(_json(plan.get("selected_node_gids", [])).encode()).hexdigest()
        plan_hash = str(plan["plan_hash"])
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT gid,plan_hash,status FROM workmanship_sim_environment_publish_plans "
                "WHERE workspace_gid=%s AND idempotency_key=%s FOR UPDATE",
                (workspace_gid, idempotency_key),
            )
            replay = cursor.fetchone()
            if replay:
                if replay["plan_hash"] != plan_hash:
                    raise PublishRepositoryError("idempotency_conflict")
                return {"publish_plan_gid": str(replay["gid"]), "plan_hash": plan_hash, "status": replay["status"]}
            cursor.execute(
                "INSERT INTO workmanship_sim_environment_publish_plans "
                "(gid,workspace_gid,environment_version_gid,tenant_gid,owner_gid,base_bop_version_gid,"
                "base_bop_revision,selection_hash,plan_hash,plan_json,idempotency_key,status,row_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'prepared',1)",
                (publish_plan_gid, workspace_gid, environment_version_gid, tenant_gid, owner_gid,
                 base_bop_version_gid, base_bop_revision, selection_hash, plan_hash, payload, idempotency_key),
            )
        return {"publish_plan_gid": publish_plan_gid, "plan_hash": plan_hash, "status": "prepared"}

    def claim_dispatch(self, *, publish_plan_gid: str, tenant_gid: str, owner_gid: str,
                       expected_row_version: int, craft_action_ref: Mapping[str, Any]) -> dict[str, Any]:
        outbox_gid = str(next_gid())
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_environment_publish_plans SET status='dispatching',row_version=row_version+1,"
                "craft_action_ref_json=%s,updated_at=NOW(6) WHERE gid=%s AND tenant_gid=%s AND owner_gid=%s "
                "AND status='prepared' AND row_version=%s",
                (_json(craft_action_ref), publish_plan_gid, tenant_gid, owner_gid, expected_row_version),
            )
            if cursor.rowcount != 1:
                raise PublishRepositoryError("publish_plan_conflict")
            cursor.execute(
                "INSERT INTO workmanship_sim_environment_publish_outbox "
                "(gid,publish_plan_gid,tenant_gid,owner_gid,effect_type,payload_json,status,attempt) "
                "VALUES (%s,%s,%s,%s,'craft_dispatch',%s,'pending',0)",
                (outbox_gid, publish_plan_gid, tenant_gid, owner_gid, _json(craft_action_ref)),
            )
        return {"publish_plan_gid": publish_plan_gid, "outbox_gid": outbox_gid, "status": "dispatching"}

    def record_craft_outcome(
        self, *, publish_plan_gid: str, tenant_gid: str, owner_gid: str,
        craft_bop_version_gid: str, craft_bop_revision: int,
        mappings: list[Mapping[str, Any]], outcome_hash: str,
    ) -> dict[str, Any]:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT status,outcome_hash FROM workmanship_sim_environment_publish_plans "
                "WHERE gid=%s AND tenant_gid=%s AND owner_gid=%s FOR UPDATE",
                (publish_plan_gid, tenant_gid, owner_gid),
            )
            row = cursor.fetchone()
            if not row:
                raise PublishRepositoryError("publish_plan_not_found")
            if row["status"] == "completed":
                if row["outcome_hash"] != outcome_hash:
                    raise PublishRepositoryError("outcome_conflict")
                return {"publish_plan_gid": publish_plan_gid, "status": "completed"}
            if row["status"] not in {"dispatching", "outcome_unknown"}:
                raise PublishRepositoryError("publish_plan_conflict")
            for item in mappings:
                cursor.execute(
                    "INSERT INTO workmanship_sim_environment_publish_maps "
                    "(gid,publish_plan_gid,environment_node_gid,craft_node_gid,client_ref,tenant_gid,owner_gid) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE craft_node_gid=VALUES(craft_node_gid)",
                    (str(next_gid()), publish_plan_gid, item["environment_node_gid"], item["craft_node_gid"],
                     item["client_ref"], tenant_gid, owner_gid),
                )
            cursor.execute(
                "UPDATE workmanship_sim_environment_publish_plans SET status='completed',craft_bop_version_gid=%s,"
                "craft_bop_revision=%s,outcome_hash=%s,row_version=row_version+1,updated_at=NOW(6) WHERE gid=%s",
                (craft_bop_version_gid, craft_bop_revision, outcome_hash, publish_plan_gid),
            )
            cursor.execute(
                "UPDATE workmanship_sim_environment_publish_outbox SET status='completed',updated_at=NOW(6) "
                "WHERE publish_plan_gid=%s AND status IN ('pending','leased','outcome_unknown')",
                (publish_plan_gid,),
            )
        return {"publish_plan_gid": publish_plan_gid, "status": "completed"}

    def mark_outcome_unknown(self, *, publish_plan_gid: str, reason: str) -> None:
        with get_simulation_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_sim_environment_publish_plans SET status='outcome_unknown',"
                "last_error=%s,row_version=row_version+1,updated_at=NOW(6) "
                "WHERE gid=%s AND status='dispatching'", (reason[:1000], publish_plan_gid),
            )
            cursor.execute(
                "UPDATE workmanship_sim_environment_publish_outbox SET status='outcome_unknown',last_error=%s,"
                "updated_at=NOW(6) WHERE publish_plan_gid=%s AND status IN ('pending','leased')",
                (reason[:1000], publish_plan_gid),
            )


__all__ = ["PublishRepository", "PublishRepositoryError"]
