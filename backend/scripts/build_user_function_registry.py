"""Build and check the reviewed User Function Registry.

The registry intentionally keeps human governance decisions in version control.
Discovery refreshes source evidence and consumers; it never removes a record that
was reviewed by a person.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPOSITORY_ROOT / "docs" / "governance" / "user-function-registry.json"
REVIEW_PATH = REPOSITORY_ROOT / "docs" / "governance" / "capability-coverage-review"
CATALOG_PATH = REPOSITORY_ROOT / "docs" / "capabilities" / "catalog.v2.json"
DOMAINS = (
    "Base Platform",
    "Agent",
    "Craft",
    "Digital Model",
    "Project Management",
    "Simulation",
    "Ontology",
    "Knowledge",
    "Local Integration",
)
VALID_EXCLUSIONS = {
    "internal", "operations", "ui_transient", "transport_adapter",
    "unstable_product_surface",
}
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
CAPABILITY_PATTERN = r"(?:base|craft|digital_model|identity|knowledge|local|ontology|plugin|semantic|simulation|system|vismockup)\.[a-z0-9_.]+"
CAPABILITY_RE = re.compile(rf"(?<![a-z0-9_.])({CAPABILITY_PATTERN})(?![a-z0-9_.])")
FETCH_CALL_RE = re.compile(
    r"\b(?:fetch|_cloudFetch)\s*\(\s*(?P<quote>[\"'])(?P<endpoint>[^\"'\x60${]+)(?P=quote)(?P<options>\s*,\s*\{[^{}]*\})?\s*\)"
)
FETCH_START_RE = re.compile(r"\b(?:fetch|_cloudFetch)\s*\(")
FETCH_METHOD_RE = re.compile(r"(?:[\"']method[\"']|method)\s*:\s*[\"'](?P<method>[A-Za-z]+)[\"']")
BRIDGE_INVOKE_RE = re.compile(r"\bbridge\.invoke\s*\(\s*[\"'](?P<name>[^\"']+)[\"']")
AGENT_RUNTIME_STATIC_ROUTE_RE = re.compile(
    r'req\.method\s*===\s*"(?P<method>GET|POST|PUT|PATCH|DELETE)"\s*&&\s*url\.pathname\s*===\s*"(?P<route>/[^\"]+)"'
)
AGENT_RUNTIME_MATCH_RE = re.compile(
    r"const\s+(?P<variable>\w+)\s*=\s*url\.pathname\.match\(/\^(?P<route>.+?)\$/\);"
)
DEFAULT_EXCLUSION_REASON = "Operations or transient interface; not selected for a Capability migration."

TARGET_CAPABILITIES = {
    "rest:GET:/api/bop/versions": "craft.bop.version.list",
    "rest:GET:/api/bop/versions/{version_gid}/entries": "craft.bop.execution_structure.get",
    "rest:GET:/api/knowledge_hub/items": "knowledge.context.retrieve",
    "rest:GET:/api/ontology/schema/{node_type}": "ontology.concept.resolve",
    "rest:GET:/api/simulation/environments": "simulation.environment.list",
    "rest:GET:/api/simulation/environments/{environment_gid}": "simulation.environment.get",
    "rest:POST:/api/simulation/environments": "simulation.environment.create",
    "agent_tool:get_bop_entries": "craft.bop.execution_structure.get",
    "agent_tool:list_asm_lines": "craft.bop.execution_structure.get",
    "agent_tool:search_knowledge": "knowledge.context.retrieve",
    "agent_tool:get_ontology_schema": "ontology.concept.resolve",
}


def _relative(path: Path) -> str:
    return path.relative_to(REPOSITORY_ROOT).as_posix()


def _domain(value: str, path: str = "") -> str:
    subject = f"{value} {path}".lower()
    capability_id = value.lower().removeprefix("capability:")
    if value.lower().startswith("capability:"):
        if capability_id.startswith("base.project."):
            return "Project Management"
        for prefix, domain in (
            ("craft.", "Craft"),
            ("digital_model.", "Digital Model"),
            ("knowledge.", "Knowledge"),
            ("ontology.", "Ontology"),
            ("agent.", "Agent"),
            ("simulation.", "Simulation"),
        ):
            if capability_id.startswith(prefix):
                return domain
    if "vismockup" in subject or "local" in subject or "device" in subject:
        return "Local Integration"
    if "simulation" in subject:
        return "Simulation"
    if "digital" in subject:
        return "Digital Model"
    if "ontology" in subject:
        return "Ontology"
    if "knowledge" in subject:
        return "Knowledge"
    if value.lower() in {
        "agent_tool:find_similar_cases", "agent_tool:recommend_practice",
    }:
        return "Knowledge"
    if value.lower() in {
        "agent_tool:audit_entry_rules", "agent_tool:check_rules", "agent_tool:generate_canvas",
        "agent_tool:get_canvas_state", "agent_tool:get_entry_relations",
        "agent_tool:get_selected_elements", "agent_tool:list_rules", "agent_tool:run_skill_canvas",
    }:
        return "Craft"
    if value.lower().startswith("agent_tool:") and any(
        marker in value.lower() for marker in ("bop", "pbom", "gbop", "craft")
    ):
        return "Craft"
    if value.lower() == "agent_tool:open_in_container":
        return "Local Integration"
    if value.lower() in {"agent_tool:global_search", "agent_tool:search"}:
        return "Base Platform"
    if value.lower() in {
        "agent_tool:list_tasks", "agent_tool:get_task",
        "agent_tool:list_task_lists", "agent_tool:list_issues", "agent_tool:get_issue",
        "agent_tool:list_issue_lists", "agent_tool:list_projects",
        "agent_tool:list_approval_orders", "agent_tool:create_task",
        "agent_tool:update_task", "agent_tool:create_issue", "agent_tool:update_issue",
        "agent_tool:create_approval_order", "agent_tool:add_task_progress_log",
    }:
        return "Project Management"
    if any(marker in subject for marker in (
        "/api/projects", "/api/project/", "base.project.",
        "/api/tasks", "/api/issues", "/api/milestones", "/api/workbenches",
        "/api/workbench/", "/api/workspaces", "/api/task-dependencies",
        "/api/approval/", "/api/lists", "/api/task-templates", "/api/collab/",
        "/api/shares", "/api/share-links", "/api/bitable-sync", "/api/item-entries",
        "/api/change-logs", "/api/follows", "/api/notifications",
        "/api/permission-requests", "/api/mentions", "/share/issues",
        "project_management", "project-management",
        "routers/projects.py", "routers/tasks.py", "routers/issues.py",
    )):
        return "Project Management"
    if any(marker in subject for marker in (
        "/api/agents", "agent.", "agent_runtime", "agent-runtime",
        "plugins/agent", "routers/agents.py", "capabilities/agent_",
    )):
        return "Agent"
    if "craft" in subject or "bop" in subject or "pbom" in subject or "gbop" in subject:
        return "Craft"
    return "Base Platform"


def _resource_types(value: str) -> list[str]:
    subject = value.lower()
    for marker, resource_type in (
        ("bop", "bop"), ("pbom", "pbom"), ("gbop", "gbop"),
        ("knowledge", "knowledge"), ("ontology", "ontology"),
        ("project", "project"), ("device", "device"), ("vismockup", "device"),
    ):
        if marker in subject:
            return [resource_type]
    return ["system"]


def _join_route(prefix: str, route: str) -> str:
    if not route:
        return prefix or "/"
    if route.startswith("/api/") or route in {"/auth", "/users", "/teams", "/admin"}:
        return route
    if not prefix:
        return route if route.startswith("/") else f"/{route}"
    return f"{prefix.rstrip('/')}/{route.lstrip('/')}"


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _router_prefix(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if getattr(node.value.func, "id", None) != "APIRouter":
                continue
            for keyword in node.value.keywords:
                if keyword.arg == "prefix":
                    return _literal(keyword.value) or ""
    return ""


def _add(found: dict[str, dict], function_id: str, *, consumer: str, source_path: str,
         domain: str | None = None, stability: str = "stable") -> None:
    row = found.setdefault(function_id, {
        "function_id": function_id,
        "domain": domain or _domain(function_id, source_path),
        "stability": stability,
        "current_consumers": set(),
        "source_paths": set(),
    })
    row["current_consumers"].add(consumer)
    row["source_paths"].add(source_path)


def scan_web_source(content: str, source_path: str) -> dict[str, dict]:
    """Discover static Web calls, retaining method and dynamic-call audit gaps."""
    found: dict[str, dict] = {}
    static_starts: set[int] = set()
    for match in FETCH_CALL_RE.finditer(content):
        static_starts.add(match.start())
        endpoint = match.group("endpoint")
        if not endpoint.startswith("/api/"):
            continue
        method_match = FETCH_METHOD_RE.search(match.group("options") or "")
        method = method_match.group("method").upper() if method_match else "GET"
        _add(found, f"rest:{method}:{endpoint}", consumer="Web", source_path=source_path)
    for match in BRIDGE_INVOKE_RE.finditer(content):
        _add(found, f"bridge:invoke:{match.group('name')}", consumer="Web", source_path=source_path)
    for match in FETCH_START_RE.finditer(content):
        if match.start() not in static_starts:
            line = content.count("\n", 0, match.start()) + 1
            _add(found, f"web_gap:dynamic_fetch:{source_path}:{line}", consumer="Web",
                 source_path=source_path, stability="experimental")
    return found


def scan_fastapi_routes(root: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for base in (root / "backend" / "routers", root / "plugins"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "routers" not in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            prefix = _router_prefix(tree)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                        continue
                    method = decorator.func.attr.lower()
                    if method not in ROUTE_METHODS or not decorator.args:
                        continue
                    route = _literal(decorator.args[0])
                    if route is None:
                        continue
                    endpoint = _join_route(prefix, route)
                    _add(found, f"rest:{method.upper()}:{endpoint}", consumer="REST", source_path=_relative(path))
    return found


def scan_web_calls(root: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    roots = [root / "dist" / "web", root / "packages", root / "plugins"]
    for base in roots:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".js", ".ts"} or path.name.endswith(".min.js"):
                continue
            relative = _relative(path)
            if base == root / "plugins" and "/web/" not in f"/{relative}/":
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for function_id, row in scan_web_source(content, relative).items():
                _add(found, function_id, consumer="Web", source_path=relative,
                     domain=row["domain"], stability=row["stability"])
    return found


def capability_ids_in_source(content: str, registered_ids: set[str]) -> set[str]:
    """Return only strings that are real frozen Descriptor identities.

    Capability source also contains permission names, subject concepts and
    resource types with the same dotted syntax. Treating those strings as
    invokable functions corrupts the governance registry.
    """
    return set(CAPABILITY_RE.findall(content)) & registered_ids


def _registered_capability_ids(root: Path) -> set[str]:
    catalog_path = root / "docs" / "governance" / "capability-catalog-release.json"
    if not catalog_path.is_file():
        raise FileNotFoundError(
            "frozen Capability Catalog Release is required before User Function discovery"
        )
    document = json.loads(catalog_path.read_text(encoding="utf-8"))
    descriptors = document.get("descriptors")
    if not isinstance(descriptors, list):
        raise ValueError("Capability Catalog Release has no descriptor array")
    result = {
        str(item.get("id") or "")
        for item in descriptors
        if isinstance(item, dict) and item.get("id")
    }
    if not result:
        raise ValueError("Capability Catalog Release contains no descriptor identities")
    return result


def scan_capability_registrations(
    root: Path,
    *,
    registered_ids: set[str] | None = None,
) -> dict[str, dict]:
    found: dict[str, dict] = {}
    known_ids = registered_ids if registered_ids is not None else _registered_capability_ids(root)
    for base in (root / "backend" / "capabilities", root / "plugins"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            relative = _relative(path)
            if base == root / "plugins" and "/capabilities/" not in f"/{relative}/":
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for capability_id in capability_ids_in_source(content, known_ids):
                _add(found, f"capability:{capability_id}", consumer="Capability Registry", source_path=relative)
    return found


def scan_agent_tools(root: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    agent_root = root / "plugins" / "agent"
    if not agent_root.exists():
        return found
    for path in sorted(agent_root.rglob("*.py")):
        if "tool" not in path.name:
            continue
        relative = _relative(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if _literal(key) == "name":
                    name = _literal(value)
                    if name:
                        _add(found, f"agent_tool:{name}", consumer="Agent", source_path=relative)
    return found


def scan_mcp_tools(root: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in sorted(root.glob("**/*.py")):
        if any(part.startswith("pytest-cache-files") for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                   and decorator.func.attr == "tool" for decorator in node.decorator_list):
                _add(found, f"mcp_tool:{node.name}", consumer="MCP", source_path=_relative(path))
    return found


def scan_local_runtime_commands(root: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    path = root / "plugins" / "device" / "device_backend" / "capabilities" / "runtime.py"
    if not path.exists():
        return found
    content = path.read_text(encoding="utf-8")
    for command in re.findall(r"\(\s*[\"']((?:vismockup|local)\.[a-z0-9_.]+)[\"']", content):
        _add(found, f"local_command:{command}", consumer="Local Runtime", source_path=_relative(path), domain="Local Integration")
    return found


def _runtime_route_template(route_pattern: str) -> str:
    route = route_pattern.replace(r"\/", "/")
    parameter_number = 0

    def replace_parameter(_match: re.Match) -> str:
        nonlocal parameter_number
        parameter_number += 1
        return "{session_gid}" if parameter_number == 1 else f"{{parameter_{parameter_number}}}"

    return re.sub(r"\(\[\^/\]\+\)", replace_parameter, route)


def scan_agent_runtime_routes(root: Path) -> dict[str, dict]:
    """Discover the checked-in TypeScript runtime's user-facing HTTP contract."""
    found: dict[str, dict] = {}
    path = root / "services" / "agent-runtime" / "src" / "server.ts"
    if not path.exists():
        return found
    content = path.read_text(encoding="utf-8")
    source_path = _relative(path)
    for match in AGENT_RUNTIME_STATIC_ROUTE_RE.finditer(content):
        _add(found, f"agent_runtime:{match.group('method')}:{match.group('route')}",
             consumer="Agent Runtime API", source_path=source_path, domain="Agent")
    for match in AGENT_RUNTIME_MATCH_RE.finditer(content):
        variable = match.group("variable")
        route = _runtime_route_template(match.group("route"))
        conditions = (
            re.compile(rf'if\s*\(\s*{re.escape(variable)}\s*&&\s*req\.method\s*===\s*"(?P<method>GET|POST|PUT|PATCH|DELETE)"'),
            re.compile(rf'if\s*\(\s*req\.method\s*===\s*"(?P<method>GET|POST|PUT|PATCH|DELETE)"\s*&&\s*{re.escape(variable)}'),
        )
        for condition in conditions:
            for method_match in condition.finditer(content):
                _add(found, f"agent_runtime:{method_match.group('method')}:{route}",
                     consumer="Agent Runtime API", source_path=source_path, domain="Agent")
    return found


