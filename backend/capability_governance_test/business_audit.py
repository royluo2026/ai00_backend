"""Read-only seven-layer aggregation over existing governance evidence."""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
import re
from types import MappingProxyType
from typing import Any

from .redaction import redact


LAYERS = tuple("ABCDEFG")
MATURITY_LEVELS = tuple(f"L{index}" for index in range(7))
_SHA = re.compile(r"[0-9a-f]{40}")
_UNBOUND_TYPES = {
    "rest_route": "REST route",
    "legacy_api": "REST route",
    "provider": "Provider",
    "worker": "worker",
    "mcp_tool": "MCP",
    "agent_tool": "Agent Tool",
}
_STATE_ACTIONS = {"approve", "authorize", "delete", "publish", "reject", "retire", "transition"}


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): item for key, item in value.items()})


def _value(record: Any, name: str, default: Any = None) -> Any:
    return record.get(name, default) if isinstance(record, Mapping) else getattr(record, name, default)


def _json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {item.name: _json(getattr(value, item.name)) for item in fields(value)}
    return value


def root_cause_key(reason_code: str, capability_id: str, major: int, rule_id: str | None) -> str:
    suffix = f":{rule_id}" if rule_id else ""
    return f"{reason_code}:{capability_id}@{major}{suffix}"


@dataclass(frozen=True)
class AuditCapability:
    capability_id: str
    major_version: int
    domain: str
    maturity: str
    layer_evidence: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    capability_version_gid: str = ""
    semantic_class: str = ""
    change_kind: str = ""
    governance_status: str = ""

    def __post_init__(self) -> None:
        if self.maturity not in MATURITY_LEVELS:
            raise ValueError("business_audit_maturity_invalid")
        normalized = {
            layer: tuple(str(item) for item in self.layer_evidence.get(layer, ()) if str(item))
            for layer in LAYERS
        }
        object.__setattr__(self, "layer_evidence", _freeze_mapping(normalized))
        object.__setattr__(self, "reason_codes", tuple(str(item) for item in self.reason_codes if str(item)))

    @property
    def capability_key(self) -> str:
        return f"{self.capability_id}@{self.major_version}"


@dataclass(frozen=True)
class AuditEvidence:
    reason_code: str
    capability_id: str
    major_version: int
    domain: str
    layer: str
    evidence_ref: str
    remediation_family: str
    severity: str = "warning"
    rule_id: str | None = None
    related_capability_keys: tuple[str, ...] = ()
    related_domains: tuple[str, ...] = ()

    @property
    def capability_key(self) -> str:
        return f"{self.capability_id}@{self.major_version}"

    @property
    def group_key(self) -> str:
        if self.reason_code in {"cross_domain_conflict", "conflict"} and self.related_capability_keys:
            capability_id, major = _split_capability_key(min(self.related_capability_keys))
            return root_cause_key(self.reason_code, capability_id, major, self.rule_id)
        return root_cause_key(self.reason_code, self.capability_id, self.major_version, self.rule_id)


@dataclass(frozen=True)
class RootCauseGroup:
    root_cause_key: str
    reason_code: str
    capability_keys: tuple[str, ...]
    domains: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    finding_count: int
    remediation_family: str
    severity: str


@dataclass(frozen=True)
class AuditRelation:
    candidate_hash: str
    relation_type: str
    source: str
    capability_keys: tuple[str, ...]
    evidence: Mapping[str, Any]
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_keys", tuple(sorted(str(item) for item in self.capability_keys)))
        safe = redact(dict(self.evidence)) if isinstance(self.evidence, Mapping) else {}
        object.__setattr__(self, "evidence", _freeze_mapping(safe))


@dataclass(frozen=True)
class UnboundPublicEntry:
    entry_type: str
    canonical_key: str
    domain: str
    source_path: str
    source_symbol: str
    http_method: str | None = None
    route_path: str | None = None


