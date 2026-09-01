"""Fail-closed, AST-only implementation scanner for test governance."""
from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from backend.capability_v2.business_definition import is_generated_business_effect

from .config import GovernanceSettings
from .fingerprint import canonical_fingerprint
from .graph import node_key
from .models import (
    CapabilityBinding,
    CapabilityFingerprint,
    CapabilityMaturity,
    ImplementationNode,
    ImplementationRelation,
    ScanFinding,
    ScannedCapability,
    SnapshotDocument,
)


class ScanPolicyError(RuntimeError):
    """Raised when a scan request would escape the trusted repository boundary."""


_TABLE = re.compile(r"\b(workmanship_[a-z][a-z0-9_]*)\b", re.IGNORECASE)
_MIGRATION_FILE = re.compile(r"^\d{12}_.+\.sql$", re.IGNORECASE)
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_CLASS_TYPES = (
    ("gateway", "gateway"),
    ("provider", "provider"),
    ("domain_port", "port"),
    ("repository", "repository"),
)
_PATH_TYPES = (
    ("rest_route", ("/routes/", "/routers/", "routes.py", "router.py")),
    ("legacy_api", ("legacy", "_api.py")),
    ("mount_binding", ("mount",)),
    ("agent_tool", ("agent_tool",)),
    ("mcp_tool", ("mcp_tool",)),
    ("worker", ("worker", "task")),
    ("local_runtime", ("local_runtime",)),
)


def _json_document(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, Mapping):
            return dumped
    raise TypeError("scanner_requires_structured_manifest")


def _digest(value: Any) -> str:
    return canonical_fingerprint(value)


def _source_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dotted_name(value: ast.AST) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        prefix = _dotted_name(value.value)
        return f"{prefix}.{value.attr}" if prefix else value.attr
    return ""


def _constant_string(value: ast.AST) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _node_type(name: str, path: str) -> str | None:
    lower = f"{path}/{name}".lower()
    if "/tests/" in f"/{path}/" or name.startswith("test_"):
        return "test_case"
    for node_type, markers in _PATH_TYPES:
        if any(marker in lower for marker in markers):
            return node_type
    for node_type, marker in _CLASS_TYPES:
        if marker in lower:
            return node_type
    if "handler" in lower:
        return "handler"
    return None


def _is_http_route_handler(item: ast.AST) -> bool:
    """Return whether an AST declaration is explicitly mounted as an HTTP route."""
    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    methods = {"get", "post", "put", "patch", "delete", "head", "options", "api_route"}
    for decorator in item.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in methods:
            return True
    return False


def _is_retired_http_route(item: ast.AST) -> bool:
    """Return whether an HTTP handler is explicitly retired with status 410."""
    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for decorator in item.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        for keyword in decorator.keywords:
            if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant) and keyword.value.value == 410:
                return True
    for node in ast.walk(item):
        if not isinstance(node, ast.Call) or _dotted_name(node.func).split(".")[-1] != "HTTPException":
            continue
        status = node.args[0] if node.args else next((keyword.value for keyword in node.keywords if keyword.arg == "status_code"), None)
        if isinstance(status, ast.Constant) and status.value == 410:
            return True
    return False


def _normalise_relative(path: Path) -> str:
    return PurePosixPath(path.as_posix()).as_posix()


def _business_action(capability_id: str, descriptor: Mapping[str, Any]) -> str:
    return str(descriptor.get("business_action") or capability_id.rsplit(".", 1)[-1]).strip()


def _business_object(descriptor: Mapping[str, Any]) -> str:
    explicit = str(descriptor.get("business_object") or "").strip()
    if explicit:
        return explicit
    parts = str(descriptor.get("id") or "").split(".")
    return ".".join(parts[1:-1]) if len(parts) > 2 else (parts[-2] if len(parts) == 2 else "")


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (bytes, Mapping)):
        raise ScanPolicyError("product_catalog_string_list_invalid")
    if not isinstance(value, (list, tuple, set, frozenset)):
        if value is None:
            return ()
        raise ScanPolicyError("product_catalog_string_list_invalid")
    if any(not isinstance(item, str) for item in value):
        raise ScanPolicyError("product_catalog_string_list_invalid")
    return tuple(sorted({item.strip() for item in value if item.strip()}))


