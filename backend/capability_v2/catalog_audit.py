"""Machine-readable audit for Capability contract and exposure provenance debt."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class CatalogAuditConfigurationError(ValueError):
    """Raised when the catalog cannot be audited safely."""


@dataclass(frozen=True)
class CatalogAuditReport:
    stable_count: int
    generic_operation_count: int
    open_arguments_count: int
    # All-consumer exposure is only debt when it came from the adapter default;
    # provider-explicit grants are reviewable policy and remain visible in the
    # generated catalog.
    default_all_exposure_count: int
    generic_operation_ids: tuple[str, ...]

    def serialized(self) -> dict[str, object]:
        return {
            "stable_count": self.stable_count,
            "generic_operation_count": self.generic_operation_count,
            "open_arguments_count": self.open_arguments_count,
            "default_all_exposure_count": self.default_all_exposure_count,
            "generic_operation_ids": list(self.generic_operation_ids),
        }


def _load_catalog(path: Path) -> list[dict]:
    if not path.is_file():
        raise CatalogAuditConfigurationError(f"missing catalog: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogAuditConfigurationError(f"invalid catalog: {path}") from exc
    entries = document.get("capabilities") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise CatalogAuditConfigurationError("catalog capabilities must be an array of objects")
    return entries


def audit_catalog(path: Path) -> CatalogAuditReport:
    stable = [entry for entry in _load_catalog(path) if entry.get("lifecycle_status") == "stable"]
    generic_ids: list[str] = []
    open_arguments = 0
    default_all = 0
    for entry in stable:
        capability_id = entry.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            raise CatalogAuditConfigurationError("stable capability ID is invalid")
        schema = entry.get("input_schema")
        properties = schema.get("properties") if isinstance(schema, dict) else None
        if isinstance(properties, dict) and {"operation", "arguments"} <= set(properties):
            generic_ids.append(capability_id)
            arguments = properties["arguments"]
            if not isinstance(arguments, dict) or arguments.get("additionalProperties") is not False:
                open_arguments += 1
        exposure = entry.get("exposure")
        if (
            entry.get("exposure_policy_source") == "adapter_default"
            and isinstance(exposure, dict)
            and all(
            exposure.get(name) is True for name in ("web", "api", "plugin", "agent", "mcp")
            )
        ):
            default_all += 1
    return CatalogAuditReport(
        stable_count=len(stable),
        generic_operation_count=len(generic_ids),
        open_arguments_count=open_arguments,
        default_all_exposure_count=default_all,
        generic_operation_ids=tuple(sorted(generic_ids)),
    )


__all__ = ["CatalogAuditConfigurationError", "CatalogAuditReport", "audit_catalog"]
