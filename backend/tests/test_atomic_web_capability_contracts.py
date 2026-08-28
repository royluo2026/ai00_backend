from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/governance/atomic-web-capability-contracts.json"
CATALOG = ROOT / "docs/capabilities/catalog.v2.json"
SAFE_CAPABILITIES = {
    "base.authorization.grant.list",
    "base.authorization.grant.create",
    "base.authorization.grant.revoke",
    "base.notification.preference.atomic.get",
    "base.notification.preference.atomic.update",
    "base.identity.directory.feishu.sync",
    "base.plugin.installed.list",
    "base.identity.user.search",
    "base.organization.team.directory.list",
    "base.team.directory.list",
    "base.self_annotation.batch.get",
    "base.self_annotation.record.get",
    "base.self_annotation.search",
    "base.self_annotation.change.apply",
    "base.identity.session.profile.get",
    "base.identity.admin_user.list",
    "base.identity.role.assign.atomic",
    "base.saved_view.search",
    "base.saved_view.create",
    "base.saved_view.update",
    "base.saved_view.copy",
    "base.saved_view.delete",
}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_conserves_the_reviewed_48_groups_and_71_occurrences():
    payload = _manifest()
    entries = payload["entries"]
    assert len(entries) == 48
    assert sum(len(entry["occurrences"]) for entry in entries) == 71
    assert payload["counts_by_owner"] == {
        "agent": {"groups": 4, "occurrences": 5},
        "base": {"groups": 24, "occurrences": 44},
        "craft": {"groups": 7, "occurrences": 9},
        "integration": {"groups": 12, "occurrences": 12},
        "project_management": {"groups": 1, "occurrences": 1},
    }


def test_every_implemented_contract_is_closed_bounded_and_policy_complete():
    implemented = [entry for entry in _manifest()["entries"] if entry["final_disposition"] == "migrated"]
    assert implemented
    for entry in implemented:
        assert entry["capability_id"].startswith(entry["owner_prefix"] + ".")
        assert entry["major_version"] == 1
        assert entry["provider_anchor"]
        provider_path = ROOT / entry["provider_anchor"].partition(":")[0]
        assert entry["provider_source_sha256"] == "sha256:" + hashlib.sha256(provider_path.read_bytes()).hexdigest()
        assert entry["authorization_policy"]
        assert entry["confirmation_policy"] in {"none", "user", "admin"}
        assert entry["idempotency_policy"] in {"none", "required"}
        assert entry["atomicity_class"] in {"read", "single_transaction", "external"}
        for schema_name in ("input_schema", "output_schema"):
            schema = entry[schema_name]
            assert schema["type"] == "object"
            assert schema["additionalProperties"] is False


def test_only_service_backed_contracts_remain_migrated_with_typed_outputs():
    implemented = [entry for entry in _manifest()["entries"] if entry["final_disposition"] == "migrated"]
    assert {entry["capability_id"] for entry in implemented} == SAFE_CAPABILITIES
    for entry in implemented:
        schema = entry["output_schema"]
        assert "result_json" not in schema["properties"]
        assert schema["properties"]
        validate_payload(schema, entry["example_output"], label="output")
        with pytest.raises(ValueError):
            validate_payload(schema, {"unexpected": True}, label="output")


def test_all_migrated_specs_register_and_use_production_validation():
    from backend.base.web_atomic import register_atomic_web_capabilities as register_base

    registry = CapabilityRegistry()
    register_base(registry)
    entries = [entry for entry in _manifest()["entries"] if entry["final_disposition"] == "migrated"]
    for entry in entries:
        if entry["owner_domain"] == "project_management":
            continue
        item = registry.get(entry["capability_id"])
        assert item.spec.owner == entry["owner_domain"]
        validate_payload(dict(item.spec.input_schema), entry["example_input"])
        validate_payload(dict(item.spec.output_schema), entry["example_output"])
        with pytest.raises(ValueError, match="unknown field"):
            validate_payload(dict(item.spec.input_schema), {**entry["example_input"], "__unknown": True})


def test_production_catalog_enforces_atomic_schemas_and_gateway_policies():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    descriptors = {item["id"]: item for item in catalog["capabilities"]}
    for entry in (item for item in _manifest()["entries"] if item["final_disposition"] == "migrated"):
        descriptor = descriptors[entry["capability_id"]]
        assert descriptor["lifecycle_status"] == "stable"
        assert descriptor["owner_domain"] == entry["owner_domain"]
        assert descriptor["confirmation_policy"] == entry["confirmation_policy"]
        assert descriptor["idempotency_policy"] == entry["idempotency_policy"]
        assert entry["authorization_policy"] in descriptor["authorization_policy"]
        validate_payload(descriptor["input_schema"], entry["example_input"])
        validate_payload(descriptor["output_schema"], entry["example_output"])
        with pytest.raises(ValueError, match="unknown field"):
            validate_payload(descriptor["input_schema"], {**entry["example_input"], "__unknown": True})


def test_reclassifications_are_evidence_backed_not_fake_successes():
    reclassified = [entry for entry in _manifest()["entries"] if entry["final_disposition"] != "migrated"]
    assert reclassified
    for entry in reclassified:
        assert entry["final_disposition"] in {"retirement_review_required", "domain_design_required"}
        assert entry["reclassification_reason"]
        assert entry["provider_anchor"]
        assert not entry.get("capability_id")
