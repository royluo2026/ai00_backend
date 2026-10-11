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


def require_readable_item(gid, context):
    """Prove the Knowledge item is readable before another owner reads its comments."""
    from .application.outcomes import knowledge_outcomes
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    result=knowledge_outcomes.invoke('knowledge.hub.read',{'operation':'items.get','arguments':{'gid':gid}},context)
    if not result:raise CapabilityBusinessError('resource_not_found','The Knowledge item is unavailable.')


def readable_entry_scope(gid, context):
    """Return typed Knowledge-entry scope after the owner's current visibility check."""
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    from .capabilities.knowledge_next import get_knowledge
    if not gid or not context.user_gid or not context.team_gid or 'knowledge.read' not in context.permissions:
        raise CapabilityBusinessError('permission_denied', 'Authenticated Knowledge read access is required.')
    try:
        row = get_knowledge({'gid': str(gid)}, context).data
    except LookupError:
        raise CapabilityBusinessError('resource_not_found', 'The Knowledge entry is unavailable.') from None
    return {key: row.get(key) for key in ('gid', 'source_project_gid', 'share_scope', 'creator_gid')}


__all__ = ["list_knowledge_workbench_items", "require_readable_item", "readable_entry_scope"]

