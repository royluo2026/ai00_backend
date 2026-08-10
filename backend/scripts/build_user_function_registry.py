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
DOMAINS = ("Base", "Craft", "Digital Model", "Simulation", "Ontology", "Knowledge", "Local Integration")
VALID_EXCLUSIONS = {"internal", "operations", "ui_transient"}
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
CAPABILITY_PATTERN = r"(?:base|craft|identity|knowledge|local|ontology|plugin|semantic|system|vismockup)\.[a-z0-9_.]+"
CAPABILITY_RE = re.compile(rf"(?<![a-z0-9_.])({CAPABILITY_PATTERN})(?![a-z0-9_.])")
WEB_CALL_RE = re.compile(r"(?:fetch|_cloudFetch|bridge(?:\.invoke)?)\s*\(\s*[\"']([^\"'\x60${?]+)")

TARGET_CAPABILITIES = {
    "rest:GET:/api/bop/versions": "craft.bop.version.list",
    "rest:GET:/api/bop/versions/{version_gid}/entries": "craft.bop.execution_structure.get",
    "rest:GET:/api/knowledge_hub/items": "knowledge.context.retrieve",
    "rest:GET:/api/ontology/schema/{node_type}": "ontology.concept.resolve",
    "agent_tool:get_bop_entries": "craft.bop.execution_structure.get",
    "agent_tool:list_asm_lines": "craft.bop.execution_structure.get",
    "agent_tool:search_knowledge": "knowledge.context.retrieve",
    "agent_tool:get_ontology_schema": "ontology.concept.resolve",
}


def _relative(path: Path) -> str:
    return path.relative_to(REPOSITORY_ROOT).as_posix()


def _domain(value: str, path: str = "") -> str:
    subject = f"{value} {path}".lower()
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
    if "craft" in subject or "bop" in subject or "pbom" in subject or "gbop" in subject:
        return "Craft"
    return "Base"


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


def _add(found: dict[str, dict], function_id: str, *, consumer: str, source_path: str, domain: str | None = None) -> None:
    row = found.setdefault(function_id, {
        "function_id": function_id,
        "domain": domain or _domain(function_id, source_path),
        "stability": "stable",
        "current_consumers": set(),
        "source_paths": set(),
    })
    row["current_consumers"].add(consumer)
    row["source_paths"].add(source_path)


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
            for endpoint in WEB_CALL_RE.findall(content):
                if endpoint.startswith("/api/"):
                    function_id = f"web:{endpoint}"
                else:
                    function_id = f"web:bridge:{endpoint}"
                _add(found, function_id, consumer="Web", source_path=relative)
    return found


def scan_capability_registrations(root: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
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
            for capability_id in CAPABILITY_RE.findall(content):
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
    path = root / "backend" / "capabilities" / "local_runtime_next.py"
    if not path.exists():
        return found
    content = path.read_text(encoding="utf-8")
    for command in re.findall(r"\(\s*[\"']((?:vismockup|local)\.[a-z0-9_.]+)[\"']", content):
        _add(found, f"local_command:{command}", consumer="Local Runtime", source_path=_relative(path), domain="Local Integration")
    return found


def discover_user_functions(root: Path = REPOSITORY_ROOT) -> list[dict]:
    """Return sorted records discovered from every supported public-function surface."""
    found: dict[str, dict] = {}
    for scanner in (scan_fastapi_routes, scan_web_calls, scan_capability_registrations,
                    scan_agent_tools, scan_mcp_tools, scan_local_runtime_commands):
        for function_id, row in scanner(root).items():
            for consumer in row["current_consumers"]:
                _add(found, function_id, consumer=consumer, source_path=next(iter(row["source_paths"])), domain=row["domain"])
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
        "classification": "mapped" if target_capability else "operations",
        "migration_status": "registered" if function_id.startswith("capability:") else (
            "mapped" if target_capability else "excluded"),
        "owner": discovered["domain"],
        "exclusion_reason": None if target_capability else "Operations or transient interface; not selected for a Capability migration.",
        "source_paths": discovered["source_paths"],
    }


def merge_discovery(existing: dict[str, dict], discovered: list[dict]) -> list[dict]:
    """Merge generated evidence while preserving reviewed governance fields."""
    discovered_by_id = {row["function_id"]: row for row in discovered}
    merged: list[dict] = []
    for function_id in sorted(set(existing) | set(discovered_by_id)):
        if function_id not in discovered_by_id:
            merged.append(existing[function_id])
            continue
        generated = _defaults(discovered_by_id[function_id])
        previous = existing.get(function_id)
        if previous:
            generated.update(previous)
            generated["current_consumers"] = discovered_by_id[function_id]["current_consumers"]
            generated["source_paths"] = discovered_by_id[function_id]["source_paths"]
            if previous.get("classification") == "unreviewed":
                generated.update({key: value for key, value in _defaults(discovered_by_id[function_id]).items()
                                  if key not in {"current_consumers", "source_paths"}})
                generated["current_consumers"] = discovered_by_id[function_id]["current_consumers"]
                generated["source_paths"] = discovered_by_id[function_id]["source_paths"]
        merged.append(generated)
    return merged


def registry_errors(existing: dict[str, dict], discovered: list[dict]) -> list[str]:
    discovered_ids = {row["function_id"] for row in discovered}
    errors: list[str] = []
    for row in discovered:
        if row["stability"] == "stable" and row["function_id"] not in existing:
            errors.append(f"missing stable function: {row['function_id']}")
    for function_id, row in existing.items():
        if row.get("stability") == "stable" and function_id not in discovered_ids:
            errors.append(f"stale stable function: {function_id}")
        if (row.get("stability") == "stable" and not row.get("target_capability")
                and row.get("classification") not in VALID_EXCLUSIONS):
            errors.append(f"stable function lacks capability or valid exclusion: {function_id}")
    return sorted(set(errors))


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
    parser.add_argument("--check", action="store_true", help="fail if stable functions are missing or stale")
    parser.add_argument("--write", action="store_true", help="write the merged registry")
    args = parser.parse_args(argv)
    existing = load_registry()
    discovered = discover_user_functions()
    errors = registry_errors(existing, discovered)
    if args.check:
        if errors:
            print("User Function Registry drift:", *errors, sep="\n- ", file=sys.stderr)
            return 1
        print(f"User Function Registry check passed: {_counts(existing.values())}")
        return 0
    records = merge_discovery(existing, discovered)
    write_registry(records)
    print(f"User Function Registry written: {_counts(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
