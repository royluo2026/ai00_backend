"""Authoritative BOP edit checks. Ordinary membership never implies edit access."""
from __future__ import annotations

from backend.db.connection import get_conn


def get_bop_edit_scope(*, tenant_gid: str, user_gid: str, active_roles: tuple[str, ...],
                       project_gid: str, line_gids: tuple[str, ...] = ()) -> dict:
    """Resolve project-wide or line-scoped BOP edit access in one bounded query set.

    ``tenant_gid`` stays in the compatibility signature, but single-tenant mode
    deliberately scopes collaboration by project and actor instead.
    """
    if "super_admin" in active_roles:
        return {"project_wide": True, "editable_line_gids": (), "reason": "super_admin"}
    requested = tuple(dict.fromkeys(str(value) for value in line_gids if value))
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT managed FROM workmanship_base_project_manager_heads "
                "WHERE project_gid=%s LIMIT 1", (project_gid,),
            )
            head = cursor.fetchone()
            if head:
                cursor.execute(
                    "SELECT 1 FROM workmanship_base_project_manager_assignments "
                    "WHERE project_gid=%s AND user_gid=%s LIMIT 1",
                    (project_gid, user_gid),
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM workmanship_auth_project_members "
                    "WHERE project_gid=%s AND user_gid=%s AND role='project_manager' LIMIT 1",
                    (project_gid, user_gid),
                )
            if cursor.fetchone():
                return {"project_wide": True, "editable_line_gids": (), "reason": "project_manager"}
            if not requested:
                return {"project_wide": False, "editable_line_gids": (), "reason": "no_responsibility"}
            placeholders = ",".join(["%s"] * len(requested))
            cursor.execute(
                "SELECT bop_line_gid FROM workmanship_base_line_responsibility_targets "
                "WHERE project_gid=%s AND user_gid=%s AND source_count>0 "
                f"AND bop_line_gid IN ({placeholders})",
                (project_gid, user_gid, *requested),
            )
            editable = tuple(sorted(str(row["bop_line_gid"]) for row in cursor.fetchall()))
    return {
        "project_wide": False,
        "editable_line_gids": editable,
        "reason": "line_leader" if editable else "no_responsibility",
    }


def check_bop_edit(*, tenant_gid: str, user_gid: str, active_roles: tuple[str, ...],
                   project_gid: str, line_gid: str | None) -> dict:
    resolved = get_bop_edit_scope(
        tenant_gid=tenant_gid, user_gid=user_gid, active_roles=active_roles,
        project_gid=project_gid, line_gids=(line_gid,) if line_gid else (),
    )
    if resolved["project_wide"]:
        scope = "global" if resolved["reason"] == "super_admin" else "project"
        return {"allowed": True, "scope": scope, "reason": resolved["reason"]}
    if line_gid and line_gid in resolved["editable_line_gids"]:
        return {"allowed": True, "scope": "line", "reason": "line_leader"}
    return {"allowed": False, "scope": "none", "reason": "no_responsibility"}


__all__ = ["check_bop_edit", "get_bop_edit_scope"]

