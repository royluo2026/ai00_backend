"""Fail-closed completion evaluation for the Capability V2 program."""
from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from .consumer_routes import scan_web_routes
from .atomicity import load_atomicity_dispositions
from .catalog_targets import CatalogTargetIndex
from .route_inventory import audit_route_inventory, load_route_inventory


class CompletionConfigurationError(ValueError):
    """Raised when completion evidence is malformed or cannot be verified."""


@dataclass(frozen=True)
class CompletionReport:
    domains: tuple[str, ...]
    plugin_agent_gateway_only: bool
    independent_domains: int
    sync_production_paths: int
    async_production_paths: int
    cross_domain_sql: int
    internal_imports: int
    consumer_bypasses: int
    catalog_capabilities: int
    failed: tuple[str, ...]
    web_consumer_bypasses: int = 0

    @property
    def complete(self) -> bool:
        return not self.failed

    def serialized(self) -> dict[str, object]:
        document = asdict(self)
        document["domains"] = list(self.domains)
        document["failed"] = list(self.failed)
        return {**document, "complete": self.complete}


def _load_json(path: Path, *, required: bool = True) -> dict:
    if not path.is_file():
        if required:
            raise CompletionConfigurationError(f"missing completion input: {path.as_posix()}")
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompletionConfigurationError(
            f"invalid completion input: {path.as_posix()}"
        ) from exc
    if not isinstance(document, dict):
        raise CompletionConfigurationError(
            f"completion input must be an object: {path.as_posix()}"
        )
    return document


def _relative_path(root: Path, value: str, *, field: str) -> Path:
    pure = PurePosixPath(value)
    if not value or "\\" in value or pure.is_absolute() or ".." in pure.parts:
        raise CompletionConfigurationError(f"{field} must be repository-relative")
    return root.joinpath(*pure.parts)


def _independent_domains(
    root: Path,
    manifests: list[dict],
    required_domains: tuple[str, ...],
) -> tuple[int, list[str]]:
    failures: list[str] = []
    by_id = {
        item.get("domain_id"): item
        for item in manifests
        if isinstance(item, dict) and isinstance(item.get("domain_id"), str)
    }
    database_names: set[str] = set()
    runtime_envs: set[str] = set()
    ddl_envs: set[str] = set()
    independent = 0
    for domain_id in required_domains:
        manifest = by_id.get(domain_id)
        if manifest is None:
            failures.append(f"missing_domain:{domain_id}")
            continue
        database = manifest.get("database")
        if not isinstance(database, dict):
            failures.append(f"domain_not_independent:{domain_id}:database")
            continue
        unique_values = (
            ("database_name", database_names),
            ("runtime_url_env", runtime_envs),
            ("ddl_url_env", ddl_envs),
        )
        duplicate = False
        for key, seen in unique_values:
            value = database.get(key)
            if not isinstance(value, str) or not value or value in seen:
                failures.append(f"domain_not_independent:{domain_id}:{key}")
                duplicate = True
            else:
                seen.add(value)
        artifact_path = manifest.get("artifact_path")
        migration_path = database.get("migration_path")
        if not isinstance(artifact_path, str) or not _relative_path(
            root, artifact_path, field="artifact_path"
        ).is_dir():
            failures.append(f"domain_not_independent:{domain_id}:artifact_path")
            duplicate = True
        if not isinstance(migration_path, str) or not _relative_path(
            root, migration_path, field="migration_path"
        ).is_dir():
            failures.append(f"domain_not_independent:{domain_id}:migration_path")
            duplicate = True
        if not duplicate:
            independent += 1
    return independent, failures


def _boundary_counts(document: dict) -> tuple[int, int]:
    violations = document.get("violations", [])
    if not isinstance(violations, list):
        raise CompletionConfigurationError("boundary violations must be an array")
    return (
        sum(
            isinstance(item, dict) and item.get("category") == "cross_domain_sql"
            for item in violations
        ),
        sum(
            isinstance(item, dict) and item.get("category") == "internal_import"
            for item in violations
        ),
    )


def _iter_python_files(root: Path, configured_roots: list[str]):
    seen: set[Path] = set()
    for value in configured_roots:
        path = _relative_path(root, value, field="consumer_adapter_root")
        candidates = path.rglob("*.py") if path.is_dir() else (path,)
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix == ".py" and candidate not in seen:
                seen.add(candidate)
                yield candidate


