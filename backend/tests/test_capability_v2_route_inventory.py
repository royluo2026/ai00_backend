from __future__ import annotations

import ast
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from backend.capability_v2.consumer_routes import normalize_route, scan_web_routes
from backend.capability_v2.catalog_targets import CatalogTargetIndex
from backend.capability_v2.route_inventory import (
    audit_route_inventory,
    load_legacy_route_baseline,
    load_route_inventory,
)
from backend.capability_v2.route_root_cause_ledger import (
    audit_route_root_cause_ledger,
    load_route_root_cause_ledger,
)


def test_task3b3a_root_cause_ledger_covers_pinned_unresolved_evidence() -> None:
    root = Path(__file__).resolve().parents[2]
    ledger = load_route_root_cause_ledger(
        root / "docs/governance/web-route-root-cause-ledger.json"
    )

    assert ledger.baseline_unresolved_count == 148
    assert ledger.baseline_group_count == 93
    assert sum(entry.occurrence_count for entry in ledger.entries) == 148
    assert len(ledger.entries) == 93
    assert audit_route_root_cause_ledger(root, ledger) == ()


def test_route_scan_excludes_named_generated_dist_outputs(tmp_path: Path) -> None:
    web = tmp_path / "web"
    (web / "dist-production").mkdir(parents=True)
    (web / "src").mkdir()
    (web / "dist-production" / "bundle.js").write_text("fetch('/api/bop/generated');", encoding="utf-8")
    (web / "src" / "app.js").write_text("fetch('/api/bop/source');", encoding="utf-8")

    report = scan_web_routes(tmp_path, roots=["web"], legacy_prefixes=["/api/bop"])

    assert [item.route for item in report.routes] == ["/api/bop/source"]


def test_route_inventory_validates_deadline_and_target(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({
        "inventory_kind": "legacy_rest",
        "entries": [{
            "route_path": "/api/bop/entries", "method": "GET", "owner": "craft",
            "migration_target_capability": "craft.bop.read", "migration_deadline": date.today().isoformat(),
            "source": "plugins/craft/craft_backend/routers/bop.py", "allowed_consumers": ["web"],
        }],
    }), encoding="utf-8")

    inventory = load_route_inventory(path)

    assert inventory.entries[0].migration_target_capability == "craft.bop.read"
    assert audit_route_inventory(inventory) == ()


def test_route_inventory_reports_expired_unapproved_route(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({
        "inventory_kind": "bff",
        "entries": [{
            "route_path": "/api/legacy", "method": "POST", "owner": "craft",
            "migration_target_capability": "craft.legacy.write", "migration_deadline":
            (date.today() - timedelta(days=1)).isoformat(), "source": "web/app.js",
        }],
    }), encoding="utf-8")

    assert audit_route_inventory(load_route_inventory(path)) == ("expired:POST:/api/legacy",)


def test_route_inventory_blocks_deprecated_target(tmp_path: Path) -> None:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({
        "inventory_kind": "legacy_rest",
        "entries": [{
            "route_path": "/api/legacy", "method": "GET", "owner": "craft",
            "migration_target_capability": "craft.legacy.read", "migration_deadline": "2099-01-01",
            "source": "web/app.js",
        }],
    }), encoding="utf-8")
    catalog_index = CatalogTargetIndex.from_catalog({"capabilities": [{
        "id": "craft.legacy.read", "major_version": 1,
        "lifecycle_status": "deprecated", "owner_domain": "craft",
    }]})

    failures = audit_route_inventory(load_route_inventory(path), catalog_index=catalog_index)

    assert failures[0].reason_code == "target_not_stable"
    assert failures[0].entry.route_path == "/api/legacy"


