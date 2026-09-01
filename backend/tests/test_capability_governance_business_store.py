from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, RLock
from types import SimpleNamespace

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
from backend.capability_governance_test.release_gate import ReleaseGate
from backend.capability_governance_test.service import CapabilityGovernanceService
from backend.capability_governance_test.store import MemoryGovernanceStore, SqlGovernanceStore
from backend.capability_governance_test.workflow import Proposal, ProposalService, ReviewerContext, WaiverService, WorkflowError
from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, TenantIdentity


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64
HASH_A = "sha256:" + "a" * 64


def _memory_review_store() -> MemoryGovernanceStore:
    store = MemoryGovernanceStore()
    store._snapshots[501] = SimpleNamespace(
        snapshot_gid=501, entries=(SimpleNamespace(capability_version_gid=202),),
    )
    return store


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
    store = _memory_review_store()
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
    store = _memory_review_store()
    review = CapabilityBusinessReview(
        101, 202, HASH_A, "approved", "Evidence is sufficient", "9001", "super_admin",
        NOW, 701, 501,
    )
    store.save_business_review(review)

    assert store.current_business_review(202, HASH_A.upper()) is None
    assert store.current_business_review(202, HASH_A + " ") is None


def test_memory_business_review_requires_the_referenced_snapshot_and_version():
    review = CapabilityBusinessReview(
        101, 202, HASH_1, "approved", "Evidence is sufficient", "9001", "super_admin",
        NOW, 701, 501,
    )

    with pytest.raises(ImmutableRecordError, match="business_review_evidence_snapshot_not_found"):
        MemoryGovernanceStore().save_business_review(review)
    wrong_version = _memory_review_store()
    wrong_version._snapshots[501] = SimpleNamespace(
        snapshot_gid=501, entries=(SimpleNamespace(capability_version_gid=999),),
    )
    with pytest.raises(ImmutableRecordError, match="business_review_capability_version_not_in_snapshot"):
        wrong_version.save_business_review(review)


def test_memory_atomic_business_decision_is_shared_across_workflow_instances():
    store = _memory_review_store()
    ids = iter(range(1, 100)).__next__
    first = ProposalService(next_gid=ids, business_review_store=store)
    proposal = first.detect(
        capability_id="person.height.read", capability_version_gid=202, base_snapshot_gid=501,
        previous_hash=HASH_2, proposed_descriptor_hash=HASH_1, evidence_hash=HASH_2,
        submitted_by_gid="author", idempotency_key="detect", review_kind="business_definition",
    )
    draft = first.transition(proposal.proposal_gid, "draft", expected_row_version=proposal.row_version, idempotency_key="draft")
    submitted = first.transition(draft.proposal_gid, "submitted", expected_row_version=draft.row_version, idempotency_key="submitted")
    checking = first.transition(submitted.proposal_gid, "checking", expected_row_version=submitted.row_version, idempotency_key="checking")
    pending = first.transition(checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version, idempotency_key="pending")
    second = ProposalService(next_gid=iter(range(100, 200)).__next__, business_review_store=store)
    reviewer = ReviewerContext("reviewer", ("super_admin",), (), ())

    barrier = Barrier(2)
    def decide(service: ProposalService, decision: str, key: str):
        barrier.wait()
        try:
            return service.decide_business_definition(
                pending.proposal_gid, reviewer_context=reviewer, definition_hash=HASH_1,
                current_definition_hash=HASH_1, decision=decision, decision_reason="Evidence sufficient",
                expected_row_version=pending.row_version, idempotency_key=key,
            )
        except WorkflowError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(pool.submit(decide, service, decision, key)
                        for service, decision, key in ((first, "approved", "approve"), (second, "rejected", "reject")))
        outcomes = tuple(future.result() for future in futures)

    assert sum(isinstance(outcome, WorkflowError) for outcome in outcomes) == 1
    assert sum(getattr(outcome, "status", None) in {"approved", "rejected"} for outcome in outcomes) == 1
    assert next(outcome for outcome in outcomes if isinstance(outcome, WorkflowError)).args == ("row_version_conflict",)
    assert len(store._business_reviews) == 1


def test_durable_supersession_survives_a_fresh_workflow_and_displaces_old_business_review():
    store = _memory_review_store()
    ids = iter(range(1, 200)).__next__
    first = ProposalService(next_gid=ids, business_review_store=store)
    old = first.detect(
        capability_id="person.height.read", capability_version_gid=202, base_snapshot_gid=501,
        previous_hash=HASH_2, proposed_descriptor_hash=HASH_1, evidence_hash=HASH_2,
        submitted_by_gid="author", idempotency_key="old", review_kind="business_definition",
    )
    for status in ("draft", "submitted", "checking", "pending_approval"):
        old = first.transition(old.proposal_gid, status, expected_row_version=old.row_version, idempotency_key=f"old-{status}")

    replacement = ProposalService(next_gid=ids, business_review_store=store).detect(
        capability_id="person.height.read", capability_version_gid=202, base_snapshot_gid=501,
        previous_hash=HASH_1, proposed_descriptor_hash=HASH_A, evidence_hash=HASH_2,
        submitted_by_gid="other", idempotency_key="replacement", review_kind="business_definition",
    )

    reloaded = ProposalService(next_gid=ids, business_review_store=store)
    displaced = reloaded.get(old.proposal_gid)
    assert replacement.proposed_descriptor_hash == HASH_A
    assert displaced.status == "superseded"
    with pytest.raises(WorkflowError, match="review_subject_type_invalid"):
        reloaded.decide_business_definition(
            displaced.proposal_gid, reviewer_context=ReviewerContext("reviewer", ("super_admin",), (), ()),
            definition_hash=HASH_1, current_definition_hash=HASH_1, decision="approved",
            decision_reason="Evidence sufficient", expected_row_version=displaced.row_version,
            idempotency_key="old-review",
        )


