from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from time import sleep

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capability_governance_test.service import CapabilityGovernanceService
from backend.capability_governance_test.contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS
from backend.capability_governance_test.provider import _safe_response
from backend.capabilities.validation_next import validate_payload
from backend.capability_v2.contracts import (
    ActorIdentity,
    AutomationLevel,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    DelegationContext,
    TenantIdentity,
)


NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)
HASH = "sha256:" + "a" * 64
OTHER_HASH = "sha256:" + "b" * 64


class _ReviewStore:
    persistent = False

    def __init__(self, definition_hash: str = HASH) -> None:
        capability = SimpleNamespace(
            capability_id="base.capability_registry.search",
            major_version=1,
            descriptor={
                "business_definition_hash": definition_hash,
                "business_effect": "Operators can find governed capabilities.",
                "business_invariants": ({"rule_id": "catalog.search.filtered"},),
            },
            business_rules=({"rule_id": "catalog.search.filtered"},),
            business_maturity=SimpleNamespace(level="L4", reason_codes=("machine_reviewed",)),
        )
        self.snapshot = SimpleNamespace(
            snapshot_gid=31,
            document=SimpleNamespace(capabilities=(capability,)),
            entries=(SimpleNamespace(
                capability_id="base.capability_registry.search",
                capability_version_gid=17,
                major_version=1,
            ),),
        )
        self.current_snapshot = self.snapshot
        self.reviews = []
        self.relation_candidates = ()

    def latest_snapshot(self):
        return self.current_snapshot

    def get_snapshot(self, snapshot_gid):
        return self.snapshot if snapshot_gid == self.snapshot.snapshot_gid else None

    def save_business_review(self, review):
        self.reviews.append(review)

    def current_business_review(self, capability_version_gid, definition_hash):
        matches = [
            review for review in self.reviews
            if review.capability_version_gid == capability_version_gid
            and review.definition_hash == definition_hash
        ]
        return matches[-1] if matches else None

    def list_relation_candidates(self, snapshot_gid):
        assert snapshot_gid == 31
        return self.relation_candidates


def _context(
    *,
    user_gid: str = "author",
    effective_roles: tuple[str, ...] = (),
    claimed_roles: tuple[str, ...] = (),
    consumer_type: ConsumerType = ConsumerType.WEB,
    delegated: bool = False,
    service_identity: bool = False,
) -> CapabilityContext:
    identity = ConsumerIdentity(
        actor=ActorIdentity(
            **({"service_id": "governance-service"} if service_identity else {"user_id": user_gid}),
            authentication_method="test", authenticated_at=NOW,
        ),
        tenant=TenantIdentity(tenant_id="tenant", membership="member", active_roles=effective_roles),
        consumer=ConsumerDescriptor(type=consumer_type, consumer_id="ai00.web"),
        delegation=(DelegationContext(
            delegation_id="delegation", delegated_by="author", capability_scopes=("*",),
            resource_scopes=("*",), data_scopes=("*",), catalog_release="catalog",
            maximum_automation_level=AutomationLevel.A0, expires_at=NOW,
        ) if delegated else None),
    )
    return CapabilityContext(
        user_gid=user_gid,
        active_roles=claimed_roles,
        effective_identity=identity,
    )


def _proposal_payload(**overrides):
    payload = {
        "capability_id": "base.capability_registry.search",
        "capability_version_gid": "17",
        "base_snapshot_gid": "31",
        "previous_hash": OTHER_HASH,
        # P1: this durable legacy field pins the canonical business hash.
        "proposed_descriptor_hash": HASH,
        "definition_hash": HASH,
        "evidence_hash": "sha256:" + "e" * 64,
        "idempotency_key": "proposal-business",
    }
    payload.update(overrides)
    return payload


def _pending_business_proposal(service: CapabilityGovernanceService):
    proposal = service.base_capability_proposal_submit(_proposal_payload(), _context())["proposal"]
    checking = service._proposals.transition(
        proposal.proposal_gid, "checking", expected_row_version=proposal.row_version,
        idempotency_key="proposal-business-checking",
    )
    return service._proposals.transition(
        checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version,
        idempotency_key="proposal-business-pending",
    )


def _decision_payload(proposal, **overrides):
    payload = {
        "proposal_gid": str(proposal.proposal_gid),
        "definition_hash": HASH,
        "decision": "approved",
        "decision_reason": "The purpose, rule, and current hash are sufficient.",
        "row_version": str(proposal.row_version),
        "idempotency_key": "business-decision",
    }
    payload.update(overrides)
    return payload