def _consumer_bypasses(root: Path, configuration: dict) -> int:
    roots = configuration.get("consumer_adapter_roots", [])
    forbidden_paths = configuration.get("forbidden_consumer_paths", [])
    import_fragments = configuration.get("forbidden_consumer_import_fragments", [])
    call_fragments = configuration.get("forbidden_consumer_call_fragments", [])
    if not all(isinstance(value, str) and value for value in roots):
        raise CompletionConfigurationError("consumer_adapter_roots must contain paths")
    if not all(isinstance(value, str) and value for value in forbidden_paths):
        raise CompletionConfigurationError("forbidden_consumer_paths must contain paths")
    if not all(isinstance(value, str) and value for value in import_fragments):
        raise CompletionConfigurationError(
            "forbidden_consumer_import_fragments must contain strings"
        )
    if not all(isinstance(value, str) and value for value in call_fragments):
        raise CompletionConfigurationError(
            "forbidden_consumer_call_fragments must contain strings"
        )
    violations: set[tuple[str, str]] = set()
    for value in forbidden_paths:
        path = _relative_path(root, value, field="forbidden_consumer_path")
        candidates = path.rglob("*.py") if path.is_dir() else (path,)
        for candidate in candidates:
            if candidate.is_file():
                violations.add(
                    (candidate.relative_to(root).as_posix(), "legacy_consumer_path")
                )
    for path in _iter_python_files(root, roots):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError as exc:
            raise CompletionConfigurationError(
                f"consumer adapter cannot be parsed: {relative}"
            ) from exc
        for node in ast.walk(tree):
            modules: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            for module in modules:
                for fragment in import_fragments:
                    if fragment in module:
                        violations.add((relative, f"import:{module}"))
        for fragment in call_fragments:
            if fragment in text:
                violations.add((relative, f"call:{fragment}"))
    return len(violations)


def _nested_value(document: dict, dotted_path: str):
    value: object = document
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _coverage_invariant_failures(root: Path, configuration: dict) -> list[str]:
    expected = configuration.get("coverage_invariants")
    if not isinstance(expected, dict) or not expected:
        raise CompletionConfigurationError(
            "coverage_invariants must be a non-empty object"
        )
    summary = _load_json(
        root
        / "docs/governance/capability-coverage-review/generated/summary.json"
    )
    failures = []
    for field, expected_value in sorted(expected.items()):
        if not isinstance(field, str) or not isinstance(expected_value, int):
            raise CompletionConfigurationError(
                "coverage_invariants values must be integer predicates"
            )
        actual = _nested_value(summary, field)
        if actual != expected_value:
            failures.append(
                f"coverage_invariant:{field}:{actual}!={expected_value}"
            )
    return failures


def _catalog_capability_count(root: Path) -> int:
    catalog = _load_json(root / "docs/capabilities/catalog.v2.json")
    entries = catalog.get("capabilities")
    if not isinstance(entries, list):
        raise CompletionConfigurationError("Catalog capabilities must be an array")
    capability_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise CompletionConfigurationError("Catalog capability ID is invalid")
        lifecycle_status = entry.get("lifecycle_status")
        if not isinstance(lifecycle_status, str):
            raise CompletionConfigurationError(
                "Catalog capability lifecycle status is invalid"
            )
        if lifecycle_status != "stable":
            continue
        capability_ids.add(entry["id"])
    return len(capability_ids)


def _web_route_inventory_drift(
    root: Path,
    configuration: dict,
    report: dict,
) -> bool:
    """Return whether checked-in Web route evidence differs from a fresh scan."""
    relative = configuration.get("web_route_inventory_artifact")
    if relative is None:
        return False
    if not isinstance(relative, str) or not relative:
        raise CompletionConfigurationError(
            "web_route_inventory_artifact must be a repository-relative path"
        )
    expected = _load_json(_relative_path(root, relative, field="web_route_inventory_artifact"))
    return expected != report


def _route_inventory_failures(root: Path, configuration: dict) -> list[str]:
    artifacts = [
        (field, configuration.get(field))
        for field in ("legacy_route_inventory_artifact", "bff_route_inventory_artifact")
        if configuration.get(field) is not None
    ]
    if not artifacts:
        return []
    replacements: dict[tuple[str, int], str] = {}
    disposition_path = root / "docs/governance/capability-atomicity-dispositions.json"
    if disposition_path.is_file():
        replacements = {
            (item.capability_id, item.major_version): item.replacement_capabilities[0]
            for item in load_atomicity_dispositions(disposition_path).dispositions
            if item.replacement_capabilities
        }
    catalog_index = CatalogTargetIndex.from_catalog(
        _load_json(root / "docs/capabilities/catalog.v2.json"), replacements=replacements
    )
    failures: list[str] = []
    for field, relative in artifacts:
        if not isinstance(relative, str) or not relative:
            raise CompletionConfigurationError(f"{field} must be a repository-relative path")
        inventory = load_route_inventory(_relative_path(root, relative, field=field))
        failures.extend(
            f"{field}:{issue}" for issue in audit_route_inventory(inventory, catalog_index=catalog_index)
        )
    return failures


