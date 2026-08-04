from __future__ import annotations

import uuid

from .connection import get_agent_conn

TABLE = "workmanship_app_ai_audit_logs"


class AuditRepository:
    def __init__(self, connection_factory=get_agent_conn, id_factory=None):
        self._connection_factory = connection_factory
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))

    def record(self, event: dict) -> str:
        user_gid = str(event.get("user_gid") or "")
        if not user_gid:
            raise ValueError("user_gid is required for Agent audit events")
        gid = str(event.get("gid") or self._id_factory())
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {TABLE}
                    (gid, session_gid, user_gid, tool_name, is_write, is_confirmed,
                     inputs_json, result_json, resource_gid, resource_type, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE gid=VALUES(gid)""",
                (
                    gid,
                    event.get("session_gid", ""),
                    user_gid,
                    event.get("tool_name", ""),
                    bool(event.get("is_write", False)),
                    bool(event.get("is_confirmed", False)),
                    event.get("inputs_json", "{}"),
                    event.get("result_json", "{}"),
                    event.get("resource_gid", ""),
                    event.get("resource_type", ""),
                    event.get("status", "ok"),
                ),
            )
        return gid

    def list(self, *, session_gid="", user_gid="", tool_name="", is_write="", limit=50, offset=0):
        conditions = ["1=1"]
        params: list = []
        if session_gid:
            conditions.append("session_gid=%s")
            params.append(session_gid)
        if user_gid:
            conditions.append("user_gid=%s")
            params.append(user_gid)
        if tool_name:
            conditions.append("tool_name LIKE %s")
            params.append(f"%{tool_name}%")
        if is_write == "true":
            conditions.append("is_write=1")
        elif is_write == "false":
            conditions.append("is_write=0")
        where = " AND ".join(conditions)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS total FROM {TABLE} WHERE {where}", params)
            total = cur.fetchone()["total"]
            cur.execute(
                f"""SELECT id, gid, session_gid, user_gid, tool_name, is_write, is_confirmed,
                    inputs_json, result_json, resource_gid, resource_type, status, created_at
                    FROM {TABLE} WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s""",
                params + [limit, offset],
            )
            return total, list(cur.fetchall())
