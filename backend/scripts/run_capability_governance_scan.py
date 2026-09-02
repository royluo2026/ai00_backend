"""Run the bounded, offline capability-governance implementation scan."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_governance_test.config import GovernanceSettings
from backend.capability_governance_test.fingerprint import snapshot_fingerprint
from backend.capability_governance_test.models import ScanFinding, SnapshotDocument
from backend.capability_governance_test.scanner import GovernanceScanner
from backend.capability_v2.catalog import load_catalog_release
from backend.capability_v2.domain_manifest import load_domain_manifests


PRODUCT_CATALOG = REPOSITORY_ROOT / "docs/governance/capability-catalog-release.json"
EXTENSION_CATALOG = REPOSITORY_ROOT / "docs/governance/test-extension/capability-governance-catalog-release.json"
OFFICIAL_DOMAINS = REPOSITORY_ROOT / "backend/capability_v2/official_domains.json"
ACCEPTANCE_MANIFEST = REPOSITORY_ROOT / "backend/tests/acceptance/fixtures/case-manifest.json"
EXPECTED_OFFICIAL_DOMAIN_COUNT = 11
EXPECTED_OFFICIAL_DOMAINS = (
    "agent", "base", "craft", "device", "digital_model", "factory", "integration",
    "knowledge", "ontology", "project_management", "simulation",
)
PINNED_STABLE_PRODUCT_DESCRIPTOR_COUNT = 488


def _inside_repository(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("output_path_not_in_repository") from exc
    return resolved


def _blocked_document(source_path: str, message: str) -> SnapshotDocument:
    finding = ScanFinding(
        "scan_configuration_error", "blocking", "configuration", source_path, message,
    )
    draft = SnapshotDocument(
        "", None, "offline", "", (), (), (), (), (finding,), "blocked",
        catalog_hash="sha256:" + "0" * 64,
    )
    return replace(draft, snapshot_hash=snapshot_fingerprint(draft))


def _write_report(
    output: Path,
    document: SnapshotDocument,
    *,
    official_domain_count: int = 0,
    product_descriptor_count: int = 0,
    stable_product_descriptor_count: int = 0,
    extension_descriptor_count: int = 0,
) -> dict[str, object]:
    report = {
        "mode": "offline",
        "status": document.scan_status,
        "official_domain_count": official_domain_count,
        "product_descriptor_count": product_descriptor_count,
        "stable_product_descriptor_count": stable_product_descriptor_count,
        "extension_descriptor_count": extension_descriptor_count,
        "snapshot": document.to_json(),
    }
    destination = _inside_repository(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def run_offline_scan(output: Path) -> dict[str, object]:
    """Produce one portable document from checked-in trusted inputs only."""
    # Bind the scanner to the same official registry that serves requests.  A
    # catalog-only scan can only emit ``declared_in`` edges and falsely reports
    # every capability as missing its provider.
    from backend.capability_v2.bootstrap import build_capability_registry

    failure_source = "product_catalog"
    failure_reason = "product_catalog_validation_error"
    try:
        product = load_catalog_release(PRODUCT_CATALOG.read_text(encoding="utf-8"))
        failure_source, failure_reason = "extension_catalog", "extension_catalog_validation_error"
        extension = load_catalog_release(EXTENSION_CATALOG.read_text(encoding="utf-8"))
        failure_source, failure_reason = "official_domain_manifests", "official_domain_manifests_load_error"
        manifests = load_domain_manifests(OFFICIAL_DOMAINS)
        failure_source, failure_reason = "acceptance_manifest", "acceptance_manifest_load_error"
        acceptance_manifest = json.loads(ACCEPTANCE_MANIFEST.read_text(encoding="utf-8"))
        failure_source, failure_reason = "official_domain_manifests", "official_domain_count_mismatch"
        if len(manifests.domains) != EXPECTED_OFFICIAL_DOMAIN_COUNT:
            raise RuntimeError(failure_reason)
        failure_reason = "official_domain_set_mismatch"
        if tuple(sorted(item.domain_id for item in manifests.domains)) != EXPECTED_OFFICIAL_DOMAINS:
            raise RuntimeError(failure_reason)
        stable_count = sum(item.lifecycle_status.value == "stable" for item in product.descriptors)
        failure_source, failure_reason = "product_catalog", "pinned_product_descriptor_count_mismatch"
        if stable_count != PINNED_STABLE_PRODUCT_DESCRIPTOR_COUNT:
            raise RuntimeError(failure_reason)
        failure_source, failure_reason = "capability_registry", "capability_registry_load_error"
        registry = build_capability_registry(REPOSITORY_ROOT)
    except Exception:
        return _write_report(output, _blocked_document(failure_source, failure_reason))
    document = GovernanceScanner(
        GovernanceSettings("test-governance", REPOSITORY_ROOT),
        registry_snapshot=registry.snapshot(),
        product_catalog=product,
        extension_catalog=extension,
        domain_manifests=manifests,
        acceptance_manifest=acceptance_manifest,
        acceptance_manifest_path=ACCEPTANCE_MANIFEST.relative_to(REPOSITORY_ROOT).as_posix(),
    ).scan(code_revision="offline")
    return _write_report(
        output, document,
        official_domain_count=len(manifests.domains),
        product_descriptor_count=len(product.descriptors),
        stable_product_descriptor_count=stable_count,
        extension_descriptor_count=len(extension.descriptors),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="required: networked scanning is unsupported")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.offline:
        parser.error("--offline is required")
    report = run_offline_scan(args.output)
    print(json.dumps({
        "snapshot_hash": report["snapshot"]["snapshot_hash"],
        "official_domain_count": report["official_domain_count"],
        "product_descriptor_count": report["product_descriptor_count"],
        "stable_product_descriptor_count": report["stable_product_descriptor_count"],
        "extension_descriptor_count": report["extension_descriptor_count"],
        "scan_status": report["status"],
    }, sort_keys=True))
    return 1 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
