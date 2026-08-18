"""Table-driven proposal, review, and bounded-waiver workflows."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone


class WorkflowError(RuntimeError):
    """Raised for rejected governance workflow transitions and concurrency conflicts."""


CAPABILITY_TRANSITIONS = {
    "experimental": frozenset({"stable", "deprecated", "retired"}),
    "stable": frozenset({"deprecated", "retired"}),
    "deprecated": frozenset({"retired"}),
    "retired": frozenset(),
}
PROPOSAL_TRANSITIONS = {
    "detected": frozenset({"draft", "withdrawn", "superseded", "stale"}),
    "draft": frozenset({"submitted", "withdrawn", "superseded", "stale"}),
    "submitted": frozenset({"checking", "withdrawn", "superseded", "stale", "expired"}),
    "checking": frozenset({"pending_approval", "checks_failed", "withdrawn", "superseded", "stale", "expired"}),
    "pending_approval": frozenset({"approved", "rejected", "withdrawn", "superseded", "stale", "expired"}),
    "approved": frozenset({"released", "superseded", "stale", "expired"}),
    "released": frozenset({"superseded"}),
    "checks_failed": frozenset({"draft", "withdrawn", "superseded", "stale"}),
    "rejected": frozenset(), "withdrawn": frozenset(), "superseded": frozenset(), "expired": frozenset(), "stale": frozenset(),
}
FINDING_TRANSITIONS = {
    "candidate": frozenset({"confirmed", "rejected"}),
    "confirmed": frozenset({"resolving", "waived"}),
    "resolving": frozenset({"resolved", "waived"}),
    "resolved": frozenset(), "rejected": frozenset(), "waived": frozenset(),
}


def _can_transition(table: dict[str, frozenset[str]], current: str, target: str) -> bool:
    return target in table.get(current, frozenset())


def transition_state(machine: str, current: str, target: str) -> str:
    """Validate one declared lifecycle edge without permitting implicit shortcuts."""
    tables = {"capability": CAPABILITY_TRANSITIONS, "proposal": PROPOSAL_TRANSITIONS, "finding": FINDING_TRANSITIONS}
    try:
        table = tables[machine]
    except KeyError as exc:
        raise WorkflowError("state_machine_unknown") from exc
    if not _can_transition(table, current, target):
        raise WorkflowError("invalid_transition")
    return target


@dataclass(frozen=True)
class Review:
    review_gid: int
    proposal_gid: int
    review_stage: str
    decision: str
    reviewer_gid: str
    base_snapshot_gid: int
    descriptor_hash: str
    evidence_snapshot_hash: str
    decided_at: datetime


@dataclass(frozen=True)
class Proposal:
    proposal_gid: int
    capability_id: str
    capability_version_gid: int
    base_snapshot_gid: int
    previous_hash: str
    proposed_descriptor_hash: str
    evidence_hash: str
    submitted_by_gid: str
    status: str = "detected"
    row_version: int = 1
    reviews: tuple[Review, ...] = ()

    @property
    def governance_capability(self) -> bool:
        return self.capability_id.startswith("base.capability_")


@dataclass(frozen=True)
class Waiver:
    waiver_gid: int
    finding_gid: int
    capability_version_gid: int
    scope: str
    reason: str
    granted_by_gid: str
    starts_at: datetime
    expires_at: datetime
    status: str = "active"
    revoked_at: datetime | None = None
    row_version: int = 1


def _time(value: datetime | None) -> datetime:
    moment = value or datetime.now(timezone.utc)
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


class ProposalService:
    def __init__(self, *, next_gid: Callable[[], int]) -> None:
        self._next_gid = next_gid
        self._proposals: dict[int, Proposal] = {}
        self._idempotency: dict[str, Proposal] = {}

    def get(self, proposal_gid: int) -> Proposal:
        try:
            return self._proposals[proposal_gid]
        except KeyError as exc:
            raise WorkflowError("proposal_not_found") from exc

    def _existing(self, key: str) -> Proposal | None:
        if not key:
            raise WorkflowError("idempotency_key_required")
        return self._idempotency.get(key)

    def _record(self, key: str, proposal: Proposal) -> Proposal:
        self._proposals[proposal.proposal_gid] = proposal
        self._idempotency[key] = proposal
        return proposal

    def detect(self, *, capability_id: str, capability_version_gid: int, base_snapshot_gid: int, previous_hash: str, proposed_descriptor_hash: str, evidence_hash: str, submitted_by_gid: str, idempotency_key: str) -> Proposal:
        key = str(idempotency_key).strip()
        existing = self._existing(key)
        if existing is not None:
            return existing
        for gid, proposal in tuple(self._proposals.items()):
            if proposal.capability_id == capability_id and proposal.status not in {"released", "rejected", "withdrawn", "superseded", "expired", "stale"} and proposal.proposed_descriptor_hash != proposed_descriptor_hash:
                self._proposals[gid] = replace(proposal, status="superseded", row_version=proposal.row_version + 1)
        return self._record(key, Proposal(self._next_gid(), str(capability_id), int(capability_version_gid), int(base_snapshot_gid), str(previous_hash), str(proposed_descriptor_hash), str(evidence_hash), str(submitted_by_gid)))

    def transition(self, proposal_gid: int, target: str, *, expected_row_version: int, idempotency_key: str) -> Proposal:
        key = str(idempotency_key).strip()
        existing = self._existing(key)
        if existing is not None:
            return existing
        proposal = self.get(proposal_gid)
        if proposal.row_version != expected_row_version:
            raise WorkflowError("row_version_conflict")
        if not _can_transition(PROPOSAL_TRANSITIONS, proposal.status, target):
            raise WorkflowError("invalid_transition")
        return self._record(key, replace(proposal, status=target, row_version=proposal.row_version + 1))

    def submit(self, proposal_gid: int, *, expected_row_version: int, idempotency_key: str) -> Proposal:
        return self.transition(proposal_gid, "submitted", expected_row_version=expected_row_version, idempotency_key=idempotency_key)

    def refresh(self, proposal_gid: int, *, current_descriptor_hash: str, current_evidence_hash: str, expected_row_version: int, idempotency_key: str) -> Proposal:
        proposal = self.get(proposal_gid)
        target = "stale" if proposal.proposed_descriptor_hash != current_descriptor_hash or proposal.evidence_hash != current_evidence_hash else proposal.status
        if target == proposal.status:
            return proposal
        return self.transition(proposal_gid, target, expected_row_version=expected_row_version, idempotency_key=idempotency_key)

    def decide(self, proposal_gid: int, *, stage: str, decision: str, reviewer_gid: str, expected_row_version: int, idempotency_key: str, decided_at: datetime | None = None) -> Proposal:
        key = str(idempotency_key).strip()
        existing = self._existing(key)
        if existing is not None:
            return existing
        proposal = self.get(proposal_gid)
        if proposal.row_version != expected_row_version:
            raise WorkflowError("row_version_conflict")
        if proposal.status != "pending_approval":
            raise WorkflowError("invalid_transition")
        reviewer = str(reviewer_gid)
        if reviewer == proposal.submitted_by_gid or reviewer.startswith("ai:"):
            raise WorkflowError("independent_reviewer_required")
        prior_stages = {review.review_stage for review in proposal.reviews if review.decision == "approved"}
        prior_reviewers = {review.reviewer_gid for review in proposal.reviews if review.decision == "approved"}
        required = ("base_owner", "platform_release") if proposal.governance_capability else ("base_owner",)
        if proposal.governance_capability and reviewer in prior_reviewers:
            raise WorkflowError("independent_reviewer_required")
        if stage not in required or stage in prior_stages or (stage == "platform_release" and "base_owner" not in prior_stages):
            raise WorkflowError("review_stage_invalid")
        if decision not in {"approved", "rejected"}:
            raise WorkflowError("review_decision_invalid")
        review = Review(self._next_gid(), proposal.proposal_gid, stage, decision, reviewer, proposal.base_snapshot_gid, proposal.proposed_descriptor_hash, proposal.evidence_hash, _time(decided_at))
        next_status = "rejected" if decision == "rejected" else ("approved" if set(required).issubset(prior_stages | {stage}) else "pending_approval")
        return self._record(key, replace(proposal, status=next_status, reviews=proposal.reviews + (review,), row_version=proposal.row_version + 1))


class WaiverService:
    def __init__(self, *, next_gid: Callable[[], int]) -> None:
        self._next_gid = next_gid
        self._waivers: dict[int, Waiver] = {}
        self._idempotency: dict[str, Waiver] = {}

    def grant(self, *, finding_gid: int, capability_version_gid: int, scope: str, reason: str, granted_by_gid: str, expires_at: datetime | None, idempotency_key: str, starts_at: datetime | None = None) -> Waiver:
        key = str(idempotency_key).strip()
        if not key:
            raise WorkflowError("idempotency_key_required")
        if key in self._idempotency:
            return self._idempotency[key]
        if expires_at is None:
            raise WorkflowError("waiver_expiry_required")
        start, expiry = _time(starts_at), _time(expires_at)
        if expiry <= start:
            raise WorkflowError("waiver_expiry_invalid")
        status = "expired" if expiry <= datetime.now(timezone.utc) else "active"
        waiver = Waiver(self._next_gid(), int(finding_gid), int(capability_version_gid), str(scope), str(reason), str(granted_by_gid), start, expiry, status)
        self._waivers[waiver.waiver_gid] = waiver
        self._idempotency[key] = waiver
        return waiver

    def effective(self, waiver_gid: int, *, now: datetime | None = None) -> bool:
        waiver = self._waivers[waiver_gid]
        moment = _time(now)
        return waiver.status == "active" and waiver.starts_at <= moment < waiver.expires_at and waiver.revoked_at is None

    def revoke(self, waiver_gid: int, *, expected_row_version: int, idempotency_key: str, revoked_at: datetime | None = None) -> Waiver:
        key = str(idempotency_key).strip()
        if key in self._idempotency:
            return self._idempotency[key]
        waiver = self._waivers[waiver_gid]
        if waiver.row_version != expected_row_version:
            raise WorkflowError("row_version_conflict")
        if waiver.status != "active":
            raise WorkflowError("invalid_transition")
        revised = replace(waiver, status="revoked", revoked_at=_time(revoked_at), row_version=waiver.row_version + 1)
        self._waivers[waiver_gid] = revised
        self._idempotency[key] = revised
        return revised


__all__ = ["CAPABILITY_TRANSITIONS", "FINDING_TRANSITIONS", "PROPOSAL_TRANSITIONS", "Proposal", "ProposalService", "Review", "Waiver", "WaiverService", "WorkflowError", "transition_state"]
