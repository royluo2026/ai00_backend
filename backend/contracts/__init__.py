"""Stable public contracts shared across AI00 product domains."""

from .craft_execution_plan_v1 import (
    CONTRACT_ID as CRAFT_EXECUTION_PLAN_CONTRACT_ID,
    CONTRACT_VERSION as CRAFT_EXECUTION_PLAN_CONTRACT_VERSION,
    ContractValidationError,
    CraftExecutionStructureV1,
    compute_content_hash,
    seal_execution_plan,
    validate_execution_plan,
)
from .connector_execution_plan_v2 import (
    ConnectorExecutionPlanV2,
    ConnectorPlanOutcomeV2,
    canonicalize_v2,
    compute_plan_hash,
    verify_outcome_signature,
    verify_plan_signature,
)

__all__ = [
    "CRAFT_EXECUTION_PLAN_CONTRACT_ID",
    "CRAFT_EXECUTION_PLAN_CONTRACT_VERSION",
    "ContractValidationError",
    "ConnectorExecutionPlanV2",
    "ConnectorPlanOutcomeV2",
    "CraftExecutionStructureV1",
    "compute_content_hash",
    "canonicalize_v2",
    "compute_plan_hash",
    "seal_execution_plan",
    "validate_execution_plan",
    "verify_outcome_signature",
    "verify_plan_signature",
]
