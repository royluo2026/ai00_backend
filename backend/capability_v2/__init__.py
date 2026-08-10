"""Capability V2 contracts and migration services."""

from .catalog import CatalogRelease, CatalogResolver, ProviderArtifact
from .delegation import DelegationGrant, SqlDelegationStore
from .identity import AuthenticatedPrincipal, IdentityBroker
from .gateway import CapabilityGatewayService
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
    "AuthenticatedPrincipal",
    "CatalogRelease",
    "CatalogResolver",
    "CapabilityDescriptorV2",
    "CapabilityGatewayService",
    "CapabilityResultV2",
    "ConsumerIdentity",
    "DelegationGrant",
    "IdentityBroker",
    "InvocationEnvelope",
    "OperationRef",
    "ProviderArtifact",
    "SqlDelegationStore",
]
