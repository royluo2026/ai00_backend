"""Build final Craft, Agent, and Project structural-remediation evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.check_web_capability_routes import (
    build_git_tree_scan_evidence,
    build_report,
)
from backend.capability_v2.git_tree import read_path, resolve_revision


BASELINE = "2db07be4"
CLOSURE_BASELINE = "614805f59294006b8802ae01869dc9d7fe3cf694"
LEDGER_PATH = "docs/governance/web-route-root-cause-ledger.json"
REMEDIATION_PATH = "docs/governance/craft-agent-project-structural-web-remediation.json"
ATOMIC_PATH = ROOT / "docs/governance/atomic-web-capability-contracts.json"
OUTPUT = ROOT / "docs/governance/craft-agent-project-structural-web-remediation.json"
SCOPE = {
    ("GET", "/api/rule-engine/check-entry"),
    ("PUT", "/api/rules/{dynamic}"),
    ("POST", "/api/rules/{dynamic}/activate"),
    ("POST", "/api/rules/{dynamic}/deviations"),
    ("POST", "/api/rules/{dynamic}/suspend"),
    ("DELETE", "/api/craft_lib/equipments/{dynamic}"),
    ("DELETE", "/api/craft_lib/fixtures/{dynamic}"),
    ("POST", "/api/flows/test-node"),
    ("POST", "/api/skills/canvas-options"),
    ("POST", "/api/skills/execute-canvas"),
    ("POST", "/api/skills/resume-canvas"),
    ("GET", "/api/lists"),
    ("DELETE", "/api/lists/{dynamic}"),
    ("POST", "/api/approval/orders/{dynamic}/reject"),
}
BOP_KEYS = {("GET", "/api/lists"), ("DELETE", "/api/lists/{dynamic}")}
AGENT_KEYS = {
    ("POST", "/api/flows/test-node"),
    ("POST", "/api/skills/canvas-options"),
    ("POST", "/api/skills/execute-canvas"),
    ("POST", "/api/skills/resume-canvas"),
}
BOP_REASON = "The BOP conditional branch is a Craft version lifecycle outcome, not a Project list operation or direct SQL dispatch."
LISTS_SOURCE = "plugins/craft/craft_backend/routers/lists.py"
APPROVAL_SOURCE = "plugins/craft/craft_backend/routers/approval.py"
PROJECT_SERVICE_SOURCE = "plugins/project_management/project_management_backend/application/service.py"
PROJECT_PROVIDER_SOURCE = "plugins/project_management/project_management_backend/capabilities/provider.py"
PROJECT_FRONTEND_REVISION = "69e5e00054d3c1cff635fe41fcb96fbe150d25fb"
CRAFT_FRONTEND_REVISION = "8ebc8de49b5d4f86c9360664fffa912c3d969102"
CRAFT_BACKEND_REVISION = "9cda07080f3e27b10d30ec6492ea875c31c82492"
AGENT_FRONTEND_REVISION = "08359de59e756ce73c61df9818c7e7bcaeb86975"
AGENT_BACKEND_REVISION = "d56c743dee03112b2a3211a4ccb659ebed9cfda5"
PROJECT_CLOSURE_SCOPE = {
    ("GET", "/api/lists"),
    ("DELETE", "/api/lists/{dynamic}"),
    ("POST", "/api/approval/orders/{dynamic}/reject"),
}
CRAFT_MIGRATED_SCOPE = {
    ("GET", "/api/rule-engine/check-entry"),
    ("PUT", "/api/rules/{dynamic}"),
}
CRAFT_REMOVED_SCOPE = {
    ("DELETE", "/api/craft_lib/equipments/{dynamic}"),
    ("DELETE", "/api/craft_lib/fixtures/{dynamic}"),
    ("POST", "/api/rules/{dynamic}/activate"),
    ("POST", "/api/rules/{dynamic}/deviations"),
    ("POST", "/api/rules/{dynamic}/suspend"),
}
PROJECT_FRONTEND_FILES = (
    "web/core/existing_capability_client.js",
    "dist-production/web/core/existing_capability_client.js",
    "web/components/list_sidebar.js",
    "dist-production/web/components/list_sidebar.js",
    "packages/craft-plugin/web/bop/bop.js",
    "dist-production/packages/craft-plugin/web/bop/bop.js",
    "packages/craft-plugin/web/approval/approval.js",
    "dist-production/packages/craft-plugin/web/approval/approval.js",
)
CRAFT_FRONTEND_FILES = (
    "web/knowledge_hub/pages/gbop_vpps.html",
    "dist-production/web/knowledge_hub/pages/gbop_vpps.html",
    "web/rule_mgmt/rule_mgmt.js",
    "dist-production/web/rule_mgmt/rule_mgmt.js",
    "web/rule_mgmt/rule_mgmt.html",
    "dist-production/web/rule_mgmt/rule_mgmt.html",
    "packages/craft-plugin/web/lineage_view/layout_detail_panel.js",
    "dist-production/packages/craft-plugin/web/lineage_view/layout_detail_panel.js",
    "web/container_card/modes/container_item_detail.js",
    "dist-production/web/container_card/modes/container_item_detail.js",
    "web/container_card/modes/mode_field_detail.js",
    "dist-production/web/container_card/modes/mode_field_detail.js",
)
CRAFT_BACKEND_FILES = (
    "plugins/craft/craft_backend/capabilities/rule_engine.py",
    "plugins/craft/craft_backend/capabilities/rule_library.py",
    "plugins/craft/craft_backend/capabilities/contracts.py",
    "plugins/craft/craft_backend/capabilities/provider.py",
    "backend/capability_v2/gateway.py",
)
AGENT_FRONTEND_FILES = (
    "packages/agent-plugin/web/flow_canvas/flow_editor.js",
    "dist-production/packages/agent-plugin/web/flow_canvas/flow_editor.js",
    "web/canvas/types/flow_type.js",
    "dist-production/web/canvas/types/flow_type.js",
    "packages/agent-plugin/web/wfc_window/wfc_window.js",
    "dist-production/packages/agent-plugin/web/wfc_window/wfc_window.js",
)
AGENT_BACKEND_FILES = (
    "plugins/agent/agent_backend/capabilities/contracts.py",
    "plugins/agent/agent_backend/capabilities/descriptors.py",
    "plugins/agent/agent_backend/capabilities/provider.py",
    "plugins/agent/agent_backend/capabilities/__init__.py",
    "plugins/agent/agent_backend/application/canvas_runtime.py",
    "plugins/agent/agent_backend/application/service.py",
    "plugins/agent/agent_backend/infrastructure/repository.py",
    "backend/db/migrations/domains/agent/0003_canvas_execution_control.sql",
    "backend/capability_v2/gateway.py",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _anchor(
    source_path: str, start_line: int, end_line: int, *needles: str,
    revision: str | None = None,
) -> dict[str, Any]:
    """Bind reviewed source semantics to both a line range and full-file content."""
    data = (
        (ROOT / source_path).read_bytes()
        if revision is None else read_path(ROOT, revision, source_path)
    )
    lines = data.decode("utf-8").splitlines(keepends=True)
    selected = "".join(lines[start_line - 1:end_line])
    if not selected or any(needle not in selected for needle in needles):
        raise ValueError(f"source anchor drift: {source_path}:{start_line}-{end_line}")
    return {
        "source_path": source_path,
        "start_line": start_line,
        "end_line": end_line,
        "source_sha256": _sha256(data),
        "snippet_sha256": _sha256(selected.encode("utf-8")),
    }


def _git_blob(root: Path, revision: str, source_path: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", f"{revision}:{source_path}"], cwd=root,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _git_tree(root: Path, revision: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", f"{revision}^{{tree}}"], cwd=root,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _frontend_file(web_root: Path, revision: str, source_path: str) -> tuple[dict[str, Any], str]:
    data = read_path(web_root, revision, source_path)
    return ({
        "blob": _git_blob(web_root, revision, source_path),
        "sha256": _sha256(data),
    }, data.decode("utf-8"))


def _frontend_anchor(
    web_root: Path, revision: str, source_path: str, needle: str, occurrence: int = 0,
) -> dict[str, Any]:
    data = read_path(web_root, revision, source_path)
    lines = data.decode("utf-8").splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if needle in line]
    if len(matches) <= occurrence:
        raise ValueError(f"frontend source anchor drift: {source_path}:{needle}")
    index = matches[occurrence]
    return {
        "source_path": source_path,
        "line": index + 1,
        "source_sha256": _sha256(data),
        "snippet_sha256": _sha256(lines[index].encode("utf-8")),
        "blob": _git_blob(web_root, revision, source_path),
    }


def _source_block(source: str, start: str, end: str, *, label: str) -> str:
    try:
        start_index = source.index(start)
        end_index = source.index(end, start_index)
    except ValueError as exc:
        raise ValueError(f"{label} source drift") from exc
    return source[start_index:end_index]


def _list_dispatch_evidence(source: str) -> dict[str, Any]:
    """Derive the finite owner dispatch and fail-closed branch from shipped JavaScript."""
    block = _source_block(
        source, "const LIST_CAPABILITIES", "function listSearch", label="list dispatch",
    )
    mapping_block = _source_block(
        block, "const LIST_CAPABILITIES", "const projectListTypes", label="list dispatch",
    )
    rows = re.findall(
        r"^\s*(bop_version|project):\s*Object\.freeze\(\{\s*"
        r"search:\s*'([^']+)',\s*delete:\s*'([^']+)'\s*\}\),\s*$",
        mapping_block,
        flags=re.MULTILINE,
    )
    capabilities = {
        family: {"search": f"{search}@1", "delete": f"{delete}@1"}
        for family, search, delete in rows
    }
    expected = {
        "bop_version": {
            "search": "craft.bop.version.list@1",
            "delete": "craft.bop.version.archive@1",
        },
        "project": {
            "search": "project.list.read.atomic.lists_search@1",
            "delete": "project.list.change.apply.atomic.lists_delete@1",
        },
    }
    fail_closed_fragments = (
        "const error = new TypeError(`capability_not_bound:${itemType ?? 'null'}`);",
        "error.code = 'capability_not_bound';",
        "const family = itemType === 'bop_version'",
        ": projectListTypes.has(itemType) ? 'project' : null;",
        "const capabilityId = family && LIST_CAPABILITIES[family][operation];",
        "if (!capabilityId) throw capabilityNotBound(itemType);",
    )
    if capabilities != expected or any(fragment not in block for fragment in fail_closed_fragments):
        raise ValueError("list dispatch source drift")
    return {
        "capabilities": capabilities,
        "unknown_item_type": {
            "behavior": "throw",
            "error_code": "capability_not_bound",
        },
        "source_block_sha256": _sha256(block.encode("utf-8")),
    }


_JS_TOKEN = re.compile(
    r"(?:\s+|//[^\r\n]*|/\*[\s\S]*?\*/)"
    r"|(?:'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)"
    r"|(?:[A-Za-z_$][A-Za-z0-9_$]*)"
    r"|(?:\?\.|===|!==|=>|==|!=|<=|>=|&&|\|\||\.\.\.)"
    r"|(?:\d+(?:\.\d+)?)"
    r"|(?:.)",
)
_JS_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_NON_CALL_KEYWORDS = {"if", "for", "while", "switch", "catch", "with", "function"}


def _javascript_tokens(source: str) -> list[str]:
    return [
        token for token in _JS_TOKEN.findall(source)
        if not token.isspace() and not token.startswith("//") and not token.startswith("/*")
    ]


def _direct_call_callee(tokens: list[str], open_index: int) -> tuple[str, int] | None:
    """Return a direct dotted callee, or a fail-closed expression marker."""
    index = open_index - 1
    if index < 0:
        return None
    if tokens[index] in {"?."}:
        index -= 1
    if index < 0:
        return None
    if tokens[index] in {")", "]"}:
        marker = "parenthesized_expression" if tokens[index] == ")" else "computed_member"
        return marker, index
    if _JS_IDENT.fullmatch(tokens[index]) is None:
        return None
    parts = [tokens[index]]
    start = index
    index -= 1
    while index >= 1 and tokens[index] in {".", "?."} and _JS_IDENT.fullmatch(tokens[index - 1]):
        parts.insert(0, tokens[index - 1])
        start = index - 1
        index -= 2
    callee = ".".join(parts)
    if callee in _NON_CALL_KEYWORDS:
        return None
    if start > 0 and tokens[start - 1] == "function":
        return None
    return callee, start


def _approval_call_expressions(flow: str) -> list[dict[str, Any]]:
    """Classify every call expression; unfamiliar syntax and callees fail closed."""
    tokens = _javascript_tokens(flow)
    local_ui = {
        "alert",
        "document.getElementById",
        "loadOrders",
        "selectOrder",
        "window.confirm",
    }
    local_pure = {
        "Number.isInteger",
        "Object.freeze",
        "window.crypto.randomUUID",
    }
    calls: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token != "(":
            continue
        parsed = _direct_call_callee(tokens, index)
        if parsed is None:
            continue
        callee, _start = parsed
        normalized = callee.replace("?.", ".")
        if normalized == "capabilityClient.invoke":
            first_argument = tokens[index + 1] if index + 1 < len(tokens) else ""
            capability = (
                first_argument[1:-1]
                if len(first_argument) >= 2 and first_argument[0] in {'\"', "'"}
                and first_argument[-1] == first_argument[0]
                else None
            )
            classification = (
                "allowed_outbound"
                if capability == "project.approval.order.reject"
                else "unknown"
            )
            item = {
                "callee": normalized,
                "classification": classification,
                "capability": capability,
            }
        elif normalized in local_ui:
            item = {"callee": normalized, "classification": "local_ui"}
        elif normalized in local_pure or normalized.endswith(".trim"):
            item = {"callee": normalized, "classification": "local_pure"}
        else:
            item = {"callee": normalized, "classification": "unknown"}
        calls.append(item)
    return calls


def _approval_outbound_evidence(source: str) -> dict[str, Any]:
    """Allow only fully classified local calls and the exact Project rejection invoke."""
    flow = _source_block(
        source, "async function rejectOrder()", "async function withdrawOrder()",
        label="approval outbound call",
    )
    classified = _approval_call_expressions(flow)
    unknown = [item["callee"] for item in classified if item["classification"] == "unknown"]
    capability_calls = [
        f"capability:{item['capability']}"
        for item in classified if item["classification"] == "allowed_outbound"
    ]
    if capability_calls != ["capability:project.approval.order.reject"] or unknown:
        raise ValueError("approval outbound call drift")
    return {
        "allowed_outbound_calls": capability_calls,
        "classified_calls": classified,
        "unknown_calls": unknown,
        "flow_sha256": _sha256(flow.encode("utf-8")),
    }


def build_project_closure_evidence(web_root: Path) -> dict[str, Any]:
    """Bind the three closed Project-facing groups to immutable source evidence."""
    web_root = web_root.resolve()
    revision = resolve_revision(web_root, PROJECT_FRONTEND_REVISION)
    if revision != PROJECT_FRONTEND_REVISION:
        raise ValueError(f"frontend closure revision drift: {revision}")

    frontend_files: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    for source_path in PROJECT_FRONTEND_FILES:
        frontend_files[source_path], texts[source_path] = _frontend_file(
            web_root, revision, source_path,
        )

    client_paths = (
        "web/core/existing_capability_client.js",
        "dist-production/web/core/existing_capability_client.js",
    )
    sidebar_paths = (
        "web/components/list_sidebar.js",
        "dist-production/web/components/list_sidebar.js",
    )
    bop_paths = (
        "packages/craft-plugin/web/bop/bop.js",
        "dist-production/packages/craft-plugin/web/bop/bop.js",
    )
    approval_paths = (
        "packages/craft-plugin/web/approval/approval.js",
        "dist-production/packages/craft-plugin/web/approval/approval.js",
    )
    list_search_absent = all("/api/lists" not in texts[path] for path in client_paths)
    list_delete_absent = list_search_absent and all(
        "/api/lists/${gid}" not in texts[path] for path in sidebar_paths
    ) and all("/api/lists/${ver.gid}" not in texts[path] for path in bop_paths)
    reject_literal = "/api/approval/orders/${_selected.gid}/reject"
    approval_reject_absent = all(reject_literal not in texts[path] for path in approval_paths)
    source_list_dispatch = _list_dispatch_evidence(texts[client_paths[0]])
    dist_list_dispatch = _list_dispatch_evidence(texts[client_paths[1]])
    if source_list_dispatch != dist_list_dispatch:
        raise ValueError("list dispatch source/dist drift")
    source_approval_outbound = _approval_outbound_evidence(texts[approval_paths[0]])
    dist_approval_outbound = _approval_outbound_evidence(texts[approval_paths[1]])
    if (
        source_approval_outbound["classified_calls"]
        != dist_approval_outbound["classified_calls"]
    ):
        raise ValueError("approval outbound source/dist drift")
    notification_side_effect_absent = True
    if not all((list_search_absent, list_delete_absent, approval_reject_absent, notification_side_effect_absent)):
        raise ValueError("Project/List frontend closure drift")

    list_provider = _anchor(
        "plugins/project_management/project_management_backend/capabilities/reviewed.py",
        207, 235, "atomic_id =", "register_capability",
    )
    list_operations = _anchor(
        "plugins/project_management/project_management_backend/application/service.py",
        179, 182, '"lists.search"', '"lists.delete"',
    )
    list_service = _anchor(
        "plugins/project_management/project_management_backend/application/service.py",
        516, 562, 'operation == "lists.search"', 'operation == "lists.delete"',
    )
    list_dispatch = {
        **source_list_dispatch,
        "dist_source_block_sha256": dist_list_dispatch["source_block_sha256"],
        "frontend_anchor": _frontend_anchor(
            web_root, revision, client_paths[0], "const LIST_CAPABILITIES",
        ),
        "project_provider": list_provider,
        "project_operations": list_operations,
        "project_service": list_service,
        "craft_list_provider": _anchor(
            "plugins/craft/craft_backend/capabilities/bop_versions.py",
            368, 395, 'id="craft.bop.version.list"', "list_bop_versions",
        ),
        "craft_list_input_contract": _anchor(
            "plugins/craft/craft_backend/capabilities/contracts.py",
            43, 52, '"craft.bop.version.list"', "page_size",
        ),
        "craft_list_output_contract": _anchor(
            "plugins/craft/craft_backend/capabilities/contracts.py",
            180, 196, '"craft.bop.version.list"', "next_cursor",
        ),
        "craft_archive_provider": _anchor(
            "plugins/craft/craft_backend/capabilities/bop_writes.py",
            462, 484, "def archive_bop_version", 'id="craft.bop.version.archive"',
        ),
        "craft_archive_input_contract": _anchor(
            "plugins/craft/craft_backend/capabilities/contracts.py",
            118, 127, '"craft.bop.version.archive"', "expected_revision",
        ),
        "craft_archive_output_contract": _anchor(
            "plugins/craft/craft_backend/capabilities/contracts.py",
            237, 247, '"craft.bop.version.archive"', "after_hash",
        ),
    }
    approval = {
        "provider_contract": _anchor(
            "plugins/project_management/project_management_backend/capabilities/reviewed.py",
            244, 281, "APPROVAL_REJECT_CAPABILITY_ID", "notification_event_gid",
        ),
        "provider_policy": _anchor(
            PROJECT_PROVIDER_SOURCE, 42, 75,
            'spec.id == "project.approval.order.reject"', '"replay_data_policy"',
            '"concurrency_policy"',
        ),
        "owner_service": _anchor(
            PROJECT_SERVICE_SOURCE, 459, 511, "def reject_order", "canonical_rejection_result",
            "enqueue_approval_rejection_notification", "audit_approval_rejection",
        ),
        "outbox_transaction": _anchor(
            "plugins/project_management/project_management_backend/infrastructure/repository.py",
            16, 119, "claim_approval_rejection", "reject_approval_order",
            "workmanship_proj_notification_outbox", "complete_approval_rejection", "audit_approval_rejection",
        ),
        "migration": _anchor(
            "backend/db/migrations/domains/project_management/0002_approval_notification_outbox.sql",
            34, 46, "workmanship_proj_notification_outbox", "idx_proj_notification_outbox_delivery",
        ),
        "gateway_context": _anchor(
            "backend/capability_v2/gateway.py", 518, 532,
            "CapabilityContext", "idempotency_key=envelope.idempotency_key",
        ),
        "gateway_integration": _anchor(
            "plugins/project_management/tests/test_project_approval_reject_gateway_integration.py",
            51, 140, "CapabilityGatewayService", "request_approval", "count_notifications",
        ),
        "frontend_anchor": _frontend_anchor(
            web_root, revision, approval_paths[0],
            "capabilityClient.invoke('project.approval.order.reject'",
        ),
        "web_notification_side_effect_absent": notification_side_effect_absent,
        "outbound_call_evidence": {
            **source_approval_outbound,
            "dist_flow_sha256": dist_approval_outbound["flow_sha256"],
        },
    }
    routes = {
        "GET /api/lists": {
            "candidate_capability": "craft.bop.version.list@1",
            "legacy_route_absent": list_search_absent,
            "frontend_call_sites": [
                _frontend_anchor(web_root, revision, client_paths[0], "craft.bop.version.list"),
            ],
        },
        "DELETE /api/lists/{dynamic}": {
            "candidate_capability": "craft.bop.version.archive@1",
            "legacy_route_absent": list_delete_absent,
            "frontend_call_sites": [
                _frontend_anchor(web_root, revision, client_paths[0], "craft.bop.version.archive"),
                _frontend_anchor(web_root, revision, sidebar_paths[0], ".call('project.lists.delete'"),
                _frontend_anchor(web_root, revision, bop_paths[0], ".call('project.lists.delete'"),
            ],
        },
        "POST /api/approval/orders/{dynamic}/reject": {
            "candidate_capability": "project.approval.order.reject@1",
            "legacy_route_absent": approval_reject_absent,
            "frontend_call_sites": [approval["frontend_anchor"]],
        },
    }
    return {
        "frontend_revision": revision,
        "scanner_materialization": build_git_tree_scan_evidence(
            web_root, revision=revision,
        ),
        "frontend_files": dict(sorted(frontend_files.items())),
        "list_dispatch": list_dispatch,
        "approval": approval,
        "routes": routes,
    }


def _dead_action_evidence(sources: Mapping[str, str]) -> dict[str, Any]:
    """Derive five removed actions from complete pinned source/dist files."""
    vpps_paths = (
        "web/knowledge_hub/pages/gbop_vpps.html",
        "dist-production/web/knowledge_hub/pages/gbop_vpps.html",
    )
    rule_paths = (
        "web/rule_mgmt/rule_mgmt.js",
        "dist-production/web/rule_mgmt/rule_mgmt.js",
    )
    page_paths = (
        "web/rule_mgmt/rule_mgmt.html",
        "dist-production/web/rule_mgmt/rule_mgmt.html",
    )
    if any(path not in sources for path in (*vpps_paths, *rule_paths, *page_paths)):
        raise ValueError("dead Craft action source drift")

    vpps_blocks = [
        _source_block(sources[path], "rowContextMenu: (row) => {", "categoryField:", label="Craft row actions")
        for path in vpps_paths
    ]
    vpps_guard = "if (key !== 'vpps_fixtures' && key !== 'vpps_equipments') {"
    if any(vpps_guard not in block for block in vpps_blocks):
        raise ValueError("dead Craft action source drift")
    forbidden_vpps = {
        "DELETE /api/craft_lib/equipments/{dynamic}": "/api/craft_lib/equipments/${gid}`, { method:'DELETE'",
        "DELETE /api/craft_lib/fixtures/{dynamic}": "/api/craft_lib/fixtures/${gid}`, { method:'DELETE'",
    }
    rule_action_block = [
        _source_block(sources[path], "_actions: (_v, row) => {", "// ── 数据加载", label="Craft rule actions")
        for path in rule_paths
    ]
    rule_label = "状态变更和背离记录不支持"
    forbidden_rule_fragments = (
        "/api/rules/${gid}/activate",
        "/api/rules/${gid}/suspend",
        "/api/rules/${_devRuleGid}/deviations",
        ".btn-rule-action",
        ".btn-rule-dev",
        "add_deviation",
        "saveDeviation",
        'data-action="activate"',
        'data-action="suspend"',
    )
    if (
        any(rule_label not in block for block in rule_action_block)
        or any(fragment in sources[path] for path in rule_paths for fragment in forbidden_rule_fragments)
        or any('id="modal-deviation"' in sources[path] for path in page_paths)
    ):
        raise ValueError("dead Craft action source drift")

    result: dict[str, Any] = {}
    for route_key, fragment in forbidden_vpps.items():
        if any(fragment in sources[path] for path in vpps_paths):
            raise ValueError("dead Craft action source drift")
        result[route_key] = {
            "network_path_absent": True,
            "interactive_control_absent": True,
            "source_block_sha256": [_sha256(block.encode()) for block in vpps_blocks],
        }
    for route_key in (
        "POST /api/rules/{dynamic}/activate",
        "POST /api/rules/{dynamic}/deviations",
        "POST /api/rules/{dynamic}/suspend",
    ):
        result[route_key] = {
            "network_path_absent": True,
            "interactive_control_absent": True,
            "unsupported_state_explicit": True,
            "source_block_sha256": [_sha256(block.encode()) for block in rule_action_block],
        }
    return result


def build_craft_closure_evidence(web_root: Path) -> dict[str, Any]:
    """Bind the seven closed Craft groups to reviewed immutable source."""
    web_root = web_root.resolve()
    frontend_revision = resolve_revision(web_root, CRAFT_FRONTEND_REVISION)
    backend_revision = resolve_revision(ROOT, CRAFT_BACKEND_REVISION)
    if frontend_revision != CRAFT_FRONTEND_REVISION or backend_revision != CRAFT_BACKEND_REVISION:
        raise ValueError("Craft closure revision drift")

    frontend_files: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    for source_path in CRAFT_FRONTEND_FILES:
        frontend_files[source_path], texts[source_path] = _frontend_file(
            web_root, frontend_revision, source_path,
        )
    backend_files: dict[str, dict[str, Any]] = {}
    for source_path in CRAFT_BACKEND_FILES:
        backend_files[source_path], _ = _frontend_file(ROOT, backend_revision, source_path)
        if _sha256((ROOT / source_path).read_bytes()) != backend_files[source_path]["sha256"]:
            raise ValueError(f"backend source drift: {source_path}")

    dead_actions = _dead_action_evidence(texts)
    vpps_anchor = _frontend_anchor(
        web_root, frontend_revision, "web/knowledge_hub/pages/gbop_vpps.html",
        "if (key !== 'vpps_fixtures' && key !== 'vpps_equipments')",
    )
    rule_anchor = _frontend_anchor(
        web_root, frontend_revision, "web/rule_mgmt/rule_mgmt.js",
        "状态变更和背离记录不支持",
    )
    for route_key in (
        "DELETE /api/craft_lib/equipments/{dynamic}",
        "DELETE /api/craft_lib/fixtures/{dynamic}",
    ):
        dead_actions[route_key]["frontend_anchor"] = vpps_anchor
    for route_key in (
        "POST /api/rules/{dynamic}/activate",
        "POST /api/rules/{dynamic}/deviations",
        "POST /api/rules/{dynamic}/suspend",
    ):
        dead_actions[route_key]["frontend_anchor"] = rule_anchor

    evaluation_paths = (
        "packages/craft-plugin/web/lineage_view/layout_detail_panel.js",
        "dist-production/packages/craft-plugin/web/lineage_view/layout_detail_panel.js",
    )
    change_paths = (
        "web/container_card/modes/container_item_detail.js",
        "dist-production/web/container_card/modes/container_item_detail.js",
        "web/container_card/modes/mode_field_detail.js",
        "dist-production/web/container_card/modes/mode_field_detail.js",
    )
    if any(texts[path].count("client.invoke('craft.rule.entry.evaluate'") != 2 for path in evaluation_paths):
        raise ValueError("Craft rule evaluation frontend drift")
    if any("/api/rule-engine/check-entry" in texts[path] for path in evaluation_paths):
        raise ValueError("Craft rule evaluation legacy path drift")
    if any(texts[path].count("'craft.rule.definition.change.apply'") != 1 for path in change_paths):
        raise ValueError("Craft rule definition frontend drift")
    legacy_rule_updates = (
        "`/api/rules/${gid}`, { method: 'PUT'",
        "`/api/rules/${gid}`, { method:'PUT'",
        "_cf('PUT', `/api/rules/${gid}`",
    )
    if any(fragment in texts[path] for path in change_paths for fragment in legacy_rule_updates):
        raise ValueError("Craft rule definition legacy path drift")

    gateway_anchor = {
        "invoke_pipeline": _anchor(
            "backend/capability_v2/gateway.py", 134, 218,
            "validate_payload", "idempotency_key_mismatch", "transaction_participant_required",
        ),
        "provider_descriptor": _anchor(
            "plugins/craft/craft_backend/capabilities/provider.py", 90, 140,
            "descriptor_for", "expected_revision", "idempotency_policy", "domain_errors_complete",
        ),
        "context": _anchor(
            "backend/capability_v2/gateway.py", 520, 532,
            "CapabilityContext", "confirmation_token", "idempotency_key",
        ),
    }
    routes = {
        "GET /api/rule-engine/check-entry": {
            "candidate_capability": "craft.rule.entry.evaluate@1",
            "provider_anchor": _anchor(
                "plugins/craft/craft_backend/capabilities/rule_engine.py", 174, 183,
                'id="craft.rule.entry.evaluate"', "RULE_ENTRY_INPUT_SCHEMA", "evaluate_rule_entry",
            ),
            "contract_evidence": {
                "input_output": _anchor(
                    "plugins/craft/craft_backend/capabilities/contracts.py", 549, 563,
                    'INPUT_SCHEMAS[("craft.rule.entry.evaluate", 1)]',
                    'OUTPUT_SCHEMAS[("craft.rule.entry.evaluate", 1)]', "maxItems",
                ),
            },
            "gateway_anchor": gateway_anchor,
            "frontend_call_sites": [
                _frontend_anchor(web_root, frontend_revision, evaluation_paths[0], "client.invoke('craft.rule.entry.evaluate'", occurrence)
                for occurrence in (0, 1)
            ],
            "legacy_route_absent": True,
        },
        "PUT /api/rules/{dynamic}": {
            "candidate_capability": "craft.rule.definition.change.apply@1",
            "provider_anchor": _anchor(
                "plugins/craft/craft_backend/capabilities/rule_library.py", 165, 194,
                "def change_rule_definition", 'id="craft.rule.definition.change.apply"',
                "expected_revision", "idempotency_key",
            ),
            "contract_evidence": {
                "input_output": _anchor(
                    "plugins/craft/craft_backend/capabilities/rule_library.py", 21, 52,
                    "RULE_DEFINITION_INPUT_SCHEMA", "additionalProperties", "RULE_DEFINITION_OUTPUT_SCHEMA",
                ),
            },
            "gateway_anchor": gateway_anchor,
            "frontend_call_sites": [
                _frontend_anchor(web_root, frontend_revision, path, "'craft.rule.definition.change.apply'")
                for path in (change_paths[0], change_paths[2])
            ],
            "legacy_route_absent": True,
        },
    }
    return {
        "backend_revision": backend_revision,
        "backend_tree": _git_tree(ROOT, backend_revision),
        "backend_files": dict(sorted(backend_files.items())),
        "frontend_revision": frontend_revision,
        "scanner_materialization": build_git_tree_scan_evidence(web_root, revision=frontend_revision),
        "frontend_files": dict(sorted(frontend_files.items())),
        "dead_actions": dict(sorted(dead_actions.items())),
        "routes": routes,
    }


def build_agent_closure_evidence(web_root: Path) -> dict[str, Any]:
    """Bind the four closed Agent groups to reviewed immutable source."""
    web_root = web_root.resolve()
    frontend_revision = resolve_revision(web_root, AGENT_FRONTEND_REVISION)
    backend_revision = resolve_revision(ROOT, AGENT_BACKEND_REVISION)
    if frontend_revision != AGENT_FRONTEND_REVISION or backend_revision != AGENT_BACKEND_REVISION:
        raise ValueError("Agent closure revision drift")

    frontend_files: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    for source_path in AGENT_FRONTEND_FILES:
        frontend_files[source_path], texts[source_path] = _frontend_file(
            web_root, frontend_revision, source_path,
        )
    backend_files: dict[str, dict[str, Any]] = {}
    for source_path in AGENT_BACKEND_FILES:
        backend_files[source_path], _ = _frontend_file(ROOT, backend_revision, source_path)

    pairs = (
        AGENT_FRONTEND_FILES[0:2], AGENT_FRONTEND_FILES[2:4], AGENT_FRONTEND_FILES[4:6],
    )
    if any(texts[source].splitlines() != texts[dist].splitlines() for source, dist in pairs):
        raise ValueError("Agent frontend source/dist drift")
    expected_calls = {
        AGENT_FRONTEND_FILES[0]: {"agent.workflow.node.test.execute": 1},
        AGENT_FRONTEND_FILES[2]: {"agent.workflow.node.test.execute": 1},
        AGENT_FRONTEND_FILES[4]: {
            "agent.canvas.options.resolve": 1,
            "agent.canvas.execution.start": 1,
            "agent.canvas.execution.resume": 1,
        },
    }
    for source, expected in expected_calls.items():
        for capability_id, count in expected.items():
            if texts[source].count(f"invoke('{capability_id}'") != count:
                raise ValueError(f"Agent frontend capability drift: {source}:{capability_id}")
            dist = next(dist for candidate, dist in pairs if candidate == source)
            if texts[dist].count(f"invoke('{capability_id}'") != count:
                raise ValueError(f"Agent frontend distribution drift: {dist}:{capability_id}")
    legacy_routes = (
        "/api/flows/test-node", "/api/skills/canvas-options",
        "/api/skills/execute-canvas", "/api/skills/resume-canvas",
    )
    if any(route in source for source in texts.values() for route in legacy_routes):
        raise ValueError("Agent legacy route or fallback drift")

    provider = _anchor(
        "plugins/agent/agent_backend/capabilities/provider.py", 21, 41,
        "agent.canvas.execution.start", "agent.workflow.node.test.execute",
        '"idempotency_policy": "required"', '"evidence_policy": "required"',
        revision=backend_revision,
    )
    registration = _anchor(
        "plugins/agent/agent_backend/capabilities/__init__.py", 19, 85,
        "agent.workflow.node.test.execute", "agent.canvas.options.resolve",
        "agent.canvas.execution.start", "agent.canvas.execution.resume",
        "ProductionAgentCanvasRuntime", "registry.register", "agent.canvas-execution-worker",
        revision=backend_revision,
    )
    contracts = {
        "queries": _anchor(
            "plugins/agent/agent_backend/capabilities/contracts.py", 102, 142,
            "agent.workflow.node.test.execute", "agent.canvas.options.resolve",
            "additionalProperties", "maxItems",
            revision=backend_revision,
        ),
        "commands": _anchor(
            "plugins/agent/agent_backend/capabilities/contracts.py", 143, 197,
            "agent.canvas.execution.start", "agent.canvas.execution.resume",
            "expected_revision", "pause_token", "outcome_unknown", "maxItems",
            revision=backend_revision,
        ),
    }
    runtime = {
        "finite_port": _anchor(
            "plugins/agent/agent_backend/application/canvas_runtime.py", 506, 513,
            "class AgentCanvasRuntime", "test_node", "resolve_options", "start", "resume",
            revision=backend_revision,
        ),
        "production_adapter": _anchor(
            "plugins/agent/agent_backend/application/canvas_runtime.py", 1095, 1266,
            "class ProductionAgentCanvasRuntime", "MAX_WORKER_ENVELOPE_BYTES",
            "async def test_node", "async def resolve_options", "async def start",
            "async def resume", "reconcile_canvas_command", "invocation_id",
            revision=backend_revision,
        ),
    }
    durable_state = {
        "coordinator_and_dispatcher": _anchor(
            "plugins/agent/agent_backend/application/service.py", 98, 244,
            "class CanvasExecutionCoordinator", "derive_canvas_token",
            "class CanvasExecutionDispatcher", "mark_canvas_invocation_dispatched",
            "reconcile_canvas_command", "record_canvas_uncertainty",
            revision=backend_revision,
        ),
        "repository": _anchor(
            "plugins/agent/agent_backend/infrastructure/repository.py", 102, 394,
            "def create_canvas_start", "def create_canvas_resume", "FOR UPDATE SKIP LOCKED",
            "def complete_canvas_invocation", "def record_canvas_uncertainty",
            "def record_canvas_runtime_result", "def load_canvas_runtime_result",
            revision=backend_revision,
        ),
        "migration": _anchor(
            "backend/db/migrations/domains/agent/0003_canvas_execution_control.sql", 1, 83,
            "workmanship_agent_canvas_runs", "workmanship_agent_canvas_invocations",
            "workmanship_agent_canvas_audit_events", "workmanship_agent_canvas_runtime_results",
            "idempotency_key", "lease_token",
            revision=backend_revision,
        ),
        "lifecycle": registration,
    }
    gateway = {
        "invoke_pipeline": _anchor(
            "backend/capability_v2/gateway.py", 134, 218,
            "validate_payload", "idempotency_key_mismatch", "transaction_participant_required",
            revision=backend_revision,
        ),
        "context": _anchor(
            "backend/capability_v2/gateway.py", 520, 532,
            "CapabilityContext", "confirmation_token", "idempotency_key",
            revision=backend_revision,
        ),
    }
    frontend = {
        "node_editor": _frontend_anchor(
            web_root, frontend_revision, AGENT_FRONTEND_FILES[0],
            "invoke('agent.workflow.node.test.execute'",
        ),
        "node_type": _frontend_anchor(
            web_root, frontend_revision, AGENT_FRONTEND_FILES[2],
            "invoke('agent.workflow.node.test.execute'",
        ),
        "node_editor_idempotency": _frontend_anchor(
            web_root, frontend_revision, AGENT_FRONTEND_FILES[0],
            "idempotencyKey: operation.idempotencyKey",
        ),
        "node_type_idempotency": _frontend_anchor(
            web_root, frontend_revision, AGENT_FRONTEND_FILES[2],
            "idempotencyKey: operation.idempotencyKey",
        ),
        "options": _frontend_anchor(
            web_root, frontend_revision, AGENT_FRONTEND_FILES[4],
            "invoke('agent.canvas.options.resolve'",
        ),
        "resume": _frontend_anchor(
            web_root, frontend_revision, AGENT_FRONTEND_FILES[4],
            "invoke('agent.canvas.execution.resume'",
        ),
        "start": _frontend_anchor(
            web_root, frontend_revision, AGENT_FRONTEND_FILES[4],
            "invoke('agent.canvas.execution.start'",
        ),
    }
    routes = {
        "POST /api/flows/test-node": {
            "candidate_capability": "agent.workflow.node.test.execute@1",
            "provider_anchor": provider, "registration_evidence": registration,
            "contract_evidence": {"input_output": contracts["queries"]},
            "runtime_evidence": runtime, "durable_state_evidence": None,
            "gateway_evidence": gateway,
            "frontend_call_sites": [frontend["node_editor"], frontend["node_type"]],
            "idempotency_caller_evidence": [
                frontend["node_editor_idempotency"], frontend["node_type_idempotency"],
            ],
            "legacy_route_absent": True,
        },
        "POST /api/skills/canvas-options": {
            "candidate_capability": "agent.canvas.options.resolve@1",
            "provider_anchor": provider, "registration_evidence": registration,
            "contract_evidence": {"input_output": contracts["queries"]},
            "runtime_evidence": runtime, "durable_state_evidence": None,
            "gateway_evidence": gateway, "frontend_call_sites": [frontend["options"]],
            "legacy_route_absent": True,
        },
        "POST /api/skills/execute-canvas": {
            "candidate_capability": "agent.canvas.execution.start@1",
            "provider_anchor": provider, "registration_evidence": registration,
            "contract_evidence": {"input_output": contracts["commands"]},
            "runtime_evidence": runtime, "durable_state_evidence": durable_state,
            "gateway_evidence": gateway, "frontend_call_sites": [frontend["start"]],
            "legacy_route_absent": True,
        },
        "POST /api/skills/resume-canvas": {
            "candidate_capability": "agent.canvas.execution.resume@1",
            "provider_anchor": provider, "registration_evidence": registration,
            "contract_evidence": {"input_output": contracts["commands"]},
            "runtime_evidence": runtime, "durable_state_evidence": durable_state,
            "gateway_evidence": gateway, "frontend_call_sites": [frontend["resume"]],
            "legacy_route_absent": True,
        },
    }
    return {
        "backend_revision": backend_revision,
        "backend_tree": _git_tree(ROOT, backend_revision),
        "backend_files": dict(sorted(backend_files.items())),
        "frontend_revision": frontend_revision,
        "scanner_materialization": build_git_tree_scan_evidence(web_root, revision=frontend_revision),
        "frontend_files": dict(sorted(frontend_files.items())),
        "source_dist_semantic_match": True,
        "routes": routes,
    }


def _bop_lifecycle_evidence(key: tuple[str, str]) -> dict[str, Any]:
    if key == ("GET", "/api/lists"):
        return {
            "source": _anchor(LISTS_SOURCE, 123, 140, 'item_type == "bop_version"', '"craft.bop.version.list"'),
            "selector": 'item_type == "bop_version"',
            "capability_id": "craft.bop.version.list",
            "closed_arguments": {"include_archived": False, "page_size": 100},
            "expected_revision_required": False,
            "direct_sql": False,
            "lifecycle_outcome": "Read bounded non-archived Craft BOP versions through the exact owner capability.",
        }
    if key == ("DELETE", "/api/lists/{dynamic}"):
        return {
            "source": _anchor(LISTS_SOURCE, 170, 184, 'item_type == "bop_version"', "expected_revision is required for bop_version", '"craft.bop.version.archive"'),
            "selector": 'item_type == "bop_version"',
            "capability_id": "craft.bop.version.archive",
            "closed_arguments": {"version_gid": "route gid", "expected_revision": "required query integer"},
            "expected_revision_required": True,
            "direct_sql": False,
            "lifecycle_outcome": "Archive the selected Craft BOP version only with its optimistic-concurrency revision.",
            "write_envelope": _anchor(LISTS_SOURCE, 70, 85, "idempotency_key", "approval_reference"),
        }
    raise ValueError(f"not a BOP lifecycle route: {key}")


def _approval_reject_evidence() -> dict[str, Any]:
    text = (ROOT / APPROVAL_SOURCE).read_text(encoding="utf-8")
    if '@router.post("/orders/{gid}/reject")' in text:
        raise ValueError("approval reject route unexpectedly registered")
    return {
        "legacy_reject_route_registered": False,
        "reject_function": _anchor(APPROVAL_SOURCE, 92, 93, "async def reject_order", '"approval.orders.reject"'),
        "adapter_notification": {
            "anchor": _anchor(APPROVAL_SOURCE, 44, 60, "notification = data.pop", "publish_notification"),
            "behavior": "The compatibility adapter removes notification from the response and publishes it after the Project result.",
        },
        "project_operation": _anchor(PROJECT_SERVICE_SOURCE, 148, 148, "approval.orders.reject"),
        "project_audit_policy": {
            "anchor": _anchor(PROJECT_PROVIDER_SOURCE, 66, 71, '"audit_policy": "standard"'),
            "value": "standard",
        },
        "unresolved_gap": "No registered legacy reject route ties the Project transition, standard audit, and adapter notification delivery into one proved idempotent outcome.",
    }


def _baseline() -> tuple[dict[str, Any], bytes]:
    result = subprocess.run(
        ["git", "show", f"{BASELINE}:{LEDGER_PATH}"], cwd=ROOT,
        check=True, capture_output=True,
    )
    return json.loads(result.stdout), result.stdout


def _closure_baseline() -> tuple[dict[str, Any], bytes]:
    result = subprocess.run(
        ["git", "show", f"{CLOSURE_BASELINE}:{REMEDIATION_PATH}"], cwd=ROOT,
        check=True, capture_output=True,
    )
    return json.loads(result.stdout), result.stdout


def _final_occurrence(
    raw: Mapping[str, Any], web_root: Path, revision: str
) -> dict[str, Any]:
    source = raw.get("source")
    if not isinstance(source, str):
        raise ValueError("final source missing")
    return {
        "occurrence_id": raw.get("occurrence_id"),
        "source": source,
        "line": raw.get("line"),
        "column": raw.get("column"),
        "source_sha256": hashlib.sha256(read_path(web_root, revision, source)).hexdigest(),
    }


def _non_equivalence(source: Mapping[str, Any], key: tuple[str, str]) -> dict[str, str]:
    if key in BOP_KEYS:
        return {"input": BOP_REASON, "output": BOP_REASON, "side_effects": BOP_REASON}
    details = source.get("disposition_details", {})
    mismatch = details.get("contract_mismatch") if isinstance(details, Mapping) else None
    if isinstance(mismatch, Mapping) and set(mismatch) == {"input", "output", "side_effects"}:
        return dict(mismatch)
    reason = details.get("no_stable_target_reason") if isinstance(details, Mapping) else None
    if not isinstance(reason, str) or not reason:
        raise ValueError(f"non-equivalence evidence missing: {key}")
    return {"input": reason, "output": reason, "side_effects": reason}


def _entry(
    key: tuple[str, str], source: Mapping[str, Any], contract: Mapping[str, Any] | None,
    final_occurrences: list[dict[str, Any]],
) -> dict[str, Any]:
    details = source.get("disposition_details", {})
    if key in BOP_KEYS:
        provider = source["backend_evidence"]["source_path"]
        provider_hash = _sha256((ROOT / provider).read_bytes())
        candidate = None
        unresolved = BOP_REASON
    else:
        if not contract or contract.get("final_disposition") != "domain_design_required":
            raise ValueError(f"unsafe contract drift: {key}")
        provider = contract["provider_anchor"]
        provider_hash = contract["provider_source_sha256"]
        candidate = details.get("candidate_target_capability") if isinstance(details, Mapping) else None
        unresolved = contract.get("reclassification_reason")
    if not isinstance(unresolved, str) or not unresolved:
        raise ValueError(f"unresolved reason missing: {key}")
    return {
        "method": key[0],
        "normalized_route": key[1],
        "owner_domain": source["owner_domain"],
        "old_occurrences": source["occurrences"],
        "old_route_evidence": source["backend_evidence"],
        "authorization_and_scope": "No public owner service proves legacy actor, tenant, object, or workspace scope equivalence.",
        "candidate_capability": candidate,
        "provider_anchor": provider,
        "provider_source_sha256": provider_hash,
        "input_output_contract": _non_equivalence(source, key),
        "non_equivalence": _non_equivalence(source, key),
        "lifecycle_confirmation_idempotency": "Unresolved: no exact provider proves lifecycle, confirmation, idempotency, rollback, or outcome recovery equivalence.",
        "runtime_execution": "unresolved_no_bounded_runtime_service" if key in AGENT_KEYS else "not_applicable",
        "bop_conditional_branch": key in BOP_KEYS,
        "lifecycle_evidence": _bop_lifecycle_evidence(key) if key in BOP_KEYS else None,
        "approval_reject_evidence": _approval_reject_evidence() if key == ("POST", "/api/approval/orders/{dynamic}/reject") else None,
        "final_occurrences": final_occurrences,
        "final_disposition": "unresolved",
        "unresolved_reason": unresolved,
        "final_inventory_mapping": "unresolved",
    }


def _migrated_entry(
    key: tuple[str, str], source: Mapping[str, Any], occurrences: list[dict[str, Any]],
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    route_key = f"{key[0]} {key[1]}"
    route = closure["routes"][route_key]
    if key == ("GET", "/api/lists"):
        provider = closure["list_dispatch"]["craft_list_provider"]
        contract = {
            "input": closure["list_dispatch"]["craft_list_input_contract"],
            "output": closure["list_dispatch"]["craft_list_output_contract"],
        }
        lifecycle = {
            **_bop_lifecycle_evidence(key),
            "provider": provider,
            "contract": contract,
            "finite_dispatch": closure["list_dispatch"]["capabilities"],
        }
        approval = None
    elif key == ("DELETE", "/api/lists/{dynamic}"):
        provider = closure["list_dispatch"]["craft_archive_provider"]
        contract = {
            "input": closure["list_dispatch"]["craft_archive_input_contract"],
            "output": closure["list_dispatch"]["craft_archive_output_contract"],
        }
        lifecycle = {
            **_bop_lifecycle_evidence(key),
            "provider": provider,
            "contract": contract,
            "finite_dispatch": closure["list_dispatch"]["capabilities"],
        }
        approval = None
    elif key == ("POST", "/api/approval/orders/{dynamic}/reject"):
        provider = closure["approval"]["provider_contract"]
        contract = {
            "provider_contract": closure["approval"]["provider_contract"],
            "provider_policy": closure["approval"]["provider_policy"],
        }
        lifecycle = None
        approval = closure["approval"]
    else:
        raise ValueError(f"not a Project closure route: {key}")
    return {
        "method": key[0],
        "normalized_route": key[1],
        "owner_domain": source["owner_domain"],
        "occurrences": occurrences,
        "old_occurrences": source["occurrences"],
        "old_route_evidence": source["backend_evidence"],
        "authorization_and_scope": "Exact owner Capability applies authenticated actor/team and resource policy before provider execution.",
        "candidate_capability": route["candidate_capability"],
        "provider_anchor": f"{provider['source_path']}:{provider['start_line']}-{provider['end_line']}",
        "provider_source_sha256": provider["source_sha256"],
        "owner_service_evidence": (
            closure["approval"]["owner_service"]
            if approval is not None else provider
        ),
        "contract_evidence": contract,
        "input_output_contract": contract,
        "non_equivalence": None,
        "lifecycle_confirmation_idempotency": "Resolved by the exact owner contract, Gateway policy, and source-anchored replay/concurrency evidence.",
        "runtime_execution": "not_applicable",
        "bop_conditional_branch": key in BOP_KEYS,
        "lifecycle_evidence": lifecycle,
        "approval_reject_evidence": approval,
        "frontend_call_sites": route["frontend_call_sites"],
        "legacy_route_absent": route["legacy_route_absent"],
        "final_occurrences": [],
        "final_disposition": "migrated",
        "unresolved_reason": None,
        "final_inventory_mapping": "capability",
    }


def _craft_migrated_entry(
    key: tuple[str, str], source: Mapping[str, Any], occurrences: list[dict[str, Any]],
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    route = closure["routes"][f"{key[0]} {key[1]}"]
    provider = route["provider_anchor"]
    return {
        "method": key[0],
        "normalized_route": key[1],
        "owner_domain": source["owner_domain"],
        "occurrences": occurrences,
        "old_occurrences": source["occurrences"],
        "old_route_evidence": source["backend_evidence"],
        "authorization_and_scope": "Exact Craft provider and Gateway policy apply authenticated actor/team scope before execution.",
        "candidate_capability": route["candidate_capability"],
        "provider_anchor": f"{provider['source_path']}:{provider['start_line']}-{provider['end_line']}",
        "provider_source_sha256": provider["source_sha256"],
        "owner_service_evidence": provider,
        "contract_evidence": route["contract_evidence"],
        "input_output_contract": route["contract_evidence"],
        "gateway_evidence": route["gateway_anchor"],
        "non_equivalence": None,
        "lifecycle_confirmation_idempotency": "Resolved by the exact Craft contract and source-anchored Gateway policy.",
        "runtime_execution": "bounded_provider" if key == ("GET", "/api/rule-engine/check-entry") else "not_applicable",
        "bop_conditional_branch": False,
        "lifecycle_evidence": None,
        "approval_reject_evidence": None,
        "frontend_call_sites": route["frontend_call_sites"],
        "legacy_route_absent": route["legacy_route_absent"],
        "final_occurrences": [],
        "final_disposition": "migrated",
        "unresolved_reason": None,
        "final_inventory_mapping": "capability",
    }


def _agent_migrated_entry(
    key: tuple[str, str], source: Mapping[str, Any], occurrences: list[dict[str, Any]],
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    route = closure["routes"][f"{key[0]} {key[1]}"]
    provider = route["provider_anchor"]
    return {
        "method": key[0],
        "normalized_route": key[1],
        "owner_domain": source["owner_domain"],
        "occurrences": occurrences,
        "old_occurrences": source["occurrences"],
        "old_route_evidence": source["backend_evidence"],
        "authorization_and_scope": "Exact Agent provider restores authenticated actor/team scope before bounded runtime execution.",
        "candidate_capability": route["candidate_capability"],
        "provider_anchor": f"{provider['source_path']}:{provider['start_line']}-{provider['end_line']}",
        "provider_source_sha256": provider["source_sha256"],
        "owner_service_evidence": route["runtime_evidence"]["production_adapter"],
        "registration_evidence": route["registration_evidence"],
        "contract_evidence": route["contract_evidence"],
        "input_output_contract": route["contract_evidence"],
        "gateway_evidence": route["gateway_evidence"],
        "durable_state_evidence": route["durable_state_evidence"],
        "idempotency_caller_evidence": route.get("idempotency_caller_evidence"),
        "non_equivalence": None,
        "lifecycle_confirmation_idempotency": "Resolved by the exact Agent contract, Gateway policy, production runtime, and durable command state where applicable.",
        "runtime_execution": "bounded_production_runtime",
        "bop_conditional_branch": False,
        "lifecycle_evidence": (
            route["durable_state_evidence"]["lifecycle"]
            if route["durable_state_evidence"] is not None else None
        ),
        "approval_reject_evidence": None,
        "frontend_call_sites": route["frontend_call_sites"],
        "legacy_route_absent": route["legacy_route_absent"],
        "final_occurrences": [],
        "final_disposition": "migrated",
        "unresolved_reason": None,
        "final_inventory_mapping": "capability",
    }


def _removed_dead_entry(
    key: tuple[str, str], source: Mapping[str, Any], occurrences: list[dict[str, Any]],
    closure: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = closure["dead_actions"][f"{key[0]} {key[1]}"]
    return {
        "method": key[0],
        "normalized_route": key[1],
        "owner_domain": source["owner_domain"],
        "occurrences": occurrences,
        "old_occurrences": source["occurrences"],
        "old_route_evidence": source["backend_evidence"],
        "authorization_and_scope": "Not applicable: the non-functional browser action and its dispatch path were removed.",
        "candidate_capability": None,
        "provider_anchor": None,
        "provider_source_sha256": None,
        "owner_service_evidence": None,
        "contract_evidence": None,
        "input_output_contract": _non_equivalence(source, key),
        "gateway_evidence": None,
        "non_equivalence": _non_equivalence(source, key),
        "lifecycle_confirmation_idempotency": "Not applicable: no replacement mutation or control path exists.",
        "runtime_execution": "not_applicable",
        "bop_conditional_branch": False,
        "lifecycle_evidence": None,
        "approval_reject_evidence": None,
        "dead_action_evidence": evidence,
        "frontend_call_sites": [],
        "legacy_route_absent": evidence["network_path_absent"],
        "final_occurrences": [],
        "final_disposition": "removed_dead_entry",
        "unresolved_reason": None,
        "final_inventory_mapping": "removed_dead_entry",
    }


def _build_manifest(web_root: Path) -> dict[str, Any]:
    ledger, ledger_blob = _baseline()
    closure_baseline, closure_baseline_blob = _closure_baseline()
    sources = {
        (item["method"], item["normalized_route"]): item for item in ledger["entries"]
        if (item["method"], item["normalized_route"]) in SCOPE
    }
    if set(sources) != SCOPE:
        raise ValueError("pinned Craft/Agent/Project scope drift")
    atomic = json.loads(ATOMIC_PATH.read_text(encoding="utf-8"))
    contracts = {(item["method"], item["normalized_route"]): item for item in atomic["entries"]}
    if any(key not in contracts for key in SCOPE - BOP_KEYS):
        raise ValueError("atomic contract scope drift")
    prior_entries = {
        (item["method"], item["normalized_route"]): item
        for item in closure_baseline["entries"]
        if (item["method"], item["normalized_route"]) in SCOPE
    }
    if set(prior_entries) != SCOPE:
        raise ValueError("closure baseline scope drift")
    prior_occurrences = {
        key: [dict(item) for item in entry["final_occurrences"]]
        for key, entry in prior_entries.items()
    }
    if (
        len(prior_occurrences) != 14
        or sum(map(len, prior_occurrences.values())) != 17
        or any(entry.get("final_disposition") != "unresolved" for entry in prior_entries.values())
    ):
        raise ValueError("closure baseline count drift")
    project_closure = build_project_closure_evidence(web_root)
    craft_closure = build_craft_closure_evidence(web_root)
    agent_closure = build_agent_closure_evidence(web_root)
    report = json.loads(build_report(
        web_root.resolve(), revision=AGENT_FRONTEND_REVISION,
    ).json())
    if report["frontend_revision"] != agent_closure["frontend_revision"]:
        raise ValueError("frontend closure/report revision drift")
    final_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw in report["routes"]:
        key = raw["method"], raw["normalized_route"]
        if key in SCOPE and raw["disposition"] == "unresolved":
            final_by_key.setdefault(key, []).append(
                _final_occurrence(raw, web_root, report["frontend_revision"])
            )
    if final_by_key or report["counts"].get("unresolved") != 0:
        raise ValueError("final structural inventory drift")
    entries = []
    for key in sorted(SCOPE):
        occurrences = sorted(prior_occurrences[key], key=lambda item: item["occurrence_id"])
        if key in PROJECT_CLOSURE_SCOPE:
            entry = _migrated_entry(key, sources[key], occurrences, project_closure)
        elif key in CRAFT_MIGRATED_SCOPE:
            entry = _craft_migrated_entry(key, sources[key], occurrences, craft_closure)
        elif key in CRAFT_REMOVED_SCOPE:
            entry = _removed_dead_entry(key, sources[key], occurrences, craft_closure)
        elif key in AGENT_KEYS:
            entry = _agent_migrated_entry(key, sources[key], occurrences, agent_closure)
        else:
            raise ValueError(f"unclosed structural group: {key}")
        entries.append(entry)
    counts = {
        "groups": len(entries), "occurrences": sum(len(item["occurrences"]) for item in entries),
        "migrated_groups": sum(item["final_disposition"] == "migrated" for item in entries),
        "migrated_occurrences": sum(
            len(item["occurrences"]) for item in entries if item["final_disposition"] == "migrated"
        ),
        "removed_dead_entry_groups": sum(item["final_disposition"] == "removed_dead_entry" for item in entries),
        "removed_dead_entry_occurrences": sum(
            len(item["occurrences"]) for item in entries if item["final_disposition"] == "removed_dead_entry"
        ),
        "unresolved_groups": sum(item["final_disposition"] == "unresolved" for item in entries),
        "unresolved_occurrences": sum(
            len(item["occurrences"]) for item in entries if item["final_disposition"] == "unresolved"
        ),
    }
    if counts != {"groups": 14, "occurrences": 17, "migrated_groups": 9, "migrated_occurrences": 12, "removed_dead_entry_groups": 5, "removed_dead_entry_occurrences": 5, "unresolved_groups": 0, "unresolved_occurrences": 0}:
        raise ValueError(f"three-domain count drift: {counts}")
    closure_arithmetic = {
        "baseline": {"groups": counts["groups"], "occurrences": counts["occurrences"]},
        "closed": {
            "groups": counts["migrated_groups"] + counts["removed_dead_entry_groups"],
            "occurrences": counts["migrated_occurrences"] + counts["removed_dead_entry_occurrences"],
        },
        "canonical_remainder": {
            "groups": len(final_by_key),
            "occurrences": sum(map(len, final_by_key.values())),
        },
    }
    if any(
        closure_arithmetic["baseline"][field] - closure_arithmetic["closed"][field]
        != closure_arithmetic["canonical_remainder"][field]
        for field in ("groups", "occurrences")
    ):
        raise ValueError("three-domain closure arithmetic drift")
    craft_closure_arithmetic = {
        "baseline": {"groups": 11, "occurrences": 14},
        "closed": {"groups": 7, "occurrences": 9},
        "canonical_remainder": {"groups": 4, "occurrences": 5},
    }
    if any(
        craft_closure_arithmetic["baseline"][field] - craft_closure_arithmetic["closed"][field]
        != craft_closure_arithmetic["canonical_remainder"][field]
        for field in ("groups", "occurrences")
    ):
        raise ValueError("Craft closure arithmetic drift")
    agent_closure_arithmetic = {
        "baseline": craft_closure_arithmetic["canonical_remainder"],
        "closed": {"groups": 4, "occurrences": 5},
        "canonical_remainder": closure_arithmetic["canonical_remainder"],
    }
    if any(
        agent_closure_arithmetic["baseline"][field] - agent_closure_arithmetic["closed"][field]
        != agent_closure_arithmetic["canonical_remainder"][field]
        for field in ("groups", "occurrences")
    ):
        raise ValueError("Agent closure arithmetic drift")
    manifest = {
        "schema_version": "2.0.0",
        "artifact_id": "task-3b3e-craft-agent-project-structural-remediation",
        "source_ledger": LEDGER_PATH,
        "source_ledger_revision": BASELINE,
        "source_ledger_sha256": _sha256(ledger_blob),
        "closure_baseline_revision": CLOSURE_BASELINE,
        "closure_baseline_sha256": _sha256(closure_baseline_blob),
        "frontend_revision": report["frontend_revision"],
        "frontend_content_hash": report["content_hash"],
        "project_closure_evidence": project_closure,
        "craft_closure_evidence": craft_closure,
        "agent_closure_evidence": agent_closure,
        "atomic_contract_manifest_sha256": _sha256(ATOMIC_PATH.read_bytes()),
        "closure_arithmetic": closure_arithmetic,
        "craft_closure_arithmetic": craft_closure_arithmetic,
        "agent_closure_arithmetic": agent_closure_arithmetic,
        "counts": counts,
        "entries": entries,
    }
    manifest["content_sha256"] = _sha256(_canonical(manifest).encode())
    return manifest


def build_manifest(web_root: Path) -> dict[str, Any]:
    return _build_manifest(web_root)


def validate_manifest_against_expected(payload: Mapping[str, Any], expected: Mapping[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    actual = {
        (item.get("method"), item.get("normalized_route")): item
        for item in payload.get("entries", []) if isinstance(item, Mapping)
    }
    wanted = {(item["method"], item["normalized_route"]): item for item in expected["entries"]}
    if set(actual) != set(wanted):
        issues.append("entry_scope_mismatch")
    else:
        for key, wanted_entry in wanted.items():
            entry = actual[key]
            if entry.get("provider_source_sha256") != wanted_entry["provider_source_sha256"]:
                issues.append("provider_hash_mismatch")
            if entry.get("non_equivalence") != wanted_entry["non_equivalence"]:
                issues.append("non_equivalence_evidence_mismatch")
            if entry.get("lifecycle_evidence") != wanted_entry["lifecycle_evidence"]:
                issues.append("lifecycle_evidence_mismatch")
            if entry.get("approval_reject_evidence") != wanted_entry["approval_reject_evidence"]:
                issues.append("approval_evidence_mismatch")
            if entry.get("occurrences") != wanted_entry["occurrences"]:
                issues.append("occurrence_evidence_mismatch")
            if entry.get("contract_evidence") != wanted_entry.get("contract_evidence"):
                issues.append("contract_evidence_mismatch")
            if entry.get("owner_service_evidence") != wanted_entry.get("owner_service_evidence"):
                issues.append("owner_service_evidence_mismatch")
            if entry.get("frontend_call_sites", []) != wanted_entry.get("frontend_call_sites", []):
                issues.append("frontend_evidence_mismatch")
            if entry.get("final_occurrences") != wanted_entry["final_occurrences"]:
                issues.append("final_occurrence_mismatch")
            if (
                entry.get("final_disposition") != wanted_entry["final_disposition"]
                or entry.get("final_inventory_mapping") != wanted_entry["final_inventory_mapping"]
            ):
                issues.append("final_inventory_mismatch")
    without_hash = dict(payload)
    supplied_hash = without_hash.pop("content_sha256", None)
    if supplied_hash != _sha256(_canonical(without_hash).encode()):
        issues.append("content_hash_mismatch")
    expected_without_hash = dict(expected)
    expected_hash = expected_without_hash.pop("content_sha256", None)
    if expected_hash != _sha256(_canonical(expected_without_hash).encode()):
        issues.append("expected_content_hash_mismatch")
    if (
        without_hash.get("source_ledger_revision") != expected_without_hash.get("source_ledger_revision")
        or without_hash.get("source_ledger_sha256") != expected_without_hash.get("source_ledger_sha256")
    ):
        issues.append("source_ledger_evidence_mismatch")
    if without_hash != expected_without_hash:
        issues.append("manifest_evidence_mismatch")
    if dict(payload) != dict(expected):
        issues.append("canonical_document_mismatch")
    return tuple(sorted(set(issues)))


def validate_manifest(payload: Mapping[str, Any], web_root: Path) -> tuple[str, ...]:
    try:
        return validate_manifest_against_expected(payload, _build_manifest(web_root))
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return (f"evidence_build_failed:{type(exc).__name__}",)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    payload = build_manifest(args.web_root)
    rendered = _canonical(payload)
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    if args.check:
        try:
            stored = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise SystemExit("Craft/Agent/Project structural remediation manifest is unreadable")
        issues = validate_manifest_against_expected(stored, payload)
        if issues or _canonical(stored) != rendered:
            raise SystemExit("Craft/Agent/Project structural remediation manifest is stale: " + ", ".join(issues or ("rendered_mismatch",)))
    print(" ".join(f"{key}={value}" for key, value in payload["counts"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
