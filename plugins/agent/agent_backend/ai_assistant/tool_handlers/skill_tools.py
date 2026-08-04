"""
backend/ai_assistant/tool_handlers/skill_tools.py
──────────────────────────────────────────────────
Skill / AI 画布 工具处理器
"""
from __future__ import annotations
from typing import Any

from ...data.connection import get_agent_conn

TOOL_NAMES: set[str] = {
    "run_skill_canvas",
    "list_skills",
}

# skill_tool_<name> 前缀由本模块兜底处理，不在 TOOL_NAMES 中声明
# （__init__.py 中用 startswith 路由过来）


def dispatch(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    user_gid: str = "",
    **_kwargs,
) -> Any:
    if tool_name == "run_skill_canvas":
        return _run_skill_canvas(user_gid=user_gid, auth_token=auth_token, **inputs)
    if tool_name == "list_skills":
        return _list_skills(user_gid=user_gid, **inputs)
    if tool_name.startswith("skill_tool_"):
        skill_name = tool_name[len("skill_tool_"):]
        return _run_skill_by_name(
            skill_name=skill_name,
            user_gid=user_gid,
            user_inputs=inputs.get("user_inputs", {}),
            auth_token=auth_token,
        )
    return {"error": f"skill_tools: 未知工具 {tool_name}"}


# ── 实现 ───────────────────────────────────────────────────────────────────────

def _run_skill_canvas(
    skill_gid: str = "",
    user_inputs: dict = None,
    pause_token: str = None,
    resume_inputs: dict = None,
    user_gid: str = "",
    auth_token: str = "",
) -> dict:
    """简化版 skill 执行：返回 skill 画布结构，由前端 wfc_window.js 处理。"""
    try:
        with get_agent_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid, title, content FROM workmanship_app_skills "
                    "WHERE gid=%s AND deleted_at IS NULL AND (owner_gid=%s OR owner_gid='__system__' OR scope='global')",
                    (skill_gid, user_gid),
                )
                row = cur.fetchone()
        if not row:
            return {"error": f"Skill 不存在：{skill_gid}"}
        content = row["content"] or {}
        canvas  = content.get("canvas", {}) if isinstance(content, dict) else {}
        return {
            "text":        f"Skill「{row['title']}」画布已加载",
            "status":      "canvas_generated",
            "canvas":      canvas,
            "skill_title": row["title"],
        }
    except Exception as e:
        return {"error": str(e)}


def _list_skills(scope_filter: str = "all", limit: int = 30, user_gid: str = "") -> dict:
    try:
        with get_agent_conn() as conn:
            with conn.cursor() as cur:
                q = "SELECT gid, name, title, description FROM workmanship_app_skills WHERE deleted_at IS NULL AND (owner_gid=%s OR owner_gid='__system__' OR scope='global')"
                params: list = [user_gid]
                if scope_filter and scope_filter != "all":
                    q += " AND scope=%s"; params.append(scope_filter)
                q += f" ORDER BY created_at DESC LIMIT {min(int(limit or 30), 100)}"
                cur.execute(q, params)
                rows = cur.fetchall()
        items = [dict(r) for r in rows]
        text = f"Skill 列表（{len(items)} 个）：\n" + "\n".join(
            f"  {r.get('title') or r.get('name', '')} [{r['gid']}]" for r in items
        )
        return {"text": text, "items": items}
    except Exception as e:
        return {"error": str(e)}


def _run_skill_by_name(
    skill_name: str,
    user_gid: str = "",
    user_inputs: dict = None,
    auth_token: str = "",
) -> dict:
    try:
        with get_agent_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid, title FROM workmanship_app_skills "
                    "WHERE name=%s AND deleted_at IS NULL AND (owner_gid=%s OR owner_gid='__system__' OR scope='global')",
                    (skill_name, user_gid),
                )
                row = cur.fetchone()
        if not row:
            return {"error": f"Skill 不存在：{skill_name}"}
        return _run_skill_canvas(
            skill_gid=row["gid"],
            user_inputs=user_inputs,
            user_gid=user_gid,
            auth_token=auth_token,
        )
    except Exception as e:
        return {"error": str(e)}
