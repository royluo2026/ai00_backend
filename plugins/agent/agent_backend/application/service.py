from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from dataclasses import asdict

from .canvas_runtime import (
    CanvasOptionsRequest, CanvasResumeRequest, CanvasStartRequest, NodeTestRequest, RunPrincipal,
)


_CANVAS_REQUESTS = {
    "agent.workflow.node.test.execute": (NodeTestRequest, "test_node"),
    "agent.canvas.options.resolve": (CanvasOptionsRequest, "resolve_options"),
    "agent.canvas.execution.start": (CanvasStartRequest, "start"),
    "agent.canvas.execution.resume": (CanvasResumeRequest, "resume"),
}


class AgentApplication:
    def __init__(self, repository, audit_repository=None, session_repository=None, canvas_runtime=None):
        self.repository = repository
        self.audit_repository = audit_repository
        self.session_repository = session_repository
        self.canvas_runtime = canvas_runtime

    def invoke(self, capability_id: str, payload: dict, context):
        actor = getattr(context, "user_gid", None) or getattr(context, "actor_gid", None)
        tenant = getattr(context, "team_gid", None) or getattr(context, "tenant_gid", None)
        if not actor or not tenant:
            raise CapabilityBusinessError("permission_denied", "Agent access requires actor and tenant context")
        if capability_id in _CANVAS_REQUESTS:
            if self.canvas_runtime is None:
                raise CapabilityBusinessError(
                    "provider_unavailable", "Agent canvas runtime adapter is not configured", retryable=True
                )
            request_type, method_name = _CANVAS_REQUESTS[capability_id]
            try:
                request = request_type.from_payload(payload)
            except (TypeError, ValueError) as exc:
                raise CapabilityBusinessError("invalid_input", str(exc)) from exc
            principal = RunPrincipal(actor_gid=str(actor), team_gid=str(tenant))

            async def invoke_canvas():
                result = await getattr(self.canvas_runtime, method_name)(request, principal)
                return asdict(result)

            return invoke_canvas()
        family = capability_id.split(".")[1]
        data = {
            **payload,
            "owner_gid": str(actor),
            "tenant_gid": str(tenant),
            "resource_type": family,
            "active_roles": tuple(getattr(context, "active_roles", ()) or ()),
        }
        if family == "audit":
            if self.audit_repository is None:
                raise CapabilityBusinessError("provider_unavailable", "Agent audit provider is not configured")
            if capability_id == "agent.audit.record":
                event = {**payload, "user_gid": str(actor)}
                return {"gid": self.audit_repository.record(event)}
            if "super_admin" not in data["active_roles"]:
                raise CapabilityBusinessError("permission_denied", "Agent audit reads require super_admin")
            limit = payload.get("limit", 50)
            offset = payload.get("offset", 0)
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
                raise ValueError("limit must be between 1 and 500")
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                raise ValueError("offset must be >= 0")
            total, rows = self.audit_repository.list(
                session_gid=str(payload.get("session_gid") or ""),
                user_gid=str(payload.get("user_gid") or ""),
                tool_name=str(payload.get("tool_name") or ""),
                is_write=str(payload.get("is_write") or ""),
                limit=limit,
                offset=offset,
            )
            logs = []
            for row in rows:
                item = dict(row)
                created_at = item.get("created_at")
                if hasattr(created_at, "isoformat"):
                    item["created_at"] = created_at.isoformat()
                logs.append(item)
            return {"logs": logs, "total": int(total), "limit": limit, "offset": offset}
        if family == "session":
            if self.session_repository is None:
                raise CapabilityBusinessError("provider_unavailable", "Agent session provider is not configured")
            operation = str(payload.get("operation") or ("list" if capability_id.endswith(".read") else ""))
            if capability_id == "agent.session.read":
                if operation == "list":
                    return {"sessions": self.session_repository.list_sessions(str(actor))}
                if operation == "get":
                    session_gid = str(payload.get("session_gid") or "").strip()
                    if not session_gid:
                        raise ValueError("session_gid is required")
                    return {"turns": self.session_repository.get_session(session_gid, str(actor))}
            elif capability_id == "agent.session.change.apply":
                if operation == "create":
                    return {"session_gid": self.session_repository.create_session(str(actor))}
                if operation == "delete":
                    session_gid = str(payload.get("session_gid") or "").strip()
                    if not session_gid:
                        raise ValueError("session_gid is required")
                    if not self.session_repository.delete_owned_session(session_gid, str(actor)):
                        raise CapabilityBusinessError(
                            "resource_not_found", "Agent session was not found",
                            details={"session_gid": session_gid},
                        )
                    return {"success": True}
            raise ValueError(f"unsupported session operation: {operation}")
        if family == "flow":
            return self.repository.flow_read(data) if capability_id.endswith(".read") else self.repository.flow_apply(data)
        if family == "skill":
            return self.repository.skill_read(data) if capability_id.endswith(".read") else self.repository.skill_apply(data)
        if capability_id == "agent.script.generate":
            return self.repository.generate_script(data)
        if capability_id == "agent.runtime.config.read":
            return self.repository.runtime_config(data)
        if capability_id == "agent.tool_catalog.read":
            operation = str(payload.get("operation") or "list")
            if operation != "list":
                raise ValueError(f"unsupported tool catalog operation: {operation}")
            from ..ai_assistant.tool_registry import _READ_TOOLS, _WRITE_TOOLS_CONFIRM, _WRITE_TOOLS_NO_CONFIRM, _SYSTEM_TOOLS

            def format_tools(tools, category, need_confirm):
                return [{"name": item["name"], "description": item["description"], "category": category, "need_confirm": need_confirm, "params": list(item["input_schema"].get("properties", {}).keys())} for item in tools]

            return {
                "read": format_tools(_READ_TOOLS, "read", False),
                "write_confirm": format_tools(_WRITE_TOOLS_CONFIRM, "write_confirm", True),
                "write_no_confirm": format_tools(_WRITE_TOOLS_NO_CONFIRM, "write_no_confirm", False),
                "system": format_tools(_SYSTEM_TOOLS, "system", False),
                "total": len(_READ_TOOLS) + len(_WRITE_TOOLS_CONFIRM) + len(_WRITE_TOOLS_NO_CONFIRM) + len(_SYSTEM_TOOLS),
            }
        if capability_id == "agent.interaction.cancel":
            session_gid = str(payload.get("session_gid") or "").strip()
            if not session_gid:
                raise ValueError("session_gid is required")
            if self.session_repository is None:
                raise CapabilityBusinessError("provider_unavailable", "Agent session provider is not configured")
            self.session_repository.get_session(session_gid, str(actor))
            from .interaction_state import request_abort
            request_abort(session_gid)
            return {"ok": True, "session_gid": session_gid}
        if capability_id.endswith(".read"):
            return self.repository.read(data)
        if capability_id == "agent.interaction.request":
            return self.repository.request_interaction(data)
        return self.repository.apply(data)
