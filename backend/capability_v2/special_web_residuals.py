"""Independent evidence audit for Task 3B.3d's six special Web residuals."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCOPED = (
    ("DELETE", "/api/lists/{dynamic}", "conditional_dispatch", (
        "project.list.change.apply.atomic.lists_delete",
    )),
    ("GET", "/api/lists", "conditional_dispatch", (
        "project.list.read.atomic.lists_search",
    )),
    ("PATCH", "/api/lists/{dynamic}", "conditional_dispatch", (
        "project.list.change.apply.atomic.lists_update", "project.list.change.apply.atomic.lists_delete",
    )),
    ("GET", "/api/workbench/home", "truthful_bff", (
        "project.project.read.atomic.projects_search", "project.follow.read.atomic.follows_list",
    )),
    ("GET", "/api/workbench/panel1", "truthful_bff", (
        "project.task.read.atomic.tasks_search", "project.issue.read.atomic.issues_search",
    )),
    ("GET", "/api/file-store/config", "file_store_capability", (
        "base.file_store.public_config.get",
    )),
)

REST_RECLASSIFIED = {
    ("GET", "/api/lists"): [
        {"selector_value": "bop_version", "transport": "GET /api/lists?item_type=bop_version"},
    ],
    ("DELETE", "/api/lists/{dynamic}"): [
        {"selector_value": "bop_version", "transport": "DELETE /api/lists/{gid}?item_type=bop_version&expected_revision={revision}"},
    ],
}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def audit_manifest(root: Path, manifest: dict[str, Any]) -> tuple[str, ...]:
    failures: list[str] = []
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(entries) != 6:
        return ("scope_group_count",)
    expected = {(method, route): (kind, targets) for method, route, kind, targets in SCOPED}
    ledger = _json(root / "docs/governance/web-route-root-cause-ledger.json")
    ledger_entries = {(entry["method"], entry["normalized_route"]): entry for entry in ledger["entries"]}
    catalog_ids = {item["id"] for item in _json(root / "docs/capabilities/catalog.v2.json")["capabilities"]}
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (entry.get("method"), entry.get("normalized_route"))
        if key not in expected or key in seen:
            failures.append(f"unexpected_entry:{key}")
            continue
        seen.add(key)
        kind, targets = expected[key]
        if entry.get("kind") != kind:
            failures.append(f"kind:{key}")
        field = "branch_capabilities" if kind == "conditional_dispatch" else ("constituents" if kind == "truthful_bff" else "capabilities")
        actual_targets = entry.get(field)
        normalized = tuple(
            item.get("capability_id") if isinstance(item, dict) else item
            for item in (actual_targets or [])
        )
        if normalized != targets or any(target not in catalog_ids for target in normalized):
            failures.append(f"target:{key}")
        if entry.get("reclassified_rest_branches", []) != REST_RECLASSIFIED.get(key, []):
            failures.append(f"rest_reclassification:{key}")
        baseline = ledger_entries.get(key, {}).get("occurrences", [])
        if entry.get("baseline_occurrences") != baseline:
            failures.append(f"baseline_occurrences:{key}")
    if seen != set(expected):
        failures.append("scope_keys")
    counts = manifest.get("counts", {})
    if sum(len(entry.get("baseline_occurrences", [])) for entry in entries) != 23:
        failures.append("occurrence_count")
    expected_counts = {
        "conditional_dispatch": {"groups": 3, "occurrences": 20},
        "truthful_bff": {"groups": 2, "occurrences": 2},
        "file_store_capability": {"groups": 1, "occurrences": 1},
    }
    if counts != expected_counts:
        failures.append("counts")
    if manifest.get("final_outcomes") != {
        "fully_governed": {"groups": 4, "baseline_occurrences": 9},
        "mixed_gateway_and_reclassified_rest": {"groups": 2, "baseline_occurrences": 14},
    }:
        failures.append("final_outcomes")
    inventory = root / "docs/governance/capability-coverage-review/generated/web_route_inventory.json"
    if manifest.get("final_inventory_sha256") != _sha(inventory):
        failures.append("final_inventory_sha256")
    return tuple(sorted(set(failures)))


def build_manifest(root: Path) -> dict[str, Any]:
    ledger = _json(root / "docs/governance/web-route-root-cause-ledger.json")
    indexed = {(entry["method"], entry["normalized_route"]): entry for entry in ledger["entries"]}
    bff = {entry["route_path"]: entry for entry in _json(root / "docs/governance/bff_capability_registry.json")["entries"]}
    entries = []
    for method, route, kind, targets in SCOPED:
        value: dict[str, Any] = {
            "method": method,
            "normalized_route": route,
            "kind": kind,
            "baseline_occurrences": indexed[(method, route)]["occurrences"],
        }
        if kind == "conditional_dispatch":
            value["branch_capabilities"] = list(targets)
            value["reclassified_rest_branches"] = REST_RECLASSIFIED.get((method, route), [])
        elif kind == "truthful_bff":
            value["constituents"] = bff[route]["constituents"]
            value["bff_registry_source_sha256"] = bff[route]["source_sha256"]
        else:
            value["capabilities"] = list(targets)
        entries.append(value)
    return {
        "schema_version": 1,
        "artifact_id": "task-3b3d-special-web-residual-contracts",
        "baseline_backend_revision": "5c5c4439a2dd33a1d90afd926f12f53fa5741f8d",
        "baseline_frontend_revision": "af7f8e1f71e11c3f255bcf632d8eb91d8a0f86f1",
        "final_frontend_revision": "3c6ad771d4e20f65ff2fff108ab8b2a3e4680941",
        "counts": {
            "conditional_dispatch": {"groups": 3, "occurrences": 20},
            "truthful_bff": {"groups": 2, "occurrences": 2},
            "file_store_capability": {"groups": 1, "occurrences": 1},
        },
        "final_outcomes": {
            "fully_governed": {"groups": 4, "baseline_occurrences": 9},
            "mixed_gateway_and_reclassified_rest": {"groups": 2, "baseline_occurrences": 14},
        },
        "final_inventory_sha256": _sha(root / "docs/governance/capability-coverage-review/generated/web_route_inventory.json"),
        "entries": entries,
    }


__all__ = ["SCOPED", "audit_manifest", "build_manifest"]
