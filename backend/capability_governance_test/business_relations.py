"""Deterministic, narrowed relationship candidates for scanned Capabilities."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from itertools import combinations
from typing import Any

from .business_models import CapabilityRelationCandidate
from .fingerprint import canonical_fingerprint
from .models import ScannedCapability


def _key(item: ScannedCapability) -> str:
    return f"{item.capability_id}@{item.major_version}"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _scopes(item: ScannedCapability) -> tuple[str, ...]:
    fingerprint = item.fingerprint
    if fingerprint is None:
        return ()
    return tuple(sorted(set(fingerprint.read_scope) | set(fingerprint.write_scope)))


def _rules(item: ScannedCapability) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for raw in item.business_rules:
        if not isinstance(raw, Mapping):
            continue
        constraints = raw.get("machine_constraints", raw.get("constraints", {}))
        if not isinstance(constraints, Mapping):
            constraints = {}
        result.append({
            "rule_id": _text(raw.get("rule_id")),
            "version": raw.get("version"),
            "statement": _text(raw.get("statement")),
            "applies_when": _text(raw.get("applies_when")),
            "error_code": _text(raw.get("error_code")),
            "machine_constraints": dict(constraints),
        })
    return tuple(sorted(result, key=canonical_fingerprint))


def _same_contract(left: ScannedCapability, right: ScannedCapability) -> bool:
    left_fingerprint = left.fingerprint
    right_fingerprint = right.fingerprint
    if left_fingerprint is None or right_fingerprint is None:
        return False
    return (
        _text(left_fingerprint.business_effect) == _text(right_fingerprint.business_effect)
        and left_fingerprint.input_schema_hash == right_fingerprint.input_schema_hash
        and left_fingerprint.output_schema_hash == right_fingerprint.output_schema_hash
        and left_fingerprint.read_scope == right_fingerprint.read_scope
        and left_fingerprint.write_scope == right_fingerprint.write_scope
        and _rules(left) == _rules(right)
    )


def candidate_pairs(items: Iterable[ScannedCapability]) -> Iterator[tuple[ScannedCapability, ScannedCapability]]:
    """Yield only same-object/same-action pairs, in canonical order."""
    buckets: dict[tuple[str, str], dict[str, ScannedCapability]] = defaultdict(dict)
    for item in items:
        fingerprint = item.fingerprint
        if fingerprint is None:
            continue
        bucket = (_text(fingerprint.business_object), _text(fingerprint.action))
        if not all(bucket):
            continue
        buckets[bucket].setdefault(_key(item), item)
    for bucket in sorted(buckets):
        values = tuple(sorted(buckets[bucket].values(), key=_key))
        yield from combinations(values, 2)


def _interval(rule: Mapping[str, Any]) -> tuple[str, str, float | None, float | None] | None:
    constraints = rule.get("machine_constraints")
    if not isinstance(constraints, Mapping):
        return None
    field = _text(constraints.get("field"))
    if not field:
        return None
    try:
        minimum = constraints.get("minimum")
        maximum = constraints.get("maximum")
        lower = None if minimum is None else float(minimum)
        upper = None if maximum is None else float(maximum)
    except (TypeError, ValueError):
        return None
    if lower is None and upper is None:
        return None
    return field, _text(rule.get("applies_when")), lower, upper


def _conflict_evidence(left: ScannedCapability, right: ScannedCapability) -> dict[str, object] | None:
    for left_rule in _rules(left):
        left_interval = _interval(left_rule)
        if left_interval is None:
            continue
        for right_rule in _rules(right):
            right_interval = _interval(right_rule)
            if right_interval is None or left_interval[:2] != right_interval[:2]:
                continue
            left_lower, left_upper = left_interval[2:]
            right_lower, right_upper = right_interval[2:]
            lower = max(value for value in (left_lower, right_lower) if value is not None) if any(
                value is not None for value in (left_lower, right_lower)
            ) else None
            upper = min(value for value in (left_upper, right_upper) if value is not None) if any(
                value is not None for value in (left_upper, right_upper)
            ) else None
            if lower is not None and upper is not None and lower > upper:
                return {
                    "applies_when": left_interval[1],
                    "constraint_field": left_interval[0],
                    "left_interval": (left_lower, left_upper),
                    "left_rule_id": left_rule["rule_id"],
                    "right_interval": (right_lower, right_upper),
                    "right_rule_id": right_rule["rule_id"],
                }
    return None


def _candidate(
    relation_type: str, left: ScannedCapability, right: ScannedCapability, evidence: Mapping[str, object], *, snapshot_gid: int,
) -> CapabilityRelationCandidate:
    capability_keys = tuple(sorted((_key(left), _key(right))))
    payload = {
        "capability_keys": capability_keys,
        "evidence": dict(evidence),
        "relation_type": relation_type,
        "snapshot_gid": snapshot_gid,
        "source": "deterministic",
    }
    candidate_hash = canonical_fingerprint(payload)
    relation_candidate_gid = int(candidate_hash.split(":", 1)[1][:15], 16) or 1
    return CapabilityRelationCandidate(
        relation_candidate_gid=relation_candidate_gid,
        snapshot_gid=snapshot_gid,
        candidate_hash=candidate_hash,
        relation_type=relation_type,  # type: ignore[arg-type]
        source="deterministic",
        capability_keys=capability_keys,
        evidence=dict(evidence),
    )


def _analyze_pair(
    left: ScannedCapability, right: ScannedCapability, *, snapshot_gid: int,
) -> CapabilityRelationCandidate | None:
    left_fingerprint = left.fingerprint
    right_fingerprint = right.fingerprint
    if left_fingerprint is None or right_fingerprint is None:
        return None
    conflict = _conflict_evidence(left, right)
    if conflict is not None:
        return _candidate("conflict", left, right, conflict, snapshot_gid=snapshot_gid)
    if _same_contract(left, right):
        return _candidate("duplicate", left, right, {
            "matching_fields": (
                "action", "business_effect", "business_object", "input_schema_hash",
                "output_schema_hash", "read_scope", "rules", "write_scope",
            ),
            "provider_refs": tuple(sorted((left_fingerprint.provider_ref, right_fingerprint.provider_ref))),
        }, snapshot_gid=snapshot_gid)
    left_scopes = set(_scopes(left))
    right_scopes = set(_scopes(right))
    left_read, right_read = set(left_fingerprint.read_scope), set(right_fingerprint.read_scope)
    left_write, right_write = set(left_fingerprint.write_scope), set(right_fingerprint.write_scope)
    left_covers = left_read.issuperset(right_read) and left_write.issuperset(right_write)
    right_covers = right_read.issuperset(left_read) and right_write.issuperset(left_write)
    if (
        _text(left_fingerprint.business_effect) == _text(right_fingerprint.business_effect)
        and left_fingerprint.input_schema_hash == right_fingerprint.input_schema_hash
        and left_fingerprint.output_schema_hash == right_fingerprint.output_schema_hash
        and _rules(left) == _rules(right)
        and left_covers != right_covers
    ):
        covering, covered = (left, right) if left_covers else (right, left)
        covering_fingerprint, covered_fingerprint = covering.fingerprint, covered.fingerprint
        assert covering_fingerprint is not None and covered_fingerprint is not None
        contained_fields = tuple(field for field, covering_scope, covered_scope in (
            ("read_scope", covering_fingerprint.read_scope, covered_fingerprint.read_scope),
            ("write_scope", covering_fingerprint.write_scope, covered_fingerprint.write_scope),
        ) if tuple(covering_scope) != tuple(covered_scope))
        return _candidate("coverage", left, right, {
            "contained_fields": contained_fields,
            "covered_capability_key": _key(covered),
            "covering_capability_key": _key(covering),
            "covered_read_scope": covered_fingerprint.read_scope,
            "covered_write_scope": covered_fingerprint.write_scope,
            "covering_read_scope": covering_fingerprint.read_scope,
            "covering_write_scope": covering_fingerprint.write_scope,
        }, snapshot_gid=snapshot_gid)
    shared_scope = tuple(sorted(left_scopes & right_scopes))
    same_provider = left_fingerprint.provider_ref == right_fingerprint.provider_ref and bool(left_fingerprint.provider_ref)
    if not shared_scope and not same_provider:
        return None
    differing = tuple(field for field, left_value, right_value in (
        ("business_effect", _text(left_fingerprint.business_effect), _text(right_fingerprint.business_effect)),
        ("provider_ref", left_fingerprint.provider_ref, right_fingerprint.provider_ref),
        ("rules", _rules(left), _rules(right)),
    ) if left_value != right_value)
    if not differing:
        return None
    return _candidate("boundary_overlap", left, right, {
        "differing_fields": differing,
        "shared_provider_ref": left_fingerprint.provider_ref if same_provider else "",
        "shared_scope": shared_scope,
    }, snapshot_gid=snapshot_gid)


def analyze_relationships(
    capabilities: Iterable[ScannedCapability], *, snapshot_gid: int = 0,
) -> tuple[CapabilityRelationCandidate, ...]:
    """Produce one deterministic candidate per narrowed pair without AI input."""
    candidates = []
    for left, right in candidate_pairs(capabilities):
        candidate = _analyze_pair(left, right, snapshot_gid=snapshot_gid)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(sorted(candidates, key=lambda item: (item.relation_type, item.capability_keys, item.candidate_hash)))


__all__ = ["analyze_relationships", "candidate_pairs"]
