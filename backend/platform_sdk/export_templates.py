"""Base-owned export-template storage facade."""
from __future__ import annotations

import json

from backend.db.connection import get_conn
from backend.utils.gid import next_gid


def list_export_templates(user_gid: str, module: str = "") -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if module:
                cur.execute(
                    "SELECT gid,name,module,owner_gid,is_shared,config,created_at,updated_at "
                    "FROM workmanship_app_export_templates "
                    "WHERE (owner_gid=%s OR is_shared=TRUE) AND (module=%s OR module='*') "
                    "ORDER BY created_at",
                    (user_gid, module),
                )
            else:
                cur.execute(
                    "SELECT gid,name,module,owner_gid,is_shared,config,created_at,updated_at "
                    "FROM workmanship_app_export_templates "
                    "WHERE owner_gid=%s OR is_shared=TRUE ORDER BY module,created_at",
                    (user_gid,),
                )
            return [dict(row) for row in cur.fetchall()]


def create_export_template(
    user_gid: str, name: str, module: str, config: dict, is_shared: bool
) -> str:
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_app_export_templates "
                "(gid,name,module,owner_gid,is_shared,config) VALUES (%s,%s,%s,%s,%s,%s)",
                (gid, name, module, user_gid, is_shared, json.dumps(config)),
            )
    return gid


def update_export_template(gid: str, user_gid: str, is_admin: bool, updates: dict) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT owner_gid FROM workmanship_app_export_templates WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise LookupError("模板不存在")
            if str(row["owner_gid"]) != user_gid and not is_admin:
                raise PermissionError("无权修改此模板")
            set_parts = []
            params = []
            for field in ("name", "module", "is_shared"):
                if field in updates and updates[field] is not None:
                    set_parts.append(f"{field}=%s")
                    params.append(updates[field])
            if updates.get("config") is not None:
                set_parts.append("config=%s")
                params.append(json.dumps(updates["config"]))
            if not set_parts:
                return
            set_parts.append("updated_at=NOW()")
            params.append(gid)
            cur.execute(
                f"UPDATE workmanship_app_export_templates SET {','.join(set_parts)} WHERE gid=%s",
                params,
            )


def delete_export_template(gid: str, user_gid: str, is_admin: bool) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT owner_gid FROM workmanship_app_export_templates WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row:
                raise LookupError("模板不存在")
            if str(row["owner_gid"]) != user_gid and not is_admin:
                raise PermissionError("无权删除此模板")
            cur.execute("DELETE FROM workmanship_app_export_templates WHERE gid=%s", (gid,))


__all__ = [
    "create_export_template",
    "delete_export_template",
    "list_export_templates",
    "update_export_template",
]
