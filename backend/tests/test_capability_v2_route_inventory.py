from __future__ import annotations

import ast
import hashlib
import json
from collections import Counter
from dataclasses import replace
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


ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "docs/governance/web-route-root-cause-ledger.json"
CANONICAL_WEB_INVENTORY = ROOT / "docs/governance/capability-coverage-review/generated/web_route_inventory.json"
BASELINE_BACKEND_REVISION = "800ec6ba559db3301221e674b2a5026d354214ff"
BASELINE_INVENTORY_SHA256 = "55f3de074e060a71dc6acab4bee993d42d7af05026e6acd4c0e8d7f6d06b9694"


def _root_cause_ledger():
    return load_route_root_cause_ledger(LEDGER_PATH)


def _entry(ledger, method: str, route: str):
    return next(item for item in ledger.entries if item.key == (method, route))


def _replace_ledger_entry(ledger, replacement):
    return replace(
        ledger,
        entries=tuple(
            replacement if item.key == replacement.key else item
            for item in ledger.entries
        ),
    )


def test_canonical_web_inventory_has_no_unknown_method() -> None:
    inventory = json.loads(CANONICAL_WEB_INVENTORY.read_text(encoding="utf-8"))

    assert all(route.get("method") is not None for route in inventory["routes"])
    assert all("UNKNOWN:" not in route["occurrence_id"] for route in inventory["routes"])


def test_task3b3a_root_cause_ledger_covers_pinned_unresolved_evidence() -> None:
    ledger = _root_cause_ledger()

    assert ledger.baseline_unresolved_count == 148
    assert ledger.baseline_group_count == 93
    assert getattr(ledger, "baseline_backend_revision", None) == BASELINE_BACKEND_REVISION
    assert getattr(ledger, "baseline_inventory_sha256", None) == BASELINE_INVENTORY_SHA256
    baseline = [
        entry for entry in ledger.entries
        if getattr(entry, "occurrence_scope", None) == "baseline"
    ]
    assert sum(entry.occurrence_count for entry in baseline) == 148
    assert len(baseline) == 93
    assert audit_route_root_cause_ledger(ROOT, ledger) == ()


def test_task3b3a_ledger_rejects_replaced_baseline_occurrence() -> None:
    ledger = _root_cause_ledger()
    original = next(
        (
            entry for entry in ledger.entries
            if getattr(entry, "occurrence_scope", None) == "baseline"
        ),
        ledger.entries[0],
    )
    fabricated = dict(original.occurrences[0])
    fabricated["raw_route"] = str(fabricated["raw_route"]) + "-fabricated"
    replacement = replace(
        original,
        occurrences=(fabricated, *original.occurrences[1:]),
    )

    issues = audit_route_root_cause_ledger(
        ROOT, _replace_ledger_entry(ledger, replacement)
    )

    assert "ledger_baseline_occurrence_mismatch:1" in issues


def test_task3b3a_bff_requires_real_anchored_multi_capability_aggregation() -> None:
    ledger = _root_cause_ledger()
    bff_entries = [
        entry for entry in ledger.entries
        if entry.disposition == "truthful_bff_registered"
    ]

    assert {entry.key for entry in bff_entries} == {
        ("GET", "/api/workbench/home"),
        ("GET", "/api/workbench/panel1"),
    }
    assert all(len(entry.disposition_details["constituent_capabilities"]) >= 2 for entry in bff_entries)
    assert all(entry.backend_evidence["route_definition"] for entry in bff_entries)
    assert all(entry.disposition_details["aggregation_evidence"]["kind"] == "multi_result_merge" for entry in bff_entries)

    original = bff_entries[0]
    single = dict(original.disposition_details)
    single["constituent_capabilities"] = single["constituent_capabilities"][:1]
    issues = audit_route_root_cause_ledger(
        ROOT,
        _replace_ledger_entry(ledger, replace(original, disposition_details=single)),
    )
    assert f"ledger_bff_constituent_count_invalid:{original.method}:{original.normalized_route}" in issues

    generic = dict(original.disposition_details)
    generic["aggregation_evidence"] = "conditional dispatch is aggregation"
    issues = audit_route_root_cause_ledger(
        ROOT,
        _replace_ledger_entry(ledger, replace(original, disposition_details=generic)),
    )
    assert f"ledger_bff_aggregation_invalid:{original.method}:{original.normalized_route}" in issues


