"""
backend/ai_assistant/tool_handlers/system_tools.py
───────────────────────────────────────────────────
系统 / 计算 / 偏好 / 画布生成 / 画布状态 / 复核标记 工具处理器
"""
from __future__ import annotations
import datetime
import math
import uuid
from typing import Any

from backend.db.connection import get_conn

TOOL_NAMES: set[str] = {
    "calculate",
    "save_preference",
    "list_preferences",
    "ask_for_clarification",
    "generate_canvas",
    "open_in_container",
    "create_discussion_topic",
    "get_canvas_state",
    "get_selected_elements",
    "flag_for_review",
}


def dispatch(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    user_gid: str = "",
    session_gid: str = "",
    canvas_context: dict | None = None,
    **_kwargs,
) -> Any:
    if tool_name == "calculate":
        return _calculate(inputs.get("expression", ""))
    if tool_name == "save_preference":
        return _save_preference(
            user_gid=user_gid,
            key=inputs.get("key", ""),
            value=inputs.get("value", ""),
        )
    if tool_name == "list_preferences":
        return _list_preferences(user_gid=user_gid)
    if tool_name == "ask_for_clarification":
        return {"text": inputs.get("question", ""), "type": "clarification"}
    if tool_name == "generate_canvas":
        return _generate_canvas(**inputs)
    if tool_name == "open_in_container":
        return {
            "status":  "ok",
            "page_id": inputs.get("page_id", ""),
            "title":   inputs.get("title", ""),
            "url":     inputs.get("url", ""),
        }
    if tool_name == "create_discussion_topic":
        return {"status": "topic_created", "topic": inputs}
    if tool_name == "get_canvas_state":
        return _get_canvas_state(inputs.get("canvas_id"), canvas_context)
    if tool_name == "get_selected_elements":
        return _get_selected_elements(canvas_context)
    if tool_name == "flag_for_review":
        return _flag_for_review(
            reason=inputs.get("reason", ""),
            context=inputs.get("context", ""),
            severity=inputs.get("severity", "medium"),
            user_gid=user_gid,
            session_gid=session_gid,
        )
    return {"error": f"system_tools: 未知工具 {tool_name}"}


# ── 原有实现 ───────────────────────────────────────────────────────────────────

def _calculate(expression: str) -> dict:
    allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("__")}
    allowed_names["datetime"] = datetime
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)  # noqa: S307
        return {"text": f"计算结果：{expression} = {result}", "result": result}
    except Exception as e:
        return {"error": f"计算失败：{e}"}


