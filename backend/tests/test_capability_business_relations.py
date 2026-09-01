from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from backend.capability_governance_test.business_relations import analyze_relationships, candidate_pairs
from backend.capability_governance_test.fingerprint import snapshot_fingerprint
from backend.capability_governance_test.models import CapabilityFingerprint, ScannedCapability, SnapshotDocument
from backend.capability_governance_test.service import CapabilityGovernanceService
from backend.capability_governance_test.store import MemoryGovernanceStore


def _capability(
    capability_id: str,
    *,
    domain: str = "person",
    effect: str = "Record a normalized height.",
    read_scope: tuple[str, ...] = ("person.height",),
    write_scope: tuple[str, ...] = ("person.height",),
    rules: tuple[dict[str, object], ...] = (),
    object_name: str = "height",
    action: str = "write",
) -> ScannedCapability:
    fingerprint = CapabilityFingerprint(
        owner_domain=domain,
        business_object=object_name,
        action=action,
        business_effect=effect,
        input_schema_hash="sha256:" + "a" * 64,
        output_schema_hash="sha256:" + "b" * 64,
        provider_ref=f"{domain}.provider:{action}_{object_name}",
        read_scope=read_scope,
        write_scope=write_scope,
        rule_ids=tuple(sorted(str(rule["rule_id"]) for rule in rules)),
    )
    return ScannedCapability(
        capability_id=capability_id,
        major_version=1,
        owner_domain=domain,
        semantic_class="write",
        business_effect=effect,
        lifecycle_status="stable",
        descriptor_hash="sha256:" + "c" * 64,
        input_schema_hash=fingerprint.input_schema_hash,
        output_schema_hash=fingerprint.output_schema_hash,
        error_schema_hash="sha256:" + "d" * 64,
        policy_hash="sha256:" + "e" * 64,
        provider_hash="sha256:" + "f" * 64,
        business_rules=rules,
        fingerprint=fingerprint,
        descriptor={"id": capability_id, "major_version": 1},
    )


def _rule(
    rule_id: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    applies_when: str = "A height is changed.",
) -> dict[str, object]:
    constraints: dict[str, object] = {"field": "height", "unit": "m"}
    if minimum is not None:
        constraints["minimum"] = minimum
    if maximum is not None:
        constraints["maximum"] = maximum
    return {
        "rule_id": rule_id,
        "version": 1,
        "statement": "Structured rule evidence.",
        "applies_when": applies_when,
        "enforcement_ref": "person/provider.py:validate_height",
        "error_code": "invalid_height",
        "machine_constraints": constraints,
    }


def _relation(items: tuple[ScannedCapability, ...], relation_type: str):
    return next(item for item in analyze_relationships(items) if item.relation_type == relation_type)


def test_duplicate_is_cross_domain_and_field_explainable():
    candidate = _relation((
        _capability("ergonomics.height.write", domain="ergonomics"),
        _capability("person.height.write"),
    ), "duplicate")

    assert candidate.capability_keys == ("ergonomics.height.write@1", "person.height.write@1")
    assert candidate.source == "deterministic"
    assert set(candidate.evidence["matching_fields"]) >= {"business_effect", "criteria", "input_schema", "output_schema", "resource_selectors", "rules"}


def test_coverage_has_one_explicit_direction():
    broad = _capability("person.height.write_all")
    narrow = _capability("person.height.write")
    broad = replace(broad, descriptor={"resource_selectors": ({"resource_type": "person.height", "payload_path": "$.person"}, {"resource_type": "person.profile", "payload_path": "$.person"})})
    narrow = replace(narrow, descriptor={"resource_selectors": ({"resource_type": "person.height", "payload_path": "$.person"},)})

    candidate = _relation((narrow, broad), "coverage")

    assert candidate.evidence["covering_capability_key"] == "person.height.write_all@1"
    assert candidate.evidence["covered_capability_key"] == "person.height.write@1"
    assert candidate.evidence["resource_selector_containment"] is True


def test_coverage_does_not_reverse_read_and_write_scope_direction():
    writes_more = _capability(
        "person.height.write_more", read_scope=("person.height",),
        write_scope=("person.height", "person.profile", "person.audit"),
    )
    reads_more = _capability(
        "person.height.read_more", read_scope=("person.height", "person.profile"),
        write_scope=("person.height",),
    )

    result = analyze_relationships((writes_more, reads_more))

    assert not any(item.relation_type == "coverage" for item in result)


def test_conflict_requires_disjoint_machine_constraints_not_merely_different_text():
    compatible = analyze_relationships((
        _capability("ergonomics.height.validate", domain="ergonomics", rules=(_rule("height.maximum", maximum=2.5),)),
        _capability("person.height.write", rules=(_rule("height.maximum", maximum=2.2),)),
    ))
    conflict = _relation((
        _capability("ergonomics.height.validate", domain="ergonomics", rules=(_rule("height.maximum", maximum=2.5),)),
        _capability("person.height.write", rules=(_rule("height.minimum", minimum=2.6),)),
    ), "conflict")

    assert not any(item.relation_type == "conflict" for item in compatible)
    assert conflict.capability_keys == ("ergonomics.height.validate@1", "person.height.write@1")
    assert conflict.evidence["constraint_field"] == "height"
    assert conflict.evidence["left_interval"] == (None, 2.5)
    assert conflict.evidence["right_interval"] == (2.6, None)


