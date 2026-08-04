"""Public Base-owned access-scope projection for official product domains."""
from __future__ import annotations

from backend.db.connection import get_conn


def build_access_scope(user: dict) -> dict:
    """Resolve identity relations without exposing Auth SQL to another domain."""
    user_gid = str(user.get("gid") or "")
    team_gid = str(user.get("team_id") or "")
    role = str(user.get("org_role") or user.get("system_role") or "external")
    team_gids: list[str] = [team_gid] if team_gid else []
    member_gids: list[str] = [user_gid] if user_gid else []
    project_gids: list[str] = []

    with get_conn() as conn:
        with conn.cursor() as cur:
            if team_gid:
                cur.execute("SELECT parent_team_gid FROM workmanship_auth_teams WHERE gid=%s", (team_gid,))
                row = cur.fetchone()
                parent_gid = str((row or {}).get("parent_team_gid") or "")
                if parent_gid and parent_gid not in team_gids:
                    team_gids.append(parent_gid)
                placeholders = ",".join(["%s"] * len(team_gids))
                cur.execute(
                    f"SELECT gid FROM workmanship_auth_users WHERE is_active=1 AND team_id IN ({placeholders})",
                    team_gids,
                )
                member_gids = sorted({str(row["gid"]) for row in cur.fetchall()} | set(member_gids))
            if user_gid:
                cur.execute(
                    "SELECT project_gid FROM workmanship_auth_project_members WHERE user_gid=%s",
                    (user_gid,),
                )
                project_gids = sorted({str(row["project_gid"]) for row in cur.fetchall()})

    return {
        "user_gid": user_gid,
        "team_gids": team_gids,
        "team_member_gids": member_gids,
        "project_gids": project_gids,
        "is_admin": role in {"super_admin", "team_admin"},
    }


__all__ = ["build_access_scope"]