def discover_user_functions(root: Path = REPOSITORY_ROOT) -> list[dict]:
    """Return sorted records discovered from every supported public-function surface."""
    found: dict[str, dict] = {}
    for scanner in (scan_fastapi_routes, scan_web_calls, scan_capability_registrations,
                    scan_agent_tools, scan_mcp_tools, scan_local_runtime_commands,
                    scan_agent_runtime_routes):
        for function_id, row in scanner(root).items():
            for consumer in row["current_consumers"]:
                _add(found, function_id, consumer=consumer, source_path=next(iter(row["source_paths"])),
                     domain=row["domain"], stability=row["stability"])
            found[function_id]["source_paths"].update(row["source_paths"])
    return [{**row, "current_consumers": sorted(row["current_consumers"]), "source_paths": sorted(row["source_paths"])}
            for _, row in sorted(found.items())]


def _defaults(discovered: dict) -> dict:
    function_id = discovered["function_id"]
    target_capability = TARGET_CAPABILITIES.get(function_id)
    if function_id.startswith("capability:"):
        target_capability = function_id.removeprefix("capability:")
    if function_id.startswith("local_command:"):
        target_capability = function_id.removeprefix("local_command:")
    automated = function_id.startswith(("agent_tool:", "mcp_tool:", "local_command:", "capability:"))
    return {
        "function_id": function_id,
        "domain": discovered["domain"],
        "stability": discovered["stability"],
        "current_consumers": discovered["current_consumers"],
        "target_capability": target_capability,
        "exposure": "Capability" if function_id.startswith("capability:") else (
            "Agent" if function_id.startswith("agent_tool:") else (
                "MCP" if function_id.startswith("mcp_tool:") else (
                    "Local Runtime" if function_id.startswith("local_command:") else "Web/REST"))),
        "automation_level": "automated" if automated else "interactive",
        "resource_types": _resource_types(function_id),
        "data_classification": "internal",
        "classification": "mapped" if target_capability else "unreviewed",
        "migration_status": "registered" if function_id.startswith("capability:") else (
            "mapped" if target_capability else "candidate"),
        "owner": discovered["domain"],
        "exclusion_reason": None,
        "source_paths": discovered["source_paths"],
    }


