"""Source-scoped, reference-counted manual-line responsibility projection."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.db.connection import get_conn
from backend.utils.gid import next_gid

from .project_responsibility import ProjectManagerError


def apply_projection(payload: dict[str, Any], *, tenant_gid: str, actor_gid: str) -> dict[str, Any]:
    user_gids = sorted({str(value).strip() for value in payload["user_gids"] if str(value).strip()})
    if len(user_gids) > 50:
        raise ProjectManagerError("invalid_input", "线体负责人最多 50 人")
    canonical = {**payload, "user_gids": user_gids}
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_digest,result_json FROM workmanship_base_line_projection_operations "
                "WHERE tenant_gid=%s AND operation_gid=%s FOR UPDATE",
                (tenant_gid, payload["operation_gid"]),
            )
            replay = cursor.fetchone()
            if replay:
                if str(replay["command_digest"]) != digest:
                    raise ProjectManagerError("idempotency_conflict", "投影操作内容不一致")
                return json.loads(replay["result_json"])
            cursor.execute(
                "SELECT source_revision FROM workmanship_base_line_responsibility_sources "
                "WHERE tenant_gid=%s AND source_gid=%s FOR UPDATE",
                (tenant_gid, payload["source_gid"]),
            )
            source = cursor.fetchone()
            if source and int(source["source_revision"]) >= int(payload["source_revision"]):
                raise ProjectManagerError("version_conflict", "投影来源修订号未递增")
            cursor.execute(
                "SELECT target_gid FROM workmanship_base_line_responsibility_source_targets "
                "WHERE tenant_gid=%s AND source_gid=%s FOR UPDATE",
                (tenant_gid, payload["source_gid"]),
            )
            old_targets = [str(row["target_gid"]) for row in cursor.fetchall()]
            cursor.execute(
                "DELETE FROM workmanship_base_line_responsibility_source_targets "
                "WHERE tenant_gid=%s AND source_gid=%s", (tenant_gid, payload["source_gid"]),
            )
            for target_gid in old_targets:
                cursor.execute(
                    "UPDATE workmanship_base_line_responsibility_targets SET source_count=source_count-1 "
                    "WHERE gid=%s AND source_count>0", (target_gid,),
                )
                cursor.execute(
                    "DELETE FROM workmanship_base_line_responsibility_targets WHERE gid=%s AND source_count=0",
                    (target_gid,),
                )
            bop_line_gid = payload.get("bop_line_gid") or None
            if source:
                cursor.execute(
                    "UPDATE workmanship_base_line_responsibility_sources SET source_revision=%s,project_gid=%s," 
                    "bop_line_gid=%s,updated_at=NOW() WHERE tenant_gid=%s AND source_gid=%s",
                    (payload["source_revision"], payload["project_gid"], bop_line_gid,
                     tenant_gid, payload["source_gid"]),
                )
            else:
                cursor.execute(
                    "INSERT INTO workmanship_base_line_responsibility_sources "
                    "(gid,tenant_gid,source_gid,source_revision,project_gid,bop_line_gid) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (str(next_gid()), tenant_gid, payload["source_gid"], payload["source_revision"],
                     payload["project_gid"], bop_line_gid),
                )
            if bop_line_gid:
                for user_gid in user_gids:
                    cursor.execute(
                        "SELECT gid FROM workmanship_base_line_responsibility_targets "
                        "WHERE tenant_gid=%s AND project_gid=%s AND bop_line_gid=%s AND user_gid=%s FOR UPDATE",
                        (tenant_gid, payload["project_gid"], bop_line_gid, user_gid),
                    )
                    target = cursor.fetchone()
                    target_gid = str(target["gid"]) if target else str(next_gid())
                    if target:
                        cursor.execute(
                            "UPDATE workmanship_base_line_responsibility_targets SET source_count=source_count+1 WHERE gid=%s",
                            (target_gid,),
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO workmanship_base_line_responsibility_targets "
                            "(gid,tenant_gid,project_gid,bop_line_gid,user_gid,source_count) VALUES (%s,%s,%s,%s,%s,1)",
                            (target_gid, tenant_gid, payload["project_gid"], bop_line_gid, user_gid),
                        )
                    cursor.execute(
                        "INSERT INTO workmanship_base_line_responsibility_source_targets "
                        "(tenant_gid,source_gid,target_gid) VALUES (%s,%s,%s)",
                        (tenant_gid, payload["source_gid"], target_gid),
                    )
            result = {"operation_gid": payload["operation_gid"],
                      "source_revision": payload["source_revision"], "status": "completed"}
            cursor.execute(
                "INSERT INTO workmanship_base_line_projection_operations "
                "(gid,tenant_gid,operation_gid,source_gid,command_digest,result_json,actor_gid) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (str(next_gid()), tenant_gid, payload["operation_gid"], payload["source_gid"],
                 digest, json.dumps(result, ensure_ascii=False), actor_gid),
            )
            return result


def get_projection(operation_gid: str, *, tenant_gid: str) -> dict[str, Any] | None:
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT result_json FROM workmanship_base_line_projection_operations "
                "WHERE tenant_gid=%s AND operation_gid=%s", (tenant_gid, operation_gid),
            )
            row = cursor.fetchone()
            return json.loads(row["result_json"]) if row else None


__all__ = ["apply_projection", "get_projection"]

