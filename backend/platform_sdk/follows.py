"""Base-owned personal follow projections for official domains."""
from __future__ import annotations

from backend.db.connection import get_conn


def list_recent_follows(user_gid: str, limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(int(limit), 100))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,item_type,item_gid,item_title,notify_on "
                "FROM workmanship_work_follows WHERE user_gid=%s "
                f"ORDER BY created_at DESC LIMIT {safe_limit}",
                (user_gid,),
            )
            return [dict(row) for row in cur.fetchall()]


__all__ = ["list_recent_follows"]
