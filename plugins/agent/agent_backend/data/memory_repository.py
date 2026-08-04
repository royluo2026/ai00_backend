from __future__ import annotations

import uuid

from .connection import get_agent_conn

TABLE = "workmanship_app_ai_memory"


class MemoryRepository:
    def __init__(self, connection_factory=get_agent_conn, id_factory=None):
        self._connection_factory = connection_factory
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))

    @staticmethod
    def _require_user(user_gid: str) -> None:
        if not user_gid:
            raise ValueError("user_gid is required for private Agent memory")

    def save(self, user_gid: str, key: str, content: str, tag: str, overwrite: bool) -> None:
        self._require_user(user_gid)
        if overwrite:
            sql = f"""INSERT INTO {TABLE}
                (gid, user_gid, memory_key, content, tag, scope, confidence)
                VALUES (%s, %s, %s, %s, %s, 'user', 1.0)
                ON DUPLICATE KEY UPDATE content=VALUES(content), tag=VALUES(tag), updated_at=NOW()"""
        else:
            sql = f"""INSERT IGNORE INTO {TABLE}
                (gid, user_gid, memory_key, content, tag, scope, confidence)
                VALUES (%s, %s, %s, %s, %s, 'user', 1.0)"""
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(sql, (self._id_factory(), user_gid, key, content, tag))

    def search(self, user_gid: str, query: str, tag: str = "", limit: int = 10) -> list[dict]:
        self._require_user(user_gid)
        conditions = ["user_gid=%s", "(memory_key LIKE %s OR content LIKE %s)"]
        params: list = [user_gid, f"%{query}%", f"%{query}%"]
        if tag:
            conditions.append("tag=%s")
            params.append(tag)
        params.append(min(max(limit, 1), 50))
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"""SELECT gid, memory_key, content, tag, confidence, updated_at FROM {TABLE}
                    WHERE {' AND '.join(conditions)} ORDER BY updated_at DESC LIMIT %s""",
                params,
            )
            return list(cur.fetchall())

    def list_for_user(self, user_gid: str, limit: int = 100) -> list[dict]:
        self._require_user(user_gid)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"""SELECT gid, memory_key, content, tag, confidence, updated_at FROM {TABLE}
                    WHERE user_gid=%s ORDER BY tag, updated_at DESC LIMIT %s""",
                (user_gid, min(max(limit, 1), 200)),
            )
            return list(cur.fetchall())
