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


def _subject(capability: ScannedCapability, role: str = "capability") -> FindingSubject:
    return FindingSubject(
        capability.capability_id, capability.major_version, role,
        f"capability:{capability.capability_id}@{capability.major_version}",
    )


def _pair_key(capability: ScannedCapability) -> tuple[str, str]:
    return (_business_object(capability), _operation_family(capability))


def _has_lifecycle_pair(capability: ScannedCapability, capabilities: tuple[ScannedCapability, ...]) -> bool:
    descriptor = capability.descriptor
    required = descriptor.get("requires_lifecycle_pair", descriptor.get("lifecycle_pair_required", False))
    if not isinstance(required, bool) or not required:
        return True
    pair = descriptor.get("lifecycle_pair")
    if isinstance(pair, str) and pair.strip():
        pair_names = {pair.strip().lower()}
    elif isinstance(pair, (tuple, list, set, frozenset)):
        pair_names = {str(value).strip().lower() for value in pair if str(value).strip()}
    else:
        pair_names = {"get", "list", "search"} if _operation_family(capability) in {"create", "update", "delete"} else {"create", "update"}
    business_object = _business_object(capability)
    return any(
        other is not capability and _business_object(other) == business_object
        and _operation_family(other) in pair_names
        for other in capabilities
    )


def _structural_findings(snapshot: SnapshotDocument) -> tuple[FindingCandidate, ...]:
    """Return deterministic candidate classes not tied to implementation rules.

    These are deliberately conservative: semantic evidence is derived only
    from declared descriptor fields, never from names alone beyond the
    normalized business object/operation family already declared by a
    descriptor.  The same candidate is fingerprint-deduplicated below.
    """
    capabilities = tuple(sorted(snapshot.capabilities, key=lambda item: (item.capability_id, item.major_version)))
    findings: list[FindingCandidate] = []
    by_pair: dict[tuple[str, str], list[ScannedCapability]] = defaultdict(list)
    for capability in capabilities:
        by_pair[_pair_key(capability)].append(capability)

    for values in by_pair.values():
        for offset, left in enumerate(values):
            for right in values[offset + 1:]:
                if left.owner_domain == right.owner_domain:
                    continue
                subjects = _subjects(left, right)
                evidence = tuple(subject.evidence_key for subject in subjects)
                same_contract = (
                    left.input_schema_hash == right.input_schema_hash
                    and left.output_schema_hash == right.output_schema_hash
                    and left.error_schema_hash == right.error_schema_hash
                    and left.semantic_class == right.semantic_class
                )
                if same_contract and left.policy_hash == right.policy_hash:
                    findings.append(FindingCandidate(
                        "duplicate", "warning", subjects, evidence,
                        "cross_domain_duplicate_boundary",
                    ))
                else:
                    findings.append(FindingCandidate(
                        "semantic_overlap", "warning", subjects, evidence,
                        "cross_domain_semantic_boundary",
                    ))
                if left.policy_hash != right.policy_hash:
                    findings.append(FindingCandidate(
                        "cross_domain_conflict", "blocking", subjects, evidence,
                        "cross_domain_policy_boundary",
                    ))

    for capability in capabilities:
        descriptor = capability.descriptor
        # A missing provider is already a blocking release rule; this compact
        # candidate alias is what Agent advisory contracts consume as a gap.
        # It is generated only from an explicit provider binding check here so
        # the result cannot be forged by an advisory model.
        provider_bound = any(
            binding.capability_id == capability.capability_id
            and binding.major_version == capability.major_version
            and binding.binding_type == "implemented_by"
            for binding in snapshot.bindings
        )
        if not provider_bound:
            findings.append(FindingCandidate(
                "gap", "blocking", (_subject(capability),),
                (f"capability:{capability.capability_id}@{capability.major_version}",),
                "capability_implementation_boundary",
            ))
        if not _has_lifecycle_pair(capability, capabilities):
            findings.append(FindingCandidate(
                "lifecycle_pair_gap", "warning", (_subject(capability),),
                (f"capability:{capability.capability_id}@{capability.major_version}",),
                "capability_lifecycle_boundary",
            ))
        provider_keys = tuple(
            binding.node_canonical_key for binding in snapshot.bindings
            if binding.capability_id == capability.capability_id
            and binding.major_version == capability.major_version
            and binding.binding_type == "implemented_by"
        )
        facade = bool(descriptor.get("facade") or descriptor.get("aggregate_facade") or descriptor.get("non_atomic_facade"))
        if facade and len(provider_keys) > 1:
            nodes = {node.canonical_key: node for node in snapshot.nodes}
            transactional = any(
                bool(nodes.get(key) and (nodes[key].metadata.get("transactional") or nodes[key].metadata.get("transaction_participant")))
                for key in provider_keys
            )
            if not transactional:
                subjects = tuple(sorted((_subject(capability),) + tuple(
                    FindingSubject("", 0, "provider", key) for key in provider_keys
                )))
                findings.append(FindingCandidate(
                    "non_atomic_facade", "blocking", subjects,
                    tuple([f"capability:{capability.capability_id}@{capability.major_version}", *provider_keys]),
                    "facade_transaction_boundary",
                ))
    return tuple(sorted(set(findings), key=lambda item: (item.code, item.fingerprint)))


def _semantic_findings(snapshot: SnapshotDocument, request: AnalysisRequest) -> tuple[str, tuple[FindingCandidate, ...], int, int]:
    if request.max_candidates < 0 or request.max_candidates > _MAX_CANDIDATES or request.max_subjects_per_finding < 1 or request.max_subjects_per_finding > _MAX_SUBJECTS_PER_FINDING:
        return "analysis_budget_exceeded", (), 0, 0
    blocks: dict[tuple[str, str], list[ScannedCapability]] = defaultdict(list)
    for capability in sorted(snapshot.capabilities, key=lambda item: (item.capability_id, item.major_version)):
        blocks[_pair_key(capability)].append(capability)
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
                same_contract = (
                    left.input_schema_hash == right.input_schema_hash
                    and left.output_schema_hash == right.output_schema_hash
                    and left.error_schema_hash == right.error_schema_hash
                    and left.semantic_class == right.semantic_class
                )
                if same_contract and left.policy_hash == right.policy_hash:
                    code, severity, boundary = "duplicate", "warning", "cross_domain_duplicate_boundary"
                else:
                    code, severity, boundary = "semantic_overlap", "warning", "cross_domain_semantic_boundary"
                findings.append(FindingCandidate(code, severity, subjects,
                    tuple(subject.evidence_key for subject in subjects), boundary))
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
    findings.extend(_structural_findings(snapshot))
    findings.extend(semantic)
    bounded = tuple(sorted(set(findings), key=lambda item: (item.code, item.fingerprint)))
    if any(len(finding.subjects) > request.max_subjects_per_finding for finding in bounded):
        return AnalysisResult("analysis_budget_exceeded", (), candidates, operations)
    return AnalysisResult("ok", bounded, candidates, operations)


__all__ = ["AnalysisRequest", "AnalysisResult", "run_deterministic_analysis"]
