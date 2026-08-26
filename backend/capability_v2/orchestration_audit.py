"""Audits orchestration entry registries against the frozen Capability Catalog."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .catalog_targets import CatalogTargetIndex, TargetResolution


class OrchestrationAuditConfigurationError(ValueError):
    """Raised when an orchestration registry is malformed."""


@dataclass(frozen=True)
class OrchestrationTargetFailure:
    entry_key: str
    resolution: TargetResolution

    @property
    def reason_code(self) -> str:
        assert self.resolution.reason_code is not None
        return self.resolution.reason_code


@dataclass(frozen=True)
class OrchestrationAudit:
    registry_kind: str
    entry_count: int
    invalid_entries: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    duplicate_keys: tuple[str, ...]
    target_failures: tuple[OrchestrationTargetFailure, ...] = ()

    @property
    def passed(self) -> bool:
        return not (self.invalid_entries or self.missing_capabilities or self.duplicate_keys or self.target_failures)

    def serialized(self) -> dict[str, Any]:
        return {
            "registry_kind": self.registry_kind,
            "entry_count": self.entry_count,
            "invalid_entries": list(self.invalid_entries),
            "missing_capabilities": list(self.missing_capabilities),
            "duplicate_keys": list(self.duplicate_keys),
            "target_failures": [
                {"entry_key": item.entry_key, "reason_code": item.reason_code,
                 "capability_id": item.resolution.capability_id,
                 "major_version": item.resolution.major_version}
                for item in self.target_failures
            ],
            "passed": self.passed,
        }


def _load(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise OrchestrationAuditConfigurationError(f"missing orchestration registry: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OrchestrationAuditConfigurationError(f"invalid orchestration registry: {path}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("entries"), list):
        raise OrchestrationAuditConfigurationError("orchestration registry entries must be an array")
    return document


def audit_orchestration_registry(
    path: Path,
    catalog_index: CatalogTargetIndex | Mapping[str, Any],
) -> OrchestrationAudit:
    document = _load(path)
    kind = document.get("registry_kind")
    if kind not in {"task_tool", "bff_capability", "business_capability"}:
        raise OrchestrationAuditConfigurationError("unknown orchestration registry kind")
    entries = document["entries"]
    if not isinstance(catalog_index, CatalogTargetIndex):
        catalog_index = CatalogTargetIndex.from_catalog(catalog_index)
    invalid: list[str] = []
    missing: list[str] = []
    duplicates: list[str] = []
    target_failures: list[OrchestrationTargetFailure] = []
    seen: set[str] = set()
    key_field = {"task_tool": "task_id", "bff_capability": "route_id", "business_capability": "business_id"}[kind]
    for index, entry in enumerate(entries):
        label = f"entry[{index}]"
        if not isinstance(entry, dict):
            invalid.append(label)
            continue
        key = entry.get(key_field)
        capability_id = entry.get("capability_id")
        owner_domain = entry.get("owner_domain")
        if not isinstance(key, str) or not key or not isinstance(capability_id, str) or not capability_id or not isinstance(owner_domain, str) or not owner_domain:
            invalid.append(label)
            continue
        if key in seen:
            duplicates.append(key)
        seen.add(key)
        major_version = entry.get("major_version", 1)
        if not isinstance(major_version, int) or major_version < 1:
            invalid.append(label)
            continue
        resolution = catalog_index.resolve_stable(capability_id, major_version, owner_domain)
        if resolution.reason_code == "target_missing":
            missing.append(f"{key}:{capability_id}")
        if not resolution.ok:
            target_failures.append(OrchestrationTargetFailure(key, resolution))
    return OrchestrationAudit(
        kind, len(entries), tuple(sorted(invalid)), tuple(sorted(missing)), tuple(sorted(duplicates)),
        tuple(sorted(target_failures, key=lambda item: (item.entry_key, item.reason_code))),
    )


__all__ = ["OrchestrationAudit", "OrchestrationAuditConfigurationError", "OrchestrationTargetFailure", "audit_orchestration_registry"]