def test_cross_action_validate_and_write_rules_conflict_when_their_closed_intervals_do_not_overlap():
    result = analyze_relationships((
        _capability("ergonomics.height.validate", domain="ergonomics", action="validate", rules=(_rule("height.maximum", maximum=2.5),)),
        _capability("person.height.write", action="write", rules=(_rule("height.minimum", minimum=2.6),)),
    ))

    conflict = next(item for item in result if item.relation_type == "conflict")
    assert conflict.capability_keys == ("ergonomics.height.validate@1", "person.height.write@1")


def test_open_boundary_and_units_are_part_of_a_provable_conflict():
    upper = _rule("height.maximum", maximum=2.5)
    lower = _rule("height.minimum", minimum=2.5)
    lower["machine_constraints"]["minimum_inclusive"] = False
    result = analyze_relationships((_capability("a.height.validate", domain="a", action="validate", rules=(upper,)), _capability("b.height.write", domain="b", rules=(lower,))))
    assert any(item.relation_type == "conflict" for item in result)
    lower["machine_constraints"]["unit"] = "cm"
    result = analyze_relationships((_capability("a.height.validate", domain="a", action="validate", rules=(upper,)), _capability("b.height.write", domain="b", rules=(lower,))))
    assert not any(item.relation_type == "conflict" for item in result)


def test_boundary_overlap_requires_shared_structured_responsibility():
    candidate = _relation((
        _capability("ergonomics.height.recommend", domain="ergonomics", effect="Recommend a workstation height."),
        _capability("person.height.write", effect="Record a normalized height."),
    ), "boundary_overlap")

    assert candidate.evidence["shared_write_scope"] == ("person.height",)
    assert candidate.evidence["differing_fields"] == ("business_effect",)


def test_candidate_narrowing_skips_other_buckets_and_is_bounded():
    height_one = _capability("person.height.write")
    height_two = _capability("ergonomics.height.write", domain="ergonomics")
    weight = _capability("person.weight.write", object_name="weight")
    name = _capability("person.height.read", action="read")

    assert list(candidate_pairs((height_one, height_two, weight, name))) == [(height_two, height_one)]
    assert analyze_relationships((height_one, weight, name)) == ()


def test_shuffle_does_not_change_candidate_hash_or_evidence():
    items = (
        _capability("person.height.write", write_scope=("person.height",)),
        _capability("ergonomics.height.write", domain="ergonomics", write_scope=("person.height", "person.profile")),
    )

    forward = analyze_relationships(items)
    reverse = analyze_relationships(tuple(reversed(items)))

    assert [(item.candidate_hash, item.evidence, item.capability_keys) for item in forward] == [
        (item.candidate_hash, item.evidence, item.capability_keys) for item in reverse
    ]


def test_service_persists_candidates_once_when_identical_snapshot_is_scanned_again():
    capabilities = (
        _capability("person.height.write"),
        _capability("ergonomics.height.write", domain="ergonomics"),
    )
    document = SnapshotDocument("catalog", None, "revision", "", capabilities, (), (), ())
    document = replace(document, snapshot_hash=snapshot_fingerprint(document))

    class Scanner:
        def scan(self, _code_revision):
            return document

    store = MemoryGovernanceStore(next_ids=iter(range(1, 100)).__next__)
    service = CapabilityGovernanceService(store, scanner=Scanner())
    payload = {"code_revision": "revision", "idempotency_key": "scan-1"}

    first = service.base_capability_scan_run(payload, object())
    second = service.base_capability_scan_run({**payload, "idempotency_key": "scan-2"}, object())

    assert first["snapshot_gid"] == second["snapshot_gid"]
    assert len(store.list_relation_candidates(int(first["snapshot_gid"]))) == 1


def test_advisory_failure_cannot_remove_persisted_deterministic_evidence():
    capabilities = (
        _capability("person.height.write"),
        _capability("ergonomics.height.write", domain="ergonomics"),
    )
    document = SnapshotDocument("catalog", None, "revision", "", capabilities, (), (), ())
    document = replace(document, snapshot_hash=snapshot_fingerprint(document))

    class Scanner:
        def scan(self, _code_revision):
            return document

    class FailingAdvisor:
        async def review(self, _package, **_kwargs):
            raise TimeoutError("advisor timed out")

    store = MemoryGovernanceStore(next_ids=iter(range(1, 100)).__next__)
    service = CapabilityGovernanceService(store, scanner=Scanner(), advisor=FailingAdvisor())
    result = service.base_capability_scan_run({"code_revision": "revision", "idempotency_key": "scan"}, object())

    advice = asyncio.run(service.review_advisory({}, context=type("Context", (), {"identity": object()})(), request_id="advice"))
    assert advice.findings == ()
    assert len(store.list_relation_candidates(int(result["snapshot_gid"]))) == 1