def test_business_reviews_are_append_only_and_latest_exact_hash_is_current():
    store = _memory_review_store()
    first = CapabilityBusinessReview(101, 202, HASH_1, "changes_requested", "Add evidence", "9001", "super_admin", NOW, 701, 501)
    second = CapabilityBusinessReview(102, 202, HASH_1, "approved", "Evidence added", "9001", "super_admin", NOW + timedelta(seconds=1), 701, 501)

    store.save_business_review(first)
    store.save_business_review(second)

    assert store.current_business_review(202, HASH_1) == second
    with pytest.raises(ImmutableRecordError, match="business_review_gid_already_exists"):
        store.save_business_review(first)


@pytest.mark.parametrize("decision", ("rejected", "changes_requested"))
def test_current_business_review_does_not_resurrect_a_superseded_approval(decision: str):
    """A later non-approval is current evidence, so older approval is expired."""
    store = _memory_review_store()
    store.save_business_review(CapabilityBusinessReview(
        101, 202, HASH_1, "approved", "Evidence is sufficient", "9001", "super_admin",
        NOW, 701, 501,
    ))
    store.save_business_review(CapabilityBusinessReview(
        102, 202, HASH_1, decision, "Needs another review", "9002", "super_admin",
        NOW + timedelta(seconds=1), 702, 501,
    ))

    assert store.current_business_review(202, HASH_1) is None


def test_current_business_review_uses_append_order_not_client_timestamp():
    store = _memory_review_store()
    store.save_business_review(CapabilityBusinessReview(
        101, 202, HASH_1, "approved", "Evidence is sufficient", "9001", "super_admin",
        NOW + timedelta(days=1), 701, 501,
    ))
    store.save_business_review(CapabilityBusinessReview(
        102, 202, HASH_1, "rejected", "Evidence was withdrawn", "9002", "super_admin",
        NOW, 702, 501,
    ))

    assert store.current_business_review(202, HASH_1) is None


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


class _BusinessDecisionCursor:
    def __init__(self, connection):
        self.connection, self.row, self.rows, self.rowcount = connection, None, [], 0

    def execute(self, query, parameters=()):
        self.connection.calls.append((query, parameters))
        database = self.connection
        if query.startswith("SELECT request_fingerprint"):
            request = database.staged_requests.get(parameters[0])
            self.row = None if request is None else (request[0], request[1])
        elif query.startswith("INSERT INTO workmanship_base_capability_change_proposals"):
            proposal_gid, version_gid, snapshot_gid, definition_hash, review_kind, _risk, status, submitted_by, _submitted, _summary, change_json, row_version = parameters
            payload = __import__("json").loads(change_json)
            database.staged_proposal = Proposal(
                proposal_gid, payload["capability_id"], version_gid, snapshot_gid,
                payload["previous_hash"], definition_hash, payload["evidence_hash"], str(submitted_by),
                status=status, row_version=row_version, review_kind=payload["review_kind"],
            )
        elif query.startswith("UPDATE workmanship_base_capability_change_proposals"):
            status, proposal_gid, row_version, *state = parameters
            proposal = database.staged_proposal
            expected_status = "pending_approval" if len(state) == 1 else state[0]
            definition_hash = state[-1]
            self.rowcount = int(
                proposal.proposal_gid == proposal_gid and proposal.row_version == row_version
                and proposal.status == expected_status and proposal.proposed_descriptor_hash == definition_hash
            )
            if self.rowcount:
                database.staged_proposal = replace(proposal, status=status, row_version=row_version + 1)
        elif query.startswith("INSERT INTO workmanship_base_capability_business_reviews"):
            database.staged_reviews[parameters[0]] = tuple(parameters)
        elif query.startswith("INSERT INTO workmanship_base_capability_business_review_requests"):
            if database.fail_request_insert:
                raise RuntimeError("request_insert_failed")
            database.staged_requests[parameters[0]] = (parameters[1], parameters[2])
        elif query.startswith("SELECT business_review_gid, proposal_gid, decision"):
            self.rows = [
                (review[0], review[1], review[4], review[6], review[8], review[3], review[5], review[9])
                for review in database.committed_reviews.values()
                if review[1] == parameters[0]
            ]
        elif query.startswith("SELECT proposal_gid, capability_version_gid"):
            proposal = database.committed_proposal
            row = _business_proposal_row(proposal)
            if "WHERE proposal_gid" in query:
                self.row = row if proposal.proposal_gid == parameters[0] else None
            else:
                self.rows = [row]

    def fetchone(self): return self.row
    def fetchall(self): return self.rows
    def close(self): pass


