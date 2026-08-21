from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from backend.capability_v2.consumer_routes import scan_web_routes
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
