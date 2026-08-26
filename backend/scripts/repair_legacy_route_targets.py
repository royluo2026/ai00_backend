#!/usr/bin/env python3
"""Repair deprecated Legacy Route Inventory targets from reviewed route mappings."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.atomicity import load_atomicity_dispositions
from backend.capability_v2.catalog_targets import CatalogTargetIndex


MAPPING_PATH = ROOT / "docs/governance/legacy-route-target-mappings.json"
INVENTORY_PATH = ROOT / "docs/governance/legacy_route_inventory.json"
CATALOG_PATH = ROOT / "docs/capabilities/catalog.v2.json"
ATOMICITY_PATH = ROOT / "docs/governance/capability-atomicity-dispositions.json"
EXPECTED_FAMILIES = MappingProxyType({
    "craft-manufacturing-resource-change": (
        "craft.manufacturing_resource.change.apply", 1, 37
    ),
    "craft-manufacturing-resource-read": (
        "craft.manufacturing_resource.read", 1, 11
    ),
    "craft-gbop-change": ("craft.gbop.change.apply", 1, 24),
    "craft-gbop-read": ("craft.gbop.read", 1, 8),
    "project-craft-scope-read": ("project.craft_scope.read", 1, 1),
})
EXPECTED_COUNTS = MappingProxyType({
    source_id: count
    for source_id, _source_major_version, count in EXPECTED_FAMILIES.values()
})
_PARAMETER = re.compile(r"\{[^/{}]+\}")


@dataclass(frozen=True)
class RepairFailure:
    reason_code: str
    family_id: str
    source_capability_id: str
    source_major_version: int
    method: str
    route_pattern: str
    target_capability_id: str | None = None
    target_major_version: int | None = None

    def serialized(self) -> dict[str, str | int]:
        result: dict[str, str | int] = {
            "reason_code": self.reason_code,
            "family_id": self.family_id,
            "source_capability_id": self.source_capability_id,
            "source_major_version": self.source_major_version,
            "method": self.method,
            "route_pattern": self.route_pattern,
        }
        if self.target_capability_id is not None:
            result["target_capability_id"] = self.target_capability_id
        if self.target_major_version is not None:
            result["target_major_version"] = self.target_major_version
        return result

    def __str__(self) -> str:
        return json.dumps(self.serialized(), ensure_ascii=False, separators=(",", ":"))


class MappingConfigurationError(ValueError):
    """Raised when reviewed route mappings are incomplete or unsafe."""

    def __init__(self, message: str, *, failure: RepairFailure | None = None) -> None:
        self.failure = failure
        super().__init__(f"{message}: {failure}" if failure is not None else message)


@dataclass(frozen=True)
class RouteTarget:
    route_method: str
    route_pattern: str
    target_capability_id: str
    target_major_version: int
    owner: str
    review_reference: str

    @property
    def key(self) -> tuple[str, str]:
        return self.route_method, self.route_pattern


@dataclass(frozen=True)
class RouteTargetFamily:
    family_id: str
    source_capability_id: str
    source_major_version: int
    routes: tuple[RouteTarget, ...]


@dataclass(frozen=True)
class RepairResult:
    updated: int
    unchanged: int
    unmatched: tuple[RepairFailure, ...]
    counts_by_source: Mapping[str, int]


def normalize_route_pattern(path: str) -> str:
    return _PARAMETER.sub("{}", path.rstrip("/") or "/")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MappingConfigurationError(f"invalid {label}: {path}") from exc
    if not isinstance(document, dict):
        raise MappingConfigurationError(f"{label} must be an object")
    return document


def _required_string(raw: Mapping[str, Any], name: str, context: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value:
        raise MappingConfigurationError(f"{context} requires {name}")
    return value


def _required_version(raw: Mapping[str, Any], name: str, context: str) -> int:
    value = raw.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise MappingConfigurationError(f"{context} has invalid {name}")
    return value


def load_mapping_families(path: Path) -> tuple[RouteTargetFamily, ...]:
    document = _load_json(path, "legacy route target mappings")
    raw_families = document.get("mapping_families")
    if not isinstance(raw_families, list):
        raise MappingConfigurationError("mapping_families must be an array")
    families: list[RouteTargetFamily] = []
    family_ids: set[str] = set()
    source_ids: set[tuple[str, int]] = set()
    route_keys: set[tuple[str, str]] = set()
    for raw_family in raw_families:
        if not isinstance(raw_family, dict):
            raise MappingConfigurationError("mapping family must be an object")
        family_id = _required_string(raw_family, "family_id", "mapping family")
        source_id = _required_string(raw_family, "source_capability_id", family_id)
        source_version = _required_version(raw_family, "source_major_version", family_id)
        if family_id in family_ids:
            raise MappingConfigurationError(f"duplicate family_id: {family_id}")
        source_key = source_id, source_version
        if source_key in source_ids:
            raise MappingConfigurationError(
                f"duplicate source capability: {source_id}@{source_version}"
            )
        family_ids.add(family_id)
        source_ids.add(source_key)
        raw_routes = raw_family.get("routes")
        if not isinstance(raw_routes, list) or not raw_routes:
            raise MappingConfigurationError(f"{family_id} routes must be a non-empty array")
        routes: list[RouteTarget] = []
        for raw_route in raw_routes:
            if not isinstance(raw_route, dict):
                raise MappingConfigurationError(f"{family_id} route must be an object")
            method = _required_string(raw_route, "route_method", family_id).upper()
            raw_pattern = _required_string(raw_route, "route_pattern", family_id)
            pattern = normalize_route_pattern(raw_pattern)
            if not pattern.startswith("/api/"):
                raise MappingConfigurationError(f"invalid route pattern: {raw_pattern}")
            key = method, pattern
            if key in route_keys:
                raise MappingConfigurationError(f"duplicate route mapping: {method} {pattern}")
            route_keys.add(key)
            routes.append(RouteTarget(
                route_method=method,
                route_pattern=pattern,
                target_capability_id=_required_string(raw_route, "target_capability_id", f"{method} {pattern}"),
                target_major_version=_required_version(raw_route, "target_major_version", f"{method} {pattern}"),
                owner=_required_string(raw_route, "owner", f"{method} {pattern}"),
                review_reference=_required_string(raw_route, "review_reference", f"{method} {pattern}"),
            ))
        families.append(RouteTargetFamily(family_id, source_id, source_version, tuple(routes)))
    actual_families = {
        family.family_id: (
            family.source_capability_id,
            family.source_major_version,
            len(family.routes),
        )
        for family in families
    }
    if actual_families != dict(EXPECTED_FAMILIES):
        raise MappingConfigurationError(
            "unexpected_mapping_family: "
            f"expected {dict(EXPECTED_FAMILIES)}, got {actual_families}"
        )
    return tuple(families)


def repair_inventory(
    inventory: dict[str, Any],
    families: Sequence[RouteTargetFamily],
    catalog_index: CatalogTargetIndex,
) -> RepairResult:
    entries = inventory.get("entries")
    if not isinstance(entries, list):
        raise MappingConfigurationError("legacy route inventory entries must be an array")
    rules: dict[tuple[str, str], tuple[RouteTargetFamily, RouteTarget]] = {}
    source_families = {
        (family.source_capability_id, family.source_major_version): family
        for family in families
    }
    source_families_by_id = {
        family.source_capability_id: family for family in families
    }
    for family in families:
        for route in family.routes:
            resolution = catalog_index.resolve_stable(
                route.target_capability_id, route.target_major_version, route.owner
            )
            if not resolution.ok:
                failure = RepairFailure(
                    reason_code=resolution.reason_code or "target_invalid",
                    family_id=family.family_id,
                    source_capability_id=family.source_capability_id,
                    source_major_version=family.source_major_version,
                    method=route.route_method,
                    route_pattern=route.route_pattern,
                    target_capability_id=route.target_capability_id,
                    target_major_version=route.target_major_version,
                )
                raise MappingConfigurationError(
                    failure.reason_code,
                    failure=failure,
                )
            if route.key in rules:
                raise MappingConfigurationError(
                    f"duplicate route mapping: {route.route_method} {route.route_pattern}"
                )
            rules[route.key] = family, route

    updated = 0
    unchanged = 0
    counts = {source_id: 0 for source_id in EXPECTED_COUNTS}
    unmatched: list[RepairFailure] = []
    seen_inventory: set[tuple[str, str]] = set()
    matched_rules: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise MappingConfigurationError("legacy route inventory entry must be an object")
        method = entry.get("method")
        path = entry.get("route_path")
        if not isinstance(method, str) or not isinstance(path, str):
            raise MappingConfigurationError("legacy route inventory route key is invalid")
        key = method.upper(), normalize_route_pattern(path)
        if key in seen_inventory:
            raise MappingConfigurationError(f"duplicate inventory route: {key[0]} {key[1]}")
        seen_inventory.add(key)
        mapping = rules.get(key)
        if mapping is None:
            source_id = entry.get("migration_target_capability")
            source_version = entry.get("migration_target_major_version", 1)
            if isinstance(source_id, str) and source_id in source_families_by_id:
                expected_family = source_families_by_id[source_id]
                exact_family = source_families.get((source_id, source_version))
                unmatched.append(RepairFailure(
                    reason_code=(
                        "source_route_unmapped"
                        if exact_family is not None
                        else "source_major_version_mismatch"
                    ),
                    family_id=expected_family.family_id,
                    source_capability_id=source_id,
                    source_major_version=(
                        source_version if isinstance(source_version, int)
                        and not isinstance(source_version, bool)
                        else expected_family.source_major_version
                    ),
                    method=key[0],
                    route_pattern=key[1],
                ))
            continue
        family, route = mapping
        matched_rules.add(key)
        counts[family.source_capability_id] += 1
        desired = (
            route.target_capability_id,
            route.target_major_version,
            route.owner,
        )
        current = (
            entry.get("migration_target_capability"),
            entry.get("migration_target_major_version", 1),
            entry.get("owner"),
        )
        if current == desired:
            unchanged += 1
            continue
        entry["migration_target_capability"] = route.target_capability_id
        entry["migration_target_major_version"] = route.target_major_version
        entry["owner"] = route.owner
        updated += 1
    for method, pattern in sorted(set(rules) - matched_rules):
        family, _route = rules[(method, pattern)]
        unmatched.append(RepairFailure(
            reason_code="inventory_route_missing",
            family_id=family.family_id,
            source_capability_id=family.source_capability_id,
            source_major_version=family.source_major_version,
            method=method,
            route_pattern=pattern,
        ))
    return RepairResult(
        updated=updated,
        unchanged=unchanged,
        unmatched=tuple(sorted(
            unmatched,
            key=lambda failure: (
                failure.reason_code,
                failure.family_id,
                failure.method,
                failure.route_pattern,
            ),
        )),
        counts_by_source=MappingProxyType(counts),
    )


def _catalog_index() -> CatalogTargetIndex:
    dispositions = load_atomicity_dispositions(ATOMICITY_PATH)
    replacements = {
        (item.capability_id, item.major_version): item.replacement_capabilities[0]
        for item in dispositions.dispositions
        if item.replacement_capabilities
    }
    return CatalogTargetIndex.from_catalog(
        _load_json(CATALOG_PATH, "Capability Catalog"), replacements=replacements
    )


def _write_atomic(path: Path, document: Mapping[str, Any]) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary_name = handle.name
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _render_result(result: RepairResult, mode: str) -> str:
    counts = ",".join(
        f"{source}={result.counts_by_source.get(source, 0)}" for source in EXPECTED_COUNTS
    )
    return (
        f"mode={mode} updated={result.updated} unchanged={result.unchanged} "
        f"unmatched={len(result.unmatched)} total={sum(result.counts_by_source.values())} "
        f"counts=[{counts}]"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if the inventory still needs repair")
    mode.add_argument("--write", action="store_true", help="atomically rewrite the inventory")
    args = parser.parse_args(argv)
    selected_mode = "write" if args.write else "check"
    try:
        inventory = _load_json(INVENTORY_PATH, "Legacy Route Inventory")
        result = repair_inventory(
            inventory, load_mapping_families(MAPPING_PATH), _catalog_index()
        )
    except MappingConfigurationError as exc:
        if exc.failure is not None:
            print(f"legacy-route-target-repair failure={exc.failure}", file=sys.stderr)
        else:
            print(f"legacy-route-target-repair failed: {exc}", file=sys.stderr)
        return 1
    print(_render_result(result, selected_mode))
    for item in result.unmatched:
        print(f"failure={item}", file=sys.stderr)
    counts_ok = dict(result.counts_by_source) == dict(EXPECTED_COUNTS)
    if result.unmatched or not counts_ok:
        return 1
    if args.write:
        _write_atomic(INVENTORY_PATH, inventory)
        return 0
    return 1 if result.updated else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MappingConfigurationError",
    "RepairFailure",
    "RepairResult",
    "RouteTarget",
    "RouteTargetFamily",
    "load_mapping_families",
    "normalize_route_pattern",
    "repair_inventory",
]