class _BusinessDecisionConnection:
    def __init__(self, proposal, *, fail_request_insert=False):
        self.committed_proposal = self.staged_proposal = proposal
        self.committed_reviews: dict[int, tuple[object, ...]] = {}
        self.staged_reviews: dict[int, tuple[object, ...]] = {}
        self.committed_requests: dict[str, tuple[object, int]] = {}
        self.staged_requests: dict[str, tuple[object, int]] = {}
        self.fail_request_insert, self.calls = fail_request_insert, []
        self.commits = self.rollbacks = 0

    def cursor(self): return _BusinessDecisionCursor(self)
    def commit(self):
        self.committed_proposal = self.staged_proposal
        self.committed_reviews = dict(self.staged_reviews)
        self.committed_requests = dict(self.staged_requests)
        self.commits += 1
    def rollback(self):
        self.staged_proposal = self.committed_proposal
        self.staged_reviews = dict(self.committed_reviews)
        self.staged_requests = dict(self.committed_requests)
        self.rollbacks += 1


class _SharedBusinessDatabase:
    """Transactional SQL fixture with connection-local writes and one shared commit state."""

    def __init__(self, proposal=None):
        self.proposals = {} if proposal is None else {proposal.proposal_gid: proposal}
        self.reviews: dict[int, tuple[object, ...]] = {}
        self.requests: dict[str, tuple[object, int]] = {}
        self.sequence_value = max(self.proposals, default=0)
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._lock = RLock()

    def connect(self):
        return _SharedBusinessConnection(self)


class _SharedBusinessConnection:
    def __init__(self, database):
        self.database = database
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.commits = self.rollbacks = 0
        self.last_insert_id = 0
        self._in_transaction = False

    def _begin(self):
        if self._in_transaction:
            return
        self.database._lock.acquire()
        self._in_transaction = True
        self.staged_proposals = dict(self.database.proposals)
        self.staged_reviews = dict(self.database.reviews)
        self.staged_requests = dict(self.database.requests)
        self.staged_sequence_value = self.database.sequence_value

    def _view(self, name):
        if self._in_transaction:
            return getattr(self, f"staged_{name}")
        with self.database._lock:
            value = getattr(self.database, name)
            return dict(value) if isinstance(value, dict) else value

    def cursor(self):
        return _SharedBusinessCursor(self)

    def commit(self):
        if self._in_transaction:
            self.database.proposals = dict(self.staged_proposals)
            self.database.reviews = dict(self.staged_reviews)
            self.database.requests = dict(self.staged_requests)
            self.database.sequence_value = self.staged_sequence_value
            self._in_transaction = False
            self.database._lock.release()
        self.commits += 1

    def rollback(self):
        if self._in_transaction:
            self._in_transaction = False
            self.database._lock.release()
        self.rollbacks += 1


class _SharedBusinessCursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None
        self.rows = []
        self.rowcount = 0

    def execute(self, query, parameters=()):
        parameters = tuple(parameters)
        self.connection.calls.append((query, parameters))
        self.connection.database.calls.append((query, parameters))
        self.row, self.rows, self.rowcount = None, [], 0
        connection = self.connection
        if query.startswith("SELECT request_fingerprint"):
            connection._begin()
            request = connection.staged_requests.get(parameters[0])
            self.row = None if request is None else (request[0], request[1])
        elif query.startswith("INSERT INTO workmanship_display_id_counters"):
            connection._begin()
            connection.staged_sequence_value = max(
                connection.staged_sequence_value,
                max(connection.staged_proposals, default=0),
            )
            self.rowcount = 1
        elif query.startswith("UPDATE workmanship_display_id_counters"):
            connection._begin()
            connection.staged_sequence_value += 1
            connection.last_insert_id = connection.staged_sequence_value
            self.rowcount = 1
        elif query.startswith("SELECT LAST_INSERT_ID()"):
            self.row = (connection.last_insert_id,)
        elif query.startswith("INSERT INTO workmanship_base_capability_change_proposals"):
            connection._begin()
            proposal_gid, version_gid, snapshot_gid, definition_hash, review_kind, _risk, status, submitted_by, _submitted, _summary, change_json, row_version = parameters
            payload = __import__("json").loads(change_json)
            proposal = Proposal(
                proposal_gid, payload["capability_id"], version_gid, snapshot_gid,
                payload["previous_hash"], definition_hash, payload["evidence_hash"], str(submitted_by),
                status=status, row_version=row_version, review_kind=payload["review_kind"],
            )
            if proposal_gid in connection.staged_proposals and "ON DUPLICATE KEY UPDATE" not in query:
                raise RuntimeError("duplicate proposal_gid")
            connection.staged_proposals[proposal_gid] = proposal
            self.rowcount = 1
        elif query.startswith("UPDATE workmanship_base_capability_change_proposals"):
            connection._begin()
            status, proposal_gid, row_version, *state = parameters
            proposal = connection.staged_proposals.get(proposal_gid)
            expected_status = "pending_approval" if len(state) == 1 else state[0]
            definition_hash = state[-1]
            self.rowcount = int(
                proposal is not None
                and proposal.row_version == row_version
                and proposal.status == expected_status
                and proposal.proposed_descriptor_hash == definition_hash
            )
            if self.rowcount:
                connection.staged_proposals[proposal_gid] = replace(
                    proposal, status=status, row_version=row_version + 1,
                )
        elif query.startswith("INSERT INTO workmanship_base_capability_business_reviews"):
            connection._begin()
            if parameters[0] in connection.staged_reviews:
                raise RuntimeError("duplicate business_review_gid")
            connection.staged_reviews[parameters[0]] = parameters
            self.rowcount = 1
        elif query.startswith("INSERT INTO workmanship_base_capability_business_review_requests"):
            connection._begin()
            if parameters[0] in connection.staged_requests:
                raise RuntimeError("duplicate idempotency_key")
            connection.staged_requests[parameters[0]] = (parameters[1], parameters[2])
            self.rowcount = 1
        elif query.startswith("SELECT business_review_gid, proposal_gid, decision"):
            reviews = connection._view("reviews")
            self.rows = [
                (review[0], review[1], review[4], review[6], review[8], review[3], review[5], review[9])
                for review in reviews.values() if review[1] == parameters[0]
            ]
        elif query.startswith("SELECT proposal_gid, capability_version_gid"):
            proposals = connection._view("proposals")
            if "WHERE proposal_gid" in query:
                proposal = proposals.get(parameters[0])
                self.row = None if proposal is None else _business_proposal_row(proposal)
            else:
                self.rows = [_business_proposal_row(proposal) for proposal in sorted(
                    proposals.values(), key=lambda item: item.proposal_gid,
                )]

    def fetchone(self): return self.row
    def fetchall(self): return self.rows
    def close(self): pass