def test_business_review_requires_effective_undelegated_web_super_admin():
    service = CapabilityGovernanceService(_ReviewStore())
    proposal = _pending_business_proposal(service)

    with pytest.raises(CapabilityBusinessError, match="reviewer_not_authorized"):
        service.base_capability_review_decide(
            _decision_payload(proposal, role="super_admin"),
            _context(effective_roles=("admin",), claimed_roles=("super_admin",)),
        )

    with pytest.raises(CapabilityBusinessError, match="reviewer_not_authorized"):
        service.base_capability_review_decide(
            _decision_payload(proposal, idempotency_key="agent-decision"),
            _context(effective_roles=("super_admin",), consumer_type=ConsumerType.AGENT),
        )

    for idempotency_key, context in (
        ("delegated-decision", _context(effective_roles=("super_admin",), delegated=True)),
        ("service-decision", _context(effective_roles=("super_admin",), service_identity=True)),
    ):
        with pytest.raises(CapabilityBusinessError, match="reviewer_not_authorized"):
            service.base_capability_review_decide(
                _decision_payload(proposal, idempotency_key=idempotency_key), context,
            )


def test_business_review_rejects_duck_typed_effective_identity():
    service = CapabilityGovernanceService(_ReviewStore())
    proposal = _pending_business_proposal(service)
    spoofed = SimpleNamespace(
        actor=SimpleNamespace(user_id="reviewer", service_id=None),
        tenant=SimpleNamespace(active_roles=("super_admin",)),
        consumer=SimpleNamespace(type="web"),
        delegation=None,
    )
    context = CapabilityContext(user_gid="reviewer", effective_identity=spoofed)

    with pytest.raises(CapabilityBusinessError, match="reviewer_not_authorized"):
        service.base_capability_review_decide(_decision_payload(proposal), context)


def test_business_review_persists_an_exact_hash_approval_and_replays_only_the_same_request():
    store = _ReviewStore()
    service = CapabilityGovernanceService(store)
    proposal = _pending_business_proposal(service)
    payload = _decision_payload(proposal)
    descriptor_before = dict(store.snapshot.document.capabilities[0].descriptor)

    approved = service.base_capability_review_decide(
        payload, _context(user_gid="reviewer", effective_roles=("super_admin",)),
    )
    replay = service.base_capability_review_decide(
        payload, _context(user_gid="reviewer", effective_roles=("super_admin",)),
    )

    assert approved["proposal"] == replay["proposal"]
    assert approved["proposal"].status == "approved"
    assert store.current_business_review(17, HASH).decision == "approved"
    assert store.current_business_review(17, OTHER_HASH) is None
    assert store.snapshot.document.capabilities[0].descriptor == descriptor_before
    with pytest.raises(CapabilityBusinessError, match="idempotency_conflict"):
        service.base_capability_review_decide(
            _decision_payload(proposal, decision="rejected"),
            _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )


def test_business_review_uses_server_timestamp_not_payload_timestamp():
    store = _ReviewStore()
    service = CapabilityGovernanceService(store)
    proposal = _pending_business_proposal(service)

    service.base_capability_review_decide(
        _decision_payload(proposal, decided_at="2000-01-01T00:00:00Z"),
        _context(user_gid="reviewer", effective_roles=("super_admin",)),
    )

    assert store.reviews[-1].decided_at.year != 2000


def test_business_review_rejects_a_missing_pinned_snapshot():
    service = CapabilityGovernanceService(_ReviewStore())
    proposal = service.base_capability_proposal_submit(
        _proposal_payload(base_snapshot_gid="999", idempotency_key="proposal-missing-snapshot"), _context(),
    )["proposal"]
    checking = service._proposals.transition(
        proposal.proposal_gid, "checking", expected_row_version=proposal.row_version,
        idempotency_key="proposal-missing-snapshot-checking",
    )
    pending = service._proposals.transition(
        checking.proposal_gid, "pending_approval", expected_row_version=checking.row_version,
        idempotency_key="proposal-missing-snapshot-pending",
    )

    with pytest.raises(CapabilityBusinessError, match="review_subject_hash_mismatch"):
        service.base_capability_review_decide(
            _decision_payload(pending), _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )


