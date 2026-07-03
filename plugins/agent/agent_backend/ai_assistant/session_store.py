"""
backend/ai_assistant/session_store.py
────────────────────────────────────
PG-backed AI 会话和轮次存储。
表：app.ai_sessions, app.ai_turns
"""
from __future__ import annotations
import json
from backend.db.connection import get_conn
from backend.utils.gid import next_gid


def _ensure_tables():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app.ai_sessions (
                    gid        TEXT PRIMARY KEY,
                    user_gid   TEXT NOT NULL DEFAULT '',
                    title      TEXT NOT NULL DEFAULT '新对话',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_sessions_user
                ON app.ai_sessions(user_gid)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app.ai_turns (
                    gid         TEXT PRIMARY KEY,
                    session_gid TEXT NOT NULL REFERENCES app.ai_sessions(gid) ON DELETE CASCADE,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL DEFAULT '',
                    tool_calls  JSONB NOT NULL DEFAULT '[]',
                    sort_order  DOUBLE PRECISION NOT NULL DEFAULT 0,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_turns_session
                ON app.ai_turns(session_gid, sort_order)
            """)


_tables_ready = False

def _maybe_ensure():
    global _tables_ready
    if not _tables_ready:
        _ensure_tables()
        _tables_ready = True


class SessionStore:
    def create_session(self, user_gid: str = "") -> str:
        _maybe_ensure()
        gid = str(next_gid())
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO app.ai_sessions (gid, user_gid) VALUES (%s, %s)",
                    (gid, user_gid)
                )
        return gid

    def update_title(self, session_gid: str, title: str) -> None:
        _maybe_ensure()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE app.ai_sessions SET title=%s, updated_at=NOW() WHERE gid=%s",
                    (title[:60], session_gid)
                )

    def touch(self, session_gid: str) -> None:
        _maybe_ensure()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE app.ai_sessions SET updated_at=NOW() WHERE gid=%s",
                    (session_gid,)
                )

    def add_turn(
        self, session_gid: str, role: str, content: str,
        tool_calls: list | None = None
    ) -> None:
        _maybe_ensure()
        gid = str(next_gid())
        with get_conn() as conn:
            with conn.cursor() as cur:
                # sort_order = current max + 1
                cur.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) FROM app.ai_turns WHERE session_gid=%s",
                    (session_gid,)
                )
                max_ord = cur.fetchone()["coalesce"] or 0
                cur.execute("""
                    INSERT INTO app.ai_turns
                        (gid, session_gid, role, content, tool_calls, sort_order)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                """, (
                    gid, session_gid, role, content or "",
                    json.dumps(tool_calls or [], ensure_ascii=False),
                    max_ord + 1,
                ))

    def get_turns(self, session_gid: str) -> list[dict]:
        _maybe_ensure()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT role, content, tool_calls
                    FROM app.ai_turns WHERE session_gid=%s
                    ORDER BY sort_order ASC
                """, (session_gid,))
                rows = cur.fetchall()
        return [
            {
                "role":       r["role"],
                "content":    r["content"],
                "tool_calls": r["tool_calls"] or [],
            }
            for r in rows
        ]

    def list_sessions(self, user_gid: str = "") -> list[dict]:
        _maybe_ensure()
        with get_conn() as conn:
            with conn.cursor() as cur:
                if user_gid:
                    cur.execute("""
                        SELECT gid, title, created_at, updated_at
                        FROM app.ai_sessions WHERE user_gid=%s
                        ORDER BY updated_at DESC LIMIT 50
                    """, (user_gid,))
                else:
                    cur.execute("""
                        SELECT gid, title, created_at, updated_at
                        FROM app.ai_sessions
                        ORDER BY updated_at DESC LIMIT 50
                    """)
                rows = cur.fetchall()
        return [
            {
                "gid":        r["gid"],
                "title":      r["title"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
            }
            for r in rows
        ]

    def delete_session(self, session_gid: str) -> None:
        _maybe_ensure()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM app.ai_sessions WHERE gid=%s", (session_gid,))

    def compress_session(self, session_gid: str, summary_text: str, keep_recent: int = 15) -> None:
        """压缩旧轮次：删除旧 turn，插入 summary turn，保留最近 keep_recent 条。"""
        _maybe_ensure()
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 获取所有 turns 排序
                cur.execute("""
                    SELECT gid, sort_order FROM app.ai_turns
                    WHERE session_gid=%s ORDER BY sort_order ASC
                """, (session_gid,))
                all_turns = cur.fetchall()
                if len(all_turns) <= keep_recent:
                    return
                # 删除旧 turns（保留最近 keep_recent 条）
                to_delete = all_turns[:-keep_recent]
                delete_gids = [t["gid"] for t in to_delete]
                if delete_gids:
                    cur.execute(
                        "DELETE FROM app.ai_turns WHERE gid = ANY(%s)",
                        (delete_gids,)
                    )
                # 插入 summary turn at sort_order=0
                summary_gid = str(next_gid())
                cur.execute("""
                    INSERT INTO app.ai_turns (gid, session_gid, role, content, tool_calls, sort_order)
                    VALUES (%s, %s, 'summary', %s, '[]'::jsonb, 0)
                """, (summary_gid, session_gid, summary_text))


_store = SessionStore()
