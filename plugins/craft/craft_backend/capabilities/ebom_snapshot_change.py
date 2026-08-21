"""Atomic PBOM snapshot metadata mutations."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

from .ebom_change import apply_ebom_change


def _handler(operation: str):
    def invoke(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        request = dict(payload)
        request["operation"] = operation
        return apply_ebom_change(request, context)
    return invoke


def register_ebom_snapshot_change_capabilities(registry: Any) -> None:
    for capability_id, operation, description in (
        ("craft.ebom.snapshot.delete", "snapshot.delete", "Delete one PBOM snapshot."),
        ("craft.ebom.snapshot.update", "snapshot.patch", "Update PBOM snapshot metadata."),
    ):
        registry.register(CapabilitySpec(
            id=capability_id, owner="craft", description=description,
            use_when="A governed consumer changes one PBOM snapshot metadata resource.",
            do_not_use_when="The request changes snapshot status, statistics, or a part.",
            risk="write", confirmation="user", permissions=("craft.write",),
            input_schema={"type": "object"}, output_schema={"type": "object"},
            tags=("craft", "ebom", "snapshot", "write"),
        ), _handler(operation))


__all__ = ["register_ebom_snapshot_change_capabilities"]