def test_task3b3a_conditional_dispatch_is_not_bff_aggregation() -> None:
    ledger = _root_cause_ledger()
    lists = _entry(ledger, "GET", "/api/lists")

    assert lists.disposition == "conditional_dispatch_migrated"
    assert lists.disposition_details["selector"] == "item_type"
    assert len(lists.disposition_details["branch_capabilities"]) == 2

    fake_bff = replace(
        lists,
        disposition="truthful_bff_required",
        disposition_details={
            "constituent_capabilities": lists.disposition_details["branch_capabilities"],
            "aggregation_evidence": {
                "kind": "conditional_dispatch",
                "anchor": lists.backend_evidence["route_definition"],
            },
        },
    )
    issues = audit_route_root_cause_ledger(
        ROOT, _replace_ledger_entry(ledger, fake_bff)
    )
    assert "ledger_bff_aggregation_invalid:GET:/api/lists" in issues


def test_task3b3a_retirement_proofs_cover_every_supported_evidence_kind() -> None:
    ledger = _root_cause_ledger()
    retired = [entry for entry in ledger.entries if entry.disposition == "frontend_retire"]
    kinds = Counter(
        entry.disposition_details.get("retirement_proof", {}).get("kind")
        for entry in retired
    )

    assert len(retired) == 17
    assert sum(entry.occurrence_count for entry in retired) == 21
    assert kinds == Counter({
        "explicit_product_retirement": 8,
        "backend_route_retired": 4,
        "http_410": 2,
        "sample_template_only": 2,
        "backend_route_absent": 1,
    })
    assert all(entry.disposition_details.get("retirement_proof", {}).get("anchors") for entry in retired)
    assert all(entry.disposition_details.get("retirement_proof", {}).get("final_sources") for entry in retired)


def test_task3b3a_retirement_rejects_empty_or_generic_proof() -> None:
    ledger = _root_cause_ledger()
    original = next(entry for entry in ledger.entries if entry.disposition == "frontend_retire")
    details = dict(original.disposition_details)
    proof = dict(details.get("retirement_proof", {}))
    proof["anchors"] = []
    proof["rationale"] = "reviewed"
    details["retirement_proof"] = proof

    issues = audit_route_root_cause_ledger(
        ROOT,
        _replace_ledger_entry(ledger, replace(original, disposition_details=details)),
    )

    assert f"ledger_retirement_proof_invalid:{original.method}:{original.normalized_route}" in issues


def test_task3b3a_promotes_every_finite_residual_to_a_first_class_group() -> None:
    ledger = _root_cause_ledger()
    derived = {
        entry.key: entry for entry in ledger.entries
        if getattr(entry, "occurrence_scope", None) == "post_normalization"
    }
    expected = {
        ("DELETE", "/api/knowledges/{dynamic}"),
        ("GET", "/api/knowledge/entries"),
        ("GET", "/api/knowledges/{dynamic}"),
        ("PATCH", "/api/knowledges/{dynamic}"),
        ("POST", "/api/knowledges"),
        ("PUT", "/api/knowledges/{dynamic}"),
        ("PUT", "/api/rules/{dynamic}"),
        ("POST", "/api/rules/{dynamic}/activate"),
        ("POST", "/api/rules/{dynamic}/suspend"),
    }

    assert set(derived) == expected
    assert sum(entry.occurrence_count for entry in derived.values()) == 13
    assert all(
        "residual_unresolved_routes" not in entry.disposition_details
        for entry in ledger.entries
        if entry.disposition == "frontend_route_normalize"
    )
    assert all(
        derived[key].backend_evidence["source_path"]
        == "plugins/craft/craft_backend/routers/rules.py"
        for key in {
            ("PUT", "/api/rules/{dynamic}"),
            ("POST", "/api/rules/{dynamic}/activate"),
            ("POST", "/api/rules/{dynamic}/suspend"),
        }
    )


