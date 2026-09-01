from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from backend.capability_governance_test.business_models import (
    BusinessPurposeRecord,
    BusinessRuleRecord,
    CapabilityBusinessProjection,
    CapabilityBusinessReview,
    CapabilityFingerprint,
    CapabilityMaturity,
    CapabilityRelationCandidate,
    RuleEffectivenessRecord,
)
from backend.capability_governance_test.models import ImmutableRecordError
from backend.capability_governance_test.store import MemoryGovernanceStore, SqlGovernanceStore


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64


def _effectiveness_record(**overrides: object) -> RuleEffectivenessRecord:
    values: dict[str, object] = {
        "effectiveness_gid": 301,
        "capability_version_gid": 202,
        "definition_hash": HASH_1,
        "metric_name": "rule_rejection_count",
        "metric_value": 7,
        "evidence": {"error_codes": ["invalid_height"], "source": "audit"},
        "measured_from": NOW - timedelta(days=1),
        "measured_to": NOW,
    }
    values.update(overrides)
    return RuleEffectivenessRecord(**values)


def _projection() -> CapabilityBusinessProjection:
    purpose = BusinessPurposeRecord(
        purpose_gid=401,
        capability_version_gid=202,
        definition_hash=HASH_1,
        business_effect="Record a valid normalized height.",
        acceptance_criteria=("A read returns the normalized height.",),
        evidence_snapshot_gid=501,
        created_at=NOW,
    )
    rule = BusinessRuleRecord(
        business_rule_gid=402,
        capability_version_gid=202,
        definition_hash=HASH_1,
        rule_id="person.height.valid_range",
        rule_version=1,
        statement="Normalized height is between 0.3 m and 2.5 m.",
        applies_when="A height is created or changed.",
        enforcement_ref="person/provider.py:validate_height",
        error_code="invalid_height",
        test_refs=("tests/test_person_height.py::test_height_range",),
        evidence_snapshot_gid=501,
    )
    relation = CapabilityRelationCandidate(
        relation_candidate_gid=403,
        snapshot_gid=501,
        candidate_hash=HASH_2,
        relation_type="boundary_overlap",
        source="deterministic",
        capability_keys=("person.height.read@1", "person.height.write@1"),
        evidence={"shared_fields": ["height"]},
        status="pending_review",
    )
    return CapabilityBusinessProjection(
        purpose=purpose,
        rules=(rule,),
        fingerprint=CapabilityFingerprint(
            owner_domain="person",
            business_object="height",
            action="write",
            business_effect=purpose.business_effect,
            input_schema_hash=HASH_1,
            output_schema_hash=HASH_2,
            provider_ref="person/provider.py:write_height",
            read_scope=("person.height",),
            write_scope=("person.height",),
            rule_ids=(rule.rule_id,),
        ),
        maturity=CapabilityMaturity(level="L3", reason_codes=("rule_evidence_present",)),
        relation_candidates=(relation,),
    )


def test_business_records_are_deeply_immutable():
    evidence = {"shared_fields": ["height"]}
    candidate = CapabilityRelationCandidate(
        relation_candidate_gid=1,
        snapshot_gid=2,
        candidate_hash=HASH_1,
        relation_type="duplicate",
        source="deterministic",
        capability_keys=["person.height.read@1", "person.height.lookup@1"],
        evidence=evidence,
        status="pending_review",
    )

    evidence["shared_fields"].append("unit")

    assert candidate.capability_keys == ("person.height.read@1", "person.height.lookup@1")
    assert candidate.evidence["shared_fields"] == ("height",)
    with pytest.raises(FrozenInstanceError):
        candidate.status = "confirmed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        candidate.evidence["new"] = "value"  # type: ignore[index]


def test_memory_projection_round_trips_relation_candidates():
    store = MemoryGovernanceStore()
    projection = _projection()

    store.save_business_projection(projection)

    assert store.list_relation_candidates(501) == projection.relation_candidates


def test_business_review_is_bound_to_exact_definition_hash():
    store = MemoryGovernanceStore()
    review = CapabilityBusinessReview(
        review_gid=101,
        capability_version_gid=202,
        definition_hash=HASH_1,
        decision="approved",
        decision_reason="Evidence is sufficient",
        reviewer_gid="9001",
        reviewer_role="super_admin",
        decided_at=NOW,
    )

    store.save_business_review(review)

    assert store.current_business_review(202, review.definition_hash) == review
    assert store.current_business_review(202, HASH_2) is None


