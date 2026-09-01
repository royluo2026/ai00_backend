"""Immutable business-governance projections owned by the test Governance Center."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple | list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    frozen = _freeze(value)
    if not isinstance(frozen, Mapping):
        raise TypeError("expected a mapping")
    return frozen


@dataclass(frozen=True)
class BusinessPurposeRecord:
    purpose_gid: int
    capability_version_gid: int
    definition_hash: str
    business_effect: str
    acceptance_criteria: tuple[str, ...]
    evidence_snapshot_gid: int
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "acceptance_criteria", tuple(self.acceptance_criteria))


@dataclass(frozen=True)
class BusinessRuleRecord:
    business_rule_gid: int
    capability_version_gid: int
    definition_hash: str
    rule_id: str
    rule_version: int
    statement: str
    applies_when: str
    enforcement_ref: str
    error_code: str
    test_refs: tuple[str, ...]
    evidence_snapshot_gid: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "test_refs", tuple(self.test_refs))


@dataclass(frozen=True)
class CapabilityFingerprint:
    owner_domain: str
    business_object: str
    action: str
    business_effect: str
    input_schema_hash: str
    output_schema_hash: str
    provider_ref: str
    read_scope: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "read_scope", tuple(self.read_scope))
        object.__setattr__(self, "write_scope", tuple(self.write_scope))
        object.__setattr__(self, "rule_ids", tuple(self.rule_ids))


@dataclass(frozen=True)
class CapabilityRelationCandidate:
    relation_candidate_gid: int
    snapshot_gid: int
    candidate_hash: str
    relation_type: Literal["duplicate", "coverage", "conflict", "boundary_overlap"]
    source: Literal["deterministic", "advisory"]
    capability_keys: tuple[str, ...]
    evidence: Mapping[str, object] = field(default_factory=dict)
    status: str = "pending_review"

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_keys", tuple(self.capability_keys))
        object.__setattr__(self, "evidence", _frozen_mapping(self.evidence))


@dataclass(frozen=True)
class CapabilityMaturity:
    level: Literal["L0", "L1", "L2", "L3", "L4", "L5", "L6"]
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))


@dataclass(frozen=True)
class CapabilityBusinessProjection:
    purpose: BusinessPurposeRecord
    rules: tuple[BusinessRuleRecord, ...]
    fingerprint: CapabilityFingerprint
    maturity: CapabilityMaturity
    relation_candidates: tuple[CapabilityRelationCandidate, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(self.rules))
        object.__setattr__(self, "relation_candidates", tuple(self.relation_candidates))


@dataclass(frozen=True)
class CapabilityBusinessReview:
    review_gid: int
    capability_version_gid: int
    definition_hash: str
    decision: Literal["approved", "rejected", "changes_requested"]
    decision_reason: str
    reviewer_gid: str
    reviewer_role: str
    decided_at: datetime
    proposal_gid: int
    evidence_snapshot_gid: int


@dataclass(frozen=True)
class RuleEffectivenessRecord:
    effectiveness_gid: int
    capability_version_gid: int
    definition_hash: str
    metric_name: str
    metric_value: int
    evidence: Mapping[str, object]
    measured_from: datetime
    measured_to: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _frozen_mapping(self.evidence))


__all__ = [
    "BusinessPurposeRecord",
    "BusinessRuleRecord",
    "CapabilityBusinessProjection",
    "CapabilityBusinessReview",
    "CapabilityFingerprint",
    "CapabilityMaturity",
    "CapabilityRelationCandidate",
    "RuleEffectivenessRecord",
]