def _pending_business_proposal() -> Proposal:
    return Proposal(
        701, "person.height.read", 202, 501, HASH_2, HASH_1, HASH_2, "1",
        status="pending_approval", row_version=5, review_kind="business_definition",
    )


def _business_proposal_row(proposal: Proposal):
    return (
        proposal.proposal_gid, proposal.capability_version_gid, proposal.base_snapshot_gid,
        proposal.proposed_descriptor_hash, proposal.status, proposal.submitted_by_gid,
        __import__("json").dumps({
            "capability_id": proposal.capability_id, "previous_hash": proposal.previous_hash,
            "evidence_hash": proposal.evidence_hash, "review_kind": proposal.review_kind,
        }), proposal.row_version,
    )


def _super_admin_context(user_gid="9001"):
    return CapabilityContext(
        user_gid=user_gid,
        effective_identity=ConsumerIdentity(
            actor=ActorIdentity(user_id=user_gid, authentication_method="test", authenticated_at=NOW),
            tenant=TenantIdentity(tenant_id="tenant", membership="member", active_roles=("super_admin",)),
            consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
        ),
    )


def _base_owner_context(user_gid="9003"):
    return CapabilityContext(
        user_gid=user_gid,
        active_roles=("base_owner",),
        permissions=("system.capability.govern",),
        owned_domains=("base",),
    )


def _business_snapshot(snapshot_gid: int, capability_version_gid: int, definition_hash: str):
    return SimpleNamespace(
        snapshot_gid=snapshot_gid,
        entries=(SimpleNamespace(
            capability_version_gid=capability_version_gid,
            capability_id="person.height.read",
            major_version=1,
        ),),
        document=SimpleNamespace(capabilities=(SimpleNamespace(
            capability_id="person.height.read",
            major_version=1,
            descriptor={"business_definition_hash": definition_hash},
        ),)),
    )


def _persistent_service(database: _SharedBusinessDatabase, *snapshots):
    connection = database.connect()
    store = SqlGovernanceStore(connection)
    indexed = {snapshot.snapshot_gid: snapshot for snapshot in snapshots}
    store.get_snapshot = indexed.get
    store.latest_snapshot = lambda: indexed[max(indexed)] if indexed else None
    return CapabilityGovernanceService(store=store), connection


def _proposal_payload(review_kind: str, idempotency_key: str):
    if review_kind == "business_definition":
        return {
            "capability_id": "person.height.read", "capability_version_gid": "202",
            "base_snapshot_gid": "501", "previous_hash": HASH_2,
            "proposed_descriptor_hash": HASH_1, "definition_hash": HASH_1,
            "evidence_hash": HASH_2, "idempotency_key": idempotency_key,
        }
    return {
        "capability_id": "person.height.write", "capability_version_gid": "203",
        "base_snapshot_gid": "501", "previous_hash": HASH_2,
        "proposed_descriptor_hash": HASH_A,
        "evidence_hash": HASH_2, "idempotency_key": idempotency_key,
    }


@pytest.mark.parametrize("order", (
    ("standard", "business_definition"),
    ("business_definition", "standard"),
))
def test_fresh_memory_services_share_one_proposal_identity_namespace(order):
    store = MemoryGovernanceStore()
    created = {}
    for index, review_kind in enumerate(order, start=1):
        service = CapabilityGovernanceService(store=store)
        created[review_kind] = service.base_capability_proposal_submit(
            _proposal_payload(review_kind, f"memory-{review_kind}"),
            _super_admin_context(str(index)),
        )["proposal"]

    restarted = CapabilityGovernanceService(store=store)
    rows = restarted.base_capability_proposal_search({}, _super_admin_context())["items"]

    assert len({proposal.proposal_gid for proposal in created.values()}) == 2
    assert {
        (row["proposal_gid"], row["review_type"], row["status"])
        for row in rows
    } == {
        (str(created[review_kind].proposal_gid), review_kind, "submitted")
        for review_kind in order
    }
    assert {
        restarted._proposals.get(proposal.proposal_gid).capability_id
        for proposal in created.values()
    } == {"person.height.read", "person.height.write"}


