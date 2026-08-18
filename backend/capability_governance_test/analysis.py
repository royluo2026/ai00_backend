"""Bounded deterministic cross-domain analysis over immutable snapshots."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from .fingerprint import canonical_fingerprint
from .graph import ImplementationGraph
from .models import ScannedCapability, SnapshotDocument
from .rules import FindingCandidate, FindingSubject, RULES


_MAX_CANDIDATES = 5000
_MAX_SUBJECTS_PER_FINDING = 20


@dataclass(frozen=True)
class AnalysisRequest:
    max_candidates: int = _MAX_CANDIDATES
    max_subjects_per_finding: int = _MAX_SUBJECTS_PER_FINDING


@dataclass(frozen=True)
class AnalysisResult:
    status: str
    findings: tuple[FindingCandidate, ...]
    candidate_count: int
    operation_count: int


def _value(descriptor: Mapping[str, object], key: str, fallback: str = "") -> str:
    value = descriptor.get(key, fallback)
    return str(value).strip().lower().replace("-", "_")


def _business_object(capability: ScannedCapability) -> str:
    explicit = _value(capability.descriptor, "business_object")
    if explicit:
        return explicit
    parts = capability.capability_id.split(".")
    return ".".join(parts[1:-1]) if len(parts) > 2 else capability.capability_id


def _operation_family(capability: ScannedCapability) -> str:
    explicit = _value(capability.descriptor, "operation_family")
    return explicit or capability.capability_id.rsplit(".", 1)[-1].lower()


def _permission_family(capability: ScannedCapability) -> str:
    value = capability.descriptor.get("authorization_policy", {})
    if isinstance(value, Mapping):
        return _value(value, "family") or canonical_fingerprint(value)
    return str(value).strip().lower()


def _semantic_block(capability: ScannedCapability) -> tuple[str, str, tuple[str, str, str], str, str, str]:
    descriptor = capability.descriptor
    return (
        _business_object(capability), _operation_family(capability),
        (capability.input_schema_hash, capability.output_schema_hash, capability.error_schema_hash),
        _value(descriptor, "side_effect_level", capability.semantic_class),
        _value(descriptor, "consistency_policy"), _permission_family(capability),
    )


def _subjects(left: ScannedCapability, right: ScannedCapability) -> tuple[FindingSubject, FindingSubject]:
    return tuple(sorted((
        FindingSubject(left.capability_id, left.major_version, "conflicting_capability", f"capability:{left.capability_id}@{left.major_version}"),
        FindingSubject(right.capability_id, right.major_version, "conflicting_capability", f"capability:{right.capability_id}@{right.major_version}"),
    )))  # type: ignore[return-value]


def _semantic_findings(snapshot: SnapshotDocument, request: AnalysisRequest) -> tuple[str, tuple[FindingCandidate, ...], int, int]:
    if request.max_candidates < 0 or request.max_candidates > _MAX_CANDIDATES or request.max_subjects_per_finding < 1 or request.max_subjects_per_finding > _MAX_SUBJECTS_PER_FINDING:
        return "analysis_budget_exceeded", (), 0, 0
    blocks: dict[tuple[str, str, tuple[str, str, str], str, str, str], list[ScannedCapability]] = defaultdict(list)
    for capability in sorted(snapshot.capabilities, key=lambda item: (item.capability_id, item.major_version)):
        blocks[_semantic_block(capability)].append(capability)
    candidates = 0
    operations = 0
    findings: list[FindingCandidate] = []
    for values in blocks.values():
        for offset, left in enumerate(values):
            for right in values[offset + 1:]:
                if left.owner_domain == right.owner_domain:
                    continue
                candidates += 1
                operations += 1
                if candidates > request.max_candidates:
                    return "analysis_budget_exceeded", (), candidates, operations
                subjects = _subjects(left, right)
                if len(subjects) > request.max_subjects_per_finding:
                    return "analysis_budget_exceeded", (), candidates, operations
                if left.policy_hash != right.policy_hash:
                    findings.append(FindingCandidate("cross_domain_conflict", "blocking", subjects,
                        tuple(subject.evidence_key for subject in subjects), "cross_domain_policy_boundary"))
    return "ok", tuple(sorted(set(findings), key=lambda item: item.fingerprint)), candidates, operations


def run_deterministic_analysis(snapshot: SnapshotDocument, request: AnalysisRequest) -> AnalysisResult:
    """Run every pure release rule and bounded semantic analysis without mutation."""
    graph = ImplementationGraph(snapshot.nodes, snapshot.relations, snapshot.bindings)
    status, semantic, candidates, operations = _semantic_findings(snapshot, request)
    if status != "ok":
        return AnalysisResult(status, (), candidates, operations)
    findings = [finding for rule in RULES for finding in rule(snapshot, graph)]
    findings.extend(semantic)
    bounded = tuple(sorted(set(findings), key=lambda item: (item.code, item.fingerprint)))
    if any(len(finding.subjects) > request.max_subjects_per_finding for finding in bounded):
        return AnalysisResult("analysis_budget_exceeded", (), candidates, operations)
    return AnalysisResult("ok", bounded, candidates, operations)


__all__ = ["AnalysisRequest", "AnalysisResult", "run_deterministic_analysis"]
