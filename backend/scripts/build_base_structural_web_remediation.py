"""Build the independent Task 3B.3e Base structural remediation manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.check_web_capability_routes import build_report


BASELINE = "8ee5dc2340a9e77c5d84e8f84f733bb5415e9d08"
LEDGER_PATH = "docs/governance/web-route-root-cause-ledger.json"
ATOMIC_PATH = ROOT / "docs/governance/atomic-web-capability-contracts.json"
MIGRATION_PATH = ROOT / "docs/governance/existing-capability-web-migrations.json"
OUTPUT = ROOT / "docs/governance/base-structural-web-remediation.json"
SCOPE = {
    ("GET", "/api/org/teams"), ("GET", "/api/teams"),
    ("POST", "/api/plugin/install"), ("DELETE", "/api/plugin/uninstall/{dynamic}"),
    ("GET", "/api/self_ann/{dynamic}"), ("PUT", "/api/self_ann/{dynamic}"),
    ("GET", "/api/self_ann/batch"), ("GET", "/api/self_ann/list"),
    ("GET", "/api/users"), ("PATCH", "/api/users/{dynamic}/role"), ("GET", "/api/users/me"),
    ("GET", "/api/views"), ("POST", "/api/views"), ("DELETE", "/api/views/{dynamic}"),
    ("PATCH", "/api/views/{dynamic}"), ("POST", "/api/views/{dynamic}/copy"),
}
SAVED_VIEW_TARGETS = {
    ("GET", "/api/views"): "base.saved_view.search",
    ("POST", "/api/views"): "base.saved_view.create",
    ("PATCH", "/api/views/{dynamic}"): "base.saved_view.update",
    ("DELETE", "/api/views/{dynamic}"): "base.saved_view.delete",
    ("POST", "/api/views/{dynamic}/copy"): "base.saved_view.copy",
}
OWNER_SERVICE_TARGETS = {
    **SAVED_VIEW_TARGETS,
    ("GET", "/api/self_ann/{dynamic}"): "base.self_annotation.record.get",
    ("GET", "/api/self_ann/list"): "base.self_annotation.search",
    ("PUT", "/api/self_ann/{dynamic}"): "base.self_annotation.change.apply",
    ("GET", "/api/users/me"): "base.identity.session.profile.get",
    ("POST", "/api/plugin/install"): "base.plugin.installation.request.create",
    ("DELETE", "/api/plugin/uninstall/{dynamic}"): "base.plugin.installation.transition.uninstall",
    ("GET", "/api/org/teams"): "base.organization.team.directory.list",
    ("GET", "/api/self_ann/batch"): "base.self_annotation.batch.get",
    ("GET", "/api/teams"): "base.team.directory.list",
    ("GET", "/api/users"): "base.identity.admin_user.list",
    ("PATCH", "/api/users/{dynamic}/role"): "base.identity.role.assign.atomic",
}
OWNER_SERVICE_EVIDENCE = {
    **{key: ("backend/base/saved_views.py", ("search", "create", "update", "copy", "delete")) for key in SAVED_VIEW_TARGETS},
    ("GET", "/api/self_ann/{dynamic}"): ("backend/base/self_annotations.py", ("get",)),
    ("GET", "/api/self_ann/list"): ("backend/base/self_annotations.py", ("search",)),
    ("PUT", "/api/self_ann/{dynamic}"): ("backend/base/self_annotations.py", ("apply_change",)),
    ("GET", "/api/users/me"): ("backend/base/identity_profile.py", ("get_current",)),
    ("POST", "/api/plugin/install"): ("backend/plugin_platform/service.py", ("request_install",)),
    ("DELETE", "/api/plugin/uninstall/{dynamic}"): ("backend/plugin_platform/service.py", ("transition_uninstall",)),
    ("GET", "/api/org/teams"): ("backend/base/structural_web.py", ("list_organization_teams",)),
    ("GET", "/api/self_ann/batch"): ("backend/base/structural_web.py", ("annotation_batch",)),
    ("GET", "/api/teams"): ("backend/base/structural_web.py", ("list_teams",)),
    ("GET", "/api/users"): ("backend/base/structural_web.py", ("list_admin_users",)),
    ("PATCH", "/api/users/{dynamic}/role"): ("backend/base/structural_web.py", ("assign_user_role",)),
}
PLUGIN_FRONTEND_OPERATIONS = {
    ("POST", "/api/plugin/install"): "base.plugins.install",
    ("DELETE", "/api/plugin/uninstall/{dynamic}"): "base.plugins.uninstall",
}
ATOMIC_FRONTEND_OPERATIONS = {
    ("GET", "/api/org/teams"): "base.orgTeams.list",
    ("GET", "/api/self_ann/batch"): "base.annotations.batch",
    ("GET", "/api/teams"): "base.teams.list",
    ("GET", "/api/users"): "base.users.list",
    ("PATCH", "/api/users/{dynamic}/role"): "base.users.assignRole",
}


def _saved_view_boundary_ready(key: tuple[str, str], contract: dict[str, Any]) -> bool:
    """Prevent a saved-view route from being marked migrated without its owner boundary."""
    expected = SAVED_VIEW_TARGETS.get(key)
    if expected is None:
        return True
    from backend.base.saved_views import SavedViewService
    from backend.base.web_atomic import HANDLERS
    from backend.capability_v2.atomic_web_contracts import ROUTE_CAPABILITIES

    definition = ROUTE_CAPABILITIES.get(key, {})
    return (
        contract.get("capability_id") == expected
        and contract.get("major_version") == 1
        and definition.get("id") == expected
        and expected in HANDLERS
        and all(callable(getattr(SavedViewService, method, None)) for method in ("search", "create", "update", "copy", "delete"))
        and definition.get("schema", {}).get("additionalProperties") is False
        and definition.get("output_schema", {}).get("additionalProperties") is False
    )


def _owner_service_boundary_ready(key: tuple[str, str], contract: dict[str, Any]) -> bool:
    expected = OWNER_SERVICE_TARGETS.get(key)
    if expected is None:
        return True
    source, methods = OWNER_SERVICE_EVIDENCE[key]
    from backend.base.web_atomic import HANDLERS
    from backend.capability_v2.atomic_web_contracts import ROUTE_CAPABILITIES
    module = __import__(source.removesuffix(".py").replace("/", "."), fromlist=["*"])
    service_name = {
        "backend/base/self_annotations.py": "SelfAnnotationService",
        "backend/base/identity_profile.py": "IdentityProfileService",
        "backend/base/saved_views.py": "SavedViewService",
        "backend/plugin_platform/service.py": "PluginPlatformService",
    }.get(source)
    service = module if service_name is None else getattr(module, service_name)
    definition = ROUTE_CAPABILITIES.get(key, {})
    return (
        contract.get("capability_id") == expected and contract.get("major_version") == 1
        and definition.get("id") == expected and expected in HANDLERS
        and all(callable(getattr(service, method, None)) for method in methods)
        and definition.get("schema", {}).get("additionalProperties") is False
        and definition.get("output_schema", {}).get("additionalProperties") is False
    )


def _plugin_frontend_evidence(web_root: Path, key: tuple[str, str]) -> dict[str, Any]:
    operation = PLUGIN_FRONTEND_OPERATIONS[key]
    relative = "web/core/web_compat.js"
    source = (web_root / relative).read_text(encoding="utf-8")
    needle = f".call('{operation}'"
    offset = source.find(needle)
    if offset < 0:
        raise ValueError(f"plugin lifecycle frontend call missing: {operation}")
    line = source.count("\n", 0, offset) + 1
    line_start = source.rfind("\n", 0, offset) + 1
    return {
        "decision": "migrate", "target_capability_id": OWNER_SERVICE_TARGETS[key], "target_major_version": 1,
        "frontend_operation": operation,
        "frontend_call_sites": [{"source_path": relative, "line": line, "column": offset - line_start + 1,
                                   "operation": operation, "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()}],
        "equivalence_evidence": {"provider_contract": _source_evidence("backend/base/web_atomic.py")},
    }


def _atomic_frontend_evidence(
    web_root: Path, key: tuple[str, str], contract: dict[str, Any], occurrences: list[dict[str, Any]]
) -> dict[str, Any]:
    operation = ATOMIC_FRONTEND_OPERATIONS[key]
    target = contract["capability_id"]
    matcher = re.compile(rf"(?:\.call|_baseCall)\(\s*(['\"]){re.escape(operation)}\1")
    by_source: dict[str, list[dict[str, Any]]] = {}
    for occurrence in occurrences:
        by_source.setdefault(occurrence["source"], []).append(occurrence)
    call_sites = []
    for relative, source_occurrences in by_source.items():
        source = (web_root / relative).read_text(encoding="utf-8")
        matches = list(matcher.finditer(source))
        if len(matches) != len(source_occurrences):
            raise ValueError(
                f"atomic frontend consumer count mismatch: {operation} {relative} "
                f"expected={len(source_occurrences)} actual={len(matches)}"
            )
        for occurrence, match in zip(source_occurrences, matches, strict=True):
            offset = match.start() + match.group().index(operation)
            call_sites.append(_frontend_call_site(
                source, relative, offset, operation, matcher.pattern,
                occurrence["occurrence_id"],
            ))

    if len(call_sites) != len(occurrences):
        raise ValueError(f"atomic frontend consumer conservation failed: {operation} -> {target}")
    return {
        "decision": "migrate",
        "target_capability_id": target,
        "target_major_version": contract["major_version"],
        "frontend_operation": operation,
        "frontend_call_sites": call_sites,
        "equivalence_evidence": {"provider_contract": _source_evidence("backend/base/web_atomic.py")},
    }


def _frontend_call_site(
    source: str, relative: str, offset: int, operation: str, matcher: str,
    occurrence_id: str | None = None,
) -> dict[str, Any]:
    line = source.count("\n", 0, offset) + 1
    line_start = source.rfind("\n", 0, offset) + 1
    evidence = {
        "source_path": relative,
        "line": line,
        "column": offset - line_start + 1,
        "operation": operation,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }
    if matcher:
        evidence["operation_matcher"] = matcher
    if occurrence_id is not None:
        evidence["historical_occurrence_id"] = occurrence_id
    return evidence


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _source_evidence(relative_path: str) -> dict[str, str]:
    payload = (ROOT / relative_path).read_bytes()
    return {
        "source_path": relative_path,
        "source_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
    }


def _baseline() -> tuple[dict[str, Any], bytes]:
    result = subprocess.run(
        ["git", "show", f"{BASELINE}:{LEDGER_PATH}"], cwd=ROOT, check=True,
        capture_output=True,
    )
    return json.loads(result.stdout), result.stdout


def build_manifest(web_root: Path) -> dict[str, Any]:
    ledger, ledger_blob = _baseline()
    atomic = json.loads(ATOMIC_PATH.read_text(encoding="utf-8"))
    atomic_by_key = {(item["method"], item["normalized_route"]): item for item in atomic["entries"]}
    migration = json.loads(MIGRATION_PATH.read_text(encoding="utf-8"))
    migration_by_key = {
        (item["method"], item["normalized_route"]): item
        for item in migration["groups"]
    }
    report = json.loads(build_report(web_root.resolve()).json())
    unresolved = {(item["method"], item["normalized_route"]) for item in report["routes"] if item["disposition"] == "unresolved"}
    baseline_entries = {
        (item["method"], item["normalized_route"]): item
        for item in ledger["entries"]
        if (item["method"], item["normalized_route"]) in SCOPE
    }
    if set(baseline_entries) != SCOPE:
        raise ValueError("pinned Base structural scope drift")
    entries = []
    for key in sorted(SCOPE):
        source = baseline_entries[key]
        contract = atomic_by_key.get(key)
        if not contract:
            raise ValueError(f"atomic contract missing: {key}")
        migrated = contract["final_disposition"] == "migrated"
        if migrated and not _owner_service_boundary_ready(key, contract):
            raise ValueError(f"owner-service boundary evidence missing: {key}")
        owner_evidence = (
            _plugin_frontend_evidence(web_root, key) if key in PLUGIN_FRONTEND_OPERATIONS
            else _atomic_frontend_evidence(web_root, key, contract, source["occurrences"]) if key in ATOMIC_FRONTEND_OPERATIONS
            else migration_by_key.get(key) if key in OWNER_SERVICE_TARGETS else None
        )
        if owner_evidence is not None:
            expected_target = OWNER_SERVICE_TARGETS.get(key, contract["capability_id"])
            if (
                owner_evidence.get("decision") != "migrate"
                or owner_evidence.get("target_capability_id") != expected_target
                or owner_evidence.get("target_major_version") != 1
                or not owner_evidence.get("frontend_call_sites")
            ):
                raise ValueError(f"owner-service migration evidence missing: {key}")
        mapping = "unresolved" if key in unresolved else "capability"
        if migrated != (mapping == "capability"):
            raise ValueError(f"final mapping does not match contract: {key}")
        owner_source = OWNER_SERVICE_EVIDENCE[key][0] if key in OWNER_SERVICE_EVIDENCE else None
        owner_functions = OWNER_SERVICE_EVIDENCE[key][1] if key in OWNER_SERVICE_EVIDENCE else ()
        owner_service_evidence = _source_evidence(owner_source) if owner_evidence is not None else None
        if key in ATOMIC_FRONTEND_OPERATIONS and owner_service_evidence is not None:
            owner_service_evidence["function"] = owner_functions[0]
        entry = {
            "method": key[0],
            "normalized_route": key[1],
            "occurrences": source["occurrences"],
            "old_route_evidence": source["backend_evidence"],
            "authorization_and_scope": contract.get("authorization_policy") or "legacy route authorization retained; no safe provider contract",
            "candidate_capability": f"{contract['capability_id']}@{contract['major_version']}" if migrated else None,
            "provider_anchor": contract["provider_anchor"],
            "provider_source_sha256": contract["provider_source_sha256"],
            "owner_service_evidence": owner_service_evidence,
            "contract_evidence": (
                owner_evidence["equivalence_evidence"]["provider_contract"]
                if owner_evidence is not None else None
            ),
            "frontend_operation": (
                owner_evidence["frontend_operation"]
                if owner_evidence is not None else None
            ),
            "frontend_call_sites": (
                owner_evidence["frontend_call_sites"]
                if owner_evidence is not None else []
            ),
            "input_schema": contract["input_schema"],
            "output_schema": contract["output_schema"],
            "confirmation_policy": contract.get("confirmation_policy"),
            "idempotency_policy": contract.get("idempotency_policy"),
            "atomicity_class": contract.get("atomicity_class"),
            "final_disposition": "migrated" if migrated else "unresolved",
            "unresolved_reason": None if migrated else contract["reclassification_reason"],
            "final_inventory_mapping": mapping,
        }
        entries.append(entry)
    counts = {
        "groups": len(entries), "occurrences": sum(len(item["occurrences"]) for item in entries),
        "migrated_groups": sum(item["final_disposition"] == "migrated" for item in entries),
        "migrated_occurrences": sum(len(item["occurrences"]) for item in entries if item["final_disposition"] == "migrated"),
        "unresolved_groups": sum(item["final_disposition"] == "unresolved" for item in entries),
        "unresolved_occurrences": sum(len(item["occurrences"]) for item in entries if item["final_disposition"] == "unresolved"),
    }
    if counts != {"groups": 16, "occurrences": 33, "migrated_groups": 16, "migrated_occurrences": 33, "unresolved_groups": 0, "unresolved_occurrences": 0}:
        raise ValueError(f"Base structural count drift: {counts}")
    manifest = {
        "schema_version": "1.0.0", "artifact_id": "task-3b3e-base-structural-remediation",
        "source_ledger": LEDGER_PATH, "source_ledger_revision": BASELINE,
        "source_ledger_sha256": "sha256:" + hashlib.sha256(ledger_blob).hexdigest(),
        "frontend_revision": report["frontend_revision"], "frontend_content_hash": report["content_hash"],
        "atomic_contract_manifest_sha256": "sha256:" + hashlib.sha256(ATOMIC_PATH.read_bytes()).hexdigest(),
        "counts": counts, "entries": entries,
    }
    manifest["content_sha256"] = "sha256:" + hashlib.sha256(_canonical(manifest).encode()).hexdigest()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = _canonical(build_manifest(args.web_root))
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    if args.check and (not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered):
        raise SystemExit("Base structural remediation manifest is stale")
    payload = json.loads(rendered)
    print(" ".join(f"{key}={value}" for key, value in payload["counts"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