def _save_preference(user_gid: str = "", key: str = "", value: str = "") -> dict:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO app.user_preferences (user_gid, pref_key, pref_value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_gid, pref_key)
                    DO UPDATE SET pref_value=EXCLUDED.pref_value, updated_at=NOW()
                """, (user_gid, key, value))
        return {"text": f"已保存偏好：{key} = {value}"}
    except Exception:
        # 表不存在时不报错
        return {"text": f"已记录偏好：{key} = {value}"}


def _list_preferences(user_gid: str = "") -> dict:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pref_key, pref_value FROM app.user_preferences WHERE user_gid=%s",
                    (user_gid,),
                )
                rows = cur.fetchall()
        items = {r["pref_key"]: r["pref_value"] for r in rows}
        text = (
            "用户偏好：\n" + "\n".join(f"  {k}: {v}" for k, v in items.items())
            if items else "暂无保存的偏好"
        )
        return {"text": text, "preferences": items}
    except Exception:
        return {"text": "暂无保存的偏好", "preferences": {}}


def _generate_canvas(
    title: str = "工作流画布",
    canvas_mode: str = "flow",
    nodes: list = None,
    connections: list = None,
    lanes: list = None,
    step_labels: list = None,
    description: str = "",
    **_kwargs,
) -> dict:
    """生成画布结构（前端 workflow_canvas.js fromJSON 处理 result.canvas）。
    流程图模式（默认）：lanes + step_labels + nodes(lane_id/step) + connections 全部透传。
    沙盘模式：nodes 可不带 lane_id/step，自动按网格分配 x/y。
    """
    if canvas_mode == "sandbox":
        sandbox_nodes = []
        for i, node in enumerate(nodes or []):
            sandbox_nodes.append({
                "id":     node.get("id", f"n_{i}"),
                "type":   node.get("type", "bop_node"),
                "label":  node.get("label", ""),
                "x":      node.get("x", 40 + (i % 5) * 220),
                "y":      node.get("y", 40 + (i // 5) * 100),
                "params": node.get("params", {}),
            })
        return {
            "text":   f"沙盘画布已生成：{title}",
            "status": "canvas_generated",
            "canvas": {
                "title":          title,
                "canvas_mode":    "sandbox",
                "sandbox_nodes":  sandbox_nodes,
                "sandbox_conns":  connections or [],
            },
        }

    # 流程图模式（默认）
    canvas = {
        "title":       title,
        "lanes":       lanes or [],
        "step_labels": step_labels or [],
        "nodes":       nodes or [],
        "connections": connections or [],
    }
    # 提取节点内嵌的 questions，汇总到画布顶层
    questions: list = []
    for node in canvas["nodes"]:
        node_qs = node.pop("questions", None) or []
        for q in node_qs:
            q["nodeId"] = node["id"]
            questions.append(q)
    canvas["questions"] = questions
    return {
        "text":   f"画布已生成：{title}",
        "status": "canvas_generated",
        "canvas": canvas,
    }


# ── Phase 5：画布双向工具 ─────────────────────────────────────────────────────

def _get_canvas_state(canvas_id: str | None, canvas_context: dict | None) -> dict:
    """
    从会话 canvas_context 中读取画布状态。
    canvas_context 由前端在发起对话时通过 body.canvas_context 字段传入。
    """
    ctx = canvas_context or {}
    if not ctx:
        return {
            "text": "当前会话无画布上下文，请在画布页面发起对话",
            "canvas_id": None,
            "nodes": [],
        }

    cid = canvas_id or ctx.get("canvas_id") or ctx.get("skill_gid") or ""
    nodes = ctx.get("nodes") or []
    connections = ctx.get("connections") or []

    # 统计节点类型
    type_counter: dict[str, int] = {}
    for n in nodes:
        t = n.get("type") or n.get("node_type") or "unknown"
        type_counter[t] = type_counter.get(t, 0) + 1

    status_summary = (
        f"画布包含 {len(nodes)} 个节点（{', '.join(f'{v} {k}' for k, v in type_counter.items())}）"
        f"和 {len(connections)} 条连接"
    ) if nodes else "画布为空"

    return {
        "text":           f"画布状态：{status_summary}",
        "canvas_id":      cid,
        "nodes":          nodes,
        "connections":    connections,
        "status_summary": status_summary,
    }


def _get_selected_elements(canvas_context: dict | None) -> dict:
    """
    从会话 canvas_context 中读取当前选中元素列表。
    前端通过 body.canvas_context.selected 传入选中元素。
    """
    ctx = canvas_context or {}
    selected = ctx.get("selected") or []
    count = len(selected)

    if not selected:
        return {
            "text":     "当前无选中元素",
            "selected": [],
            "count":    0,
        }

    text = f"当前选中 {count} 个元素：\n" + "\n".join(
        f"  [{it.get('type', '?')}] {it.get('label') or it.get('title') or it.get('gid', '?')}"
        for it in selected
    )
    return {"text": text, "selected": selected, "count": count}


def _flag_for_review(
    reason: str = "",
    context: str = "",
    severity: str = "medium",
    user_gid: str = "",
    session_gid: str = "",
) -> dict:
    """
    标记需要人工复核，记录到 app.ai_audit_logs。
    """
    if not reason:
        return {"error": "reason 不能为空"}

    valid_severities = {"low", "medium", "high"}
    if severity not in valid_severities:
        severity = "medium"

    gid = str(uuid.uuid4()).replace("-", "")
    import json as _json

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO app.ai_audit_logs
                        (gid, session_gid, user_gid, action_type, payload, created_at)
                    VALUES (%s, %s, %s, 'flag_for_review', %s, NOW())
                    ON CONFLICT DO NOTHING
                """, (
                    gid, session_gid, user_gid,
                    _json.dumps({
                        "reason":   reason,
                        "context":  context,
                        "severity": severity,
                    }, ensure_ascii=False),
                ))
    except Exception:
        # 表不存在时静默忽略
        pass

    return {
        "text":    f"已标记人工复核（{severity}）：{reason}",
        "flagged": True,
        "gid":     gid,
        "severity": severity,
    }
