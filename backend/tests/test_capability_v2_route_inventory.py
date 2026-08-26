from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from backend.capability_v2.consumer_routes import scan_web_routes
from backend.capability_v2.catalog_targets import CatalogTargetIndex
from backend.capability_v2.route_inventory import audit_route_inventory, load_route_inventory


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


def test_task3_legacy_addition_review_is_complete_and_traceable() -> None:
    root = Path(__file__).resolve().parents[2]
    review = json.loads(
        (root / "docs/governance/web-api-legacy-addition-review.json").read_text(
            encoding="utf-8"
        )
    )
    inventory = load_route_inventory(root / "docs/governance/legacy_route_inventory.json")
    targets = {
        (entry.method, entry.route_path): entry.migration_target_capability
        for entry in inventory.entries
    }
    original = [entry for entry in review["entries"] if entry["scope"] == "original_109"]
    retained = [entry for entry in original if entry["disposition"] == "retained"]
    removed = [entry for entry in original if entry["disposition"] == "removed"]

    assert review["baseline_revision"] == "565b00a0"
    assert len(original) == 109
    assert len(retained) == 90
    assert len(removed) == 19
    assert len(review["entries"]) == 113
    for entry in review["entries"]:
        key = (entry["method"], entry["route_path"])
        assert entry["reason"]
        assert entry["evidence_refs"]
        for reference in entry["evidence_refs"]:
            assert (root / reference.split("#", 1)[0]).is_file(), reference
        if entry["disposition"] == "retained":
            assert targets[key] == entry["target_capability"]
        else:
            assert key not in targets
