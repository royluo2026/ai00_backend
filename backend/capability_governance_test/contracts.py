"""Closed, test-only contracts for the Capability Governance Center extension."""
from __future__ import annotations

from pathlib import Path

from backend.capability_v2.catalog import ProviderArtifact
from backend.capability_v2.provider_loader import hash_domain_artifact


READ_IDS = (
    "base.capability_registry.search",
    "base.capability_registry.get",
    "base.capability_governance.snapshot.summary.get",
    "base.capability_graph.get",
    "base.capability_finding.search",
    "base.capability_analysis.get",
    "base.capability_proposal.search",
    "base.capability_health.get",
    "base.capability_audit.search",
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
    "base.capability_release_gate.evaluate",
}
_LIMIT_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 200}
_OFFSET_SCHEMA = {"type": "integer", "minimum": 0, "maximum": 100000}
_DEPTH_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 4}
_NODES_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 500}
_COUNT_SCHEMA = {"type": "integer", "minimum": 0, "maximum": 100000}
_VERSION_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 255}
_SHA256_SCHEMA = {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$", "minLength": 71, "maxLength": 71}
_SMALL_STRING_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 255}
_BOOLEAN_SCHEMA = {"type": "boolean"}
_RESPONSE_GID_FIELDS = (
    "capability_version_gid", "snapshot_gid", "scan_run_gid", "run_gid", "proposal_gid",
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
        properties.update({"limit": _LIMIT_SCHEMA, "offset": _OFFSET_SCHEMA, "domain": _SMALL_STRING_SCHEMA})
    if capability_id == "base.capability_finding.search":
        properties.update({
            "limit": _LIMIT_SCHEMA, "offset": _OFFSET_SCHEMA, "domain": _SMALL_STRING_SCHEMA,
            "severity": _SMALL_STRING_SCHEMA, "status": _SMALL_STRING_SCHEMA,
            "reason_code": _SMALL_STRING_SCHEMA,
        })
    if capability_id == "base.capability_governance.snapshot.summary.get":
        properties.update({
            "snapshot_gid": GID_SCHEMA,
            "domains": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 11},
            "severity": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 4},
            "limit": _LIMIT_SCHEMA,
            "offset": _OFFSET_SCHEMA,
        })
    if capability_id == "base.capability_proposal.search":
        properties.update({
            "domain": _SMALL_STRING_SCHEMA,
            "stage": _SMALL_STRING_SCHEMA,
            "limit": _LIMIT_SCHEMA,
            "cursor": _SMALL_STRING_SCHEMA,
        })
    if capability_id == "base.capability_analysis.get":
        properties.update({
            "collection": {"type": "string", "enum": ["review_queue", "root_causes", "unbound_entries", "relations"]},
            "cursor": _SMALL_STRING_SCHEMA,
            "limit": _LIMIT_SCHEMA,
        })
    if capability_id == "base.capability_analysis.run":
        properties["web_revision"] = {
            "type": "string", "pattern": r"^[0-9a-f]{40}$", "minLength": 40, "maxLength": 40,
        }
    if capability_id == "base.capability_health.get":
        properties.update({
            "domains": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 11},
            "snapshot_gid": GID_SCHEMA,
        })
    if capability_id == "base.capability_audit.search":
        properties.update({
            "from": _SMALL_STRING_SCHEMA,
            "to": _SMALL_STRING_SCHEMA,
            "actor": _SMALL_STRING_SCHEMA,
            "capability": _SMALL_STRING_SCHEMA,
            "event_type": _SMALL_STRING_SCHEMA,
            "result": _SMALL_STRING_SCHEMA,
            "limit": _LIMIT_SCHEMA,
            "cursor": _SMALL_STRING_SCHEMA,
        })
    if capability_id == "base.capability_graph.get":
        properties.update({
            "max_depth": _DEPTH_SCHEMA, "max_nodes": _NODES_SCHEMA,
            "relation_offset": _OFFSET_SCHEMA, "relation_limit": _LIMIT_SCHEMA,
        })
        required = ("target_gid", "max_depth", "max_nodes")
    if capability_id in {
        "base.capability_registry.get", "base.capability_analysis.get",
        "base.capability_analysis.run", "base.capability_repair_prompt.generate",
        "base.capability_test.run",
    }:
        required = tuple(sorted(set(required) | {"target_gid"}))
    if capability_id == "base.capability_scan.run":
        properties["code_revision"] = _VERSION_SCHEMA
        required = tuple(sorted(set(required) | {"code_revision"}))
    if capability_id in {"base.capability_review.decide", "base.capability_waiver.revoke"}:
        properties.update({"row_version": _VERSION_SCHEMA, "expected_resource_version": _VERSION_SCHEMA})
    # These are intentionally explicit rather than accepting an open-ended
    # workflow payload.  The service has two proposal paths (detect a new
    # proposal or transition an existing one), so all fields used by either
    # path are declared here and the handler remains responsible for the
    # branch-specific required fields.
    if capability_id == "base.capability_proposal.submit":
        properties.update({
            "proposal_gid": GID_SCHEMA,
            "capability_id": STRING_SCHEMA,
            "capability_version_gid": GID_SCHEMA,
            "base_snapshot_gid": GID_SCHEMA,
            "previous_hash": _VERSION_SCHEMA,
            "proposed_descriptor_hash": _VERSION_SCHEMA,
            "definition_hash": _SHA256_SCHEMA,
            "evidence_hash": _VERSION_SCHEMA,
            "row_version": _VERSION_SCHEMA,
            "expected_resource_version": _VERSION_SCHEMA,
        })
    elif capability_id == "base.capability_review.decide":
        properties.update({
            "proposal_gid": GID_SCHEMA,
            "stage": _SMALL_STRING_SCHEMA,
            "definition_hash": _SHA256_SCHEMA,
            "decision": {"type": "string", "enum": ["approved", "rejected", "changes_requested"]},
            "decision_reason": {"type": "string", "minLength": 1, "maxLength": 2000},
        })
    elif capability_id == "base.capability_waiver.grant":
        properties.update({
            "finding_gid": GID_SCHEMA,
            "capability_version_gid": GID_SCHEMA,
            "scope": _SMALL_STRING_SCHEMA,
            "reason": STRING_SCHEMA,
            "code_hash": _VERSION_SCHEMA,
            "catalog_hash": _VERSION_SCHEMA,
            "evidence_hash": _VERSION_SCHEMA,
            "starts_at": _SMALL_STRING_SCHEMA,
            "expires_at": _SMALL_STRING_SCHEMA,
        })
    elif capability_id == "base.capability_waiver.revoke":
        properties.update({"waiver_gid": GID_SCHEMA, "revoked_at": _SMALL_STRING_SCHEMA})
    elif capability_id == "base.capability_release_gate.evaluate":
        properties.update({
            "code_revision": _VERSION_SCHEMA,
            "product_catalog_release_id": _VERSION_SCHEMA,
            "snapshot_gid": GID_SCHEMA,
            "test_run_gid": GID_SCHEMA,
            "test_status": _SMALL_STRING_SCHEMA,
            "available": _BOOLEAN_SCHEMA,
            "stale_evidence": _BOOLEAN_SCHEMA,
            "approvals_complete": _BOOLEAN_SCHEMA,
            "data_complete": _BOOLEAN_SCHEMA,
            "evidence_hash": _VERSION_SCHEMA,
            "findings": _BOUNDED_COLLECTION_SCHEMA,
            "waivers": _BOUNDED_COLLECTION_SCHEMA,
            "now": _SMALL_STRING_SCHEMA,
        })
    elif capability_id == "base.capability_repair_prompt.generate":
        # The prompt is generated from a bounded candidate finding and fixed
        # evidence/change-boundary maps.  No free-form model prompt or source
        # text crosses the Gateway.
        properties.update({
            "finding": _BOUNDED_OBJECT_SCHEMA,
            "evidence": _BOUNDED_OBJECT_SCHEMA,
            "boundary": _BOUNDED_OBJECT_SCHEMA,
            "request_id": _SMALL_STRING_SCHEMA,
        })
    return _closed(properties, required)


