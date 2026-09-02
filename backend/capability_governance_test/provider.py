"""Test-only Base registration for governance catalog descriptors."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable
from unittest.mock import patch
import hashlib
import json

from backend.base import provider as base_provider
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityRisk, CapabilitySpec

from .contracts import ALL_IDS, ANALYZE_IDS, GOVERN_IDS, INPUT_SCHEMAS, OUTPUT_SCHEMAS, RELEASE_IDS, WRITE_IDS
from .redaction import redact


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
        if value is None and field == "review_type":
            value = _value(record, "review_kind")
        if value is None and field == "proposed_descriptor_hash_label":
            value = "business_definition_hash" if _value(record, "review_kind") == "business_definition" else None
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


def _string_list(value: Any, *, maximum: int, item_length: int = 1000) -> list[str]:
    if not isinstance(value, (tuple, list)):
        return []
    return [str(item)[:item_length] for item in value[:maximum] if str(item)]


def _evidence_projection(value: Any) -> dict[str, Any]:
    entries = []
    if isinstance(value, Mapping):
        for key, item in sorted(redact(dict(value)).items(), key=lambda pair: str(pair[0]))[:40]:
            encoded = json.dumps(_transport_value(item, depth=0), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
            entries.append({
                "key": str(key)[:255], "value_json": encoded[:512],
                "value_hash": "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                "truncated": len(encoded) > 512,
            })
    return {"entries": entries}


def _business_relation_projection(record: Any) -> dict[str, Any]:
    return {
        **_projection(record, ("candidate_hash", "relation_type", "source", "status")),
        "capability_keys": _string_list(_value(record, "capability_keys"), maximum=20, item_length=255),
        "evidence": _evidence_projection(_value(record, "evidence")),
    }


def _business_rule_projection(record: Any) -> dict[str, Any]:
    result = _projection(record, (
        "rule_id", "version", "statement", "applies_when", "enforcement_ref", "error_code",
    ))
    result["test_refs"] = _string_list(_value(record, "test_refs"), maximum=50)
    constraints = _value(record, "machine_constraints")
    if isinstance(constraints, Mapping):
        result["machine_constraints"] = _projection(constraints, (
            "field", "unit", "minimum", "maximum", "minimum_inclusive", "maximum_inclusive",
        ))
    return result


def _review_projection(record: Any) -> dict[str, Any]:
    return _projection(record, (
        "review_gid", "proposal_gid", "capability_key", "base_snapshot_gid", "definition_hash",
        "review_stage", "decision", "reviewer_gid", "decision_reason", "review_type",
    ))


def _review_evidence_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result = _projection(value, (
        "capability_key", "major_version", "capability_version_gid", "business_effect", "definition_hash",
    ))
    result["business_acceptance_criteria"] = _string_list(value.get("business_acceptance_criteria"), maximum=50, item_length=4000)
    result["accepted_examples"] = _string_list(value.get("accepted_examples"), maximum=50, item_length=4000)
    result["rejected_examples"] = _string_list(value.get("rejected_examples"), maximum=50, item_length=4000)
    result["owner_domains"] = _string_list(value.get("owner_domains"), maximum=11, item_length=64)
    rules = value.get("business_rules")
    result["business_rules"] = [
        _business_rule_projection(item) for item in tuple(rules or ())[:50] if isinstance(item, Mapping)
    ]
    maturity = value.get("business_maturity")
    if isinstance(maturity, Mapping):
        result["business_maturity"] = {
            **_projection(maturity, ("level",)),
            "reason_codes": _string_list(maturity.get("reason_codes"), maximum=50, item_length=255),
        }
    evidence = value.get("evidence")
    if isinstance(evidence, Mapping):
        result["evidence"] = _projection(evidence, (
            "redacted", "snapshot_gid", "source_revision", "catalog_release_id",
        ))
    for field in ("deterministic_relation_candidates", "ai_advisory_relation_candidates"):
        relations = value.get(field)
        result[field] = [
            _business_relation_projection(item)
            for item in tuple(relations or ())[:20] if isinstance(item, Mapping)
        ]
    return result


def _business_audit_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CapabilityBusinessError("provider_invalid_response", "provider_invalid_response")
    scalar_fields = {
        "snapshot_gid", "source_revisions", "catalog_binding", "finding_count", "root_cause_group_count",
        "affected_capability_count", "affected_domains", "shared_remediation_family_count",
        "shared_remediation_families", "maturity_counts", "layer_counts", "machine_passed",
        "human_approved", "runtime_verified", "legacy_pending_review_count", "root_cause_count",
        "relation_count", "unbound_entry_count", "review_queue_count", "collection", "limit", "next_cursor",
    }
    collections = {"root_causes", "relations", "unbound_entries", "review_queue"}
    collection = value.get("collection")
    if (
        collection not in collections
        or set(value) - scalar_fields - collections
        or collection not in value
        or (set(value) & collections) != {collection}
        or set(value.get("source_revisions", {})) != {"backend", "web", "source"}
    ):
        raise CapabilityBusinessError("provider_invalid_response", "provider_invalid_response")
    binding = value.get("catalog_binding")
    if not isinstance(binding, Mapping) or set(binding) != {"catalog_release_id", "catalog_hash"}:
        raise CapabilityBusinessError("provider_invalid_response", "provider_invalid_response")
    result = _projection(value, (
        "snapshot_gid", "collection", "limit", "finding_count", "root_cause_group_count",
        "affected_capability_count", "shared_remediation_family_count", "machine_passed",
        "human_approved", "runtime_verified", "legacy_pending_review_count", "root_cause_count",
        "relation_count", "unbound_entry_count", "review_queue_count",
    ))
    result["source_revisions"] = _projection(value.get("source_revisions", {}), ("backend", "web", "source"))
    result["catalog_binding"] = _projection(
        value["catalog_binding"], ("catalog_release_id", "catalog_hash"),
    )
    result["affected_domains"] = _string_list(value.get("affected_domains"), maximum=11, item_length=64)
    result["maturity_counts"] = _projection(value.get("maturity_counts", {}), tuple(f"L{index}" for index in range(7)))
    result["layer_counts"] = _projection(value.get("layer_counts", {}), tuple("ABCDEFG"))
    families = value.get("shared_remediation_families")
    result["shared_remediation_families"] = [{
        "family": str(key)[:255], "count": min(max(0, int(item)), 100000),
    }
        for key, item in tuple(families.items())[:200]
    ] if isinstance(families, Mapping) else []
    cursor = value.get("next_cursor")
    result["next_cursor"] = None if cursor is None else str(cursor)[:255]
    if "review_queue" in value:
        result["review_queue"] = [_projection(item, (
            "capability_key", "domain", "maturity", "priority", "reason",
        )) for item in tuple(value.get("review_queue", ()))[:200]]
    if "root_causes" in value:
        result["root_causes"] = [{
            **_projection(item, (
                "root_cause_key", "reason_code", "finding_count", "remediation_family", "severity",
            )),
            "capability_keys": _string_list(_value(item, "capability_keys"), maximum=20, item_length=255),
            "domains": _string_list(_value(item, "domains"), maximum=11, item_length=64),
            "evidence_refs": _string_list(_value(item, "evidence_refs"), maximum=50),
        } for item in tuple(value.get("root_causes", ()))[:200]]
    if "unbound_entries" in value:
        result["unbound_entries"] = [_projection(item, (
            "entry_type", "canonical_key", "domain", "location", "source_path", "source_symbol",
            "http_method", "route_path",
        )) for item in tuple(value.get("unbound_entries", ()))[:200]]
    if "relations" in value:
        result["relations"] = [
            _business_relation_projection(item) for item in tuple(value.get("relations", ()))[:200]
        ]
    return result


def _safe_response(capability_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {"capability_id": capability_id, "status": str(result["status"])}
    if isinstance(result.get("data"), Mapping):
        response["data"] = _bounded_object(result["data"])
    for field in ("items", "nodes", "findings", "root_causes", "domain_summaries"):
        if field in result:
            response[field] = _bounded_collection(result[field])
    for field in (
        "capability_version_gid", "snapshot_gid", "scan_run_gid", "run_gid", "proposal_gid",
        "waiver_gid", "release_report_gid",
    ):
        if result.get(field) is not None:
            response[field] = str(result[field])
    for field in (
        "total", "product_capability_total", "governance_extension_capability_total",
        "offset", "root_cause_total", "capability_total", "finding_total", "blocking_total",
        "critical_total", "limit",
    ):
        if result.get(field) is not None:
            try:
                response[field] = min(max(0, int(result[field])), 100000)
            except (TypeError, ValueError):
                pass
    if capability_id == "base.capability_scan.run" and result.get("scan_status") in {"completed", "blocked"}:
        response["scan_status"] = str(result["scan_status"])
    if capability_id == "base.capability_registry.search":
        response["items"] = [_projection(item, (
            "capability_id", "capability_version_gid", "capability_gid", "major_version",
            "owner_domain", "domain", "semantic_class", "business_effect", "lifecycle_status",
            "lifecycle", "descriptor_hash", "contract",
        )) for item in tuple(result.get("items", ()))[:200]]
    elif capability_id == "base.capability_governance.snapshot.summary.get":
        response["root_causes"] = [_projection(item, (
            "root_cause_key", "reason_code", "root_cause_label", "capabilities", "domains",
            "finding_count", "severity", "evidence_refs",
        )) for item in tuple(result.get("root_causes", ()))[:200]]
        response["domain_summaries"] = [_projection(item, (
            "domain", "finding_count", "capability_count",
        )) for item in tuple(result.get("domain_summaries", ()))[:11]]
        if "next_offset" in result:
            response["next_offset"] = result.get("next_offset")
        for field in ("catalog_release", "snapshot_hash"):
            if result.get(field) is not None:
                response[field] = str(result[field])
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
        response["relation_candidates"] = [_relation_candidate_projection(item) for item in tuple(result.get("relation_candidates", ()))[:200]]
        for field in ("relation_total", "relation_offset", "relation_limit"):
            if result.get(field) is not None:
                response[field] = min(max(0, int(result[field])), 100000)
    elif capability_id == "base.capability_finding.search":
        response["findings"] = [_projection(finding, (
            "finding_gid", "code", "severity", "status", "fingerprint", "remediation_boundary",
            "subject_version_gids", "domains", "evidence", "reason_code", "reason", "subject_summary",
            "root_cause_key", "root_cause_label", "root_cause_count",
        )) for finding in tuple(result.get("findings", result.get("items", ())))[:200]]
    elif capability_id == "base.capability_proposal.search":
        response["items"] = []
        for proposal in tuple(result.get("items", ()))[:200]:
            item = _projection(proposal, (
                "proposal_gid", "capability_id", "capability_version_gid", "base_snapshot_gid",
                "previous_hash", "proposed_descriptor_hash", "proposed_descriptor_hash_label",
                "business_definition_hash", "review_type", "evidence_hash", "submitted_by_gid",
                "status", "row_version", "domain", "major_version", "review_total", "reviews_truncated",
            ))
            item["reviews"] = [
                _review_projection(review) for review in tuple(_value(proposal, "reviews") or ())[:20]
            ]
            item["review_evidence"] = _review_evidence_projection(_value(proposal, "review_evidence"))
            response["items"].append(item)
    elif capability_id == "base.capability_health.get":
        response["items"] = [_projection(item, (
            "domain", "status", "snapshot_gid", "checked_at", "entry_count", "finding_count",
            "severities", "reason",
        )) for item in tuple(result.get("items", ()))[:11]]
    elif capability_id == "base.capability_audit.search":
        response["items"] = [_projection(item, (
            "audit_event_gid", "operation", "capability_id", "event_type", "actor_gid",
            "request_gid", "status", "occurred_at", "detail",
        )) for item in tuple(result.get("items", ()))[:200]]
    elif capability_id in {"base.capability_analysis.run", "base.capability_test.run", "base.capability_analysis.get"}:
        run = result.get("run")
        if run is None and result.get("run_gid") is not None:
            run = {"run_gid": result.get("run_gid"), "snapshot_gid": result.get("snapshot_gid"), "kind": result.get("kind", "analysis"), "status": result.get("run_status", "queued")}
        if run is not None:
            response["run"] = _projection(run, ("run_gid", "snapshot_gid", "kind", "status"))
            run_result = _value(run, "result")
            if isinstance(run_result, Mapping) and set(run_result) != {"business_audit"}:
                raise CapabilityBusinessError("provider_invalid_response", "provider_invalid_response")
            if isinstance(run_result, Mapping) and isinstance(run_result.get("business_audit"), Mapping):
                response["run"]["result"] = {
                    "business_audit": _business_audit_projection(run_result["business_audit"]),
                }
    elif capability_id == "base.capability_repair_prompt.generate":
        if result.get("snapshot_gid") is not None:
            response["snapshot"] = {
                "snapshot_gid": str(result["snapshot_gid"]),
                **({"snapshot_hash": str(result["snapshot_hash"])} if result.get("snapshot_hash") else {}),
            }
        if result.get("prompt_status") is not None:
            response["prompt_status"] = str(result["prompt_status"])
        prompt = result.get("prompt")
        if isinstance(prompt, Mapping):
            response["prompt"] = _projection(prompt, ("prompt_hash", "redacted_summary"))
    elif capability_id in {"base.capability_proposal.submit", "base.capability_review.decide"}:
        proposal = result.get("proposal")
        if proposal is not None:
            fields = ("proposal_gid", "status", "row_version")
            if _value(proposal, "review_kind") == "business_definition":
                fields += ("business_definition_hash", "review_type", "proposed_descriptor_hash_label")
            response["proposal"] = _projection(proposal, fields)
    elif capability_id in {"base.capability_waiver.grant", "base.capability_waiver.revoke"}:
        waiver = result.get("waiver")
        if waiver is not None:
            response["waiver"] = _projection(waiver, ("waiver_gid", "status", "row_version"))
    elif capability_id == "base.capability_release_gate.evaluate":
        release = result.get("release")
        if release is not None:
            response["release"] = _release_projection(release)
    return response


def _relation_candidate_projection(record: Any) -> dict[str, Any]:
    return {
        **_projection(record, (
            "relation_candidate_gid", "candidate_hash", "relation_type", "source", "capability_keys", "status",
        )),
        "evidence": _evidence_projection(_value(record, "evidence")),
    }


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
