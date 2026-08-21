"""Atomic PBOM VPPS check statistics mutation."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

from .ebom_change import apply_ebom_change


def register_ebom_vpps_stats_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.ebom.snapshot.vpps_stats.update", owner="craft",
        description="Store one PBOM snapshot VPPS check result.",
        use_when="A governed consumer records bounded VPPS statistics.",
        do_not_use_when="The request changes snapshot metadata or status.",
        risk="write", confirmation="user", permissions=("craft.write",),
        input_schema={"type": "object"}, output_schema={"type": "object"},
        tags=("craft", "ebom", "vpps", "write"),
    ), lambda payload, context: apply_ebom_change(
        {**payload, "operation": "snapshot.vpps_stats.patch"}, context
    ))


__all__ = ["register_ebom_vpps_stats_change_capability"]


def _handler(operation: str):
    def invoke(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        return apply_ebom_change({**payload, "operation": operation}, context)
    return invoke


def register_ebom_part_change_capabilities(registry: Any) -> None:
    specs = (
        ("craft.ebom.part.create", "part.add", "Create one PBOM part."),
        ("craft.ebom.part.bulk_create", "part.add_batch", "Create a bounded PBOM part batch."),
        ("craft.ebom.part.update", "part.update", "Update one PBOM part."),
        ("craft.ebom.part.delete", "part.delete", "Delete one PBOM part."),
    )
    for capability_id, operation, description in specs:
        register_capability(registry, CapabilitySpec(
            id=capability_id, owner="craft", description=description,
            use_when="A governed consumer changes one PBOM part resource.",
            do_not_use_when="The request changes a PBOM snapshot or crosses Craft domains.",
            risk="write", confirmation="user", permissions=("craft.write",),
            input_schema={"type": "object"}, output_schema={"type": "object"},
            tags=("craft", "ebom", "part", "write"),
        ), _handler(operation))


__all__ = ["register_ebom_part_change_capabilities"]