def test_business_review_requires_exact_pinned_and_current_version_subjects():
    store = _ReviewStore()
    service = CapabilityGovernanceService(store)
    proposal = _pending_business_proposal(service)
    store.snapshot.entries = (SimpleNamespace(
        capability_id="base.capability_registry.search", capability_version_gid=17, major_version=2,
    ),)

    with pytest.raises(CapabilityBusinessError, match="review_subject_hash_mismatch"):
        service.base_capability_review_decide(
            _decision_payload(proposal), _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )

    store = _ReviewStore()
    service = CapabilityGovernanceService(store)
    proposal = _pending_business_proposal(service)
    store.current_snapshot = SimpleNamespace(
        snapshot_gid=32,
        document=SimpleNamespace(capabilities=(SimpleNamespace(
            capability_id="base.capability_registry.search", major_version=1,
            descriptor={"business_definition_hash": OTHER_HASH}, business_rules=(), business_maturity=None,
        ),)),
        entries=(SimpleNamespace(
            capability_id="base.capability_registry.search", capability_version_gid=17, major_version=1,
        ),),
    )
    with pytest.raises(CapabilityBusinessError, match="review_subject_hash_mismatch"):
        service.base_capability_review_decide(
            _decision_payload(proposal), _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )


def test_business_review_concurrent_decisions_have_one_winner_and_one_review():
    store = _ReviewStore()
    service = CapabilityGovernanceService(store)
    proposal = _pending_business_proposal(service)
    original_save = store.save_business_review

    def delayed_save(review):
        sleep(0.05)
        original_save(review)
    store.save_business_review = delayed_save

    def decide(decision):
        return service.base_capability_review_decide(
            _decision_payload(proposal, decision=decision, idempotency_key=f"race-{decision}"),
            _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (pool.submit(decide, "approved"), pool.submit(decide, "rejected"))
        outcomes = [future.result() if future.exception() is None else future.exception() for future in futures]

    assert sum(isinstance(result, dict) for result in outcomes) == 1
    assert sum(isinstance(result, CapabilityBusinessError) for result in outcomes) == 1
    assert len(store.reviews) == 1


def test_business_review_persistence_failure_does_not_change_proposal_or_history():
    store = _ReviewStore()
    service = CapabilityGovernanceService(store)
    proposal = _pending_business_proposal(service)

    def fail_save(review):
        raise RuntimeError("database unavailable")
    store.save_business_review = fail_save

    with pytest.raises(CapabilityBusinessError, match="business_review_persistence_failed"):
        service.base_capability_review_decide(
            _decision_payload(proposal), _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )

    assert service._proposals.get(proposal.proposal_gid) == proposal
    assert store.reviews == []


def test_business_review_requires_a_trimmed_bounded_reason():
    service = CapabilityGovernanceService(_ReviewStore())
    proposal = _pending_business_proposal(service)

    with pytest.raises(CapabilityBusinessError, match="invalid_input"):
        service.base_capability_review_decide(
            _decision_payload(proposal, decision_reason="  ", idempotency_key="empty-reason"),
            _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )
    with pytest.raises(CapabilityBusinessError, match="review_reason_invalid"):
        service.base_capability_review_decide(
            _decision_payload(proposal, decision_reason="x" * 2001, idempotency_key="long-reason"),
            _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )


@pytest.mark.parametrize("decision", ("rejected", "changes_requested"))
def test_business_review_records_every_non_approval_decision(decision: str):
    store = _ReviewStore()
    service = CapabilityGovernanceService(store)
    proposal = _pending_business_proposal(service)

    result = service.base_capability_review_decide(
        _decision_payload(proposal, decision=decision, idempotency_key=f"business-{decision}"),
        _context(user_gid="reviewer", effective_roles=("super_admin",)),
    )

    assert store.reviews[-1].decision == decision
    assert result["proposal"].status == ("rejected" if decision == "rejected" else "checks_failed")


def test_business_review_rejects_stale_current_hash_and_row_version_without_writing_history():
    store = _ReviewStore(definition_hash=OTHER_HASH)
    service = CapabilityGovernanceService(store)
    proposal = _pending_business_proposal(service)

    with pytest.raises(CapabilityBusinessError, match="review_subject_hash_mismatch"):
        service.base_capability_review_decide(
            _decision_payload(proposal), _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )
    assert store.reviews == []
    store.snapshot.document.capabilities[0].descriptor["business_definition_hash"] = HASH
    with pytest.raises(CapabilityBusinessError, match="row_version_conflict"):
        service.base_capability_review_decide(
            _decision_payload(proposal, row_version="999", idempotency_key="business-race"),
            _context(user_gid="reviewer", effective_roles=("super_admin",)),
        )
    assert store.reviews == []


def test_business_proposal_readback_is_stable_and_limits_evidence_to_super_admins():
    service = CapabilityGovernanceService(_ReviewStore())
    proposal = _pending_business_proposal(service)
    second = service.base_capability_proposal_submit(
        _proposal_payload(
            idempotency_key="proposal-business-second",
            previous_hash="sha256:" + "c" * 64,
            evidence_hash="sha256:" + "d" * 64,
        ),
        _context(),
    )["proposal"]

    ordinary = service.base_capability_proposal_search({"limit": 1}, _context())
    privileged = service.base_capability_proposal_search(
        {"limit": 1}, _context(user_gid="reviewer", effective_roles=("super_admin",)),
    )
    next_page = service.base_capability_proposal_search(
        {"limit": 1, "cursor": privileged["data"]["next_cursor"]},
        _context(user_gid="reviewer", effective_roles=("super_admin",)),
    )

    assert ordinary["items"][0]["reviews"] == ()
    assert ordinary["items"][0]["review_evidence"] == {}
    assert privileged["items"][0]["review_evidence"]["definition_hash"] == HASH
    assert [item["proposal_gid"] for item in (*privileged["items"], *next_page["items"])] == [
        str(proposal.proposal_gid), str(second.proposal_gid),
    ]


def test_business_proposal_search_uses_limit_plus_one_for_the_next_cursor():
    service = CapabilityGovernanceService(_ReviewStore())
    for item in range(201):
        service._proposals.detect(
            capability_id=f"base.page.{item}", capability_version_gid=item + 1,
            base_snapshot_gid=31, previous_hash=OTHER_HASH, proposed_descriptor_hash=HASH,
            evidence_hash="sha256:" + f"{item:064x}", submitted_by_gid="author",
            idempotency_key=f"page-{item}",
        )

    first = service.base_capability_proposal_search({"limit": 200}, _context())
    second = service.base_capability_proposal_search(
        {"limit": 200, "cursor": first["data"]["next_cursor"]}, _context(),
    )

    assert len(first["items"]) == 200
    assert first["data"]["next_cursor"] == "200"
    assert [item["proposal_gid"] for item in second["items"]] == ["201"]


def test_business_review_evidence_is_limited_to_the_pinned_major_and_relation_key():
    store = _ReviewStore()
    first = store.snapshot.document.capabilities[0]
    store.snapshot.document.capabilities = (
        first,
        SimpleNamespace(
            capability_id=first.capability_id, major_version=2,
            descriptor={"business_definition_hash": OTHER_HASH},
            business_effect="Wrong major must not leak.", business_rules=(), business_maturity=None,
        ),
    )
    store.relation_candidates = (
        SimpleNamespace(candidate_hash="kept", relation_type="overlap", source="deterministic",
                        capability_keys=("base.capability_registry.search@1",), evidence={"safe": True}),
        SimpleNamespace(candidate_hash="hidden", relation_type="overlap", source="deterministic",
                        capability_keys=("base.capability_registry.search@2",), evidence={"wrong": True}),
    )
    service = CapabilityGovernanceService(store)
    _pending_business_proposal(service)

    result = service.base_capability_proposal_search(
        {"limit": 1}, _context(user_gid="reviewer", effective_roles=("super_admin",)),
    )
    evidence = result["items"][0]["review_evidence"]

    assert evidence["business_effect"] == ""
    assert [item["candidate_hash"] for item in evidence["deterministic_relation_candidates"]] == ["kept"]


def test_business_review_provider_contract_is_closed_and_labels_the_pinned_hash():
    service = CapabilityGovernanceService(_ReviewStore())
    proposal = _pending_business_proposal(service)

    with pytest.raises(ValueError):
        validate_payload(
            INPUT_SCHEMAS["base.capability_review.decide"],
            _decision_payload(proposal, role="super_admin"),
            label="input",
        )
    with pytest.raises(ValueError):
        validate_payload(
            INPUT_SCHEMAS["base.capability_review.decide"],
            _decision_payload(proposal, decided_at="2000-01-01T00:00:00Z"),
            label="input",
        )
    result = _safe_response("base.capability_review.decide", {
        "status": "accepted", "proposal": proposal,
    })
    validate_payload(OUTPUT_SCHEMAS["base.capability_review.decide"], result, label="output")

    assert result["proposal"] == {
        "proposal_gid": str(proposal.proposal_gid), "status": "pending_approval",
        "row_version": str(proposal.row_version), "business_definition_hash": HASH,
        "review_type": "business_definition",
        "proposed_descriptor_hash_label": "business_definition_hash",
    }
