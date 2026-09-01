from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
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
HASH_A = "sha256:" + "a" * 64


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


def test_memory_projection_enforces_purpose_subject_unique_key():
    store = MemoryGovernanceStore()
    projection = replace(_projection(), rules=(), relation_candidates=())
    duplicate = replace(
        projection,
        purpose=replace(projection.purpose, purpose_gid=999),
    )

    store.save_business_projection(projection)

    with pytest.raises(ImmutableRecordError, match="uq_capability_business_purpose"):
        store.save_business_projection(duplicate)


def test_memory_projection_rejects_duplicate_rule_identity_and_gid_within_batch():
    projection = _projection()
    rule = projection.rules[0]

    duplicate_identity = replace(rule, business_rule_gid=999)
    with pytest.raises(ImmutableRecordError, match="uq_capability_business_rule"):
        MemoryGovernanceStore().save_business_projection(
            replace(projection, rules=(rule, duplicate_identity), relation_candidates=()),
        )

    duplicate_gid = replace(rule, rule_id="person.height.unit")
    with pytest.raises(ImmutableRecordError, match="business_rule_gid_already_exists"):
        MemoryGovernanceStore().save_business_projection(
            replace(projection, rules=(rule, duplicate_gid), relation_candidates=()),
        )


def test_memory_projection_rejects_duplicate_candidate_subject_and_gid_within_batch():
    projection = _projection()
    candidate = projection.relation_candidates[0]

    duplicate_subject = replace(candidate, relation_candidate_gid=999)
    with pytest.raises(ImmutableRecordError, match="uq_capability_relation_candidate"):
        MemoryGovernanceStore().save_business_projection(
            replace(projection, rules=(), relation_candidates=(candidate, duplicate_subject)),
        )

    duplicate_gid = replace(candidate, candidate_hash=HASH_1)
    with pytest.raises(ImmutableRecordError, match="relation_candidate_gid_already_exists"):
        MemoryGovernanceStore().save_business_projection(
            replace(projection, rules=(), relation_candidates=(candidate, duplicate_gid)),
        )


def test_memory_relation_candidates_use_sql_order():
    projection = _projection()
    first = replace(projection.relation_candidates[0], relation_candidate_gid=405, candidate_hash=HASH_1)
    second = replace(projection.relation_candidates[0], relation_candidate_gid=403, candidate_hash=HASH_2)
    store = MemoryGovernanceStore()

    store.save_business_projection(
        replace(projection, rules=(), relation_candidates=(first, second)),
    )

    assert store.list_relation_candidates(501) == (second, first)


def test_memory_relation_candidate_batch_is_all_or_nothing():
    candidate = _projection().relation_candidates[0]
    valid = replace(candidate, relation_candidate_gid=404, candidate_hash=HASH_1)
    conflicting = replace(valid, relation_candidate_gid=405)
    store = MemoryGovernanceStore()

    with pytest.raises(ImmutableRecordError, match="uq_capability_relation_candidate"):
        store.save_relation_candidates((valid, conflicting))

    assert store.list_relation_candidates(candidate.snapshot_gid) == ()


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
        proposal_gid=701,
        evidence_snapshot_gid=501,
    )

    store.save_business_review(review)

    assert store.current_business_review(202, review.definition_hash) == review
    assert store.current_business_review(202, HASH_2) is None


def test_business_review_hash_lookup_is_case_and_space_exact_in_memory():
    store = MemoryGovernanceStore()
    review = CapabilityBusinessReview(
        101, 202, HASH_A, "approved", "Evidence is sufficient", "9001", "super_admin",
        NOW, 701, 501,
    )
    store.save_business_review(review)

    assert store.current_business_review(202, HASH_A.upper()) is None
    assert store.current_business_review(202, HASH_A + " ") is None


def test_business_reviews_are_append_only_and_latest_exact_hash_is_current():
    store = MemoryGovernanceStore()
    first = CapabilityBusinessReview(101, 202, HASH_1, "changes_requested", "Add evidence", "9001", "super_admin", NOW, 701, 501)
    second = CapabilityBusinessReview(102, 202, HASH_1, "approved", "Evidence added", "9001", "super_admin", NOW + timedelta(seconds=1), 701, 501)

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


