"""Compose an official catalog with a separately governed test extension."""
from __future__ import annotations

from dataclasses import dataclass

from .catalog import CatalogRelease, build_release


@dataclass(frozen=True)
class EffectiveCatalog:
    product: CatalogRelease
    extension: CatalogRelease
    effective: CatalogRelease


def compose_catalogs(product: CatalogRelease, extension: CatalogRelease) -> EffectiveCatalog:
    product_keys = {(item.id, item.major_version) for item in product.descriptors}
    extension_keys = {(item.id, item.major_version) for item in extension.descriptors}
    if product_keys & extension_keys:
        raise ValueError("catalog_overlay_capability_collision")
    product_providers = {item.plugin_id for item in product.provider_artifacts}
    extension_providers = {item.plugin_id for item in extension.provider_artifacts}
    if product_providers & extension_providers:
        raise ValueError("catalog_overlay_provider_collision")
    return EffectiveCatalog(
        product=product,
        extension=extension,
        effective=build_release(
            (*product.descriptors, *extension.descriptors),
            (*product.provider_artifacts, *extension.provider_artifacts),
        ),
    )


__all__ = ["EffectiveCatalog", "compose_catalogs"]