def test_reviewed_ai_routes_match_exact_handler_invocations() -> None:
    root = Path(__file__).resolve().parents[2]
    inventory = load_route_inventory(root / "docs/governance/legacy_route_inventory.json")
    targets = {
        (entry.method, entry.route_path): entry.migration_target_capability
        for entry in inventory.entries
    }

    assert targets[("POST", "/api/ai/chat")] == "agent.interaction.chat.change.apply"
    assert targets[("POST", "/api/ai/chat/stream")] == "agent.interaction.chat.change.apply"
    assert targets[("POST", "/api/ai/confirm/sync")] == "agent.interaction.chat.change.apply"
    assert targets[("POST", "/api/ai/abort")] == "agent.interaction.cancel"
    assert ("GET", "/api/ai/balance") not in targets


def test_lark_business_routes_are_registered_not_operations_excluded() -> None:
    root = Path(__file__).resolve().parents[2]
    inventory = load_route_inventory(root / "docs/governance/legacy_route_inventory.json")
    targets = {
        (entry.method, entry.route_path): entry.migration_target_capability
        for entry in inventory.entries
    }
    operations = json.loads(
        (root / "docs/governance/web-api-operations-exclusions.json").read_text(
            encoding="utf-8"
        )
    )["entries"]
    operation_keys = {
        (entry["route_method"], entry["normalized_route"]) for entry in operations
    }

    for transport in ("lark-sheets", "lark-bitable"):
        assert targets[("POST", f"/api/import-export/{transport}/read")] == (
            "craft.data_exchange.lark.read"
        )
        assert targets[("POST", f"/api/import-export/{transport}/write")] == (
            "craft.data_exchange.lark.write"
        )
        assert ("POST", f"/api/import-export/{transport}/read") not in operation_keys
        assert ("POST", f"/api/import-export/{transport}/write") not in operation_keys


def test_unapproved_file_store_read_is_not_operations_excluded() -> None:
    root = Path(__file__).resolve().parents[2]
    operations = json.loads(
        (root / "docs/governance/web-api-operations-exclusions.json").read_text(
            encoding="utf-8"
        )
    )["entries"]

    assert ("GET", "/api/file-store/config") not in {
        (entry["route_method"], entry["normalized_route"])
        for entry in operations
    }


def test_round4_exact_adapter_families_have_governed_targets() -> None:
    root = Path(__file__).resolve().parents[2]
    inventory = load_route_inventory(root / "docs/governance/legacy_route_inventory.json")
    targets = {
        (entry.method, entry.route_path): entry.migration_target_capability
        for entry in inventory.entries
    }
    expected = {
        ("GET", "/api/tasks"): "project.task.read.atomic.tasks_search",
        ("POST", "/api/tasks"): "project.task.change.apply.atomic.tasks_create",
        ("PUT", "/api/tasks/{gid}"): "project.task.change.apply.atomic.tasks_update",
        ("GET", "/api/issues"): "project.issue.read.atomic.issues_search",
        ("POST", "/api/issues"): "project.issue.change.apply.atomic.issues_create",
        ("GET", "/api/task-dependencies"): "project.task.read.atomic.task_dependencies_list",
        ("POST", "/api/task-dependencies"): "project.task.change.apply.atomic.task_dependencies_create",
        ("POST", "/api/lists"): "project.list.change.apply.atomic.lists_create",
        ("GET", "/api/follows"): "project.follow.read.atomic.follows_list",
        ("POST", "/api/follows"): "project.follow.change.apply.atomic.follows_create",
        ("GET", "/api/notifications"): "project.notification.read.atomic.notifications_list",
        ("PATCH", "/api/notifications/read_all"): "project.notification.change.apply.atomic.notifications_mark_all_read",
        ("GET", "/api/approval/orders"): "project.approval.read.atomic.approval_orders_search",
        ("POST", "/api/approval/orders/{gid}/start"): "project.approval.change.apply.atomic.approval_orders_start",
        ("GET", "/api/change-logs"): "project.change_log.read.atomic.change_logs_search",
        ("GET", "/api/knowledge_entries"): "knowledge.search",
        ("POST", "/api/knowledge_entries"): "knowledge.entry.change.apply.atomic.entries_create",
        ("GET", "/api/knowledge_hub/items"): "knowledge.hub.read.atomic.items_list",
        ("POST", "/api/knowledge_hub/items"): "knowledge.hub.change.apply.atomic.items_create",
        ("GET", "/api/knowledge_hub/recent"): "knowledge.personalization.read.atomic.recent_list",
        ("GET", "/api/ebom/vpps_check"): "craft.ebom.vpps_check.read",
        ("GET", "/api/rules"): "craft.rule.library.read",
        ("GET", "/api/import-export/templates"): "base.export_template.read",
        ("POST", "/api/import-export/export/excel"): "craft.data_exchange.export",
        ("POST", "/api/ai/confirm"): "agent.interaction.chat.change.apply",
    }

    assert {key: targets.get(key) for key in expected} == expected


