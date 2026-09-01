"""Build or verify the test-only Capability Governance Catalog Extension."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_governance_test.contracts import ALL_IDS, provider_artifact
from backend.capability_governance_test.provider import register_governance_capabilities
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.catalog import CatalogRelease, build_release, load_catalog_release


DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs" / "governance" / "test-extension" / "capability-governance-catalog-release.json"


def current_release() -> CatalogRelease:
    """Build only the tracked test-governance provider's 18 descriptors.

    The test extension is intentionally independent from the official provider
    registry: its artifact hash must not be affected by unrelated local edits.
    """
    registry = CapabilityRegistry()
    register_governance_capabilities(registry)
    descriptors = [registry.get(capability_id, 1).descriptor for capability_id in ALL_IDS]
    return build_release(
        descriptors,
        (provider_artifact(REPOSITORY_ROOT),),
        enforce_collection_boundaries=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    release = current_release()
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(release.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"Governance catalog release written: {release.release_id}, {len(release.descriptors)} descriptors")
        return 0
    if not args.output.is_file():
        print(f"Governance catalog release missing: {args.output}")
        return 1
    expected = load_catalog_release(args.output.read_text(encoding="utf-8"))
    if (expected.catalog_hash, expected.release_id) != (release.catalog_hash, release.release_id):
        print(f"Governance catalog release drift: expected {expected.release_id}/{expected.catalog_hash}, actual {release.release_id}/{release.catalog_hash}")
        return 1
    print(f"Governance catalog release check passed: {expected.release_id}, {len(expected.descriptors)} descriptors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