def test_memory_rule_effectiveness_uses_sql_order():
    store = MemoryGovernanceStore()
    latest = _effectiveness_record(effectiveness_gid=303, measured_to=NOW + timedelta(hours=1))
    same_time_high_gid = _effectiveness_record(effectiveness_gid=302)
    same_time_low_gid = _effectiveness_record(effectiveness_gid=301)

    store.save_rule_effectiveness(latest)
    store.save_rule_effectiveness(same_time_high_gid)
    store.save_rule_effectiveness(same_time_low_gid)

    assert store.list_rule_effectiveness(202, HASH_1) == (
        same_time_low_gid, same_time_high_gid, latest,
    )


class _Cursor:
    def __init__(self, connection: "_Connection"):
        self.connection = connection
        self.row = None
        self.rows: list[object] = []

    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> None:
        self.connection.calls.append((query, parameters))
        if query.startswith("SELECT business_review_gid"):
            row = self.connection.review_row
            if row is not None:
                stored_hash = row[2].decode("ascii") if isinstance(row[2], bytes) else str(row[2])
                requested_hash = str(parameters[1])
                exact = "definition_hash = BINARY %s" in query
                matches = stored_hash == requested_hash if exact else stored_hash.rstrip().casefold() == requested_hash.rstrip().casefold()
                row = row if matches else None
            self.row = row
        elif query.startswith("SELECT effectiveness_gid"):
            exact = "definition_hash = BINARY %s" in query
            requested_hash = str(parameters[1])
            self.rows = [
                row for row in self.connection.effectiveness_rows
                if (
                    (row[2].decode("ascii") if isinstance(row[2], bytes) else str(row[2])) == requested_hash
                    if exact else
                    (row[2].decode("ascii") if isinstance(row[2], bytes) else str(row[2])).rstrip().casefold()
                    == requested_hash.rstrip().casefold()
                )
            ]
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
    review = CapabilityBusinessReview(101, 202, HASH_1, "approved", "Evidence is sufficient", "9001", "super_admin", NOW, 701, 501)
    effectiveness = _effectiveness_record()
    connection = _Connection(
        review_row=(101, 202, HASH_1, "approved", "Evidence is sufficient", "9001", "super_admin", NOW, 701, 501),
        effectiveness_rows=((301, 202, HASH_1, "rule_rejection_count", 7,
                             '{"error_codes":["invalid_height"],"source":"audit"}',
                             NOW - timedelta(days=1), NOW),),
    )
    store = SqlGovernanceStore(connection)

    store.save_business_review(review)
    store.save_rule_effectiveness(effectiveness)

    assert store.current_business_review(202, HASH_1) == review
    assert store.list_rule_effectiveness(202, HASH_1) == (effectiveness,)
    assert store.list_rule_effectiveness(202, HASH_1.upper()) == ()
    review_select = next((query, parameters) for query, parameters in connection.calls if query.startswith("SELECT business_review_gid"))
    effectiveness_select = next((query, parameters) for query, parameters in connection.calls if query.startswith("SELECT effectiveness_gid"))
    assert review_select[1] == (202, HASH_1)
    assert effectiveness_select[1] == (202, HASH_1)
    assert "definition_hash = BINARY %s" in effectiveness_select[0]
    assert connection.commits == 2


def test_sql_review_lookup_is_binary_exact_for_case_and_trailing_space():
    connection = _Connection(
        review_row=(101, 202, HASH_A.encode("ascii"), "approved", "Evidence is sufficient", "9001", "super_admin", NOW, 701, 501),
    )
    store = SqlGovernanceStore(connection)

    assert store.current_business_review(202, HASH_A.upper()) is None
    assert store.current_business_review(202, HASH_A + " ") is None
    queries = [query for query, _ in connection.calls if query.startswith("SELECT business_review_gid")]
    assert all("definition_hash = BINARY %s" in query for query in queries)


