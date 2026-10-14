"""Craft-owned BOP projections used by Project composition routes."""
from __future__ import annotations

from ..data.connection import get_conn


def line_titles_for_project(project_gid: str) -> dict[str, str]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT e.gid,e.title FROM workmanship_bop_bop_entries e JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid WHERE v.project_gid=%s AND v.archived_at IS NULL AND e.node_type='line_process' AND e.is_deleted=FALSE", (project_gid,))
            return {row["gid"]: row["title"] or "" for row in cur.fetchall()}


def line_titles(line_gids: list[str]) -> dict[str, str]:
    if not line_gids: return {}
    placeholders = ",".join(["%s"] * len(line_gids))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT gid,title FROM workmanship_bop_bop_entries WHERE gid IN ({placeholders})", line_gids)
            return {row["gid"]: row["title"] for row in cur.fetchall()}


def project_bop_lines(project_gid: str) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid,title,sort_order FROM workmanship_bop_bop_entries WHERE version_gid IN (SELECT gid FROM workmanship_bop_bop_versions WHERE project_gid=%s AND archived_at IS NULL) AND node_type='line_process' AND is_deleted=FALSE ORDER BY sort_order,title", (project_gid,))
            rows = cur.fetchall()
    by_title = {}
    for row in rows:
        title = row["title"] or ""
        by_title.setdefault(title, {"gid": row["gid"], "title": title or "（未命名线体）", "seq_no": row["sort_order"], "all_gids": []})["all_gids"].append(row["gid"])
    return list(by_title.values())


def equivalent_line_gids(project_gid: str, line_gid: str) -> list[str]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT title FROM workmanship_bop_bop_entries WHERE gid=%s AND node_type='line_process' AND is_deleted=FALSE", (line_gid,))
            row = cur.fetchone()
            if not row: return []
            cur.execute("SELECT e.gid FROM workmanship_bop_bop_entries e JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid WHERE v.project_gid=%s AND v.archived_at IS NULL AND e.node_type='line_process' AND e.is_deleted=FALSE AND e.title=%s", (project_gid, row["title"]))
            return [item["gid"] for item in cur.fetchall()]


def entry_project_gid(entry_gid, context):
    """Resolve a live entry for a currently responsible project manager."""
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    from backend.platform_sdk.project_access import can_edit_project_bop
    if not entry_gid or not context.user_gid or not context.team_gid or 'craft.read' not in context.permissions:
        raise CapabilityBusinessError('permission_denied', 'Authenticated Craft read access is required.')
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute('SELECT v.project_gid FROM workmanship_bop_bop_entries e '
                    'JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid '
                    'WHERE e.gid=%s AND e.is_deleted=FALSE AND v.archived_at IS NULL', (str(entry_gid),))
        row = cur.fetchone()
    project = str((row or {}).get('project_gid') or '')
    if not project or not can_edit_project_bop(context.user_gid, project, None, ()):
        raise CapabilityBusinessError('permission_denied', 'The Craft entry is unavailable in the managed project scope.')
    return project


def line_ancestor_gids(project_gid: str, line_gids: list[str]) -> dict[str, list[str]]:
    """Trace actual version-copy provenance, scoped to one project and BOP family."""
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    gids = list(dict.fromkeys(line_gids))
    if len(gids) > 5000:
        raise CapabilityBusinessError("graph_limit_exceeded", "Too many BOP lines")
    by_gid = {}
    frontier = gids
    with get_conn() as conn, conn.cursor() as cur:
        for _ in range(32):
            if not frontier:
                break
            placeholders = ','.join(['%s'] * len(frontier))
            cur.execute(
                "SELECT e.gid,e.source_entry_gid,COALESCE(NULLIF(v.version_family_gid,''),v.gid) AS family_gid "
                "FROM workmanship_bop_bop_entries e JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid "
                "WHERE v.project_gid=%s AND e.node_type='line_process' "
                f"AND e.gid IN ({placeholders})", (project_gid, *frontier))
            rows = [dict(row) for row in cur.fetchall()]
            by_gid.update({str(row['gid']): row for row in rows})
            frontier = list({str(row['source_entry_gid']) for row in rows
                             if row.get('source_entry_gid') and str(row['source_entry_gid']) not in by_gid})
            if len(by_gid) > 5000:
                raise CapabilityBusinessError("graph_limit_exceeded", "BOP provenance exceeds 5000 nodes")
        else:
            if frontier:
                raise CapabilityBusinessError("graph_limit_exceeded", "BOP provenance exceeds depth 32")
    result = {}
    for gid in gids:
        ancestors, seen = [], {gid}
        row = by_gid.get(gid)
        family = row.get('family_gid') if row else None
        while row and row.get('source_entry_gid'):
            parent = str(row['source_entry_gid'])
            if parent in seen:
                raise CapabilityBusinessError("graph_limit_exceeded", "Cyclic BOP provenance")
            seen.add(parent)
            row = by_gid.get(parent)
            if not row or row.get('family_gid') != family:
                break
            ancestors.append(parent)
        result[gid] = ancestors
    return result


__all__ = ["equivalent_line_gids", "line_titles", "line_titles_for_project", "project_bop_lines", "entry_project_gid", "line_ancestor_gids"]
