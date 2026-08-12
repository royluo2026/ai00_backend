"""Frozen Project Management outcomes backed by the application port."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from ..application.outcomes import project_outcome_port
from .provider import register_capability


PROJECT_CAPABILITY_IDS = frozenset(
    {
        "project.activity.aggregate",
        "project.approval.change.apply",
        "project.approval.read",
        "project.bitable_binding.change.apply",
        "project.bitable_binding.read",
        "project.change_log.read",
        "project.collaboration.change.apply",
        "project.collaboration.read",
        "project.craft_scope.read",
        "project.follow.change.apply",
        "project.follow.read",
        "project.issue.change.apply",
        "project.issue.read",
        "project.list.change.apply",
        "project.list.read",
        "project.member.change.apply",
        "project.member.read",
        "project.notification.change.apply",
        "project.notification.read",
        "project.permission_request.change.apply",
        "project.permission_request.read",
        "project.project.change.apply",
        "project.project.read",
        "project.sharing.change.apply",
        "project.sharing.read",
        "project.task.change.apply",
        "project.task.read",
        "project.task_template.change.apply",
        "project.task_template.read",
        "project.workbench.change.apply",
        "project.workbench.read",
    }
)


def _handler(capability_id: str):
    def invoke(payload: dict[str, Any], context: object) -> dict[str, Any]:
        return {"data": project_outcome_port.invoke(capability_id, payload, context)}

    return invoke


def register_reviewed_capabilities(registry: Any) -> None:
    for capability_id in sorted(PROJECT_CAPABILITY_IDS):
        is_write = capability_id.endswith(".change.apply")
        register_capability(
            registry,
            CapabilitySpec(
                id=capability_id,
                owner="project_management",
                description=f"Execute the reviewed {capability_id} project outcome.",
                use_when="A governed consumer needs this Project Management outcome.",
                do_not_use_when="The operation belongs to another domain.",
                risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
                confirmation="user" if is_write else "none",
                permissions=("project.write",) if is_write else ("project.read",),
                input_schema={"type": "object", "properties": {}},
                output_schema={
                    "type": "object",
                    "required": ["data"],
                    "properties": {"data": {}},
                },
                tags=("project_management", "write" if is_write else "read"),
            ),
            _handler(capability_id),
        )


__all__ = ["PROJECT_CAPABILITY_IDS", "register_reviewed_capabilities"]