@dataclass(frozen=True)
class ReviewQueueEntry:
    capability_key: str
    domain: str
    maturity: str
    priority: int
    reason: str


@dataclass(frozen=True)
class BusinessAuditReport:
    snapshot_gid: str
    source_revisions: Mapping[str, str]
    maturity_counts: Mapping[str, int]
    maturity_evidence: Mapping[str, tuple[str, ...]]
    layer_counts: Mapping[str, int]
    layer_evidence: Mapping[str, Mapping[str, tuple[str, ...]]]
    finding_count: int
    root_cause_group_count: int
    affected_capability_count: int
    affected_capabilities: tuple[str, ...]
    affected_domains: tuple[str, ...]
    shared_remediation_family_count: int
    shared_remediation_families: Mapping[str, int]
    findings: tuple[AuditEvidence, ...]
    root_causes: tuple[RootCauseGroup, ...]
    relations: tuple[AuditRelation, ...]
    unbound_entries: tuple[UnboundPublicEntry, ...]
    review_queue: tuple[ReviewQueueEntry, ...]
    machine_passed: bool
    human_approved: bool
    runtime_verified: bool
    legacy_pending_review_count: int

    def to_dict(self) -> dict[str, Any]:
        return _json(self)


def _split_capability_key(key: str) -> tuple[str, int]:
    capability_id, separator, raw_major = str(key).rpartition("@")
    if not separator or not capability_id:
        raise ValueError("business_audit_capability_key_invalid")
    return capability_id, int(raw_major)


def _effective_maturity(capability: AuditCapability, gate_row: Any | None, relations: tuple[AuditRelation, ...]) -> str:
    level = int(capability.maturity[1])
    related = tuple(item for item in relations if capability.capability_key in item.capability_keys)
    relations_dispositioned = all(item.status not in {"", "pending_review"} for item in related)
    if level >= 3 and gate_row is not None and bool(_value(gate_row, "machine_passed", False)) and relations_dispositioned:
        level = 4
    if level >= 4 and bool(_value(gate_row, "human_approved", False)) and str(_value(gate_row, "governance_status", "")) == "passed":
        level = 5
    if level >= 5 and bool(_value(gate_row, "runtime_verified", False)):
        level = 6
    return f"L{level}"


def _review_queue(capabilities: tuple[AuditCapability, ...], relations: tuple[AuditRelation, ...]) -> tuple[ReviewQueueEntry, ...]:
    conflict_keys = {
        key for relation in relations if relation.relation_type == "conflict"
        for key in relation.capability_keys
    }
    queued: list[ReviewQueueEntry] = []
    for item in capabilities:
        if item.maturity in {"L5", "L6"}:
            continue
        action = item.capability_id.rsplit(".", 1)[-1]
        write = item.semantic_class in {"write", "high_risk_write"}
        missing_rule = any(code in {"business_rules_missing", "business_rule_evidence_incomplete"} for code in item.reason_codes)
        if write and missing_rule:
            priority, reason = 1, "write_without_proven_business_rule"
        elif action in _STATE_ACTIONS:
            priority, reason = 2, "state_transition_or_authority_operation"
        elif item.capability_key in conflict_keys:
            priority, reason = 3, "relationship_conflict_pending_review"
        elif write:
            priority, reason = 5, "write_pending_review"
        else:
            priority, reason = 6, "read_pending_review"
        queued.append(ReviewQueueEntry(item.capability_key, item.domain, item.maturity, priority, reason))
    return tuple(sorted(queued, key=lambda item: (item.priority, item.domain, item.capability_key)))


