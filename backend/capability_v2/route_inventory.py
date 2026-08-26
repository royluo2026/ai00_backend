"""Checked-in route inventories for legacy and BFF migration governance."""
from __future__ import annotations

import ast
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .catalog_targets import CatalogTargetIndex, TargetResolution


class RouteInventoryConfigurationError(ValueError):
    """Raised when a route inventory is incomplete or unsafe."""


class LegacyRouteProofConfigurationError(ValueError):
    """Raised when the governed Legacy proof artifact is malformed."""


@dataclass(frozen=True)
class RouteInventoryEntry:
    route_path: str
    method: str
    owner: str
    migration_target_capability: str
    migration_deadline: date
    source: str
    migration_target_major_version: int = 1
    allowed_consumers: tuple[str, ...] = ()
    exception_approval_reference: str | None = None
    evidence_provenance: str | None = None

    def serialized(self) -> dict[str, Any]:
        value = asdict(self)
        value["migration_deadline"] = self.migration_deadline.isoformat()
        value["allowed_consumers"] = list(self.allowed_consumers)
        return value


@dataclass(frozen=True)
class RouteInventory:
    inventory_kind: str
    entries: tuple[RouteInventoryEntry, ...]

    def serialized(self) -> dict[str, Any]:
        return {"inventory_kind": self.inventory_kind,
                "entries": [entry.serialized() for entry in self.entries]}


@dataclass(frozen=True)
class RouteInventoryTargetFailure:
    entry: RouteInventoryEntry
    resolution: TargetResolution

    @property
    def reason_code(self) -> str:
        assert self.resolution.reason_code is not None
        return self.resolution.reason_code

    def __str__(self) -> str:
        return f"{self.reason_code}:{self.entry.method}:{self.entry.route_path}"


