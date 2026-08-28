"""Build the Task 3B.3a reviewed Web route root-cause ledger."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.route_root_cause_ledger import (
    BASELINE_BACKEND_REVISION,
    BASELINE_CONTENT_HASH,
    BASELINE_FRONTEND_REVISION,
    BASELINE_GROUP_COUNT,
    BASELINE_INVENTORY_PATH,
    BASELINE_INVENTORY_SHA256,
    BASELINE_UNRESOLVED_COUNT,
    CLASSIFIED_GROUP_COUNT,
    CLASSIFIED_OCCURRENCE_COUNT,
    build_route_definition_evidence,
)
from backend.capability_v2.existing_capability_migrations import (
    audit_existing_capability_migrations,
    load_existing_capability_migrations,
)
from backend.scripts.check_web_capability_routes import build_report
from backend.capability_v2.git_tree import read_path, read_text

DEFAULT_LEDGER = ROOT / "docs/governance/web-route-root-cause-ledger.json"
MIGRATION_MANIFEST = ROOT / "docs/governance/existing-capability-web-migrations.json"
ATOMIC_CONTRACT_MANIFEST = ROOT / "docs/governance/atomic-web-capability-contracts.json"


@lru_cache(maxsize=1)
def _atomic_contracts():
    payload = json.loads(ATOMIC_CONTRACT_MANIFEST.read_text(encoding="utf-8"))
    return {
        (entry["method"], entry["normalized_route"]): entry
        for entry in payload["entries"]
    }


@lru_cache(maxsize=1)
def _migration_decisions(web_root: Path):
    manifest = load_existing_capability_migrations(MIGRATION_MANIFEST)
    issues = audit_existing_capability_migrations(
        ROOT, manifest, web_root=web_root, check_final_inventory=False
    )
    if issues:
        raise RuntimeError(
            "Task 3B.3b independent migration review failed: " + "; ".join(issues)
        )
    return {(group.method, group.normalized_route): group for group in manifest.groups}

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
    ("POST", "/api/rules/{dynamic}/{dynamic}"): [
        "POST /api/rules/{dynamic}/activate",
        "POST /api/rules/{dynamic}/suspend",
    ],
}

TRUE_BFF = {
    ("GET", "/api/workbench/home"): [
        "project.project.read.atomic.projects_search@1",
        "project.follow.read.atomic.follows_list@1",
    ],
    ("GET", "/api/workbench/panel1"): [
        "project.task.read.atomic.tasks_search@1",
        "project.issue.read.atomic.issues_search@1",
    ],
}

CONDITIONAL = {
    ("PATCH", "/api/lists/{dynamic}"): (
        "body.archive",
        [
            "project.list.change.apply.atomic.lists_update@1",
            "project.list.change.apply.atomic.lists_delete@1",
        ],
    ),
}

PARTIAL_CONDITIONAL = {
    ("GET", "/api/lists"): (
        "item_type", ["project.list.read.atomic.lists_search@1"],
        [{"selector_value": "bop_version", "transport": "GET /api/lists?item_type=bop_version"}],
    ),
    ("DELETE", "/api/lists/{dynamic}"): (
        "item_type", ["project.list.change.apply.atomic.lists_delete@1"],
        [{"selector_value": "bop_version", "transport": "DELETE /api/lists/{gid}?item_type=bop_version&expected_revision={revision}"}],
    ),
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

DERIVED_KEYS = {
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

ATOMIC_OUTCOMES = {
    ("DELETE", "/api/craft_lib/equipments/{dynamic}"):
        "Remove one identified equipment record from the governed Craft library.",
    ("DELETE", "/api/craft_lib/fixtures/{dynamic}"):
        "Remove one identified fixture record from the governed Craft library.",
    ("GET", "/api/plugin/list"):
        "List the bounded installed plugin manifests visible to the authenticated user.",
    ("POST", "/api/flows/test-node"):
        "Execute one configured workflow node against bounded authoring-test inputs and return its node output.",
    ("POST", "/api/skills/canvas-options"):
        "Resolve the bounded approval-form options for one selected workflow-canvas tool and parameter set.",
    ("POST", "/api/rules/{dynamic}/suspend"):
        "Suspend one identified active rule release and return its resulting lifecycle state.",
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
    if route == "/api/file-store/config":
        return "platform-runtime"
    return "base"


def _migration_target(key: tuple[str, str]) -> str | None:
    method, route = key
    if key in EXT_TARGETS:
        return EXT_TARGETS[key]
    if route.startswith("/api/grants"):
        return f"base.authorization.grant.{'read' if method == 'GET' else 'change.apply'}@1"
    if route == "/api/notifications/prefs":
        return f"base.notification.preference.{'get' if method == 'GET' else 'update'}@1"
    if route in {"/api/org/teams", "/api/teams"}:
        return "base.team.read@1"
    if route == "/api/org/sync-from-feishu":
        return "base.identity.directory.sync@1"
    if route.startswith("/api/self_ann"):
        return f"base.annotation.{'read' if method == 'GET' else 'change.apply'}@1"
    if route == "/api/users/me":
        return "base.identity.session.get@1"
    if route in {"/api/users", "/api/users/search"}:
        return "identity.principal.search@1"
    if route == "/api/users/{dynamic}/role":
        return "base.identity.role.assign@1"
    if route.startswith("/api/views"):
        return f"base.saved_view.{'read' if method == 'GET' else 'change.apply'}@1"
    explicit = {
        ("POST", "/api/approval/orders/{dynamic}/reject"): "project.approval.change.apply.atomic.approval_orders_reject@1",
        ("PUT", "/api/tasks"): "project.task.change.apply.atomic.tasks_update@1",
        ("PUT", "/api/issues"): "project.issue.change.apply.atomic.issues_update@1",
        ("PUT", "/api/knowledge/entries"): "knowledge.entry.change.apply.atomic.entries_update@1",
        ("GET", "/api/tasks/{dynamic}/entries"): "project.list.read.atomic.item_entries_get@1",
        ("PUT", "/api/tasks/{dynamic}/entries"): "project.list.change.apply.atomic.item_entries_replace@1",
        ("POST", "/api/plugin/install"): "plugin.install@1",
        ("DELETE", "/api/plugin/uninstall/{dynamic}"): "plugin.uninstall@1",
        ("GET", "/api/rule-engine/check-entry"): "craft.rule.engine.evaluate@1",
        ("POST", "/api/rules/{dynamic}/deviations"): "craft.rule.waiver.create@1",
        ("POST", "/api/skills/execute-canvas"): "agent.run.change.apply@1",
        ("POST", "/api/skills/resume-canvas"): "agent.run.change.apply@1",
        ("DELETE", "/api/knowledges/{dynamic}"): "knowledge.entry.change.apply.atomic.entries_delete@1",
        ("GET", "/api/knowledge/entries"): "knowledge.search@1",
        ("GET", "/api/knowledges/{dynamic}"): "knowledge.get@1",
        ("PATCH", "/api/knowledges/{dynamic}"): "knowledge.entry.change.apply.atomic.entries_update@1",
        ("POST", "/api/knowledges"): "knowledge.entry.change.apply.atomic.entries_create@1",
        ("PUT", "/api/knowledges/{dynamic}"): "knowledge.entry.change.apply.atomic.entries_update@1",
        ("PUT", "/api/rules/{dynamic}"): "craft.rule.library.change.apply@1",
        ("POST", "/api/rules/{dynamic}/activate"): "craft.rule.release.activate@1",
    }
    return explicit.get(key)


def _source_path(route: str) -> str:
    candidates = (
        ("/api/grants", "backend/routers/grants.py"),
        ("/api/lists", "plugins/craft/craft_backend/routers/lists.py"),
        ("/api/notifications", "backend/routers/notifications.py"),
        ("/api/org", "backend/routers/org.py"),
        ("/api/teams", "backend/routers/teams.py"),
        ("/api/self_ann", "backend/routers/self_annotations.py"),
        ("/api/users", "backend/routers/users.py"),
        ("/api/views", "backend/routers/views.py"),
        ("/api/workbench", "backend/routers/workbench_home.py"),
        ("/api/approval", "plugins/craft/craft_backend/routers/approval.py"),
        ("/api/tasks", "plugins/craft/craft_backend/routers/promotion.py"),
        ("/api/issues", "plugins/craft/craft_backend/routers/promotion.py"),
        ("/api/knowledge", "plugins/knowledge/knowledge_backend/api/knowledge_entries_legacy.py"),
        ("/api/plugin", "backend/routers/plugins.py"),
        ("/api/rule-engine", "plugins/craft/craft_backend/routers/rule_engine.py"),
        ("/api/rules", "plugins/craft/craft_backend/routers/rules.py"),
        ("/api/skills", "plugins/agent/agent_backend/routers/skills_v2.py"),
        ("/api/flows", "plugins/agent/agent_backend/routers/flows.py"),
        ("/api/file-store", "backend/routers/file_store.py"),
        ("/api/ext-", "plugins/integration/integration_backend/capabilities/provider.py"),
        ("/api/std_op", "plugins/craft/craft_backend/routers/std_op.py"),
        ("/api/craft_lib", "plugins/craft/craft_backend/routers/craft_library.py"),
        ("/api/craft/", "backend/routers/craft.py"),
        ("/api/ai/", "plugins/agent/agent_backend/routers/ai_audit.py"),
        ("/api/feishu", "backend/routers/feishu_proxy.py"),
        ("/api/bitable", "backend/main.py"),
        ("/api/my-plugin", "backend/main.py"),
    )
    return next(
        (path for prefix, path in candidates if route.startswith(prefix)),
        "backend/main.py",
    )


def _anchor_from_text(
    repository: str, source_path: str, text: str, start_line: int, end_line: int
) -> dict[str, Any]:
    lines = text.splitlines(keepends=True)
    selected = "".join(lines[start_line - 1:end_line])
    if not selected or end_line > len(lines):
        raise RuntimeError(f"anchor range invalid: {source_path}:{start_line}-{end_line}")
    return {
        "repository": repository, "source_path": source_path,
        "start_line": start_line, "end_line": end_line,
        "sha256": hashlib.sha256(selected.encode("utf-8")).hexdigest(),
    }


def _backend_anchor(source_path: str, token: str) -> dict[str, Any]:
    text = (ROOT / source_path).read_text(encoding="utf-8")
    indexes = [index for index, line in enumerate(text.splitlines()) if token in line]
    if len(indexes) != 1:
        raise RuntimeError(f"anchor token must be unique: {source_path}:{token}")
    return _anchor_from_text("backend", source_path, text, indexes[0] + 1, indexes[0] + 1)


def _git_blob(root: Path, revision: str, source: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{revision}:{source}"],
        capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"git evidence missing: {revision}:{source}")
    return result.stdout


def _frontend_anchor(
    web_root: Path, source_path: str, token: str, *, baseline: bool,
    final_revision: str | None = None,
) -> dict[str, Any]:
    if baseline:
        text = _git_blob(web_root, BASELINE_FRONTEND_REVISION, source_path).decode("utf-8")
        repository = "frontend_baseline"
    else:
        if final_revision is None:
            raise RuntimeError("final frontend revision is required")
        text = read_text(web_root, final_revision, source_path)
        repository = "frontend_final"
    indexes = [index for index, line in enumerate(text.splitlines()) if token in line]
    if len(indexes) != 1:
        raise RuntimeError(f"frontend anchor token must be unique: {source_path}:{token}")
    return _anchor_from_text(repository, source_path, text, indexes[0] + 1, indexes[0] + 1)


def _frontend_line_anchor(
    web_root: Path, source_path: str, line: int
) -> dict[str, Any]:
    text = _git_blob(web_root, BASELINE_FRONTEND_REVISION, source_path).decode("utf-8")
    return _anchor_from_text("frontend_baseline", source_path, text, line, line)


def _route_anchor(route_definition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "repository": "backend",
        "source_path": route_definition["source_path"],
        "start_line": route_definition["start_line"],
        "end_line": route_definition["end_line"],
        "sha256": route_definition["sha256"],
    }


def _backend_evidence(
    key: tuple[str, str],
    source_path: str,
    *,
    status: str | None = None,
    anchors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    route_definition = build_route_definition_evidence(ROOT, source_path, key)
    handler_status = status or ("registered" if route_definition else "absent")
    if handler_status != "registered":
        route_definition = None
    return {
        "handler_status": handler_status,
        "source_path": source_path,
        "finding": (
            "Exact registered route definition is anchored and machine-checked."
            if handler_status == "registered"
            else "No exact registered route/method definition exists in this reviewed handler family."
        ),
        "route_definition": route_definition,
        "anchors": anchors or [],
    }


def _final_source_proof(
    web_root: Path, revision: str, occurrences: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_source: dict[str, set[str]] = defaultdict(set)
    for raw in occurrences:
        by_source[raw["source"]].add(raw["raw_route"])
    proofs = []
    for source, raw_routes in sorted(by_source.items()):
        blob, text = read_path(web_root, revision, source), read_text(web_root, revision, source)
        present = [route for route in raw_routes if route in text]
        if present:
            raise RuntimeError(f"retired frontend calls remain in {source}: {present}")
        proofs.append({
            "source_path": source,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "removed_raw_routes": sorted(raw_routes),
        })
    return proofs


def _retirement_proof(
    key: tuple[str, str],
    evidence: dict[str, Any],
    occurrences: list[Mapping[str, Any]],
    web_root: Path,
    final_revision: str,
) -> dict[str, Any]:
    route = key[1]
    if route.startswith("/api/bitable-sync"):
        kind = "explicit_product_retirement"
        rationale = "The Bitable synchronization product surface was explicitly retired with its V1 backend and the compatibility shell now makes no request."
        anchors = [_frontend_anchor(
            web_root, "web/components/bitable_sync_manager.js",
            "The Bitable synchronization backend was retired", baseline=False,
            final_revision=final_revision,
        )]
    elif route.startswith("/api/craft/"):
        kind = "backend_route_retired"
        rationale = "The V1 craft work-plan, section, and operation-flat backend family is an explicit tombstone after schema retirement."
        anchors = [_backend_anchor("backend/routers/craft.py", "work_plans / sections / operation_flat")]
        evidence.update(_backend_evidence(key, "backend/routers/craft.py", status="retired", anchors=anchors))
    elif route == "/api/ai/balance":
        kind = "http_410"
        rationale = "The registered AI balance compatibility endpoint is permanently gone and returns HTTP 410, so polling it cannot yield a supported outcome."
        anchors = [_backend_anchor("plugins/agent/agent_backend/routers/ai_audit.py", "@router.get(\"/balance\", status_code=410)")]
        evidence.update(_backend_evidence(key, "plugins/agent/agent_backend/routers/ai_audit.py", anchors=anchors))
    elif route.endswith("clone-to-post"):
        kind = "http_410"
        rationale = "The registered V1 standard-operation clone compatibility endpoint raises HTTP 410 and instructs callers to use the current BOP entry surface."
        anchors = [_backend_anchor("plugins/craft/craft_backend/routers/std_op.py", "raise HTTPException(status_code=410")]
        evidence.update(_backend_evidence(key, "plugins/craft/craft_backend/routers/std_op.py", anchors=anchors))
    elif route == "/api/my-plugin/items":
        kind = "sample_template_only"
        rationale = "The only caller lived in the distributable plugin SDK template and represented placeholder sample data rather than a shipped product route."
        first = occurrences[0]
        anchors = [_frontend_line_anchor(web_root, first["source"], first["line"])]
    else:
        kind = "backend_route_absent"
        rationale = "The standalone Feishu UI had no matching API-prefixed configuration handler; it now uses a bounded local default configuration."
        anchors = [_backend_anchor("backend/routers/feishu_proxy.py", 'router = APIRouter(prefix="/feishu"')]
        evidence.update(_backend_evidence(key, "backend/routers/feishu_proxy.py", anchors=anchors))
    evidence["anchors"] = anchors
    return {
        "kind": kind, "rationale": rationale, "anchors": anchors,
        "final_sources": _final_source_proof(web_root, final_revision, occurrences),
    }


def _classify(
    key: tuple[str, str],
    occurrences: list[Mapping[str, Any]],
    final_revision: str,
    web_root: Path,
) -> tuple[str, str, dict[str, Any], dict[str, Any], str]:
    method, route = key
    owner, source = _owner(route), _source_path(route)
    evidence = _backend_evidence(key, source)
    if key in EXISTING:
        owner, target, source, token = EXISTING[key]
        anchors = [_backend_anchor(source, token)]
        evidence = _backend_evidence(key, source, anchors=anchors)
        return owner, "existing_stable_capability", evidence, {
            "target_capability": target,
            "proof_reference": f"task-3b3a:{method}:{route}",
        }, "The exact registered handler reaches the stable target through the anchored provider invocation."
    if key in RETIRE:
        if route.startswith("/api/craft/"):
            evidence = _backend_evidence(key, "backend/routers/craft.py", status="retired")
        proof = _retirement_proof(key, evidence, occurrences, web_root, final_revision)
        return owner, "frontend_retire", evidence, {
            "removed_in_frontend_revision": final_revision,
            "retirement_proof": proof,
        }, "The baseline caller existed, its final source hash proves removal, and an independent lifecycle proof supports retirement."
    if key in NORMALIZE:
        evidence = _backend_evidence(
            key, source, status="not_applicable"
        )
        return owner, "frontend_route_normalize", evidence, {
            "finite_routes": NORMALIZE[key],
            "runtime_target_preserved": True,
            "normalization_basis": "Only the finite frontend route expression changed; the reviewed method and runtime destinations remain explicit.",
        }, "The baseline scanner ambiguity came from a malformed template or a finite action/item-type interpolation."
    if key == ("GET", "/api/file-store/config"):
        evidence = _backend_evidence(key, "backend/routers/file_store.py")
        return "base", "file_store_capability_migrated", evidence, {
            "target_capability": "base.file_store.public_config.get@1",
            "public_projection": "secret_filtered_closed_schema",
            "manifest": "docs/governance/special-web-residual-contracts.json",
        }, "The Web consumer invokes an authenticated, secret-filtered Base capability through Gateway."
    if key in TRUE_BFF:
        evidence = _backend_evidence(key, "backend/routers/workbench_home.py")
        route_definition = evidence["route_definition"]
        if not route_definition:
            raise RuntimeError(f"BFF handler missing: {key}")
        anchor = _route_anchor(route_definition)
        evidence["anchors"] = [anchor]
        return owner, "truthful_bff_registered", evidence, {
            "constituent_capabilities": TRUE_BFF[key],
            "aggregation_evidence": {
                "kind": "multi_result_merge", "anchors": [anchor],
                "combined_outcomes": TRUE_BFF[key],
            },
        }, "The anchored handler invokes two stable outcomes and merges their results into one reviewed workbench response."
    if key in PARTIAL_CONDITIONAL:
        selector, branches, rest_branches = PARTIAL_CONDITIONAL[key]
        evidence = _backend_evidence(key, "plugins/craft/craft_backend/routers/lists.py")
        anchor = _route_anchor(evidence["route_definition"])
        evidence["anchors"] = [anchor]
        return owner, "conditional_dispatch_partially_migrated", evidence, {
            "selector": selector, "branch_capabilities": branches,
            "reclassified_rest_branches": rest_branches,
            "dispatch_evidence": {"kind": "conditional_branch", "aggregation": False, "anchors": [anchor]},
        }, "Project-owned branches remain exact Gateway migrations; BOP-version branches are explicitly restored to REST and remain unresolved."
    if key in CONDITIONAL:
        selector, branches = CONDITIONAL[key]
        evidence = _backend_evidence(key, "plugins/craft/craft_backend/routers/lists.py")
        route_definition = evidence["route_definition"]
        if not route_definition:
            raise RuntimeError(f"conditional handler missing: {key}")
        anchor = _route_anchor(route_definition)
        evidence["anchors"] = [anchor]
        return owner, "conditional_dispatch_migrated", evidence, {
            "selector": selector, "branch_capabilities": branches,
            "dispatch_evidence": {
                "kind": "conditional_branch", "aggregation": False,
                "anchors": [anchor],
            },
        }, "The handler selects exactly one branch per request; conditional dispatch is not aggregation and cannot be registered as a BFF."
    atomic = _atomic_contracts().get(key)
    if atomic and atomic["final_disposition"] == "migrated":
        target = f"{atomic['capability_id']}@{atomic['major_version']}"
        provider_source, provider_token = atomic["provider_anchor"].split(":", 1)
        return owner, "existing_capability_migrated", evidence, {
            "target_capability": target,
            "provider_equivalence": "proven",
            "request_transform": "Exact closed payload defined by Task 3B.3c atomic contract manifest.",
            "response_transform": "Bounded result_json is decoded to the original legacy response value.",
            "equivalence_evidence": {
                "proof_kind": "provider_equivalent_adapter",
                "provider_contract": _backend_anchor(provider_source, provider_token),
                "provider_source_sha256": atomic["provider_source_sha256"],
                "manifest": "docs/governance/atomic-web-capability-contracts.json",
            },
        }, "The frontend invokes the exact stable atomic owner-domain outcome through the shared Gateway client."
    target = _migration_target(key)
    if target:
        decision = _migration_decisions(web_root).get(key)
        if decision is None or f"{decision.target_capability_id}@{decision.target_major_version}" != target:
            raise RuntimeError(f"Task 3B.3b migration decision missing or stale: {key}")
        if decision.decision == "migrate":
            return owner, "existing_capability_migrated", evidence, {
                "target_capability": target,
                "provider_equivalence": "proven",
                "request_transform": decision.request_transform,
                "response_transform": decision.response_transform,
                "equivalence_evidence": decision.equivalence_evidence,
            }, "The frontend now invokes the exact stable target through the shared Gateway adapter using provider-equivalent request and response transformations."
        return owner, "existing_capability_reclassified", evidence, {
            "candidate_target_capability": target,
            **dict(decision.reclassification or {}),
        }, "Independent Provider review found the name-matched stable candidate non-equivalent; the route remains visibly unresolved under its evidence-backed follow-up class."
    return owner, "new_atomic_capability_required", evidence, {
        "proposed_owner_domain": owner,
        "atomic_outcome": ATOMIC_OUTCOMES[key],
        "provider_or_handler": source,
        "bounded_input": "Authenticated principal, finite identifiers, and one closed request object with bounded strings and collections.",
        "bounded_output": "One closed result object or a paginated bounded collection with explicit domain errors.",
        "no_stable_target_reason": "Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.",
    }, "No exact stable provider outcome exists for this method and normalized route."


def _baseline_document() -> tuple[Mapping[str, Any], bytes]:
    blob = _git_blob(ROOT, BASELINE_BACKEND_REVISION, BASELINE_INVENTORY_PATH)
    if hashlib.sha256(blob).hexdigest() != BASELINE_INVENTORY_SHA256:
        raise RuntimeError("pinned backend baseline inventory hash drift")
    document = json.loads(blob.decode("utf-8"))
    if (
        document.get("frontend_revision") != BASELINE_FRONTEND_REVISION
        or document.get("content_hash") != BASELINE_CONTENT_HASH
        or document.get("counts", {}).get("unresolved") != BASELINE_UNRESOLVED_COUNT
    ):
        raise RuntimeError("pinned backend baseline inventory metadata drift")
    return document, blob


def _occurrence_with_hash(raw: Mapping[str, Any], digest: str) -> dict[str, Any]:
    return {**dict(raw), "source_sha256": digest}


def build_document(web_root: Path) -> dict[str, Any]:
    baseline, _ = _baseline_document()
    baseline_routes = [raw for raw in baseline["routes"] if raw["disposition"] == "unresolved"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in baseline_routes:
        grouped[(raw["method"], raw["normalized_route"])].append(raw)
    if len(grouped) != BASELINE_GROUP_COUNT or len(baseline_routes) != BASELINE_UNRESOLVED_COUNT:
        raise RuntimeError("pinned baseline unresolved evidence drift")

    baseline_sources = sorted({raw["source"] for raw in baseline_routes})
    baseline_source_hashes = {
        source: hashlib.sha256(
            _git_blob(web_root, BASELINE_FRONTEND_REVISION, source)
        ).hexdigest()
        for source in baseline_sources
    }
    final_report = build_report(web_root)
    final_document = json.loads(final_report.json())
    final_routes = [raw for raw in final_document["routes"] if raw["disposition"] == "unresolved"]
    final_grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in final_routes:
        final_grouped[(raw["method"], raw["normalized_route"])].append(raw)
    derived = set(final_grouped) - set(grouped)
    if not derived <= DERIVED_KEYS:
        raise RuntimeError(f"post-normalization route groups drift: {sorted(derived)}")

    migration_occurrences = {
        (group.method, group.normalized_route): [dict(raw) for raw in group.occurrences]
        for group in load_existing_capability_migrations(MIGRATION_MANIFEST).groups
    }
    post_normalization_groups = {
        key: final_grouped.get(key) or migration_occurrences[key]
        for key in DERIVED_KEYS
    }

    entries: list[dict[str, Any]] = []
    for scope, groups in (("baseline", grouped), ("post_normalization", post_normalization_groups)):
        for key in sorted(groups):
            values = sorted(groups[key], key=lambda raw: raw["occurrence_id"])
            if scope == "baseline":
                occurrences = [
                    _occurrence_with_hash(raw, baseline_source_hashes[raw["source"]])
                    for raw in values
                ]
            else:
                occurrences = [
                    _occurrence_with_hash(
                        raw, hashlib.sha256(
                            read_path(web_root, final_report.frontend_revision, raw["source"])
                        ).hexdigest()
                    )
                    for raw in values
                ]
            owner, disposition, evidence, details, conclusion = _classify(
                key, occurrences, final_report.frontend_revision, web_root
            )
            entries.append({
                "method": key[0], "normalized_route": key[1],
                "occurrence_scope": scope, "occurrence_count": len(occurrences),
                "occurrences": occurrences, "owner_domain": owner,
                "backend_evidence": evidence, "lifecycle_conclusion": conclusion,
                "disposition": disposition, "disposition_details": details,
            })
    entries.sort(key=lambda raw: (raw["method"], raw["normalized_route"]))
    if len(entries) != CLASSIFIED_GROUP_COUNT or sum(raw["occurrence_count"] for raw in entries) != CLASSIFIED_OCCURRENCE_COUNT:
        raise RuntimeError("classified ledger totals drift")
    entry_index = {(raw["method"], raw["normalized_route"]): raw for raw in entries}
    missing_final = set(final_grouped) - set(entry_index)
    if missing_final:
        raise RuntimeError(f"unclassified final route groups: {sorted(missing_final)}")
    final_groups = Counter(
        (raw["method"], raw["normalized_route"]) for raw in final_routes
    )
    return {
        "schema_version": 2,
        "artifact_id": "web-route-root-cause-ledger",
        "review_authority": "capability-governance-evidence-closure/task-3b3a/fix-round-1",
        "baseline_backend_revision": BASELINE_BACKEND_REVISION,
        "baseline_inventory_path": BASELINE_INVENTORY_PATH,
        "baseline_inventory_sha256": BASELINE_INVENTORY_SHA256,
        "baseline_frontend_revision": BASELINE_FRONTEND_REVISION,
        "baseline_content_hash": BASELINE_CONTENT_HASH,
        "baseline_unresolved_count": BASELINE_UNRESOLVED_COUNT,
        "baseline_group_count": BASELINE_GROUP_COUNT,
        "baseline_source_hashes": baseline_source_hashes,
        "final_evidence": {
            "frontend_revision": final_report.frontend_revision,
            "content_hash": final_report.content_hash,
            "unresolved_count": final_report.unresolved_count,
            "unresolved_group_count": len(final_groups),
        },
        "final_unresolved_groups": [
            {
                "method": method, "normalized_route": route,
                "occurrence_count": count,
                "disposition": entry_index[(method, route)]["disposition"],
            }
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
    dispositions = Counter(raw["disposition"] for raw in document["entries"])
    print(
        f"baseline_occurrences={BASELINE_UNRESOLVED_COUNT} "
        f"baseline_groups={BASELINE_GROUP_COUNT} "
        f"classified_occurrences={CLASSIFIED_OCCURRENCE_COUNT} "
        f"classified_groups={CLASSIFIED_GROUP_COUNT} "
        f"final_unresolved={document['final_evidence']['unresolved_count']} "
        f"final_groups={document['final_evidence']['unresolved_group_count']} "
        f"dispositions={dict(sorted(dispositions.items()))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
