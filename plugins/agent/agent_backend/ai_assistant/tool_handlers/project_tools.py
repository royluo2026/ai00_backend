"""
backend/ai_assistant/tool_handlers/project_tools.py
─────────────────────────────────────────────────────
项目 / 任务 / 问题 / 审批单 工具处理器
"""
from __future__ import annotations
from typing import Any

from backend.db.connection import get_conn

TOOL_NAMES: set[str] = {
    # 读工具
    "search",
    "list_tasks",
    "get_task",
    "list_task_lists",
    "list_issues",
    "get_issue",
    "list_issue_lists",
    "list_projects",
    "list_approval_orders",
    # 写工具（需确认）
    "create_task",
    "update_task",
    "create_issue",
    "update_issue",
    "create_approval_order",
    # 写工具（免确认）
    "add_task_progress_log",
}


def dispatch(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    user_gid: str = "",
    **_kwargs,
) -> Any:
    if tool_name == "search":
        return _search(**inputs)
    if tool_name == "list_tasks":
        return _list_tasks(**inputs)
    if tool_name == "get_task":
        return _get_task(inputs.get("gid", ""))
    if tool_name == "get_issue":
        return _get_issue(inputs.get("gid", ""))
    if tool_name == "list_task_lists":
        return _list_task_lists()
    if tool_name == "list_issue_lists":
        return _list_issue_lists()
    if tool_name == "list_issues":
        return _list_issues(**inputs)
    if tool_name == "list_projects":
        return _list_projects()
    if tool_name == "list_approval_orders":
        return _list_approval_orders(**inputs)
    if tool_name == "create_task":
        return _create_task(user_gid=user_gid, **inputs)
    if tool_name == "update_task":
        return _update_task(**inputs)
    if tool_name == "create_issue":
        return _create_issue(user_gid=user_gid, **inputs)
    if tool_name == "update_issue":
        return _update_issue(**inputs)
    if tool_name == "create_approval_order":
        return _create_approval_order(user_gid=user_gid, **inputs)
    if tool_name == "add_task_progress_log":
        return _add_task_progress_log(user_gid=user_gid, **inputs)
    return {"error": f"project_tools: 未知工具 {tool_name}"}


# ── 读工具 ─────────────────────────────────────────────────────────────────────