def test_task3_legacy_addition_review_is_complete_and_traceable() -> None:
    root = Path(__file__).resolve().parents[2]
    review = json.loads(
        (root / "docs/governance/web-api-legacy-addition-review.json").read_text(
            encoding="utf-8"
        )
    )
    inventory = load_route_inventory(root / "docs/governance/legacy_route_inventory.json")
    targets = {
        (entry.method, entry.route_path): (
            entry.migration_target_capability,
            entry.migration_target_major_version,
        )
        for entry in inventory.entries
    }
    catalog = json.loads(
        (root / "docs/capabilities/catalog.v2.json").read_text(encoding="utf-8")
    )
    catalog_targets = {
        (entry["id"], entry["major_version"]): entry["lifecycle_status"]
        for entry in catalog["capabilities"]
    }
    atomicity = json.loads(
        (root / "docs/governance/capability-atomicity-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    replacements = {
        (entry["capability_id"], entry["major_version"]): set(
            entry["replacement_capabilities"]
        )
        for entry in atomicity["dispositions"]
        if entry["disposition"] == "split"
    }
    original = [entry for entry in review["entries"] if entry["scope"] == "original_109"]
    retained = [entry for entry in original if entry["disposition"] == "retained"]
    removed = [entry for entry in original if entry["disposition"] == "removed"]

    assert review["baseline_revision"] == "565b00a0"
    assert len(original) == 109
    assert review["original_retained_count"] == len(retained)
    assert review["original_removed_count"] == len(removed)
    assert review["retained_count"] == len(
        [entry for entry in review["entries"] if entry["disposition"] == "retained"]
    )
    assert review["removed_count"] == len(
        [entry for entry in review["entries"] if entry["disposition"] == "removed"]
    )
    round_4_re_retained = [
        entry
        for entry in review["entries"]
        if entry.get("round_4_change") == "re_retained"
    ]
    round_4_new = [
        entry
        for entry in review["entries"]
        if entry.get("round_4_change") == "new"
    ]
    assert review["round_4_re_retained_count"] == len(round_4_re_retained) == 35
    assert review["round_4_new_count"] == len(round_4_new) == 41
    assert review["round_4_delta_count"] == (
        len(round_4_re_retained) + len(round_4_new)
    ) == 76
    assert all(entry["disposition"] == "retained" for entry in round_4_re_retained)
    assert all(entry["scope"] == "fix_round_4" for entry in round_4_new)
    for entry in review["entries"]:
        key = (entry["method"], entry["route_path"])
        assert entry["reason"]
        if entry["disposition"] == "retained":
            target = entry["target_capability"]
            major = entry["target_major_version"]
            assert targets[key] == (target, major)
            assert catalog_targets[(target, major)] == "stable"
            evidence = entry["evidence"]
            assert evidence["kind"] in {
                "capability_invocation",
                "exact_delegation",
                "atomic_composition_invocation",
                "facade_operation_invocation",
                "facade_operation_delegation",
                "facade_operation_delegation_chain",
            }

            def anchored_text(anchor: dict) -> str:
                assert set(anchor) == {
                    "source_path", "start_line", "end_line", "sha256"
                }
                source_path = root / anchor["source_path"]
                assert source_path.is_file(), source_path
                lines = source_path.read_text(encoding="utf-8").splitlines(keepends=True)
                assert 1 <= anchor["start_line"] <= anchor["end_line"] <= len(lines)
                text = "".join(lines[anchor["start_line"] - 1:anchor["end_line"]])
                assert hashlib.sha256(text.encode("utf-8")).hexdigest() == anchor["sha256"]
                return text

            handler = anchored_text(evidence["handler"])

            def exact_calls(source: str) -> set[str]:
                tree = ast.parse(source)
                return {
                    ast.get_source_segment(source, node)
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                }

            if evidence["kind"] == "capability_invocation":
                invocation = evidence["expected_target_invocation"]
                assert target in invocation
                assert invocation in exact_calls(handler)
            elif evidence["kind"] == "exact_delegation":
                symbol = evidence["delegation_symbol"]
                delegation = evidence["expected_delegation"]
                binding = anchored_text(evidence["binding"])
                target_binding = evidence["expected_target_binding"]
                assert symbol in delegation and delegation in exact_calls(handler)
                assert f"def {symbol}" in binding
                assert target in target_binding
                assert target_binding in exact_calls(binding)
            else:
                facade = evidence["facade_capability"]
                operation = evidence["operation"]
                assert target == f"{facade}.atomic.{operation.replace('.', '_')}"
                assert target in replacements[(facade, major)]
                if evidence["kind"] == "atomic_composition_invocation":
                    invocation = evidence["expected_facade_invocation"]
                    symbol = evidence["composition_symbol"]
                    binding = anchored_text(evidence["binding"])
                    construction = evidence["expected_target_construction"]
                    assert facade in invocation and operation in invocation
                    assert symbol in invocation and invocation in exact_calls(handler)
                    assert f"def {symbol}" in binding
                    assert construction in binding
                elif evidence["kind"] == "facade_operation_invocation":
                    invocation = evidence["expected_facade_invocation"]
                    assert facade in invocation and operation in invocation
                    assert invocation in exact_calls(handler)
                elif evidence["kind"] == "facade_operation_delegation_chain":
                    symbol = evidence["delegation_symbol"]
                    delegation = evidence["expected_delegation"]
                    bridge = anchored_text(evidence["bridge"])
                    facade_symbol = evidence["facade_symbol"]
                    bridge_delegation = evidence["expected_bridge_delegation"]
                    binding = anchored_text(evidence["binding"])
                    facade_binding = evidence["expected_facade_binding"]
                    assert symbol in delegation and operation in delegation
                    assert delegation in exact_calls(handler)
                    assert f"def {symbol}" in bridge
                    assert facade_symbol in bridge_delegation
                    assert bridge_delegation in exact_calls(bridge)
                    assert f"def {facade_symbol}" in binding
                    assert facade in facade_binding
                    assert facade_binding in exact_calls(binding)
                else:
                    symbol = evidence["delegation_symbol"]
                    delegation = evidence["expected_delegation"]
                    binding = anchored_text(evidence["binding"])
                    facade_binding = evidence["expected_facade_binding"]
                    assert symbol in delegation and operation in delegation
                    assert delegation in exact_calls(handler)
                    assert f"def {symbol}" in binding
                    assert facade in facade_binding
                    assert facade_binding in exact_calls(binding)
        else:
            assert key not in targets


def test_current_legacy_proofs_biject_exactly_to_immutable_baseline_difference() -> None:
    root = Path(__file__).resolve().parents[2]
    baseline = load_legacy_route_baseline(
        root / "docs/governance/legacy_route_baseline.json"
    )
    inventory = load_route_inventory(
        root / "docs/governance/legacy_route_inventory.json"
    )
    review = json.loads(
        (root / "docs/governance/web-api-legacy-addition-review.json").read_text(
            encoding="utf-8"
        )
    )
    current_keys = {
        (entry.method, normalize_route(entry.route_path))
        for entry in inventory.entries
    }
    active_proof_keys = {
        (entry["method"], normalize_route(entry["route_path"]))
        for entry in review["entries"]
        if entry["disposition"] == "retained"
    }

    assert current_keys - baseline.key_set == active_proof_keys
    assert len(active_proof_keys) == review["retained_count"] == 137
