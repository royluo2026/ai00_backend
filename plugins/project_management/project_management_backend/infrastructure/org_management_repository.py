"""Project-owned persistence for revisioned manual responsibility lines."""
from __future__ import annotations

import json
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.utils.gid import next_gid

from ..data.connection import get_project_management_conn
from ..domain.models import OrgManagementError, apply_line_change, decode_org_management


class OrgManagementRepository:
    def project(self, project_gid: str, tenant_gid: str | None = None) -> dict[str, Any] | None:
        with get_project_management_conn() as connection:
            with connection.cursor() as cursor:
                sql = "SELECT gid,name,team_id,is_deleted,meta FROM workmanship_proj_projects WHERE gid=%s"
                params: tuple[Any, ...] = (project_gid,)
                if tenant_gid:
                    sql += " AND team_id=%s"
                    params += (tenant_gid,)
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return dict(row) if row else None

    def search(self, tenant_gid: str | None, cursor_gid: str | None, page_size: int) -> tuple[list[dict[str, Any]], str | None]:
        with get_project_management_conn() as connection:
            with connection.cursor() as cursor:
                sql = (
                    "SELECT gid,name,meta FROM workmanship_proj_projects "
                    "WHERE is_deleted=0 AND is_archived=0 AND gid>%s"
                )
                params: list[Any] = [cursor_gid or ""]
                if tenant_gid is not None:
                    sql += " AND team_id=%s"
                    params.append(tenant_gid)
                sql += " ORDER BY gid LIMIT %s"
                params.append(page_size + 1)
                cursor.execute(sql, tuple(params))
                rows = [dict(row) for row in cursor.fetchall()]
        more = len(rows) > page_size
        rows = rows[:page_size]
        items = []
        for row in rows:
            state = decode_org_management(row.get("meta"))
            items.append({"gid": str(row["gid"]), "name": str(row.get("name") or ""), **state})
        return items, str(rows[-1]["gid"]) if more and rows else None

    def operation(self, operation_gid: str, tenant_gid: str) -> dict[str, Any] | None:
        with get_project_management_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT gid AS operation_gid,project_gid,revision,status,error_code "
                    "FROM workmanship_proj_org_management_operations WHERE gid=%s AND tenant_gid=%s",
                    (operation_gid, tenant_gid),
                )
                row = cursor.fetchone()
                return dict(row) if row else None

    def pending_projection(self, operation_gid: str, tenant_gid: str) -> dict[str, Any] | None:
        with get_project_management_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT payload_json FROM workmanship_proj_org_management_outbox "
                    "WHERE operation_gid=%s AND tenant_gid=%s AND status='pending' FOR UPDATE",
                    (operation_gid, tenant_gid),
                )
                row = cursor.fetchone()
                return json.loads(row["payload_json"]) if row else None

    def complete_projection(self, operation_gid: str, tenant_gid: str) -> None:
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE workmanship_proj_org_management_outbox SET status='completed',updated_at=NOW() "
                        "WHERE operation_gid=%s AND tenant_gid=%s", (operation_gid, tenant_gid),
                    )
                    cursor.execute(
                        "UPDATE workmanship_proj_org_management_operations SET status='completed',"
                        "result_json=JSON_SET(result_json,'$.status','completed'),updated_at=NOW() "
                        "WHERE gid=%s AND tenant_gid=%s", (operation_gid, tenant_gid),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def fail_projection(self, operation_gid: str, tenant_gid: str, message: str) -> None:
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE workmanship_proj_org_management_outbox SET attempts=attempts+1,last_error=%s,"
                        "available_at=DATE_ADD(NOW(),INTERVAL 30 SECOND),updated_at=NOW() "
                        "WHERE operation_gid=%s AND tenant_gid=%s", (message[:1024], operation_gid, tenant_gid),
                    )
                    cursor.execute(
                        "UPDATE workmanship_proj_org_management_operations SET status='failed_retryable',"
                        "error_code='projection_failed',result_json=JSON_SET(result_json,'$.status','failed_retryable'),updated_at=NOW() "
                        "WHERE gid=%s AND tenant_gid=%s", (operation_gid, tenant_gid),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def apply(self, *, tenant_gid: str, actor_gid: str, project_gid: str, operation: str,
              arguments: dict[str, Any], expected_revision: int, idempotency_key: str,
              command_digest: str) -> dict[str, Any]:
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT command_digest,result_json FROM workmanship_proj_org_management_operations "
                        "WHERE tenant_gid=%s AND actor_gid=%s AND idempotency_key=%s FOR UPDATE",
                        (tenant_gid, actor_gid, idempotency_key),
                    )
                    replay = cursor.fetchone()
                    if replay:
                        if str(replay["command_digest"]) != command_digest:
                            raise CapabilityBusinessError("idempotency_conflict", "幂等键已用于不同请求")
                        return json.loads(replay["result_json"])
                    cursor.execute(
                        "SELECT gid,meta FROM workmanship_proj_projects "
                        "WHERE gid=%s AND (team_id=%s OR team_id IS NULL OR team_id='') "
                        "AND is_deleted=0 FOR UPDATE",
                        (project_gid, tenant_gid),
                    )
                    project = cursor.fetchone()
                    if not project:
                        raise CapabilityBusinessError("resource_not_found", "项目不存在")
                    meta, line = apply_line_change(
                        project.get("meta"), operation=operation, arguments=arguments,
                        expected_revision=expected_revision, new_gid=lambda: str(next_gid()),
                    )
                    revision = expected_revision + 1
                    operation_gid = str(next_gid())
                    projection_line = line
                    if operation == "managed_line.delete" and line:
                        # Deletion removes this source's effective grants while
                        # keeping the stable source GID for ref-count cleanup.
                        projection_line = {**line, "bop_line_gid": None, "leader_user_gids": []}
                    needs_projection = bool(line and (
                        operation == "managed_line.delete" or line.get("bop_line_gid") or line.get("leader_user_gids")
                    ))
                    status = "pending_projection" if needs_projection else "completed"
                    result = {"operation_gid": operation_gid, "revision": revision, "status": status}
                    cursor.execute("UPDATE workmanship_proj_projects SET meta=%s,updated_at=NOW() WHERE gid=%s",
                                   (json.dumps(meta, ensure_ascii=False), project_gid))
                    cursor.execute(
                        "INSERT INTO workmanship_proj_org_management_operations "
                        "(gid,tenant_gid,actor_gid,project_gid,revision,operation,idempotency_key,command_digest,status,result_json) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (operation_gid, tenant_gid, actor_gid, project_gid, revision, operation,
                         idempotency_key, command_digest, status, json.dumps(result, ensure_ascii=False)),
                    )
                    if needs_projection:
                        cursor.execute(
                            "INSERT INTO workmanship_proj_org_management_outbox "
                            "(gid,operation_gid,tenant_gid,project_gid,payload_json,status) "
                            "VALUES (%s,%s,%s,%s,%s,'pending')",
                            (str(next_gid()), operation_gid, tenant_gid, project_gid,
                             json.dumps({"line": projection_line, "revision": revision, "operation": operation}, ensure_ascii=False)),
                        )
                connection.commit()
                return result
            except OrgManagementError as exc:
                connection.rollback()
                raise CapabilityBusinessError(exc.code, str(exc)) from exc
            except Exception:
                connection.rollback()
                raise


__all__ = ["OrgManagementRepository"]