def merge_discovery(existing: dict[str, dict], discovered: list[dict]) -> list[dict]:
    """Merge generated evidence while preserving reviewed governance fields."""
    discovered_by_id = {row["function_id"]: row for row in discovered}
    merged: list[dict] = []
    for function_id in sorted(set(existing) | set(discovered_by_id)):
        if function_id not in discovered_by_id:
            retained = dict(existing[function_id])
            if (
                function_id.startswith("capability:")
                and retained.get("migration_status") == "registered"
                and not retained.get("review_notes")
            ):
                # Capability discovery is now constrained by the frozen
                # Descriptor catalog. A stale generated record is therefore a
                # permission/resource literal, or a capability already removed
                # through the catalog compatibility process—not a callable.
                continue
            if retained.get("exclusion_reason") == DEFAULT_EXCLUSION_REASON:
                retained.update({
                    "classification": "unreviewed",
                    "migration_status": "candidate",
                    "exclusion_reason": None,
                })
            if (retained.get("target_capability") is None
                    and retained.get("classification") == "unreviewed"
                    and retained.get("migration_status") == "candidate"
                    and not retained.get("review_notes")):
                continue
            merged.append(retained)
            continue
        generated = _defaults(discovered_by_id[function_id])
        previous = existing.get(function_id)
        if previous:
            generated.update(previous)
            # Domain labels are generated evidence, not a governance override.
            # Recompute them deterministically while retaining reviewed
            # exposure, lifecycle, and explanatory metadata.
            previous_domain = previous.get("domain")
            generated["domain"] = discovered_by_id[function_id]["domain"]
            if previous.get("owner") == previous_domain:
                generated["owner"] = generated["domain"]
            generated["current_consumers"] = discovered_by_id[function_id]["current_consumers"]
            generated["source_paths"] = discovered_by_id[function_id]["source_paths"]
            if (previous.get("classification") == "unreviewed"
                    or previous.get("exclusion_reason") == DEFAULT_EXCLUSION_REASON):
                generated.update({key: value for key, value in _defaults(discovered_by_id[function_id]).items()
                                  if key not in {"current_consumers", "source_paths"}})
                generated["current_consumers"] = discovered_by_id[function_id]["current_consumers"]
                generated["source_paths"] = discovered_by_id[function_id]["source_paths"]
        merged.append(generated)
    return merged