@pytest.mark.parametrize(
    ("proposal_gid", "evidence_snapshot_gid", "error_code"),
    ((0, 501, "business_review_proposal_gid_invalid"), (701, 0, "business_review_evidence_snapshot_gid_invalid")),
)
def test_stores_reject_invalid_business_review_references_before_insert(
    proposal_gid: int, evidence_snapshot_gid: int, error_code: str,
):
    review = CapabilityBusinessReview(
        101, 202, HASH_1, "approved", "Evidence is sufficient", "9001", "super_admin",
        NOW, proposal_gid, evidence_snapshot_gid,
    )

    with pytest.raises(ImmutableRecordError, match=error_code):
        MemoryGovernanceStore().save_business_review(review)

    connection = _Connection()
    with pytest.raises(ImmutableRecordError, match=error_code):
        SqlGovernanceStore(connection).save_business_review(review)
    assert connection.calls == []


class _RelationTxCursor:
    def __init__(self, connection): self.connection, self.rows = connection, []
    def execute(self, query, parameters=()):
        self.connection.calls.append((query, parameters))
        if self.connection.fail_insert:
            raise RuntimeError("transport_down")
        if query.startswith("INSERT INTO workmanship_base_capability_relation_candidates"):
            row = tuple(parameters)
            if not any(item[0] == row[0] or (item[1] == row[1] and item[2] == row[2]) for item in self.connection.staged):
                self.connection.staged.append(row)
        elif query.startswith("SELECT relation_candidate_gid"):
            gid, snapshot, digest = parameters
            self.rows = [item for item in self.connection.staged if item[0] == gid or (item[1] == snapshot and item[2] == digest)]
    def fetchall(self): return self.rows
    def close(self): pass


class _RelationTxConnection:
    def __init__(self, rows=(), fail_insert=False):
        self.rows, self.staged, self.calls, self.fail_insert = list(rows), list(rows), [], fail_insert
        self.commits = self.rollbacks = 0
    def cursor(self): return _RelationTxCursor(self)
    def commit(self): self.rows = list(self.staged); self.commits += 1
    def rollback(self): self.staged = list(self.rows); self.rollbacks += 1


def _relation_row(candidate):
    return (candidate.relation_candidate_gid, candidate.snapshot_gid, candidate.candidate_hash, candidate.relation_type,
            candidate.source, '["person.height.read@1","person.height.write@1"]', '{"shared_fields":["height"]}', candidate.status)


def test_sql_relation_transactional_readback_exact_replay_and_conflicts_rollback():
    candidate = _projection().relation_candidates[0]
    connection = _RelationTxConnection((_relation_row(candidate),))
    store = SqlGovernanceStore(connection)
    store.save_relation_candidates((candidate,))
    assert connection.commits == 1 and len(connection.rows) == 1
    assert any("FOR UPDATE" in query for query, _ in connection.calls)
    assert any("ON DUPLICATE KEY UPDATE" in query for query, _ in connection.calls)
    for conflict in (replace(candidate, snapshot_gid=999, candidate_hash=HASH_1), replace(candidate, relation_candidate_gid=999)):
        with pytest.raises(ImmutableRecordError, match="relation_candidate_immutable_conflict"):
            store.save_relation_candidates((conflict,))
        assert connection.rollbacks and connection.rows == [_relation_row(candidate)]


def test_sql_relation_transaction_batch_rolls_back_and_preserves_nonunique_errors():
    candidate = _projection().relation_candidates[0]
    first = replace(candidate, relation_candidate_gid=404, candidate_hash=HASH_1)
    conflicting = replace(candidate, relation_candidate_gid=405, candidate_hash=HASH_1)
    connection = _RelationTxConnection()
    with pytest.raises(ImmutableRecordError):
        SqlGovernanceStore(connection).save_relation_candidates((first, conflicting))
    assert connection.rows == []
    with pytest.raises(RuntimeError, match="transport_down"):
        SqlGovernanceStore(_RelationTxConnection(fail_insert=True)).save_relation_candidates((candidate,))
