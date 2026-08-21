"""Single release gate combining completion, Web path, and catalog audits."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .atomicity import AtomicityAudit, audit_generic_operations, load_atomicity_dispositions
from .catalog_audit import CatalogAuditReport, audit_catalog
from .completion import CompletionReport, evaluate_completion


@dataclass(frozen=True)
class ReleaseGateReport:
    completion: CompletionReport
    audit: CatalogAuditReport
    atomicity: AtomicityAudit | None = None

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
            and self.atomicity is not None
            and self.atomicity.passed
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
    return ReleaseGateReport(
        completion=evaluate_completion(root, mode="strict", web_root=web_root),
        audit=audit_catalog(resolved_catalog),
        atomicity=audit_generic_operations(catalog, load_atomicity_dispositions(resolved_atomicity)),
    )


__all__ = ["ReleaseGateReport", "evaluate_release_gate"]