def registry_errors(
    existing: dict[str, dict],
    discovered: list[dict],
    *,
    include_governance: bool = True,
) -> list[str]:
    discovered_by_id = {row["function_id"]: row for row in discovered}
    discovered_ids = set(discovered_by_id)
    errors: list[str] = []
    for row in discovered:
        if row["stability"] == "stable" and row["function_id"] not in existing:
            errors.append(f"missing stable function: {row['function_id']}")
    for function_id, row in existing.items():
        if row.get("stability") == "stable" and function_id not in discovered_ids:
            errors.append(f"stale stable function: {function_id}")
        if function_id in discovered_by_id:
            for field in ("domain", "stability", "current_consumers", "source_paths"):
                actual = row.get(field)
                expected = discovered_by_id[function_id].get(field)
                if isinstance(actual, list):
                    actual = sorted(actual)
                if isinstance(expected, list):
                    expected = sorted(expected)
                if actual != expected:
                    errors.append(f"generated evidence drift for {function_id}: {field}")
        if include_governance:
            if (row.get("stability") == "stable" and not row.get("target_capability")
                    and row.get("classification") not in VALID_EXCLUSIONS):
                errors.append(f"stable function lacks capability or valid exclusion: {function_id}")
            elif row.get("stability") == "stable" and not row.get("target_capability"):
                reason = row.get("exclusion_reason")
                if (not isinstance(reason, str) or len(reason.strip()) < 20
                        or reason == DEFAULT_EXCLUSION_REASON):
                    errors.append(f"stable function lacks a specific reviewed exclusion: {function_id}")
    return sorted(set(errors))


