"""Table-driven proposal, review, and bounded-waiver workflows."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from threading import RLock

from .audit import AuditSink
from .business_models import CapabilityBusinessReview


class WorkflowError(RuntimeError):
    """Raised for rejected governance workflow transitions and concurrency conflicts."""


CAPABILITY_TRANSITIONS = {
    "experimental": frozenset({"stable"}),
    "stable": frozenset({"deprecated"}),
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
    decision_reason: str = ""
    review_type: str = "standard"


@dataclass(frozen=True)
class ReviewerContext:
    """Review authority supplied by the trusted identity and permission boundary."""

    gid: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    owned_domains: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "gid", str(self.gid))
        object.__setattr__(self, "roles", tuple(sorted(set(str(value) for value in self.roles))))
        object.__setattr__(self, "permissions", tuple(sorted(set(str(value) for value in self.permissions))))
        object.__setattr__(self, "owned_domains", tuple(sorted(set(str(value) for value in self.owned_domains))))


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
    review_kind: str = "standard"

    @property
    def governance_capability(self) -> bool:
        return self.capability_id.startswith("base.capability_")

    @property
    def business_definition_hash(self) -> str | None:
        return self.proposed_descriptor_hash if self.review_kind == "business_definition" else None


@dataclass(frozen=True)
class Waiver:
    waiver_gid: int
    finding_gid: int
    capability_version_gid: int
    scope: str
    reason: str
    granted_by_gid: str
    code_hash: str
    catalog_hash: str
    evidence_hash: str
    starts_at: datetime
    expires_at: datetime
    status: str = "active"
    revoked_at: datetime | None = None
    row_version: int = 1


def _time(value: datetime | None) -> datetime:
    moment = value or datetime.now(timezone.utc)
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


class ProposalService:
    def __init__(
        self, *, next_gid: Callable[[], int], audit_sink: AuditSink | None = None,
        business_review_sink: Callable[[CapabilityBusinessReview], None] | None = None,
        business_review_store: object | None = None,
    ) -> None:
        self._next_gid = next_gid
        self._audit_sink = audit_sink
        self._proposals: dict[int, Proposal] = {}
        self._idempotency: dict[str, Proposal] = {}
        self._business_review_sink = business_review_sink
        self._business_review_store = business_review_store
        self._business_decisions: dict[str, tuple[tuple[object, ...], Proposal]] = {}
        self._business_review_lock = RLock()

    def get(self, proposal_gid: int) -> Proposal:
        loader = getattr(self._business_review_store, "get_workflow_proposal", None)
        if callable(loader):
            value = loader(proposal_gid)
            if value is not None:
                self._proposals[proposal_gid] = value
        try:
            return self._proposals[proposal_gid]
        except KeyError as exc:
            raise WorkflowError("proposal_not_found") from exc

    def _existing(self, key: str) -> Proposal | None:
        if not key:
            raise WorkflowError("idempotency_key_required")
        return self._idempotency.get(key)

    def _audit(self, *, operation: str, entity_gid: int, actor_gid: str, idempotency_key: str, detail: dict[str, object]) -> None:
        if self._audit_sink is not None:
            self._audit_sink.append(operation=operation, entity_gid=entity_gid, actor_gid=actor_gid, request_gid=idempotency_key, detail=detail, idempotency_key=f"{operation}:{idempotency_key}")

    def _record(self, key: str, proposal: Proposal, *, operation: str, actor_gid: str) -> Proposal:
        saver = getattr(self._business_review_store, "save_workflow_proposal", None)
        if proposal.review_kind == "business_definition" and callable(saver):
            saver(proposal)
        self._proposals[proposal.proposal_gid] = proposal
        self._idempotency[key] = proposal
        self._audit(operation=operation, entity_gid=proposal.proposal_gid, actor_gid=actor_gid, idempotency_key=key, detail={"status": proposal.status, "capability_id": proposal.capability_id})
        return proposal

    def detect(self, *, capability_id: str, capability_version_gid: int, base_snapshot_gid: int, previous_hash: str, proposed_descriptor_hash: str, evidence_hash: str, submitted_by_gid: str, idempotency_key: str, review_kind: str = "standard") -> Proposal:
        key = str(idempotency_key).strip()
        existing = self._existing(key)
        if existing is not None:
            return existing
        if review_kind not in {"standard", "business_definition"}:
            raise WorkflowError("review_subject_type_invalid")
        if review_kind == "business_definition" and not _is_sha256(proposed_descriptor_hash):
            raise WorkflowError("review_subject_hash_invalid")
        for gid, proposal in tuple(self._proposals.items()):
            if proposal.capability_id == capability_id and proposal.status not in {"released", "rejected", "withdrawn", "superseded", "expired", "stale"} and proposal.proposed_descriptor_hash != proposed_descriptor_hash:
                superseded = replace(proposal, status="superseded", row_version=proposal.row_version + 1)
                self._proposals[gid] = superseded
                self._audit(operation="proposal_superseded", entity_gid=gid, actor_gid=str(submitted_by_gid), idempotency_key=f"{key}:superseded:{gid}", detail={"before_status": proposal.status, "after_status": "superseded", "capability_id": proposal.capability_id})
        return self._record(key, Proposal(self._next_gid(), str(capability_id), int(capability_version_gid), int(base_snapshot_gid), str(previous_hash), str(proposed_descriptor_hash), str(evidence_hash), str(submitted_by_gid), review_kind=review_kind), operation="proposal", actor_gid=str(submitted_by_gid))

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
        candidate = replace(proposal, status=target, row_version=proposal.row_version + 1)
        atomic = getattr(self._business_review_store, "transition_workflow_proposal", None)
        if proposal.review_kind == "business_definition" and callable(atomic):
            try:
                resolved = atomic(proposal, candidate)
            except Exception as exc:
                raise WorkflowError(str(exc)) from exc
            self._proposals[proposal_gid] = resolved
            self._idempotency[key] = resolved
            self._audit(operation="proposal", entity_gid=proposal_gid, actor_gid=proposal.submitted_by_gid,
                        idempotency_key=key, detail={"status": resolved.status, "capability_id": resolved.capability_id})
            return resolved
        return self._record(key, candidate, operation="proposal", actor_gid=proposal.submitted_by_gid)

    def submit(self, proposal_gid: int, *, expected_row_version: int, idempotency_key: str) -> Proposal:
        return self.transition(proposal_gid, "submitted", expected_row_version=expected_row_version, idempotency_key=idempotency_key)

    def refresh(self, proposal_gid: int, *, current_descriptor_hash: str, current_evidence_hash: str, expected_row_version: int, idempotency_key: str) -> Proposal:
        proposal = self.get(proposal_gid)
        target = "stale" if proposal.proposed_descriptor_hash != current_descriptor_hash or proposal.evidence_hash != current_evidence_hash else proposal.status
        if target == proposal.status:
            return proposal
        return self.transition(proposal_gid, target, expected_row_version=expected_row_version, idempotency_key=idempotency_key)

    def decide(self, proposal_gid: int, *, stage: str, decision: str, reviewer_context: ReviewerContext, expected_row_version: int, idempotency_key: str, decided_at: datetime | None = None) -> Proposal:
        key = str(idempotency_key).strip()
        existing = self._existing(key)
        if existing is not None:
            return existing
        proposal = self.get(proposal_gid)
        if proposal.review_kind == "business_definition":
            raise WorkflowError("business_review_required")
        if proposal.row_version != expected_row_version:
            raise WorkflowError("row_version_conflict")
        if proposal.status != "pending_approval":
            raise WorkflowError("invalid_transition")
        reviewer = reviewer_context.gid
        if reviewer == proposal.submitted_by_gid or reviewer.startswith("ai:"):
            raise WorkflowError("independent_reviewer_required")
        prior_stages = {review.review_stage for review in proposal.reviews if review.decision == "approved"}
        prior_reviewers = {review.reviewer_gid for review in proposal.reviews if review.decision == "approved"}
        required = ("base_owner", "platform_release") if proposal.governance_capability else ("base_owner",)
        if proposal.governance_capability and reviewer in prior_reviewers:
            raise WorkflowError("independent_reviewer_required")
        if stage not in required or stage in prior_stages or (stage == "platform_release" and "base_owner" not in prior_stages):
            raise WorkflowError("review_stage_invalid")
        authority = {
            "base_owner": ("base_owner", "system.capability.govern", "base"),
            "platform_release": ("platform_release", "system.capability.release", "platform"),
        }[stage]
        if authority[0] not in reviewer_context.roles or authority[1] not in reviewer_context.permissions or authority[2] not in reviewer_context.owned_domains:
            raise WorkflowError("reviewer_not_authorized")
        if decision not in {"approved", "rejected"}:
            raise WorkflowError("review_decision_invalid")
        review = Review(self._next_gid(), proposal.proposal_gid, stage, decision, reviewer, proposal.base_snapshot_gid, proposal.proposed_descriptor_hash, proposal.evidence_hash, _time(decided_at))
        next_status = "rejected" if decision == "rejected" else ("approved" if set(required).issubset(prior_stages | {stage}) else "pending_approval")
        return self._record(key, replace(proposal, status=next_status, reviews=proposal.reviews + (review,), row_version=proposal.row_version + 1), operation="review", actor_gid=reviewer)

    def decide_business_definition(
        self, proposal_gid: int, *, reviewer_context: ReviewerContext,
        definition_hash: str, current_definition_hash: str, decision: str,
        decision_reason: str, expected_row_version: int, idempotency_key: str,
    ) -> Proposal:
        """Append one super-admin decision for a pinned business definition."""
        with self._business_review_lock:
            key = str(idempotency_key).strip()
            if not key:
                raise WorkflowError("idempotency_key_required")
            reason = str(decision_reason).strip()
            fingerprint = (
                int(proposal_gid), str(definition_hash), str(decision), reason,
                int(expected_row_version), reviewer_context.gid,
            )
            replay = self._business_decisions.get(key)
            if replay is not None:
                if replay[0] != fingerprint:
                    raise WorkflowError("idempotency_conflict")
                return replay[1]
            if not _is_sha256(definition_hash) or not _is_sha256(current_definition_hash):
                raise WorkflowError("review_subject_hash_invalid")
            if decision not in {"approved", "rejected", "changes_requested"}:
                raise WorkflowError("review_decision_invalid")
            if not reason or len(reason) > 2000:
                raise WorkflowError("review_reason_invalid")
            proposal = self.get(proposal_gid)
            if proposal.row_version != expected_row_version:
                raise WorkflowError("row_version_conflict")
            if proposal.review_kind != "business_definition" or proposal.status != "pending_approval":
                raise WorkflowError("review_subject_type_invalid")
            if definition_hash != proposal.proposed_descriptor_hash or current_definition_hash != proposal.proposed_descriptor_hash:
                raise WorkflowError("review_subject_hash_mismatch")
            if "super_admin" not in reviewer_context.roles:
                raise WorkflowError("reviewer_not_authorized")
            if reviewer_context.gid == proposal.submitted_by_gid:
                raise WorkflowError("independent_reviewer_required")
            if self._business_review_sink is None and not callable(
                getattr(self._business_review_store, "decide_business_review_atomic", None)
            ):
                raise WorkflowError("business_review_persistence_unavailable")
            review_gid = self._next_gid()
            moment = _time(None)
            business_review = CapabilityBusinessReview(
                review_gid=review_gid, capability_version_gid=proposal.capability_version_gid,
                definition_hash=definition_hash, decision=decision, decision_reason=reason,
                reviewer_gid=reviewer_context.gid, reviewer_role="super_admin", decided_at=moment,
                proposal_gid=proposal.proposal_gid, evidence_snapshot_gid=proposal.base_snapshot_gid,
            )
            review = Review(
                review_gid, proposal.proposal_gid, "business_definition", decision,
                reviewer_context.gid, proposal.base_snapshot_gid, definition_hash,
                proposal.evidence_hash, moment, reason, "business_definition",
            )
            target = "approved" if decision == "approved" else (
                "rejected" if decision == "rejected" else "checks_failed"
            )
            candidate = replace(proposal, status=target, reviews=proposal.reviews + (review,),
                                row_version=proposal.row_version + 1)
            atomic = getattr(self._business_review_store, "decide_business_review_atomic", None)
            if callable(atomic):
                try:
                    resolved = atomic(proposal, candidate, business_review, fingerprint, key)
                except Exception as exc:
                    raise WorkflowError(str(exc)) from exc
                self._proposals[proposal.proposal_gid] = resolved
                self._idempotency[key] = resolved
                self._business_decisions[key] = (fingerprint, resolved)
                self._audit(operation="business_review", entity_gid=proposal.proposal_gid,
                            actor_gid=reviewer_context.gid, idempotency_key=key,
                            detail={"status": resolved.status, "capability_id": resolved.capability_id})
                return resolved
            try:
                self._business_review_sink(business_review)
            except Exception as exc:
                raise WorkflowError("business_review_persistence_failed") from exc
            resolved = self._record(
                key, candidate,
                operation="business_review", actor_gid=reviewer_context.gid,
            )
            self._business_decisions[key] = (fingerprint, resolved)
            return resolved

    def list(self) -> tuple[Proposal, ...]:
        return tuple(sorted(self._proposals.values(), key=lambda proposal: proposal.proposal_gid))


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


class WaiverService:
    def __init__(self, *, next_gid: Callable[[], int], audit_sink: AuditSink | None = None) -> None:
        self._next_gid = next_gid
        self._audit_sink = audit_sink
        self._waivers: dict[int, Waiver] = {}
        self._idempotency: dict[str, Waiver] = {}

    def _audit(self, waiver: Waiver, *, idempotency_key: str) -> None:
        if self._audit_sink is not None:
            self._audit_sink.append(operation="waiver", entity_gid=waiver.waiver_gid, actor_gid=waiver.granted_by_gid, request_gid=idempotency_key, detail={"status": waiver.status, "finding_gid": waiver.finding_gid}, idempotency_key=f"waiver:{idempotency_key}")

    def grant(self, *, finding_gid: int, capability_version_gid: int, scope: str, reason: str, granted_by_gid: str, code_hash: str, catalog_hash: str, evidence_hash: str, expires_at: datetime | None, idempotency_key: str, starts_at: datetime | None = None) -> Waiver:
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
        waiver = Waiver(self._next_gid(), int(finding_gid), int(capability_version_gid), str(scope), str(reason), str(granted_by_gid), str(code_hash), str(catalog_hash), str(evidence_hash), start, expiry, status)
        self._waivers[waiver.waiver_gid] = waiver
        self._idempotency[key] = waiver
        self._audit(waiver, idempotency_key=key)
        return waiver

    def effective(self, waiver_gid: int, *, now: datetime | None = None, code_hash: str | None = None, catalog_hash: str | None = None, evidence_hash: str | None = None) -> bool:
        waiver = self._waivers[waiver_gid]
        moment = _time(now)
        return waiver.status == "active" and waiver.starts_at <= moment < waiver.expires_at and waiver.revoked_at is None and (code_hash is None or waiver.code_hash == code_hash) and (catalog_hash is None or waiver.catalog_hash == catalog_hash) and (evidence_hash is None or waiver.evidence_hash == evidence_hash)

    def refresh(self, waiver_gid: int, *, code_hash: str, catalog_hash: str, evidence_hash: str, expected_row_version: int, idempotency_key: str, now: datetime | None = None) -> Waiver:
        key = str(idempotency_key).strip()
        if not key:
            raise WorkflowError("idempotency_key_required")
        if key in self._idempotency:
            return self._idempotency[key]
        waiver = self._waivers[waiver_gid]
        if waiver.row_version != expected_row_version:
            raise WorkflowError("row_version_conflict")
        if waiver.status != "active":
            raise WorkflowError("invalid_transition")
        moment = _time(now)
        status = "stale" if (waiver.code_hash, waiver.catalog_hash, waiver.evidence_hash) != (str(code_hash), str(catalog_hash), str(evidence_hash)) else ("expired" if moment >= waiver.expires_at else "active")
        if status == "active":
            return waiver
        revised = replace(waiver, status=status, row_version=waiver.row_version + 1)
        self._waivers[waiver_gid] = revised
        self._idempotency[key] = revised
        self._audit(revised, idempotency_key=key)
        return revised

    def revoke(self, waiver_gid: int, *, expected_row_version: int, idempotency_key: str, revoked_at: datetime | None = None) -> Waiver:
        key = str(idempotency_key).strip()
        if not key:
            raise WorkflowError("idempotency_key_required")
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
        self._audit(revised, idempotency_key=key)
        return revised


__all__ = ["CAPABILITY_TRANSITIONS", "FINDING_TRANSITIONS", "PROPOSAL_TRANSITIONS", "Proposal", "ProposalService", "Review", "ReviewerContext", "Waiver", "WaiverService", "WorkflowError", "transition_state"]
