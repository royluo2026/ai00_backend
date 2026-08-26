from __future__ import annotations

import pytest

from backend.capability_v2.catalog_targets import CatalogTargetIndex


def test_resolve_stable_rejects_deprecated_and_cross_domain() -> None:
    index = CatalogTargetIndex.from_catalog({"capabilities": [
        {"id": "craft.old.read", "major_version": 1, "lifecycle": "deprecated", "owner": "craft"},
        {"id": "project.scope.read", "major_version": 1, "lifecycle": "stable", "owner": "project"},
    ]})

    assert index.resolve_stable("craft.old.read", 1, "craft").reason_code == "target_not_stable"
    assert index.resolve_stable("project.scope.read", 1, "craft").reason_code == "target_owner_mismatch"


def test_resolve_stable_accepts_exact_version_and_owner() -> None:
    index = CatalogTargetIndex.from_catalog({"capabilities": [
        {"id": "craft.bop.read", "major_version": 1, "lifecycle": "stable", "owner": "craft"},
    ]})

    assert index.resolve_stable("craft.bop.read", 1, "craft").ok is True


def test_resolve_stable_rejects_missing_and_replaced_targets() -> None:
    index = CatalogTargetIndex.from_catalog(
        {"capabilities": [{"id": "craft.old.read", "major_version": 1, "lifecycle": "stable", "owner": "craft"}]},
        replacements={("craft.old.read", 1): "craft.new.read"},
    )

    assert index.resolve_stable("craft.missing.read", 1, "craft").reason_code == "target_missing"
    assert index.resolve_stable("craft.old.read", 1, "craft").reason_code == "target_replaced"


def test_catalog_target_index_rejects_duplicate_versions() -> None:
    with pytest.raises(ValueError, match="duplicate Catalog target"):
        CatalogTargetIndex.from_catalog({"capabilities": [
            {"id": "craft.bop.read", "major_version": 1, "lifecycle": "stable", "owner": "craft"},
            {"id": "craft.bop.read", "major_version": 1, "lifecycle": "stable", "owner": "craft"},
        ]})
