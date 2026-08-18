"""Closed, test-only contracts for the Capability Governance Center extension."""
from __future__ import annotations

from backend.capability_v2.catalog import ProviderArtifact


READ_IDS = (
    "base.capability_registry.search",
    "base.capability_registry.get",
    "base.capability_graph.get",
    "base.capability_finding.search",
    "base.capability_analysis.get",
)
ANALYZE_IDS = (
    "base.capability_analysis.run",
    "base.capability_repair_prompt.generate",
)
GOVERN_IDS = (
    "base.capability_scan.run",
    "base.capability_test.run",
    "base.capability_proposal.submit",
    "base.capability_review.decide",
    "base.capability_waiver.grant",
    "base.capability_waiver.revoke",
)
RELEASE_IDS = ("base.capability_release_gate.evaluate",)
ALL_IDS = READ_IDS + ANALYZE_IDS + GOVERN_IDS + RELEASE_IDS

GID_SCHEMA = {"type": "string", "pattern": r"^[0-9]{1,19}$", "minLength": 1, "maxLength": 19}
STRING_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 512}
STATUS_SCHEMA = {"type": "string", "enum": ["accepted", "completed"]}
WRITE_IDS = {
    "base.capability_scan.run",
    "base.capability_test.run",
    "base.capability_proposal.submit",
    "base.capability_review.decide",
    "base.capability_waiver.grant",
    "base.capability_waiver.revoke",
}


def _closed(properties: dict[str, object], required: tuple[str, ...] = ()) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _input_schema(capability_id: str) -> dict[str, object]:
    properties: dict[str, object] = {
        "target_gid": GID_SCHEMA,
        "query": {"type": "string", "maxLength": 512},
    }
    required: tuple[str, ...] = ()
    if capability_id in WRITE_IDS:
        properties["idempotency_key"] = {"type": "string", "minLength": 1, "maxLength": 255}
        required = ("idempotency_key",)
    return _closed(properties, required)


INPUT_SCHEMAS = {capability_id: _input_schema(capability_id) for capability_id in ALL_IDS}
OUTPUT_SCHEMAS = {
    capability_id: _closed({"capability_id": STRING_SCHEMA, "status": STATUS_SCHEMA}, ("capability_id", "status"))
    for capability_id in ALL_IDS
}
PROVIDER_ARTIFACT = ProviderArtifact(
    plugin_id="test.governance",
    module="backend.capability_governance_test.provider",
    version="1.0.0",
    artifact_hash="sha256:5f57bb31a5b099578974b43e75dd6f644e9501e4d8fd8b0bba49dbb2cb9d8c4f",
)


__all__ = [
    "ALL_IDS", "ANALYZE_IDS", "GID_SCHEMA", "GOVERN_IDS", "INPUT_SCHEMAS",
    "OUTPUT_SCHEMAS", "PROVIDER_ARTIFACT", "READ_IDS", "RELEASE_IDS", "WRITE_IDS",
]
