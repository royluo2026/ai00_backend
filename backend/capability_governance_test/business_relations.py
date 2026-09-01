"""Narrowed, reproducible relationship analysis over structured business evidence."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from itertools import combinations
import math
from typing import Any

from .business_models import CapabilityRelationCandidate
from .fingerprint import canonical_fingerprint
from .models import ScannedCapability


def _key(item: ScannedCapability) -> str:
    return f"{item.capability_id}@{item.major_version}"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(sorted({_text(item) for item in value or () if _text(item)})) if isinstance(value, (tuple, list)) else ()


def _rules(item: ScannedCapability) -> tuple[dict[str, Any], ...]:
    values = []
    for raw in item.business_rules:
        if not isinstance(raw, Mapping):
            continue
        constraint = raw.get("machine_constraints")
        values.append({"rule_id": _text(raw.get("rule_id")), "version": raw.get("version"), "statement": _text(raw.get("statement")), "applies_when": _text(raw.get("applies_when")), "error_code": _text(raw.get("error_code")), "machine_constraints": dict(constraint) if isinstance(constraint, Mapping) else None})
    return tuple(sorted(values, key=canonical_fingerprint))


def _selectors(item: ScannedCapability) -> tuple[dict[str, object], ...]:
    values = []
    for raw in item.descriptor.get("resource_selectors", ()) if isinstance(item.descriptor, Mapping) else ():
        if isinstance(raw, Mapping) and _text(raw.get("resource_type")) and _text(raw.get("payload_path")):
            values.append({"resource_type": _text(raw.get("resource_type")), "payload_path": _text(raw.get("payload_path")), "required": bool(raw.get("required", True))})
    return tuple(sorted(values, key=canonical_fingerprint))


def _semantic(item: ScannedCapability) -> dict[str, object] | None:
    fp = item.fingerprint
    if fp is None:
        return None
    descriptor = item.descriptor if isinstance(item.descriptor, Mapping) else {}
    return {"business_effect": _text(fp.business_effect), "criteria": _strings(descriptor.get("business_acceptance_criteria")), "input_schema_hash": fp.input_schema_hash, "output_schema_hash": fp.output_schema_hash, "input_schema": descriptor.get("input_schema", {}), "output_schema": descriptor.get("output_schema", {}), "read_scope": tuple(sorted(fp.read_scope)), "write_scope": tuple(sorted(fp.write_scope)), "resource_selectors": _selectors(item), "rules": _rules(item)}


def candidate_pairs(items: Iterable[ScannedCapability]) -> Iterator[tuple[ScannedCapability, ScannedCapability]]:
    """Narrow duplicate/coverage/overlap work to the same object and action."""
    buckets: dict[tuple[str, str], dict[str, ScannedCapability]] = defaultdict(dict)
    for item in items:
        fp = item.fingerprint
        if fp is not None and _text(fp.business_object) and _text(fp.action):
            buckets[(_text(fp.business_object), _text(fp.action))].setdefault(_key(item), item)
    for bucket in sorted(buckets):
        yield from combinations(tuple(sorted(buckets[bucket].values(), key=_key)), 2)


def _interval(rule: Mapping[str, Any]) -> tuple[str, str, str, float | None, float | None, bool, bool] | None:
    value = rule.get("machine_constraints")
    if not isinstance(value, Mapping):
        return None
    field, applies, unit = _text(value.get("field")), _text(rule.get("applies_when")), _text(value.get("unit"))
    if not field or not applies or not unit:
        return None
    lower, upper = value.get("minimum"), value.get("maximum")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in (lower, upper) if v is not None) or (lower is None and upper is None):
        return None
    return field, applies, unit, None if lower is None else float(lower), None if upper is None else float(upper), bool(value.get("minimum_inclusive", True)), bool(value.get("maximum_inclusive", True))


def _conflict(left: ScannedCapability, right: ScannedCapability) -> dict[str, object] | None:
    for a in _rules(left):
        ar = _interval(a)
        if ar is None:
            continue
        for b in _rules(right):
            br = _interval(b)
            if br is None or ar[:3] != br[:3]:
                continue
            low = max(v for v in (ar[3], br[3]) if v is not None) if any(v is not None for v in (ar[3], br[3])) else None
            high = min(v for v in (ar[4], br[4]) if v is not None) if any(v is not None for v in (ar[4], br[4])) else None
            if low is not None and high is not None:
                low_inc = (ar[5] if low == ar[3] else True) and (br[5] if low == br[3] else True)
                high_inc = (ar[6] if high == ar[4] else True) and (br[6] if high == br[4] else True)
                if low > high or (low == high and not (low_inc and high_inc)):
                    return {"constraint_field": ar[0], "applies_when": ar[1], "unit": ar[2], "left_interval": (ar[3], ar[4]), "right_interval": (br[3], br[4]), "left_rule_id": a["rule_id"], "right_rule_id": b["rule_id"]}
    return None


def _conflict_pairs(items: Iterable[ScannedCapability]) -> Iterator[tuple[ScannedCapability, ScannedCapability]]:
    buckets: dict[tuple[str, str, str, str], dict[str, ScannedCapability]] = defaultdict(dict)
    for item in items:
        fp = item.fingerprint
        if fp is None or not _text(fp.business_object):
            continue
        for rule in _rules(item):
            value = _interval(rule)
            if value is not None:
                buckets[(_text(fp.business_object), value[0], value[1], value[2])].setdefault(_key(item), item)
    for bucket in sorted(buckets):
        yield from combinations(tuple(sorted(buckets[bucket].values(), key=_key)), 2)


def _candidate(kind: str, left: ScannedCapability, right: ScannedCapability, evidence: Mapping[str, object], snapshot_gid: int) -> CapabilityRelationCandidate:
    keys = tuple(sorted((_key(left), _key(right))))
    digest = canonical_fingerprint({"snapshot_gid": snapshot_gid, "relation_type": kind, "capability_keys": keys, "evidence": dict(evidence), "source": "deterministic"})
    return CapabilityRelationCandidate(int(digest.split(":", 1)[1][:15], 16) or 1, snapshot_gid, digest, kind, "deterministic", keys, dict(evidence))  # type: ignore[arg-type]


def _analyze_pair(left: ScannedCapability, right: ScannedCapability, snapshot_gid: int) -> CapabilityRelationCandidate | None:
    lf, rf = left.fingerprint, right.fingerprint
    if lf is None or rf is None or _text(lf.business_object) != _text(rf.business_object):
        return None
    conflict = _conflict(left, right)
    if conflict is not None:
        return _candidate("conflict", left, right, conflict, snapshot_gid)
    if _text(lf.action) != _text(rf.action):
        return None
    a, b = _semantic(left), _semantic(right)
    if a is None or b is None:
        return None
    if a == b:
        return _candidate("duplicate", left, right, {"matching_fields": tuple(sorted(a)), "provider_refs": tuple(sorted((lf.provider_ref, rf.provider_ref)))}, snapshot_gid)
    core = ("business_effect", "criteria", "input_schema_hash", "output_schema_hash", "input_schema", "output_schema", "read_scope", "write_scope", "rules")
    if all(a[name] == b[name] for name in core):
        sa, sb = set(map(canonical_fingerprint, a["resource_selectors"])), set(map(canonical_fingerprint, b["resource_selectors"]))
        if sa > sb or sb > sa:
            covering, covered = (left, right) if sa > sb else (right, left)
            return _candidate("coverage", left, right, {"covering_capability_key": _key(covering), "covered_capability_key": _key(covered), "resource_selector_containment": True}, snapshot_gid)
    shared_writes = tuple(sorted(set(lf.write_scope) & set(rf.write_scope)))
    shared_resources = tuple(sorted({item["resource_type"] for item in _selectors(left)} & {item["resource_type"] for item in _selectors(right)}))
    if shared_writes or shared_resources:
        return _candidate("boundary_overlap", left, right, {"shared_write_scope": shared_writes, "shared_resource_types": shared_resources, "differing_fields": tuple(name for name in sorted(set(a) | set(b)) if a.get(name) != b.get(name))}, snapshot_gid)
    return None


def analyze_relationships(capabilities: Iterable[ScannedCapability], *, snapshot_gid: int = 0) -> tuple[CapabilityRelationCandidate, ...]:
    items = tuple(capabilities)
    pairs = {tuple(sorted((_key(a), _key(b)))): (a, b) for a, b in candidate_pairs(items)}
    for left, right in _conflict_pairs(items):
        pairs.setdefault(tuple(sorted((_key(left), _key(right)))), (left, right))
    values = (_analyze_pair(left, right, snapshot_gid) for left, right in pairs.values())
    return tuple(sorted((item for item in values if item is not None), key=lambda item: (item.relation_type, item.capability_keys, item.candidate_hash)))


__all__ = ["analyze_relationships", "candidate_pairs"]
