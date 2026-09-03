"""Public provider-side contracts for independently deployable domains.

The implementation currently delegates to the reviewed V1 provider records
during migration. Domain packages import this shared-kernel surface only; the
legacy module remains an internal compatibility detail.
"""
from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class CapabilityStreamOutput:
    """Provider stream whose execution lifecycle remains owned by Gateway."""

    iterator: Any
    output: dict[str, Any]
    media_type: str = "text/event-stream"
    max_events: int = 500

__all__ = [
    "CapabilityBusinessError",
    "CapabilityCollectionPolicy",
    "CapabilityContext",
    "CapabilityExecutionBudget",
    "CapabilityMemoryClass",
    "CapabilityOutput",
    "CapabilityRisk",
    "CapabilitySpec",
    "CapabilityStreamOutput",
    "EvidenceRef",
]
