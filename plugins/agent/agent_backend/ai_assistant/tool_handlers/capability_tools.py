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
            "limit": min(int(inputs.get("limit", 10)), 10),
        }
        invocation = _invoke("knowledge.context.retrieve", payload, user_gid, auth_mode)
        result = invocation["data"]
        items = list(result.get("items", []))
        text = f"知识上下文「{payload['query']}」：{len(items)} 条\n" + "\n".join(
            f"  {item.get('title', '')} [{item.get('document_gid', '')}@{item.get('revision_gid', '')}]"
            for item in items
        )
        return {
            "text": text,
            "items": items,
            "total": len(items),
            "evidence": invocation.get("evidence", []),
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


def dispatch_bop_structure(inputs: dict[str, Any], *, user_gid: str, auth_mode: str) -> dict[str, Any]:
    version_gid = str(inputs.get("version_gid") or "").strip()
    if not version_gid:
        return {"error": "请提供 version_gid"}
    invocation = _invoke(
        "craft.bop.execution_structure.get",
        {"version_gid": version_gid},
        user_gid,
        auth_mode,
    )
    structure = invocation["data"]
    nodes = list(structure.get("nodes", []))
    lines = [f"BOP 正式执行结构共 {len(nodes)} 个节点："]
    for node in nodes[:100]:
        vpps = f" `{node['vpps']}`" if node.get("vpps") else ""
        lines.append(f"- [{node.get('kind', '')}]{vpps} {node.get('name', '')}")
    if len(nodes) > 100:
        lines.append(f"…（共 {len(nodes)} 个节点，仅展示前 100 个）")
    return {
        "text": "\n".join(lines),
        "data": structure,
        "evidence": invocation.get("evidence", []),
        "source": "capability",
    }


def dispatch_ontology(inputs: dict[str, Any], *, user_gid: str, auth_mode: str) -> dict[str, Any]:
    term = str(inputs.get("node_type") or inputs.get("term") or "").strip()
    if not term:
        return {"error": "请提供 node_type 或 term"}
    resolved_invocation = _invoke("ontology.concept.resolve", {"term": term}, user_gid, auth_mode)
    resolved = resolved_invocation["data"]
    concept = resolved.get("concept")
    if resolved.get("status") != "resolved" or not isinstance(concept, dict):
        return {
            "text": f"本体概念「{term}」未唯一解析，状态：{resolved.get('status', 'unresolved')}",
            "data": resolved,
            "evidence": resolved_invocation.get("evidence", []),
            "source": "capability",
        }
    detail_invocation = _invoke(
        "ontology.concept.get",
        {
            "stable_gid": concept["stable_gid"],
            "kind": concept.get("kind", "concept"),
            "release_gid": resolved["release_gid"],
            "view": "schema",
        },
        user_gid,
        auth_mode,
    )
    detail = detail_invocation["data"]
    evidence = [*resolved_invocation.get("evidence", []), *detail_invocation.get("evidence", [])]
    return {
        "text": f"本体概念：{concept.get('label_zh') or concept.get('name') or concept['stable_gid']}",
        "data": detail,
        "evidence": evidence,
        "source": "capability",
    }
