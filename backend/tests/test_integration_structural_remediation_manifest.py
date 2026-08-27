from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/build_integration_structural_web_remediation.py"
WEB_ROOT = ROOT.parent / "workmanship-web-capability-governance"


def _module():
    spec = importlib.util.spec_from_file_location("integration_structural_manifest", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_conserves_pinned_integration_scope_without_claiming_unsafe_migrations():
    """Breaks if an absent legacy route or non-equivalent provider is promoted."""
    payload = _module().build_manifest(WEB_ROOT)

    assert payload["counts"] == {
        "groups": 12,
        "occurrences": 12,
        "migrated_groups": 0,
        "migrated_occurrences": 0,
        "unresolved_groups": 12,
        "unresolved_occurrences": 12,
    }
    for entry in payload["entries"]:
        assert entry["final_disposition"] == "unresolved"
        assert entry["final_inventory_mapping"] == "unresolved"
        assert entry["old_route_evidence"]["handler_status"] == "absent"
        assert entry["candidate_capability"].startswith("integration.")
        assert entry["credential_handling"] == "legacy plaintext credentials are not represented; governed inputs accept only credential_ref"
        assert entry["external_outcome"] in {"not_applicable", "unknown_without_provider_equivalence"}


def test_manifest_binds_each_route_to_its_real_candidate_contract_and_service_evidence():
    """Breaks if a route is justified by a generic provider claim rather than its real evidence."""
    payload = _module().build_manifest(WEB_ROOT)
    entries = {(item["method"], item["normalized_route"]): item for item in payload["entries"]}

    for key, entry in entries.items():
        evidence = entry["candidate_evidence"]
        assert evidence["migration_decision"]["anchor"]["source_path"] == "backend/capability_v2/existing_capability_migration_decisions.py"
        assert evidence["service"]["anchor"]["source_path"] == "plugins/integration/integration_backend/application/service.py"
        assert evidence["contract"]["input_schema"]["additionalProperties"] is False
        assert evidence["contract"]["output_schema"]["additionalProperties"] is False
        assert entry["non_equivalence"]["input"]
        assert entry["non_equivalence"]["output"]
        assert entry["non_equivalence"]["side_effects"]
        assert entry["candidate_policy"]["confirmation"] in {"none", "user"}
        assert entry["candidate_policy"]["idempotency"] in {"none", "required"}
        assert entry["candidate_policy"]["external_side_effect"] in {"none", "connector_runtime", "asynchronous_sync"}
        if entry["candidate_policy"]["external_side_effect"] == "none":
            assert entry["candidate_policy"]["timeout"] == "not_applicable"
        else:
            assert entry["candidate_policy"]["timeout"] == "not declared by the public service"
        assert key in entries

    assert entries[("POST", "/api/ext-mappings/{dynamic}/import")]["candidate_policy"]["external_side_effect"] == "asynchronous_sync"
    assert entries[("GET", "/api/ext-datasources/{dynamic}/tables")]["candidate_policy"]["external_side_effect"] == "connector_runtime"


def test_manifest_validator_rejects_tampered_target_provider_and_final_inventory():
    """Breaks if a hand-edited manifest can bypass target, provider, or inventory evidence."""
    module = _module()
    payload = module.build_manifest(WEB_ROOT)
    assert module.validate_manifest_against_expected(payload, payload) == ()

    for field, value, reason in (
        ("candidate_capability", "base.identity.session.get@1", "candidate_target_mismatch"),
        ("provider_source_sha256", "sha256:" + "0" * 64, "provider_hash_mismatch"),
        ("final_inventory_mapping", "capability", "final_inventory_mismatch"),
    ):
        mutated = {**payload, "entries": [dict(item) for item in payload["entries"]]}
        mutated["entries"][0][field] = value
        assert reason in module.validate_manifest_against_expected(mutated, payload)


def test_manifest_validator_rejects_tampered_route_evidence_and_final_occurrence_identity():
    """Breaks if a service/decision edit or moved frontend occurrence can remain certified."""
    module = _module()
    payload = module.build_manifest(WEB_ROOT)

    mutations = (
        ("decision_evidence_mismatch", lambda item: item["candidate_evidence"]["migration_decision"]["anchor"].__setitem__("sha256", "0" * 64)),
        ("service_evidence_mismatch", lambda item: item["candidate_evidence"]["service"].__setitem__("source_sha256", "sha256:" + "0" * 64)),
        ("final_occurrence_mismatch", lambda item: item["final_occurrences"][0].__setitem__("line", 999)),
    )
    for reason, mutate in mutations:
        changed = json.loads(json.dumps(payload))
        mutate(changed["entries"][0])
        assert reason in module.validate_manifest_against_expected(changed, payload)
