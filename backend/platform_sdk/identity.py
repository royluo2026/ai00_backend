"""Base-owned identity lookup commands for official domains."""
from __future__ import annotations

from backend.db.connection import get_conn


def get_user_summaries(user_gids) -> dict[str, dict]:
    gids = tuple(sorted({str(gid) for gid in user_gids if gid}))
    if not gids:
        return {}
    rows = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            for offset in range(0, len(gids), 500):
                chunk = gids[offset:offset + 500]
                placeholders = ",".join(["%s"] * len(chunk))
                cur.execute(
                    f"SELECT gid,name,avatar_url,team_id FROM workmanship_auth_users WHERE is_active=TRUE AND gid IN ({placeholders})",
                    chunk,
                )
                rows.extend(cur.fetchall())
    return {str(row["gid"]): dict(row) for row in rows}


def get_active_team_member_gids(team_gid: str) -> tuple[str, ...]:
    team = str(team_gid or "").strip()
    if not team:
        return ()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid FROM workmanship_auth_users WHERE team_id=%s AND is_active=TRUE ORDER BY gid",
                (team,),
            )
            rows = cur.fetchall()
    return tuple(str(row["gid"]) for row in rows)

def resolve_identity_labels(gids: dict[str, str]) -> dict[str, str]:
    """Resolve Base-owned user/team references without exposing tables to domains."""
    user_fields = {field: gid for field, gid in gids.items() if field in {"owner_gid", "created_by"} and gid}
    team_fields = {field: gid for field, gid in gids.items() if field == "team_gid" and gid}
    result: dict[str, str] = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            for field, gid in user_fields.items():
                cur.execute("SELECT name FROM workmanship_auth_users WHERE gid=%s LIMIT 1", (gid,))
                row = cur.fetchone()
                if row:
                    result[field] = row["name"]
            for field, gid in team_fields.items():
                cur.execute("SELECT name FROM workmanship_auth_teams WHERE gid=%s LIMIT 1", (gid,))
                row = cur.fetchone()
                if row:
                    result[field] = row["name"]
    return result


def find_active_user_by_role(role: str, team_gid: str | None = None) -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if team_gid and role != "super_admin":
                cur.execute(
                    "SELECT gid FROM workmanship_auth_users "
                    "WHERE system_role=%s AND team_id=%s AND is_active=TRUE LIMIT 1",
                    (role, team_gid),
                )
            else:
                cur.execute(
                    "SELECT gid FROM workmanship_auth_users "
                    "WHERE system_role=%s AND is_active=TRUE LIMIT 1",
                    (role,),
                )
            row = cur.fetchone()
    return str(row["gid"]) if row else None


__all__ = ["find_active_user_by_role", "get_active_team_member_gids", "get_user_summaries", "resolve_identity_labels"]
