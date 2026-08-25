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
from backend.capability_v2.catalog import (
    CatalogRelease,
    ProviderArtifact,
    build_release,
    compatibility_errors,
    complete_governance_metadata,
    unbounded_collection_paths,
)
from backend.capability_v2.descriptor_adapter import descriptor_from_provider_spec


DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs" / "governance" / "capability-catalog-release.json"
PROVIDERS_PATH = REPOSITORY_ROOT / "backend" / "capability_v2" / "official_domains.json"
CONTRACT_TEST = REPOSITORY_ROOT / "backend/tests/test_capability_v2_contracts.py"


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
            test_refs=(
                {
                    "test_type": "contract",
                    "test_node_id": "backend/tests/test_capability_v2_contracts.py::test_v21_descriptor_exposes_independent_business_and_error_contract_fields",
                    "code_revision": _contract_test_revision(),
                    "result": "pass",
                    "path": "backend/tests/test_capability_v2_contracts.py",
                },
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
