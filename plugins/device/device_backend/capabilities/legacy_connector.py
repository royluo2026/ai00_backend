"""Fail-closed tombstones for Connector capabilities formerly owned by Device."""
from __future__ import annotations

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityRisk,
    CapabilitySpec,
)


def _moved(_payload, _context):
    raise CapabilityBusinessError(
        "capability_migration_required",
        "Connector and VisMockup moved to the Simulation domain.",
    )


def register_legacy_connector_capabilities(registry) -> None:
    from .provider import register

    definitions = (
        ("device.connector.health.get", 1, CapabilityRisk.READ),
        ("device.connector.plan.queue", 1, CapabilityRisk.WRITE),
        ("device.connector.plan.queue", 2, CapabilityRisk.WRITE),
    )
    for capability_id, version, risk in definitions:
        register(registry, CapabilitySpec(
            id=capability_id, owner="device", version=version,
            description="Deprecated Connector compatibility identity.",
            use_when="Never for new work; migrate to Simulation Connector capabilities.",
            do_not_use_when="For every executable Connector or VisMockup operation.",
            risk=risk,
            confirmation="user" if risk is CapabilityRisk.WRITE else "none",
            permissions=("agent.run",), input_schema={}, output_schema={},
            tags=("device", "deprecated", "connector"),
        ), _moved)


__all__ = ["register_legacy_connector_capabilities"]