def _owner_key(domain: str) -> str:
    return {
        "Base Platform": "base",
        "Local Integration": "local_integration",
    }.get(domain, domain.lower().replace(" ", "_"))


def load_coverage_reviews(path: Path = REVIEW_PATH) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(review_path.read_text(encoding="utf-8"))
        for review_path in sorted(path.glob("*.json"))
        if review_path.name != "manifest.json"
    ]


def load_catalog_owners(path: Path = CATALOG_PATH) -> dict[str, str]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    return {row["id"]: row["owner_domain"] for row in catalog["capabilities"]}


def _reviewed_dispositions(reviews: list[dict]) -> tuple[dict[str, dict], set[str]]:
    dispositions: dict[str, dict] = {}
    duplicates: set[str] = set()
    for review in reviews:
        domain = review["domain"]
        for function_id, disposition in review.get("excluded_functions", {}).items():
            item = {**disposition, "review_domain": domain, "capability_id": None}
            if function_id in dispositions:
                duplicates.add(function_id)
            dispositions[function_id] = item
        for capability_id, group in review.get("capabilities", {}).items():
            for function_id, disposition in group.get("function_dispositions", {}).items():
                item = {
                    **disposition,
                    "review_domain": domain,
                    "capability_id": capability_id,
                    "kind": group["kind"],
                    "candidate_definition": group.get("candidate_definition"),
                }
                if function_id in dispositions:
                    duplicates.add(function_id)
                dispositions[function_id] = item
    return dispositions, duplicates


