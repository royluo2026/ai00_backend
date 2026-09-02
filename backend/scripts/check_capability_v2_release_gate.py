"""Run the fail-closed Capability V2 release gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.release_gate import (
    BusinessGovernanceConfigurationError,
    create_legacy_baseline,
    evaluate_release_gate,
    load_business_approval_artifact,
)
from backend.capability_v2.atomicity import AtomicityConfigurationError
from backend.capability_v2.catalog_audit import CatalogAuditConfigurationError
from backend.capability_v2.completion import CompletionConfigurationError
from backend.capability_v2.consumer_routes import RouteScanConfigurationError
from backend.capability_v2.orchestration_audit import OrchestrationAuditConfigurationError


CONFIGURATION_ERRORS = (
    AtomicityConfigurationError,
    CatalogAuditConfigurationError,
    CompletionConfigurationError,
    RouteScanConfigurationError,
    OrchestrationAuditConfigurationError,
    BusinessGovernanceConfigurationError,
)


def evaluate_document(
    root: Path, web_root: Path, catalog: Path | None,
    legacy_baseline: Path | None = None,
    business_approvals: Path | None = None,
) -> dict:
    try:
        approval_lookup = None
        if business_approvals is not None:
            business_catalog_document = json.loads(
                (root / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
            )
            approval_lookup = load_business_approval_artifact(
                business_approvals,
                catalog_release_id=str(business_catalog_document.get("release_id", "")),
            )
        report = evaluate_release_gate(
            root, web_root=web_root, catalog_path=catalog,
            legacy_baseline_path=legacy_baseline,
            business_review_lookup=approval_lookup,
        )
    except CONFIGURATION_ERRORS as exc:
        reason_code = {
            RouteScanConfigurationError: "route_scan_configuration_error",
            CompletionConfigurationError: "completion_configuration_error",
            CatalogAuditConfigurationError: "catalog_audit_configuration_error",
            AtomicityConfigurationError: "atomicity_configuration_error",
            OrchestrationAuditConfigurationError: "orchestration_configuration_error",
            BusinessGovernanceConfigurationError: "business_governance_configuration_error",
        }.get(type(exc), "release_gate_configuration_error")
        return {
            "passed": False,
            "configuration_blockers": [{
                "reason_code": reason_code,
                "message": str(exc),
            }],
        }
    return report.serialized()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--web-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--legacy-baseline", type=Path)
    parser.add_argument("--business-approvals", type=Path)
    parser.add_argument("--create-legacy-baseline", action="store_true")
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    if args.create_legacy_baseline:
        baseline = create_legacy_baseline(
            args.root / "docs/governance/capability-catalog-release.json",
            args.legacy_baseline or args.root / "docs/governance/capability-business-governance-legacy-baseline.json",
            source_revision=str(args.source_revision or ""),
        )
        print(json.dumps({
            "status": "created",
            "source_revision": baseline.source_revision,
            "catalog_release_id": baseline.catalog_release_id,
            "capability_count": len(baseline.capabilities),
            "baseline_hash": baseline.baseline_hash,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    document = evaluate_document(
        args.root, args.web_root, args.catalog, args.legacy_baseline,
        args.business_approvals,
    )
    print(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if document.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