def _production_path_count(root: Path, document: dict, kind: str) -> int:
    entries = document.get(kind, [])
    if not isinstance(entries, list):
        raise CompletionConfigurationError(f"production paths {kind} must be an array")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise CompletionConfigurationError(f"production path {kind} must be an object")
        path_id = entry.get("path_id")
        if not isinstance(path_id, str) or not path_id or path_id in seen:
            raise CompletionConfigurationError(f"invalid or duplicate production path ID: {path_id}")
        seen.add(path_id)
        source_modules = entry.get("source_modules")
        if not isinstance(source_modules, list) or not source_modules:
            raise CompletionConfigurationError(f"{path_id}: production source is required")
        for value in source_modules:
            if not isinstance(value, str):
                raise CompletionConfigurationError(f"{path_id}: production source is invalid")
            pure = PurePosixPath(value)
            if "tests" in pure.parts or pure.name.startswith("test_"):
                raise CompletionConfigurationError(
                    f"{path_id}: production source cannot be test-only"
                )
            if not _relative_path(root, value, field="production source").is_file():
                raise CompletionConfigurationError(f"{path_id}: production source is missing")
        test_node = entry.get("test_node")
        if not isinstance(test_node, str) or "::test_" not in test_node:
            raise CompletionConfigurationError(f"{path_id}: pytest node is required")
        test_path = test_node.split("::", 1)[0]
        if not _relative_path(root, test_path, field="test_node").is_file():
            raise CompletionConfigurationError(f"{path_id}: pytest file is missing")
    return len(entries)


def evaluate_completion(
    root: Path,
    mode: Literal["progress", "strict"] = "progress",
    web_root: Path | None = None,
) -> CompletionReport:
    """Evaluate the three completion goals from repository-owned evidence."""

    if mode not in {"progress", "strict"}:
        raise ValueError(f"unsupported completion mode: {mode}")
    root = root.resolve()
    configuration = _load_json(
        root / "backend/governance/capability_v2_completion.json"
    )
    if configuration.get("schema_version") != 1:
        raise CompletionConfigurationError("unsupported completion configuration version")
    required = configuration.get("required_domains")
    if (
        not isinstance(required, list)
        or len(required) != 11
        or not all(isinstance(item, str) and item for item in required)
        or len(set(required)) != len(required)
    ):
        raise CompletionConfigurationError("required_domains must contain eleven unique IDs")
    required_domains = tuple(sorted(required))
    manifests_document = _load_json(
        root / "backend/capability_v2/official_domains.json"
    )
    manifests = manifests_document.get("domains", [])
    if not isinstance(manifests, list):
        raise CompletionConfigurationError("official domains must be an array")
    independent, failures = _independent_domains(
        root, manifests, required_domains
    )
    failures.extend(_coverage_invariant_failures(root, configuration))
    failures.extend(_route_inventory_failures(root, configuration))
    boundary = _load_json(root / "backend/governance/boundary_baseline.json")
    cross_domain_sql, internal_imports = _boundary_counts(boundary)
    consumer_bypasses = _consumer_bypasses(root, configuration)
    web_consumer_bypasses = 0
    if web_root is not None:
        web_prefixes = configuration.get(
            "web_legacy_route_prefixes",
            [
                "/api/bop", "/api/gbop", "/api/ontology", "/api/projects",
                "/api/flows", "/api/factory", "/api/simulation", "/api/device",
            ],
        )
        if not isinstance(web_prefixes, list):
            raise CompletionConfigurationError("web_legacy_route_prefixes must be an array")
        allowlisted_routes = configuration.get("web_allowlisted_legacy_routes", [])
        if not isinstance(allowlisted_routes, list) or not all(
            isinstance(value, str) and value for value in allowlisted_routes
        ):
            raise CompletionConfigurationError(
                "web_allowlisted_legacy_routes must be an array of routes"
            )
        web_scan = scan_web_routes(
            Path(web_root), roots=(".",), legacy_prefixes=tuple(web_prefixes),
            allowlisted_legacy_routes=tuple(allowlisted_routes),
        )
        web_consumer_bypasses = web_scan.legacy_count
        if _web_route_inventory_drift(root, configuration, web_scan.serialized()):
            failures.append("web_route_inventory_drift:1")
    catalog_capabilities = _catalog_capability_count(root)
    production_paths = _load_json(
        root / "backend/governance/capability_v2_production_paths.json",
        required=False,
    )
    sync_paths = _production_path_count(root, production_paths, "sync")
    async_paths = _production_path_count(root, production_paths, "async")

    if cross_domain_sql:
        failures.append(f"cross_domain_sql:{cross_domain_sql}")
    if internal_imports:
        failures.append(f"internal_imports:{internal_imports}")
    if consumer_bypasses:
        failures.append(f"consumer_bypasses:{consumer_bypasses}")
    if web_consumer_bypasses:
        failures.append(f"web_consumer_bypasses:{web_consumer_bypasses}")
    if not sync_paths:
        failures.append("sync_production_paths:0")
    if not async_paths:
        failures.append("async_production_paths:0")
    return CompletionReport(
        domains=required_domains,
        plugin_agent_gateway_only=consumer_bypasses == 0,
        independent_domains=independent,
        sync_production_paths=sync_paths,
        async_production_paths=async_paths,
        cross_domain_sql=cross_domain_sql,
        internal_imports=internal_imports,
        consumer_bypasses=consumer_bypasses,
        catalog_capabilities=catalog_capabilities,
        failed=tuple(sorted(failures)),
        web_consumer_bypasses=web_consumer_bypasses,
    )


__all__ = [
    "CompletionConfigurationError",
    "CompletionReport",
    "evaluate_completion",
]
