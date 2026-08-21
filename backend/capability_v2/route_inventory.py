"""Checked-in route inventories for legacy and BFF migration governance."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping


class RouteInventoryConfigurationError(ValueError):
    """Raised when a route inventory is incomplete or unsafe."""


@dataclass(frozen=True)
class RouteInventoryEntry:
    route_path: str
    method: str
    owner: str
    migration_target_capability: str
    migration_deadline: date
    source: str
    allowed_consumers: tuple[str, ...] = ()
    exception_approval_reference: str | None = None

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
        entries.append(RouteInventoryEntry(
            route_path=route_path, method=method, owner=raw["owner"],
            migration_target_capability=raw["migration_target_capability"],
            migration_deadline=deadline, source=raw["source"],
            allowed_consumers=tuple(consumers), exception_approval_reference=approval,
        ))
    return RouteInventory(str(kind), tuple(entries))


def audit_route_inventory(inventory: RouteInventory, *, today: date | None = None) -> tuple[str, ...]:
    """Return blocking issues; deadlines are intentionally checked centrally."""

    now = today or date.today()
    issues: list[str] = []
    for entry in inventory.entries:
        if entry.migration_deadline < now and not entry.exception_approval_reference:
            issues.append(f"expired:{entry.method}:{entry.route_path}")
    return tuple(sorted(issues))


__all__ = [
    "RouteInventory",
    "RouteInventoryConfigurationError",
    "RouteInventoryEntry",
    "audit_route_inventory",
    "load_route_inventory",
]
