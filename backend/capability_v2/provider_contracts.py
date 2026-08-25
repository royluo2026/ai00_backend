"""Public provider-side contracts for independently deployable domains.

The implementation currently delegates to the reviewed V1 provider records
during migration. Domain packages import this shared-kernel surface only; the
legacy module remains an internal compatibility detail.
"""
from backend.capabilities.models_next import (
    CapabilityBusinessError,
    CapabilityCollectionPolicy,
    CapabilityContext,
    CapabilityExecutionBudget,
    CapabilityMemoryClass,
    CapabilityOutput,
    CapabilityRisk,
    CapabilitySpec,
    EvidenceRef,
)

__all__ = [
    "CapabilityBusinessError",
    "CapabilityCollectionPolicy",
    "CapabilityContext",
    "CapabilityExecutionBudget",
    "CapabilityMemoryClass",
    "CapabilityOutput",
    "CapabilityRisk",
    "CapabilitySpec",
    "EvidenceRef",
]
