from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/build_base_structural_web_remediation.py"


def _module():
    spec = importlib.util.spec_from_file_location("base_structural_manifest", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_conserves_pinned_base_scope_and_keeps_only_plugins_unresolved():
    payload = _module().build_manifest(ROOT.parent / "workmanship-web-capability-governance")
    assert payload["counts"] == {"groups": 16, "occurrences": 33, "migrated_groups": 14, "migrated_occurrences": 31, "unresolved_groups": 2, "unresolved_occurrences": 2}
    entries = {(item["method"], item["normalized_route"]): item for item in payload["entries"]}
    for key in (("POST", "/api/plugin/install"), ("DELETE", "/api/plugin/uninstall/{dynamic}")):
        assert entries[key]["final_disposition"] == "unresolved"
        assert "signed" in entries[key]["unresolved_reason"] or "lifecycle" in entries[key]["unresolved_reason"]
    for entry in entries.values():
        assert entry["occurrences"]
        assert entry["old_route_evidence"]["source_path"]
        assert entry["final_inventory_mapping"] in {"capability", "unresolved"}


def test_saved_view_routes_require_shared_service_and_closed_contract_evidence():
    module = _module()
    key = ("POST", "/api/views")
    assert module._saved_view_boundary_ready(key, {"capability_id": "base.saved_view.create", "major_version": 1})
    assert not module._saved_view_boundary_ready(key, {"capability_id": "base.saved_view.create", "major_version": 2})


def test_saved_view_routes_have_exact_owner_contract_and_frontend_source_evidence():
    module = _module()
    payload = module.build_manifest(ROOT.parent / "workmanship-web-capability-governance")
    entries = {(item["method"], item["normalized_route"]): item for item in payload["entries"]}
    for key, target in module.SAVED_VIEW_TARGETS.items():
        entry = entries[key]
        assert entry["final_disposition"] == "migrated"
        assert entry["candidate_capability"] == f"{target}@1"
        assert entry["provider_anchor"].startswith("backend/base/web_atomic.py:")
        assert entry["owner_service_evidence"]["source_path"] == "backend/base/saved_views.py"
        assert entry["owner_service_evidence"]["source_sha256"].startswith("sha256:")
        assert entry["contract_evidence"]["source_path"] == "backend/base/web_atomic.py"
        assert entry["frontend_operation"].startswith("base.savedViews.")
        assert entry["frontend_call_sites"]
        assert all(site["source_path"].startswith("web/") for site in entry["frontend_call_sites"])


def test_annotation_and_identity_routes_have_exact_owner_service_contract_and_frontend_evidence():
    module = _module()
    payload = module.build_manifest(ROOT.parent / "workmanship-web-capability-governance")
    entries = {(item["method"], item["normalized_route"]): item for item in payload["entries"]}
    expected = {
        ("GET", "/api/self_ann/{dynamic}"): ("base.self_annotation.record.get", "backend/base/self_annotations.py", "base.annotations.get"),
        ("GET", "/api/self_ann/list"): ("base.self_annotation.search", "backend/base/self_annotations.py", "base.annotations.search"),
        ("PUT", "/api/self_ann/{dynamic}"): ("base.self_annotation.change.apply", "backend/base/self_annotations.py", "base.annotations.apply"),
        ("GET", "/api/users/me"): ("base.identity.session.profile.get", "backend/base/identity_profile.py", "base.identity.session.profile.get"),
    }
    for key, (target, service, operation) in expected.items():
        entry = entries[key]
        assert entry["final_disposition"] == "migrated"
        assert entry["candidate_capability"] == f"{target}@1"
        assert entry["owner_service_evidence"]["source_path"] == service
        assert entry["contract_evidence"]["source_path"] == "backend/base/web_atomic.py"
        assert entry["frontend_operation"] == operation
        assert entry["frontend_call_sites"]
