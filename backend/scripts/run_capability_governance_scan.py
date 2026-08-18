"""Run the bounded, offline capability-governance implementation scan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_governance_test.config import GovernanceSettings
from backend.capability_governance_test.scanner import GovernanceScanner
from backend.capability_v2.bootstrap import build_capability_registry
from backend.capability_v2.catalog import CatalogRelease
from backend.capability_v2.domain_manifest import load_domain_manifests


PRODUCT_CATALOG = REPOSITORY_ROOT / "docs/governance/capability-catalog-release.json"
EXTENSION_CATALOG = REPOSITORY_ROOT / "docs/governance/test-extension/capability-governance-catalog-release.json"
OFFICIAL_DOMAINS = REPOSITORY_ROOT / "backend/capability_v2/official_domains.json"
EXPECTED_OFFICIAL_DOMAIN_COUNT = 11
PINNED_STABLE_PRODUCT_DESCRIPTOR_COUNT = 267


def _inside_repository(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("output_path_not_in_repository") from exc
    return resolved


def run_offline_scan(output: Path) -> dict[str, object]:
    """Produce one portable document from checked-in trusted inputs only."""
    product = CatalogRelease.model_validate_json(PRODUCT_CATALOG.read_text(encoding="utf-8"))
    extension = CatalogRelease.model_validate_json(EXTENSION_CATALOG.read_text(encoding="utf-8"))
    manifests = load_domain_manifests(OFFICIAL_DOMAINS)
    if len(manifests.domains) != EXPECTED_OFFICIAL_DOMAIN_COUNT:
        raise RuntimeError("official_domain_count_mismatch")
    stable_count = sum(item.lifecycle_status.value == "stable" for item in product.descriptors)
    if stable_count != PINNED_STABLE_PRODUCT_DESCRIPTOR_COUNT:
        raise RuntimeError("pinned_product_descriptor_count_mismatch")
    registry = build_capability_registry(REPOSITORY_ROOT, OFFICIAL_DOMAINS)
    document = GovernanceScanner(
        GovernanceSettings("test-governance", REPOSITORY_ROOT),
        registry_snapshot=registry.snapshot(),
        product_catalog=product,
        extension_catalog=extension,
        domain_manifests=manifests,
    ).scan(code_revision="offline")
    report = {
        "mode": "offline",
        "official_domain_count": len(manifests.domains),
        "product_descriptor_count": len(product.descriptors),
        "stable_product_descriptor_count": stable_count,
        "extension_descriptor_count": len(extension.descriptors),
        "snapshot": document.to_json(),
    }
    destination = _inside_repository(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


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
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
