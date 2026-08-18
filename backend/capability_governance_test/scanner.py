"""Fail-closed, AST-only implementation scanner for test governance."""
from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .config import GovernanceSettings
from .fingerprint import canonical_fingerprint
from .graph import node_key
from .models import (
    CapabilityBinding,
    ImplementationNode,
    ImplementationRelation,
    ScannedCapability,
    SnapshotDocument,
)


class ScanPolicyError(RuntimeError):
    """Raised when a scan request would escape the trusted repository boundary."""


_TABLE = re.compile(r"\b(workmanship_[a-z][a-z0-9_]*)\b", re.IGNORECASE)
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


def _normalise_relative(path: Path) -> str:
    return PurePosixPath(path.as_posix()).as_posix()


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
    ) -> None:
        self.settings = settings
        self._registry_snapshot = tuple(registry_snapshot or ())
        self._product_catalog = product_catalog
        self._extension_catalog = extension_catalog
        self._domain_manifests = domain_manifests

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

    def scan(self, code_revision: str) -> SnapshotDocument:
        """Create an immutable document without importing or executing scanned source."""
        product = self._require_catalog(self._product_catalog, "product_catalog_required")
        extension = _json_document(self._extension_catalog) if self._extension_catalog is not None else None
        manifests = self._require_manifest(self._domain_manifests)
        domains = self._domains(manifests)
        units, tables, unresolved = self._parse_allowlisted_sources(domains)
        nodes, relations = self._build_nodes_and_relations(units, tables, unresolved)
        capabilities = self._scan_capabilities(product, domains)
        bindings, extra_relations = self._bind_capabilities(capabilities, nodes, units, domains)
        relations.extend(extra_relations)
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
        snapshot_hash = _digest({
            "product_release_id": str(product.get("release_id", "")),
            "extension_release_id": str(extension.get("release_id", "")) if extension else None,
            "code_revision": code_revision,
            "capabilities": [item.to_json() for item in ordered_capabilities],
            "nodes": [item.to_json() for item in ordered_nodes],
            "bindings": [item.__dict__ for item in ordered_bindings],
            "relations": [item.__dict__ for item in ordered_relations],
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
    ) -> tuple[list[_AstUnit], list[_TableReference], list[tuple[str, str, str]]]:
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
                    tables.extend(_TableReference(owner, relative, table.lower(), None, is_migration_path) for table in _TABLE.findall(source))
                    continue
                try:
                    tree = ast.parse(source, filename=relative)
                except SyntaxError:
                    unresolved.append((owner, relative, "syntax_error"))
                    continue
                source_hash = _source_hash(source)
                imported_symbols = tuple(sorted({
                    alias.asname or alias.name.rsplit(".", 1)[-1]
                    for item in tree.body if isinstance(item, (ast.Import, ast.ImportFrom))
                    for alias in item.names
                }))
                classes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
                for item in classes:
                    found_type = _node_type(item.name, relative)
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
        return units, tables, unresolved

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
            descriptor = _json_document(raw_descriptor)
            capability_id = str(descriptor.get("id", ""))
            major = int(descriptor.get("major_version", 0))
            owner = str(descriptor.get("owner_domain", ""))
            if not capability_id or major < 1 or owner not in domains:
                raise ScanPolicyError("product_catalog_descriptor_invalid")
            artifact = domains[owner].get("artifact")
            provider_hash = str(artifact.get("artifact_hash", "")) if isinstance(artifact, Mapping) else ""
            capabilities.append(ScannedCapability(
                capability_id=capability_id,
                major_version=major,
                owner_domain=owner,
                semantic_class=str(descriptor.get("side_effect_level", "")),
                business_effect=str(descriptor.get("description", descriptor.get("title", ""))),
                lifecycle_status=str(descriptor.get("lifecycle_status", "")),
                descriptor_hash=_digest(descriptor),
                input_schema_hash=_digest(descriptor.get("input_schema", {})),
                output_schema_hash=_digest(descriptor.get("output_schema", {})),
                error_schema_hash=_digest(descriptor.get("domain_errors", ())),
                policy_hash=_digest({key: descriptor.get(key) for key in ("authorization_policy", "confirmation_policy", "audit_policy", "idempotency_policy")}),
                provider_hash=provider_hash,
                descriptor=descriptor,
            ))
        return capabilities

    def _bind_capabilities(
        self,
        capabilities: list[ScannedCapability],
        nodes: dict[str, ImplementationNode],
        units: list[_AstUnit],
        domains: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[CapabilityBinding], list[ImplementationRelation]]:
        bindings: list[CapabilityBinding] = []
        relations: list[ImplementationRelation] = []
        registry_modules = self._registry_modules()
        for capability in capabilities:
            descriptor_path = f"catalog/{capability.capability_id}@{capability.major_version}"
            descriptor_key = node_key("descriptor", capability.owner_domain, descriptor_path)
            nodes[descriptor_key] = ImplementationNode(
                descriptor_key, capability.owner_domain, "descriptor", descriptor_path,
                capability.descriptor_hash, capability.capability_id,
            )
            bindings.append(self._binding(capability, descriptor_key, "declared_in"))
            module = registry_modules.get((capability.capability_id, capability.major_version))
            providers = [
                unit for unit in units if unit.owner == capability.owner_domain and unit.node_type == "provider"
                and module is not None and unit.source_path[:-3].replace("/", ".") == module
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
