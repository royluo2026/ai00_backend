"""Capability V2 contracts and migration services."""

from .catalog import CatalogRelease, CatalogResolver, ProviderArtifact
from .contracts import (
    ArtifactRef,
    CapabilityDescriptorV2,
    CapabilityResultV2,
    ConsumerIdentity,
    InvocationEnvelope,
    OperationRef,
)

__all__ = [
    "ArtifactRef",
    "CatalogRelease",
    "CatalogResolver",
    "CapabilityDescriptorV2",
    "CapabilityResultV2",
    "ConsumerIdentity",
    "InvocationEnvelope",
    "OperationRef",
    "ProviderArtifact",
]
