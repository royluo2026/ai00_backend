from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/build_craft_agent_project_structural_web_remediation.py"
PLAN_SCRIPT = ROOT / "backend/scripts/check_structural_remediation_plan.py"
WEB_ROOT = ROOT.parent / "workmanship-web-capability-governance"


def _module():
    spec = importlib.util.spec_from_file_location("craft_agent_project_structural_manifest", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plan_module():
    spec = importlib.util.spec_from_file_location("structural_remediation_plan", PLAN_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frontend_source(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"69e5e00054d3c1cff635fe41fcb96fbe150d25fb:{path}"],
        cwd=WEB_ROOT, check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout


def test_structural_plan_uses_the_registered_craft_list_capability_identity():
    """Breaks if the generated execution card points to an unregistered search alias."""
    assert _plan_module().GROUP_SPECS[("GET", "/api/lists")]["target_capability"] == (
        "craft.bop.version.list@1"
    )


def test_project_closure_evidence_freezes_exact_frontend_commit_blobs_and_absence():
    """Breaks if closure can drift to another Web commit or retain one of the three legacy calls."""
    evidence = _module().build_project_closure_evidence(WEB_ROOT)

    assert evidence["frontend_revision"] == "69e5e00054d3c1cff635fe41fcb96fbe150d25fb"
    assert evidence["scanner_materialization"] == {
        "method": "git-tree-blobs-v1",
        "revision": "69e5e00054d3c1cff635fe41fcb96fbe150d25fb",
        "tree": "0eb308bf3f8ad300a584659a2d27c6b6de60bd95",
        "roots": ["web", "packages"],
        "document_count": 224,
        "materialization_sha256": "sha256:2bf2b224b9a09396811ec61a9a067f60eff6a1ce400ff9f56710557106c28e55",
    }
    assert {
        path: item["blob"] for path, item in evidence["frontend_files"].items()
    } == {
        "dist-production/packages/craft-plugin/web/approval/approval.js": "67019bf6dec52d8be278b8dda44e76299269d870",
        "dist-production/packages/craft-plugin/web/bop/bop.js": "313b6f9c06920a8d905099e40f2754be71a5dba8",
        "dist-production/web/components/list_sidebar.js": "5441dcc79b2eddf24af8b87f0fa959e42f3e216f",
        "dist-production/web/core/existing_capability_client.js": "a179dc94009217bafb32b7f9571d3c052bb01d56",
        "packages/craft-plugin/web/approval/approval.js": "7903b987d7f27b5d05b94181cf0361eca0abad6f",
        "packages/craft-plugin/web/bop/bop.js": "9f99585bb577e331241743027a631e84bf77ec4b",
        "web/components/list_sidebar.js": "5441dcc79b2eddf24af8b87f0fa959e42f3e216f",
        "web/core/existing_capability_client.js": "a179dc94009217bafb32b7f9571d3c052bb01d56",
    }
    assert all(item["legacy_route_absent"] for item in evidence["routes"].values())
    assert evidence["approval"]["web_notification_side_effect_absent"] is True
    assert evidence["list_dispatch"]["capabilities"] == {
        "bop_version": {
            "search": "craft.bop.version.list@1",
            "delete": "craft.bop.version.archive@1",
        },
        "project": {
            "search": "project.list.read.atomic.lists_search@1",
            "delete": "project.list.change.apply.atomic.lists_delete@1",
        },
    }


def test_list_dispatch_evidence_is_derived_from_complete_mapping_and_fail_closed_source():
    """Breaks on a wrong owner mapping or an unknown-item branch that no longer fails closed."""
    module = _module()
    source = _frontend_source("web/core/existing_capability_client.js")

    evidence = module._list_dispatch_evidence(source)

    assert evidence["capabilities"] == {
        "bop_version": {
            "search": "craft.bop.version.list@1",
            "delete": "craft.bop.version.archive@1",
        },
        "project": {
            "search": "project.list.read.atomic.lists_search@1",
            "delete": "project.list.change.apply.atomic.lists_delete@1",
        },
    }
    assert evidence["unknown_item_type"] == {
        "behavior": "throw",
        "error_code": "capability_not_bound",
    }
    assert evidence["source_block_sha256"].startswith("sha256:")

    mutations = (
        source.replace(
            "search: 'project.list.read.atomic.lists_search'",
            "search: 'project.project.read.atomic.projects_search'",
            1,
        ),
        source.replace(
            "if (!capabilityId) throw capabilityNotBound(itemType);",
            "if (!capabilityId) return { capabilityId: null, write: false };",
            1,
        ),
    )
    for changed in mutations:
        with pytest.raises(ValueError, match="list dispatch source drift"):
            module._list_dispatch_evidence(changed)


def test_approval_outbound_evidence_rejects_notification_helpers_and_capabilities():
    """Breaks unless every call in the complete rejection flow is classified fail-closed."""
    module = _module()
    source = _frontend_source("packages/craft-plugin/web/approval/approval.js")

    evidence = module._approval_outbound_evidence(source)

    assert evidence["allowed_outbound_calls"] == [
        "capability:project.approval.order.reject",
    ]
    assert evidence["unknown_calls"] == []
    assert {item["classification"] for item in evidence["classified_calls"]} == {
        "local_pure",
        "local_ui",
        "allowed_outbound",
    }
    assert evidence["flow_sha256"].startswith("sha256:")

    mutations = (
        source.replace(
            "let res;",
            "notificationClient.publish({ order_gid: _selected.gid });\n  let res;",
            1,
        ),
        source.replace(
            "capabilityClient.invoke('project.approval.order.reject'",
            "capabilityClient.invoke('base.notification.change.apply'",
            1,
        ),
        source.replace("let res;", "broadcastRejection(_selected.gid);\n  let res;", 1),
        source.replace("let res;", "announceApplicant(result);\n  let res;", 1),
        source.replace("let res;", "helpers.broadcastRejection(_selected.gid);\n  let res;", 1),
        source.replace("let res;", "(0, announceApplicant)(result);\n  let res;", 1),
        source.replace("let res;", "helpers['announceApplicant'](result);\n  let res;", 1),
    )
    for changed in mutations:
        with pytest.raises(ValueError, match="approval outbound call drift"):
            module._approval_outbound_evidence(changed)


def test_project_closure_evidence_pins_provider_contract_outbox_and_gateway_anchors():
    """Breaks if Project closure is inferred from names instead of the shipped owner transaction."""
    evidence = _module().build_project_closure_evidence(WEB_ROOT)
    routes = evidence["routes"]

    assert routes["GET /api/lists"]["candidate_capability"] == "craft.bop.version.list@1"
    assert routes["DELETE /api/lists/{dynamic}"]["candidate_capability"] == "craft.bop.version.archive@1"
    assert routes["POST /api/approval/orders/{dynamic}/reject"]["candidate_capability"] == "project.approval.order.reject@1"
    assert evidence["approval"]["provider_contract"] == {
        "source_path": "plugins/project_management/project_management_backend/capabilities/reviewed.py",
        "start_line": 244,
        "end_line": 281,
        "source_sha256": "sha256:af0a539e6faebdb5e861318e9c8e38018f95cb3708578dd1e6cc1ecb7c56a091",
        "snippet_sha256": "sha256:0d655febbfe0e66ea4304dc17c08542368095461299c5fe5c26e237e4ae1609c",
    }
    assert evidence["approval"]["outbox_transaction"] == {
        "source_path": "plugins/project_management/project_management_backend/infrastructure/repository.py",
        "start_line": 16,
        "end_line": 119,
        "source_sha256": "sha256:37c950dcc3099b1889b4cefd8c2cc3211bf8707f83927c2ce491938c69844a24",
        "snippet_sha256": "sha256:21dc028a0c1952d0ae4085d8d4650a4aa8904bcbd388e680093bcc087d04286c",
    }
    assert evidence["approval"]["migration"] == {
        "source_path": "backend/db/migrations/domains/project_management/0002_approval_notification_outbox.sql",
        "start_line": 34,
        "end_line": 46,
        "source_sha256": "sha256:8f9d437b414d1d4e1231ee5069f6f702e5698ec2a43247bda84bc7c59456ca40",
        "snippet_sha256": "sha256:77392346742d41ab87b36ee71e83d78f9cb638626482576821e8f3e54a2e4e5e",
    }
    assert evidence["approval"]["gateway_context"] == {
        "source_path": "backend/capability_v2/gateway.py",
        "start_line": 518,
        "end_line": 532,
        "source_sha256": "sha256:9f123749f61db87e7d1341bb4bfc938e4e54e4e30282a261bf879b054eb84f33",
        "snippet_sha256": "sha256:3534699625178c993d9ea37f1c5ac9df2c81c934d339d1ad51a3cc57afbcc4f4",
    }
    assert evidence["approval"]["gateway_integration"] == {
        "source_path": "plugins/project_management/tests/test_project_approval_reject_gateway_integration.py",
        "start_line": 51,
        "end_line": 140,
        "source_sha256": "sha256:a9b21f575e75f1537db8f3b459861a7119a3835ef7437865b61dd13ec887dd93",
        "snippet_sha256": "sha256:1aeb89b36d304a50f41b46ecc0274de6d3aa3c55a74095947a20070664ace452",
    }


@pytest.fixture(scope="module")
def manifest():
    """One fresh scanner pass keeps the independently runnable suite bounded."""
    module = _module()
    return module, module.build_manifest(WEB_ROOT)


def test_manifest_closes_three_source_proved_groups_and_conserves_the_remainder(manifest):
    """Breaks if closure counts are hand-authored instead of conserved from immutable evidence."""
    _, payload = manifest

    assert payload["counts"] == {
        "groups": 14,
        "occurrences": 17,
        "migrated_groups": 3,
        "migrated_occurrences": 3,
        "unresolved_groups": 11,
        "unresolved_occurrences": 14,
    }
    assert payload["closure_arithmetic"] == {
        "baseline": {"groups": 14, "occurrences": 17},
        "closed": {"groups": 3, "occurrences": 3},
        "canonical_remainder": {"groups": 11, "occurrences": 14},
    }
    assert payload["closure_arithmetic"]["baseline"]["groups"] - payload["closure_arithmetic"]["closed"]["groups"] == payload["closure_arithmetic"]["canonical_remainder"]["groups"]
    assert payload["closure_arithmetic"]["baseline"]["occurrences"] - payload["closure_arithmetic"]["closed"]["occurrences"] == payload["closure_arithmetic"]["canonical_remainder"]["occurrences"]
    assert {entry["owner_domain"] for entry in payload["entries"]} == {
        "craft", "agent", "project_management",
    }
    migrated = [entry for entry in payload["entries"] if entry["final_disposition"] == "migrated"]
    unresolved = [entry for entry in payload["entries"] if entry["final_disposition"] == "unresolved"]
    assert {(entry["method"], entry["normalized_route"]) for entry in migrated} == {
        ("GET", "/api/lists"),
        ("DELETE", "/api/lists/{dynamic}"),
        ("POST", "/api/approval/orders/{dynamic}/reject"),
    }
    assert sum(len(entry["occurrences"]) for entry in migrated) == 3
    assert sum(len(entry["occurrences"]) for entry in unresolved) == 14
    for entry in unresolved:
        assert entry["final_disposition"] == "unresolved"
        assert entry["final_inventory_mapping"] == "unresolved"
        assert entry["non_equivalence"]


def test_manifest_preserves_agent_findings_and_closes_only_exact_bop_and_approval_outcomes(manifest):
    """Breaks if unresolved Agent/Craft findings are relabeled or Project closure uses a generic target."""
    _, payload = manifest
    entries = {
        (entry["method"], entry["normalized_route"]): entry
        for entry in payload["entries"]
    }
    for key in (
        ("POST", "/api/flows/test-node"),
        ("POST", "/api/skills/canvas-options"),
        ("POST", "/api/skills/execute-canvas"),
        ("POST", "/api/skills/resume-canvas"),
    ):
        assert entries[key]["runtime_execution"] == "unresolved_no_bounded_runtime_service"
    for key in (("GET", "/api/lists"), ("DELETE", "/api/lists/{dynamic}")):
        entry = entries[key]
        assert entry["bop_conditional_branch"] is True
        assert entry["final_disposition"] == "migrated"
        assert entry["final_inventory_mapping"] == "capability"
        assert entry["frontend_call_sites"]
        lifecycle = entry["lifecycle_evidence"]
        assert lifecycle["selector"] == 'item_type == "bop_version"'
        assert lifecycle["direct_sql"] is False
    assert entries[("GET", "/api/lists")]["candidate_capability"] == "craft.bop.version.list@1"
    assert entries[("GET", "/api/lists")]["lifecycle_evidence"]["capability_id"] == "craft.bop.version.list"
    delete = entries[("DELETE", "/api/lists/{dynamic}")]["lifecycle_evidence"]
    assert entries[("DELETE", "/api/lists/{dynamic}")]["candidate_capability"] == "craft.bop.version.archive@1"
    assert delete["capability_id"] == "craft.bop.version.archive"
    assert delete["expected_revision_required"] is True

    approval = entries[("POST", "/api/approval/orders/{dynamic}/reject")]["approval_reject_evidence"]
    assert entries[("POST", "/api/approval/orders/{dynamic}/reject")]["candidate_capability"] == "project.approval.order.reject@1"
    assert entries[("POST", "/api/approval/orders/{dynamic}/reject")]["final_disposition"] == "migrated"
    assert approval["web_notification_side_effect_absent"] is True
    assert approval["migration"]["source_path"].endswith("0002_approval_notification_outbox.sql")
    assert approval["gateway_integration"]["source_path"].endswith("test_project_approval_reject_gateway_integration.py")


def test_manifest_validator_rejects_tampered_provider_contract_and_final_occurrence(manifest):
    """Breaks if hand edits can erase owner-service, contract, or frontend identity evidence."""
    module, payload = manifest
    assert module.validate_manifest_against_expected(payload, payload) == ()

    mutations = (
        ("provider_hash_mismatch", ("DELETE", "/api/craft_lib/equipments/{dynamic}"), lambda entry: entry.__setitem__("provider_source_sha256", "sha256:" + "0" * 64)),
        ("non_equivalence_evidence_mismatch", ("DELETE", "/api/craft_lib/equipments/{dynamic}"), lambda entry: entry["non_equivalence"].__setitem__("input", "forged")),
        ("lifecycle_evidence_mismatch", ("GET", "/api/lists"), lambda entry: entry["lifecycle_evidence"]["provider"].__setitem__("source_sha256", "sha256:" + "0" * 64)),
        ("approval_evidence_mismatch", ("POST", "/api/approval/orders/{dynamic}/reject"), lambda entry: entry["approval_reject_evidence"]["migration"].__setitem__("start_line", 999)),
    )
    for reason, key, mutate in mutations:
        changed = json.loads(json.dumps(payload))
        entry = next(item for item in changed["entries"] if (item["method"], item["normalized_route"]) == key)
        mutate(entry)
        assert reason in module.validate_manifest_against_expected(changed, payload)

    for field, value in (("occurrence_id", "forged"), ("source", "web/forged.js"), ("line", 999), ("column", 999), ("source_sha256", "0" * 64)):
        changed = json.loads(json.dumps(payload))
        changed["entries"][0]["final_occurrences"][0][field] = value
        assert "final_occurrence_mismatch" in module.validate_manifest_against_expected(changed, payload)
    for field in ("source_ledger_revision", "source_ledger_sha256"):
        changed = json.loads(json.dumps(payload))
        changed[field] = "forged"
        assert "source_ledger_evidence_mismatch" in module.validate_manifest_against_expected(changed, payload)


def _rehash(module, payload):
    without_hash = {key: value for key, value in payload.items() if key != "content_sha256"}
    payload["content_sha256"] = module._sha256(module._canonical(without_hash).encode())
    return payload


def test_manifest_validator_requires_exact_canonical_document_equality(manifest):
    """Breaks if any self-rehashed decision field can differ from the independent rebuild."""
    module, payload = manifest

    def approval(document):
        return next(
            item for item in document["entries"]
            if (item["method"], item["normalized_route"])
            == ("POST", "/api/approval/orders/{dynamic}/reject")
        )

    mutations = []
    changed = json.loads(json.dumps(payload))
    approval(changed)["candidate_capability"] = "project.approval.order.withdraw@1"
    mutations.append(changed)
    changed = json.loads(json.dumps(payload))
    approval(changed)["method"] = "PUT"
    mutations.append(changed)
    changed = json.loads(json.dumps(payload))
    approval(changed)["normalized_route"] = "/api/approval/orders/{dynamic}/withdraw"
    mutations.append(changed)
    changed = json.loads(json.dumps(payload))
    approval(changed)["occurrences"].append(dict(approval(changed)["occurrences"][0]))
    mutations.append(changed)
    changed = json.loads(json.dumps(payload))
    approval(changed)["legacy_route_absent"] = False
    mutations.append(changed)
    changed = json.loads(json.dumps(payload))
    changed["closure_arithmetic"]["canonical_remainder"]["occurrences"] = 13
    mutations.append(changed)
    changed = json.loads(json.dumps(payload))
    approval(changed)["approval_reject_evidence"]["gateway_context"]["start_line"] += 1
    mutations.append(changed)

    for changed in (*mutations, {}):
        if changed:
            _rehash(module, changed)
        issues = module.validate_manifest_against_expected(changed, payload)
        assert "canonical_document_mismatch" in issues