def _scopes(descriptor: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    read_scope = _strings(descriptor.get("read_scope"))
    write_scope = _strings(descriptor.get("write_scope"))
    selectors = descriptor.get("resource_selectors", ())
    resources = tuple(sorted({
        str(item.get("resource_type") or "").strip()
        for item in selectors if isinstance(item, Mapping) and str(item.get("resource_type") or "").strip()
    })) if isinstance(selectors, (list, tuple)) else ()
    semantic_class = str(descriptor.get("side_effect_level") or "")
    if not read_scope and semantic_class == "read":
        read_scope = resources
    if not write_scope and semantic_class in {"write", "high_risk_write"}:
        write_scope = resources
    return read_scope, write_scope


def _business_evidence(
    descriptor: Mapping[str, Any], business_effect: str, rules: tuple[Mapping[str, Any], ...],
    *, resolved_enforcement_refs: tuple[str, ...] = (), resolved_test_refs: tuple[str, ...] = (),
) -> tuple[Mapping[str, tuple[str, ...]], CapabilityMaturity]:
    generated = is_generated_business_effect(business_effect, descriptor.get("description"))
    no_rule_reason = str(descriptor.get("no_business_invariant_reason") or "").strip()
    enforcement_refs = tuple(sorted({
        str(rule.get("enforcement_ref") or "").strip() for rule in rules
        if str(rule.get("enforcement_ref") or "").strip()
    }))
    test_refs = tuple(sorted({
        ref for rule in rules for ref in _strings(rule.get("test_refs"))
    }))
    rule_ids = tuple(str(rule.get("rule_id") or "").strip() for rule in rules)
    acceptance = _strings(descriptor.get("business_acceptance_criteria"))
    provider_ref = str(descriptor.get("provider_ref") or "").strip()
    definition_hash = str(descriptor.get("business_definition_hash") or "").strip()
    evidence = {
        "A": (business_effect,) + acceptance if business_effect else acceptance,
        "B": tuple(value for value in (_business_object(descriptor), _business_action(str(descriptor.get("id") or ""), descriptor)) if value),
        "C": tuple(value for value in (*rule_ids, no_rule_reason) if value),
        "D": resolved_enforcement_refs,
        "E": resolved_test_refs,
        "F": tuple(value for value in (provider_ref, *_strings(descriptor.get("api_refs"))) if value),
        "G": (definition_hash,) if definition_hash else (),
    }
    if not business_effect:
        maturity = CapabilityMaturity("L1", ("missing_business_effect",))
    elif generated:
        maturity = CapabilityMaturity("L1", ("generated_business_effect",))
    elif rules:
        complete = all(
            str(rule.get(field) or "").strip()
            for rule in rules for field in ("rule_id", "statement", "applies_when", "enforcement_ref", "error_code")
        ) and all(_strings(rule.get("test_refs")) for rule in rules)
        enforcement_resolved = complete and enforcement_refs == resolved_enforcement_refs
        tests_resolved = complete and test_refs == resolved_test_refs
        if enforcement_resolved and tests_resolved:
            maturity = CapabilityMaturity("L3", ("enforcement_mapping_resolved", "rule_test_evidence_resolved"))
        elif complete:
            reasons = []
            if not enforcement_resolved:
                reasons.append("enforcement_ref_unresolved")
            if not tests_resolved:
                reasons.append("rule_test_ref_unresolved")
            maturity = CapabilityMaturity("L2", tuple(reasons))
        else:
            maturity = CapabilityMaturity("L2", ("business_rule_evidence_incomplete",))
    elif no_rule_reason:
        maturity = CapabilityMaturity("L2", ("business_invariants_not_applicable",))
    else:
        maturity = CapabilityMaturity("L1", ("business_rules_missing",))
    return evidence, maturity


@dataclass(frozen=True)
class _AstUnit:
    owner: str
    source_path: str
    symbol: str
    node_type: str
    tree: ast.AST
    source_hash: str
    imported_symbols: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return node_key(self.node_type, self.owner, self.source_path, self.symbol)


@dataclass(frozen=True)
class _TableReference:
    owner: str
    source_path: str
    table: str
    symbol: str | None
    is_migration: bool = False


class GovernanceScanner:
    """Scan only source already bounded by trusted settings and declared manifests."""

    def __init__(
        self,
        settings: GovernanceSettings,
        *,
        registry_snapshot: Iterable[Any] | None = None,
        product_catalog: Mapping[str, Any] | Any | None = None,
        extension_catalog: Mapping[str, Any] | Any | None = None,
        domain_manifests: Mapping[str, Any] | Any | None = None,
        acceptance_manifest: Mapping[str, Any] | Any | None = None,
        acceptance_manifest_path: str = "backend/tests/acceptance/fixtures/case-manifest.json",
    ) -> None:
        self.settings = settings
        self._registry_snapshot = tuple(registry_snapshot or ())
        self._product_catalog = product_catalog
        self._extension_catalog = extension_catalog
        self._domain_manifests = domain_manifests
        self._acceptance_manifest = acceptance_manifest
        self._acceptance_manifest_path = acceptance_manifest_path

    def scan_path(self, requested: Path) -> tuple[Path, ...]:
        """Resolve a caller's repository-relative root only when it is allowlisted."""
        if requested.is_absolute() or ".." in requested.parts or str(requested) in {"", "."}:
            raise ScanPolicyError("scan_path_not_allowlisted")
        relative = _normalise_relative(requested)
        allowed = tuple(PurePosixPath(value).as_posix().rstrip("/") for value in self.settings.allowed_relative_roots)
        if not any(relative == root or relative.startswith(f"{root}/") for root in allowed):
            raise ScanPolicyError("scan_path_not_allowlisted")
        target = (self.settings.repository_root / Path(relative)).resolve()
        repository = self.settings.repository_root.resolve()
        try:
            target.relative_to(repository)
        except ValueError as exc:
            raise ScanPolicyError("scan_path_not_allowlisted") from exc
        if not target.exists():
            return ()
        if target.is_file():
            return (target,) if self._is_safe_repository_file(target) else ()
        return tuple(sorted(path for path in target.rglob("*") if self._is_safe_repository_file(path)))

    def bind_registry_snapshot(self, snapshot: Iterable[Any]) -> None:
        """Attach the authoritative provider registrations before a scan.

        The scanner is deliberately constructed before the capability registry
        in the test-profile bootstrap.  Binding the immutable registry snapshot
        afterwards keeps the scanner read-only while ensuring implementation
        edges are derived from the same registrations that serve requests.
        """
        self._registry_snapshot = tuple(snapshot)

    def scan(self, code_revision: str) -> SnapshotDocument:
        """Create an immutable document without importing or executing scanned source."""
        try:
            return self._scan(code_revision)
        except (ScanPolicyError, OSError, UnicodeError, TypeError, ValueError, SyntaxError) as exc:
            return self._failed_scan(code_revision, exc)

    def _scan(self, code_revision: str) -> SnapshotDocument:
        product = self._require_catalog(self._product_catalog, "product_catalog_required")
        extension = _json_document(self._extension_catalog) if self._extension_catalog is not None else None
        manifests = self._require_manifest(self._domain_manifests)
        domains = self._domains(manifests)
        units, tables, unresolved, source_trees, source_imports = self._parse_allowlisted_sources(domains)
        scan_findings = tuple(
            ScanFinding(
                code="scan_parser_error", severity="blocking", category="parser",
                source_path=source_path, message=reason,
            )
            for _owner, source_path, reason in sorted(set(unresolved))
            if reason == "syntax_error"
        )
        nodes, relations = self._build_nodes_and_relations(units, tables, unresolved)
        capabilities = self._scan_capabilities(product, domains)
        bindings, extra_relations = self._bind_capabilities(
            capabilities, nodes, units, domains, source_trees, source_imports,
        )
        relations.extend(extra_relations)
        test_bindings, test_relations = self._bind_acceptance_tests(capabilities, nodes)
        bindings.extend(test_bindings)
        relations.extend(test_relations)
        capabilities = self._resolve_business_evidence(capabilities, nodes)
        ordered_nodes = tuple(sorted(nodes.values(), key=lambda item: item.canonical_key))
        ordered_relations = tuple(sorted(
            self._unique_relations(relations),
            key=lambda item: (item.from_canonical_key, item.relation_type, item.to_canonical_key),
        ))
        ordered_bindings = tuple(sorted(
            self._unique_bindings(bindings),
            key=lambda item: (item.capability_id, item.major_version, item.node_canonical_key, item.binding_type),
        ))
        ordered_capabilities = tuple(sorted(capabilities, key=lambda item: (item.capability_id, item.major_version)))
        scan_status = "blocked" if scan_findings else "completed"
        snapshot_hash = _digest({
            "product_release_id": str(product.get("release_id", "")),
            "extension_release_id": str(extension.get("release_id", "")) if extension else None,
            "code_revision": code_revision,
            "capabilities": [item.to_json() for item in ordered_capabilities],
            "nodes": [item.to_json() for item in ordered_nodes],
            "bindings": [item.__dict__ for item in ordered_bindings],
            "relations": [item.__dict__ for item in ordered_relations],
            "scan_findings": [item.to_json() for item in scan_findings],
            "scan_status": scan_status,
        })
        return SnapshotDocument(
            product_release_id=str(product.get("release_id", "")),
            extension_release_id=str(extension.get("release_id", "")) if extension else None,
            code_revision=code_revision,
            snapshot_hash=snapshot_hash,
            capabilities=ordered_capabilities,
            nodes=ordered_nodes,
            bindings=ordered_bindings,
            relations=ordered_relations,
            scan_findings=scan_findings,
            scan_status=scan_status,
        )

    def _failed_scan(self, code_revision: str, error: Exception) -> SnapshotDocument:
        message = str(error) or error.__class__.__name__
        category = "parser" if isinstance(error, SyntaxError) else (
            "source_io" if isinstance(error, (OSError, UnicodeError)) else "configuration"
        )
        source_path = "scanner"
        if message.startswith("product_catalog") or message == "scanner_requires_structured_manifest":
            source_path = "product_catalog"
        elif message.startswith("official_domain"):
            source_path = "official_domain_manifests"
        finding = ScanFinding(
            code=f"scan_{category}_error", severity="blocking", category=category,
            source_path=source_path, message=message,
        )
        product_release = ""
        if isinstance(self._product_catalog, Mapping):
            product_release = str(self._product_catalog.get("release_id") or "")
        payload = {
            "product_release_id": product_release, "extension_release_id": None,
            "code_revision": code_revision, "capabilities": [], "nodes": [],
            "bindings": [], "relations": [], "scan_findings": [finding.to_json()],
            "scan_status": "blocked",
        }
        return SnapshotDocument(
            product_release, None, code_revision, _digest(payload), (), (), (), (), (finding,), "blocked",
        )

    @staticmethod
    def _require_catalog(value: Any, message: str) -> Mapping[str, Any]:
        if value is None:
            raise ScanPolicyError(message)
        return _json_document(value)

    @staticmethod
    def _require_manifest(value: Any) -> Mapping[str, Any]:
        if value is None:
            raise ScanPolicyError("official_domain_manifests_required")
        document = _json_document(value)
        if not isinstance(document.get("domains"), (list, tuple)):
            raise ScanPolicyError("official_domain_manifests_invalid")
        return document

    @staticmethod
    def _domains(manifests: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        result: dict[str, Mapping[str, Any]] = {}
        for item in manifests["domains"]:
            if not isinstance(item, Mapping) or not isinstance(item.get("domain_id"), str):
                raise ScanPolicyError("official_domain_manifests_invalid")
            domain_id = item["domain_id"]
            artifact_path = item.get("artifact_path")
            if not isinstance(artifact_path, str) or not artifact_path or Path(artifact_path).is_absolute() or ".." in PurePosixPath(artifact_path).parts:
                raise ScanPolicyError("official_domain_manifests_invalid")
            result[domain_id] = item
        return result

    def _parse_allowlisted_sources(
        self, domains: Mapping[str, Mapping[str, Any]],
    ) -> tuple[
        list[_AstUnit], list[_TableReference], list[tuple[str, str, str]],
        dict[tuple[str, str], ast.Module], dict[tuple[str, str], dict[str, tuple[str, str, str]]],
    ]:
        roots: dict[str, tuple[str, bool]] = {}
        for owner, manifest in domains.items():
            roots[str(manifest["artifact_path"])] = (owner, False)
            database = manifest.get("database")
            if isinstance(database, Mapping):
                migration = database.get("migration_path")
                if isinstance(migration, str):
                    roots[migration] = (owner, True)
                schema_paths = database.get("schema_paths", ())
                if isinstance(schema_paths, (list, tuple)):
                    for schema_path in schema_paths:
                        if isinstance(schema_path, str):
                            roots.setdefault(schema_path, (owner, False))
        units: list[_AstUnit] = []
        tables: list[_TableReference] = []
        unresolved: list[tuple[str, str, str]] = []
        source_trees: dict[tuple[str, str], ast.Module] = {}
        source_imports: dict[tuple[str, str], dict[str, tuple[str, str, str]]] = {}
        deferred_table_names: list[tuple[str, str, int, str, str]] = []
        for relative_root, (owner, is_migration_path) in sorted(roots.items()):
            paths = self._scan_declared_manifest_path(relative_root)
            for path in paths:
                if path.suffix not in {".py", ".sql"} or path.name.startswith("."):
                    continue
                relative = path.relative_to(self.settings.repository_root).as_posix()
                try:
                    source = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if path.suffix == ".sql":
                    is_migration_file = is_migration_path or bool(_MIGRATION_FILE.fullmatch(path.name))
                    tables.extend(_TableReference(owner, relative, table.lower(), None, is_migration_file) for table in _TABLE.findall(source))
                    continue
                try:
                    tree = ast.parse(source, filename=relative)
                except SyntaxError:
                    unresolved.append((owner, relative, "syntax_error"))
                    continue
                source_trees[(owner, relative)] = tree
                imports: dict[str, tuple[str, str, str]] = {}
                for item in tree.body:
                    if not isinstance(item, ast.ImportFrom):
                        continue
                    target_path = self._resolve_import_source(relative, item.module, item.level)
                    if target_path is None:
                        continue
                    for alias in item.names:
                        imports[alias.asname or alias.name] = (owner, target_path, alias.name)
                source_imports[(owner, relative)] = imports
                source_hash = _source_hash(source)
                imported_symbols = tuple(sorted({
                    alias.asname or alias.name.rsplit(".", 1)[-1]
                    for item in tree.body if isinstance(item, (ast.Import, ast.ImportFrom))
                    for alias in item.names
                }))
                classes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
                for item in classes:
                    found_type = _node_type(item.name, relative)
                    if found_type in {"rest_route", "legacy_api"} and (
                        _is_retired_http_route(item) or not _is_http_route_handler(item)
                    ):
                        found_type = None
                    if found_type:
                        units.append(_AstUnit(owner, relative, item.name, found_type, item, source_hash, imported_symbols))
                for assignment in ast.walk(tree):
                    if not isinstance(assignment, ast.Assign):
                        continue
                    text = _constant_string(assignment.value)
                    table_names = {table.lower() for table in _TABLE.findall(text or "")}
                    symbols = tuple(target.id for target in assignment.targets if isinstance(target, ast.Name))
                    if table_names:
                        tables.extend(
                            _TableReference(owner, relative, table, symbol)
                            for table in sorted(table_names) for symbol in symbols or (None,)
                        )
                    elif (
                        isinstance(assignment.value, ast.Name)
                        and any("table" in symbol.lower() for symbol in symbols)
                        and assignment.value.id in imported_symbols
                    ):
                        for symbol in symbols:
                            if "table" in symbol.lower():
                                deferred_table_names.append((owner, relative, assignment.lineno, symbol, assignment.value.id))
                    elif (
                        (any("table" in symbol.lower() or "sql" in symbol.lower() for symbol in symbols))
                        and isinstance(assignment.value, (ast.BinOp, ast.JoinedStr, ast.Call, ast.Name))
                    ):
                        unresolved.append((owner, relative, f"dynamic_table:{assignment.lineno}"))
                for call in ast.walk(tree):
                    if not isinstance(call, ast.Call):
                        continue
                    dotted = _dotted_name(call.func).lower()
                    if dotted.endswith(("execute", "executemany", "text")) and call.args and _constant_string(call.args[0]) is None:
                        unresolved.append((owner, relative, f"dynamic_sql:{call.lineno}"))
        literal_symbols: dict[tuple[str, str], set[str]] = defaultdict(set)
        for reference in tables:
            if reference.symbol:
                literal_symbols[(reference.owner, reference.symbol)].add(reference.table)
        for owner, source_path, lineno, target_symbol, imported_symbol in deferred_table_names:
            candidates = literal_symbols.get((owner, imported_symbol), set())
            if len(candidates) == 1:
                tables.append(_TableReference(owner, source_path, next(iter(candidates)), target_symbol))
            else:
                unresolved.append((owner, source_path, f"dynamic_table:{lineno}"))
        return units, tables, unresolved, source_trees, source_imports

    @staticmethod
    def _resolve_import_source(source_path: str, module: str | None, level: int) -> str | None:
        """Resolve a relative Python import to one repository source path."""
        if level < 0:
            return None
        if level:
            parts = list(PurePosixPath(source_path).parent.parts)
            for _ in range(level - 1):
                if not parts:
                    return None
                parts.pop()
            if module:
                parts.extend(module.split("."))
        elif module and (module.startswith("backend.") or module.startswith("plugins.")):
            parts = module.split(".")
        else:
            return None
        if not parts:
            return None
        return PurePosixPath(*parts).as_posix() + ".py"

    def _scan_declared_manifest_path(self, relative_root: str) -> tuple[Path, ...]:
        """Read one path declared by the official manifest, never a caller path.

        Domain artifacts legitimately include domain packages outside the generic
        configuration roots (for example ``backend/base``).  Those paths are
        trusted only because they came from the already-supplied official
        manifest; public :meth:`scan_path` remains limited to settings roots.
        """
        pure = PurePosixPath(relative_root)
        if pure.is_absolute() or ".." in pure.parts or str(pure) in {"", "."}:
            raise ScanPolicyError("official_domain_manifests_invalid")
        target = (self.settings.repository_root / Path(pure)).resolve()
        repository = self.settings.repository_root.resolve()
        try:
            target.relative_to(repository)
        except ValueError as exc:
            raise ScanPolicyError("official_domain_manifests_invalid") from exc
        if not target.exists():
            return ()
        if target.is_file():
            return (target,) if self._is_safe_repository_file(target) else ()
        return tuple(sorted(path for path in target.rglob("*") if self._is_safe_repository_file(path)))

    def _is_safe_repository_file(self, path: Path) -> bool:
        """Exclude symlinks, oversize inputs, and every resolved path outside the repo."""
        if not path.is_file() or path.is_symlink():
            return False
        try:
            path.resolve().relative_to(self.settings.repository_root.resolve())
            return path.stat().st_size <= _MAX_SOURCE_BYTES
        except (OSError, ValueError):
            return False

    def _build_nodes_and_relations(
        self,
        units: list[_AstUnit],
        tables: list[_TableReference],
        unresolved: list[tuple[str, str, str]],
    ) -> tuple[dict[str, ImplementationNode], list[ImplementationRelation]]:
        nodes: dict[str, ImplementationNode] = {}
        relations: list[ImplementationRelation] = []
        by_symbol: dict[tuple[str, str], list[_AstUnit]] = defaultdict(list)
        for unit in units:
            node = ImplementationNode(unit.key, unit.owner, unit.node_type, unit.source_path, unit.source_hash, unit.symbol)
            nodes[node.canonical_key] = node
            by_symbol[(unit.owner, unit.symbol)].append(unit)
        table_nodes: dict[tuple[str, str], str] = {}
        table_declarations: dict[tuple[str, str], set[str]] = defaultdict(set)
        for reference in sorted(set(tables), key=lambda item: (item.owner, item.table, item.source_path, item.symbol or "")):
            table_nodes.setdefault((reference.owner, reference.table), node_key("database_table", reference.owner, f"tables/{reference.table}", reference.table))
            table_declarations[(reference.owner, reference.table)].add(reference.source_path)
        for (owner, table), key in sorted(table_nodes.items()):
            nodes[key] = ImplementationNode(
                key, owner, "database_table", f"tables/{table}", _digest({"table": table}), table,
                metadata={"declared_by": tuple(sorted(table_declarations[(owner, table)]))},
            )
        table_symbols: dict[tuple[str, str], set[str]] = defaultdict(set)
        tables_by_source: dict[tuple[str, str], set[str]] = defaultdict(set)
        for reference in tables:
            tables_by_source[(reference.owner, reference.source_path)].add(reference.table)
            if reference.symbol:
                table_symbols[(reference.owner, reference.symbol)].add(reference.table)
            if reference.is_migration:
                migration_key = node_key("migration", reference.owner, reference.source_path)
                nodes.setdefault(migration_key, ImplementationNode(migration_key, reference.owner, "migration", reference.source_path, _digest({"migration": reference.source_path})))
                relations.append(self._relation(migration_key, table_nodes[(reference.owner, reference.table)], "migrates_table"))
        for owner, source_path, reason in sorted(set(unresolved)):
            key = node_key("unresolved_binding", owner, source_path, reason)
            nodes[key] = ImplementationNode(key, owner, "unresolved_binding", source_path, _digest({"reason": reason}), reason, metadata={"reason": reason})
        for unit in units:
            for call in ast.walk(unit.tree):
                if not isinstance(call, ast.Call):
                    continue
                candidate = self._called_constructor(call.func)
                if not candidate:
                    continue
                targets = by_symbol.get((unit.owner, candidate), ())
                for target in targets:
                    if target.key != unit.key:
                        relations.append(self._relation(unit.key, target.key, "calls"))
            if unit.node_type == "repository":
                referenced_tables = set(tables_by_source.get((unit.owner, unit.source_path), set()))
                used_names = {item.id for item in ast.walk(unit.tree) if isinstance(item, ast.Name)}
                for symbol in set(unit.imported_symbols) & used_names:
                    candidates = table_symbols.get((unit.owner, symbol), set())
                    if len(candidates) == 1:
                        referenced_tables.update(candidates)
                for table in sorted(referenced_tables):
                    relations.append(self._relation(unit.key, table_nodes[(unit.owner, table)], "persists_to"))
                for key, node in nodes.items():
                    if node.owner_domain == unit.owner and node.node_type == "unresolved_binding" and node.source_path == unit.source_path:
                        relations.append(self._relation(unit.key, key, "unresolved_binding"))
        return nodes, relations

    @staticmethod
    def _called_constructor(function: ast.AST) -> str:
        if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Call):
            inner = function.value.func
            if isinstance(inner, ast.Name):
                return inner.id
        return ""

    def _scan_capabilities(
        self, catalog: Mapping[str, Any], domains: Mapping[str, Mapping[str, Any]],
    ) -> list[ScannedCapability]:
        capabilities: list[ScannedCapability] = []
        for raw_descriptor in catalog.get("descriptors", ()):
            descriptor = dict(_json_document(raw_descriptor))
            capability_id = str(descriptor.get("id", ""))
            major = int(descriptor.get("major_version", 0))
            owner = str(descriptor.get("owner_domain", ""))
            if not capability_id or major < 1 or owner not in domains:
                raise ScanPolicyError("product_catalog_descriptor_invalid")
            artifact = domains[owner].get("artifact")
            provider_hash = str(artifact.get("artifact_hash", "")) if isinstance(artifact, Mapping) else ""
            business_effect = str(descriptor.get("business_effect") or "").strip()
            raw_rules = descriptor.get("business_invariants", ())
            if not isinstance(raw_rules, (list, tuple)):
                raise ScanPolicyError("product_catalog_business_rules_invalid")
            rules = tuple(sorted(
                (dict(_json_document(rule)) for rule in raw_rules),
                key=lambda rule: (str(rule.get("rule_id") or ""), int(rule.get("rule_version") or 0)),
            ))
            identities = [(str(rule.get("rule_id") or "").strip(), int(rule.get("rule_version") or 0)) for rule in rules]
            if any(not rule_id or version < 1 for rule_id, version in identities):
                raise ScanPolicyError("product_catalog_business_rule_invalid")
            if len(set(identities)) != len(identities):
                raise ScanPolicyError("product_catalog_business_rule_duplicate")
            for rule in rules:
                _strings(rule.get("test_refs"))
            descriptor["business_invariants"] = rules
            for field_name in ("read_scope", "write_scope", "api_refs", "business_acceptance_criteria"):
                if field_name in descriptor:
                    descriptor[field_name] = _strings(descriptor[field_name])
            input_hash = _digest(descriptor.get("input_schema", {}))
            output_hash = _digest(descriptor.get("output_schema", {}))
            read_scope, write_scope = _scopes(descriptor)
            fingerprint = CapabilityFingerprint(
                owner_domain=owner,
                business_object=_business_object(descriptor),
                action=_business_action(capability_id, descriptor),
                business_effect=business_effect,
                input_schema_hash=input_hash,
                output_schema_hash=output_hash,
                provider_ref=str(descriptor.get("provider_ref") or ""),
                read_scope=tuple(sorted(read_scope)),
                write_scope=tuple(sorted(write_scope)),
                rule_ids=tuple(sorted(str(rule.get("rule_id") or "") for rule in rules if str(rule.get("rule_id") or ""))),
            )
            layer_evidence, maturity = _business_evidence(descriptor, business_effect, rules)
            capabilities.append(ScannedCapability(
                capability_id=capability_id,
                major_version=major,
                owner_domain=owner,
                semantic_class=str(descriptor.get("side_effect_level", "")),
                business_effect=business_effect,
                lifecycle_status=str(descriptor.get("lifecycle_status", "")),
                descriptor_hash=_digest(descriptor),
                input_schema_hash=input_hash,
                output_schema_hash=output_hash,
                error_schema_hash=_digest(descriptor.get("domain_errors", ())),
                policy_hash=_digest({key: descriptor.get(key) for key in ("authorization_policy", "confirmation_policy", "audit_policy", "idempotency_policy")}),
                provider_hash=provider_hash,
                business_rules=rules,
                fingerprint=fingerprint,
                business_layer_evidence=layer_evidence,
                business_maturity=maturity,
                descriptor=descriptor,
            ))
        return capabilities

    @staticmethod
    def _resolve_business_evidence(
        capabilities: list[ScannedCapability], nodes: Mapping[str, ImplementationNode],
    ) -> list[ScannedCapability]:
        provider_refs: set[tuple[str, str]] = set()
        test_refs: set[tuple[str, str]] = set()
        for node in nodes.values():
            if node.node_type in {"provider", "port", "repository", "handler"} and node.source_symbol:
                provider_refs.add((node.owner_domain, f"{node.source_path}:{node.source_symbol}"))
            if node.node_type == "test_case" and node.source_symbol:
                reference = node.source_symbol if "::" in node.source_symbol else f"{node.source_path}::{node.source_symbol}"
                test_refs.add((node.owner_domain, reference))
        resolved: list[ScannedCapability] = []
        for capability in capabilities:
            enforcement = tuple(sorted({
                str(rule.get("enforcement_ref") or "").strip()
                for rule in capability.business_rules
                if (capability.owner_domain, str(rule.get("enforcement_ref") or "").strip()) in provider_refs
            }))
            tests = tuple(sorted({
                ref for rule in capability.business_rules for ref in _strings(rule.get("test_refs"))
                if (capability.owner_domain, ref) in test_refs
            }))
            evidence, maturity = _business_evidence(
                capability.descriptor, capability.business_effect, capability.business_rules,
                resolved_enforcement_refs=enforcement, resolved_test_refs=tests,
            )
            resolved.append(replace(capability, business_layer_evidence=evidence, business_maturity=maturity))
        return resolved

    def _bind_capabilities(
        self,
        capabilities: list[ScannedCapability],
        nodes: dict[str, ImplementationNode],
        units: list[_AstUnit],
        domains: Mapping[str, Mapping[str, Any]],
        source_trees: Mapping[tuple[str, str], ast.Module],
        source_imports: Mapping[tuple[str, str], Mapping[str, tuple[str, str, str]]],
    ) -> tuple[list[CapabilityBinding], list[ImplementationRelation]]:
        bindings: list[CapabilityBinding] = []
        relations: list[ImplementationRelation] = []
        registry_modules = self._registry_modules()
        descriptor_keys: dict[tuple[str, int], str] = {}
        for capability in capabilities:
            descriptor_path = f"catalog/{capability.capability_id}@{capability.major_version}"
            descriptor_key = node_key("descriptor", capability.owner_domain, descriptor_path)
            descriptor_keys[(capability.capability_id, capability.major_version)] = descriptor_key
            nodes[descriptor_key] = ImplementationNode(
                descriptor_key, capability.owner_domain, "descriptor", descriptor_path,
                capability.descriptor_hash, capability.capability_id,
            )
            bindings.append(self._binding(capability, descriptor_key, "declared_in"))
            module = registry_modules.get((capability.capability_id, capability.major_version))
            providers = [
                unit for unit in units if unit.owner == capability.owner_domain and unit.node_type == "provider"
                and module is not None
                and self.registry_module_matches_source(module, unit.source_path)
            ]
            if not providers:
                reason = "provider_not_resolved"
                key = node_key("unresolved_binding", capability.owner_domain, descriptor_path, reason)
                nodes[key] = ImplementationNode(key, capability.owner_domain, "unresolved_binding", descriptor_path, _digest({"reason": reason}), reason, metadata={"reason": reason})
                relations.append(self._relation(descriptor_key, key, "unresolved_binding"))
                continue
            for provider in providers:
                bindings.append(self._binding(capability, provider.key, "implemented_by"))
                relations.append(self._relation(descriptor_key, provider.key, "implements"))
            provider_symbols = {item.symbol for item in providers}
            gateways = [
                unit for unit in units if unit.owner == capability.owner_domain and unit.node_type == "gateway"
                and any(self._called_constructor(call.func) in provider_symbols for call in ast.walk(unit.tree) if isinstance(call, ast.Call))
            ]
            for gateway in gateways:
                bindings.append(self._binding(capability, gateway.key, "exposed_by"))
                relations.append(self._relation(descriptor_key, gateway.key, "exposes"))

        for route in units:
            if route.node_type not in {"rest_route", "legacy_api"}:
                continue
            for capability in self._route_capabilities(
                route.tree,
                capabilities,
                source_trees.get((route.owner, route.source_path)),
                source_trees=source_trees,
                source_imports=source_imports,
                source_owner=route.owner,
                source_path=route.source_path,
            ):
                descriptor_key = descriptor_keys[(capability.capability_id, capability.major_version)]
                bindings.append(self._binding(capability, route.key, "exposed_by"))
                relations.append(self._relation(descriptor_key, route.key, "exposes"))
        return bindings, relations

    @staticmethod
    def _route_capabilities(
        tree: ast.AST,
        capabilities: Iterable[ScannedCapability],
        module_tree: ast.Module | None = None,
        *,
        source_trees: Mapping[tuple[str, str], ast.Module] | None = None,
        source_imports: Mapping[tuple[str, str], Mapping[str, tuple[str, str, str]]] | None = None,
        source_owner: str = "",
        source_path: str = "",
    ) -> tuple[ScannedCapability, ...]:
        """Resolve only explicit capability literals inside a decorated route."""
        by_id: dict[str, list[ScannedCapability]] = defaultdict(list)
        by_version: dict[str, ScannedCapability] = {}
        for capability in capabilities:
            by_id[capability.capability_id].append(capability)
            by_version[f"{capability.capability_id}@{capability.major_version}"] = capability
        literals = {
            node.value.strip()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip()
        }
        resolved: dict[tuple[str, int], ScannedCapability] = {}
        for literal in literals:
            capability = by_version.get(literal)
            if capability is not None:
                resolved[(capability.capability_id, capability.major_version)] = capability
                continue
            matches = by_id.get(literal, ())
            if len(matches) == 1:
                capability = matches[0]
                resolved[(capability.capability_id, capability.major_version)] = capability

        if module_tree is not None and isinstance(tree, (ast.FunctionDef, ast.AsyncFunctionDef)):
            trees = source_trees or {(source_owner, source_path): module_tree}
            imports_by_source = source_imports or {}
            visiting: set[tuple[str, str, str, tuple[tuple[str, object], ...]]] = set()

            def function_aliases(owner: str, path: str) -> dict[str, ast.AST]:
                tree_for_source = trees.get((owner, path))
                if tree_for_source is None:
                    return {}
                functions = {
                    item.name: item for item in tree_for_source.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                aliases: dict[str, ast.AST] = {}
                for assignment in tree_for_source.body:
                    if not isinstance(assignment, ast.Assign) or not isinstance(assignment.value, ast.Call):
                        continue
                    if not isinstance(assignment.value.func, ast.Name):
                        continue
                    factory = functions.get(assignment.value.func.id)
                    if factory is None:
                        continue
                    returns = [
                        item.value for item in factory.body
                        if isinstance(item, ast.Return) and isinstance(item.value, (ast.Tuple, ast.List))
                    ]
                    if not returns:
                        continue
                    returned_names = [item.id for item in returns[-1].elts if isinstance(item, ast.Name)]
                    nested = {
                        item.name: item for item in ast.walk(factory)
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    }
                    targets = assignment.targets[0] if assignment.targets else None
                    target_names = [item.id for item in targets.elts] if isinstance(targets, (ast.Tuple, ast.List)) else []
                    for alias, returned in zip(target_names, returned_names):
                        if returned in nested:
                            aliases[alias] = nested[returned]
                return aliases

            def function_for(owner: str, path: str, name: str) -> tuple[str, str, ast.AST] | None:
                tree_for_source = trees.get((owner, path))
                if tree_for_source is None:
                    return None
                for item in tree_for_source.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
                        return owner, path, item
                alias = function_aliases(owner, path).get(name)
                if alias is not None:
                    return owner, path, alias
                imported = imports_by_source.get((owner, path), {}).get(name)
                if imported is None:
                    return None
                target_owner, target_path, target_name = imported
                target_tree = trees.get((target_owner, target_path))
                if target_tree is None:
                    return None
                for item in target_tree.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == target_name:
                        return target_owner, target_path, item
                return None

            def evaluate(value: ast.AST, environment: Mapping[str, object]) -> object | None:
                if isinstance(value, ast.Constant) and isinstance(value.value, (bool, str)):
                    return value.value
                if isinstance(value, ast.Name):
                    return environment.get(value.id)
                if isinstance(value, ast.IfExp):
                    condition = evaluate(value.test, environment)
                    if isinstance(condition, bool):
                        return evaluate(value.body if condition else value.orelse, environment)
                if isinstance(value, ast.Compare) and len(value.ops) == 1 and len(value.comparators) == 1:
                    left = evaluate(value.left, environment)
                    right = evaluate(value.comparators[0], environment)
                    if isinstance(left, (bool, str)) and isinstance(right, (bool, str)):
                        if isinstance(value.ops[0], ast.Eq):
                            return left == right
                        if isinstance(value.ops[0], ast.NotEq):
                            return left != right
                return None

            def call_environment(
                function: ast.AST,
                call: ast.Call,
                parent_environment: Mapping[str, object],
            ) -> dict[str, object]:
                if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return {}
                parameters = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
                environment: dict[str, object] = {}
                for parameter, argument in zip(parameters, call.args):
                    value = evaluate(argument, parent_environment)
                    if value is not None:
                        environment[parameter.arg] = value
                for keyword in call.keywords:
                    if keyword.arg is not None:
                        value = evaluate(keyword.value, parent_environment)
                        if value is not None:
                            environment[keyword.arg] = value
                defaults = [*function.args.defaults]
                for parameter, default in zip(parameters[-len(defaults):] if defaults else (), defaults):
                    environment.setdefault(parameter.arg, evaluate(default, parent_environment))
                for parameter, default in zip(function.args.kwonlyargs, function.args.kw_defaults):
                    if default is not None:
                        environment.setdefault(parameter.arg, evaluate(default, parent_environment))
                return environment

            def visit(function: ast.AST, environment: Mapping[str, object], owner: str, path: str) -> None:
                key = (owner, path, getattr(function, "name", ""), tuple(sorted(environment.items(), key=lambda item: item[0])))
                if key in visiting:
                    return
                visiting.add(key)
                local_environment = dict(environment)
                for statement in getattr(function, "body", ()):
                    assignment = statement.value if isinstance(statement, ast.Expr) else statement
                    if isinstance(assignment, (ast.Assign, ast.AnnAssign)):
                        value = evaluate(assignment.value, local_environment)
                        targets = assignment.targets if isinstance(assignment, ast.Assign) else (assignment.target,)
                        if value is not None:
                            for target in targets:
                                if isinstance(target, ast.Name):
                                    local_environment[target.id] = value
                for call in ast.walk(function):
                    if not isinstance(call, ast.Call):
                        continue
                    for keyword in call.keywords:
                        if keyword.arg != "capability_id":
                            continue
                        literal = evaluate(keyword.value, local_environment)
                        capability = by_version.get(str(literal)) if isinstance(literal, str) else None
                        if capability is None and isinstance(literal, str):
                            matches = by_id.get(literal, ())
                            capability = matches[0] if len(matches) == 1 else None
                        if capability is not None:
                            resolved[(capability.capability_id, capability.major_version)] = capability
                    if isinstance(call.func, ast.Name):
                        target = function_for(owner, path, call.func.id)
                        if target is not None:
                            target_owner, target_path, target_function = target
                            visit(
                                target_function,
                                call_environment(target_function, call, local_environment),
                                target_owner,
                                target_path,
                            )
                visiting.remove(key)

            visit(tree, {}, source_owner, source_path)
        return tuple(resolved[key] for key in sorted(resolved))

    def _bind_acceptance_tests(
        self,
        capabilities: list[ScannedCapability],
        nodes: dict[str, ImplementationNode],
    ) -> tuple[list[CapabilityBinding], list[ImplementationRelation]]:
        """Bind only executable test node ids explicitly declared by the acceptance manifest."""
        if self._acceptance_manifest is None:
            return [], []
        manifest = _json_document(self._acceptance_manifest)
        declared = manifest.get("capabilities")
        if not isinstance(declared, Mapping):
            raise ScanPolicyError("acceptance_manifest_invalid")
        by_key = {
            f"{item.capability_id}@{item.major_version}": item
            for item in capabilities
        }
        bindings: list[CapabilityBinding] = []
        relations: list[ImplementationRelation] = []
        for raw_key, raw_cases in sorted(declared.items(), key=lambda item: str(item[0])):
            if not isinstance(raw_key, str) or raw_key not in by_key:
                raise ScanPolicyError("acceptance_manifest_capability_invalid")
            capability = by_key[raw_key]
            if capability.lifecycle_status != "stable" or not isinstance(raw_cases, Mapping):
                raise ScanPolicyError("acceptance_manifest_capability_invalid")
            descriptor_key = node_key(
                "descriptor", capability.owner_domain,
                f"catalog/{capability.capability_id}@{capability.major_version}",
            )
            for case_name, raw_node_id in sorted(raw_cases.items(), key=lambda item: str(item[0])):
                if not isinstance(case_name, str) or not isinstance(raw_node_id, str):
                    raise ScanPolicyError("acceptance_manifest_case_invalid")
                source_path, separator, source_symbol = raw_node_id.partition("::")
                if (
                    not separator
                    or not source_symbol.startswith("test_")
                    or not source_path.endswith(".py")
                    or Path(source_path).is_absolute()
                    or ".." in PurePosixPath(source_path).parts
                ):
                    raise ScanPolicyError("acceptance_manifest_case_invalid")
                source = (self.settings.repository_root / Path(PurePosixPath(source_path))).resolve()
                try:
                    source.relative_to(self.settings.repository_root.resolve())
                except ValueError as exc:
                    raise ScanPolicyError("acceptance_manifest_case_invalid") from exc
                if not self._is_safe_repository_file(source):
                    raise ScanPolicyError("acceptance_manifest_case_invalid")
                relative_source = source.relative_to(self.settings.repository_root).as_posix()
                key = node_key("test_case", capability.owner_domain, relative_source, raw_node_id)
                nodes[key] = ImplementationNode(
                    key,
                    capability.owner_domain,
                    "test_case",
                    relative_source,
                    _source_hash(source.read_text(encoding="utf-8")),
                    raw_node_id,
                    metadata={
                        "case_type": case_name,
                        "test_node_id": raw_node_id,
                        "acceptance_manifest": self._acceptance_manifest_path,
                    },
                )
                bindings.append(self._binding(capability, key, "tested_by"))
                relations.append(self._relation(descriptor_key, key, "tested_by"))
        return bindings, relations

    def _registry_modules(self) -> dict[tuple[str, int], str]:
        result: dict[tuple[str, int], str] = {}
        for item in self._registry_snapshot:
            spec = getattr(item, "spec", None)
            handler = getattr(item, "handler", None)
            capability_id = getattr(spec, "id", None)
            version = getattr(spec, "version", None)
            module = getattr(handler, "__module__", None)
            if isinstance(capability_id, str) and isinstance(version, int) and isinstance(module, str):
                result[(capability_id, version)] = module
        return result

    @staticmethod
    def registry_module_matches_source(registry_module: str, source_path: str) -> bool:
        """Match an imported handler module to its bounded provider source.

        Domain registrations often import a descriptor submodule such as
        ``craft_backend.capabilities.rule_descriptors`` while the serving
        provider is the sibling ``capabilities/provider.py`` module.  Compare
        normalized module suffixes and that explicit package-provider alias;
        never infer a match from an unrelated application/outcome module.
        """
        if not isinstance(registry_module, str) or not registry_module.strip():
            return False
        if not isinstance(source_path, str) or not source_path.endswith(".py"):
            return False
        source_module = source_path[:-3].replace("/", ".").replace("\\", ".")
        module = registry_module.strip().strip(".")
        candidates = {module}
        parts = module.split(".")
        if len(parts) >= 2 and parts[-2] in {"capabilities", "capability"}:
            candidates.add(".".join(parts[:-1]))
        if any(
            source_module == candidate
            or source_module.endswith(f".{candidate}")
            or source_module.endswith(f".{candidate}.provider")
            for candidate in candidates
        ):
            return True
        # Some domains keep their provider at ``<domain>_backend/provider.py``
        # while registrations live in a capability submodule.  Fall back only
        # to that same domain package's provider module; application/outcome
        # modules remain deliberately excluded.
        if source_module == "backend.base.provider" and (
            module.startswith("backend.capabilities.")
            or module.startswith("backend.plugin_platform.")
        ):
            return True
        package = ".".join(parts[:2]) if parts[:1] == ["backend"] and len(parts) >= 2 else parts[0]
        return source_module == f"{package}.provider" or source_module.endswith(f".{package}.provider")

    @staticmethod
    def _relation(from_key: str, to_key: str, relation_type: str) -> ImplementationRelation:
        return ImplementationRelation(from_key, to_key, relation_type, _digest({"from": from_key, "to": to_key, "type": relation_type}))

    @staticmethod
    def _binding(capability: ScannedCapability, key: str, binding_type: str) -> CapabilityBinding:
        return CapabilityBinding(
            capability.capability_id, capability.major_version, key, binding_type,
            _digest({"capability": capability.capability_id, "major": capability.major_version, "node": key, "type": binding_type}),
        )

    @staticmethod
    def _unique_relations(relations: Iterable[ImplementationRelation]) -> tuple[ImplementationRelation, ...]:
        values = {(item.from_canonical_key, item.relation_type, item.to_canonical_key): item for item in relations}
        return tuple(values[key] for key in sorted(values))

    @staticmethod
    def _unique_bindings(bindings: Iterable[CapabilityBinding]) -> tuple[CapabilityBinding, ...]:
        values = {(item.capability_id, item.major_version, item.node_canonical_key, item.binding_type): item for item in bindings}
        return tuple(values[key] for key in sorted(values))


__all__ = ["GovernanceScanner", "ScanPolicyError"]