def review_disposition_errors(
    registry: dict[str, dict], reviews: list[dict], catalog_owners: dict[str, str]
) -> list[str]:
    """Validate the one-way link from reviewed domain decisions to Registry evidence."""
    dispositions, duplicates = _reviewed_dispositions(reviews)
    errors = [f"duplicate reviewed disposition: {function_id}" for function_id in duplicates]
    for function_id, row in sorted(registry.items()):
        if row.get("stability") != "stable":
            continue
        disposition = dispositions.get(function_id)
        if disposition is None:
            errors.append(f"missing reviewed disposition: {function_id}")
            continue
        if disposition["review_domain"] != row.get("domain"):
            errors.append(f"review domain mismatch: {function_id}")
        if sorted(disposition.get("source_paths", [])) != sorted(row.get("source_paths", [])):
            errors.append(f"review source evidence mismatch: {function_id}")
        resolution = disposition.get("resolution")
        if resolution == "existing_capability":
            capability_id = disposition["capability_id"]
            owner = catalog_owners.get(capability_id)
            if owner is None:
                errors.append(f"dangling Catalog capability: {function_id}")
            elif owner != _owner_key(row["domain"]):
                errors.append(f"capability owner mismatch: {function_id}")
        elif resolution == "new_capability":
            definition = disposition.get("candidate_definition") or {}
            if definition.get("owner_domain") != _owner_key(row["domain"]):
                errors.append(f"capability owner mismatch: {function_id}")
        elif resolution != "excluded":
            errors.append(f"missing reviewed disposition: {function_id}")
    return sorted(set(errors))


def apply_review_dispositions(
    records: dict[str, dict], reviews: list[dict], catalog_owners: dict[str, str]
) -> dict[str, dict]:
    """Return a Registry projection without mutating authored review documents."""
    dispositions, _ = _reviewed_dispositions(reviews)
    projected = {function_id: dict(row) for function_id, row in records.items()}
    for function_id, row in projected.items():
        disposition = dispositions.get(function_id)
        if not disposition:
            continue
        if disposition["review_domain"] != row.get("domain"):
            continue
        if sorted(disposition.get("source_paths", [])) != sorted(row.get("source_paths", [])):
            continue
        resolution = disposition.get("resolution")
        if resolution == "existing_capability":
            if catalog_owners.get(disposition["capability_id"]) != _owner_key(row["domain"]):
                continue
            row.update(target_capability=disposition["capability_id"], classification="mapped")
        elif resolution == "new_capability":
            definition = disposition.get("candidate_definition") or {}
            if definition.get("owner_domain") != _owner_key(row["domain"]):
                continue
            row.update(
                target_capability=disposition["capability_id"],
                classification="proposed",
                migration_status="proposed",
                exclusion_reason=None,
            )
        elif resolution == "excluded":
            migration_status = row.get("migration_status")
            if migration_status == "candidate":
                migration_status = "excluded"
            row.update(
                target_capability=None,
                classification=disposition["classification"],
                migration_status=migration_status,
                exclusion_reason=disposition["reason"],
            )
    return projected


