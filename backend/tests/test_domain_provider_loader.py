from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.provider_loader import DomainProviderLoader, ProviderTrustError
from backend.scripts.freeze_official_domains import (
    current_repository_head,
    freeze_official_domains,
    hash_manifest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DOMAINS = REPOSITORY_ROOT / "backend/capability_v2/official_domains.json"


def _write_document(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "official_domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_loader_registers_domains_in_sorted_domain_order() -> None:
    registry = CapabilityRegistry()
    loader = DomainProviderLoader(
        REPOSITORY_ROOT,
        load_domain_manifests(OFFICIAL_DOMAINS),
    )

    loaded = loader.register_all(registry)

    assert loaded == tuple(sorted(loaded))
    assert "base" in loaded
    assert "craft" in loaded
    assert registry.get("system.search", 1).spec.owner == "base"


def test_loader_rejects_changed_artifact_hash(tmp_path: Path) -> None:
    document = json.loads(OFFICIAL_DOMAINS.read_text(encoding="utf-8"))
    document["domains"][0]["artifact"]["artifact_hash"] = f"sha256:{'0' * 64}"
    path = _write_document(tmp_path, document)

    with pytest.raises(ProviderTrustError, match="artifact_mismatch"):
        DomainProviderLoader(
            REPOSITORY_ROOT,
            load_domain_manifests(path),
        ).register_all(CapabilityRegistry())


def test_loader_rejects_search_export_owned_by_another_domain(tmp_path: Path) -> None:
    document = json.loads(OFFICIAL_DOMAINS.read_text(encoding="utf-8"))
    craft = next(item for item in document["domains"] if item["domain_id"] == "craft")
    craft["search_export"] = {
        "capability_id": "system.search",
        "major_version": 1,
    }
    path = _write_document(tmp_path, document)

    with pytest.raises(ProviderTrustError, match="search_export_owner_mismatch"):
        DomainProviderLoader(
            REPOSITORY_ROOT,
            load_domain_manifests(path),
        ).register_all(CapabilityRegistry())


def test_freeze_rejects_stale_manifest_digest(tmp_path: Path) -> None:
    path = tmp_path / "official_domains.json"
    path.write_bytes(OFFICIAL_DOMAINS.read_bytes())

    with pytest.raises(ProviderTrustError, match="stale_manifest"):
        freeze_official_domains(
            REPOSITORY_ROOT,
            path,
            expected_head=current_repository_head(REPOSITORY_ROOT),
            expected_manifest_sha256=f"sha256:{'0' * 64}",
            check=False,
        )


def test_freeze_rejects_stale_integration_head(tmp_path: Path) -> None:
    path = tmp_path / "official_domains.json"
    path.write_bytes(OFFICIAL_DOMAINS.read_bytes())

    with pytest.raises(ProviderTrustError, match="stale_head"):
        freeze_official_domains(
            REPOSITORY_ROOT,
            path,
            expected_head="0" * 40,
            expected_manifest_sha256=hash_manifest(path),
            check=False,
        )
