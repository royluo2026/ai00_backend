from __future__ import annotations

import json
import uuid
from collections.abc import Callable

from .connection import get_agent_conn
from backend.capability_v2.provider_contracts import CapabilityBusinessError

SESSIONS_TABLE = "workmanship_app_ai_sessions"
TURNS_TABLE = "workmanship_app_ai_turns"


class SessionRepository:
    def __init__(self, connection_factory: Callable = get_agent_conn, id_factory: Callable[[], str] | None = None):
        self._connection_factory = connection_factory
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))

    def create_session(self, user_gid: str = "") -> str:
        if not user_gid:
            raise ValueError("user_gid is required for a private Agent session")
        gid = self._id_factory()
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {SESSIONS_TABLE} (gid, user_gid) VALUES (%s, %s)",
                (gid, user_gid),
            )
        return gid

    def update_title(self, session_gid: str, title: str) -> None:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE {SESSIONS_TABLE} SET title=%s, updated_at=NOW() WHERE gid=%s",
                (title[:60], session_gid),
            )

    def touch(self, session_gid: str) -> None:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE {SESSIONS_TABLE} SET updated_at=NOW() WHERE gid=%s", (session_gid,))

    def add_turn(self, session_gid: str, role: str, content: str, tool_calls: list | None = None) -> None:
        gid = self._id_factory()
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT COALESCE(MAX(sort_order), 0) AS max_sort_order FROM {TURNS_TABLE} WHERE session_gid=%s",
                (session_gid,),
            )
            row = cur.fetchone() or {}
            max_order = row.get("max_sort_order", 0) if isinstance(row, dict) else row[0]
            cur.execute(
                f"""INSERT INTO {TURNS_TABLE}
                    (gid, session_gid, role, content, tool_calls, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                (gid, session_gid, role, content or "", json.dumps(tool_calls or [], ensure_ascii=False), max_order + 1),
            )

    def get_turns(self, session_gid: str) -> list[dict]:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT role, content, tool_calls FROM {TURNS_TABLE} WHERE session_gid=%s ORDER BY sort_order ASC",
                (session_gid,),
            )
            rows = cur.fetchall()
        result = []
        for row in rows:
            tool_calls = row.get("tool_calls") or []
            if isinstance(tool_calls, str):
                tool_calls = json.loads(tool_calls)
            result.append({"role": row["role"], "content": row["content"], "tool_calls": tool_calls})
        return result

    def list_sessions(self, user_gid: str = "") -> list[dict]:
        if not user_gid:
            raise ValueError("user_gid is required; team-wide Agent session listing is forbidden")
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"""SELECT gid, title, created_at, updated_at FROM {SESSIONS_TABLE}
                    WHERE user_gid=%s ORDER BY updated_at DESC LIMIT 50""",
                (user_gid,),
            )
            rows = cur.fetchall()
        return [
            {
                "gid": row["gid"],
                "title": row["title"],
                "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
            }
            for row in rows
        ]

    def require_owned_session(self, session_gid: str, user_gid: str) -> None:
        """Require exact ownership without relying on the bounded recent-session list."""
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT 1 FROM {SESSIONS_TABLE} WHERE gid=%s AND user_gid=%s",
                (session_gid, user_gid),
            )
            if not cur.fetchone():
                raise CapabilityBusinessError(
                    "resource_not_found", "Agent session was not found",
                    details={"session_gid": session_gid},
                )

    def delete_session(self, session_gid: str) -> None:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM {SESSIONS_TABLE} WHERE gid=%s", (session_gid,))

    def delete_owned_session(self, session_gid: str, user_gid: str) -> bool:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {SESSIONS_TABLE} WHERE gid=%s AND user_gid=%s",
                (session_gid, user_gid),
            )
            return cur.rowcount == 1

    def get_session(self, session_gid: str, user_gid: str) -> list[dict]:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT gid FROM {SESSIONS_TABLE} WHERE gid=%s AND user_gid=%s",
                (session_gid, user_gid),
            )
            if not cur.fetchone():
                raise CapabilityBusinessError(
                    "resource_not_found", "Agent session was not found",
                    details={"session_gid": session_gid},
                )
            cur.execute(
                f"SELECT role, content, tool_calls FROM {TURNS_TABLE} "
                f"WHERE session_gid=%s ORDER BY sort_order ASC LIMIT %s",
                (session_gid, 501),
            )
            rows = cur.fetchall()
        if len(rows) > 500:
            raise CapabilityBusinessError(
                "dataset_too_large", "Agent session history exceeds the bounded response limit",
                details={"limit": 500, "session_gid": session_gid},
            )
        result = []
        for row in rows:
            tool_calls = row.get("tool_calls") or []
            if isinstance(tool_calls, str):
                tool_calls = json.loads(tool_calls)
            result.append({"role": row["role"], "content": row["content"], "tool_calls": tool_calls})
        return result

    def compress_session(self, session_gid: str, summary_text: str, keep_recent: int = 15) -> None:
        if keep_recent < 1:
            raise ValueError("keep_recent must be >= 1")
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT gid, sort_order FROM {TURNS_TABLE} WHERE session_gid=%s ORDER BY sort_order ASC",
                (session_gid,),
            )
            rows = cur.fetchall()
            if len(rows) <= keep_recent:
                return
            delete_ids = [row["gid"] for row in rows[:-keep_recent]]
            placeholders = ",".join(["%s"] * len(delete_ids))
            cur.execute(f"DELETE FROM {TURNS_TABLE} WHERE gid IN ({placeholders})", tuple(delete_ids))
            cur.execute(
                f"""INSERT INTO {TURNS_TABLE}
                    (gid, session_gid, role, content, tool_calls, sort_order)
                    VALUES (%s, %s, 'summary', %s, %s, 0)""",
                (self._id_factory(), session_gid, summary_text, "[]"),
            )
