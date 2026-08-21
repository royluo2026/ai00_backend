"""Atomic PBOM snapshot status transition."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

from .ebom_change import apply_ebom_change


def register_ebom_snapshot_status_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.ebom.snapshot.status.update", owner="craft",
        description="Transition one PBOM snapshot status.",
        use_when="A governed consumer transitions a PBOM snapshot status.",
        do_not_use_when="The request changes metadata or VPPS statistics.",
        risk="write", confirmation="user", permissions=("craft.write",),
        input_schema={"type": "object"}, output_schema={"type": "object"},
        tags=("craft", "ebom", "snapshot", "status", "write"),
    ), lambda payload, context: apply_ebom_change(
        {**payload, "operation": "snapshot.status.patch"}, context
    ))


__all__ = ["register_ebom_snapshot_status_change_capability"]
