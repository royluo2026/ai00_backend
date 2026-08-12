"""Stable read projections for host composition; implemented with Knowledge credentials."""
from __future__ import annotations

from .data.connection import get_knowledge_conn


def list_knowledge_workbench_items(user_gid: str, list_gids: list[str] | None = None) -> list[dict]:
    clauses = ["maintainer_gid=%s", "status!='archived'"]
    params: list = [user_gid]
    if list_gids:
        clauses.append(f"list_gid IN ({','.join(['%s'] * len(list_gids))})")
        params.extend(list_gids)
    with get_knowledge_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 'knowledge' AS item_type,gid,title,status,NULL AS priority,scheduled_date,NULL AS due_date,created_at,NULL AS project_name,maintainer_gid AS owner_user_gid FROM workmanship_know_entries "
                f"WHERE {' AND '.join(clauses)} ORDER BY COALESCE(scheduled_date,'9999-12-31') ASC LIMIT 200",
                params,
            )
            return [dict(row) for row in cur.fetchall()]


__all__ = ["list_knowledge_workbench_items"]

