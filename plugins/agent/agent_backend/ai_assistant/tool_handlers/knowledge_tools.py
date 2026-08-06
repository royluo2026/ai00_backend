"""Knowledge/rule tools that never query another domain's tables."""
from __future__ import annotations

from ...integrations.platform_http import PlatformHttpClient, PlatformHttpError
from .capability_tools import dispatch_knowledge, dispatch_ontology

TOOL_NAMES = {
    "search_knowledge", "get_knowledge_entry", "get_knowledge_document", "list_rules", "find_similar_cases",
    "aggregate_history", "check_rules", "recommend_practice", "get_ontology_schema",
    "audit_entry_rules", "get_entry_relations",
}


def dispatch(tool_name: str, inputs: dict, auth_mode: str = "feishu", auth_token: str = "", user_gid: str = "", **_kwargs):
    if not user_gid:
        return {"error": "用户身份缺失，不能访问知识能力"}
    if tool_name in {"search_knowledge", "get_knowledge_entry", "get_knowledge_document"}:
        try:
            return dispatch_knowledge(tool_name, inputs, user_gid=user_gid, auth_mode=auth_mode)
        except Exception as exc:
            return {"error": str(exc), "source": "capability"}
    if tool_name == "get_ontology_schema":
        try:
            return dispatch_ontology(inputs, user_gid=user_gid, auth_mode=auth_mode)
        except Exception as exc:
            return {"error": str(exc), "source": "capability"}
    client = PlatformHttpClient(auth_token)
    try:
        if tool_name == "list_rules":
            value = client.get("/api/rules", inputs)
        elif tool_name == "find_similar_cases":
            value = client.get("/api/search/similar", inputs)
        elif tool_name == "aggregate_history":
            value = client.get("/api/analytics/history", inputs)
        elif tool_name == "check_rules":
            value = client.post("/api/rule-engine/check-batch", inputs)
        elif tool_name == "recommend_practice":
            value = client.get("/api/knowledge/recommendations", inputs)
        elif tool_name == "audit_entry_rules":
            value = client.post(f"/api/rule-engine/audit/entry/{inputs.get('entry_gid', '')}", inputs)
        elif tool_name == "get_entry_relations":
            value = client.get(f"/api/bop/entries/{inputs.get('entry_gid', '')}/relations", {"rel_type": inputs.get("rel_type", "")})
        else:
            return {"error": f"knowledge_tools: 未知工具 {tool_name}"}
        return {"text": f"{tool_name} 调用完成", "data": value, "source": "domain_http"}
    except PlatformHttpError as exc:
        return {"error": str(exc), "tool": tool_name, "source": "domain_http"}
