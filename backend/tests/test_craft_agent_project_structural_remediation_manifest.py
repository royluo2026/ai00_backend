from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/build_craft_agent_project_structural_web_remediation.py"
PLAN_SCRIPT = ROOT / "backend/scripts/check_structural_remediation_plan.py"
LEDGER_SCRIPT = ROOT / "backend/scripts/build_web_route_root_cause_ledger.py"
WEB_ROOT = ROOT.parent / "workmanship-web-capability-governance"
CRAFT_FRONTEND_REVISION = "8ebc8de49b5d4f86c9360664fffa912c3d969102"
AGENT_BACKEND_REVISION = "d56c743dee03112b2a3211a4ccb659ebed9cfda5"
AGENT_FRONTEND_REVISION = "08359de59e756ce73c61df9818c7e7bcaeb86975"


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


def _ledger_module():
    spec = importlib.util.spec_from_file_location("web_route_root_cause_ledger", LEDGER_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frontend_source(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"69e5e00054d3c1cff635fe41fcb96fbe150d25fb:{path}"],
        cwd=WEB_ROOT, check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout


def _craft_frontend_source(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{CRAFT_FRONTEND_REVISION}:{path}"],
        cwd=WEB_ROOT, check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout


def test_agent_closure_evidence_freezes_exact_source_identities_and_anchors():
    """Breaks if Agent closure is inferred from names or a mutable checkout."""
    evidence = _module().build_agent_closure_evidence(WEB_ROOT)

    assert evidence["backend_revision"] == AGENT_BACKEND_REVISION
    assert evidence["backend_tree"] == "9ec7401102fc337bd2b1a77361eae9e52b817478"
    assert evidence["frontend_revision"] == AGENT_FRONTEND_REVISION
    assert evidence["scanner_materialization"] == {
        "method": "git-tree-blobs-v1",
        "revision": AGENT_FRONTEND_REVISION,
        "tree": "3c3156841af0d4bf2833dba8184b071265993965",
        "roots": ["web", "packages"],
        "document_count": 224,
        "materialization_sha256": "sha256:2fe79af7f2d8b15397230b0c5383ea421e4ccff9e4581959e8da03ef206df992",
    }
    assert {
        path: item["blob"] for path, item in evidence["backend_files"].items()
    } == {
        "backend/capability_v2/gateway.py": "6d8a3e052901df5bff607889b4163250b5c6370d",
        "backend/db/migrations/domains/agent/0003_canvas_execution_control.sql": "5d1febea8ee0b44851029fc58716c2c387385384",
        "plugins/agent/agent_backend/application/canvas_runtime.py": "35b933b84af64e2dddd25122c56cde2ce2300820",
        "plugins/agent/agent_backend/application/service.py": "20999ec38b694bdec71f68d7bd382086de54fa60",
        "plugins/agent/agent_backend/capabilities/__init__.py": "0b81093263520cf2a44670053562020a3ff858e9",
        "plugins/agent/agent_backend/capabilities/contracts.py": "749473ea8336267cca1bd4b8bf884ed8e38e293f",
        "plugins/agent/agent_backend/capabilities/descriptors.py": "5795da4f92eab51e982ff53788b0524e03ac2422",
        "plugins/agent/agent_backend/capabilities/provider.py": "78db671e0192d8d63226be6287d9aece312f444a",
        "plugins/agent/agent_backend/infrastructure/repository.py": "594e9c7fd5e37e7518d18871891f86087aae8b5b",
    }
    assert {
        path: item["blob"] for path, item in evidence["frontend_files"].items()
    } == {
        "dist-production/packages/agent-plugin/web/flow_canvas/flow_editor.js": "36c962e917d66d1347d1f890b2aaaabf2162a09d",
        "dist-production/packages/agent-plugin/web/wfc_window/wfc_window.js": "bdb262d6a60498e73f1add1854a7f518e3511948",
        "dist-production/web/canvas/types/flow_type.js": "16f80b53fa4db1090a5218f32b93a206d49d58fa",
        "packages/agent-plugin/web/flow_canvas/flow_editor.js": "0635d8017aee32367e1c75d311c94b11e65ef952",
        "packages/agent-plugin/web/wfc_window/wfc_window.js": "feac63e030dfee47c0a6a3006bed91244a796954",
        "web/canvas/types/flow_type.js": "c50f142483240694822bde303c703a27993eec0a",
    }
    assert set(evidence["routes"]) == {
        "POST /api/flows/test-node",
        "POST /api/skills/canvas-options",
        "POST /api/skills/execute-canvas",
        "POST /api/skills/resume-canvas",
    }
    assert {
        key: item["candidate_capability"] for key, item in evidence["routes"].items()
    } == {
        "POST /api/flows/test-node": "agent.workflow.node.test.execute@1",
        "POST /api/skills/canvas-options": "agent.canvas.options.resolve@1",
        "POST /api/skills/execute-canvas": "agent.canvas.execution.start@1",
        "POST /api/skills/resume-canvas": "agent.canvas.execution.resume@1",
    }
    assert sum(len(item["frontend_call_sites"]) for item in evidence["routes"].values()) == 5
    assert [
        item["source_path"]
        for item in evidence["routes"]["POST /api/flows/test-node"][
            "idempotency_caller_evidence"
        ]
    ] == [
        "packages/agent-plugin/web/flow_canvas/flow_editor.js",
        "web/canvas/types/flow_type.js",
    ]
    pinned_provider_hash = evidence["backend_files"][
        "plugins/agent/agent_backend/capabilities/provider.py"
    ]["sha256"]
    for item in evidence["routes"].values():
        assert item["provider_anchor"]
        assert item["provider_anchor"]["source_sha256"] == pinned_provider_hash
        assert item["contract_evidence"]
        assert item["runtime_evidence"]
        assert item["gateway_evidence"]
        assert item["frontend_call_sites"]
        assert item["legacy_route_absent"] is True


def test_craft_closure_evidence_freezes_exact_source_identities_and_anchors():
    """Breaks if Craft closure drifts from the reviewed backend or frozen Web tree."""
    evidence = _module().build_craft_closure_evidence(WEB_ROOT)

    assert evidence["backend_revision"] == "9cda07080f3e27b10d30ec6492ea875c31c82492"
    assert evidence["backend_tree"] == "1c31a434c78243f163d3a1b7914ce64221a20796"
    assert evidence["frontend_revision"] == CRAFT_FRONTEND_REVISION
    assert evidence["scanner_materialization"] == {
        "method": "git-tree-blobs-v1",
        "revision": CRAFT_FRONTEND_REVISION,
        "tree": "8ffe4dde53f1b12f2a4cd55c2f7a1cf49aeb6992",
        "roots": ["web", "packages"],
        "document_count": 224,
        "materialization_sha256": "sha256:76e0efa1eb50caa5bdcba9223964ff7494932f8c2f7ddeb38e71e57898a85d9c",
    }
    assert {
        path: item["blob"] for path, item in evidence["frontend_files"].items()
    } == {
        "dist-production/packages/craft-plugin/web/lineage_view/layout_detail_panel.js": "790fa9303109bd4c914f043ea63e3d06a306ec91",
        "dist-production/web/container_card/modes/container_item_detail.js": "f80b7f2f7168b3a1049989c21b93ef231b778b00",
        "dist-production/web/container_card/modes/mode_field_detail.js": "8111a1cb22209beb708be2dea177004f13788f3b",
        "dist-production/web/knowledge_hub/pages/gbop_vpps.html": "b5f37566ebe00f00740691fb76a720aab3f46b87",
        "dist-production/web/rule_mgmt/rule_mgmt.html": "eb7f87f7347e88247bd30cf5b9a895d751bbee99",
        "dist-production/web/rule_mgmt/rule_mgmt.js": "ec66cdda6154ac2cf3af143befedd933b210b392",
        "packages/craft-plugin/web/lineage_view/layout_detail_panel.js": "790fa9303109bd4c914f043ea63e3d06a306ec91",
        "web/container_card/modes/container_item_detail.js": "7c72c1908cebea8d8cbdf72743f37366fc432f1c",
        "web/container_card/modes/mode_field_detail.js": "84f8f8a083169bc9d32870b539d739f50fd34adc",
        "web/knowledge_hub/pages/gbop_vpps.html": "2ea909184bf3d6e7c67791eb9f258e04ca62a34f",
        "web/rule_mgmt/rule_mgmt.html": "d4c58f1e74117a7cac19cdd141bbabbfd876c6bb",
        "web/rule_mgmt/rule_mgmt.js": "f6b03514744aece0c572090d8601865bb5df03a9",
    }
    assert set(evidence["dead_actions"]) == {
        "DELETE /api/craft_lib/equipments/{dynamic}",
        "DELETE /api/craft_lib/fixtures/{dynamic}",
        "POST /api/rules/{dynamic}/activate",
        "POST /api/rules/{dynamic}/deviations",
        "POST /api/rules/{dynamic}/suspend",
    }
    assert all(item["network_path_absent"] for item in evidence["dead_actions"].values())
    assert all(item["interactive_control_absent"] for item in evidence["dead_actions"].values())
    assert evidence["routes"]["GET /api/rule-engine/check-entry"]["candidate_capability"] == "craft.rule.entry.evaluate@1"
    assert evidence["routes"]["PUT /api/rules/{dynamic}"]["candidate_capability"] == "craft.rule.definition.change.apply@1"
    for item in evidence["routes"].values():
        assert item["provider_anchor"]
        assert item["contract_evidence"]
        assert item["gateway_anchor"]
        assert item["frontend_call_sites"]
        assert item["legacy_route_absent"] is True


def test_craft_dead_action_evidence_fails_closed_on_network_or_control_reintroduction():
    """Breaks if a dead action can regain a route or interactive control without failing evidence."""
    module = _module()
    sources = {
        path: _craft_frontend_source(path)
        for path in (
            "web/knowledge_hub/pages/gbop_vpps.html",
            "dist-production/web/knowledge_hub/pages/gbop_vpps.html",
            "web/rule_mgmt/rule_mgmt.js",
            "dist-production/web/rule_mgmt/rule_mgmt.js",
            "web/rule_mgmt/rule_mgmt.html",
            "dist-production/web/rule_mgmt/rule_mgmt.html",
        )
    }
    evidence = module._dead_action_evidence(sources)
    assert all(item["network_path_absent"] for item in evidence.values())
    assert all(item["interactive_control_absent"] for item in evidence.values())

    mutations = (
        ("web/knowledge_hub/pages/gbop_vpps.html", "\n_cloudFetch(`/api/craft_lib/equipments/${gid}`, { method:'DELETE' });"),
        ("web/rule_mgmt/rule_mgmt.js", "\n<button data-action=\"activate\"></button>"),
        ("web/rule_mgmt/rule_mgmt.js", "\ndocument.addEventListener('click', saveDeviation);"),
        ("web/rule_mgmt/rule_mgmt.html", "\n<div id=\"modal-deviation\"></div>"),
    )
    for path, addition in mutations:
        changed = dict(sources)
        changed[path] += addition
        with pytest.raises(ValueError, match="dead Craft action source drift"):
            module._dead_action_evidence(changed)


def test_root_cause_ledger_retains_removed_derived_occurrence_after_zero_remainder():
    """Breaks if clean regeneration requires a fake migration for removed rule suspend."""
    document = _ledger_module().build_document(WEB_ROOT)

    assert document["final_evidence"]["frontend_revision"] == AGENT_FRONTEND_REVISION
    assert document["final_evidence"]["unresolved_group_count"] == 0
    assert document["final_evidence"]["unresolved_count"] == 0
    suspend = next(
        item for item in document["entries"]
        if (item["method"], item["normalized_route"])
        == ("POST", "/api/rules/{dynamic}/suspend")
    )
    assert suspend["occurrence_count"] == 1
    assert suspend["occurrences"][0]["method"] == "POST"
    assert suspend["occurrences"][0]["raw_route"] == "/api/rules/${gid}/suspend"


def test_existing_migration_audit_accepts_canonical_removed_dead_entries(manifest):
    """Breaks if dead actions must be mislabeled migrated to leave final inventory."""
    from backend.capability_v2.existing_capability_migrations import (
        audit_existing_capability_migrations,
        load_existing_capability_migrations,
    )

    _, remediation = manifest
    migrations = load_existing_capability_migrations(
        ROOT / "docs/governance/existing-capability-web-migrations.json"
    )
    issues = audit_existing_capability_migrations(
        ROOT, migrations, web_root=WEB_ROOT, remediation_document=remediation,
    )
    assert "migration_final_reclassification_mismatch:POST:/api/rules/{dynamic}/activate" not in issues
    assert "migration_final_reclassification_mismatch:POST:/api/rules/{dynamic}/deviations" not in issues


def test_structural_plan_records_removed_dead_entries_without_fake_targets():
    """Breaks if a removed control is turned back into a candidate capability card."""
    payload = _plan_module().build_plan(ROOT)
    dead = [group for group in payload["groups"] if group["current_disposition"] == "removed_dead_entry"]

    assert len(dead) == 5
    assert all(group["target_capability"] is None for group in dead)
    assert all(group["implementation_disposition"] == "removed_dead_entry" for group in dead)
    assert all(group["approval"] == {"required": False, "decision": None} for group in dead)


def test_structural_plan_uses_the_registered_craft_list_capability_identity():
    """Breaks if the generated execution card points to an unregistered search alias."""
    assert _plan_module().GROUP_SPECS[("GET", "/api/lists")]["target_capability"] == (
        "craft.bop.version.list@1"
    )


def test_structural_plan_uses_the_shipped_agent_runtime_without_pending_approval():
    """Breaks if closed Agent groups retain the obsolete proposed-service plan."""
    module = _plan_module()
    package = module.PACKAGES["agent_bounded_runtime"]

    assert package["owner_service"] == (
        "plugins.agent.agent_backend.application.canvas_runtime.ProductionAgentCanvasRuntime"
    )
    assert package["owner_service_source"] == (
        "plugins/agent/agent_backend/application/canvas_runtime.py"
    )
    assert package["approval_gate"] is None
    assert all(
        module.GROUP_SPECS[key]["approval_required"] is False
        for key in module.AGENT_STRUCTURAL_KEYS
    )


def test_structural_plan_preserves_base_integration_and_records_agent_closure():
    """Breaks if zero remainder rewrites historical Base/Integration scope."""
    payload = _plan_module().build_plan(ROOT)
    by_domain = {
        domain: {
            "groups": sum(group["owner_domain"] == domain for group in payload["groups"]),
            "occurrences": sum(
                len(group["occurrences"])
                for group in payload["groups"] if group["owner_domain"] == domain
            ),
        }
        for domain in ("base", "integration")
    }
    assert by_domain == {
        "base": {"groups": 11, "occurrences": 16},
        "integration": {"groups": 12, "occurrences": 12},
    }
    agent = [
        group for group in payload["groups"]
        if (group["method"], group["normalized_route"])
        in _plan_module().AGENT_STRUCTURAL_KEYS
    ]
    assert len(agent) == 4
    assert sum(len(group["occurrences"]) for group in agent) == 5
    assert all(group["current_status"] == "migrated" for group in agent)
    assert all(group["current_evidence"]["canonical_occurrences"] == [] for group in agent)


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


def test_manifest_conserves_all_source_proved_closures_to_zero_remainder(manifest):
    """Breaks if 14/17 closure is hand-authored instead of derived from immutable evidence."""
    _, payload = manifest

    assert payload["counts"] == {
        "groups": 14,
        "occurrences": 17,
        "migrated_groups": 9,
        "migrated_occurrences": 12,
        "removed_dead_entry_groups": 5,
        "removed_dead_entry_occurrences": 5,
        "unresolved_groups": 0,
        "unresolved_occurrences": 0,
    }
    assert payload["closure_arithmetic"] == {
        "baseline": {"groups": 14, "occurrences": 17},
        "closed": {"groups": 14, "occurrences": 17},
        "canonical_remainder": {"groups": 0, "occurrences": 0},
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
        ("GET", "/api/rule-engine/check-entry"),
        ("DELETE", "/api/lists/{dynamic}"),
        ("POST", "/api/approval/orders/{dynamic}/reject"),
        ("POST", "/api/flows/test-node"),
        ("POST", "/api/skills/canvas-options"),
        ("POST", "/api/skills/execute-canvas"),
        ("POST", "/api/skills/resume-canvas"),
        ("PUT", "/api/rules/{dynamic}"),
    }
    assert sum(len(entry["occurrences"]) for entry in migrated) == 12
    assert unresolved == []
    assert payload["frontend_revision"] == AGENT_FRONTEND_REVISION
    assert len(payload["entries"]) == 14
    assert all(entry["legacy_route_absent"] is True for entry in payload["entries"])


def test_manifest_preserves_craft_dispositions_and_closes_exact_agent_remainder(manifest):
    """Breaks on fake migration, hand-authored counts, or drift in any Agent occurrence."""
    module, payload = manifest
    prior = module._build_manifest.__globals__["_closure_baseline"]()[0]
    prior_agent = {
        (item["method"], item["normalized_route"]): item["final_occurrences"]
        for item in prior["entries"] if item["owner_domain"] == "agent"
    }
    entries = {
        (item["method"], item["normalized_route"]): item
        for item in payload["entries"]
    }

    assert payload["counts"] == {
        "groups": 14,
        "occurrences": 17,
        "migrated_groups": 9,
        "migrated_occurrences": 12,
        "removed_dead_entry_groups": 5,
        "removed_dead_entry_occurrences": 5,
        "unresolved_groups": 0,
        "unresolved_occurrences": 0,
    }
    assert payload["craft_closure_arithmetic"] == {
        "baseline": {"groups": 11, "occurrences": 14},
        "closed": {"groups": 7, "occurrences": 9},
        "canonical_remainder": {"groups": 4, "occurrences": 5},
    }

    dead = {
        ("DELETE", "/api/craft_lib/equipments/{dynamic}"),
        ("DELETE", "/api/craft_lib/fixtures/{dynamic}"),
        ("POST", "/api/rules/{dynamic}/activate"),
        ("POST", "/api/rules/{dynamic}/deviations"),
        ("POST", "/api/rules/{dynamic}/suspend"),
    }
    for key in dead:
        entry = entries[key]
        assert entry["final_disposition"] == "removed_dead_entry"
        assert entry["final_inventory_mapping"] == "removed_dead_entry"
        assert entry["candidate_capability"] is None
        assert entry["final_occurrences"] == []
        assert entry["dead_action_evidence"]["network_path_absent"] is True
        assert entry["dead_action_evidence"]["interactive_control_absent"] is True

    assert entries[("GET", "/api/rule-engine/check-entry")]["candidate_capability"] == "craft.rule.entry.evaluate@1"
    assert entries[("PUT", "/api/rules/{dynamic}")]["candidate_capability"] == "craft.rule.definition.change.apply@1"
    for key in (
        ("GET", "/api/rule-engine/check-entry"),
        ("PUT", "/api/rules/{dynamic}"),
    ):
        entry = entries[key]
        assert entry["final_disposition"] == "migrated"
        assert entry["provider_anchor"]
        assert entry["contract_evidence"]
        assert entry["gateway_evidence"]
        assert entry["frontend_call_sites"]

    current_agent = {key: entries[key]["occurrences"] for key in prior_agent}
    assert current_agent == prior_agent
    for key in prior_agent:
        entry = entries[key]
        assert entry["final_occurrences"] == []
        assert entry["final_disposition"] == "migrated"
        assert entry["final_inventory_mapping"] == "capability"
        assert entry["runtime_execution"] == "bounded_production_runtime"
        assert entry["provider_anchor"]
        assert entry["contract_evidence"]
        assert entry["gateway_evidence"]
        assert entry["owner_service_evidence"]
        assert entry["frontend_call_sites"]
        assert entry["legacy_route_absent"] is True
    assert payload["agent_closure_arithmetic"] == {
        "baseline": {"groups": 4, "occurrences": 5},
        "closed": {"groups": 4, "occurrences": 5},
        "canonical_remainder": {"groups": 0, "occurrences": 0},
    }


def test_manifest_closes_agent_to_exact_capabilities_and_preserves_project_outcomes(manifest):
    """Breaks if Agent uses generic targets or Project closure changes disposition."""
    _, payload = manifest
    entries = {
        (entry["method"], entry["normalized_route"]): entry
        for entry in payload["entries"]
    }
    assert {
        key: entries[key]["candidate_capability"] for key in (
            ("POST", "/api/flows/test-node"),
            ("POST", "/api/skills/canvas-options"),
            ("POST", "/api/skills/execute-canvas"),
            ("POST", "/api/skills/resume-canvas"),
        )
    } == {
        ("POST", "/api/flows/test-node"): "agent.workflow.node.test.execute@1",
        ("POST", "/api/skills/canvas-options"): "agent.canvas.options.resolve@1",
        ("POST", "/api/skills/execute-canvas"): "agent.canvas.execution.start@1",
        ("POST", "/api/skills/resume-canvas"): "agent.canvas.execution.resume@1",
    }
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


def test_manifest_validator_rejects_tampered_provider_contract_and_occurrence(manifest):
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
        entry = next(item for item in changed["entries"] if item["occurrences"])
        entry["occurrences"][0][field] = value
        assert "occurrence_evidence_mismatch" in module.validate_manifest_against_expected(changed, payload)
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
