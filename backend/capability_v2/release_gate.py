"""Single release gate combining completion, Web path, and catalog audits."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .catalog_audit import CatalogAuditReport, audit_catalog
from .completion import CompletionReport, evaluate_completion


@dataclass(frozen=True)
class ReleaseGateReport:
    completion: CompletionReport
    audit: CatalogAuditReport

    @property
    def passed(self) -> bool:
        return (
            self.completion.complete
            and self.completion.web_consumer_bypasses == 0
            and self.audit.open_arguments_count == 0
            and self.audit.default_all_exposure_count == 0
        )

    def serialized(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "completion": self.completion.serialized(),
            "catalog_audit": self.audit.serialized(),
        }


def evaluate_release_gate(
    root: Path,
    *,
    web_root: Path,
    catalog_path: Path | None = None,
) -> ReleaseGateReport:
    return ReleaseGateReport(
        completion=evaluate_completion(root, mode="strict", web_root=web_root),
        audit=audit_catalog(catalog_path or root / "docs/capabilities/catalog.v2.json"),
    )


__all__ = ["ReleaseGateReport", "evaluate_release_gate"]
