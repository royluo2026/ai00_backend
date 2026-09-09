"""Authoritative BOP edit checks. Ordinary membership never implies edit access."""
from __future__ import annotations

from backend.db.connection import get_conn


def check_bop_edit(*, tenant_gid: str, user_gid: str, active_roles: tuple[str, ...],
                   project_gid: str, line_gid: str | None) -> dict:
    if "super_admin" in active_roles:
        return {"allowed": True, "scope": "global", "reason": "super_admin"}
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT managed FROM workmanship_base_project_manager_heads "
                "WHERE tenant_gid=%s AND project_gid=%s", (tenant_gid, project_gid),
            )
            head = cursor.fetchone()
            if head:
                cursor.execute(
                    "SELECT 1 FROM workmanship_base_project_manager_assignments "
                    "WHERE tenant_gid=%s AND project_gid=%s AND user_gid=%s LIMIT 1",
                    (tenant_gid, project_gid, user_gid),
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM workmanship_auth_project_members "
                    "WHERE project_gid=%s AND user_gid=%s AND role='project_manager' LIMIT 1",
                    (project_gid, user_gid),
                )
            if cursor.fetchone():
                return {"allowed": True, "scope": "project", "reason": "project_manager"}
            if line_gid:
                cursor.execute(
                    "SELECT 1 FROM workmanship_base_line_responsibility_targets "
                    "WHERE tenant_gid=%s AND project_gid=%s AND bop_line_gid=%s "
                    "AND user_gid=%s AND source_count>0 LIMIT 1",
                    (tenant_gid, project_gid, line_gid, user_gid),
                )
                if cursor.fetchone():
                    return {"allowed": True, "scope": "line", "reason": "line_leader"}
    return {"allowed": False, "scope": "none", "reason": "no_responsibility"}


__all__ = ["check_bop_edit"]