def audit(
    findings: Iterable[AuditEvidence], *, capabilities: Iterable[AuditCapability] = (),
    snapshot_gid: str, source_revisions: Mapping[str, str] | None = None,
    relations: Iterable[AuditRelation] = (), unbound_entries: Iterable[UnboundPublicEntry] = (),
    gate_result: Any | None = None,
) -> BusinessAuditReport:
    evidence_rows = tuple(findings)
    relation_rows = tuple(sorted(relations, key=lambda item: (item.relation_type, item.capability_keys, item.candidate_hash)))
    gate_rows = {
        str(_value(item, "capability_key", "")): item
        for item in tuple(_value(gate_result, "capabilities", ()) or ())
    }
    capability_rows = tuple(sorted((
        AuditCapability(
            capability_id=item.capability_id, major_version=item.major_version, domain=item.domain,
            maturity=_effective_maturity(item, gate_rows.get(item.capability_key), relation_rows),
            layer_evidence=item.layer_evidence, reason_codes=item.reason_codes,
            capability_version_gid=item.capability_version_gid, semantic_class=item.semantic_class,
            change_kind=str(_value(gate_rows.get(item.capability_key), "change_kind", item.change_kind)),
            governance_status=str(_value(gate_rows.get(item.capability_key), "governance_status", item.governance_status)),
        ) for item in capabilities
    ), key=lambda item: item.capability_key))

    maturity_evidence = {
        level: tuple(item.capability_key for item in capability_rows if item.maturity == level)
        for level in MATURITY_LEVELS
    }
    layer_evidence = {
        layer: {
            item.capability_key: item.layer_evidence[layer]
            for item in capability_rows if item.layer_evidence[layer]
        }
        for layer in LAYERS
    }
    groups: dict[str, list[AuditEvidence]] = defaultdict(list)
    for item in evidence_rows:
        groups[item.group_key].append(item)
    root_causes: list[RootCauseGroup] = []
    for key, values in sorted(groups.items()):
        capability_keys = {
            related for value in values for related in (value.related_capability_keys or (value.capability_key,))
        }
        domains = {domain for value in values for domain in (value.related_domains or (value.domain,)) if domain}
        severity = max((value.severity for value in values), key=lambda item: {"blocking": 4, "critical": 3, "error": 2, "warning": 1}.get(item.lower(), 0))
        root_causes.append(RootCauseGroup(
            key, values[0].reason_code, tuple(sorted(capability_keys)), tuple(sorted(domains)),
            tuple(sorted({value.evidence_ref for value in values if value.evidence_ref})), len(values),
            values[0].remediation_family, severity,
        ))
    affected_capabilities = tuple(sorted({key for group in root_causes for key in group.capability_keys}))
    affected_domains = tuple(sorted({domain for group in root_causes for domain in group.domains}))
    remediation_counts = dict(sorted(Counter(item.remediation_family for item in evidence_rows if item.remediation_family).items()))
    return BusinessAuditReport(
        snapshot_gid=str(snapshot_gid), source_revisions=_freeze_mapping(dict(source_revisions or {"backend": "", "web": "", "source": ""})),
        maturity_counts=_freeze_mapping({level: len(maturity_evidence[level]) for level in MATURITY_LEVELS}),
        maturity_evidence=_freeze_mapping(maturity_evidence),
        layer_counts=_freeze_mapping({layer: len(layer_evidence[layer]) for layer in LAYERS}),
        layer_evidence=_freeze_mapping({layer: _freeze_mapping(values) for layer, values in layer_evidence.items()}),
        finding_count=len(evidence_rows), root_cause_group_count=len(root_causes),
        affected_capability_count=len(affected_capabilities), affected_capabilities=affected_capabilities,
        affected_domains=affected_domains, shared_remediation_family_count=len(remediation_counts),
        shared_remediation_families=_freeze_mapping(remediation_counts), findings=evidence_rows,
        root_causes=tuple(root_causes), relations=relation_rows,
        unbound_entries=tuple(sorted(unbound_entries, key=lambda item: (item.entry_type, item.canonical_key))),
        review_queue=_review_queue(capability_rows, relation_rows),
        machine_passed=bool(_value(gate_result, "machine_passed", False)),
        human_approved=bool(_value(gate_result, "human_approved", False)),
        runtime_verified=bool(_value(gate_result, "runtime_verified", False)),
        legacy_pending_review_count=int(_value(gate_result, "legacy_pending_review_count", 0) or 0),
    )


