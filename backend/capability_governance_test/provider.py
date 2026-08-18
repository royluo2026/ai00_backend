"""Test-only Base registration for governance catalog descriptors."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable
from unittest.mock import patch

from backend.base import provider as base_provider
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityRisk, CapabilitySpec

from .contracts import ALL_IDS, ANALYZE_IDS, GOVERN_IDS, INPUT_SCHEMAS, OUTPUT_SCHEMAS, RELEASE_IDS, WRITE_IDS


_READ_PERMISSION = "system.capability.read"
_ANALYZE_PERMISSION = "system.capability.analyze"
_GOVERN_PERMISSION = "system.capability.govern"
_RELEASE_PERMISSION = "system.capability.release"


def _permissions(capability_id: str) -> tuple[str, ...]:
    if capability_id in RELEASE_IDS:
        return (_READ_PERMISSION, _ANALYZE_PERMISSION, _GOVERN_PERMISSION, _RELEASE_PERMISSION)
    if capability_id in GOVERN_IDS:
        return (_READ_PERMISSION, _ANALYZE_PERMISSION, _GOVERN_PERMISSION)
    if capability_id in ANALYZE_IDS:
        return (_READ_PERMISSION, _ANALYZE_PERMISSION)
    return (_READ_PERMISSION,)


def _value(record: Any, name: str) -> Any:
    return record.get(name) if isinstance(record, Mapping) else getattr(record, name, None)


def _projection(record: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        value = _value(record, field)
        if value is None and field == "domain":
            value = _value(record, "owner_domain")
        if value is None and field == "lifecycle":
            value = _value(record, "lifecycle_status")
        if value is None and field == "contract":
            descriptor = _value(record, "descriptor")
            if isinstance(descriptor, Mapping):
                value = descriptor.get("contract", descriptor)
        if value is not None:
            result[field] = _transport_value(value, depth=0) if not field.endswith("_gid") and field != "row_version" else str(value)
    return result


def _transport_value(value: Any, *, depth: int, max_items: int = 50) -> Any:
    """Keep nested catalog evidence bounded without flattening its meaning."""
    if depth >= 3:
        return str(value)[:512]
    if isinstance(value, Mapping):
        return {
            str(key): _transport_value(item, depth=depth + 1)
            for key, item in tuple(value.items())[:max_items]
            if isinstance(key, str) and len(key) <= 255
        }
    if isinstance(value, (list, tuple)):
        return [_transport_value(item, depth=depth + 1) for item in value[:max_items]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:512]


def _bounded_object(value: Any, *, max_properties: int = 50) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): _transport_value(item, depth=0)
        for key, item in tuple(value.items())[:max_properties]
        if isinstance(key, str) and len(key) <= 255
    }


def _bounded_collection(value: Any, *, max_items: int = 500) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_bounded_object(item) for item in value[:max_items] if isinstance(item, Mapping)]


def _release_projection(record: Any) -> dict[str, Any]:
    report_gid = _value(record, "release_report_gid") or _value(record, "report_gid")
    response: dict[str, Any] = {}
    if report_gid is not None:
        response["report_gid"] = str(report_gid)
    conclusion = _value(record, "conclusion")
    if conclusion is not None:
        response["conclusion"] = str(conclusion)
    blockers = _value(record, "blockers")
    if isinstance(blockers, (list, tuple)):
        response["blockers"] = [
            str(blocker) for blocker in blockers[:200]
            if 0 < len(str(blocker)) <= 255
        ]
    return response


def _safe_response(capability_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {"capability_id": capability_id, "status": str(result["status"])}
    if isinstance(result.get("data"), Mapping):
        response["data"] = _bounded_object(result["data"])
    for field in ("items", "nodes", "findings"):
        if field in result:
            response[field] = _bounded_collection(result[field])
    for field in (
        "capability_version_gid", "snapshot_gid", "run_gid", "proposal_gid",
        "waiver_gid", "release_report_gid",
    ):
        if result.get(field) is not None:
            response[field] = str(result[field])
    if capability_id == "base.capability_registry.search":
        response["items"] = [_projection(item, (
            "capability_id", "capability_version_gid", "capability_gid", "major_version",
            "owner_domain", "domain", "semantic_class", "business_effect", "lifecycle_status",
            "lifecycle", "descriptor_hash", "contract",
        )) for item in tuple(result.get("items", ()))[:200]]
    elif capability_id == "base.capability_registry.get" and result.get("item") is not None:
        response["item"] = _projection(result["item"], (
            "capability_id", "capability_version_gid", "capability_gid", "major_version",
            "owner_domain", "domain", "semantic_class", "business_effect", "lifecycle_status",
            "lifecycle", "descriptor_hash", "contract",
        ))
    elif capability_id == "base.capability_graph.get":
        snapshot_gid = result.get("snapshot_gid")
        if snapshot_gid is not None:
            response["snapshot"] = {"snapshot_gid": str(snapshot_gid)}
        for field in ("max_depth", "max_nodes"):
            if field in result:
                response[field] = int(result[field])
        response["nodes"] = [_projection(node, (
            "canonical_key", "owner_domain", "node_type", "source_path", "artifact_hash",
            "implementation_node_gid", "source_symbol", "http_method", "route_path", "metadata",
        )) for node in tuple(result.get("nodes", ()))[:500]]
        if result.get("bindings"):
            response["bindings"] = [_projection(binding, (
                "binding_gid", "capability_id", "major_version", "node_canonical_key",
                "binding_type", "binding_hash",
            )) for binding in tuple(result.get("bindings", ()))[:500]]
        if result.get("relations"):
            response["relations"] = [_projection(relation, (
                "relation_gid", "from_canonical_key", "to_canonical_key", "relation_type", "relation_hash",
            )) for relation in tuple(result.get("relations", ()))[:500]]
    elif capability_id == "base.capability_finding.search":
        response["findings"] = [_projection(finding, (
            "finding_gid", "code", "severity", "status", "fingerprint", "remediation_boundary",
            "subject_version_gids", "domains", "evidence",
        )) for finding in tuple(result.get("findings", result.get("items", ())))[:200]]
    elif capability_id in {"base.capability_analysis.run", "base.capability_test.run", "base.capability_analysis.get"}:
        run = result.get("run")
        if run is None and result.get("run_gid") is not None:
            run = {"run_gid": result.get("run_gid"), "snapshot_gid": result.get("snapshot_gid"), "kind": result.get("kind", "analysis"), "status": result.get("run_status", "queued")}
        if run is not None:
            response["run"] = _projection(run, ("run_gid", "snapshot_gid", "kind", "status"))
    elif capability_id == "base.capability_repair_prompt.generate" and result.get("snapshot_gid") is not None:
        response["snapshot"] = {"snapshot_gid": str(result["snapshot_gid"])}
    elif capability_id in {"base.capability_proposal.submit", "base.capability_review.decide"}:
        proposal = result.get("proposal")
        if proposal is not None:
            response["proposal"] = _projection(proposal, ("proposal_gid", "status", "row_version"))
    elif capability_id in {"base.capability_waiver.grant", "base.capability_waiver.revoke"}:
        waiver = result.get("waiver")
        if waiver is not None:
            response["waiver"] = _projection(waiver, ("waiver_gid", "status", "row_version"))
    elif capability_id == "base.capability_release_gate.evaluate":
        release = result.get("release")
        if release is not None:
            response["release"] = _release_projection(release)
    return response


def _handler(capability_id: str, service_port: Any) -> Callable[[dict[str, Any], object], dict[str, Any]]:
    def invoke(payload: dict[str, Any], context: object) -> dict[str, Any]:
        method = getattr(service_port, capability_id.replace(".", "_"), None) if service_port is not None else None
        if callable(method):
            result = method(payload, context)
            if not isinstance(result, Mapping):
                raise CapabilityBusinessError("provider_invalid_response", "provider_invalid_response")
            return _safe_response(capability_id, result)
        raise CapabilityBusinessError("provider_unavailable", "provider_unavailable", retryable=True)
    return invoke


def register_governance_capabilities(registry: Any, service_port: Any = None) -> None:
    """Register the extension only when explicitly requested by test bootstrap."""
    service = service_port
    with patch.dict(base_provider.INPUT_SCHEMAS, INPUT_SCHEMAS), patch.dict(
        base_provider.OUTPUT_SCHEMAS, OUTPUT_SCHEMAS,
    ):
        for capability_id in ALL_IDS:
            is_write = capability_id in WRITE_IDS
            base_provider.register_capability(registry, CapabilitySpec(
                owner="base",
                id=capability_id,
                version=1,
                description=f"Test-only governance operation {capability_id}.",
                use_when="The test-governance profile needs this governed capability contract.",
                do_not_use_when="The test-governance extension is not explicitly enabled.",
                risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
                confirmation="admin" if is_write else "none",
                idempotent=True,
                permissions=_permissions(capability_id),
                input_schema=INPUT_SCHEMAS[capability_id],
                output_schema=OUTPUT_SCHEMAS[capability_id],
                tags=("governance", "test-only", "write" if is_write else "read"),
            ), _handler(capability_id, service))


__all__ = ["register_governance_capabilities"]
