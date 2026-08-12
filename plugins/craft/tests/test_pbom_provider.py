from __future__ import annotations

from pathlib import Path

import pytest

from plugins.craft.craft_backend.application.pbom import PbomService
from plugins.craft.craft_backend.domain.pbom import ImmutableVersionError, PbomVersion, PbomVersionStatus


class MemoryRepository:
    def __init__(self, version: PbomVersion):
        self.version = version

    def get_version(self, version_gid: str):
        return self.version if version_gid == self.version.gid else None

    def replace_part(self, version_gid: str, part: dict):
        raise AssertionError("published version must be rejected before persistence")


def test_published_pbom_version_is_immutable():
    version = PbomVersion(gid="pbom-1", project_ref="project:1", version_tag="A", status=PbomVersionStatus.PUBLISHED)
    service = PbomService(MemoryRepository(version))

    with pytest.raises(ImmutableVersionError):
        service.change_part("pbom-1", {"part_no": "P-2"})


def test_native_pbom_provider_registers_complete_lifecycle():
    from plugins.craft.craft_backend.capabilities.pbom_descriptors import PBOM_CAPABILITY_IDS
    from plugins.craft.craft_backend.capabilities import register_capabilities

    assert set(PBOM_CAPABILITY_IDS) == {
        "craft.pbom.version.create", "craft.pbom.version.get", "craft.pbom.version.search",
        "craft.pbom.version.submit", "craft.pbom.version.publish", "craft.pbom.version.archive",
        "craft.pbom.version.compare", "craft.pbom.draft.change.preview",
        "craft.pbom.draft.change.apply", "craft.pbom.part.search", "craft.pbom.import.preview",
    }
    class Registry:
        def __init__(self): self.items = []
        def register(self, spec, handler, *, descriptor=None): self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)
    registered = {item[0].id for item in registry.items}
    assert set(PBOM_CAPABILITY_IDS) <= registered
    assert "craft.pbom.snapshot.get" not in registered
    assert "craft.pbom.snapshot.compare" not in registered


def test_native_pbom_slice_contains_no_ebom_identifiers():
    root = Path(__file__).parents[1] / "craft_backend"
    paths = [
        root / "domain" / "pbom.py",
        root / "application" / "pbom.py",
        root / "capabilities" / "pbom_descriptors.py",
        root / "infrastructure" / "repositories" / "pbom.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "ebom" not in text.casefold()


def test_pbom_migration_persists_only_exact_external_refs():
    migration = (
        Path(__file__).parents[3]
        / "backend" / "db" / "migrations" / "domains" / "craft" / "0001_pbom.sql"
    ).read_text(encoding="utf-8")
    for column in ("project_ref", "knowledge_revision_ref", "ontology_release_ref", "revision_commit_ref"):
        assert column in migration
    assert "workmanship_proj_" not in migration
    assert "workmanship_know_" not in migration
    assert "workmanship_onto_" not in migration
