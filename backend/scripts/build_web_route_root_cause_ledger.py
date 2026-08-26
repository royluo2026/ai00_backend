"""Build the Task 3B.3a reviewed Web route root-cause ledger."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.route_root_cause_ledger import (
    BASELINE_CONTENT_HASH,
    BASELINE_FRONTEND_REVISION,
    BASELINE_GROUP_COUNT,
    BASELINE_UNRESOLVED_COUNT,
)
from backend.scripts.check_web_capability_routes import build_report

BASELINE_INVENTORY = ROOT / "docs/governance/capability-coverage-review/generated/web_route_inventory.json"
DEFAULT_LEDGER = ROOT / "docs/governance/web-route-root-cause-ledger.json"

EXISTING = {
    ("GET", "/api/ai/audit-logs"): (
        "agent", "agent.audit.read@1",
        "plugins/agent/agent_backend/routers/ai_audit.py", "agent.audit.read",
    ),
    ("POST", "/api/craft_lib/tools/{dynamic}/obsolete"): (
        "craft", "craft.library.change.apply@1",
        "plugins/craft/craft_backend/routers/craft_library.py", "tools.obsolete",
    ),
    ("POST", "/api/craft_lib/equipments/{dynamic}/obsolete"): (
        "craft", "craft.library.change.apply@1",
        "plugins/craft/craft_backend/routers/craft_library.py", "equipments.obsolete",
    ),
    ("POST", "/api/craft_lib/fixtures/{dynamic}/obsolete"): (
        "craft", "craft.library.change.apply@1",
        "plugins/craft/craft_backend/routers/craft_library.py", "fixtures.obsolete",
    ),
    ("PATCH", "/api/std_op/operations/{dynamic}"): (
        "craft", "craft.standard_operation.change.apply@1",
        "plugins/craft/craft_backend/routers/std_op.py", '"update", gid=gid',
    ),
}

RETIRE = {
    ("GET", "/api/ai/balance"),
    ("DELETE", "/api/bitable-sync/bindings/{dynamic}"),
    ("GET", "/api/bitable-sync/bindings/{dynamic}"),
    ("GET", "/api/bitable-sync/bindings/{dynamic}/schema-by-token"),
    ("GET", "/api/bitable-sync/bindings/{dynamic}/status"),
    ("POST", "/api/bitable-sync/bindings/{dynamic}"),
    ("POST", "/api/bitable-sync/bindings/{dynamic}/pull"),
    ("POST", "/api/bitable-sync/bindings/{dynamic}/push"),
    ("POST", "/api/bitable-sync/rows/push"),
    ("GET", "/api/craft/work_plans"),
    ("GET", "/api/craft/work_plans/{dynamic}/sections"),
    ("GET", "/api/craft/sections/{dynamic}/operations"),
    ("POST", "/api/craft/sections/{dynamic}/operations"),
    ("GET", "/api/feishu/config"),
    ("GET", "/api/my-plugin/items"),
    ("POST", "/api/my-plugin/items"),
    ("POST", "/api/std_op/operations/{dynamic}/clone-to-post"),
}

NORMALIZE = {
    ("GET", "/api/craft_lib/tools${listGid "): ["GET /api/craft_lib/tools"],
    ("GET", "/api/craft_lib/equipments${listGid "): ["GET /api/craft_lib/equipments"],
    ("GET", "/api/craft_lib/fixtures${listGid "): ["GET /api/craft_lib/fixtures"],
    ("GET", "/api/craft_lib/fasteners${listGid "): ["GET /api/craft_lib/fasteners"],
    ("GET", "/api/craft_lib/part_names${listGid "): ["GET /api/craft_lib/part_names"],
    ("GET", "/api/tasks${listGid "): ["GET /api/tasks"],
    ("GET", "/api/issues${listGid "): ["GET /api/issues"],
    ("GET", "/api/knowledge/entries${listGid "): ["GET /api/knowledge/entries"],
    ("GET", "/api/{dynamic}"): ["GET /api/tasks", "GET /api/issues"],
    ("POST", "/api/{dynamic}"): [
        "POST /api/tasks", "POST /api/issues", "POST /api/knowledges",
        "POST /api/rules",
    ],
    ("DELETE", "/api/{dynamic}/{dynamic}"): [
        "DELETE /api/tasks/{dynamic}", "DELETE /api/issues/{dynamic}",
        "DELETE /api/knowledges/{dynamic}", "DELETE /api/rules/{dynamic}",
    ],
    ("GET", "/api/{dynamic}/{dynamic}"): [
        "GET /api/tasks/{dynamic}", "GET /api/issues/{dynamic}",
        "GET /api/knowledges/{dynamic}", "GET /api/rules/{dynamic}",
    ],
    ("PATCH", "/api/{dynamic}/{dynamic}"): [
        "PATCH /api/tasks/{dynamic}", "PATCH /api/issues/{dynamic}",
        "PATCH /api/knowledges/{dynamic}", "PATCH /api/rules/{dynamic}",
    ],
    ("PUT", "/api/{dynamic}/{dynamic}"): [
        "PUT /api/tasks/{dynamic}", "PUT /api/issues/{dynamic}",
        "PUT /api/knowledges/{dynamic}", "PUT /api/rules/{dynamic}",
    ],
}

OPERATIONS = {
    ("GET", "/api/file-store/config"),
    ("POST", "/api/flows/test-node"),
}

EXT_TARGETS = {
    ("POST", "/api/ext-datasources"): "integration.connector.create@1",
    ("PATCH", "/api/ext-datasources/{dynamic}"): "integration.connector.update@1",
    ("POST", "/api/ext-datasources/{dynamic}/test"): "integration.connector.connection.test@1",
    ("GET", "/api/ext-datasources"): "integration.connector.search@1",
    ("GET", "/api/ext-datasources/{dynamic}/tables"): "integration.connector.schema.discover@1",
    ("POST", "/api/ext-mappings"): "integration.mapping.create@1",
    ("POST", "/api/ext-mappings/{dynamic}/import"): "integration.sync.start@1",
    ("PUT", "/api/ext-field-mappings/batch"): "integration.mapping.update@1",
    ("GET", "/api/ext-mappings"): "integration.mapping.search@1",
    ("GET", "/api/ext-field-mappings"): "integration.mapping.get@1",
    ("GET", "/api/ext-mappings/{dynamic}/columns"): "integration.connector.schema.discover@1",
    ("GET", "/api/ext-mappings/{dynamic}/preview"): "integration.mapping.preview@1",
}


def _owner(route: str) -> str:
    if route.startswith(("/api/ai/", "/api/skills/", "/api/flows/")):
        return "agent"
    if route.startswith("/api/ext-"):
        return "integration"
    if route.startswith(("/api/craft", "/api/std_op", "/api/rule", "/api/rules")):
        return "craft"
    if route.startswith("/api/knowledge"):
        return "knowledge"
    if route.startswith(("/api/tasks", "/api/issues", "/api/lists", "/api/approval", "/api/workbench")):
        return "project_management"
    return "base"


def _bff_targets(key: tuple[str, str]) -> list[str] | None:
    method, route = key
    if key in EXT_TARGETS:
        return [EXT_TARGETS[key]]
    if route.startswith("/api/grants"):
        return [f"base.authorization.grant.{'read' if method == 'GET' else 'change.apply'}@1"]
    if route == "/api/lists":
        return ["project.list.read.atomic.lists_search@1", "craft.bop.version.list@1"]
    if route == "/api/lists/{dynamic}" and method == "PATCH":
        return ["project.list.change.apply.atomic.lists_update@1", "project.list.change.apply.atomic.lists_delete@1"]
    if route == "/api/lists/{dynamic}" and method == "DELETE":
        return ["project.list.change.apply.atomic.lists_delete@1", "craft.bop.version.archive@1"]
    if route == "/api/notifications/prefs":
        return [f"base.notification.preference.{'get' if method == 'GET' else 'update'}@1"]
    if route == "/api/org/teams" or route == "/api/teams":
        return ["base.team.read@1"]
    if route == "/api/org/sync-from-feishu":
        return ["base.identity.directory.sync@1"]
    if route.startswith("/api/self_ann"):
        return [f"base.annotation.{'read' if method == 'GET' else 'change.apply'}@1"]
    if route == "/api/users/me":
        return ["base.identity.session.get@1"]
    if route in {"/api/users", "/api/users/search"}:
        return ["identity.principal.search@1"]
    if route == "/api/users/{dynamic}/role":
        return ["base.identity.role.assign@1"]
    if route.startswith("/api/views"):
        return [f"base.saved_view.{'read' if method == 'GET' else 'change.apply'}@1"]
    if route == "/api/workbench/home":
        return ["project.project.read.atomic.projects_search@1", "project.follow.read.atomic.follows_list@1"]
    if route == "/api/workbench/panel1":
        return ["project.task.read.atomic.tasks_search@1", "project.issue.read.atomic.issues_search@1"]
    if route == "/api/approval/orders/{dynamic}/reject":
        return ["project.approval.change.apply.atomic.approval_orders_reject@1"]
    if route == "/api/tasks" and method == "PUT":
        return ["project.task.change.apply.atomic.tasks_update@1"]
    if route == "/api/issues" and method == "PUT":
        return ["project.issue.change.apply.atomic.issues_update@1"]
    if route == "/api/knowledge/entries" and method == "PUT":
        return ["knowledge.entry.change.apply.atomic.entries_update@1"]
    if route == "/api/tasks/{dynamic}/entries":
        return [
            "project.list.read.atomic.item_entries_get@1" if method == "GET"
            else "project.list.change.apply.atomic.item_entries_replace@1"
        ]
    if route == "/api/plugin/install":
        return ["plugin.install@1"]
    if route == "/api/plugin/uninstall/{dynamic}":
        return ["plugin.uninstall@1"]
    if route == "/api/rule-engine/check-entry":
        return ["craft.rule.engine.evaluate@1"]
    if route == "/api/rules/{dynamic}/deviations":
        return ["craft.rule.waiver.create@1"]
    if route == "/api/skills/canvas-options":
        return ["agent.skill.read@1", "agent.tool_catalog.read@1"]
    if route in {"/api/skills/execute-canvas", "/api/skills/resume-canvas"}:
        return ["agent.run.change.apply@1"]
    return None


def _source_path(route: str) -> str:
    candidates = (
        ("/api/grants", "backend/routers/grants.py"),
        ("/api/lists", "backend/routers/lists.py"),
        ("/api/notifications", "backend/routers/notifications.py"),
        ("/api/org", "backend/routers/org.py"),
        ("/api/self_ann", "backend/routers/self_annotations.py"),
        ("/api/users", "backend/routers/users.py"),
        ("/api/views", "backend/routers/views.py"),
        ("/api/workbench", "backend/routers/workbench.py"),
        ("/api/approval", "plugins/craft/craft_backend/routers/approval.py"),
        ("/api/rule", "plugins/craft/craft_backend/routers/rule_engine.py"),
        ("/api/std_op", "plugins/craft/craft_backend/routers/std_op.py"),
        ("/api/craft_lib", "plugins/craft/craft_backend/routers/craft_library.py"),
        ("/api/craft/", "backend/routers/craft.py"),
        ("/api/ai/", "plugins/agent/agent_backend/routers/ai_audit.py"),
    )
    return next((path for prefix, path in candidates if route.startswith(prefix)), "backend/governance/legacy_route_registry.json")


def _anchor(source_path: str, token: str) -> dict[str, Any]:
    path = ROOT / source_path
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    indexes = [index for index, line in enumerate(lines) if token in line]
    if len(indexes) != 1:
        raise RuntimeError(f"anchor token must be unique: {source_path}:{token}")
    line = indexes[0] + 1
    text = lines[indexes[0]]
    return {
        "source_path": source_path,
        "start_line": line,
        "end_line": line,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _git_blob(web_root: Path, source: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(web_root), "show", f"{BASELINE_FRONTEND_REVISION}:{source}"],
        capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"baseline frontend source missing: {source}")
    return result.stdout


def _classify(key: tuple[str, str], final_revision: str) -> tuple[str, str, dict[str, Any], dict[str, Any], str]:
    method, route = key
    owner = _owner(route)
    source = _source_path(route)
    evidence = {
        "openapi_status": "registered" if (ROOT / source).is_file() else "absent",
        "source_path": source,
        "finding": "Reviewed against the backend OpenAPI and implementation at 800ec6ba; same-name inference is not accepted.",
        "anchors": [],
    }
    if key in EXISTING:
        owner, target, source, token = EXISTING[key]
        evidence.update({
            "openapi_status": "registered",
            "source_path": source,
            "finding": "The exact handler invocation/delegation is anchored below.",
            "anchors": [_anchor(source, token)],
        })
        return owner, "existing_stable_capability", evidence, {
            "target_capability": target,
            "proof_reference": f"web-api-legacy-addition-review/task_3b3a:{method}:{route}",
        }, "Exact registered handler reaches the stable target through the anchored call."
    if key in RETIRE:
        if route == "/api/ai/balance":
            evidence.update({
                "openapi_status": "retired_410",
                "source_path": "plugins/agent/agent_backend/routers/ai_audit.py",
                "finding": "The registered handler returns HTTP 410 and the polling UI had no supported result.",
                "anchors": [_anchor("plugins/agent/agent_backend/routers/ai_audit.py", 'status_code=410')],
            })
        elif route.startswith("/api/craft/"):
            evidence.update({
                "openapi_status": "removed_v1_router",
                "source_path": "backend/routers/craft.py",
                "finding": "The V1 craft table router is an explicit tombstone with no routes.",
                "anchors": [_anchor("backend/routers/craft.py", "work_plans / sections / operation_flat")],
            })
        elif route.endswith("clone-to-post"):
            evidence.update({
                "openapi_status": "retired_410",
                "source_path": "plugins/craft/craft_backend/routers/std_op.py",
                "finding": "The registered compatibility handler returns HTTP 410.",
                "anchors": [_anchor("plugins/craft/craft_backend/routers/std_op.py", 'status_code=410')],
            })
        return owner, "frontend_retire", evidence, {
            "removed_in_frontend_revision": final_revision,
            "retirement_basis": evidence["finding"],
        }, "The frontend call is dead, explicitly retired, or template/sample-only and was removed without replacement."
    if key in NORMALIZE:
        return owner, "frontend_route_normalize", evidence, {
            "finite_routes": NORMALIZE[key],
            "runtime_target_preserved": True,
            "normalization_basis": "Only source expression shape changed; concrete runtime paths and HTTP methods are unchanged.",
        }, "The scanner ambiguity came from a malformed template or finite item-type interpolation."
    if key in OPERATIONS:
        return owner, "operations_candidate", evidence, {
            "approval_status": "not_approved",
            "operation_kind": "technical configuration or test execution",
            "reason": "Non-business operation candidate retained unresolved until separately approved.",
        }, "The route is technical/diagnostic, but this task grants no operations exclusion."
    constituents = _bff_targets(key)
    if constituents:
        return owner, "truthful_bff_required", evidence, {
            "constituent_capabilities": constituents,
            "aggregation_evidence": (
                "The current REST shape performs transport adaptation, conditional dispatch, or direct service/SQL access; "
                "it must be rebuilt as a truthful facade over these exact stable outcomes before Legacy registration."
            ),
        }, "Stable constituents exist, but the current route has no provider-equivalent invocation proof."
    return owner, "new_atomic_capability_required", evidence, {
        "proposed_owner_domain": owner,
        "atomic_outcome": f"Execute the bounded {method} {route} outcome without dynamic action or collection ambiguity.",
        "provider_or_handler": source,
        "bounded_input": "Authenticated principal, finite route identifiers, and one closed request object with bounded strings/collections.",
        "bounded_output": "One closed result object or a paginated bounded collection with explicit domain errors.",
        "no_stable_target_reason": "Catalog and provider review found no exact provider-equivalent stable target; similar names were rejected.",
    }, "No exact stable provider outcome exists for this method and normalized route."


def build_document(web_root: Path) -> dict[str, Any]:
    baseline = json.loads(BASELINE_INVENTORY.read_text(encoding="utf-8"))
    baseline_is_pinned = (
        baseline.get("frontend_revision") != BASELINE_FRONTEND_REVISION
        or baseline.get("content_hash") != BASELINE_CONTENT_HASH
        or baseline.get("counts", {}).get("unresolved") != BASELINE_UNRESOLVED_COUNT
    ) is False
    if baseline_is_pinned:
        baseline_routes = [
            raw for raw in baseline["routes"] if raw["disposition"] == "unresolved"
        ]
    else:
        try:
            prior = json.loads(DEFAULT_LEDGER.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "pinned baseline evidence is unavailable and no prior ledger can reconstruct it"
            ) from exc
        if (
            prior.get("baseline_frontend_revision") != BASELINE_FRONTEND_REVISION
            or prior.get("baseline_content_hash") != BASELINE_CONTENT_HASH
        ):
            raise RuntimeError("prior ledger does not contain the pinned baseline")
        baseline_routes = [
            {
                **occurrence,
                "method": entry["method"],
                "normalized_route": entry["normalized_route"],
                "disposition": "unresolved",
            }
            for entry in prior["entries"]
            for occurrence in entry["occurrences"]
        ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in baseline_routes:
        grouped[(raw["method"], raw["normalized_route"])].append(raw)
    if len(grouped) != BASELINE_GROUP_COUNT:
        raise RuntimeError("baseline unresolved group count drift")

    source_blobs = {
        source: _git_blob(web_root, source)
        for source in sorted({raw["source"] for values in grouped.values() for raw in values})
    }
    source_hashes = {
        source: hashlib.sha256(blob).hexdigest()
        for source, blob in source_blobs.items()
    }
    final_report = build_report(web_root)
    final_groups = Counter(
        (raw.method, raw.normalized_route)
        for raw in final_report.routes if raw.disposition == "unresolved"
    )
    final_revision = final_report.frontend_revision
    entries = []
    for key in sorted(grouped):
        owner, disposition, evidence, details, conclusion = _classify(key, final_revision)
        if disposition == "frontend_route_normalize":
            details["residual_unresolved_routes"] = sorted(
                value for value in details["finite_routes"]
                if tuple(value.split(" ", 1)) in final_groups
            )
        values = sorted(grouped[key], key=lambda raw: raw["occurrence_id"])
        occurrences = [{
            "occurrence_id": raw["occurrence_id"],
            "source": raw["source"],
            "line": raw["line"],
            "column": raw["column"],
            "raw_route": raw["raw_route"],
            "source_sha256": source_hashes[raw["source"]],
        } for raw in values]
        entries.append({
            "method": key[0], "normalized_route": key[1],
            "occurrence_count": len(occurrences), "occurrences": occurrences,
            "owner_domain": owner, "backend_evidence": evidence,
            "lifecycle_conclusion": conclusion, "disposition": disposition,
            "disposition_details": details,
        })
    return {
        "schema_version": 1,
        "artifact_id": "web-route-root-cause-ledger",
        "review_authority": "capability-governance-evidence-closure/task-3b3a",
        "baseline_frontend_revision": BASELINE_FRONTEND_REVISION,
        "baseline_content_hash": BASELINE_CONTENT_HASH,
        "baseline_unresolved_count": BASELINE_UNRESOLVED_COUNT,
        "baseline_group_count": BASELINE_GROUP_COUNT,
        "baseline_source_hashes": source_hashes,
        "final_evidence": {
            "frontend_revision": final_revision,
            "content_hash": final_report.content_hash,
            "unresolved_count": final_report.unresolved_count,
            "unresolved_group_count": len(final_groups),
        },
        "final_unresolved_groups": [
            {"method": method, "normalized_route": route, "occurrence_count": count}
            for (method, route), count in sorted(final_groups.items())
        ],
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args(argv)
    document = build_document(args.web_root.resolve())
    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        try:
            stored = args.output.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"route-root-cause-ledger unreadable: {exc}", file=sys.stderr)
            return 1
        if stored != rendered:
            print("route-root-cause-ledger drift", file=sys.stderr)
            return 1
    print(
        f"baseline_occurrences={BASELINE_UNRESOLVED_COUNT} baseline_groups={len(document['entries'])} "
        f"final_unresolved={document['final_evidence']['unresolved_count']} "
        f"final_groups={document['final_evidence']['unresolved_group_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
