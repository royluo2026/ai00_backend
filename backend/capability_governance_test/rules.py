"""Pure, deterministic release rules for immutable capability snapshots."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Callable

from .fingerprint import canonical_fingerprint
from .graph import ImplementationGraph
from .models import ImplementationNode, ScannedCapability, SnapshotDocument


@dataclass(frozen=True, order=True)
class FindingSubject:
    """One immutable capability or graph artifact affected by a finding."""

    capability_id: str = ""
    major_version: int = 0
    role: str = ""
    evidence_key: str = ""


@dataclass(frozen=True)
class FindingCandidate:
    """A portable, deduplicated finding before persistence assigns any GIDs."""

    code: str
    severity: str
    subjects: tuple[FindingSubject, ...] = ()
    evidence_keys: tuple[str, ...] = ()
    remediation_boundary: str = ""
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        subjects = tuple(sorted(set(self.subjects)))
        evidence = tuple(sorted(set(str(value) for value in self.evidence_keys)))
        object.__setattr__(self, "subjects", subjects)
        object.__setattr__(self, "evidence_keys", evidence)
        object.__setattr__(self, "fingerprint", finding_fingerprint(
            self.code, self.severity, subjects, evidence, self.remediation_boundary,
        ))


def finding_fingerprint(
    finding_or_code: FindingCandidate | str,
    severity: str | None = None,
    subjects: Iterable[FindingSubject] = (),
    evidence_keys: Iterable[str] = (),
    remediation_boundary: str = "",
) -> str:
    """Return a stable finding identity independent of scan or traversal order."""
    if isinstance(finding_or_code, FindingCandidate):
        return finding_or_code.fingerprint
    return canonical_fingerprint({
        "code": finding_or_code,
        "severity": severity or "",
        "subjects": [subject.__dict__ for subject in sorted(set(subjects))],
        "evidence_keys": sorted(set(str(value) for value in evidence_keys)),
        "remediation_boundary": remediation_boundary,
    })


def _capability_subject(capability: ScannedCapability, role: str = "capability") -> FindingSubject:
    return FindingSubject(capability.capability_id, capability.major_version, role, _capability_key(capability))


def _node_subject(node: ImplementationNode, role: str) -> FindingSubject:
    return FindingSubject("", 0, role, node.canonical_key)


def _capability_key(capability: ScannedCapability) -> str:
    return f"capability:{capability.capability_id}@{capability.major_version}"


def _index(snapshot: SnapshotDocument) -> tuple[
    dict[tuple[str, int], ScannedCapability], dict[tuple[str, int], tuple[ImplementationNode, ...]],
    dict[str, ImplementationNode], dict[str, tuple[ImplementationNode, ...]],
]:
    capabilities = {(item.capability_id, item.major_version): item for item in snapshot.capabilities}
    nodes = {item.canonical_key: item for item in snapshot.nodes}
    bound: dict[tuple[str, int], list[ImplementationNode]] = defaultdict(list)
    for binding in snapshot.bindings:
        node = nodes.get(binding.node_canonical_key)
        if node:
            bound[(binding.capability_id, binding.major_version)].append(node)
    outgoing: dict[str, list[ImplementationNode]] = defaultdict(list)
    for relation in snapshot.relations:
        target = nodes.get(relation.to_canonical_key)
        if target:
            outgoing[relation.from_canonical_key].append(target)
    return (
        capabilities,
        {key: tuple(sorted(value, key=lambda node: node.canonical_key)) for key, value in bound.items()},
        nodes,
        {key: tuple(sorted(value, key=lambda node: node.canonical_key)) for key, value in outgoing.items()},
    )


def _bindings(snapshot: SnapshotDocument, capability: ScannedCapability, binding_type: str) -> tuple[str, ...]:
    return tuple(sorted(binding.node_canonical_key for binding in snapshot.bindings if (
        binding.capability_id == capability.capability_id
        and binding.major_version == capability.major_version
        and binding.binding_type == binding_type
    )))


def _policy(value: object) -> str:
    return canonical_fingerprint(value) if value is not None else ""


def _is_strong_write(capability: ScannedCapability) -> bool:
    level = str(capability.descriptor.get("side_effect_level", capability.semantic_class)).lower()
    return level in {"strong_write", "strong-write", "strong"}


def descriptor_without_provider(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    """Every declared capability needs exact provider binding evidence."""
    return tuple(FindingCandidate("provider_missing", "blocking", (_capability_subject(capability),),
        (_capability_key(capability),), "provider_registration_boundary") for capability in snapshot.capabilities
        if not _bindings(snapshot, capability, "implemented_by"))


def provider_without_descriptor(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    """A provider node cannot become a release capability without a descriptor."""
    _, bound, _, _ = _index(snapshot)
    linked = {node.canonical_key for nodes in bound.values() for node in nodes}
    return tuple(FindingCandidate("provider_without_descriptor", "warning", (_node_subject(node, "provider"),),
        (node.canonical_key,), "catalog_descriptor_boundary") for node in snapshot.nodes
        if node.node_type == "provider" and node.canonical_key not in linked)


def exposure_without_capability(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    """Public entrypoints require a capability exposure binding."""
    exposure_types = {"gateway", "rest_route", "legacy_api", "mount_binding", "agent_tool", "mcp_tool"}
    linked = {binding.node_canonical_key for binding in snapshot.bindings if binding.binding_type == "exposed_by"}
    return tuple(FindingCandidate("exposure_without_capability", "blocking", (_node_subject(node, "exposure"),),
        (node.canonical_key,), "capability_exposure_boundary") for node in snapshot.nodes
        if node.node_type in exposure_types and node.canonical_key not in linked)


def strong_write_without_transactional_provider(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    """Strong writes must name a transactional provider participant."""
    nodes = {node.canonical_key: node for node in snapshot.nodes}
    findings: list[FindingCandidate] = []
    for capability in snapshot.capabilities:
        if not _is_strong_write(capability):
            continue
        providers = [nodes[key] for key in _bindings(snapshot, capability, "implemented_by") if key in nodes]
        if providers and not any(bool(provider.metadata.get("transactional") or provider.metadata.get("transaction_participant")) for provider in providers):
            findings.append(FindingCandidate("transaction_participant_missing", "blocking", (_capability_subject(capability),),
                tuple([_capability_key(capability), *(provider.canonical_key for provider in providers)]),
                "provider_transaction_boundary"))
    return tuple(findings)


def repository_table_migration_mismatch(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    """Every repository persistence target must be covered by a migration edge."""
    nodes = {node.canonical_key: node for node in snapshot.nodes}
    migrated = {relation.to_canonical_key for relation in snapshot.relations if relation.relation_type == "migrates_table"}
    findings: list[FindingCandidate] = []
    for relation in snapshot.relations:
        repository, table = nodes.get(relation.from_canonical_key), nodes.get(relation.to_canonical_key)
        if relation.relation_type != "persists_to" or not repository or not table or table.canonical_key in migrated:
            continue
        findings.append(FindingCandidate("repository_table_migration_mismatch", "blocking", (_node_subject(repository, "repository"), _node_subject(table, "database_table")),
            (repository.canonical_key, table.canonical_key), "database_migration_boundary"))
    return tuple(sorted(findings, key=lambda item: item.fingerprint))


def _provider_policy_mismatches(snapshot: SnapshotDocument, descriptor_key: str, metadata_key: str, code: str, boundary: str) -> tuple[FindingCandidate, ...]:
    nodes = {node.canonical_key: node for node in snapshot.nodes}
    findings: list[FindingCandidate] = []
    for capability in snapshot.capabilities:
        expected = capability.descriptor.get(descriptor_key)
        if expected is None:
            continue
        for key in _bindings(snapshot, capability, "implemented_by"):
            provider = nodes.get(key)
            actual = provider.metadata.get(metadata_key) if provider else None
            if actual is not None and _policy(actual) != _policy(expected):
                findings.append(FindingCandidate(code, "blocking", (_capability_subject(capability), _node_subject(provider, "provider")),
                    (_capability_key(capability), provider.canonical_key), boundary))
    return tuple(findings)


def permission_policy_mismatch(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    return _provider_policy_mismatches(snapshot, "authorization_policy", "authorization_policy", "permission_policy_mismatch", "authorization_boundary")


def confirmation_policy_mismatch(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    return _provider_policy_mismatches(snapshot, "confirmation_policy", "confirmation_policy", "confirmation_policy_mismatch", "confirmation_boundary")


def catalog_schema_drift(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    """Provider-declared schema hashes must agree with the immutable Catalog."""
    nodes = {node.canonical_key: node for node in snapshot.nodes}
    fields = {"input_schema_hash": "input_schema_hash", "output_schema_hash": "output_schema_hash", "error_schema_hash": "error_schema_hash"}
    findings: list[FindingCandidate] = []
    for capability in snapshot.capabilities:
        for key in _bindings(snapshot, capability, "implemented_by"):
            provider = nodes.get(key)
            if provider and any(str(provider.metadata.get(metadata)) not in {"", str(getattr(capability, field))} for metadata, field in fields.items()):
                findings.append(FindingCandidate("catalog_schema_drift", "blocking", (_capability_subject(capability), _node_subject(provider, "provider")),
                    (_capability_key(capability), provider.canonical_key), "catalog_schema_boundary"))
    return tuple(findings)


def required_test_missing(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    return tuple(FindingCandidate("required_test_missing", "blocking", (_capability_subject(capability),),
        (_capability_key(capability),), "release_evidence_boundary") for capability in snapshot.capabilities
        if not _bindings(snapshot, capability, "tested_by"))


def stale_evidence(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    return tuple(FindingCandidate("stale_evidence", "blocking", (_node_subject(node, "evidence"),), (node.canonical_key,), "evidence_refresh_boundary")
        for node in snapshot.nodes if not node.artifact_hash or bool(node.metadata.get("stale")))


def lifecycle_incompatibility(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    nodes = {node.canonical_key: node for node in snapshot.nodes}
    findings: list[FindingCandidate] = []
    for capability in snapshot.capabilities:
        for key in _bindings(snapshot, capability, "implemented_by"):
            provider = nodes.get(key)
            actual = str(provider.metadata.get("lifecycle_status", "")) if provider else ""
            if actual and actual != capability.lifecycle_status:
                findings.append(FindingCandidate("lifecycle_incompatibility", "blocking", (_capability_subject(capability), _node_subject(provider, "provider")),
                    (_capability_key(capability), provider.canonical_key), "lifecycle_release_boundary"))
    return tuple(findings)


def production_governance_artifact_present(snapshot: SnapshotDocument, graph: ImplementationGraph | None = None) -> tuple[FindingCandidate, ...]:
    return tuple(FindingCandidate("production_governance_artifact_present", "blocking", (_node_subject(node, "production_artifact"),),
        (node.canonical_key,), "production_artifact_boundary") for node in snapshot.nodes
        if "capability_governance_test" in node.source_path.replace("\\", "/"))


Rule = Callable[[SnapshotDocument, ImplementationGraph | None], tuple[FindingCandidate, ...]]
RULES: tuple[Rule, ...] = (
    descriptor_without_provider, provider_without_descriptor, exposure_without_capability,
    strong_write_without_transactional_provider, repository_table_migration_mismatch,
    permission_policy_mismatch, confirmation_policy_mismatch, catalog_schema_drift,
    required_test_missing, stale_evidence, lifecycle_incompatibility,
    production_governance_artifact_present,
)


__all__ = ["FindingCandidate", "FindingSubject", "RULES", "Rule", "finding_fingerprint", *[rule.__name__ for rule in RULES]]
