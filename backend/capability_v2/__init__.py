"""Capability V2 contracts and migration services."""

from .catalog import CatalogRelease, CatalogResolver, ProviderArtifact
from .delegation import DelegationGrant, SqlDelegationStore
from .identity import AuthenticatedPrincipal, IdentityBroker
from .gateway import CapabilityGatewayService
from .authorization import AuthorizationDecision, AuthorizationGrants, CapabilityAuthorizer
from .projection import project_result
from .outcomes import OutcomeRecord, SqlOutcomeStore
from .reliability import (
    ApprovalChallenge,
    ApprovalService,
    ReliabilityCoordinator,
    SqlApprovalStore,
    SqlRateLimiter,
    TransactionalCapabilityOutput,
    transactional_provider,
)
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
    "ApprovalChallenge",
    "ApprovalService",
    "AuthenticatedPrincipal",
    "AuthorizationDecision",
    "AuthorizationGrants",
    "CatalogRelease",
    "CatalogResolver",
    "CapabilityDescriptorV2",
    "CapabilityGatewayService",
    "CapabilityAuthorizer",
    "CapabilityResultV2",
    "ConsumerIdentity",
    "DelegationGrant",
    "IdentityBroker",
    "InvocationEnvelope",
    "OperationRef",
    "OutcomeRecord",
    "ProviderArtifact",
    "SqlDelegationStore",
    "SqlApprovalStore",
    "SqlOutcomeStore",
    "SqlRateLimiter",
    "ReliabilityCoordinator",
    "TransactionalCapabilityOutput",
    "transactional_provider",
    "project_result",
]
