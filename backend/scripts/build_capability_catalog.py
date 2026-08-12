"""Build or verify the checked-in immutable Capability Catalog Release."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_v2.bootstrap import build_capability_registry
from backend.capability_v2.catalog import (
    CatalogRelease,
    ProviderArtifact,
    build_release,
    compatibility_errors,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec


DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs" / "governance" / "capability-catalog-release.json"
PROVIDERS_PATH = REPOSITORY_ROOT / "backend" / "capability_v2" / "official_domains.json"


def _providers() -> tuple[ProviderArtifact, ...]:
    document = json.loads(PROVIDERS_PATH.read_text(encoding="utf-8"))
    return tuple(ProviderArtifact.model_validate(item["artifact"]) for item in document["domains"])


def current_release() -> CatalogRelease:
    registry = build_capability_registry(REPOSITORY_ROOT, PROVIDERS_PATH)
    registrations = {
        (item.spec.id, item.spec.version): item for item in registry.snapshot()
    }
    descriptors = [
        registrations[key].descriptor or descriptor_from_provider_spec(registrations[key].spec)
        for key in sorted(registrations)
    ]
    return build_release(descriptors, _providers())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--previous", type=Path, help="fail on breaking changes from a prior release")
    args = parser.parse_args(argv)
    release = current_release()
    if args.previous:
        previous = CatalogRelease.model_validate_json(args.previous.read_text(encoding="utf-8"))
        breaking = compatibility_errors(previous, release)
        if breaking:
            print("Catalog compatibility check failed:")
            for error in breaking:
                print(f"- {error}")
            return 1
    if args.check:
        if not args.output.is_file():
            print(f"Catalog release missing: {args.output}")
            return 1
        expected = CatalogRelease.model_validate_json(args.output.read_text(encoding="utf-8"))
        if expected.catalog_hash != release.catalog_hash or expected.release_id != release.release_id:
            print(
                f"Catalog release drift: expected {expected.release_id}/{expected.catalog_hash}, "
                f"actual {release.release_id}/{release.catalog_hash}"
            )
            return 1
        print(f"Catalog release check passed: {expected.release_id}, {len(expected.descriptors)} descriptors")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(release.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Catalog release written: {release.release_id}, {len(release.descriptors)} descriptors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
