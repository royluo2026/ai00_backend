"""Base-owned project access and identity facade for official domains.

The facade keeps Auth SQL in the Base domain while Craft owns project/BOP SQL.
It is an in-process extraction seam; callers must not depend on its storage model.
"""
from __future__ import annotations

from collections.abc import Iterable

from backend.db.connection import get_conn
from backend.utils.gid import next_gid


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values if value})


def get_user_profiles(user_gids: Iterable[str]) -> dict[str, dict]:
    gids = _unique(user_gids)
    if not gids:
        return {}
    placeholders = ",".join(["%s"] * len(gids))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT gid, name, email, avatar_url FROM workmanship_auth_users "
                f"WHERE is_active=1 AND gid IN ({placeholders})",
                gids,
            )
            return {str(row["gid"]): dict(row) for row in cur.fetchall()}


def can_manage_project(user_gid: str, project_gid: str) -> bool:
    """Return the Base-owned membership/grant projection for project management."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM workmanship_auth_project_members "
                "WHERE project_gid=%s AND user_gid=%s LIMIT 1",
                (project_gid, user_gid),
            )
            if cur.fetchone():
                return True
            cur.execute(
                "SELECT 1 FROM workmanship_auth_permission_grants "
                "WHERE grantee_gid=%s AND grant_type='project_admin' AND scope_gid=%s "
                "AND (expires_at IS NULL OR expires_at > NOW()) LIMIT 1",
                (user_gid, project_gid),
            )
            return bool(cur.fetchone())


def list_project_access_entries(project_gid: str, line_gids: Iterable[str] = ()) -> list[dict]:
    """Return Auth-owned member/grant rows; Craft enriches line metadata itself."""
    result: list[dict] = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pm.gid, pm.user_gid, u.name, u.email, u.avatar_url, "
                "pm.role, pm.scope_gid, pm.scope_type, pm.created_at "
                "FROM workmanship_auth_project_members pm "
                "JOIN workmanship_auth_users u ON pm.user_gid=u.gid "
                "WHERE pm.project_gid=%s",
                (project_gid,),
            )
            result.extend(dict(row) for row in cur.fetchall())

            gids = _unique(line_gids)
            if gids:
                placeholders = ",".join(["%s"] * len(gids))
                cur.execute(
                    "SELECT pg.gid, pg.grantee_gid AS user_gid, u.name, u.email, u.avatar_url, "
                    "'section_lead' AS role, pg.scope_gid, 'line' AS scope_type, "
                    "pg.granted_at AS created_at "
                    "FROM workmanship_auth_permission_grants pg "
                    "JOIN workmanship_auth_users u ON pg.grantee_gid=u.gid "
                    f"WHERE pg.grant_type='section_lead' AND pg.scope_gid IN ({placeholders}) "
                    "AND (pg.expires_at IS NULL OR pg.expires_at > NOW())",
                    gids,
                )
                result.extend(dict(row) for row in cur.fetchall())
    return result



def list_user_project_memberships(user_gid: str) -> list[dict]:
    """Return one user's Base-owned project membership projection."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT project_gid, role, scope_gid, scope_type "
                "FROM workmanship_auth_project_members WHERE user_gid=%s",
                (user_gid,),
            )
            return [dict(row) for row in cur.fetchall()]

def list_all_project_memberships() -> list[dict]:
    """Return Auth-owned membership identities for the Craft matrix projection."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pm.gid, pm.project_gid, pm.user_gid, u.name, u.email, u.avatar_url, "
                "pm.role, pm.scope_gid, pm.scope_type, pm.created_at "
                "FROM workmanship_auth_project_members pm "
                "JOIN workmanship_auth_users u ON pm.user_gid=u.gid "
                "ORDER BY u.name, pm.project_gid"
            )
            return [dict(row) for row in cur.fetchall()]


def add_project_member(
    project_gid: str,
    user_gid: str,
    role: str,
    scope_gid: str | None = None,
) -> str:
    member_gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_auth_project_members "
                "(gid, project_gid, user_gid, role, scope_type, scope_gid) "
                "VALUES (%s,%s,%s,%s,'project',%s)",
                (member_gid, project_gid, user_gid, role, scope_gid),
            )
    return member_gid


def remove_project_member(project_gid: str, member_gid: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM workmanship_auth_project_members WHERE gid=%s AND project_gid=%s",
                (member_gid, project_gid),
            )
            return cur.rowcount > 0


def replace_project_manager(project_gid: str, user_gid: str | None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM workmanship_auth_project_members "
                "WHERE project_gid=%s AND role='project_manager'",
                (project_gid,),
            )
            if user_gid:
                cur.execute(
                    "INSERT INTO workmanship_auth_project_members "
                    "(gid, project_gid, user_gid, role, scope_type, scope_gid) "
                    "VALUES (%s,%s,%s,'project_manager','project',NULL)",
                    (str(next_gid()), project_gid, user_gid),
                )


def replace_section_leads(
    project_gid: str,
    line_gids: Iterable[str],
    user_gid: str | None,
    actor_gid: str,
) -> None:
    gids = _unique(line_gids)
    if not gids:
        raise ValueError("line_gids must not be empty")
    placeholders = ",".join(["%s"] * len(gids))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM workmanship_auth_permission_grants "
                f"WHERE grant_type='section_lead' AND scope_gid IN ({placeholders})",
                gids,
            )
            cur.execute(
                f"DELETE FROM workmanship_auth_project_members "
                f"WHERE project_gid=%s AND scope_gid IN ({placeholders})",
                [project_gid] + gids,
            )
            if user_gid:
                values_sql = ",".join(["(%s,%s,'section_lead',%s,%s,'')"] * len(gids))
                params: list[str] = []
                for line_gid in gids:
                    params.extend([str(next_gid()), user_gid, line_gid, actor_gid])
                cur.execute(
                    "INSERT INTO workmanship_auth_permission_grants "
                    "(gid, grantee_gid, grant_type, scope_gid, granted_by, note) "
                    f"VALUES {values_sql}",
                    params,
                )
                cur.execute(
                    "INSERT INTO workmanship_auth_project_members "
                    "(gid, project_gid, user_gid, role, scope_type, scope_gid) "
                    "VALUES (%s,%s,%s,'section_lead','line',%s)",
                    (str(next_gid()), project_gid, user_gid, gids[0]),
                )


__all__ = [
    "add_project_member",
    "can_manage_project",
    "get_user_profiles",
    "list_all_project_memberships",
    "list_project_access_entries",
    "list_user_project_memberships",
    "remove_project_member",
    "replace_project_manager",
    "replace_section_leads",
]
