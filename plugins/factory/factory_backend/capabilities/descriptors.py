"""Factory Descriptor definitions approved by the domain architecture."""
from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from .contracts import INPUT_SCHEMA, OUTPUT_SCHEMA


FACTORY_CAPABILITY_IDS = (
    "factory.structure.create", "factory.structure.get", "factory.structure.search",
    "factory.structure.update", "factory.structure.archive",
    "factory.resource_catalog.get", "factory.resource_catalog.search",
    "factory.resource_catalog.create", "factory.resource_catalog.revise",
    "factory.resource_catalog.publish", "factory.resource_catalog.deprecate",
    "factory.asset.register", "factory.asset.get", "factory.asset.search",
    "factory.asset.update", "factory.asset.maintenance.start",
    "factory.asset.maintenance.complete", "factory.asset.scrap",
    "factory.resource.read",
)


def specs() -> tuple[CapabilitySpec, ...]:
    result = []
    for capability_id in FACTORY_CAPABILITY_IDS:
        read = capability_id.endswith((".get", ".search"))
        high_risk = capability_id == "factory.asset.scrap"
        result.append(CapabilitySpec(
            id=capability_id,
            owner="factory",
            description=f"Execute the governed {capability_id} Factory outcome.",
            use_when="A consumer needs physical factory topology, catalog, or asset data.",
            do_not_use_when="The resource is a BOP plan node or production schedule.",
            risk=CapabilityRisk.READ if read else CapabilityRisk.WRITE,
            confirmation="user" if high_risk else "none",
            permissions=("factory.read",) if read else (("factory.asset.scrap",) if high_risk else ("factory.write",)),
            input_schema=INPUT_SCHEMA,
            output_schema=OUTPUT_SCHEMA,
            tags=("factory", "read" if read else "write"),
        ))
    return tuple(result)