def _search(keyword: str = "", modules: str = "", limit: int = 5) -> dict:
    results = {}
    mods = [m.strip() for m in modules.split(",")] if modules else ["task", "issue", "knowledge", "bop"]
    limit = min(int(limit or 5), 20)

    if "task" in mods:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT gid, title, status, priority FROM proj.tasks
                    WHERE is_deleted=FALSE AND title ILIKE %s LIMIT %s
                """, (f"%{keyword}%", limit))
                results["tasks"] = [dict(r) for r in cur.fetchall()]

    if "issue" in mods:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT gid, title, status, severity FROM proj.issues
                    WHERE is_deleted=FALSE AND title ILIKE %s LIMIT %s
                """, (f"%{keyword}%", limit))
                results["issues"] = [dict(r) for r in cur.fetchall()]

    if "knowledge" in mods:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT gid, title, tags FROM knowledge.knowledge_entries
                    WHERE title ILIKE %s LIMIT %s
                """, (f"%{keyword}%", limit))
                results["knowledge"] = [dict(r) for r in cur.fetchall()]

    if "bop" in mods:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 先搜 bop_versions（按 bop_name/version_tag）
                cur.execute("""
                    SELECT gid, bop_name, version_tag, status, project_gid
                    FROM bop.bop_versions
                    WHERE (bop_name ILIKE %s OR version_tag ILIKE %s)
                      AND status != 'archived'
                    ORDER BY created_at DESC LIMIT %s
                """, (f"%{keyword}%", f"%{keyword}%", limit))
                versions = [dict(r) for r in cur.fetchall()]
                # 再搜 bop_entries（按 title/vpps）
                cur.execute("""
                    SELECT e.gid, e.title, e.node_type, e.vpps,
                           v.bop_name, v.version_tag
                    FROM bop.bop_entries e
                    JOIN bop.bop_versions v ON v.gid = e.bop_version_gid
                    WHERE (e.title ILIKE %s OR e.vpps ILIKE %s)
                      AND e.is_deleted = FALSE AND v.status != 'archived'
                    ORDER BY e.created_at DESC LIMIT %s
                """, (f"%{keyword}%", f"%{keyword}%", limit))
                entries = [dict(r) for r in cur.fetchall()]
                results["bop_versions"] = versions
                results["bop_entries"]  = entries

    total = sum(len(v) for v in results.values())
    text_lines = [f"搜索「{keyword}」找到 {total} 条结果："]
    for mod, items in results.items():
        if items:
            text_lines.append(f"\n{mod}（{len(items)} 条）：")
            for it in items:
                text_lines.append(f"  - {it.get('title', '')} [{it.get('gid', '')}]")
    return {"text": "\n".join(text_lines), "data": results}


def _list_tasks(
    keyword: str = "", list_gid: str = "", status: str = "",
    priority: str = "", limit: int = 20,
) -> dict:
    conditions = ["is_deleted=FALSE"]
    params: list = []
    if keyword:
        conditions.append("title ILIKE %s"); params.append(f"%{keyword}%")
    if list_gid:
        conditions.append("list_gid=%s"); params.append(list_gid)
    if status:
        conditions.append("status=%s"); params.append(status)
    if priority:
        conditions.append("priority=%s"); params.append(priority)
    where = " AND ".join(conditions)
    limit = min(int(limit or 20), 100)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT gid, title, status, priority, due_date FROM proj.tasks "
                f"WHERE {where} ORDER BY created_at DESC LIMIT %s",
                params + [limit],
            )
            rows = cur.fetchall()
    items = [dict(r) for r in rows]
    text = f"任务列表（{len(items)} 条）：\n" + "\n".join(
        f"  [{r.get('status', '')}] {r.get('title', '')} [{r.get('gid', '')}]"
        for r in items
    )
    return {"text": text, "items": items}


def _get_task(gid: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM proj.tasks WHERE gid=%s AND is_deleted=FALSE", (gid,)
            )
            row = cur.fetchone()
    if not row:
        return {"error": f"任务不存在：{gid}"}
    return {"text": f"任务详情：{row['title']}", "data": dict(row)}


def _get_issue(gid: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM proj.issues WHERE gid=%s AND is_deleted=FALSE", (gid,)
            )
            row = cur.fetchone()
    if not row:
        return {"error": f"问题不存在：{gid}"}
    return {"text": f"问题详情：{row['title']}", "data": dict(row)}


def _list_task_lists() -> dict:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid, name FROM app.lists WHERE item_type='task' "
                    "ORDER BY created_at ASC LIMIT 50"
                )
                rows = cur.fetchall()
        items = [dict(r) for r in rows]
        return {
            "text":  f"任务清单（{len(items)} 个）：" + ", ".join(r["name"] for r in items),
            "items": items,
        }
    except Exception as e:
        return {"error": str(e)}


def _list_issue_lists() -> dict:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid, name FROM app.lists WHERE item_type='issue' "
                    "ORDER BY created_at ASC LIMIT 50"
                )
                rows = cur.fetchall()
        items = [dict(r) for r in rows]
        return {
            "text":  f"问题清单（{len(items)} 个）：" + ", ".join(r["name"] for r in items),
            "items": items,
        }
    except Exception as e:
        return {"error": str(e)}


def _list_issues(
    keyword: str = "", list_gid: str = "", status: str = "",
    severity: str = "", limit: int = 20,
) -> dict:
    conditions = ["is_deleted=FALSE"]
    params: list = []
    if keyword:
        conditions.append("title ILIKE %s"); params.append(f"%{keyword}%")
    if list_gid:
        conditions.append("list_gid=%s"); params.append(list_gid)
    if status:
        conditions.append("status=%s"); params.append(status)
    if severity:
        conditions.append("severity=%s"); params.append(severity)
    where = " AND ".join(conditions)
    limit = min(int(limit or 20), 100)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT gid, title, status, severity FROM proj.issues "
                f"WHERE {where} ORDER BY created_at DESC LIMIT %s",
                params + [limit],
            )
            rows = cur.fetchall()
    items = [dict(r) for r in rows]
    text = f"问题列表（{len(items)} 条）：\n" + "\n".join(
        f"  [{r.get('status', '')}][{r.get('severity', '')}] {r.get('title', '')} [{r.get('gid', '')}]"
        for r in items
    )
    return {"text": text, "items": items}


def _list_projects() -> dict:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid, name, status FROM proj.projects "
                    "ORDER BY created_at DESC LIMIT 30"
                )
                rows = cur.fetchall()
        items = [dict(r) for r in rows]
        text = f"项目列表（{len(items)} 个）：\n" + "\n".join(
            f"  {r['name']} [{r['gid']}]" for r in items
        )
        return {"text": text, "items": items}
    except Exception as e:
        return {"error": str(e)}


def _list_approval_orders(status: str = "", limit: int = 20) -> dict:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                q = "SELECT gid, title, status, created_at FROM app.approval_orders"
                params: list = []
                if status:
                    q += " WHERE status=%s"; params.append(status)
                q += f" ORDER BY created_at DESC LIMIT {min(int(limit or 20), 100)}"
                cur.execute(q, params)
                rows = cur.fetchall()
        items = [dict(r) for r in rows]
        text = f"审批单（{len(items)} 条）：\n" + "\n".join(
            f"  [{r.get('status', '')}] {r.get('title', '')} [{r.get('gid', '')}]"
            for r in items
        )
        return {"text": text, "items": items}
    except Exception as e:
        return {"error": str(e)}


# ── 写工具 ─────────────────────────────────────────────────────────────────────

def _create_task(
    title: str, priority: str = "normal", description: str = "",
    due_date: str = None, list_gid: str = None, user_gid: str = "",
) -> dict:
    from backend.utils.gid import next_gid
    gid = str(next_gid())
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO proj.tasks
                        (gid, title, status, priority, description, due_date, list_gid, owner_gid)
                    VALUES (%s, %s, 'pending', %s, %s, %s, %s, %s)
                    RETURNING gid, title
                """, (gid, title, priority, description or "", due_date, list_gid, user_gid))
                row = cur.fetchone()
        return {
            "text":  f"已创建任务：{row['title']} [{row['gid']}]",
            "gid":   row["gid"],
            "title": row["title"],
        }
    except Exception as e:
        return {"error": str(e)}


