from __future__ import annotations

import inspect
from typing import Any


def invoke_capability_for_user(
    capability_id: str,
    payload: dict[str, Any],
    *,
    user_gid: str,
    source: str,
) -> dict[str, Any]:
    """Transitional in-process transport with the same checks as the future gateway."""
    if not user_gid:
        raise PermissionError("user_gid is required")
    from backend.capabilities import CapabilityContext, capability_registry
    from backend.capabilities.validation_next import validate_payload
    from backend.services.user_service import get_by_gid
    from .auth import build_profile

    user = get_by_gid(user_gid)
    if not user or not user.get("is_active", True):
        raise PermissionError("Agent 用户不存在或已停用")
    profile = build_profile(user)
    context = CapabilityContext(
        user_gid=user_gid,
        team_gid=user.get("team_id") or None,
        source=source,
        permissions=tuple(profile.get("permissions", [])),
    )
    item = capability_registry.get(capability_id)
    validate_payload(dict(item.spec.input_schema), payload)
    if item.spec.confirmation != "none":
        raise PermissionError(
            f"{item.spec.id} requires an explicit confirmation token through the Capability gateway"
        )
    missing = sorted(set(item.spec.permissions) - set(context.permissions))
    if missing:
        raise PermissionError(f"缺少能力权限：{', '.join(missing)}")
    value = item.handler(payload, context)
    if inspect.isawaitable(value):
        raise RuntimeError("同步 Agent 不支持异步 capability handler")
    from backend.capabilities.models_next import CapabilityOutput
    evidence = ()
    if isinstance(value, CapabilityOutput):
        evidence = value.evidence
        value = value.data
    return {
        "capability_id": item.spec.id,
        "version": item.spec.version,
        "data": value,
        "evidence": [item.model_dump(mode="json") for item in evidence],
    }
