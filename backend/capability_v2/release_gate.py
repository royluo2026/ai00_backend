"""Single release gate combining completion, Web path, and catalog audits."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .atomicity import AtomicityAudit, audit_generic_operations, load_atomicity_dispositions
from .catalog_targets import CatalogTargetIndex
from .orchestration_audit import OrchestrationAudit, audit_orchestration_registry
from .catalog_audit import CatalogAuditReport, audit_catalog
from .completion import CompletionReport, evaluate_completion


@dataclass(frozen=True)
class ReleaseGateReport:
    completion: CompletionReport
    audit: CatalogAuditReport
    atomicity: AtomicityAudit | None = None
    orchestration: tuple[OrchestrationAudit, ...] = ()

    @property
    def passed(self) -> bool:
        required_fields_complete = all(
            value == 0 for value in self.audit.required_field_missing_counts.values()
        )
        return (
            self.completion.complete
            and self.completion.web_consumer_bypasses == 0
            and self.audit.open_arguments_count == 0
            and self.audit.default_all_exposure_count == 0
            and required_fields_complete
            and self.audit.invalid_error_schema_count == 0
            and self.audit.test_evidence_not_run_count == 0
            and self.audit.invalid_test_ref_count == 0
            and self.atomicity is not None
            and self.atomicity.passed
            and len(self.orchestration) == 3
            and all(item.passed for item in self.orchestration)
        )

    def serialized(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "completion": self.completion.serialized(),
            "catalog_audit": self.audit.serialized(),
            "atomicity": (
                {
                    "passed": self.atomicity.passed,
                    "generic_ids": list(self.atomicity.generic_ids),
                    "unclassified_ids": list(self.atomicity.unclassified_ids),
                    "invalid_ids": list(self.atomicity.invalid_ids),
                    "expired_ids": list(self.atomicity.expired_ids),
                    "missing_replacement_ids": list(self.atomicity.missing_replacement_ids),
                }
                if self.atomicity is not None
                else None
            ),
            "orchestration": [item.serialized() for item in self.orchestration],
        }


def evaluate_release_gate(
    root: Path,
    *,
    web_root: Path,
    catalog_path: Path | None = None,
    atomicity_path: Path | None = None,
) -> ReleaseGateReport:
    resolved_catalog = catalog_path or root / "docs/capabilities/catalog.v2.json"
    resolved_atomicity = atomicity_path or root / "docs/governance/capability-atomicity-dispositions.json"
    catalog = json.loads(resolved_catalog.read_text(encoding="utf-8"))
    dispositions = load_atomicity_dispositions(resolved_atomicity)
    catalog_index = CatalogTargetIndex.from_catalog(
        catalog,
        replacements={
            (item.capability_id, item.major_version): item.replacement_capabilities[0]
            for item in dispositions.dispositions
            if item.replacement_capabilities
        },
    )
    orchestration = tuple(
        audit_orchestration_registry(root / "docs/governance" / name, catalog_index)
        for name in ("task_tool_registry.json", "bff_capability_registry.json", "business_capability_ledger.json")
    )
    return ReleaseGateReport(
        completion=evaluate_completion(root, mode="strict", web_root=web_root),
        audit=audit_catalog(resolved_catalog, source_root=root),
        atomicity=audit_generic_operations(catalog, dispositions),
        orchestration=orchestration,
    )


__all__ = ["ReleaseGateReport", "evaluate_release_gate"]