def _page(service: Any, method_name: str, *, snapshot_gid: str, item_key: str, limit: int) -> tuple[Any, ...]:
    if limit < 1 or limit > 200:
        raise ValueError("business_audit_page_limit_invalid")
    offset, total = 0, 1
    items: list[Any] = []
    method = getattr(service, method_name)
    while offset < total:
        payload = {"limit": limit, "offset": offset}
        payload["snapshot_gid" if method_name.endswith("registry_search") else "target_gid"] = snapshot_gid
        result = method(payload, None)
        page = tuple(_value(result, item_key, ()) or ())
        total = int(_value(result, "total", 0) or 0)
        items.extend(page)
        offset += limit
    return tuple(items)


def _capability_from_projection(item: Any) -> AuditCapability:
    contract = _value(item, "contract", {}) or {}
    maturity = _value(contract, "business_maturity", {}) or {}
    return AuditCapability(
        capability_id=str(_value(item, "capability_id", "")),
        major_version=int(_value(item, "major_version", 0) or 0),
        domain=str(_value(item, "owner_domain", _value(item, "domain", ""))),
        maturity=str(_value(maturity, "level", "L0")),
        reason_codes=tuple(_value(maturity, "reason_codes", ()) or ()),
        layer_evidence=_value(contract, "business_layer_evidence", {}) or {},
        capability_version_gid=str(_value(item, "capability_version_gid", "")),
        semantic_class=str(_value(item, "semantic_class", "")),
    )