def _load(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise RouteInventoryConfigurationError(f"missing route inventory: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RouteInventoryConfigurationError(f"invalid route inventory: {path}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("entries"), list):
        raise RouteInventoryConfigurationError("route inventory entries must be an array")
    return document


def load_route_inventory(path: Path) -> RouteInventory:
    document = _load(path)
    kind = document.get("inventory_kind")
    if kind not in {"legacy_rest", "bff"}:
        raise RouteInventoryConfigurationError("inventory_kind must be legacy_rest or bff")
    entries: list[RouteInventoryEntry] = []
    seen: set[tuple[str, str]] = set()
    for raw in document["entries"]:
        if not isinstance(raw, dict):
            raise RouteInventoryConfigurationError("route inventory entry must be an object")
        required = ("route_path", "method", "owner", "migration_target_capability",
                    "migration_deadline", "source")
        if any(not isinstance(raw.get(field), str) or not raw[field] for field in required):
            raise RouteInventoryConfigurationError("route inventory entry has missing required field")
        route_path = raw["route_path"]
        if not route_path.startswith("/api/"):
            raise RouteInventoryConfigurationError(f"route path is not an API route: {route_path}")
        try:
            deadline = date.fromisoformat(raw["migration_deadline"])
        except ValueError as exc:
            raise RouteInventoryConfigurationError(f"invalid migration deadline: {route_path}") from exc
        method = raw["method"].upper()
        key = (method, route_path)
        if key in seen:
            raise RouteInventoryConfigurationError(f"duplicate route inventory entry: {method} {route_path}")
        seen.add(key)
        consumers = raw.get("allowed_consumers", [])
        if not isinstance(consumers, list) or not all(isinstance(value, str) and value for value in consumers):
            raise RouteInventoryConfigurationError(f"invalid allowed_consumers: {route_path}")
        approval = raw.get("exception_approval_reference")
        if approval is not None and (not isinstance(approval, str) or not approval):
            raise RouteInventoryConfigurationError(f"invalid exception approval: {route_path}")
        provenance = raw.get("evidence_provenance")
        if provenance is not None and (
            not isinstance(provenance, str) or not provenance.strip()
        ):
            raise RouteInventoryConfigurationError(
                f"invalid evidence provenance: {route_path}"
            )
        major_version = raw.get("migration_target_major_version", 1)
        if not isinstance(major_version, int) or major_version < 1:
            raise RouteInventoryConfigurationError(f"invalid migration target version: {route_path}")
        entries.append(RouteInventoryEntry(
            route_path=route_path, method=method, owner=raw["owner"],
            migration_target_capability=raw["migration_target_capability"],
            migration_deadline=deadline, source=raw["source"],
            migration_target_major_version=major_version,
            allowed_consumers=tuple(consumers), exception_approval_reference=approval,
            evidence_provenance=provenance,
        ))
    return RouteInventory(str(kind), tuple(entries))


def audit_route_inventory(
    inventory: RouteInventory,
    *,
    today: date | None = None,
    catalog_index: CatalogTargetIndex | None = None,
) -> tuple[str | RouteInventoryTargetFailure, ...]:
    """Return blocking issues; deadlines are intentionally checked centrally."""

    now = today or date.today()
    issues: list[str | RouteInventoryTargetFailure] = []
    for entry in inventory.entries:
        if catalog_index is not None:
            resolution = catalog_index.resolve_stable(
                entry.migration_target_capability,
                entry.migration_target_major_version,
                entry.owner,
            )
            if not resolution.ok:
                issues.append(RouteInventoryTargetFailure(entry, resolution))
        if entry.migration_deadline < now and not entry.exception_approval_reference:
            issues.append(f"expired:{entry.method}:{entry.route_path}")
    return tuple(sorted(issues, key=str))


def _proof_anchor_text(root: Path, raw: object) -> str | None:
    if not isinstance(raw, dict) or set(raw) != {
        "source_path", "start_line", "end_line", "sha256"
    }:
        return None
    source_path = raw.get("source_path")
    start_line = raw.get("start_line")
    end_line = raw.get("end_line")
    expected_hash = raw.get("sha256")
    if (
        not isinstance(source_path, str)
        or not source_path
        or "\\" in source_path
        or PurePosixPath(source_path).is_absolute()
        or ".." in PurePosixPath(source_path).parts
        or not isinstance(start_line, int)
        or isinstance(start_line, bool)
        or not isinstance(end_line, int)
        or isinstance(end_line, bool)
        or start_line < 1
        or end_line < start_line
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
    ):
        return None
    path = root.joinpath(*PurePosixPath(source_path).parts)
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        return None
    if end_line > len(lines):
        return None
    text = "".join(lines[start_line - 1:end_line])
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected_hash:
        return None
    return text


def _exact_python_calls(source: str) -> set[str | None]:
    tree = ast.parse(source)
    return {
        ast.get_source_segment(source, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }


def _valid_retained_proof_evidence(
    root: Path,
    entry: Mapping[str, Any],
    replacements: Mapping[tuple[str, int], set[str]],
) -> bool:
    evidence = entry.get("evidence")
    target = entry.get("target_capability")
    major = entry.get("target_major_version")
    if (
        not isinstance(evidence, Mapping)
        or not isinstance(target, str)
        or not target
        or not isinstance(major, int)
        or isinstance(major, bool)
        or major < 1
    ):
        return False
    kind = evidence.get("kind")
    allowed = {
        "atomic_composition_invocation",
        "capability_invocation",
        "exact_delegation",
        "facade_operation_delegation",
        "facade_operation_delegation_chain",
        "facade_operation_invocation",
    }
    if kind not in allowed:
        return False
    handler = _proof_anchor_text(root, evidence.get("handler"))
    if handler is None:
        return False
    try:
        handler_calls = _exact_python_calls(handler)
        if kind == "capability_invocation":
            invocation = evidence.get("expected_target_invocation")
            return (
                isinstance(invocation, str)
                and target in invocation
                and invocation in handler_calls
            )
        if kind == "exact_delegation":
            symbol = evidence.get("delegation_symbol")
            delegation = evidence.get("expected_delegation")
            binding = _proof_anchor_text(root, evidence.get("binding"))
            target_binding = evidence.get("expected_target_binding")
            return (
                isinstance(symbol, str)
                and symbol
                and isinstance(delegation, str)
                and symbol in delegation
                and delegation in handler_calls
                and binding is not None
                and f"def {symbol}" in binding
                and isinstance(target_binding, str)
                and target in target_binding
                and target_binding in _exact_python_calls(binding)
            )

        facade = evidence.get("facade_capability")
        operation = evidence.get("operation")
        if (
            not isinstance(facade, str)
            or not facade
            or not isinstance(operation, str)
            or not operation
            or target != f"{facade}.atomic.{operation.replace('.', '_')}"
            or target not in replacements.get((facade, major), set())
        ):
            return False
        if kind == "facade_operation_invocation":
            invocation = evidence.get("expected_facade_invocation")
            return (
                isinstance(invocation, str)
                and facade in invocation
                and operation in invocation
                and invocation in handler_calls
            )
        if kind == "atomic_composition_invocation":
            invocation = evidence.get("expected_facade_invocation")
            symbol = evidence.get("composition_symbol")
            binding = _proof_anchor_text(root, evidence.get("binding"))
            construction = evidence.get("expected_target_construction")
            return (
                isinstance(invocation, str)
                and facade in invocation
                and operation in invocation
                and isinstance(symbol, str)
                and symbol in invocation
                and invocation in handler_calls
                and binding is not None
                and f"def {symbol}" in binding
                and isinstance(construction, str)
                and construction in binding
            )

        symbol = evidence.get("delegation_symbol")
        delegation = evidence.get("expected_delegation")
        if (
            not isinstance(symbol, str)
            or not symbol
            or not isinstance(delegation, str)
            or symbol not in delegation
            or operation not in delegation
            or delegation not in handler_calls
        ):
            return False
        if kind == "facade_operation_delegation_chain":
            bridge = _proof_anchor_text(root, evidence.get("bridge"))
            facade_symbol = evidence.get("facade_symbol")
            bridge_delegation = evidence.get("expected_bridge_delegation")
            binding = _proof_anchor_text(root, evidence.get("binding"))
            facade_binding = evidence.get("expected_facade_binding")
            return (
                bridge is not None
                and f"def {symbol}" in bridge
                and isinstance(facade_symbol, str)
                and isinstance(bridge_delegation, str)
                and facade_symbol in bridge_delegation
                and bridge_delegation in _exact_python_calls(bridge)
                and binding is not None
                and f"def {facade_symbol}" in binding
                and isinstance(facade_binding, str)
                and facade in facade_binding
                and facade_binding in _exact_python_calls(binding)
            )
        binding = _proof_anchor_text(root, evidence.get("binding"))
        facade_binding = evidence.get("expected_facade_binding")
        return (
            binding is not None
            and f"def {symbol}" in binding
            and isinstance(facade_binding, str)
            and facade in facade_binding
            and facade_binding in _exact_python_calls(binding)
        )
    except (SyntaxError, TypeError, ValueError):
        return False


def audit_legacy_route_proofs(
    root: Path,
    inventory: RouteInventory,
    proof_path: Path,
    *,
    catalog_index: CatalogTargetIndex,
    replacements: Mapping[tuple[str, int], set[str]],
) -> tuple[str, ...]:
    """Audit the exact bijection between Web-review inventory and active proofs."""

    try:
        document = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacyRouteProofConfigurationError(
            f"invalid Legacy route proof artifact: {proof_path}"
        ) from exc
    required_top = {
        "schema_version", "artifact_id", "review_authority", "baseline_revision",
        "original_additions", "entries", "original_retained_count",
        "original_removed_count", "retained_count", "removed_count",
        "round_4_re_retained_count", "round_4_new_count", "round_4_delta_count",
    }
    if not isinstance(document, dict) or set(document) != required_top:
        raise LegacyRouteProofConfigurationError("invalid Legacy route proof fields")
    artifact_id = document.get("artifact_id")
    entries = document.get("entries")
    if (
        document.get("schema_version") != 2
        or not isinstance(artifact_id, str)
        or not artifact_id
        or not isinstance(entries, list)
    ):
        raise LegacyRouteProofConfigurationError("invalid Legacy route proof schema")

    active: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    removed = 0
    original_retained = 0
    original_removed = 0
    round_4_re_retained = 0
    round_4_new = 0
    malformed = 0
    for raw in entries:
        if not isinstance(raw, Mapping):
            malformed += 1
            continue
        method = raw.get("method")
        route = raw.get("route_path")
        scope = raw.get("scope")
        disposition = raw.get("disposition")
        reason = raw.get("reason")
        if (
            not isinstance(method, str)
            or method != method.upper()
            or not isinstance(route, str)
            or not route.startswith("/api/")
            or not isinstance(scope, str)
            or not scope
            or disposition not in {"retained", "removed"}
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            malformed += 1
            continue
        if disposition == "removed":
            removed += 1
            if scope == "original_109":
                original_removed += 1
            continue
        key = method, route
        active.setdefault(key, []).append(raw)
        if scope == "original_109":
            original_retained += 1
        marker = raw.get("round_4_change")
        if marker == "re_retained":
            round_4_re_retained += 1
        elif marker == "new":
            round_4_new += 1
        elif marker is not None:
            malformed += 1

    metadata_valid = (
        isinstance(document.get("original_additions"), int)
        and document["original_additions"] == original_retained + original_removed
        and document.get("original_retained_count") == original_retained
        and document.get("original_removed_count") == original_removed
        and document.get("retained_count") == sum(len(value) for value in active.values())
        and document.get("removed_count") == removed
        and document.get("round_4_re_retained_count") == round_4_re_retained
        and document.get("round_4_new_count") == round_4_new
        and document.get("round_4_delta_count") == round_4_re_retained + round_4_new
    )
    issues: list[str] = []
    if malformed:
        issues.append(f"legacy_route_proof_malformed:{malformed}")
    if not metadata_valid:
        issues.append("legacy_route_proof_metadata_invalid:1")

    duplicates = sum(len(values) - 1 for values in active.values() if len(values) > 1)
    if duplicates:
        issues.append(f"legacy_route_proof_duplicate:{duplicates}")
    active_once = {key: values[0] for key, values in active.items() if len(values) == 1}
    provenance_prefix = f"{artifact_id}/"
    marked = {
        (entry.method, entry.route_path): entry
        for entry in inventory.entries
        if isinstance(entry.evidence_provenance, str)
        and entry.evidence_provenance.startswith(provenance_prefix)
    }
    missing = set(marked) - set(active_once)
    orphaned = set(active_once) - set(marked)
    if missing:
        issues.append(f"legacy_route_proof_missing:{len(missing)}")
    if orphaned:
        issues.append(f"legacy_route_proof_orphaned:{len(orphaned)}")

    anchor_invalid = 0
    target_mismatch = 0
    lifecycle_failures: Counter[str] = Counter()
    for key in sorted(set(marked) & set(active_once)):
        inventory_entry = marked[key]
        proof = active_once[key]
        expected_provenance = f"{artifact_id}/{proof['scope']}"
        if (
            inventory_entry.evidence_provenance != expected_provenance
            or proof.get("target_capability")
            != inventory_entry.migration_target_capability
            or proof.get("target_major_version")
            != inventory_entry.migration_target_major_version
        ):
            target_mismatch += 1
            continue
        resolution = catalog_index.resolve_stable(
            inventory_entry.migration_target_capability,
            inventory_entry.migration_target_major_version,
            inventory_entry.owner,
        )
        if not resolution.ok:
            assert resolution.reason_code is not None
            lifecycle_failures[resolution.reason_code] += 1
        if not _valid_retained_proof_evidence(root, proof, replacements):
            anchor_invalid += 1
    if target_mismatch:
        issues.append(f"legacy_route_proof_target_mismatch:{target_mismatch}")
    for reason, count in sorted(lifecycle_failures.items()):
        issues.append(f"legacy_route_proof_{reason}:{count}")
    if anchor_invalid:
        issues.append(f"legacy_route_proof_anchor_invalid:{anchor_invalid}")
    return tuple(sorted(issues))


__all__ = [
    "LegacyRouteProofConfigurationError",
    "RouteInventory",
    "RouteInventoryConfigurationError",
    "RouteInventoryEntry",
    "RouteInventoryTargetFailure",
    "audit_route_inventory",
    "audit_legacy_route_proofs",
    "load_route_inventory",
]
