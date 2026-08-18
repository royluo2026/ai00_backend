from __future__ import annotations

import pytest

from backend.capability_v2.catalog import ProviderArtifact, build_release
from backend.capability_v2.catalog_overlay import compose_catalogs
from backend.tests.test_capability_catalog_release import _descriptor


def product_release(capability_id: str, major: int):
    return build_release([_descriptor(capability_id, major)])


def extension_release(capability_id: str, major: int):
    return build_release([_descriptor(capability_id, major)])


def test_overlay_rejects_duplicate_capability_major():
    """A collision must never silently replace an official capability."""
    with pytest.raises(ValueError, match="catalog_overlay_capability_collision"):
        compose_catalogs(product_release("base.x", 1), extension_release("base.x", 1))


def test_overlay_rejects_duplicate_provider():
    """An extension cannot impersonate an official provider artifact."""
    provider = ProviderArtifact(
        plugin_id="test.governance", module="backend.capability_governance_test.provider",
        version="1.0.0", artifact_hash="sha256:" + "1" * 64,
    )
    with pytest.raises(ValueError, match="catalog_overlay_provider_collision"):
        compose_catalogs(build_release([], [provider]), build_release([], [provider]))


def test_overlay_keeps_product_and_extension_releases_separate():
    product = product_release("base.product.read", 1)
    extension = extension_release("base.extension.read", 1)

    effective = compose_catalogs(product, extension)

    assert effective.product is product
    assert effective.extension is extension
    assert {(item.id, item.major_version) for item in effective.effective.descriptors} == {
        ("base.product.read", 1), ("base.extension.read", 1),
    }
