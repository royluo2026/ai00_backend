"""Final approved Craft outcomes exposed through the application port."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from ..application.outcomes import craft_outcome_port
from .provider import register_capability
from .reviewed_ids import CRAFT_REVIEWED_CAPABILITIES, READ_CAPABILITIES, WRITE_CAPABILITIES


def _handler(capability_id: str):
    def invoke(payload: dict[str, Any], context: object) -> dict[str, Any]:
        return {"data": craft_outcome_port.invoke(capability_id, payload, context)}

    return invoke


def register_reviewed_capabilities(registry: Any) -> None:
    for capability_id in sorted(CRAFT_REVIEWED_CAPABILITIES):
        if capability_id in {"craft.canvas.read", "craft.canvas.change.apply", "craft.data_exchange.export", "craft.ebom.change.apply"}:
            continue
        is_write = capability_id in WRITE_CAPABILITIES
        register_capability(
            registry,
            CapabilitySpec(
                id=capability_id,
                owner="craft",
                description=f"Execute the reviewed {capability_id} Craft outcome.",
                use_when="A governed consumer needs this Craft-owned outcome.",
                do_not_use_when="The operation belongs to another business domain.",
                risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
                confirmation="user" if is_write else "none",
                permissions=("craft.write",) if is_write else ("craft.read",),
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                tags=("craft", "reviewed", "write" if is_write else "read"),
            ),
            _handler(capability_id),
        )


__all__ = [
    "CRAFT_REVIEWED_CAPABILITIES",
    "READ_CAPABILITIES",
    "WRITE_CAPABILITIES",
    "register_reviewed_capabilities",
]
