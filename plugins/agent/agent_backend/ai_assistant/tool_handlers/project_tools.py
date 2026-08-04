"""Project tools using the public domain HTTP boundary."""
from __future__ import annotations

from ...integrations.platform_http import PlatformHttpClient, PlatformHttpError

TOOL_NAMES = {
    "search", "list_tasks", "get_task", "list_task_lists", "list_issues", "get_issue",
    "list_issue_lists", "list_projects", "list_approval_orders", "create_task", "update_task",
    "create_issue", "update_issue", "create_approval_order", "add_task_progress_log",
}


def _data(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return value.get("data", value.get("items", value))
    return value


def dispatch(tool_name: str, inputs: dict, auth_token: str = "", user_gid: str = "", **_kwargs):
    if not user_gid:
        return {"error": "用户身份缺失，不能访问项目能力"}
    client = PlatformHttpClient(auth_token)
    try:
        if tool_name == "search":
            result = client.get("/api/search", {"q": inputs.get("keyword", ""), "modules": inputs.get("modules", ""), "limit": inputs.get("limit", 5)})
        elif tool_name == "list_tasks":
            result = client.get("/api/tasks", inputs)
        elif tool_name == "get_task":
            result = client.get(f"/api/tasks/{inputs.get('gid', '')}")
        elif tool_name == "list_task_lists":
            result = client.get("/api/task-lists")
        elif tool_name == "list_issues":
            result = client.get("/api/issues", inputs)
        elif tool_name == "get_issue":
            result = client.get(f"/api/issues/{inputs.get('gid', '')}")
        elif tool_name == "list_issue_lists":
            result = client.get("/api/issue-lists")
        elif tool_name == "list_projects":
            result = client.get("/api/projects")
        elif tool_name == "list_approval_orders":
            result = client.get("/api/approval-orders", inputs)
        elif tool_name == "create_task":
            result = client.post("/api/tasks", inputs)
        elif tool_name == "update_task":
            result = client.put(f"/api/tasks/{inputs.get('gid', '')}", {k: v for k, v in inputs.items() if k != "gid"})
        elif tool_name == "create_issue":
            result = client.post("/api/issues", inputs)
        elif tool_name == "update_issue":
            result = client.put(f"/api/issues/{inputs.get('gid', '')}", {k: v for k, v in inputs.items() if k != "gid"})
        elif tool_name == "create_approval_order":
            result = client.post("/api/approval-orders", inputs)
        elif tool_name == "add_task_progress_log":
            result = client.post(f"/api/tasks/{inputs.get('gid', '')}/progress", {"content": inputs.get("content", "")})
        else:
            return {"error": f"project_tools: 未知工具 {tool_name}"}
        return {"text": f"{tool_name} 调用完成", "data": _data(result), "source": "domain_http"}
    except PlatformHttpError as exc:
        return {"error": str(exc), "tool": tool_name, "source": "domain_http"}
