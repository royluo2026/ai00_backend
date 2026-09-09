"""Minimal active-principal projection used by responsibility editors."""
from __future__ import annotations

from backend.db.connection import get_conn


def get_active_principal(user_gid: str) -> dict | None:
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT gid,name,avatar_url,is_active FROM workmanship_auth_users "
                "WHERE gid=%s AND is_active=1", (user_gid,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {"gid": str(row["gid"]), "name": str(row.get("name") or ""),
                    "avatar_url": str(row.get("avatar_url") or ""), "is_active": True}


__all__ = ["get_active_principal"]