# These are deliberately projections, rather than record dumps.  They keep the
# agent transport closed while retaining the bounded result shapes returned by
# the governance service.
_BOUNDED_VALUE_SCHEMA = {"description": "Provider-validated bounded transport value."}
_BOUNDED_OBJECT_SCHEMA = {
    "type": "object", "maxProperties": 50,
    "additionalProperties": _BOUNDED_VALUE_SCHEMA,
}
_BOUNDED_COLLECTION_SCHEMA = {
    "type": "array", "maxItems": 500, "items": _BOUNDED_OBJECT_SCHEMA,
}
INPUT_SCHEMAS = {capability_id: _input_schema(capability_id) for capability_id in ALL_IDS}
_CONTRACT_SCHEMA = {"type": "object", "maxProperties": 50, "additionalProperties": _BOUNDED_VALUE_SCHEMA}
_ITEM_SCHEMA = _closed({
    "capability_id": STRING_SCHEMA, "capability_version_gid": GID_SCHEMA,
    "capability_gid": GID_SCHEMA, "major_version": {"type": "integer", "minimum": 1},
    "owner_domain": _SMALL_STRING_SCHEMA, "domain": _SMALL_STRING_SCHEMA,
    "semantic_class": _SMALL_STRING_SCHEMA, "business_effect": STRING_SCHEMA,
    "lifecycle_status": _SMALL_STRING_SCHEMA, "lifecycle": _SMALL_STRING_SCHEMA,
    "descriptor_hash": _VERSION_SCHEMA, "contract": _CONTRACT_SCHEMA,
}, ("capability_id", "capability_version_gid"))
_NODE_SCHEMA = _closed({
    "canonical_key": STRING_SCHEMA, "owner_domain": _SMALL_STRING_SCHEMA,
    "node_type": _SMALL_STRING_SCHEMA, "source_path": STRING_SCHEMA,
    "artifact_hash": _SMALL_STRING_SCHEMA,
    "implementation_node_gid": GID_SCHEMA, "source_symbol": _SMALL_STRING_SCHEMA,
    "http_method": _SMALL_STRING_SCHEMA, "route_path": STRING_SCHEMA,
    "metadata": _CONTRACT_SCHEMA,
})
_FINDING_SCHEMA = _closed({
    "code": _SMALL_STRING_SCHEMA, "severity": _SMALL_STRING_SCHEMA,
    "fingerprint": _SMALL_STRING_SCHEMA, "remediation_boundary": _SMALL_STRING_SCHEMA,
    "finding_gid": GID_SCHEMA, "status": _SMALL_STRING_SCHEMA,
    "reason_code": _SMALL_STRING_SCHEMA, "reason": STRING_SCHEMA,
    "subject_summary": STRING_SCHEMA,
    "root_cause_key": STRING_SCHEMA, "root_cause_label": STRING_SCHEMA,
    "root_cause_count": _COUNT_SCHEMA,
    "subject_version_gids": {"type": "array", "items": GID_SCHEMA, "maxItems": 20},
    "domains": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 20},
    "evidence": {"type": "array", "items": STRING_SCHEMA, "maxItems": 200},
})
_ROOT_CAUSE_SCHEMA = _closed({
    "root_cause_key": STRING_SCHEMA, "reason_code": _SMALL_STRING_SCHEMA,
    "root_cause_label": STRING_SCHEMA,
    "capabilities": {"type": "array", "items": STRING_SCHEMA, "maxItems": 20},
    "domains": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 11},
    "finding_count": _COUNT_SCHEMA, "severity": _SMALL_STRING_SCHEMA,
    "evidence_refs": {"type": "array", "items": STRING_SCHEMA, "maxItems": 20},
}, ("root_cause_key", "reason_code", "finding_count", "severity"))
_DOMAIN_SUMMARY_SCHEMA = _closed({
    "domain": _SMALL_STRING_SCHEMA, "finding_count": _COUNT_SCHEMA,
    "capability_count": _COUNT_SCHEMA,
}, ("domain", "finding_count", "capability_count"))
_BINDING_SCHEMA = _closed({
    "binding_gid": GID_SCHEMA, "capability_id": STRING_SCHEMA,
    "major_version": {"type": "integer", "minimum": 1},
    "node_canonical_key": STRING_SCHEMA, "binding_type": _SMALL_STRING_SCHEMA,
    "binding_hash": _VERSION_SCHEMA,
})
_RELATION_SCHEMA = _closed({
    "relation_gid": GID_SCHEMA, "from_canonical_key": STRING_SCHEMA,
    "to_canonical_key": STRING_SCHEMA, "relation_type": _SMALL_STRING_SCHEMA,
    "relation_hash": _VERSION_SCHEMA,
})
_RELATION_CANDIDATE_SCHEMA = _closed({
    "relation_candidate_gid": GID_SCHEMA, "candidate_hash": _VERSION_SCHEMA,
    "relation_type": _SMALL_STRING_SCHEMA, "source": _SMALL_STRING_SCHEMA,
    "capability_keys": {"type": "array", "items": STRING_SCHEMA, "maxItems": 20},
    "evidence": _closed({
        "entries": {"type": "array", "maxItems": 40, "items": _closed({
            "key": _SMALL_STRING_SCHEMA, "value_json": {"type": "string", "maxLength": 512},
            "value_hash": _VERSION_SCHEMA, "truncated": _BOOLEAN_SCHEMA,
        }, ("key", "value_json", "value_hash", "truncated"))},
    }, ("entries",)), "status": _SMALL_STRING_SCHEMA,
})
_BUSINESS_RELATION_SCHEMA = _closed({
    "candidate_hash": _VERSION_SCHEMA,
    "relation_type": _SMALL_STRING_SCHEMA,
    "source": {"type": "string", "enum": ["deterministic", "advisory"]},
    "capability_keys": {"type": "array", "items": STRING_SCHEMA, "maxItems": 20},
    "evidence": _RELATION_CANDIDATE_SCHEMA["properties"]["evidence"],
    "status": _SMALL_STRING_SCHEMA,
})
_BUSINESS_ROOT_CAUSE_SCHEMA = _closed({
    "root_cause_key": STRING_SCHEMA,
    "reason_code": _SMALL_STRING_SCHEMA,
    "capability_keys": {"type": "array", "items": STRING_SCHEMA, "maxItems": 20},
    "domains": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 11},
    "evidence_refs": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 1000}, "maxItems": 50},
    "finding_count": _COUNT_SCHEMA,
    "remediation_family": _SMALL_STRING_SCHEMA,
    "severity": _SMALL_STRING_SCHEMA,
})
_UNBOUND_ENTRY_SCHEMA = _closed({
    "entry_type": _SMALL_STRING_SCHEMA,
    "canonical_key": STRING_SCHEMA,
    "domain": _SMALL_STRING_SCHEMA,
    "location": {"type": "string", "minLength": 1, "maxLength": 1000},
    "source_path": {"type": "string", "minLength": 1, "maxLength": 1000},
    "source_symbol": STRING_SCHEMA,
    "http_method": {"type": ["string", "null"], "maxLength": 16},
    "route_path": {"type": ["string", "null"], "maxLength": 1000},
})
_REVIEW_QUEUE_SCHEMA = _closed({
    "capability_key": STRING_SCHEMA,
    "capability_id": _SMALL_STRING_SCHEMA,
    "major_version": {"type": "integer", "minimum": 1},
    "capability_version_gid": _VERSION_SCHEMA,
    "business_definition_hash": _SHA256_SCHEMA,
    "domain": _SMALL_STRING_SCHEMA,
    "owner_domains": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 11},
    "maturity": {"type": "string", "enum": [f"L{index}" for index in range(7)]},
    "priority": _COUNT_SCHEMA,
    "reason": _SMALL_STRING_SCHEMA,
    "governance_status": _SMALL_STRING_SCHEMA,
    "relationship_signals": {"type": "array", "items": _VERSION_SCHEMA, "maxItems": 200},
}, (
    "capability_key", "capability_id", "major_version", "capability_version_gid",
    "business_definition_hash", "domain", "owner_domains", "maturity", "priority",
    "reason", "governance_status", "relationship_signals",
))
_SOURCE_REVISIONS_SCHEMA = _closed({
    "backend": {"type": "string", "pattern": r"^[0-9a-f]{40}$", "minLength": 40, "maxLength": 40},
    "web": {"type": "string", "pattern": r"^[0-9a-f]{40}$", "minLength": 40, "maxLength": 40},
    "source": {"type": "string", "pattern": r"^[0-9a-f]{40}$", "minLength": 40, "maxLength": 40},
}, ("backend", "web", "source"))
_CATALOG_BINDING_SCHEMA = _closed({
    "catalog_release_id": _VERSION_SCHEMA,
    "catalog_hash": _VERSION_SCHEMA,
}, ("catalog_release_id", "catalog_hash"))
_MATURITY_COUNTS_SCHEMA = _closed({f"L{index}": _COUNT_SCHEMA for index in range(7)}, tuple(f"L{index}" for index in range(7)))
_LAYER_COUNTS_SCHEMA = _closed({layer: _COUNT_SCHEMA for layer in "ABCDEFG"}, tuple("ABCDEFG"))
_BUSINESS_AUDIT_SCHEMA = _closed({
    "snapshot_gid": GID_SCHEMA,
    "source_revisions": _SOURCE_REVISIONS_SCHEMA,
    "catalog_binding": _CATALOG_BINDING_SCHEMA,
    "finding_count": _COUNT_SCHEMA,
    "root_cause_group_count": _COUNT_SCHEMA,
    "affected_capability_count": _COUNT_SCHEMA,
    "affected_domains": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 11},
    "shared_remediation_family_count": _COUNT_SCHEMA,
    "shared_remediation_families": {"type": "array", "maxItems": 200, "items": _closed({
        "family": _SMALL_STRING_SCHEMA, "count": _COUNT_SCHEMA,
    }, ("family", "count"))},
    "maturity_counts": _MATURITY_COUNTS_SCHEMA,
    "layer_counts": _LAYER_COUNTS_SCHEMA,
    "machine_passed": _BOOLEAN_SCHEMA,
    "human_approved": _BOOLEAN_SCHEMA,
    "runtime_verified": _BOOLEAN_SCHEMA,
    "legacy_pending_review_count": _COUNT_SCHEMA,
    "root_cause_count": _COUNT_SCHEMA,
    "relation_count": _COUNT_SCHEMA,
    "unbound_entry_count": _COUNT_SCHEMA,
    "review_queue_count": _COUNT_SCHEMA,
    "collection": {"type": "string", "enum": ["review_queue", "root_causes", "unbound_entries", "relations"]},
    "limit": _LIMIT_SCHEMA,
    "next_cursor": {"type": ["string", "null"], "maxLength": 255},
    "root_causes": {"type": "array", "items": _BUSINESS_ROOT_CAUSE_SCHEMA, "maxItems": 200},
    "relations": {"type": "array", "items": _BUSINESS_RELATION_SCHEMA, "maxItems": 200},
    "unbound_entries": {"type": "array", "items": _UNBOUND_ENTRY_SCHEMA, "maxItems": 200},
    "review_queue": {"type": "array", "items": _REVIEW_QUEUE_SCHEMA, "maxItems": 200},
}, (
    "snapshot_gid", "source_revisions", "catalog_binding", "finding_count", "root_cause_group_count",
    "affected_capability_count", "affected_domains", "shared_remediation_family_count",
    "shared_remediation_families", "maturity_counts", "layer_counts", "machine_passed",
    "human_approved", "runtime_verified", "legacy_pending_review_count", "root_cause_count",
    "relation_count", "unbound_entry_count", "review_queue_count", "collection", "limit", "next_cursor",
))
_ANALYSIS_RESULT_SCHEMA = _closed({"business_audit": _BUSINESS_AUDIT_SCHEMA}, ("business_audit",))
_RUN_SCHEMA = _closed({
    "run_gid": GID_SCHEMA, "snapshot_gid": GID_SCHEMA, "kind": _SMALL_STRING_SCHEMA,
    "status": _SMALL_STRING_SCHEMA, "result": _ANALYSIS_RESULT_SCHEMA,
}, ("run_gid", "snapshot_gid", "kind", "status"))
_SNAPSHOT_SCHEMA = _closed({"snapshot_gid": GID_SCHEMA, "snapshot_hash": _SMALL_STRING_SCHEMA})
_PROMPT_SCHEMA = _closed({
    "prompt_hash": _VERSION_SCHEMA,
    "redacted_summary": {"type": "string", "minLength": 1, "maxLength": 4000},
}, ("prompt_hash", "redacted_summary"))
_PROPOSAL_SCHEMA = _closed({
    "proposal_gid": GID_SCHEMA, "status": _SMALL_STRING_SCHEMA,
    "row_version": _VERSION_SCHEMA,
    "business_definition_hash": _SHA256_SCHEMA,
    "review_type": {"type": "string", "enum": ["business_definition"]},
    "proposed_descriptor_hash_label": {"type": "string", "enum": ["business_definition_hash"]},
}, ("proposal_gid", "status", "row_version"))
_PROPOSAL_ITEM_SCHEMA = _closed({
    "proposal_gid": GID_SCHEMA,
    "capability_id": STRING_SCHEMA,
    "major_version": {"type": "integer", "minimum": 1},
    "capability_version_gid": GID_SCHEMA,
    "base_snapshot_gid": GID_SCHEMA,
    "previous_hash": _VERSION_SCHEMA,
    "proposed_descriptor_hash": _VERSION_SCHEMA,
    "proposed_descriptor_hash_label": {"type": "string", "enum": ["descriptor_hash", "business_definition_hash"]},
    "business_definition_hash": _SHA256_SCHEMA,
    "review_type": {"type": "string", "enum": ["standard", "business_definition"]},
    "evidence_hash": _VERSION_SCHEMA,
    "submitted_by_gid": _SMALL_STRING_SCHEMA,
    "status": _SMALL_STRING_SCHEMA,
    "row_version": _VERSION_SCHEMA,
    "domain": _SMALL_STRING_SCHEMA,
    "review_total": _COUNT_SCHEMA,
    "reviews_truncated": _BOOLEAN_SCHEMA,
    "reviews": {"type": "array", "maxItems": 20, "items": _closed({
        "review_gid": GID_SCHEMA,
        "proposal_gid": GID_SCHEMA,
        "capability_key": STRING_SCHEMA,
        "base_snapshot_gid": GID_SCHEMA,
        "definition_hash": _SHA256_SCHEMA,
        "review_stage": _SMALL_STRING_SCHEMA,
        "decision": _SMALL_STRING_SCHEMA,
        "reviewer_gid": _SMALL_STRING_SCHEMA,
        "decision_reason": {"type": "string", "minLength": 1, "maxLength": 2000},
        "review_type": _SMALL_STRING_SCHEMA,
    })},
    "review_evidence": _closed({
        "capability_key": STRING_SCHEMA,
        "major_version": {"type": "integer", "minimum": 1},
        "capability_version_gid": GID_SCHEMA,
        "business_effect": {"type": "string", "maxLength": 4000},
        "business_acceptance_criteria": {"type": "array", "items": {"type": "string", "maxLength": 4000}, "maxItems": 50},
        "accepted_examples": {"type": "array", "items": {"type": "string", "maxLength": 4000}, "maxItems": 50},
        "rejected_examples": {"type": "array", "items": {"type": "string", "maxLength": 4000}, "maxItems": 50},
        "owner_domains": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 11},
        "business_rules": {"type": "array", "maxItems": 50, "items": _closed({
            "rule_id": _SMALL_STRING_SCHEMA,
            "version": {"type": "integer", "minimum": 1},
            "statement": {"type": "string", "maxLength": 4000},
            "applies_when": {"type": "string", "maxLength": 4000},
            "enforcement_ref": {"type": "string", "maxLength": 1000},
            "error_code": _SMALL_STRING_SCHEMA,
            "test_refs": {"type": "array", "items": {"type": "string", "maxLength": 1000}, "maxItems": 50},
            "machine_constraints": _closed({
                "field": _SMALL_STRING_SCHEMA, "unit": _SMALL_STRING_SCHEMA,
                "minimum": {"type": ["integer", "number", "null"]},
                "maximum": {"type": ["integer", "number", "null"]},
                "minimum_inclusive": _BOOLEAN_SCHEMA, "maximum_inclusive": _BOOLEAN_SCHEMA,
            }),
        })},
        "business_maturity": _closed({
            "level": {"type": "string", "enum": [f"L{index}" for index in range(7)]},
            "reason_codes": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 50},
        }),
        "definition_hash": _SHA256_SCHEMA,
        "evidence": _closed({
            "redacted": _BOOLEAN_SCHEMA,
            "snapshot_gid": GID_SCHEMA,
            "source_revision": {"type": "string", "maxLength": 255},
            "catalog_release_id": {"type": "string", "maxLength": 255},
        }),
        "deterministic_relation_candidates": {"type": "array", "items": _BUSINESS_RELATION_SCHEMA, "maxItems": 20},
        "ai_advisory_relation_candidates": {"type": "array", "items": _BUSINESS_RELATION_SCHEMA, "maxItems": 20},
    }),
})
_HEALTH_ITEM_SCHEMA = _closed({
    "domain": _SMALL_STRING_SCHEMA,
    "status": {"type": "string", "enum": ["healthy", "attention", "blocked", "unverified"]},
    "snapshot_gid": GID_SCHEMA,
    "checked_at": _SMALL_STRING_SCHEMA,
    "entry_count": {"type": "integer", "minimum": 0, "maximum": 20000},
    # The Finding center is paged at 200, but health reports the complete
    # bounded total for a domain and may therefore exceed one page.
    "finding_count": {"type": "integer", "minimum": 0, "maximum": 5000},
    "severities": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 20},
    "reason": _SMALL_STRING_SCHEMA,
})
_AUDIT_DETAIL_SCHEMA = _closed({
    "status": _SMALL_STRING_SCHEMA,
    "capability_id": _SMALL_STRING_SCHEMA,
    "before_status": _SMALL_STRING_SCHEMA,
    "after_status": _SMALL_STRING_SCHEMA,
    "finding_gid": GID_SCHEMA,
    "conclusion": _SMALL_STRING_SCHEMA,
    "blockers": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 200},
    "prompt_hash": _VERSION_SCHEMA,
    "finding_count": {"type": "integer", "minimum": 0, "maximum": 5000},
    "finding_types": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 20},
    "reason_code": {"type": ["string", "null"], "enum": ["timeout", "failed", "invalid_output", "dependency_unavailable", None]},
})
_AUDIT_ITEM_SCHEMA = _closed({
    "audit_event_gid": GID_SCHEMA,
    "operation": _SMALL_STRING_SCHEMA,
    "capability_id": _SMALL_STRING_SCHEMA,
    "event_type": _SMALL_STRING_SCHEMA,
    "actor_gid": _SMALL_STRING_SCHEMA,
    "request_gid": _SMALL_STRING_SCHEMA,
    "status": _SMALL_STRING_SCHEMA,
    "occurred_at": _SMALL_STRING_SCHEMA,
    "detail": _AUDIT_DETAIL_SCHEMA,
})
_QUERY_META_SCHEMA = _closed({
    "available": _BOOLEAN_SCHEMA,
    "checked_at": _SMALL_STRING_SCHEMA,
    "next_cursor": {"type": ["string", "null"]},
    "snapshot_gid": GID_SCHEMA,
}, ("available", "checked_at"))
_WAIVER_SCHEMA = _closed({
    "waiver_gid": GID_SCHEMA, "status": _SMALL_STRING_SCHEMA,
    "row_version": _VERSION_SCHEMA,
}, ("waiver_gid", "status", "row_version"))
_RELEASE_SCHEMA = _closed({
    "report_gid": GID_SCHEMA, "conclusion": {"type": "string", "enum": ["pass", "fail", "expired"]},
    "blockers": {"type": "array", "items": _SMALL_STRING_SCHEMA, "maxItems": 200},
}, ("report_gid", "conclusion", "blockers"))
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
        properties.update({
            "total": _COUNT_SCHEMA,
            "product_capability_total": _COUNT_SCHEMA,
            "governance_extension_capability_total": _COUNT_SCHEMA,
            "limit": _LIMIT_SCHEMA,
            "offset": _COUNT_SCHEMA,
        })
    elif capability_id == "base.capability_governance.snapshot.summary.get":
        properties.update({
            "catalog_release": STRING_SCHEMA,
            "snapshot_hash": _SMALL_STRING_SCHEMA,
            "capability_total": _COUNT_SCHEMA,
            "finding_total": _COUNT_SCHEMA,
            "root_cause_total": _COUNT_SCHEMA,
            "blocking_total": _COUNT_SCHEMA,
            "critical_total": _COUNT_SCHEMA,
            "limit": _LIMIT_SCHEMA,
            "offset": _COUNT_SCHEMA,
            "next_offset": {"type": ["integer", "null"], "minimum": 0, "maximum": 100000},
            "root_causes": {"type": "array", "items": _ROOT_CAUSE_SCHEMA, "maxItems": 200},
            "domain_summaries": {"type": "array", "items": _DOMAIN_SUMMARY_SCHEMA, "maxItems": 11},
        })
    elif capability_id == "base.capability_registry.get":
        properties["item"] = _ITEM_SCHEMA
    elif capability_id == "base.capability_graph.get":
        properties.update({
            "snapshot": _SNAPSHOT_SCHEMA,
            "max_depth": _DEPTH_SCHEMA,
            "max_nodes": _NODES_SCHEMA,
            "nodes": {"type": "array", "items": _NODE_SCHEMA, "maxItems": 500},
            "bindings": {"type": "array", "items": _BINDING_SCHEMA, "maxItems": 500},
            "relations": {"type": "array", "items": _RELATION_SCHEMA, "maxItems": 500},
            "relation_candidates": {"type": "array", "items": _RELATION_CANDIDATE_SCHEMA, "maxItems": 500},
            "relation_total": _COUNT_SCHEMA, "relation_offset": _COUNT_SCHEMA,
            "relation_limit": _LIMIT_SCHEMA,
        })
    elif capability_id == "base.capability_finding.search":
        properties["findings"] = {"type": "array", "items": _FINDING_SCHEMA, "maxItems": 200}
        properties["total"] = _COUNT_SCHEMA
        properties["offset"] = _COUNT_SCHEMA
        properties["root_cause_total"] = _COUNT_SCHEMA
    elif capability_id == "base.capability_proposal.search":
        properties["items"] = {"type": "array", "items": _PROPOSAL_ITEM_SCHEMA, "maxItems": 200}
        properties["data"] = _QUERY_META_SCHEMA
    elif capability_id == "base.capability_health.get":
        properties["items"] = {"type": "array", "items": _HEALTH_ITEM_SCHEMA, "maxItems": 11}
        properties["data"] = _QUERY_META_SCHEMA
    elif capability_id == "base.capability_audit.search":
        properties["items"] = {"type": "array", "items": _AUDIT_ITEM_SCHEMA, "maxItems": 200}
        properties["data"] = _QUERY_META_SCHEMA
    elif capability_id in {"base.capability_analysis.run", "base.capability_test.run", "base.capability_analysis.get"}:
        properties["run"] = _RUN_SCHEMA
    elif capability_id == "base.capability_repair_prompt.generate":
        properties.update({
            "snapshot": _SNAPSHOT_SCHEMA,
            "prompt_status": {"type": "string", "enum": ["input_required", "generated"]},
            "prompt": _PROMPT_SCHEMA,
        })
    elif capability_id in {"base.capability_proposal.submit", "base.capability_review.decide"}:
        properties["proposal"] = _PROPOSAL_SCHEMA
    elif capability_id in {"base.capability_waiver.grant", "base.capability_waiver.revoke"}:
        properties["waiver"] = _WAIVER_SCHEMA
    elif capability_id == "base.capability_release_gate.evaluate":
        properties["release"] = _RELEASE_SCHEMA
    elif capability_id == "base.capability_scan.run":
        properties["scan_status"] = {"type": "string", "enum": ["completed", "blocked"]}
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
