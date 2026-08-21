"""Governed creation and refresh of Craft BOP templates."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec


OPERATIONS = ("save_as_template", "update_from")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def apply_bop_template_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    if operation == "save_as_template":
        source_gid = _required(payload, "source_version_gid")
        factory_gid = _required(payload, "factory_gid")
        template_name = _required(payload, "template_name")
        copy_operator = bool(payload.get("copy_operator", False))
        # Keep the existing, well-tested copy semantics in the Craft domain.
        from ..routers._bop.templates import SaveAsTemplateBody, _legacy_save_as_template
        return _legacy_save_as_template(
            source_gid,
            SaveAsTemplateBody(factory_gid=factory_gid, template_name=template_name, copy_operator=copy_operator),
            {"gid": context.user_gid},
        )

    template_gid = _required(payload, "template_gid")
    source_gid = _required(payload, "source_version_gid")
    from ..routers._bop.templates import _legacy_update_template_from
    return _legacy_update_template_from(template_gid, source_gid, {"gid": context.user_gid})


def register_bop_template_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.template.change.apply", owner="craft",
        description="Create a BOP template from a version or refresh a template from a source version.",
        use_when="A governed Craft consumer explicitly creates or refreshes a BOP template.",
        do_not_use_when="The request edits a working version directly or publishes a version.",
        risk="write", confirmation="user", idempotent=False, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": False}, "entries_count": {"type": "integer"}}, "additionalProperties": False},
        tags=("craft", "bop", "template", "write"),
    ), apply_bop_template_change)


__all__ = ["OPERATIONS", "apply_bop_template_change", "register_bop_template_change_capability"]
