"""
backend/ai_assistant/tool_handlers/memory_tools.py
────────────────────────────────────────────────────
结构化 AI 记忆工具（save_memory / recall_memory / list_memories）。

表：app.ai_memory（由 main.py _ensure_ai_memory_table() 幂等建表）
"""
from __future__ import annotations
import uuid
from typing import Any

from backend.db.connection import get_conn

TOOL_NAMES: set[str] = {
    "save_memory",
    "recall_memory",
    "list_memories",
}


def dispatch(
    tool_name: str,
    inputs: dict,
    auth_mode: str = "feishu",
    auth_token: str = "",
    user_gid: str = "",
    **_kwargs,
) -> Any:
    if tool_name == "save_memory":
        return _save_memory(inputs, user_gid)
    if tool_name == "recall_memory":
        return _recall_memory(inputs, user_gid)
    if tool_name == "list_memories":
        return _list_memories(inputs, user_gid)
    return {"error": f"memory_tools: 未知工具 {tool_name}"}


# ── 实现 ───────────────────────────────────────────────────────────────────────

def _save_memory(inputs: dict, user_gid: str) -> dict:
    """
    保存 AI 记忆条目。
    inputs: {key, content, tag: preference|project_context|learned_pattern|domain_rule, overwrite: bool}
    → Upsert to app.ai_memory; 返回 {"text": "已保存：{key}"}
    """
    key      = str(inputs.get("key") or "").strip()
    content  = str(inputs.get("content") or "").strip()
    tag      = str(inputs.get("tag") or "preference")
    overwrite = bool(inputs.get("overwrite", True))

    if not key:
        return {"error": "key 不能为空"}
    if not content:
        return {"error": "content 不能为空"}

    valid_tags = {"preference", "project_context", "learned_pattern", "domain_rule"}
    if tag not in valid_tags:
        tag = "preference"

    gid = str(uuid.uuid4()).replace("-", "")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                if overwrite:
                    cur.execute("""
                        INSERT INTO app.ai_memory
                            (gid, user_gid, memory_key, content, tag, scope, confidence)
                        VALUES (%s, %s, %s, %s, %s, 'user', 1.0)
                        ON CONFLICT (user_gid, memory_key)
                        DO UPDATE SET
                            content    = EXCLUDED.content,
                            tag        = EXCLUDED.tag,
                            updated_at = NOW()
                    """, (gid, user_gid, key, content, tag))
                else:
                    cur.execute("""
                        INSERT INTO app.ai_memory
                            (gid, user_gid, memory_key, content, tag, scope, confidence)
                        VALUES (%s, %s, %s, %s, %s, 'user', 1.0)
                        ON CONFLICT (user_gid, memory_key) DO NOTHING
                    """, (gid, user_gid, key, content, tag))
        return {"text": f"已保存记忆：{key}", "key": key, "tag": tag}
    except Exception as e:
        return {"error": str(e)}


def _recall_memory(inputs: dict, user_gid: str) -> dict:
    """
    检索 AI 记忆。
    inputs: {query, tag_filter, limit}
    → ILIKE 关键词搜索（无 pgvector 时降级）
    → 返回 {"text": "...", "items": [...], "total": n}
    """
    query      = str(inputs.get("query") or "").strip()
    tag_filter = inputs.get("tag_filter") or ""
    limit      = min(int(inputs.get("limit") or 10), 50)

    if not query:
        return {"error": "query 不能为空"}

    conditions = ["user_gid = %s", "(memory_key ILIKE %s OR content ILIKE %s)"]
    params: list = [user_gid, f"%{query}%", f"%{query}%"]

    if tag_filter:
        conditions.append("tag = %s")
        params.append(tag_filter)

    where = " AND ".join(conditions)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT gid, memory_key, content, tag, confidence, updated_at "
                    f"FROM app.ai_memory WHERE {where} "
                    f"ORDER BY updated_at DESC LIMIT %s",
                    params + [limit],
                )
                rows = cur.fetchall()
        items = [dict(r) for r in rows]
        # 将 datetime 对象转为字符串（JSON 序列化安全）
        for it in items:
            if "updated_at" in it and hasattr(it["updated_at"], "isoformat"):
                it["updated_at"] = it["updated_at"].isoformat()
        text = f"记忆检索「{query}」：{len(items)} 条\n" + "\n".join(
            f"  [{it['tag']}] {it['memory_key']}: {it['content'][:80]}" for it in items
        )
        return {"text": text, "items": items, "total": len(items), "search_mode": "keyword"}
    except Exception as e:
        return {"error": str(e)}


def _list_memories(inputs: dict, user_gid: str) -> dict:
    """
    列出所有记忆条目（按 tag 分组）。
    → 返回 {"text": "...", "groups": {"preference": [...], ...}}
    """
    limit = min(int(inputs.get("limit") or 100), 200)

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid, memory_key, content, tag, confidence, updated_at "
                    "FROM app.ai_memory WHERE user_gid = %s "
                    "ORDER BY tag, updated_at DESC LIMIT %s",
                    (user_gid, limit),
                )
                rows = cur.fetchall()
        groups: dict[str, list] = {}
        for r in rows:
            item = dict(r)
            if "updated_at" in item and hasattr(item["updated_at"], "isoformat"):
                item["updated_at"] = item["updated_at"].isoformat()
            tag = item.get("tag", "preference")
            groups.setdefault(tag, []).append(item)

        total = sum(len(v) for v in groups.values())
        lines = [f"共 {total} 条记忆："]
        for tag, items in groups.items():
            lines.append(f"  [{tag}] {len(items)} 条")
        return {"text": "\n".join(lines), "groups": groups, "total": total}
    except Exception as e:
        return {"error": str(e)}