def test_memory_duplicate_proposal_create_is_rejected_without_mutation():
    store = MemoryGovernanceStore()
    original = Proposal(
        701, "person.height.read", 202, 501, HASH_2, HASH_1, HASH_2, "1",
    )
    collision = replace(original, capability_id="person.height.write", proposed_descriptor_hash=HASH_A)

    store.save_workflow_proposal(original)
    with pytest.raises(ImmutableRecordError, match="workflow_proposal_gid_already_exists"):
        store.save_workflow_proposal(collision)

    assert store.get_workflow_proposal(701) == original
    assert store.list_workflow_proposals() == (original,)


def test_sql_duplicate_proposal_create_is_rejected_without_mutation():
    original = Proposal(
        701, "person.height.read", 202, 501, HASH_2, HASH_1, HASH_2, "1",
    )
    collision = replace(original, capability_id="person.height.write", proposed_descriptor_hash=HASH_A)
    database = _SharedBusinessDatabase(original)
    store = SqlGovernanceStore(database.connect())

    with pytest.raises(ImmutableRecordError, match="workflow_proposal_gid_already_exists"):
        store.save_workflow_proposal(collision)

    assert database.proposals == {701: original}


@pytest.mark.parametrize("order", (
    ("standard", "business_definition"),
    ("business_definition", "standard"),
))
def test_fresh_sql_services_share_proposal_ids_and_address_each_type_after_restart(order):
    database = _SharedBusinessDatabase()
    snapshot = _business_snapshot(501, 202, HASH_1)
    created = {}
    for index, review_kind in enumerate(order, start=1):
        service, _ = _persistent_service(database, snapshot)
        created[review_kind] = service.base_capability_proposal_submit(
            _proposal_payload(review_kind, f"sql-{review_kind}"),
            _super_admin_context(str(index)),
        )["proposal"]

    assert len({proposal.proposal_gid for proposal in created.values()}) == 2
    assert set(database.proposals) == {
        proposal.proposal_gid for proposal in created.values()
    }

    restarted, _ = _persistent_service(database, snapshot)
    rows = restarted.base_capability_proposal_search({}, _super_admin_context())["items"]
    assert {
        (row["proposal_gid"], row["review_type"], row["status"])
        for row in rows
    } == {
        (str(created[review_kind].proposal_gid), review_kind, "submitted")
        for review_kind in order
    }

    standard = restarted._proposals.get(created["standard"].proposal_gid)
    standard = restarted._proposals.transition(
        standard.proposal_gid, "checking", expected_row_version=standard.row_version,
        idempotency_key="standard-checking",
    )
    standard = restarted._proposals.transition(
        standard.proposal_gid, "pending_approval", expected_row_version=standard.row_version,
        idempotency_key="standard-pending",
    )
    standard = restarted.base_capability_review_decide({
        "proposal_gid": str(standard.proposal_gid), "stage": "base_owner",
        "decision": "approved", "row_version": str(standard.row_version),
        "idempotency_key": "standard-review",
    }, _base_owner_context())["proposal"]

    business = restarted._proposals.get(created["business_definition"].proposal_gid)
    business = restarted._proposals.transition(
        business.proposal_gid, "checking", expected_row_version=business.row_version,
        idempotency_key="business-checking",
    )
    business = restarted._proposals.transition(
        business.proposal_gid, "pending_approval", expected_row_version=business.row_version,
        idempotency_key="business-pending",
    )
    business = restarted.base_capability_review_decide({
        "proposal_gid": str(business.proposal_gid), "definition_hash": HASH_1,
        "decision": "approved", "decision_reason": "Evidence sufficient",
        "row_version": str(business.row_version), "idempotency_key": "business-review",
    }, _super_admin_context("9004"))["proposal"]

    final, _ = _persistent_service(database, snapshot)
    assert final._proposals.get(standard.proposal_gid).status == "approved"
    assert final._proposals.get(business.proposal_gid).status == "approved"
    assert final._proposals.get(standard.proposal_gid).review_kind == "standard"
    assert final._proposals.get(business.proposal_gid).review_kind == "business_definition"


def test_sql_business_decision_is_single_transaction_and_failure_rolls_back_every_row():
    proposal = _pending_business_proposal()
    review = CapabilityBusinessReview(801, 202, HASH_1, "approved", "Evidence sufficient", "9001", "super_admin", NOW, 701, 501)
    resolved = replace(proposal, status="approved", row_version=6)
    fingerprint = (701, HASH_1, "approved", "Evidence sufficient", 5, "9001")
    connection = _BusinessDecisionConnection(proposal)

    result = SqlGovernanceStore(connection).decide_business_review_atomic(
        proposal, resolved, review, fingerprint, "decision-1",
    )

    assert result.status == "approved" and result.row_version == 6
    assert connection.commits == 1 and connection.rollbacks == 0
    assert connection.committed_proposal == resolved
    assert set(connection.committed_reviews) == {801}
    assert set(connection.committed_requests) == {"decision-1"}
    write_queries = [query for query, _ in connection.calls if query.startswith(("UPDATE", "INSERT"))]
    assert [query.split()[0:3] for query in write_queries] == [
        ["UPDATE", "workmanship_base_capability_change_proposals", "SET"],
        ["INSERT", "INTO", "workmanship_base_capability_business_reviews"],
        ["INSERT", "INTO", "workmanship_base_capability_business_review_requests"],
    ]

    failing = _BusinessDecisionConnection(proposal, fail_request_insert=True)
    with pytest.raises(RuntimeError, match="request_insert_failed"):
        SqlGovernanceStore(failing).decide_business_review_atomic(
            proposal, resolved, review, fingerprint, "decision-1",
        )
    assert failing.rollbacks == 1 and failing.commits == 0
    assert failing.committed_proposal == proposal
    assert failing.committed_reviews == {} and failing.committed_requests == {}


