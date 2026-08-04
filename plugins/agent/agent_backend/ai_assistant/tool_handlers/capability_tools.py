"""Agent adapters for stable platform Capabilities."""
from __future__ import annotations

from typing import Any

from backend.platform_sdk import invoke_capability_for_user


def _invoke(capability_id: str, payload: dict[str, Any], user_gid: str, auth_mode: str) -> dict[str, Any]:
    return invoke_capability_for_user(
        capability_id,
        payload,
        user_gid=user_gid,
        source=f"agent:{auth_mode or 'web'}",
    )


def dispatch_knowledge(tool_name: str, inputs: dict[str, Any], *, user_gid: str, auth_mode: str) -> dict[str, Any]:
    if tool_name == "search_knowledge":
        payload = {
            "query": inputs.get("keyword", inputs.get("query", "")),
            "limit": inputs.get("limit", 10),
            "entry_type": inputs.get("entry_type", ""),
        }
        invocation = _invoke("knowledge.search", payload, user_gid, auth_mode)
        legacy = invocation["data"]
        items = list(legacy.get("items", []))
        evidence = list(invocation.get("evidence", []))
        try:
            documents = _invoke(
                "knowledge.document.search",
                {"query": payload["query"], "limit": payload["limit"]},
                user_gid,
                auth_mode,
            )
            document_items = documents["data"].get("items", [])
            items.extend({**item, "kind": "document_revision"} for item in document_items)
            evidence.extend(documents.get("evidence", []))
        except Exception:
            # During rolling deployment the new revision tables may not exist yet.
            pass
        text = f"知识库搜索「{payload['query']}」：{len(items)} 条\n" + "\n".join(
            f"  {item.get('title', '')} [{item.get('document_gid') or item.get('gid', '')}]"
            for item in items
        )
        return {
            "text": text,
            "items": items,
            "total": len(items),
            "evidence": evidence,
            "source": "capability",
        }
    if tool_name == "get_knowledge_document":
        invocation = _invoke(
            "knowledge.document.get",
            {
                "document_gid": str(inputs.get("document_gid") or "").strip(),
                "revision_gid": str(inputs.get("revision_gid") or "").strip(),
            },
            user_gid,
            auth_mode,
        )
        result = invocation["data"]
        return {
            "text": f"知识文档：{result.get('title', '')} revision {result.get('revision_no', '')}",
            "data": result,
            "evidence": invocation.get("evidence", []),
            "source": "capability",
        }
    if tool_name == "get_knowledge_entry":
        invocation = _invoke(
            "knowledge.get", {"gid": str(inputs.get("gid") or "").strip()}, user_gid, auth_mode
        )
        result = invocation["data"]
        return {"text": f"知识条目：{result.get('title', '')}", "data": result, "evidence": invocation.get("evidence", []), "source": "capability"}
    return {"error": f"capability_tools: 未知工具 {tool_name}"}