def collect_business_audit(
    service: Any, *, snapshot_gid: str, source_revisions: Mapping[str, str],
    gate_result: Any | None = None, page_limit: int = 200,
) -> BusinessAuditReport:
    if set(source_revisions) != {"backend", "web", "source"} or any(
        _SHA.fullmatch(str(source_revisions[key])) is None for key in ("backend", "web", "source")
    ):
        raise ValueError("business_audit_source_revision_invalid")
    projection = service.business_audit_snapshot_projection(str(snapshot_gid))
    if str(_value(projection, "snapshot_gid", "")) != str(snapshot_gid):
        raise ValueError("business_audit_snapshot_mismatch")
    if str(_value(projection, "source_revision", "")) != str(source_revisions["source"]):
        raise ValueError("business_audit_source_revision_mismatch")
    registry = _page(service, "base_capability_registry_search", snapshot_gid=str(snapshot_gid), item_key="items", limit=page_limit)
    findings = _page(service, "base_capability_finding_search", snapshot_gid=str(snapshot_gid), item_key="findings", limit=page_limit)
    capabilities = tuple(_capability_from_projection(item) for item in registry)
    by_gid = {item.capability_version_gid: item for item in capabilities if item.capability_version_gid}
    evidence: list[AuditEvidence] = []
    for finding in findings:
        subjects = tuple(by_gid[str(gid)] for gid in tuple(_value(finding, "subject_version_gids", ()) or ()) if str(gid) in by_gid)
        if not subjects:
            continue
        related_keys = tuple(sorted(item.capability_key for item in subjects))
        related_domains = tuple(sorted({item.domain for item in subjects if item.domain}))
        refs = tuple(str(item) for item in tuple(_value(finding, "evidence", ()) or ()) if str(item)) or ("unresolved",)
        for ref in refs:
            primary = subjects[0]
            evidence.append(AuditEvidence(
                reason_code=str(_value(finding, "reason_code", _value(finding, "code", "finding"))),
                capability_id=primary.capability_id, major_version=primary.major_version,
                domain=primary.domain, layer=str(_value(finding, "layer", "C")), evidence_ref=ref,
                remediation_family=str(_value(finding, "remediation_boundary", "manual_review")),
                severity=str(_value(finding, "severity", "warning")),
                rule_id=(str(_value(finding, "rule_id")) if _value(finding, "rule_id") else None),
                related_capability_keys=related_keys, related_domains=related_domains,
            ))
    for capability in capabilities:
        for reason in capability.reason_codes:
            if any(item.reason_code == reason and capability.capability_key in item.related_capability_keys for item in evidence):
                continue
            evidence.append(AuditEvidence(
                reason, capability.capability_id, capability.major_version, capability.domain,
                _reason_layer(reason), reason, _remediation_family(reason),
                related_capability_keys=(capability.capability_key,), related_domains=(capability.domain,),
            ))
    relations = tuple(AuditRelation(
        candidate_hash=str(_value(item, "candidate_hash", "")), relation_type=str(_value(item, "relation_type", "")),
        source=str(_value(item, "source", "")), capability_keys=tuple(_value(item, "capability_keys", ()) or ()),
        evidence=_value(item, "evidence", {}) or {}, status=str(_value(item, "status", "pending_review")),
    ) for item in tuple(_value(projection, "relation_candidates", ()) or ()))
    by_key = {item.capability_key: item for item in capabilities}
    for relation in relations:
        if relation.source != "deterministic" or relation.relation_type != "conflict":
            continue
        related = tuple(key for key in relation.capability_keys if key in by_key)
        related_domains = tuple(sorted({by_key[key].domain for key in related if by_key[key].domain}))
        for key in related:
            capability = by_key[key]
            evidence.append(AuditEvidence(
                "cross_domain_conflict", capability.capability_id, capability.major_version,
                capability.domain, "F", relation.candidate_hash, "resolve_formal_conflict",
                severity="blocking", related_capability_keys=related, related_domains=related_domains,
            ))
    bound = {str(_value(item, "node_canonical_key", "")) for item in tuple(_value(projection, "bindings", ()) or ())}
    unbound = tuple(UnboundPublicEntry(
        _UNBOUND_TYPES[str(_value(node, "node_type"))], str(_value(node, "canonical_key", "")),
        str(_value(node, "owner_domain", "")), str(_value(node, "source_path", "")),
        str(_value(node, "source_symbol", "")),
        str(_value(node, "http_method")) if _value(node, "http_method") else None,
        str(_value(node, "route_path")) if _value(node, "route_path") else None,
    ) for node in tuple(_value(projection, "nodes", ()) or ())
        if str(_value(node, "node_type", "")) in _UNBOUND_TYPES
        and str(_value(node, "canonical_key", "")) not in bound)
    return audit(
        evidence, capabilities=capabilities, snapshot_gid=str(snapshot_gid), source_revisions=source_revisions,
        relations=relations, unbound_entries=unbound, gate_result=gate_result,
    )


def _reason_layer(reason: str) -> str:
    if "effect" in reason:
        return "A"
    if "enforcement" in reason:
        return "D"
    if "test" in reason:
        return "E"
    if "relation" in reason or "conflict" in reason:
        return "F"
    if "approval" in reason or "runtime" in reason:
        return "G"
    return "C"


def _remediation_family(reason: str) -> str:
    if "effect" in reason:
        return "declare_business_purpose"
    if "enforcement" in reason:
        return "map_rule_enforcement"
    if "test" in reason:
        return "add_rule_specific_test"
    if "relation" in reason or "conflict" in reason:
        return "review_relationship"
    if "approval" in reason:
        return "obtain_exact_hash_approval"
    if "runtime" in reason:
        return "record_runtime_effectiveness"
    return "declare_business_rule"


__all__ = [
    "AuditCapability", "AuditEvidence", "AuditRelation", "BusinessAuditReport", "ReviewQueueEntry",
    "RootCauseGroup", "UnboundPublicEntry", "audit", "collect_business_audit", "root_cause_key",
]