def test_sql_persisted_proposal_cas_allows_one_of_two_independent_workflow_instances():
    connection = _BusinessDecisionConnection(_pending_business_proposal())
    first = ProposalService(next_gid=iter(range(801, 900)).__next__, business_review_store=SqlGovernanceStore(connection))
    second = ProposalService(next_gid=iter(range(901, 1000)).__next__, business_review_store=SqlGovernanceStore(connection))
    reviewer = ReviewerContext("9001", ("super_admin",), (), ())
    barrier = Barrier(2)

    def decide(service: ProposalService, decision: str, key: str):
        barrier.wait()
        try:
            return service.decide_business_definition(
                701, reviewer_context=reviewer, definition_hash=HASH_1,
                current_definition_hash=HASH_1, decision=decision,
                decision_reason="Evidence sufficient", expected_row_version=5,
                idempotency_key=key,
            )
        except WorkflowError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.submit(decide, service, decision, key)
                         for service, decision, key in ((first, "approved", "approve"), (second, "rejected", "reject")))
        outcomes = tuple(future.result() for future in outcomes)

    assert sum(isinstance(outcome, WorkflowError) for outcome in outcomes) == 1
    assert sum(getattr(outcome, "status", None) in {"approved", "rejected"} for outcome in outcomes) == 1
    assert len(connection.committed_reviews) == 1
    assert any("WHERE proposal_gid = %s AND row_version = %s AND status = 'pending_approval'" in query
               for query, _ in connection.calls)


def test_sql_cas_race_uses_two_services_and_trusted_identities_over_separate_connections():
    database = _SharedBusinessDatabase(_pending_business_proposal())
    snapshot = _business_snapshot(501, 202, HASH_1)
    first, first_connection = _persistent_service(database, snapshot)
    second, second_connection = _persistent_service(database, snapshot)
    assert first_connection is not second_connection
    barrier = Barrier(2)

    def decide(service, decision, key, reviewer_gid):
        barrier.wait()
        try:
            return service.base_capability_review_decide({
                "proposal_gid": "701", "definition_hash": HASH_1,
                "decision": decision, "decision_reason": "Evidence sufficient",
                "row_version": "5", "idempotency_key": key,
            }, _super_admin_context(reviewer_gid))["proposal"]
        except CapabilityBusinessError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.submit(decide, service, decision, key, reviewer_gid)
                         for service, decision, key, reviewer_gid in (
                             (first, "approved", "approve", "9001"),
                             (second, "rejected", "reject", "9002"),
                         ))
        outcomes = tuple(future.result() for future in outcomes)
    failures = tuple(outcome for outcome in outcomes if isinstance(outcome, CapabilityBusinessError))
    assert len(failures) == 1 and failures[0].code == "row_version_conflict"
    assert sum(getattr(outcome, "status", None) in {"approved", "rejected"} for outcome in outcomes) == 1
    assert len(database.reviews) == 1

    restarted, _ = _persistent_service(database, snapshot)
    reloaded = restarted._proposals.get(701)
    assert reloaded.status in {"approved", "rejected"}
    assert len(reloaded.reviews) == 1


def test_fresh_persistent_service_allocates_a_distinct_proposal_and_preserves_supersession():
    database = _SharedBusinessDatabase()
    old_snapshot = _business_snapshot(501, 202, HASH_1)
    replacement_snapshot = _business_snapshot(502, 203, HASH_A)
    first, first_connection = _persistent_service(database, old_snapshot)
    old = first.base_capability_proposal_submit({
        "capability_id": "person.height.read", "capability_version_gid": "202",
        "base_snapshot_gid": "501", "previous_hash": HASH_2,
        "proposed_descriptor_hash": HASH_1, "definition_hash": HASH_1,
        "evidence_hash": HASH_2, "idempotency_key": "old-proposal",
    }, _super_admin_context("1"))["proposal"]
    checking = first._proposals.transition(
        old.proposal_gid, "checking", expected_row_version=old.row_version,
        idempotency_key="old-checking",
    )
    pending = first._proposals.transition(
        checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version,
        idempotency_key="old-pending",
    )

    restarted, second_connection = _persistent_service(database, old_snapshot, replacement_snapshot)
    replacement = restarted.base_capability_proposal_submit({
        "capability_id": "person.height.read", "capability_version_gid": "203",
        "base_snapshot_gid": "502", "previous_hash": HASH_1,
        "proposed_descriptor_hash": HASH_A, "definition_hash": HASH_A,
        "evidence_hash": HASH_2, "idempotency_key": "replacement-proposal",
    }, _super_admin_context("2"))["proposal"]

    assert first_connection is not second_connection
    assert replacement.proposal_gid != pending.proposal_gid
    displaced = restarted._proposals.get(pending.proposal_gid)
    assert displaced.status == "superseded"
    assert restarted._proposals.get(replacement.proposal_gid) == replacement
    assert set(database.proposals) == {pending.proposal_gid, replacement.proposal_gid}
    proposal_inserts = [query for query, _ in database.calls if query.startswith(
        "INSERT INTO workmanship_base_capability_change_proposals"
    )]
    assert proposal_inserts and all("ON DUPLICATE KEY UPDATE" not in query for query in proposal_inserts)

    with pytest.raises(CapabilityBusinessError) as error:
        restarted.base_capability_review_decide({
            "proposal_gid": str(displaced.proposal_gid), "definition_hash": HASH_1,
            "decision": "approved", "decision_reason": "Evidence sufficient",
            "row_version": str(displaced.row_version), "idempotency_key": "review-displaced",
        }, _super_admin_context())
    assert error.value.code == "review_subject_hash_mismatch"


