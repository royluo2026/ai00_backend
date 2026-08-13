"""Reviewed Local Runtime device lifecycle Capability contracts."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from ..application.outcomes import device_outcome_port
from .provider import register


LOCAL_DEVICE_CAPABILITIES = frozenset(
    {"local.device.change.apply", "local.device.read"}
)


def _handler(capability_id: str):
    def invoke(payload: dict[str, Any], context: object) -> dict[str, Any]:
        return {"data": device_outcome_port.invoke(capability_id, payload, context)}

    return invoke


def register_reviewed_capabilities(registry: Any) -> None:
    for capability_id in sorted(LOCAL_DEVICE_CAPABILITIES):
        is_write = capability_id.endswith(".change.apply")
        register(
            registry,
            CapabilitySpec(
                id=capability_id,
                owner="device",
                description=f"Execute the reviewed {capability_id} device outcome.",
                use_when="A governed consumer manages its Local Runtime devices.",
                do_not_use_when="The request executes a VisMockup workstation action.",
                risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
                confirmation="user" if is_write else "none",
                permissions=("system.tech_config",) if is_write else ("agent.run",),
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                tags=("local-runtime", "device", "write" if is_write else "read"),
            ),
            _handler(capability_id),
        )


__all__ = ["LOCAL_DEVICE_CAPABILITIES", "register_reviewed_capabilities"]