def validate_registry_document(document: object, schema: dict) -> list[str]:
    """Validate this JSON-Schema contract without an optional third-party package."""
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["root must be an object"]
    root_properties = schema["properties"]
    if schema.get("additionalProperties") is False:
        for key in document:
            if key not in root_properties:
                errors.append(f"root has unknown property: {key}")
    for key in schema["required"]:
        if key not in document:
            errors.append(f"root missing required property: {key}")
    if document.get("schema_version") != 1:
        errors.append("root schema_version must be 1")
    functions = document.get("functions")
    if not isinstance(functions, dict):
        return errors + ["functions must be an object"]
    record_schema = schema["$defs"]["UserFunctionRecord"]
    allowed = set(record_schema["properties"])
    required = record_schema["required"]
    for function_id, record in functions.items():
        if not isinstance(record, dict):
            errors.append(f"record {function_id} must be an object")
            continue
        if record_schema.get("additionalProperties") is False:
            for key in record:
                if key not in allowed:
                    errors.append(f"record has unknown property: {key}")
        for key in required:
            if key not in record:
                errors.append(f"record missing required property: {key}")
        if record.get("function_id") != function_id:
            errors.append("record function_id must match its key")
        if record.get("domain") not in DOMAINS:
            errors.append("record has invalid domain")
        if record.get("stability") not in {"stable", "experimental", "deprecated"}:
            errors.append("record has invalid stability")
        if not isinstance(record.get("current_consumers"), list) or not isinstance(record.get("source_paths"), list):
            errors.append("record evidence fields must be arrays")
        if record.get("target_capability") is None:
            classification = record.get("classification")
            reason = record.get("exclusion_reason")
            candidate = classification == "unreviewed" and record.get("migration_status") == "candidate" and reason is None
            reviewed_exclusion = classification in VALID_EXCLUSIONS and isinstance(reason, str) and bool(reason.strip())
            if not (candidate or reviewed_exclusion):
                errors.append("record has invalid exclusion")
    return errors


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("functions", {})


def write_registry(records: Iterable[dict], path: Path = REGISTRY_PATH) -> None:
    document = {
        "schema_version": 1,
        "functions": {row["function_id"]: row for row in sorted(records, key=lambda row: row["function_id"])},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _counts(records: Iterable[dict]) -> str:
    totals = defaultdict(int)
    for row in records:
        totals[row["domain"]] += 1
    return ", ".join(f"{domain}={totals[domain]}" for domain in DOMAINS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail when discovered source evidence is missing, stale, or changed")
    mode.add_argument("--strict", action="store_true", help="run source drift checks and fail for unresolved stable governance candidates")
    parser.add_argument("--write", action="store_true", help="write the merged registry")
    args = parser.parse_args(argv)
    existing = load_registry()
    discovered = discover_user_functions()
    if args.check or args.strict:
        errors = registry_errors(existing, discovered, include_governance=False)
        if args.strict:
            reviews = load_coverage_reviews()
            errors.extend(review_disposition_errors(existing, reviews, load_catalog_owners()))
        if errors:
            print("User Function Registry drift:", *errors, sep="\n- ", file=sys.stderr)
            return 1
        label = "strict check" if args.strict else "check"
        print(f"User Function Registry {label} passed: {_counts(existing.values())}")
        return 0
    records = merge_discovery(existing, discovered)
    reviews = load_coverage_reviews()
    projected = apply_review_dispositions(
        {row["function_id"]: row for row in records}, reviews, load_catalog_owners()
    )
    records = list(projected.values())
    write_registry(records)
    print(f"User Function Registry written: {_counts(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