def test_persistent_proposal_port_does_not_enable_in_memory_waiver_or_release_after_restart():
    database = _SharedBusinessDatabase()
    for index in (1, 2):
        service, _ = _persistent_service(database)
        with pytest.raises(CapabilityBusinessError) as waiver_error:
            service.base_capability_waiver_grant({
                "finding_gid": "11", "capability_version_gid": "202", "scope": "one finding",
                "reason": "Temporary exception", "code_hash": HASH_1, "catalog_hash": HASH_1,
                "evidence_hash": HASH_1, "expires_at": (NOW + timedelta(days=1)).isoformat(),
                "idempotency_key": f"waiver-{index}",
            }, _super_admin_context())
        assert waiver_error.value.code == "governance_persistence_unavailable"

        with pytest.raises(CapabilityBusinessError) as release_error:
            service.base_capability_release_gate_evaluate(
                {"idempotency_key": f"release-{index}"}, _super_admin_context(),
            )
        assert release_error.value.code == "governance_persistence_unavailable"


def test_persistent_runtime_rejects_in_memory_waiver_and_release_services_on_a_workflow_port():
    database = _SharedBusinessDatabase()
    store = SqlGovernanceStore(database.connect())
    ids = iter(range(1, 20)).__next__
    workflow_port = SimpleNamespace(
        waiver_service=WaiverService(next_gid=ids),
        release_gate=ReleaseGate(next_gid=ids),
    )
    service = CapabilityGovernanceService(store=store, workflow_port=workflow_port)

    with pytest.raises(CapabilityBusinessError) as waiver_error:
        service.base_capability_waiver_grant({
            "finding_gid": "11", "capability_version_gid": "202", "scope": "one finding",
            "reason": "Temporary exception", "code_hash": HASH_1, "catalog_hash": HASH_1,
            "evidence_hash": HASH_1, "expires_at": (NOW + timedelta(days=1)).isoformat(),
            "idempotency_key": "in-memory-waiver",
        }, _super_admin_context())
    assert waiver_error.value.code == "governance_persistence_unavailable"

    with pytest.raises(CapabilityBusinessError) as release_error:
        service.base_capability_release_gate_evaluate(
            {"idempotency_key": "in-memory-release"}, _super_admin_context(),
        )
    assert release_error.value.code == "governance_persistence_unavailable"


def test_persistence_guards_follow_the_selected_workflow_services():
    database = _SharedBusinessDatabase()
    store = SqlGovernanceStore(database.connect())
    ids = iter(range(1, 20)).__next__
    workflow_port = SimpleNamespace(
        waiver_service=WaiverService(next_gid=ids),
        release_gate=ReleaseGate(next_gid=ids),
    )
    service = CapabilityGovernanceService(
        store=store,
        waiver_service=SimpleNamespace(persistent=True),
        release_gate=SimpleNamespace(persistent=True),
        workflow_port=workflow_port,
    )

    with pytest.raises(CapabilityBusinessError) as waiver_error:
        service.base_capability_waiver_grant({
            "finding_gid": "11", "capability_version_gid": "202", "scope": "one finding",
            "reason": "Temporary exception", "code_hash": HASH_1, "catalog_hash": HASH_1,
            "evidence_hash": HASH_1, "expires_at": (NOW + timedelta(days=1)).isoformat(),
            "idempotency_key": "shadowed-waiver",
        }, _super_admin_context())
    assert waiver_error.value.code == "governance_persistence_unavailable"

    with pytest.raises(CapabilityBusinessError) as release_error:
        service.base_capability_release_gate_evaluate(
            {"idempotency_key": "shadowed-release"}, _super_admin_context(),
        )
    assert release_error.value.code == "governance_persistence_unavailable"


def test_default_persistent_service_path_creates_transitions_reviews_and_rehydrates_history():
    database = _SharedBusinessDatabase(_pending_business_proposal())
    snapshot = _business_snapshot(501, 202, HASH_1)
    service, _ = _persistent_service(database, snapshot)
    payload = {
        "capability_id": "person.height.read", "capability_version_gid": "202", "base_snapshot_gid": "501",
        "previous_hash": HASH_2, "proposed_descriptor_hash": HASH_1, "definition_hash": HASH_1,
        "evidence_hash": HASH_2, "idempotency_key": "persistent-create",
    }

    submitted = service.base_capability_proposal_submit(payload, _super_admin_context("1"))["proposal"]
    checking = service._proposals.transition(submitted.proposal_gid, "checking", expected_row_version=submitted.row_version, idempotency_key="checking")
    pending = service._proposals.transition(checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version, idempotency_key="pending")
    approved = service.base_capability_review_decide({
        "proposal_gid": str(pending.proposal_gid), "definition_hash": HASH_1,
        "decision": "approved", "decision_reason": "Evidence sufficient",
        "row_version": str(pending.row_version), "idempotency_key": "persistent-approve",
    }, _super_admin_context())["proposal"]

    assert approved.status == "approved" and len(approved.reviews) == 1
    restarted, _ = _persistent_service(database, snapshot)
    reloaded = restarted._proposals.get(approved.proposal_gid)
    assert reloaded.status == "approved" and len(reloaded.reviews) == 1
    assert reloaded.reviews[0].decision == "approved"
    assert restarted.base_capability_proposal_search({}, _super_admin_context())["data"]["available"] is True


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