def _update_task(gid: str, **kwargs) -> dict:
    allowed = {"status", "title", "priority", "description", "due_date", "plan_start", "plan_end"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return {"error": "没有可更新的字段"}
    try:
        set_clause = ", ".join(f"{k}=%s" for k in updates)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE proj.tasks SET {set_clause}, updated_at=NOW() "
                    f"WHERE gid=%s RETURNING gid, title",
                    list(updates.values()) + [gid],
                )
                row = cur.fetchone()
        if not row:
            return {"error": f"任务不存在：{gid}"}
        return {"text": f"已更新任务：{row['title']} [{row['gid']}]", "gid": row["gid"]}
    except Exception as e:
        return {"error": str(e)}


def _create_issue(
    title: str, severity: str = "medium", description: str = "",
    list_gid: str = None, user_gid: str = "",
) -> dict:
    from backend.utils.gid import next_gid
    gid = str(next_gid())
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO proj.issues
                        (gid, title, status, severity, description, list_gid, owner_gid)
                    VALUES (%s, %s, 'open', %s, %s, %s, %s)
                    RETURNING gid, title
                """, (gid, title, severity, description or "", list_gid, user_gid))
                row = cur.fetchone()
        return {
            "text":  f"已创建问题：{row['title']} [{row['gid']}]",
            "gid":   row["gid"],
            "title": row["title"],
        }
    except Exception as e:
        return {"error": str(e)}


def _update_issue(gid: str, **kwargs) -> dict:
    allowed = {"status", "title", "severity", "description"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return {"error": "没有可更新的字段"}
    try:
        set_clause = ", ".join(f"{k}=%s" for k in updates)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE proj.issues SET {set_clause}, updated_at=NOW() "
                    f"WHERE gid=%s RETURNING gid, title",
                    list(updates.values()) + [gid],
                )
                row = cur.fetchone()
        if not row:
            return {"error": f"问题不存在：{gid}"}
        return {"text": f"已更新问题：{row['title']} [{row['gid']}]", "gid": row["gid"]}
    except Exception as e:
        return {"error": str(e)}


def _create_approval_order(
    title: str, description: str = "", approver_gid: str = None, user_gid: str = "",
) -> dict:
    from backend.utils.gid import next_gid
    gid = str(next_gid())
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO app.approval_orders
                        (gid, title, description, status, created_by)
                    VALUES (%s, %s, %s, 'pending', %s)
                    RETURNING gid, title
                """, (gid, title, description or "", user_gid))
                row = cur.fetchone()
        return {"text": f"已创建审批单：{row['title']} [{row['gid']}]", "gid": row["gid"]}
    except Exception as e:
        return {"error": str(e)}


def _add_task_progress_log(gid: str, content: str, user_gid: str = "") -> dict:
    from backend.utils.gid import next_gid
    entry_gid = str(next_gid())
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO item_entries
                        (gid, id, item_type, item_gid, section, author, author_gid, content)
                    VALUES (%s, %s, 'task', %s, 'progress', 'ai', %s, %s)
                """, (entry_gid, entry_gid, gid, user_gid, content))
        return {"text": f"已记录进度：{content[:50]}"}
    except Exception as e:
        return {"error": str(e)}
