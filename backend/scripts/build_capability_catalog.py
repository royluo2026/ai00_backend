"""Build or verify the checked-in immutable Capability Catalog Release."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_v2.bootstrap import build_capability_registry
from backend.capability_v2.acceptance_contract import TEST_MODULE, coverage_declarations
from backend.capability_v2.business_definition import business_definition_hash
from backend.capability_v2.catalog import (
    CatalogRelease,
    ProviderArtifact,
    build_catalog_entry,
    build_release,
    compatibility_errors,
    complete_governance_metadata,
    unbounded_collection_paths,
)
from backend.capability_v2.catalog_lineage import CatalogLineage
from backend.capability_v2.contracts import CapabilityDescriptorV2
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec


DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs" / "governance" / "capability-catalog-release.json"
DEFAULT_LINEAGE = REPOSITORY_ROOT / "docs" / "governance" / "capability-catalog-lineage.json"
PROVIDERS_PATH = REPOSITORY_ROOT / "backend" / "capability_v2" / "official_domains.json"
CONTRACT_TEST = REPOSITORY_ROOT / TEST_MODULE


def _release_document(release: CatalogRelease) -> dict[str, object]:
    document = release.model_dump(mode="json")
    document["descriptors"] = [build_catalog_entry(item) for item in release.descriptors]
    return document


def _load_release(path: Path) -> CatalogRelease:
    document = json.loads(path.read_text(encoding="utf-8"))
    for descriptor in document.get("descriptors", []):
        if isinstance(descriptor, dict):
            stored_hash = descriptor.pop("business_definition_hash", None)
            parsed_descriptor = CapabilityDescriptorV2.model_validate(descriptor)
            if stored_hash != business_definition_hash(parsed_descriptor):
                raise ValueError("business_definition_hash_mismatch")
    return CatalogRelease.model_validate(document)


def _verified_consumer_refs(capability_id: str) -> tuple[dict[str, str], ...]:
    """Return only consumers proven by migrated source files in this release."""
    consumers: list[dict[str, str]] = []
    if capability_id.startswith("craft.ebom.") or capability_id.startswith("craft.pbom."):
        consumers.append({
            "consumer_id": "craft-plugin/ebom.js",
            "consumer_type": "web",
            "version_constraint": ">=1",
        })
    if capability_id.startswith("factory.asset.") or capability_id.startswith("factory.structure."):
        consumers.append({
            "consumer_id": "knowledge-hub/factory_info.html",
            "consumer_type": "web",
            "version_constraint": ">=1",
        })
    if capability_id.startswith("project.project.") and ".atomic." in capability_id:
        consumers.append({
            "consumer_id": "knowledge-hub/project_info.html",
            "consumer_type": "web",
            "version_constraint": ">=1",
        })
    if capability_id == "craft.bop.version.list":
        consumers.append({
            "consumer_id": "web/my_files/my_files.js",
            "consumer_type": "web",
            "version_constraint": ">=1",
        })
    if capability_id in {"agent.flow.read", "agent.flow.change.apply"}:
        consumers.extend((
            {"consumer_id": "agent-plugin/flow_canvas/flow_editor.js", "consumer_type": "web", "version_constraint": ">=1"},
            {"consumer_id": "web/canvas/types/flow_type.js", "consumer_type": "web", "version_constraint": ">=1"},
        ))
    return tuple(consumers)


def _contract_test_revision() -> str:
    digest = hashlib.sha256(CONTRACT_TEST.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _providers() -> tuple[ProviderArtifact, ...]:
    document = json.loads(PROVIDERS_PATH.read_text(encoding="utf-8"))
    return tuple(ProviderArtifact.model_validate(item["artifact"]) for item in document["domains"])


def current_release() -> CatalogRelease:
    registry = build_capability_registry(REPOSITORY_ROOT, PROVIDERS_PATH)
    registrations = {
        (item.spec.id, item.spec.version): item for item in registry.snapshot()
    }
    descriptors = [
        complete_governance_metadata(
            registrations[key].descriptor or descriptor_from_provider_spec(registrations[key].spec),
            provider_ref=f"{registrations[key].spec.owner}.provider",
            consumer_refs=_verified_consumer_refs(registrations[key].spec.id),
            test_refs=coverage_declarations(
                registrations[key].spec.id,
                registrations[key].spec.version,
                code_revision=_contract_test_revision(),
            ),
        )
        for key in sorted(registrations)
    ]
    grandfathered: set[tuple[str, int, str]] = set()
    if DEFAULT_OUTPUT.is_file():
        previous_document = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        for item in previous_document.get("descriptors", []):
            if item.get("lifecycle_status") != "stable":
                continue
            for path in unbounded_collection_paths(item.get("output_schema") or {}):
                grandfathered.add((item["id"], int(item["major_version"]), path))
    return build_release(
        descriptors,
        _providers(),
        grandfathered_unbounded_paths=grandfathered,
        enforce_collection_boundaries=True,
    )


def next_lineage(
    current: CatalogLineage | None,
    previous_release: CatalogRelease,
    candidate_release: CatalogRelease,
) -> CatalogLineage:
    lineage = current or CatalogLineage.from_releases((previous_release,))
    return lineage.append(previous_release, candidate_release)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--lineage", type=Path, default=DEFAULT_LINEAGE)
    parser.add_argument("--previous", type=Path, help="fail on breaking changes from a prior release")
    args = parser.parse_args(argv)
    previous_release = (
        _load_release(args.output)
        if args.output.is_file() else None
    )
    lineage = (
        CatalogLineage.model_validate_json(args.lineage.read_text(encoding="utf-8"))
        if args.lineage.is_file() else None
    )
    if args.check and lineage is None:
        print(f"Catalog lineage missing: {args.lineage}")
        return 1
    if args.write and lineage is None and previous_release is not None:
        lineage = CatalogLineage.from_releases((previous_release,))
        args.lineage.parent.mkdir(parents=True, exist_ok=True)
        args.lineage.write_text(lineage.model_dump_json(indent=2) + "\n", encoding="utf-8")
    release = current_release()
    if args.previous:
        previous = _load_release(args.previous)
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
        expected = _load_release(args.output)
        if expected.catalog_hash != release.catalog_hash or expected.release_id != release.release_id:
            print(
                f"Catalog release drift: expected {expected.release_id}/{expected.catalog_hash}, "
                f"actual {release.release_id}/{release.catalog_hash}"
            )
            return 1
        assert lineage is not None
        latest = lineage.entries[-1]
        if latest.release_id != expected.release_id or latest.catalog_hash != expected.catalog_hash:
            print(
                f"Catalog lineage drift: latest {latest.release_id}/{latest.catalog_hash}, "
                f"catalog {expected.release_id}/{expected.catalog_hash}"
            )
            return 1
        print(f"Catalog release check passed: {expected.release_id}, {len(expected.descriptors)} descriptors")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if previous_release is None:
        lineage = CatalogLineage.from_releases((release,))
    else:
        lineage = next_lineage(lineage, previous_release, release)
    args.output.write_text(
        json.dumps(_release_document(release), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.lineage.parent.mkdir(parents=True, exist_ok=True)
    args.lineage.write_text(lineage.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Catalog release written: {release.release_id}, {len(release.descriptors)} descriptors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