def test_task3b3a_handler_evidence_is_existing_and_route_exact() -> None:
    ledger = _root_cause_ledger()
    plugin_list = _entry(ledger, "GET", "/api/plugin/list")

    assert plugin_list.backend_evidence["source_path"] == "backend/routers/plugins.py"
    assert plugin_list.backend_evidence["handler_status"] == "registered"
    assert plugin_list.backend_evidence["route_definition"]["method"] == "GET"
    assert plugin_list.backend_evidence["route_definition"]["normalized_route"] == "/api/plugin/list"

    missing = dict(plugin_list.backend_evidence)
    missing["source_path"] = "backend/routers/not_a_real_handler.py"
    issues = audit_route_root_cause_ledger(
        ROOT,
        _replace_ledger_entry(ledger, replace(plugin_list, backend_evidence=missing)),
    )
    assert "ledger_handler_path_missing:GET:/api/plugin/list" in issues

    wrong = dict(plugin_list.backend_evidence)
    wrong_definition = dict(wrong["route_definition"])
    wrong_definition["method"] = "POST"
    wrong["route_definition"] = wrong_definition
    issues = audit_route_root_cause_ledger(
        ROOT,
        _replace_ledger_entry(ledger, replace(plugin_list, backend_evidence=wrong)),
    )
    assert "ledger_handler_route_mismatch:GET:/api/plugin/list" in issues


def test_task3b3d_file_store_candidate_is_governed_without_operations_approval() -> None:
    ledger = _root_cause_ledger()
    operations = [
        entry for entry in ledger.entries
        if entry.disposition == "operations_candidate"
    ]
    flow_test = _entry(ledger, "POST", "/api/flows/test-node")

    file_store = _entry(ledger, "GET", "/api/file-store/config")
    assert operations == []
    assert file_store.disposition == "file_store_capability_migrated"
    assert file_store.owner_domain == "base"
    assert file_store.disposition_details["target_capability"] == "base.file_store.public_config.get@1"
    assert file_store.disposition_details["public_projection"] == "secret_filtered_closed_schema"
    assert flow_test.disposition == "new_atomic_capability_required"
    assert flow_test.owner_domain == "agent"


def test_task3b3d_file_store_validator_rejects_weak_capability_evidence() -> None:
    ledger = _root_cause_ledger()
    original = _entry(ledger, "GET", "/api/file-store/config")
    details = dict(original.disposition_details)
    details["target_capability"] = "base.fake@1"
    weak = replace(
        original,
        disposition_details=details,
    )

    issues = audit_route_root_cause_ledger(
        ROOT, _replace_ledger_entry(ledger, weak)
    )

    assert "ledger_file_store_capability_invalid:GET:/api/file-store/config" in issues


def test_task3b3c_reviewed_disposition_totals_are_exact() -> None:
    ledger = _root_cause_ledger()
    groups = Counter(entry.disposition for entry in ledger.entries)
    occurrences = Counter()
    for entry in ledger.entries:
        occurrences[entry.disposition] += entry.occurrence_count

    assert len(ledger.entries) == 102
    assert sum(entry.occurrence_count for entry in ledger.entries) == 161
    assert groups == Counter({
        "existing_capability_reclassified": 35,
        "existing_capability_migrated": 19,
        "frontend_retire": 17,
        "frontend_route_normalize": 15,
        "new_atomic_capability_required": 5,
        "existing_stable_capability": 5,
        "conditional_dispatch_migrated": 3,
        "truthful_bff_registered": 2,
        "file_store_capability_migrated": 1,
    })
    assert occurrences == Counter({
        "existing_capability_reclassified": 54,
        "existing_capability_migrated": 27,
        "frontend_route_normalize": 23,
        "frontend_retire": 21,
        "conditional_dispatch_migrated": 20,
        "existing_stable_capability": 7,
        "new_atomic_capability_required": 6,
        "truthful_bff_registered": 2,
        "file_store_capability_migrated": 1,
    })


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
