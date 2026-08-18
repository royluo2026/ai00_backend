"""Closed, test-only contracts for the Capability Governance Center extension."""
from __future__ import annotations

from pathlib import Path

from backend.capability_v2.catalog import ProviderArtifact
from backend.capability_v2.provider_loader import hash_domain_artifact


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
    "base.capability_analysis.run",
    "base.capability_scan.run",
    "base.capability_test.run",
    "base.capability_proposal.submit",
    "base.capability_review.decide",
    "base.capability_waiver.grant",
    "base.capability_waiver.revoke",
}
_LIMIT_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 200}
_DEPTH_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 4}
_NODES_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 500}
_VERSION_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 255}
_SMALL_STRING_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 255}
_BOOLEAN_SCHEMA = {"type": "boolean"}
_RESPONSE_GID_FIELDS = (
    "capability_version_gid", "snapshot_gid", "run_gid", "proposal_gid",
    "waiver_gid", "release_report_gid",
)


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
    if capability_id == "base.capability_registry.search":
        properties["limit"] = _LIMIT_SCHEMA
    if capability_id == "base.capability_graph.get":
        properties.update({"max_depth": _DEPTH_SCHEMA, "max_nodes": _NODES_SCHEMA})
        required = ("target_gid", "max_depth", "max_nodes")
    if capability_id in {
        "base.capability_registry.get", "base.capability_analysis.get",
        "base.capability_analysis.run", "base.capability_repair_prompt.generate",
        "base.capability_test.run",
    }:
        required = tuple(sorted(set(required) | {"target_gid"}))
    if capability_id in {"base.capability_review.decide", "base.capability_waiver.revoke"}:
        properties.update({"row_version": _VERSION_SCHEMA, "expected_resource_version": _VERSION_SCHEMA})
    return _closed(properties, required)


INPUT_SCHEMAS = {capability_id: _input_schema(capability_id) for capability_id in ALL_IDS}

# These are deliberately projections, rather than record dumps.  They keep the
# agent transport closed while retaining the bounded result shapes returned by
# the governance service.
_ITEM_SCHEMA = _closed({"capability_id": STRING_SCHEMA, "capability_version_gid": GID_SCHEMA}, ("capability_id", "capability_version_gid"))
_NODE_SCHEMA = _closed({
    "canonical_key": STRING_SCHEMA, "owner_domain": _SMALL_STRING_SCHEMA,
    "node_type": _SMALL_STRING_SCHEMA, "source_path": STRING_SCHEMA,
    "artifact_hash": _SMALL_STRING_SCHEMA,
})
_FINDING_SCHEMA = _closed({
    "code": _SMALL_STRING_SCHEMA, "severity": _SMALL_STRING_SCHEMA,
    "fingerprint": _SMALL_STRING_SCHEMA, "remediation_boundary": _SMALL_STRING_SCHEMA,
})
_RUN_SCHEMA = _closed({
    "run_gid": GID_SCHEMA, "snapshot_gid": GID_SCHEMA, "kind": _SMALL_STRING_SCHEMA,
    "status": _SMALL_STRING_SCHEMA,
}, ("run_gid", "snapshot_gid", "kind", "status"))
_SNAPSHOT_SCHEMA = _closed({"snapshot_gid": GID_SCHEMA, "snapshot_hash": _SMALL_STRING_SCHEMA})
_PROPOSAL_SCHEMA = _closed({
    "proposal_gid": GID_SCHEMA, "status": _SMALL_STRING_SCHEMA,
    "row_version": _VERSION_SCHEMA,
}, ("proposal_gid", "status", "row_version"))
_WAIVER_SCHEMA = _closed({
    "waiver_gid": GID_SCHEMA, "status": _SMALL_STRING_SCHEMA,
    "row_version": _VERSION_SCHEMA,
}, ("waiver_gid", "status", "row_version"))
_RELEASE_SCHEMA = _closed({
    "report_gid": GID_SCHEMA, "conclusion": {"type": "string", "enum": ["pass", "fail", "expired"]},
    "blockers": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 200},
}, ("report_gid", "conclusion", "blockers"))
_BOUNDED_VALUE_SCHEMA = {"description": "Provider-validated bounded transport value."}
_BOUNDED_OBJECT_SCHEMA = {
    "type": "object", "maxProperties": 50,
    "additionalProperties": _BOUNDED_VALUE_SCHEMA,
}
_BOUNDED_COLLECTION_SCHEMA = {
    "type": "array", "maxItems": 500, "items": _BOUNDED_OBJECT_SCHEMA,
}


def _output_schema(capability_id: str) -> dict[str, object]:
    properties: dict[str, object] = {
        "capability_id": STRING_SCHEMA,
        "status": STATUS_SCHEMA,
        "data": _BOUNDED_OBJECT_SCHEMA,
        "items": _BOUNDED_COLLECTION_SCHEMA,
        "nodes": _BOUNDED_COLLECTION_SCHEMA,
        "findings": _BOUNDED_COLLECTION_SCHEMA,
        **{field: GID_SCHEMA for field in _RESPONSE_GID_FIELDS},
    }
    if capability_id == "base.capability_registry.search":
        properties["items"] = {"type": "array", "items": _ITEM_SCHEMA, "maxItems": 200}
    elif capability_id == "base.capability_registry.get":
        properties["item"] = _ITEM_SCHEMA
    elif capability_id == "base.capability_graph.get":
        properties.update({
            "snapshot": _SNAPSHOT_SCHEMA,
            "max_depth": _DEPTH_SCHEMA,
            "max_nodes": _NODES_SCHEMA,
            "nodes": {"type": "array", "items": _NODE_SCHEMA, "maxItems": 500},
        })
    elif capability_id == "base.capability_finding.search":
        properties["findings"] = {"type": "array", "items": _FINDING_SCHEMA, "maxItems": 200}
    elif capability_id in {"base.capability_analysis.run", "base.capability_test.run", "base.capability_analysis.get"}:
        properties["run"] = _RUN_SCHEMA
    elif capability_id == "base.capability_repair_prompt.generate":
        properties["snapshot"] = _SNAPSHOT_SCHEMA
    elif capability_id in {"base.capability_proposal.submit", "base.capability_review.decide"}:
        properties["proposal"] = _PROPOSAL_SCHEMA
    elif capability_id in {"base.capability_waiver.grant", "base.capability_waiver.revoke"}:
        properties["waiver"] = _WAIVER_SCHEMA
    elif capability_id == "base.capability_release_gate.evaluate":
        properties["release"] = _RELEASE_SCHEMA
    return _closed(properties, ("capability_id", "status"))


OUTPUT_SCHEMAS = {capability_id: _output_schema(capability_id) for capability_id in ALL_IDS}
def provider_artifact(repository_root: Path) -> ProviderArtifact:
    """Bind the test extension to its canonical source artifact at build time."""
    return ProviderArtifact(
        plugin_id="test.governance",
        module="backend.capability_governance_test.provider",
        version="1.0.0",
        artifact_hash=hash_domain_artifact(repository_root, "backend/capability_governance_test"),
    )


__all__ = [
    "ALL_IDS", "ANALYZE_IDS", "GID_SCHEMA", "GOVERN_IDS", "INPUT_SCHEMAS",
    "OUTPUT_SCHEMAS", "READ_IDS", "RELEASE_IDS", "WRITE_IDS", "provider_artifact",
]