def test_sql_current_business_review_returns_none_for_latest_non_approval():
    connection = _Connection(review_row=(
        102, 202, HASH_1, "changes_requested", "Needs another review", "9002", "super_admin",
        NOW + timedelta(seconds=1), 702, 501,
    ))

    assert SqlGovernanceStore(connection).current_business_review(202, HASH_1) is None
    query = next(query for query, _ in connection.calls if query.startswith("SELECT business_review_gid"))
    assert "ORDER BY business_review_gid DESC" in query


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
        with pytest.raises(ImmutableRecordError, match="(relation_candidate_gid_already_exists|uq_capability_relation_candidate|relation_candidate_immutable_conflict)"):
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


class _SharedRelationDatabase:
    def __init__(self, rows=(), hook=None): self.committed, self.hook, self.upserts = list(rows), hook, 0
    def connect(self): return _SharedRelationConnection(self)


class _SharedRelationConnection:
    def __init__(self, database): self.database, self.staged, self.calls = database, [], []; self.commits = self.rollbacks = 0
    def cursor(self): return _SharedRelationCursor(self)
    def commit(self):
        for row in self.staged:
            if not any(item[0] == row[0] or (item[1] == row[1] and item[2] == row[2]) for item in self.database.committed):
                self.database.committed.append(row)
        self.staged.clear(); self.commits += 1
    def rollback(self): self.staged.clear(); self.rollbacks += 1


class _SharedRelationCursor:
    def __init__(self, connection): self.connection, self.rows = connection, []
    def execute(self, query, parameters=()):
        self.connection.calls.append((query, parameters))
        if query.startswith("INSERT INTO workmanship_base_capability_relation_candidates"):
            assert "ON DUPLICATE KEY UPDATE relation_candidate_gid=relation_candidate_gid" in query
            row = tuple(parameters); db = self.connection.database
            if not any(item[0] == row[0] or (item[1] == row[1] and item[2] == row[2]) for item in db.committed + self.connection.staged):
                self.connection.staged.append(row)
            db.upserts += 1
            if db.hook: db.hook(db, row)
        elif query.startswith("SELECT relation_candidate_gid"):
            assert "WHERE relation_candidate_gid = %s OR (snapshot_gid = %s AND candidate_hash = %s) FOR UPDATE" in query
            gid, snapshot, digest = parameters
            merged = self.connection.database.committed + self.connection.staged
            # one visible row per exact identity; concurrent conflict retains both.
            self.rows = [item for index, item in enumerate(merged) if (item[0] == gid or (item[1] == snapshot and item[2] == digest)) and item not in merged[:index]]
    def fetchall(self): return self.rows
    def close(self): pass


def test_shared_db_exact_concurrent_replay_current_read_commits_once():
    candidate = _projection().relation_candidates[0]
    def replay(database, row):
        if database.upserts == 1: database.committed.append(row)
    database = _SharedRelationDatabase(hook=replay); connection = database.connect()
    SqlGovernanceStore(connection).save_relation_candidates((candidate,))
    assert connection.commits == 1 and connection.rollbacks == 0 and database.committed == [_relation_row(candidate)]
    assert all("FOR UPDATE" in query for query, _ in connection.calls if query.startswith("SELECT"))


def test_shared_db_conflict_or_collision_and_batch_second_rollback():
    candidate = _projection().relation_candidates[0]
    conflict = replace(candidate, snapshot_gid=999, candidate_hash=HASH_1)
    def conflicting_commit(database, row):
        if database.upserts == 1: database.committed.append(_relation_row(conflict))
    database = _SharedRelationDatabase(hook=conflicting_commit); connection = database.connect()
    with pytest.raises(ImmutableRecordError, match="relation_candidate_gid_already_exists"):
        SqlGovernanceStore(connection).save_relation_candidates((candidate,))
    assert connection.rollbacks == 1 and database.committed == [_relation_row(conflict)]
    row_a = _relation_row(conflict); row_b = _relation_row(replace(candidate, relation_candidate_gid=999))
    collision = _SharedRelationDatabase((row_a, row_b)).connect()
    with pytest.raises(ImmutableRecordError): SqlGovernanceStore(collision).save_relation_candidates((candidate,))
    assert collision.rollbacks == 1
    first = replace(candidate, relation_candidate_gid=404, candidate_hash=HASH_1)
    second = replace(candidate, relation_candidate_gid=405, candidate_hash=HASH_A)
    def second_conflict(database, row):
        if database.upserts == 2: database.committed.append(_relation_row(replace(second, snapshot_gid=999, candidate_hash=HASH_2)))
    batch_database = _SharedRelationDatabase(hook=second_conflict); batch = batch_database.connect()
    with pytest.raises(ImmutableRecordError): SqlGovernanceStore(batch).save_relation_candidates((first, second))
    assert batch.rollbacks == 1 and all(row[0] != first.relation_candidate_gid for row in batch_database.committed)
