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


def test_manifest_closes_exact_integration_scope_from_immutable_frontend_source():
    """Breaks if one historical occurrence is not replaced by its exact governed call."""
    payload = _module().build_manifest(WEB_ROOT)

    assert payload["counts"] == {
        "groups": 12,
        "occurrences": 12,
        "migrated_groups": 12,
        "migrated_occurrences": 12,
        "unresolved_groups": 0,
        "unresolved_occurrences": 0,
    }
    assert payload["frontend_revision"] == "08359de59e756ce73c61df9818c7e7bcaeb86975"
    assert payload["frontend_source"]["blob"] == "4c95a998bb2f1048183d063587526eb76238be53"
    assert payload["frontend_source"]["sha256"] == (
        "sha256:bf95202bca72d6c844864ef2c3ca285a4ee288770f3538c4bc63717ec0c2ee0f"
    )
    assert payload["frontend_dist"]["blob"] == payload["frontend_source"]["blob"]
    assert payload["frontend_dist"]["sha256"] == payload["frontend_source"]["sha256"]
    assert payload["canonical_remainder"] == {"groups": 0, "occurrences": 0}
    assert len(payload["entries"]) == 12
    assert sum(len(entry["occurrences"]) for entry in payload["entries"]) == 12
    for entry in payload["entries"]:
        assert entry["final_disposition"] == "migrated"
        assert entry["final_inventory_mapping"] == "capability"
        assert entry["old_route_evidence"]["handler_status"] == "absent"
        assert entry["candidate_capability"].startswith("integration.")
        assert entry["frontend_capability_evidence"]["source_path"] == "web/ext_datasource/ext_ds.js"
        assert entry["provider_anchor"]["source_path"].endswith("capabilities/provider.py")
        assert entry["service_anchor"]["source_path"].endswith("application/service.py")
        assert entry["contract_evidence"]["input_schema"]["additionalProperties"] is False
        assert entry["contract_evidence"]["output_schema"]["additionalProperties"] is False
        assert entry["legacy_route_absent"] is True
        assert entry["plaintext_credentials_absent"] is True
        assert entry["arbitrary_sql_absent"] is True


def test_manifest_binds_each_route_to_its_real_candidate_contract_and_service_evidence():
    """Breaks if a route is justified by a generic provider claim rather than its real evidence."""
    payload = _module().build_manifest(WEB_ROOT)
    entries = {(item["method"], item["normalized_route"]): item for item in payload["entries"]}

    for key, entry in entries.items():
        evidence = entry["contract_evidence"]
        assert evidence["input_schema"]["additionalProperties"] is False
        assert evidence["output_schema"]["additionalProperties"] is False
        assert entry["candidate_policy"]["confirmation"] in {"none", "user"}
        assert entry["candidate_policy"]["idempotency"] in {"none", "required"}
        assert entry["candidate_policy"]["external_side_effect"] in {"none", "connector_runtime", "asynchronous_import"}
        if entry["candidate_policy"]["external_side_effect"] != "connector_runtime":
            assert entry["candidate_policy"]["timeout"] == "not_applicable"
        else:
            assert entry["candidate_policy"]["timeout"] == "15_seconds"
        assert key in entries

    assert entries[("POST", "/api/ext-mappings/{dynamic}/import")]["candidate_policy"]["external_side_effect"] == "asynchronous_import"
    assert entries[("GET", "/api/ext-datasources/{dynamic}/tables")]["candidate_policy"]["external_side_effect"] == "connector_runtime"


def test_manifest_validator_rejects_tampered_target_provider_and_final_inventory():
    """Breaks if a hand-edited manifest can bypass target, provider, or inventory evidence."""
    module = _module()
    payload = module.build_manifest(WEB_ROOT)
    assert module.validate_manifest_against_expected(payload, payload) == ()

    for field, value, reason in (
        ("candidate_capability", "base.identity.session.get@1", "candidate_target_mismatch"),
        ("final_inventory_mapping", "unresolved", "final_inventory_mismatch"),
    ):
        mutated = {**payload, "entries": [dict(item) for item in payload["entries"]]}
        mutated["entries"][0][field] = value
        assert reason in module.validate_manifest_against_expected(mutated, payload)


def test_manifest_validator_rejects_tampered_route_evidence_and_final_occurrence_identity():
    """Breaks if a service/decision edit or moved frontend occurrence can remain certified."""
    module = _module()
    payload = module.build_manifest(WEB_ROOT)

    mutations = (
        ("service_evidence_mismatch", lambda item: item["service_anchor"].__setitem__("sha256", "0" * 64)),
        ("contract_evidence_mismatch", lambda item: item["contract_evidence"]["input_anchor"].__setitem__("sha256", "0" * 64)),
        ("frontend_evidence_mismatch", lambda item: item["frontend_capability_evidence"].__setitem__("line", 999)),
    )
    for reason, mutate in mutations:
        changed = json.loads(json.dumps(payload))
        mutate(changed["entries"][0])
        assert reason in module.validate_manifest_against_expected(changed, payload)
