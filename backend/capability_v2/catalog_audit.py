"""Machine-readable audit for Capability contract and exposure provenance debt."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .acceptance_contract import mandatory_test_source_revision
from .business_definition import is_generated_business_effect


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
    test_evidence_failed_count: int = 0
    self_attested_test_result_count: int = 0
    invalid_test_ref_count: int = 0
    invalid_consumer_ref_count: int = 0
    invalid_business_effect_count: int = 0
    invalid_side_effect_count: int = 0
    generated_business_effect_count: int = 0
    missing_business_rule_declaration_count: int = 0

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
            "test_evidence_failed_count": self.test_evidence_failed_count,
            "self_attested_test_result_count": self.self_attested_test_result_count,
            "invalid_test_ref_count": self.invalid_test_ref_count,
            "invalid_consumer_ref_count": self.invalid_consumer_ref_count,
            "invalid_business_effect_count": self.invalid_business_effect_count,
            "invalid_side_effect_count": self.invalid_side_effect_count,
            "generated_business_effect_count": self.generated_business_effect_count,
            "missing_business_rule_declaration_count": self.missing_business_rule_declaration_count,
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


def audit_catalog(
    path: Path, *, source_root: Path | None = None,
) -> CatalogAuditReport:
    revision = mandatory_test_source_revision(source_root) if source_root else None
    return audit_catalog_entries(_load_catalog(path), mandatory_test_revision=revision)


def audit_catalog_entries(
    entries: list[dict], *, mandatory_test_revision: str | None = None,
) -> CatalogAuditReport:
    stable = [entry for entry in entries if entry.get("lifecycle_status") == "stable"]
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
    test_evidence_failed = 0
    self_attested_test_results = 0
    invalid_test_refs = 0
    invalid_consumer_refs = 0
    invalid_business_effects = 0
    invalid_side_effects = 0
    generated_business_effects = 0
    missing_business_rule_declarations = 0
    generic_side_effects = {
        "Reads domain state without mutation.",
        "Writes domain state through the owning Provider.",
    }
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
            if field == "consumer_refs" and value in (None, [], {}) and entry.get("no_consumer_reason"):
                continue
            if value is None or value == "" or value == [] or value == {}:
                missing_fields[field] += 1
        consumers = entry.get("consumer_refs")
        reason = entry.get("no_consumer_reason")
        if consumers in (None, [], {}):
            if not isinstance(reason, str) or not reason.strip():
                invalid_consumer_refs += 1
        elif not isinstance(consumers, list) or any(
            not isinstance(item, dict)
            or not {"consumer_id", "consumer_type", "version_constraint"} <= set(item)
            or not all(isinstance(item.get(key), str) and item[key].strip() for key in ("consumer_id", "consumer_type", "version_constraint"))
            for item in consumers
        ):
            invalid_consumer_refs += 1
        description = entry.get("description")
        business_effect = entry.get("business_effect")
        if is_generated_business_effect(business_effect, description):
            invalid_business_effects += 1
            generated_business_effects += 1
        invariants = entry.get("business_invariants")
        no_invariant_reason = entry.get("no_business_invariant_reason")
        if not invariants and (
            not isinstance(no_invariant_reason, str) or not no_invariant_reason.strip()
        ):
            missing_business_rule_declarations += 1
        side_effects = entry.get("side_effects")
        if not isinstance(side_effects, str) or not side_effects.strip() or side_effects.strip() in generic_side_effects:
            invalid_side_effects += 1
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
        if isinstance(test_refs, list) and any(
            isinstance(item, dict) and item.get("result") == "fail"
            for item in test_refs
        ):
            test_evidence_failed += 1
        if isinstance(test_refs, list) and any(
            isinstance(item, dict) and "result" in item
            for item in test_refs
        ):
            self_attested_test_results += 1
        if not isinstance(test_refs, list) or any(
            not isinstance(item, dict)
            or not {"test_type", "test_node_id", "code_revision"} <= set(item)
            for item in (test_refs if isinstance(test_refs, list) else [{}])
        ) or (
            mandatory_test_revision is not None
            and any(
                item.get("code_revision") != mandatory_test_revision
                for item in test_refs
            )
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
        test_evidence_failed_count=test_evidence_failed,
        self_attested_test_result_count=self_attested_test_results,
        invalid_test_ref_count=invalid_test_refs,
        invalid_consumer_ref_count=invalid_consumer_refs,
        invalid_business_effect_count=invalid_business_effects,
        invalid_side_effect_count=invalid_side_effects,
        generated_business_effect_count=generated_business_effects,
        missing_business_rule_declaration_count=missing_business_rule_declarations,
    )


__all__ = [
    "CatalogAuditConfigurationError",
    "CatalogAuditReport",
    "audit_catalog",
    "audit_catalog_entries",
]