def test_business_reviews_are_append_only_and_latest_exact_hash_is_current():
    store = MemoryGovernanceStore()
    first = CapabilityBusinessReview(101, 202, HASH_1, "changes_requested", "Add evidence", "9001", "super_admin", NOW)
    second = CapabilityBusinessReview(102, 202, HASH_1, "approved", "Evidence added", "9001", "super_admin", NOW + timedelta(seconds=1))

    store.save_business_review(first)
    store.save_business_review(second)

    assert store.current_business_review(202, HASH_1) == second
    with pytest.raises(ImmutableRecordError, match="business_review_gid_already_exists"):
        store.save_business_review(first)


def test_rule_effectiveness_is_append_only():
    store = MemoryGovernanceStore()
    first = _effectiveness_record()
    second = _effectiveness_record(effectiveness_gid=302, metric_value=9, measured_to=NOW + timedelta(hours=1))

    store.save_rule_effectiveness(first)
    store.save_rule_effectiveness(second)

    assert store.list_rule_effectiveness(first.capability_version_gid, first.definition_hash) == (first, second)
    assert store.list_rule_effectiveness(first.capability_version_gid, HASH_2) == ()
    with pytest.raises(ImmutableRecordError, match="effectiveness_gid_already_exists"):
        store.save_rule_effectiveness(first)


class _Cursor:
    def __init__(self, connection: "_Connection"):
        self.connection = connection
        self.row = None
        self.rows: list[object] = []

    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> None:
        self.connection.calls.append((query, parameters))
        if query.startswith("SELECT business_review_gid"):
            self.row = self.connection.review_row
        elif query.startswith("SELECT effectiveness_gid"):
            self.rows = list(self.connection.effectiveness_rows)
        elif query.startswith("SELECT relation_candidate_gid"):
            self.rows = list(self.connection.relation_rows)
        else:
            self.row = None
            self.rows = []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def close(self) -> None:
        pass


class _Connection:
    def __init__(self, *, review_row=None, effectiveness_rows=(), relation_rows=()):
        self.review_row = review_row
        self.effectiveness_rows = effectiveness_rows
        self.relation_rows = relation_rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_sql_projection_uses_parameterized_canonical_json_and_lists_relations():
    projection = _projection()
    relation = projection.relation_candidates[0]
    connection = _Connection(relation_rows=((
        relation.relation_candidate_gid,
        relation.snapshot_gid,
        relation.candidate_hash,
        relation.relation_type,
        relation.source,
        '["person.height.read@1","person.height.write@1"]',
        '{"shared_fields":["height"]}',
        relation.status,
    ),))
    store = SqlGovernanceStore(connection)

    store.save_business_projection(projection)

    inserts = {query.split()[2]: parameters for query, parameters in connection.calls if query.startswith("INSERT INTO")}
    assert inserts["workmanship_base_capability_business_purposes"][4] == '["A read returns the normalized height."]'
    assert inserts["workmanship_base_capability_business_rules"][9] == '["tests/test_person_height.py::test_height_range"]'
    assert inserts["workmanship_base_capability_relation_candidates"][6] == '{"shared_fields":["height"]}'
    assert all("%s" in query for query, _ in connection.calls if query.startswith("INSERT INTO"))
    assert connection.commits == 1
    assert store.list_relation_candidates(501) == (relation,)


def test_sql_review_and_effectiveness_round_trip_exact_definition_hash():
    review = CapabilityBusinessReview(101, 202, HASH_1, "approved", "Evidence is sufficient", "9001", "super_admin", NOW)
    effectiveness = _effectiveness_record()
    connection = _Connection(
        review_row=(101, 202, HASH_1, "approved", "Evidence is sufficient", "9001", "super_admin", NOW, 0, 0),
        effectiveness_rows=((301, 202, HASH_1, "rule_rejection_count", 7,
                             '{"error_codes":["invalid_height"],"source":"audit"}',
                             NOW - timedelta(days=1), NOW),),
    )
    store = SqlGovernanceStore(connection)

    store.save_business_review(review)
    store.save_rule_effectiveness(effectiveness)

    assert store.current_business_review(202, HASH_1) == review
    assert store.list_rule_effectiveness(202, HASH_1) == (effectiveness,)
    review_select = next((query, parameters) for query, parameters in connection.calls if query.startswith("SELECT business_review_gid"))
    effectiveness_select = next((query, parameters) for query, parameters in connection.calls if query.startswith("SELECT effectiveness_gid"))
    assert review_select[1] == (202, HASH_1)
    assert effectiveness_select[1] == (202, HASH_1)
    assert connection.commits == 2
