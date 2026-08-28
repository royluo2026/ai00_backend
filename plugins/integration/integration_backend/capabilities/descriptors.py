from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec
from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS


INTEGRATION_CAPABILITY_IDS = (
    "integration.connector.archive", "integration.connector.connection.test",
    "integration.connector.create", "integration.connector.schema.discover",
    "integration.connector.search", "integration.connector.update",
    "integration.field_mapping.batch.update", "integration.field_mapping.search",
    "integration.mapping.archive", "integration.mapping.create", "integration.mapping.get",
    "integration.mapping.import.start", "integration.mapping.preview", "integration.mapping.search",
    "integration.mapping.source_columns.discover", "integration.mapping.update",
    "integration.mapping_target.search",
    "integration.sync.start",
)


def specs() -> tuple[CapabilitySpec, ...]:
    reads = {
        "integration.connector.search", "integration.connector.schema.discover",
        "integration.field_mapping.search", "integration.mapping.get",
        "integration.mapping.preview", "integration.mapping.search",
        "integration.mapping.source_columns.discover", "integration.mapping_target.search",
    }
    result = []
    for capability_id in INTEGRATION_CAPABILITY_IDS:
        read = capability_id in reads
        result.append(CapabilitySpec(
            id=capability_id,
            owner="integration",
            description=f"Execute the governed {capability_id} Integration outcome.",
            use_when="A consumer needs governed external connector, mapping, or sync orchestration.",
            do_not_use_when="The caller can use an owning domain Capability directly without external integration.",
            risk=CapabilityRisk.READ if read else CapabilityRisk.WRITE,
            confirmation="none" if read else "user",
            permissions=("integration.read",) if read else ("integration.write",),
            input_schema=INPUT_SCHEMAS[capability_id], output_schema=OUTPUT_SCHEMAS[capability_id],
            tags=("integration", "read" if read else "write"),
        ))
    return tuple(result)

__all__ = ["INTEGRATION_CAPABILITY_IDS", "specs"]
