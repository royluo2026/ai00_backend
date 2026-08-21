"""Machine-readable audit for Capability contract and exposure provenance debt."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
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
    required_field_missing_counts: dict[str, int] = field(default_factory=dict)
    invalid_error_schema_count: int = 0
    test_evidence_not_run_count: int = 0
    invalid_test_ref_count: int = 0

    @property
    def missing_fields(self) -> dict[str, int]:
        return dict(self.required_field_missing_counts)

    def serialized(self) -> dict[str, object]:
        return {
            "stable_count": self.stable_count,
            "generic_operation_count": self.generic_operation_count,
            "open_arguments_count": self.open_arguments_count,
            "default_all_exposure_count": self.default_all_exposure_count,
            "generic_operation_ids": list(self.generic_operation_ids),
            "required_field_missing_counts": self.missing_fields,
            "invalid_error_schema_count": self.invalid_error_schema_count,
            "test_evidence_not_run_count": self.test_evidence_not_run_count,
            "invalid_test_ref_count": self.invalid_test_ref_count,
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
    missing_fields: dict[str, int] = {
        field: 0 for field in (
            "capability_version_gid", "error_schema", "transaction_policy",
            "consumer_refs", "provider_ref", "api_refs", "test_refs",
            "business_effect", "side_effects",
        )
    }
    invalid_error_schema = 0
    test_evidence_not_run = 0
    invalid_test_refs = 0
    for entry in stable:
        capability_id = entry.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            raise CatalogAuditConfigurationError("stable capability ID is invalid")
        schema = entry.get("input_schema")
        properties = schema.get("properties") if isinstance(schema, dict) else None
        is_operation_envelope = (
            isinstance(properties, dict)
            and "operation" in properties
            and ("arguments" in properties or capability_id == "craft.ebom.change.apply")
        )
        if is_operation_envelope:
            generic_ids.append(capability_id)
            arguments = properties.get("arguments")
            if arguments is not None and (not isinstance(arguments, dict) or arguments.get("additionalProperties") is not False):
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
        for field in missing_fields:
            value = entry.get(field)
            if value is None or value == "" or value == [] or value == {}:
                missing_fields[field] += 1
        error_schema = entry.get("error_schema")
        if error_schema not in (None, []):
            if not isinstance(error_schema, list) or any(
                not isinstance(item, dict)
                or not {"error_code", "message_template", "is_retryable", "is_caller_error"} <= set(item)
                for item in error_schema
            ):
                invalid_error_schema += 1
        test_refs = entry.get("test_refs")
        if isinstance(test_refs, list) and any(
            isinstance(item, dict) and item.get("result") in {"not_run", "skipped"}
            for item in test_refs
        ):
            test_evidence_not_run += 1
        if not isinstance(test_refs, list) or any(
            not isinstance(item, dict)
            or not {"test_type", "test_node_id", "code_revision", "result"} <= set(item)
            or item.get("result") not in {"pass", "fail", "not_run", "skipped"}
            for item in (test_refs if isinstance(test_refs, list) else [{}])
        ):
            invalid_test_refs += 1
    return CatalogAuditReport(
        stable_count=len(stable),
        generic_operation_count=len(generic_ids),
        open_arguments_count=open_arguments,
        default_all_exposure_count=default_all,
        generic_operation_ids=tuple(sorted(generic_ids)),
        required_field_missing_counts=dict(sorted(missing_fields.items())),
        invalid_error_schema_count=invalid_error_schema,
        test_evidence_not_run_count=test_evidence_not_run,
        invalid_test_ref_count=invalid_test_refs,
    )


__all__ = ["CatalogAuditConfigurationError", "CatalogAuditReport", "audit_catalog"]
