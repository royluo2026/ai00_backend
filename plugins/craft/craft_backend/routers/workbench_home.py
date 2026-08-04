"""
backend/routers/workbench_home.py
──────────────────────────────────
工作台首页聚合接口

GET /api/workbench/home    → 一次返回所有面板数据
GET /api/workbench/panel1  → 面板1多来源数据（tasks/issues/bop/knowledge/rule）
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..data.connection import get_conn
from backend.platform_sdk.auth import get_current_user
from backend.platform_sdk.follows import list_recent_follows
from backend.platform_sdk.knowledge import list_knowledge_workbench_items
from backend.platform_sdk.project_access import list_user_project_memberships

router = APIRouter(tags=["workbench"])


def _isoify(rows: list) -> list:
    """将 rows 中所有 date/datetime 对象序列化为 ISO 字符串。"""
    for item in rows:
        for k, v in item.items():
            if hasattr(v, "isoformat"):
                item[k] = v.isoformat()
    return rows


import logging as _logging
_log = _logging.getLogger(__name__)


@router.get("/api/workbench/home")
async def get_workbench_home(current_user=Depends(get_current_user)):
    uid = current_user["gid"]
    tasks: list = []
    issues: list = []
    contexts: list = []
    follows: list = []

    # 每个查询独立连接+try/except，任意一个缺列不影响其他面板
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 'task' AS item_type, t.gid, t.title, t.status, t.priority,
                           t.due_date, t.scheduled_date, t.created_at,
                           p.name AS project_name,
                           (t.attachments IS NOT NULL
                            AND JSON_LENGTH(t.attachments) > 0) AS has_links
                    FROM workmanship_proj_tasks t
                    LEFT JOIN workmanship_proj_projects p ON p.gid = t.project_gid
                    WHERE t.owner_user_gid = %s
                      AND t.is_deleted = FALSE
                      AND t.deleted_at IS NULL
                      AND t.status NOT IN ('done', 'completed', 'cancelled')
                    ORDER BY COALESCE(t.due_date, t.scheduled_date, '9999-12-31') ASC
                    LIMIT 30
                """, (uid,))
                tasks = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        _log.error("workbench/home tasks query failed: %s", e)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 'issue' AS item_type, i.gid, i.title, i.status, i.severity,
                           NULL AS priority, NULL AS due_date,
                           NULL AS scheduled_date, i.created_at,
                           p.name AS project_name,
                           (i.attachments IS NOT NULL
                            AND JSON_LENGTH(i.attachments) > 0) AS has_links
                    FROM workmanship_proj_issues i
                    LEFT JOIN workmanship_proj_projects p ON p.gid = i.project_gid
                    WHERE i.owner_user_gid = %s
                      AND i.status NOT IN ('closed', 'resolved')
                    ORDER BY i.created_at DESC
                    LIMIT 20
                """, (uid,))
                issues = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        _log.error("workbench/home issues query failed: %s", e)

    try:
        memberships = list_user_project_memberships(uid)
        project_gids = sorted({row["project_gid"] for row in memberships if row.get("project_gid")})
        project_names = {}
        if project_gids:
            placeholders = ",".join(["%s"] * len(project_gids))
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT gid, name FROM workmanship_proj_projects "
                        f"WHERE is_deleted=FALSE AND gid IN ({placeholders})",
                        project_gids,
                    )
                    project_names = {row["gid"]: row["name"] for row in cur.fetchall()}
        contexts = [
            {
                "project_gid": row["project_gid"],
                "project_name": project_names[row["project_gid"]],
                "role": row["role"],
                "scope_gid": row.get("scope_gid"),
            }
            for row in memberships if row.get("project_gid") in project_names
        ]
        contexts.sort(key=lambda row: row["project_name"])
    except Exception as e:
        _log.error("workbench/home contexts query failed: %s", e)

    try:
        follows = list_recent_follows(uid, limit=20)
    except Exception as e:
        _log.error("workbench/home follows query failed: %s", e)

    today_items = sorted(
        tasks + issues,
        key=lambda x: str(x.get("due_date") or "9999-12-31")
    )
    _isoify(today_items)
    _isoify(contexts)

    return {
        "today_items":    today_items,
        "my_contexts":    contexts,
        "alerts":         [],
        "recent_follows": follows,
    }


@router.get("/api/workbench/panel1")
async def get_panel1_items(
    sources: str = Query("task,issue", description="逗号分隔的来源：task,issue,bop,knowledge,rule"),
    task_lists:       Optional[str] = Query(None, description="逗号分隔的 task list_gid，空=全部"),
    issue_lists:      Optional[str] = Query(None, description="逗号分隔的 issue list_gid，空=全部"),
    knowledge_lists:  Optional[str] = Query(None, description="逗号分隔的 knowledge list_gid，空=全部"),
    rule_lists:       Optional[str] = Query(None, description="逗号分隔的 rule list_gid，空=全部"),
    bop_version_gids: Optional[str] = Query(None, description="逗号分隔的 bop_version gid，空=全部"),
    pbom_version_gids: Optional[str] = Query(None, description="逗号分隔的 pbom_version gid，空=全部"),
    current_user=Depends(get_current_user),
):
    """
    面板1多来源数据接口。
    负责人字段（assignee）各表对应：
      task        → owner_user_gid
      issue       → owner_user_gid
      bop_entries → assignee_user_gid  (需执行 ALTER TABLE)
      knowledge   → maintainer_gid
      rule        → owner_user_gid     (需执行 ALTER TABLE)
    """
    uid = current_user["gid"]
    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    def _parse_gids(s: Optional[str]) -> list:
        if not s: return []
        return [g.strip() for g in s.split(",") if g.strip()]

    items: list = []

    with get_conn() as conn:
        with conn.cursor() as cur:

            if "task" in source_list:
                tl = _parse_gids(task_lists)
                if tl:
                    _tph = ",".join(["%s"] * len(tl))
                    list_clause = f" AND t.list_gid IN ({_tph})"
                    list_params = tl
                else:
                    list_clause = ""
                    list_params = []
                cur.execute(f"""
                    SELECT 'task'          AS item_type,
                           t.gid, t.title, t.status, t.priority,
                           t.scheduled_date, t.due_date, t.created_at,
                           t.scheduled_start_time, t.time_estimate,
                           p.name               AS project_name,
                           t.owner_user_gid,
                           t.list_gid
                    FROM workmanship_proj_tasks t
                    LEFT JOIN workmanship_proj_projects p ON p.gid = t.project_gid
                    WHERE t.owner_user_gid = %s
                      AND t.is_deleted = FALSE
                      AND t.deleted_at IS NULL
                      AND t.status NOT IN ('done', 'completed', 'cancelled')
                      {list_clause}
                    ORDER BY COALESCE(t.scheduled_date, t.due_date,
                                      '9999-12-31') ASC
                    LIMIT 200
                """, [uid] + list_params)
                items.extend(dict(r) for r in cur.fetchall())

            if "issue" in source_list:
                il = _parse_gids(issue_lists)
                if il:
                    _iph = ",".join(["%s"] * len(il))
                    list_clause = f" AND i.list_gid IN ({_iph})"
                    list_params = il
                else:
                    list_clause = ""
                    list_params = []
                try:
                    cur.execute(f"""
                        SELECT 'issue'      AS item_type,
                               i.gid, i.title, i.status,
                               NULL         AS priority,
                               i.scheduled_date, NULL AS due_date, i.created_at,
                               p.name             AS project_name,
                               i.owner_user_gid,
                               i.list_gid
                        FROM workmanship_proj_issues i
                        LEFT JOIN workmanship_proj_projects p ON p.gid = i.project_gid
                        WHERE i.owner_user_gid = %s
                          AND i.status NOT IN ('closed', 'resolved')
                          {list_clause}
                        ORDER BY COALESCE(i.scheduled_date, '9999-12-31') ASC
                        LIMIT 200
                    """, [uid] + list_params)
                    items.extend(dict(r) for r in cur.fetchall())
                except Exception:
                    conn.rollback()
                    cur.execute(f"""
                        SELECT 'issue'      AS item_type,
                               i.gid, i.title, i.status,
                               NULL         AS priority,
                               NULL         AS scheduled_date,
                               NULL         AS due_date, i.created_at,
                               p.name             AS project_name,
                               i.owner_user_gid,
                               i.list_gid
                        FROM workmanship_proj_issues i
                        LEFT JOIN workmanship_proj_projects p ON p.gid = i.project_gid
                        WHERE i.owner_user_gid = %s
                          AND i.status NOT IN ('closed', 'resolved')
                          {list_clause}
                        ORDER BY i.created_at DESC
                        LIMIT 200
                    """, [uid] + list_params)
                    items.extend(dict(r) for r in cur.fetchall())

            if "bop" in source_list:
                bvl = _parse_gids(bop_version_gids)
                pvl = _parse_gids(pbom_version_gids)

                # 构建版本过滤子句
                version_clause = ""
                version_params: list = []
                if bvl and not pvl:
                    _bph = ",".join(["%s"] * len(bvl))
                    version_clause = f" AND e.bop_version_gid IN ({_bph})"
                    version_params = bvl
                elif pvl and not bvl:
                    _pph = ",".join(["%s"] * len(pvl))
                    version_clause = f"""
                        AND e.bop_version_gid IN (
                            SELECT bv.gid FROM workmanship_bop_bop_versions bv
                            WHERE bv.project_gid IN (
                                SELECT pv.project_gid FROM workmanship_bop_pbom_versions pv
                                WHERE pv.gid IN ({_pph}) AND pv.project_gid IS NOT NULL
                            )
                        )"""
                    version_params = pvl
                elif bvl and pvl:
                    _bph = ",".join(["%s"] * len(bvl))
                    _pph = ",".join(["%s"] * len(pvl))
                    version_clause = f"""
                        AND (
                            e.bop_version_gid IN ({_bph})
                            OR e.bop_version_gid IN (
                                SELECT bv.gid FROM workmanship_bop_bop_versions bv
                                WHERE bv.project_gid IN (
                                    SELECT pv.project_gid FROM workmanship_bop_pbom_versions pv
                                    WHERE pv.gid IN ({_pph}) AND pv.project_gid IS NOT NULL
                                )
                            )
                        )"""
                    version_params = bvl + pvl

                try:
                    cur.execute(f"""
                        SELECT 'bop'        AS item_type,
                               e.gid, e.title,
                               'active'     AS status,
                               NULL         AS priority,
                               e.scheduled_date, NULL AS due_date, e.created_at,
                               v.bop_name         AS project_name,
                               e.assignee_user_gid AS owner_user_gid
                        FROM workmanship_bop_bop_entries e
                        JOIN workmanship_bop_bop_versions v ON v.gid = e.bop_version_gid
                        WHERE e.assignee_user_gid = %s
                          AND e.deleted_at IS NULL
                          {version_clause}
                        ORDER BY COALESCE(e.scheduled_date, '9999-12-31') ASC
                        LIMIT 200
                    """, [uid] + version_params)
                    items.extend(dict(r) for r in cur.fetchall())
                except Exception:
                    conn.rollback()

            if "knowledge" in source_list:
                try:
                    items.extend(
                        list_knowledge_workbench_items(uid, _parse_gids(knowledge_lists))
                    )
                except Exception:
                    _log.exception("Knowledge workbench query failed")

            if "rule" in source_list:
                try:
                    from plugins.craft.craft_backend.public import list_rule_workbench_items
                    items.extend(list_rule_workbench_items(uid, _parse_gids(rule_lists)))
                except Exception:
                    _log.exception("Craft rule workbench query failed")

    _isoify(items)
    return {"items": items, "total": len(items)}
