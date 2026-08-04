"""Private structured memory tools backed by the Agent-owned repository."""
from __future__ import annotations

from typing import Any

from ...data.memory_repository import MemoryRepository

TOOL_NAMES = {"save_memory", "recall_memory", "list_memories"}
_repository = MemoryRepository()


def dispatch(tool_name: str, inputs: dict, user_gid: str = "", **_kwargs) -> Any:
    if not user_gid:
        return {"error": "用户身份缺失，不能访问私人记忆"}
    if tool_name == "save_memory":
        return _save_memory(inputs, user_gid)
    if tool_name == "recall_memory":
        return _recall_memory(inputs, user_gid)
    if tool_name == "list_memories":
        return _list_memories(inputs, user_gid)
    return {"error": f"memory_tools: 未知工具 {tool_name}"}


def _serialize_rows(rows):
    result = []
    for row in rows:
        item = dict(row)
        if hasattr(item.get("updated_at"), "isoformat"):
            item["updated_at"] = item["updated_at"].isoformat()
        result.append(item)
    return result


def _save_memory(inputs: dict, user_gid: str) -> dict:
    key = str(inputs.get("key") or "").strip()
    content = str(inputs.get("content") or "").strip()
    tag = str(inputs.get("tag") or "preference")
    if not key or not content:
        return {"error": "key 和 content 不能为空"}
    if tag not in {"preference", "project_context", "learned_pattern", "domain_rule"}:
        tag = "preference"
    try:
        _repository.save(user_gid, key, content, tag, bool(inputs.get("overwrite", True)))
        return {"text": f"已保存记忆：{key}", "key": key, "tag": tag}
    except Exception as exc:
        return {"error": str(exc)}


def _recall_memory(inputs: dict, user_gid: str) -> dict:
    query = str(inputs.get("query") or "").strip()
    if not query:
        return {"error": "query 不能为空"}
    try:
        items = _serialize_rows(
            _repository.search(user_gid, query, str(inputs.get("tag_filter") or ""), int(inputs.get("limit") or 10))
        )
        text = f"记忆检索「{query}」：{len(items)} 条\n" + "\n".join(
            f"  [{item['tag']}] {item['memory_key']}: {item['content'][:80]}" for item in items
        )
        return {"text": text, "items": items, "total": len(items), "search_mode": "keyword"}
    except Exception as exc:
        return {"error": str(exc)}


def _list_memories(inputs: dict, user_gid: str) -> dict:
    try:
        rows = _serialize_rows(_repository.list_for_user(user_gid, int(inputs.get("limit") or 100)))
        groups: dict[str, list] = {}
        for item in rows:
            groups.setdefault(item.get("tag", "preference"), []).append(item)
        total = sum(len(items) for items in groups.values())
        lines = [f"共 {total} 条记忆："] + [f"  [{tag}] {len(items)} 条" for tag, items in groups.items()]
        return {"text": "\n".join(lines), "groups": groups, "total": total}
    except Exception as exc:
        return {"error": str(exc)}
