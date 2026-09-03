"""Insert-only snapshot persistence with stable logical and major identities."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from dataclasses import replace
import json
from threading import RLock
from typing import Any, Protocol

from backend.utils.gid import next_gid

from .models import (
    BusinessPurposeRecord,
    BusinessRuleRecord,
    CapabilityBusinessProjection,
    CapabilityBusinessReview,
    CapabilityBinding,
    CapabilityFingerprint,
    CapabilityMaturity,
    CapabilityProjection,
    CapabilityRelationCandidate,
    ImmutableRecordError,
    ImplementationNode,
    ImplementationRelation,
    ScannedCapability,
    RuleEffectivenessRecord,
    ScanFinding,
    SnapshotDocument,
    SnapshotEntry,
    SnapshotRecord,
)


_WORKFLOW_PROPOSAL_SEQUENCE = "capability_governance_proposal_gid"
_WORKFLOW_REVIEW_SEQUENCE = "capability_governance_review_gid"


class GovernanceStore(ABC):
    persistent: bool = False
    @abstractmethod
    def import_snapshot(self, document: SnapshotDocument) -> SnapshotRecord:
        """Append a snapshot and project its stable identities."""

    def save_snapshot(self, document: SnapshotDocument) -> SnapshotRecord:
        return self.import_snapshot(document)

    @abstractmethod
    def get_snapshot(self, snapshot_gid: int) -> SnapshotRecord | None:
        """Read one immutable snapshot through the persistence boundary."""

    @abstractmethod
    def latest_snapshot(self) -> SnapshotRecord | None:
        """Read the newest immutable snapshot through the persistence boundary."""

    def list_entries(self, snapshot_gid: int | None = None) -> tuple[SnapshotEntry, ...]:
        """Return projected entries without exposing store implementation state."""
        snapshot = self.latest_snapshot() if snapshot_gid is None else self.get_snapshot(snapshot_gid)
        return tuple(getattr(snapshot, "entries", ())) if snapshot is not None else ()

    def get_findings(self, snapshot_gid: int) -> tuple[Mapping[str, Any], ...]:
        return ()

    def replace_snapshot(self, snapshot_gid: int, document: SnapshotDocument) -> None:
        raise ImmutableRecordError("snapshot_records_are_insert_only")

    @abstractmethod
    def save_business_projection(self, projection: CapabilityBusinessProjection) -> None:
        """Persist an immutable normalized business projection."""

    @abstractmethod
    def list_relation_candidates(self, snapshot_gid: int) -> tuple[CapabilityRelationCandidate, ...]:
        """Return immutable relationship candidates for one snapshot."""

    @abstractmethod
    def save_relation_candidates(self, candidates: tuple[CapabilityRelationCandidate, ...]) -> None:
        """Append deterministic relation candidates, preserving identical reruns."""

    @abstractmethod
    def save_business_review(self, review: CapabilityBusinessReview) -> None:
        """Append a business review without mutating prior decisions."""

    @abstractmethod
    def current_business_review(
        self, capability_version_gid: int, definition_hash: str,
    ) -> CapabilityBusinessReview | None:
        """Return only a latest approved review for the exact semantic definition hash."""

    @abstractmethod
    def save_rule_effectiveness(self, record: RuleEffectivenessRecord) -> None:
        """Append immutable runtime rule-effectiveness evidence."""

    @abstractmethod
    def list_rule_effectiveness(
        self, capability_version_gid: int, definition_hash: str,
    ) -> tuple[RuleEffectivenessRecord, ...]:
        """Return effectiveness evidence for the exact semantic definition hash."""


class GovernanceWorkflowPort(Protocol):
    """Durable workflow adapter required by a persistent runtime profile.

    The service consumes these domain services through a port so SQL, an
    application repository, or a transactional test adapter can be selected
    without making the Gateway aware of persistence details.
    """

    @property
    def proposal_service(self) -> Any: ...

    @property
    def waiver_service(self) -> Any: ...

    @property
    def release_gate(self) -> Any: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_value(row: Any, name: str, index: int) -> Any:
    if isinstance(row, Mapping):
        return row[name]
    return row[index]


def _optional_row_value(row: Any, name: str, index: int) -> str | None:
    value = _row_value(row, name, index)
    return None if value is None else str(value)


def _text_value(value: Any) -> str:
    return value.decode("ascii") if isinstance(value, bytes | bytearray) else str(value)


def _json_load(value: Any) -> Mapping[str, Any]:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return value if isinstance(value, Mapping) else {}


def _json_tuple(value: Any) -> tuple[Any, ...]:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return ()
    return tuple(value) if isinstance(value, tuple | list) else ()


def _duplicate_key(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "duplicate" in text or "integrity" in text and "unique" in text


def _validate_business_review_references(review: CapabilityBusinessReview) -> None:
    if review.proposal_gid <= 0:
        raise ImmutableRecordError("business_review_proposal_gid_invalid")
    if review.evidence_snapshot_gid <= 0:
        raise ImmutableRecordError("business_review_evidence_snapshot_gid_invalid")


def _scan_finding_record(finding: ScanFinding, finding_gid: int) -> Mapping[str, Any]:
    return {
        "finding_gid": finding_gid,
        "code": finding.code,
        "reason_code": finding.code,
        "severity": finding.severity,
        "status": "open",
        "source_type": "scanner",
        "fingerprint": _scan_finding_fingerprint(finding),
        "remediation_boundary": finding.category,
        "domains": (),
        "evidence": (finding.source_path,),
        "reason": finding.message,
        "subject_summary": finding.source_path,
    }


def _scan_finding_fingerprint(finding: ScanFinding) -> str:
    from .rules import finding_fingerprint
    return finding_fingerprint(
        finding.code, finding.severity, (), (finding.source_path,), finding.category,
    )


def _finding_row_record(row: Any) -> Mapping[str, Any]:
    source_path = str(_row_value(row, "recommendation", 8))
    code = str(_row_value(row, "finding_type", 1))
    return {
        "finding_gid": int(_row_value(row, "finding_gid", 0)),
        "code": code,
        "reason_code": code,
        "severity": str(_row_value(row, "severity", 2)),
        "status": str(_row_value(row, "status", 3)),
        "source_type": str(_row_value(row, "source_type", 4)),
        "fingerprint": str(_row_value(row, "finding_fingerprint", 5)),
        "remediation_boundary": str(_row_value(row, "title", 6)),
        "domains": (),
        "evidence": (source_path,),
        "reason": str(_row_value(row, "summary", 7)),
        "subject_summary": source_path,
    }


class MemoryGovernanceStore(GovernanceStore):
    """Thread-safe in-memory store used by governance tests and local projections."""

    def __init__(self, next_ids: Callable[[], int] = next_gid):
        self._next_ids = next_ids
        self._lock = RLock()
        self._logical_ids: dict[str, int] = {}
        self._major_ids: dict[tuple[int, int], int] = {}
        self._snapshots: dict[int, SnapshotRecord] = {}
        self._snapshots_by_hash: dict[str, SnapshotRecord] = {}
        self._business_purposes: dict[int, BusinessPurposeRecord] = {}
        self._business_rules: dict[int, BusinessRuleRecord] = {}
        self._relation_candidates: dict[int, CapabilityRelationCandidate] = {}
        self._business_reviews: dict[int, CapabilityBusinessReview] = {}
        self._workflow_proposals: dict[int, Any] = {}
        self._workflow_proposal_gid_value = 0
        self._workflow_review_gid_value = 0
        self._business_review_requests: dict[str, tuple[tuple[object, ...], Any]] = {}
        self._workflow_review_requests: dict[str, tuple[tuple[object, ...], Any]] = {}
        self._rule_effectiveness: dict[int, RuleEffectivenessRecord] = {}
        self._scan_findings: dict[int, tuple[Mapping[str, Any], ...]] = {}

    def import_snapshot(self, document: SnapshotDocument) -> SnapshotRecord:
        with self._lock:
            from .fingerprint import snapshot_fingerprint
            if snapshot_fingerprint(document) != document.snapshot_hash:
                raise ImmutableRecordError("snapshot_hash_mismatch")
            existing = self._snapshots_by_hash.get(document.snapshot_hash)
            if existing is not None:
                if existing.document != document:
                    raise ImmutableRecordError("snapshot_hash_conflict")
                return existing
            projections = self._project_capabilities(document)
            scan_run_gid = self._next_ids()
            snapshot_gid = self._next_ids()
            entries = tuple(
                SnapshotEntry(**projection.__dict__, snapshot_entry_gid=self._next_ids())
                for projection in projections
            )
            node_gids = {node.canonical_key: self._next_ids() for node in document.nodes}
            record = SnapshotRecord(
                snapshot_gid=snapshot_gid,
                scan_run_gid=scan_run_gid,
                document=document,
                entries=entries,
                node_gids=node_gids,
                binding_gids=tuple(self._next_ids() for _ in document.bindings),
                relation_gids=tuple(self._next_ids() for _ in document.relations),
            )
            self._snapshots[snapshot_gid] = record
            self._snapshots_by_hash[document.snapshot_hash] = record
            self._scan_findings[snapshot_gid] = tuple(
                _scan_finding_record(finding, self._next_ids()) for finding in document.scan_findings
            )
            return record

    def get_snapshot(self, snapshot_gid: int) -> SnapshotRecord | None:
        with self._lock:
            return self._snapshots.get(snapshot_gid)

    def latest_snapshot(self) -> SnapshotRecord | None:
        with self._lock:
            return self._snapshots[max(self._snapshots)] if self._snapshots else None

    def get_findings(self, snapshot_gid: int) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            return self._scan_findings.get(snapshot_gid, ())

    def list_entries(self, snapshot_gid: int | None = None) -> tuple[SnapshotEntry, ...]:
        with self._lock:
            snapshot = self._snapshots.get(snapshot_gid) if snapshot_gid is not None else (
                self._snapshots[max(self._snapshots)] if self._snapshots else None
            )
            return tuple(getattr(snapshot, "entries", ())) if snapshot is not None else ()

    def save_business_projection(self, projection: CapabilityBusinessProjection) -> None:
        with self._lock:
            purpose = projection.purpose
            purpose_subject = (purpose.capability_version_gid, purpose.definition_hash)
            if purpose.purpose_gid in self._business_purposes:
                raise ImmutableRecordError("business_purpose_gid_already_exists")
            if purpose_subject in {
                (item.capability_version_gid, item.definition_hash)
                for item in self._business_purposes.values()
            }:
                raise ImmutableRecordError("uq_capability_business_purpose")

            rule_gids = [rule.business_rule_gid for rule in projection.rules]
            rule_subjects = [
                (rule.capability_version_gid, rule.definition_hash, rule.rule_id, rule.rule_version)
                for rule in projection.rules
            ]
            if len(rule_gids) != len(set(rule_gids)) or any(
                gid in self._business_rules for gid in rule_gids
            ):
                raise ImmutableRecordError("business_rule_gid_already_exists")
            existing_rule_subjects = {
                (rule.capability_version_gid, rule.definition_hash, rule.rule_id, rule.rule_version)
                for rule in self._business_rules.values()
            }
            if len(rule_subjects) != len(set(rule_subjects)) or any(
                subject in existing_rule_subjects for subject in rule_subjects
            ):
                raise ImmutableRecordError("uq_capability_business_rule")

            candidate_gids = [candidate.relation_candidate_gid for candidate in projection.relation_candidates]
            candidate_subjects = [
                (candidate.snapshot_gid, candidate.candidate_hash)
                for candidate in projection.relation_candidates
            ]
            if len(candidate_gids) != len(set(candidate_gids)) or any(
                gid in self._relation_candidates for gid in candidate_gids
            ):
                raise ImmutableRecordError("relation_candidate_gid_already_exists")
            existing_candidate_subjects = {
                (candidate.snapshot_gid, candidate.candidate_hash)
                for candidate in self._relation_candidates.values()
            }
            if len(candidate_subjects) != len(set(candidate_subjects)) or any(
                subject in existing_candidate_subjects for subject in candidate_subjects
            ):
                raise ImmutableRecordError("uq_capability_relation_candidate")

            self._business_purposes[purpose.purpose_gid] = purpose
            self._business_rules.update((rule.business_rule_gid, rule) for rule in projection.rules)
            self._relation_candidates.update(
                (candidate.relation_candidate_gid, candidate)
                for candidate in projection.relation_candidates
            )

    def list_relation_candidates(self, snapshot_gid: int) -> tuple[CapabilityRelationCandidate, ...]:
        with self._lock:
            return tuple(sorted(
                (
                    candidate for candidate in self._relation_candidates.values()
                    if candidate.snapshot_gid == snapshot_gid
                ),
                key=lambda item: item.relation_candidate_gid,
            ))

    def save_relation_candidates(self, candidates: tuple[CapabilityRelationCandidate, ...]) -> None:
        with self._lock:
            # Validate the whole replay against a staging copy.  This gives
            # Memory the same all-or-nothing semantics as the SQL transaction.
            staged = dict(self._relation_candidates)
            subjects = {(item.snapshot_gid, item.candidate_hash): item for item in staged.values()}
            for candidate in candidates:
                existing_gid = staged.get(candidate.relation_candidate_gid)
                existing_subject = subjects.get((candidate.snapshot_gid, candidate.candidate_hash))
                if existing_gid is not None and existing_gid != candidate:
                    raise ImmutableRecordError("relation_candidate_gid_already_exists")
                if existing_subject is not None and existing_subject != candidate:
                    raise ImmutableRecordError("uq_capability_relation_candidate")
                if existing_gid is None and existing_subject is None:
                    staged[candidate.relation_candidate_gid] = candidate
                    subjects[(candidate.snapshot_gid, candidate.candidate_hash)] = candidate
            self._relation_candidates = staged

    def save_business_review(self, review: CapabilityBusinessReview) -> None:
        _validate_business_review_references(review)
        with self._lock:
            snapshot = self._snapshots.get(review.evidence_snapshot_gid)
            if snapshot is None:
                raise ImmutableRecordError("business_review_evidence_snapshot_not_found")
            if not any(
                int(getattr(entry, "capability_version_gid", 0) or 0)
                == review.capability_version_gid
                for entry in snapshot.entries
            ):
                raise ImmutableRecordError("business_review_capability_version_not_in_snapshot")
            if review.review_gid in self._business_reviews:
                raise ImmutableRecordError("business_review_gid_already_exists")
            self._business_reviews[review.review_gid] = review

    def allocate_workflow_proposal_gid(self) -> int:
        """Allocate from the proposal namespace shared by every service using this store."""
        with self._lock:
            proposal_gid = max(
                self._workflow_proposal_gid_value,
                max(self._workflow_proposals, default=0),
            ) + 1
            if proposal_gid >= 2**63:
                raise ImmutableRecordError("workflow_proposal_gid_invalid")
            self._workflow_proposal_gid_value = proposal_gid
            return proposal_gid

    def save_workflow_proposal(self, proposal: Any) -> Any:
        """Insert one newly allocated proposal without replacing an existing row."""
        with self._lock:
            proposal_gid = int(proposal.proposal_gid)
            if not 0 < proposal_gid < 2**63:
                raise ImmutableRecordError("workflow_proposal_gid_invalid")
            if proposal_gid in self._workflow_proposals:
                raise ImmutableRecordError("workflow_proposal_gid_already_exists")
            staged = dict(self._workflow_proposals)
            staged[proposal_gid] = proposal
            self._workflow_proposals = staged
            self._workflow_proposal_gid_value = max(
                self._workflow_proposal_gid_value, proposal_gid,
            )
            return proposal

    def allocate_workflow_review_gid(self) -> int:
        """Allocate review identity from the store-owned shared namespace."""
        with self._lock:
            review_gid = max(
                self._workflow_review_gid_value,
                *(review.review_gid for proposal in self._workflow_proposals.values()
                  for review in proposal.reviews),
                *self._business_reviews,
                0,
            ) + 1
            if review_gid >= 2**63:
                raise ImmutableRecordError("workflow_review_gid_invalid")
            self._workflow_review_gid_value = review_gid
            return review_gid

    def replay_workflow_review(
        self, idempotency_key: str, fingerprint: tuple[object, ...],
    ) -> Any | None:
        with self._lock:
            replay = self._workflow_review_requests.get(idempotency_key)
            if replay is None:
                return None
            if replay[0] != fingerprint:
                raise ImmutableRecordError("idempotency_conflict")
            return replay[1]

    def transition_workflow_proposal(
        self, proposal: Any, resolved: Any, *, idempotency_key: str | None = None,
        request_fingerprint: tuple[object, ...] | None = None,
    ) -> Any:
        """CAS one ordinary proposal transition against the same durable row."""
        with self._lock:
            if idempotency_key is not None:
                if request_fingerprint is None:
                    raise ImmutableRecordError("idempotency_fingerprint_required")
                replay = self._workflow_review_requests.get(idempotency_key)
                if replay is not None:
                    if replay[0] != request_fingerprint:
                        raise ImmutableRecordError("idempotency_conflict")
                    return replay[1]
            current = self._workflow_proposals.get(proposal.proposal_gid)
            if (current is None or current.row_version != proposal.row_version
                    or current.status != proposal.status):
                raise ImmutableRecordError("row_version_conflict")
            staged = dict(self._workflow_proposals)
            staged_requests = dict(self._workflow_review_requests)
            staged[proposal.proposal_gid] = resolved
            if idempotency_key is not None:
                staged_requests[idempotency_key] = (request_fingerprint, resolved)
            self._workflow_proposals = staged
            self._workflow_review_requests = staged_requests
            return resolved

    def get_workflow_proposal(self, proposal_gid: int) -> Any | None:
        with self._lock:
            return self._workflow_proposals.get(proposal_gid)

    def list_workflow_proposals(self) -> tuple[Any, ...]:
        with self._lock:
            return tuple(sorted(self._workflow_proposals.values(), key=lambda item: item.proposal_gid))

    def decide_business_review_atomic(
        self, proposal: Any, resolved: Any, review: CapabilityBusinessReview,
        fingerprint: tuple[object, ...], idempotency_key: str,
    ) -> Any:
        """Commit proposal CAS, immutable review, and replay key under one lock."""
        _validate_business_review_references(review)
        with self._lock:
            replay = self._business_review_requests.get(idempotency_key)
            if replay is not None:
                if replay[0] != fingerprint:
                    raise ImmutableRecordError("idempotency_conflict")
                return replay[1]
            current = self._workflow_proposals.get(proposal.proposal_gid)
            if current is None or current.row_version != proposal.row_version or current.status != "pending_approval":
                raise ImmutableRecordError("row_version_conflict")
            if current.proposed_descriptor_hash != review.definition_hash:
                raise ImmutableRecordError("review_subject_hash_mismatch")
            snapshot = self._snapshots.get(review.evidence_snapshot_gid)
            if snapshot is None or not any(
                int(getattr(entry, "capability_version_gid", 0) or 0) == review.capability_version_gid
                for entry in snapshot.entries
            ):
                raise ImmutableRecordError("business_review_reference_invalid")
            if review.review_gid in self._business_reviews:
                raise ImmutableRecordError("business_review_gid_already_exists")
            # Stage every durable map before publishing any of the three writes.
            staged_reviews = dict(self._business_reviews)
            staged_proposals = dict(self._workflow_proposals)
            staged_requests = dict(self._business_review_requests)
            staged_reviews[review.review_gid] = review
            staged_proposals[proposal.proposal_gid] = resolved
            staged_requests[idempotency_key] = (fingerprint, resolved)
            self._business_reviews = staged_reviews
            self._workflow_proposals = staged_proposals
            self._business_review_requests = staged_requests
            return resolved

    def current_business_review(
        self, capability_version_gid: int, definition_hash: str,
    ) -> CapabilityBusinessReview | None:
        with self._lock:
            matching = (
                review for review in self._business_reviews.values()
                if review.capability_version_gid == capability_version_gid
                and review.definition_hash == definition_hash
            )
            latest = max(matching, key=lambda item: item.review_gid, default=None)
            return latest if latest is not None and latest.decision == "approved" else None

    def list_current_business_reviews(self) -> tuple[CapabilityBusinessReview, ...]:
        with self._lock:
            current: dict[tuple[int, str], CapabilityBusinessReview] = {}
            for review in sorted(self._business_reviews.values(), key=lambda item: item.review_gid, reverse=True):
                current.setdefault((review.capability_version_gid, review.definition_hash), review)
            return tuple(review for review in current.values() if review.decision == "approved")

    def save_rule_effectiveness(self, record: RuleEffectivenessRecord) -> None:
        with self._lock:
            if record.effectiveness_gid in self._rule_effectiveness:
                raise ImmutableRecordError("effectiveness_gid_already_exists")
            self._rule_effectiveness[record.effectiveness_gid] = record

    def list_rule_effectiveness(
        self, capability_version_gid: int, definition_hash: str,
    ) -> tuple[RuleEffectivenessRecord, ...]:
        with self._lock:
            return tuple(sorted((
                record for record in self._rule_effectiveness.values()
                if record.capability_version_gid == capability_version_gid
                and record.definition_hash == definition_hash
            ), key=lambda item: (item.measured_to, item.effectiveness_gid)))

    def _project_capabilities(self, document: SnapshotDocument) -> tuple[CapabilityProjection, ...]:
        projections: list[CapabilityProjection] = []
        seen: set[tuple[str, int]] = set()
        for capability in document.capabilities:
            key = (capability.capability_id, capability.major_version)
            if key in seen:
                raise ImmutableRecordError("duplicate_capability_major_in_snapshot")
            seen.add(key)
            capability_gid = self._logical_ids.get(capability.capability_id)
            if capability_gid is None:
                capability_gid = self._next_ids()
                self._logical_ids[capability.capability_id] = capability_gid
            major_key = (capability_gid, capability.major_version)
            capability_version_gid = self._major_ids.get(major_key)
            if capability_version_gid is None:
                capability_version_gid = self._next_ids()
                self._major_ids[major_key] = capability_version_gid
            projections.append(_projection(capability, capability_gid, capability_version_gid))
        return tuple(projections)


class SqlGovernanceStore(GovernanceStore):
    """DB-API persistence using only parameterized statements and one commit."""

    persistent = True

    def __init__(self, connection: Any, next_ids: Callable[[], int] = next_gid):
        self._connection = connection
        self._next_ids = next_ids

    def import_snapshot(self, document: SnapshotDocument) -> SnapshotRecord:
        cursor = self._connection.cursor()
        try:
            from .fingerprint import snapshot_fingerprint
            if snapshot_fingerprint(document) != document.snapshot_hash:
                raise ImmutableRecordError("snapshot_hash_mismatch")
            existing = self._select_snapshot(cursor, document.snapshot_hash)
            if existing is not None:
                return self._load_existing_snapshot(cursor, existing, document)
            created_at = _now()
            scan_run_gid = self._next_ids()
            snapshot_gid = self._next_ids()
            projections = tuple(
                self._resolve_projection(cursor, capability, snapshot_gid)
                for capability in document.capabilities
            )
            self._ensure_no_duplicate_majors(projections)
            self._insert_scan_run(cursor, scan_run_gid, document, created_at)
            try:
                self._insert_snapshot(cursor, snapshot_gid, scan_run_gid, document, created_at)
            except Exception as exc:
                if not _duplicate_key(exc):
                    raise
                self._connection.rollback()
                recovered = self._select_snapshot(cursor, document.snapshot_hash)
                if recovered is None:
                    raise ImmutableRecordError("snapshot_hash_conflict: winning snapshot was not recoverable") from exc
                return self._load_existing_snapshot(cursor, recovered, document)
            entries = self._insert_snapshot_entries(cursor, snapshot_gid, projections, document, created_at)
            node_gids = self._insert_nodes(cursor, snapshot_gid, document, created_at)
            binding_gids = self._insert_bindings(cursor, snapshot_gid, projections, node_gids, document)
            relation_gids = self._insert_relations(cursor, snapshot_gid, node_gids, document)
            self._insert_scan_findings(cursor, snapshot_gid, document)
            self._update_mutable_projections(cursor, snapshot_gid, projections, created_at)
            record = SnapshotRecord(
                snapshot_gid=snapshot_gid, scan_run_gid=scan_run_gid, document=document,
                entries=entries, node_gids=node_gids, binding_gids=binding_gids, relation_gids=relation_gids,
            )
            self._connection.commit()
            return record
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def get_workflow_proposal(self, proposal_gid: int) -> Any | None:
        """Rehydrate the proposal state used for a cross-process decision CAS."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT proposal_gid, capability_version_gid, base_snapshot_gid, proposed_descriptor_hash, "
                "status, submitted_by_gid, change_json, row_version "
                "FROM workmanship_base_capability_change_proposals WHERE proposal_gid = %s",
                (proposal_gid,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            payload = _json_load(_row_value(row, "change_json", 6))
            from .workflow import Proposal
            review_kind = str(payload.get("review_kind", "business_definition"))
            reviews = self._workflow_reviews(
                cursor, int(_row_value(row, "proposal_gid", 0)), review_kind,
                _text_value(_row_value(row, "proposed_descriptor_hash", 3)),
                str(payload.get("evidence_hash", "")),
            )
            return Proposal(
                proposal_gid=int(_row_value(row, "proposal_gid", 0)),
                capability_id=str(payload.get("capability_id", "")),
                capability_version_gid=int(_row_value(row, "capability_version_gid", 1)),
                base_snapshot_gid=int(_row_value(row, "base_snapshot_gid", 2)),
                previous_hash=str(payload.get("previous_hash", "")),
                proposed_descriptor_hash=_text_value(_row_value(row, "proposed_descriptor_hash", 3)),
                evidence_hash=str(payload.get("evidence_hash", "")),
                submitted_by_gid=str(_row_value(row, "submitted_by_gid", 5)),
                status=str(_row_value(row, "status", 4)),
                row_version=int(_row_value(row, "row_version", 7)),
                reviews=reviews,
                review_kind=review_kind,
            )
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def list_workflow_proposals(self) -> tuple[Any, ...]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT proposal_gid, capability_version_gid, base_snapshot_gid, proposed_descriptor_hash, "
                "status, submitted_by_gid, change_json, row_version "
                "FROM workmanship_base_capability_change_proposals ORDER BY proposal_gid",
            )
            rows = tuple(cursor.fetchall())
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        return tuple(self._proposal_from_row(row) for row in rows)

    def _proposal_from_row(self, row: Any) -> Any:
        payload = _json_load(_row_value(row, "change_json", 6))
        from .workflow import Proposal
        proposal_gid = int(_row_value(row, "proposal_gid", 0))
        review_kind = str(payload.get("review_kind", "business_definition"))
        cursor = self._connection.cursor()
        try:
            reviews = self._workflow_reviews(
                cursor, proposal_gid, review_kind,
                _text_value(_row_value(row, "proposed_descriptor_hash", 3)),
                str(payload.get("evidence_hash", "")),
            )
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        return Proposal(
            proposal_gid=proposal_gid,
            capability_id=str(payload.get("capability_id", "")),
            capability_version_gid=int(_row_value(row, "capability_version_gid", 1)),
            base_snapshot_gid=int(_row_value(row, "base_snapshot_gid", 2)),
            previous_hash=str(payload.get("previous_hash", "")),
            proposed_descriptor_hash=_text_value(_row_value(row, "proposed_descriptor_hash", 3)),
            evidence_hash=str(payload.get("evidence_hash", "")),
            submitted_by_gid=str(_row_value(row, "submitted_by_gid", 5)),
            status=str(_row_value(row, "status", 4)),
            row_version=int(_row_value(row, "row_version", 7)),
            reviews=reviews,
            review_kind=review_kind,
        )

    @staticmethod
    def _workflow_reviews(
        cursor: Any, proposal_gid: int, review_kind: str,
        descriptor_hash: str, evidence_hash: str,
    ) -> tuple[Any, ...]:
        from .workflow import Review
        if review_kind == "standard":
            cursor.execute(
                "SELECT review_gid, proposal_gid, review_stage, decision, reviewer_gid, "
                "decision_reason, evidence_snapshot_gid, decided_at "
                "FROM workmanship_base_capability_reviews WHERE proposal_gid = %s "
                "ORDER BY review_gid",
                (proposal_gid,),
            )
            return tuple(
                Review(
                    review_gid=int(_row_value(row, "review_gid", 0)),
                    proposal_gid=int(_row_value(row, "proposal_gid", 1)),
                    review_stage=str(_row_value(row, "review_stage", 2)),
                    decision=str(_row_value(row, "decision", 3)),
                    reviewer_gid=str(_row_value(row, "reviewer_gid", 4)),
                    base_snapshot_gid=int(_row_value(row, "evidence_snapshot_gid", 6)),
                    descriptor_hash=descriptor_hash,
                    evidence_snapshot_hash=evidence_hash,
                    decided_at=_row_value(row, "decided_at", 7),
                    decision_reason=str(_row_value(row, "decision_reason", 5)),
                )
                for row in cursor.fetchall()
            )
        cursor.execute(
            "SELECT business_review_gid, proposal_gid, decision, reviewer_gid, evidence_snapshot_gid, "
            "definition_hash, decision_reason, decided_at "
            "FROM workmanship_base_capability_business_reviews WHERE proposal_gid = %s "
            "ORDER BY business_review_gid",
            (proposal_gid,),
        )
        return tuple(
            Review(
                review_gid=int(_row_value(row, "business_review_gid", 0)),
                proposal_gid=int(_row_value(row, "proposal_gid", 1)),
                review_stage="business_definition",
                decision=str(_row_value(row, "decision", 2)),
                reviewer_gid=str(_row_value(row, "reviewer_gid", 3)),
                base_snapshot_gid=int(_row_value(row, "evidence_snapshot_gid", 4)),
                descriptor_hash=_text_value(_row_value(row, "definition_hash", 5)),
                evidence_snapshot_hash="",
                decided_at=_row_value(row, "decided_at", 7),
                decision_reason=str(_row_value(row, "decision_reason", 6)),
                review_type="business_definition",
            )
            for row in cursor.fetchall()
        )

    def allocate_workflow_proposal_gid(self) -> int:
        """Allocate the next proposal id from one durable cross-process namespace."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO workmanship_display_id_counters (seq_name, val) "
                "SELECT %s, COALESCE(MAX(proposal_gid), 0) "
                "FROM workmanship_base_capability_change_proposals "
                "ON DUPLICATE KEY UPDATE val = GREATEST(val, VALUES(val))",
                (_WORKFLOW_PROPOSAL_SEQUENCE,),
            )
            cursor.execute(
                "UPDATE workmanship_display_id_counters "
                "SET val = LAST_INSERT_ID(val + 1) WHERE seq_name = %s",
                (_WORKFLOW_PROPOSAL_SEQUENCE,),
            )
            if getattr(cursor, "rowcount", 1) != 1:
                raise ImmutableRecordError("workflow_proposal_sequence_unavailable")
            cursor.execute("SELECT LAST_INSERT_ID() AS proposal_gid")
            row = cursor.fetchone()
            proposal_gid = int(_row_value(row, "proposal_gid", 0)) if row is not None else 0
            if not 0 < proposal_gid < 2**63:
                raise ImmutableRecordError("workflow_proposal_gid_invalid")
            self._connection.commit()
            return proposal_gid
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def allocate_workflow_review_gid(self) -> int:
        """Allocate a restart-safe review id from the Base counter."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO workmanship_display_id_counters (seq_name, val) "
                "SELECT %s, GREATEST("
                "COALESCE((SELECT MAX(review_gid) FROM workmanship_base_capability_reviews), 0), "
                "COALESCE((SELECT MAX(business_review_gid) FROM workmanship_base_capability_business_reviews), 0)) "
                "ON DUPLICATE KEY UPDATE val = GREATEST(val, VALUES(val))",
                (_WORKFLOW_REVIEW_SEQUENCE,),
            )
            cursor.execute(
                "UPDATE workmanship_display_id_counters "
                "SET val = LAST_INSERT_ID(val + 1) WHERE seq_name = %s",
                (_WORKFLOW_REVIEW_SEQUENCE,),
            )
            if getattr(cursor, "rowcount", 1) != 1:
                raise ImmutableRecordError("workflow_review_sequence_unavailable")
            cursor.execute("SELECT LAST_INSERT_ID() AS review_gid")
            row = cursor.fetchone()
            review_gid = int(_row_value(row, "review_gid", 0)) if row is not None else 0
            if not 0 < review_gid < 2**63:
                raise ImmutableRecordError("workflow_review_gid_invalid")
            self._connection.commit()
            return review_gid
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def save_workflow_proposal(self, proposal: Any) -> Any:
        """Insert one allocated proposal; a collision never updates the existing row."""
        cursor = self._connection.cursor()
        try:
            proposal_gid = int(proposal.proposal_gid)
            if not 0 < proposal_gid < 2**63:
                raise ImmutableRecordError("workflow_proposal_gid_invalid")
            cursor.execute(
                "INSERT INTO workmanship_base_capability_change_proposals "
                "(proposal_gid, capability_version_gid, base_snapshot_gid, proposed_descriptor_hash, change_type, risk_level, status, submitted_by_gid, submitted_at, summary, change_json, row_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (proposal.proposal_gid, proposal.capability_version_gid, proposal.base_snapshot_gid,
                 proposal.proposed_descriptor_hash, proposal.review_kind, "governed", proposal.status,
                 int(proposal.submitted_by_gid), _now(), proposal.capability_id,
                 json.dumps({"capability_id": proposal.capability_id, "previous_hash": proposal.previous_hash,
                             "evidence_hash": proposal.evidence_hash, "review_kind": proposal.review_kind}, separators=(",", ":")),
                 proposal.row_version),
            )
            self._connection.commit()
            return proposal
        except Exception as exc:
            self._connection.rollback()
            if _duplicate_key(exc):
                raise ImmutableRecordError("workflow_proposal_gid_already_exists") from exc
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def _standard_review_replay_result(
        self, proposal_gid: int, review_gid: int, status: str, row_version: int,
    ) -> Any:
        proposal = self.get_workflow_proposal(proposal_gid)
        if proposal is None:
            raise ImmutableRecordError("workflow_review_replay_missing")
        reviews = tuple(review for review in proposal.reviews if review.review_gid <= review_gid)
        return replace(proposal, status=status, row_version=row_version, reviews=reviews)

    def replay_workflow_review(
        self, idempotency_key: str, fingerprint: tuple[object, ...],
    ) -> Any | None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT request_fingerprint, proposal_gid, review_gid, result_status, result_row_version "
                "FROM workmanship_base_capability_standard_review_requests "
                "WHERE idempotency_key = %s", (idempotency_key,),
            )
            replay = cursor.fetchone()
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        if replay is None:
            return None
        encoded = json.dumps(fingerprint, separators=(",", ":"), default=str)
        if str(_row_value(replay, "request_fingerprint", 0)) != encoded:
            raise ImmutableRecordError("idempotency_conflict")
        return self._standard_review_replay_result(
            int(_row_value(replay, "proposal_gid", 1)),
            int(_row_value(replay, "review_gid", 2)),
            str(_row_value(replay, "result_status", 3)),
            int(_row_value(replay, "result_row_version", 4)),
        )

    def transition_workflow_proposal(
        self, proposal: Any, resolved: Any, *, idempotency_key: str | None = None,
        request_fingerprint: tuple[object, ...] | None = None,
    ) -> Any:
        """Apply an ordinary proposal transition with the same SQL CAS as a review."""
        cursor = self._connection.cursor()
        try:
            encoded = None
            if idempotency_key is not None:
                if request_fingerprint is None:
                    raise ImmutableRecordError("idempotency_fingerprint_required")
                encoded = json.dumps(request_fingerprint, separators=(",", ":"), default=str)
                cursor.execute(
                    "SELECT request_fingerprint, proposal_gid, review_gid, result_status, result_row_version "
                    "FROM workmanship_base_capability_standard_review_requests "
                    "WHERE idempotency_key = %s FOR UPDATE", (idempotency_key,),
                )
                replay = cursor.fetchone()
                if replay is not None:
                    if str(_row_value(replay, "request_fingerprint", 0)) != encoded:
                        raise ImmutableRecordError("idempotency_conflict")
                    self._connection.commit()
                    return self._standard_review_replay_result(
                        int(_row_value(replay, "proposal_gid", 1)),
                        int(_row_value(replay, "review_gid", 2)),
                        str(_row_value(replay, "result_status", 3)),
                        int(_row_value(replay, "result_row_version", 4)),
                    )
            cursor.execute(
                "UPDATE workmanship_base_capability_change_proposals "
                "SET status = %s, row_version = row_version + 1 "
                "WHERE proposal_gid = %s AND row_version = %s AND status = %s "
                "AND proposed_descriptor_hash = BINARY %s",
                (resolved.status, proposal.proposal_gid, proposal.row_version,
                 proposal.status, proposal.proposed_descriptor_hash),
            )
            if getattr(cursor, "rowcount", 1) != 1:
                raise ImmutableRecordError("row_version_conflict")
            appended = resolved.reviews[len(proposal.reviews):]
            if appended:
                if len(appended) != 1 or resolved.review_kind != "standard":
                    raise ImmutableRecordError("workflow_review_append_invalid")
                review = appended[0]
                cursor.execute(
                    "INSERT INTO workmanship_base_capability_reviews "
                    "(review_gid, proposal_gid, review_stage, decision, reviewer_gid, decision_reason, evidence_snapshot_gid, decided_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (review.review_gid, review.proposal_gid, review.review_stage,
                     review.decision, int(review.reviewer_gid), review.decision_reason,
                     review.base_snapshot_gid, review.decided_at),
                )
                if idempotency_key is not None:
                    cursor.execute(
                        "INSERT INTO workmanship_base_capability_standard_review_requests "
                        "(idempotency_key, request_fingerprint, proposal_gid, review_gid, result_status, result_row_version) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (idempotency_key, encoded, proposal.proposal_gid, review.review_gid,
                         resolved.status, resolved.row_version),
                    )
            self._connection.commit()
            return self.get_workflow_proposal(proposal.proposal_gid) or resolved
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def decide_business_review_atomic(
        self, proposal: Any, resolved: Any, review: CapabilityBusinessReview,
        fingerprint: tuple[object, ...], idempotency_key: str,
    ) -> Any:
        """One SQL transaction: replay check, proposal CAS, review append, replay key."""
        _validate_business_review_references(review)
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT request_fingerprint, proposal_gid FROM workmanship_base_capability_business_review_requests "
                "WHERE idempotency_key = %s FOR UPDATE", (idempotency_key,),
            )
            replay = cursor.fetchone()
            encoded = json.dumps(fingerprint, separators=(",", ":"), default=str)
            if replay is not None:
                if str(_row_value(replay, "request_fingerprint", 0)) != encoded:
                    raise ImmutableRecordError("idempotency_conflict")
                self._connection.commit()
                return self.get_workflow_proposal(proposal.proposal_gid) or resolved
            cursor.execute(
                "UPDATE workmanship_base_capability_change_proposals "
                "SET status = %s, row_version = row_version + 1 "
                "WHERE proposal_gid = %s AND row_version = %s AND status = 'pending_approval' "
                "AND proposed_descriptor_hash = BINARY %s",
                (resolved.status, proposal.proposal_gid, proposal.row_version, review.definition_hash),
            )
            if getattr(cursor, "rowcount", 1) != 1:
                raise ImmutableRecordError("row_version_conflict")
            cursor.execute(
                "INSERT INTO workmanship_base_capability_business_reviews "
                "(business_review_gid, proposal_gid, capability_version_gid, definition_hash, decision, decision_reason, reviewer_gid, reviewer_role, evidence_snapshot_gid, decided_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (review.review_gid, review.proposal_gid, review.capability_version_gid, review.definition_hash,
                 review.decision, review.decision_reason, int(review.reviewer_gid), review.reviewer_role,
                 review.evidence_snapshot_gid, review.decided_at),
            )
            cursor.execute(
                "INSERT INTO workmanship_base_capability_business_review_requests "
                "(idempotency_key, request_fingerprint, proposal_gid, review_gid) VALUES (%s, %s, %s, %s)",
                (idempotency_key, encoded, proposal.proposal_gid, review.review_gid),
            )
            self._connection.commit()
            return self.get_workflow_proposal(proposal.proposal_gid) or resolved
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def get_snapshot(self, snapshot_gid: int) -> SnapshotRecord | None:
        """Rehydrate a snapshot from immutable rows after a process restart.

        The service must consume this public port instead of reaching into a
        memory-store dictionary.  Descriptor, node, binding, and relation
        records are all pinned by ``snapshot_gid`` before constructing the
        immutable domain object.
        """
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT snapshot_gid, scan_run_gid, snapshot_hash, code_revision, catalog_release_id, catalog_hash, "
                "(SELECT status FROM workmanship_base_capability_scan_runs AS scan_run "
                "WHERE scan_run.scan_run_gid = workmanship_base_capability_snapshots.scan_run_gid) AS scan_status "
                "FROM workmanship_base_capability_snapshots WHERE snapshot_gid = %s",
                (int(snapshot_gid),),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            snapshot_id = int(_row_value(row, "snapshot_gid", 0))
            scan_run_gid = int(_row_value(row, "scan_run_gid", 1))
            snapshot_hash = str(_row_value(row, "snapshot_hash", 2))
            code_revision = str(_row_value(row, "code_revision", 3))
            product_release = str(_row_value(row, "catalog_release_id", 4))
            catalog_hash = str(_row_value(row, "catalog_hash", 5))
            scan_status = str(_row_value(row, "scan_status", 6))

            cursor.execute(
                "SELECT snapshot_entry_gid, capability_entry.capability_gid, "
                "snapshot_entry.capability_version_gid, capability_entry.capability_id, "
                "capability_version.major_version, capability_entry.owner_domain, "
                "capability_version.semantic_class, capability_version.business_effect, "
                "capability_version.lifecycle_status, snapshot_entry.descriptor_hash, "
                "snapshot_entry.input_schema_hash, snapshot_entry.output_schema_hash, "
                "snapshot_entry.error_schema_hash, snapshot_entry.policy_hash, "
                "snapshot_entry.provider_hash, snapshot_entry.descriptor_json "
                "FROM workmanship_base_capability_snapshot_entries AS snapshot_entry "
                "JOIN workmanship_base_capability_versions AS capability_version "
                "ON capability_version.capability_version_gid = snapshot_entry.capability_version_gid "
                "JOIN workmanship_base_capability_entries AS capability_entry "
                "ON capability_entry.capability_gid = capability_version.capability_gid "
                "WHERE snapshot_entry.snapshot_gid = %s ORDER BY snapshot_entry.snapshot_entry_gid",
                (snapshot_id,),
            )
            entry_rows = tuple(cursor.fetchall())
            entries: list[SnapshotEntry] = []
            capabilities: list[ScannedCapability] = []
            for item in entry_rows:
                entries.append(self._entry_from_row(item))
                payload = _json_load(_row_value(item, "descriptor_json", 15))
                descriptor = _json_load(payload.get("descriptor", payload))
                fingerprint_payload = payload.get("fingerprint")
                fingerprint = CapabilityFingerprint(**fingerprint_payload) if isinstance(fingerprint_payload, Mapping) else None
                maturity_payload = payload.get("business_maturity")
                maturity = CapabilityMaturity(**maturity_payload) if isinstance(maturity_payload, Mapping) else CapabilityMaturity("L0", ("unregistered",))
                capabilities.append(ScannedCapability(
                    capability_id=str(_row_value(item, "capability_id", 3)),
                    major_version=int(_row_value(item, "major_version", 4)),
                    owner_domain=str(_row_value(item, "owner_domain", 5)),
                    semantic_class=str(_row_value(item, "semantic_class", 6)),
                    business_effect=str(_row_value(item, "business_effect", 7)),
                    lifecycle_status=str(_row_value(item, "lifecycle_status", 8)),
                    descriptor_hash=str(_row_value(item, "descriptor_hash", 9)),
                    input_schema_hash=str(_row_value(item, "input_schema_hash", 10)),
                    output_schema_hash=str(_row_value(item, "output_schema_hash", 11)),
                    error_schema_hash=str(_row_value(item, "error_schema_hash", 12)),
                    policy_hash=str(_row_value(item, "policy_hash", 13)),
                    provider_hash=str(_row_value(item, "provider_hash", 14)),
                    descriptor=descriptor,
                    business_rules=tuple(payload.get("business_rules", ())),
                    fingerprint=fingerprint,
                    business_layer_evidence=_json_load(payload.get("business_layer_evidence", {})),
                    business_maturity=maturity,
                ))

            cursor.execute(
                "SELECT implementation_node_gid, owner_domain, node_type, canonical_key, source_path, "
                "source_symbol, http_method, route_path, artifact_hash, metadata_json "
                "FROM workmanship_base_capability_implementation_nodes WHERE snapshot_gid = %s "
                "ORDER BY implementation_node_gid",
                (snapshot_id,),
            )
            node_rows = tuple(cursor.fetchall())
            nodes: list[ImplementationNode] = []
            node_gids: dict[str, int] = {}
            for item in node_rows:
                gid = int(_row_value(item, "implementation_node_gid", 0))
                canonical_key = str(_row_value(item, "canonical_key", 3))
                node_gids[canonical_key] = gid
                nodes.append(ImplementationNode(
                    canonical_key,
                    str(_row_value(item, "owner_domain", 1)),
                    str(_row_value(item, "node_type", 2)),
                    str(_row_value(item, "source_path", 4)),
                    str(_row_value(item, "artifact_hash", 8)),
                    _optional_row_value(item, "source_symbol", 5),
                    _optional_row_value(item, "http_method", 6),
                    _optional_row_value(item, "route_path", 7),
                    _json_load(_row_value(item, "metadata_json", 9)),
                ))

            version_to_key = {
                int(_row_value(item, "capability_version_gid", 2)):
                (str(_row_value(item, "capability_id", 3)), int(_row_value(item, "major_version", 4)))
                for item in entry_rows
            }
            gid_to_key = {gid: key for key, gid in node_gids.items()}
            cursor.execute(
                "SELECT binding_gid, capability_version_gid, implementation_node_gid, binding_type, binding_hash "
                "FROM workmanship_base_capability_bindings WHERE snapshot_gid = %s ORDER BY binding_gid",
                (snapshot_id,),
            )
            binding_rows = tuple(cursor.fetchall())
            bindings: list[CapabilityBinding] = []
            binding_gids: list[int] = []
            for item in binding_rows:
                binding_gid = int(_row_value(item, "binding_gid", 0))
                version = version_to_key.get(int(_row_value(item, "capability_version_gid", 1)))
                node_key = gid_to_key.get(int(_row_value(item, "implementation_node_gid", 2)))
                if version is None or node_key is None:
                    raise ImmutableRecordError("binding_references_unknown_snapshot_entity")
                bindings.append(CapabilityBinding(
                    version[0], version[1], node_key,
                    str(_row_value(item, "binding_type", 3)), str(_row_value(item, "binding_hash", 4)),
                ))
                binding_gids.append(binding_gid)

            cursor.execute(
                "SELECT relation_gid, from_node_gid, to_node_gid, relation_type, relation_hash "
                "FROM workmanship_base_capability_implementation_relations WHERE snapshot_gid = %s ORDER BY relation_gid",
                (snapshot_id,),
            )
            relation_rows = tuple(cursor.fetchall())
            relations: list[ImplementationRelation] = []
            relation_gids: list[int] = []
            for item in relation_rows:
                relation_gid = int(_row_value(item, "relation_gid", 0))
                from_key = gid_to_key.get(int(_row_value(item, "from_node_gid", 1)))
                to_key = gid_to_key.get(int(_row_value(item, "to_node_gid", 2)))
                if from_key is None or to_key is None:
                    raise ImmutableRecordError("relation_references_unknown_snapshot_node")
                relations.append(ImplementationRelation(
                    from_key, to_key, str(_row_value(item, "relation_type", 3)),
                    str(_row_value(item, "relation_hash", 4)),
                ))
                relation_gids.append(relation_gid)
            cursor.execute(
                "SELECT finding_gid, finding_type, severity, status, source_type, finding_fingerprint, "
                "title, summary, recommendation FROM workmanship_base_capability_findings "
                "WHERE snapshot_gid = %s AND source_type = %s ORDER BY finding_gid",
                (snapshot_id, "scanner"),
            )
            scan_findings = tuple(
                ScanFinding(
                    str(_row_value(item, "finding_type", 1)), str(_row_value(item, "severity", 2)),
                    str(_row_value(item, "title", 6)), str(_row_value(item, "recommendation", 8)),
                    str(_row_value(item, "summary", 7)),
                )
                for item in cursor.fetchall()
            )
            document = SnapshotDocument(
                product_release, None, code_revision, snapshot_hash,
                tuple(capabilities), tuple(nodes), tuple(bindings), tuple(relations), scan_findings, scan_status,
                catalog_hash=catalog_hash,
            )
            return SnapshotRecord(
                snapshot_id, scan_run_gid, document, tuple(entries), node_gids,
                tuple(binding_gids), tuple(relation_gids),
            )
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def latest_snapshot(self) -> SnapshotRecord | None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT snapshot_gid FROM workmanship_base_capability_snapshots "
                "ORDER BY snapshot_gid DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return self.get_snapshot(int(_row_value(row, "snapshot_gid", 0))) if row is not None else None
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def list_entries(self, snapshot_gid: int | None = None) -> tuple[SnapshotEntry, ...]:
        snapshot = self.latest_snapshot() if snapshot_gid is None else self.get_snapshot(snapshot_gid)
        return tuple(getattr(snapshot, "entries", ())) if snapshot is not None else ()

    def get_findings(self, snapshot_gid: int) -> tuple[Mapping[str, Any], ...]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT finding_gid, finding_type, severity, status, source_type, finding_fingerprint, "
                "title, summary, recommendation FROM workmanship_base_capability_findings "
                "WHERE snapshot_gid = %s ORDER BY finding_gid",
                (int(snapshot_gid),),
            )
            return tuple(_finding_row_record(item) for item in cursor.fetchall())
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def save_business_projection(self, projection: CapabilityBusinessProjection) -> None:
        cursor = self._connection.cursor()
        try:
            purpose = projection.purpose
            cursor.execute(
                "INSERT INTO workmanship_base_capability_business_purposes "
                "(purpose_gid, capability_version_gid, definition_hash, business_effect, acceptance_criteria_json, evidence_snapshot_gid, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    purpose.purpose_gid, purpose.capability_version_gid, purpose.definition_hash,
                    purpose.business_effect, _json(purpose.acceptance_criteria),
                    purpose.evidence_snapshot_gid, purpose.created_at,
                ),
            )
            for rule in projection.rules:
                cursor.execute(
                    "INSERT INTO workmanship_base_capability_business_rules "
                    "(business_rule_gid, capability_version_gid, definition_hash, rule_id, rule_version, statement, applies_when, enforcement_ref, error_code, test_refs_json, evidence_snapshot_gid) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        rule.business_rule_gid, rule.capability_version_gid, rule.definition_hash,
                        rule.rule_id, rule.rule_version, rule.statement, rule.applies_when,
                        rule.enforcement_ref, rule.error_code, _json(rule.test_refs),
                        rule.evidence_snapshot_gid,
                    ),
                )
            for candidate in projection.relation_candidates:
                cursor.execute(
                    "INSERT INTO workmanship_base_capability_relation_candidates "
                    "(relation_candidate_gid, snapshot_gid, candidate_hash, relation_type, source, capability_keys_json, evidence_json, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        candidate.relation_candidate_gid, candidate.snapshot_gid,
                        candidate.candidate_hash, candidate.relation_type, candidate.source,
                        _json(candidate.capability_keys), _json(candidate.evidence), candidate.status,
                    ),
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def list_relation_candidates(self, snapshot_gid: int) -> tuple[CapabilityRelationCandidate, ...]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT relation_candidate_gid, snapshot_gid, candidate_hash, relation_type, source, "
                "capability_keys_json, evidence_json, status "
                "FROM workmanship_base_capability_relation_candidates "
                "WHERE snapshot_gid = %s ORDER BY relation_candidate_gid",
                (int(snapshot_gid),),
            )
            return tuple(
                CapabilityRelationCandidate(
                    relation_candidate_gid=int(_row_value(row, "relation_candidate_gid", 0)),
                    snapshot_gid=int(_row_value(row, "snapshot_gid", 1)),
                    candidate_hash=_text_value(_row_value(row, "candidate_hash", 2)),
                    relation_type=str(_row_value(row, "relation_type", 3)),
                    source=str(_row_value(row, "source", 4)),
                    capability_keys=_json_tuple(_row_value(row, "capability_keys_json", 5)),
                    evidence=_json_load(_row_value(row, "evidence_json", 6)),
                    status=str(_row_value(row, "status", 7)),
                )
                for row in cursor.fetchall()
            )
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def save_relation_candidates(self, candidates: tuple[CapabilityRelationCandidate, ...]) -> None:
        if not candidates:
            return
        gids: dict[int, CapabilityRelationCandidate] = {}
        subjects: dict[tuple[int, str], CapabilityRelationCandidate] = {}
        # Match Memory semantics before opening the write transaction.
        for candidate in candidates:
            gid_match = gids.get(candidate.relation_candidate_gid)
            subject_match = subjects.get((candidate.snapshot_gid, candidate.candidate_hash))
            if gid_match is not None and gid_match != candidate:
                raise ImmutableRecordError("relation_candidate_gid_already_exists")
            if subject_match is not None and subject_match != candidate:
                raise ImmutableRecordError("uq_capability_relation_candidate")
            gids[candidate.relation_candidate_gid] = candidate
            subjects[(candidate.snapshot_gid, candidate.candidate_hash)] = candidate
        cursor = self._connection.cursor()
        try:
            for candidate in candidates:
                cursor.execute(
                    "INSERT INTO workmanship_base_capability_relation_candidates "
                    "(relation_candidate_gid, snapshot_gid, candidate_hash, relation_type, source, capability_keys_json, evidence_json, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE relation_candidate_gid=relation_candidate_gid",
                    (candidate.relation_candidate_gid, candidate.snapshot_gid, candidate.candidate_hash,
                     candidate.relation_type, candidate.source, _json(candidate.capability_keys),
                     _json(candidate.evidence), candidate.status),
                )
                cursor.execute(
                    "SELECT relation_candidate_gid, snapshot_gid, candidate_hash, relation_type, source, "
                    "capability_keys_json, evidence_json, status "
                    "FROM workmanship_base_capability_relation_candidates "
                    "WHERE relation_candidate_gid = %s OR (snapshot_gid = %s AND candidate_hash = %s) FOR UPDATE",
                    (candidate.relation_candidate_gid, candidate.snapshot_gid, candidate.candidate_hash),
                )
                matches = tuple(CapabilityRelationCandidate(
                    relation_candidate_gid=int(_row_value(row, "relation_candidate_gid", 0)),
                    snapshot_gid=int(_row_value(row, "snapshot_gid", 1)),
                    candidate_hash=_text_value(_row_value(row, "candidate_hash", 2)),
                    relation_type=str(_row_value(row, "relation_type", 3)), source=str(_row_value(row, "source", 4)),
                    capability_keys=_json_tuple(_row_value(row, "capability_keys_json", 5)),
                    evidence=_json_load(_row_value(row, "evidence_json", 6)), status=str(_row_value(row, "status", 7)),
                ) for row in cursor.fetchall())
                if len(matches) != 1 or matches[0] != candidate:
                    if any(item.relation_candidate_gid == candidate.relation_candidate_gid for item in matches):
                        raise ImmutableRecordError("relation_candidate_gid_already_exists")
                    if any((item.snapshot_gid, item.candidate_hash) == (candidate.snapshot_gid, candidate.candidate_hash) for item in matches):
                        raise ImmutableRecordError("uq_capability_relation_candidate")
                    raise ImmutableRecordError("relation_candidate_immutable_conflict")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def save_business_review(self, review: CapabilityBusinessReview) -> None:
        _validate_business_review_references(review)
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO workmanship_base_capability_business_reviews "
                "(business_review_gid, proposal_gid, capability_version_gid, definition_hash, decision, decision_reason, reviewer_gid, reviewer_role, evidence_snapshot_gid, decided_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    review.review_gid, review.proposal_gid, review.capability_version_gid,
                    review.definition_hash, review.decision, review.decision_reason,
                    int(review.reviewer_gid), review.reviewer_role,
                    review.evidence_snapshot_gid, review.decided_at,
                ),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def current_business_review(
        self, capability_version_gid: int, definition_hash: str,
    ) -> CapabilityBusinessReview | None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT business_review_gid, capability_version_gid, definition_hash, decision, "
                "decision_reason, reviewer_gid, reviewer_role, decided_at, proposal_gid, evidence_snapshot_gid "
                "FROM workmanship_base_capability_business_reviews "
                "WHERE capability_version_gid = %s AND definition_hash = BINARY %s "
                "ORDER BY business_review_gid DESC LIMIT 1",
                (int(capability_version_gid), definition_hash),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            review = CapabilityBusinessReview(
                review_gid=int(_row_value(row, "business_review_gid", 0)),
                capability_version_gid=int(_row_value(row, "capability_version_gid", 1)),
                definition_hash=_text_value(_row_value(row, "definition_hash", 2)),
                decision=str(_row_value(row, "decision", 3)),
                decision_reason=str(_row_value(row, "decision_reason", 4)),
                reviewer_gid=str(_row_value(row, "reviewer_gid", 5)),
                reviewer_role=str(_row_value(row, "reviewer_role", 6)),
                decided_at=_row_value(row, "decided_at", 7),
                proposal_gid=int(_row_value(row, "proposal_gid", 8)),
                evidence_snapshot_gid=int(_row_value(row, "evidence_snapshot_gid", 9)),
            )
            return review if review.decision == "approved" else None
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def list_current_business_reviews(self) -> tuple[CapabilityBusinessReview, ...]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT business_review_gid, capability_version_gid, definition_hash, decision, "
                "decision_reason, reviewer_gid, reviewer_role, decided_at, proposal_gid, evidence_snapshot_gid "
                "FROM workmanship_base_capability_business_reviews ORDER BY business_review_gid DESC"
            )
            current: dict[tuple[int, str], CapabilityBusinessReview] = {}
            for row in cursor.fetchall():
                review = CapabilityBusinessReview(
                    review_gid=int(_row_value(row, "business_review_gid", 0)),
                    capability_version_gid=int(_row_value(row, "capability_version_gid", 1)),
                    definition_hash=_text_value(_row_value(row, "definition_hash", 2)),
                    decision=str(_row_value(row, "decision", 3)),
                    decision_reason=str(_row_value(row, "decision_reason", 4)),
                    reviewer_gid=str(_row_value(row, "reviewer_gid", 5)),
                    reviewer_role=str(_row_value(row, "reviewer_role", 6)),
                    decided_at=_row_value(row, "decided_at", 7),
                    proposal_gid=int(_row_value(row, "proposal_gid", 8)),
                    evidence_snapshot_gid=int(_row_value(row, "evidence_snapshot_gid", 9)),
                )
                current.setdefault((review.capability_version_gid, review.definition_hash), review)
            return tuple(review for review in current.values() if review.decision == "approved")
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def save_rule_effectiveness(self, record: RuleEffectivenessRecord) -> None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO workmanship_base_capability_rule_effectiveness "
                "(effectiveness_gid, capability_version_gid, definition_hash, metric_name, metric_value, evidence_json, measured_from, measured_to) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    record.effectiveness_gid, record.capability_version_gid,
                    record.definition_hash, record.metric_name, record.metric_value,
                    _json(record.evidence), record.measured_from, record.measured_to,
                ),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def list_rule_effectiveness(
        self, capability_version_gid: int, definition_hash: str,
    ) -> tuple[RuleEffectivenessRecord, ...]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT effectiveness_gid, capability_version_gid, definition_hash, metric_name, "
                "metric_value, evidence_json, measured_from, measured_to "
                "FROM workmanship_base_capability_rule_effectiveness "
                "WHERE capability_version_gid = %s AND definition_hash = BINARY %s "
                "ORDER BY measured_to, effectiveness_gid",
                (int(capability_version_gid), definition_hash),
            )
            return tuple(
                RuleEffectivenessRecord(
                    effectiveness_gid=int(_row_value(row, "effectiveness_gid", 0)),
                    capability_version_gid=int(_row_value(row, "capability_version_gid", 1)),
                    definition_hash=_text_value(_row_value(row, "definition_hash", 2)),
                    metric_name=str(_row_value(row, "metric_name", 3)),
                    metric_value=int(_row_value(row, "metric_value", 4)),
                    evidence=_json_load(_row_value(row, "evidence_json", 5)),
                    measured_from=_row_value(row, "measured_from", 6),
                    measured_to=_row_value(row, "measured_to", 7),
                )
                for row in cursor.fetchall()
            )
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

    def _resolve_projection(self, cursor: Any, capability: ScannedCapability, snapshot_gid: int) -> CapabilityProjection:
        capability_gid = self._resolve_logical_gid(cursor, capability)
        capability_version_gid = self._resolve_major_gid(cursor, capability_gid, capability, snapshot_gid)
        return _projection(capability, capability_gid, capability_version_gid)

    def _resolve_logical_gid(self, cursor: Any, capability: ScannedCapability) -> int:
        row = self._select_logical(cursor, capability.capability_id)
        if row is not None:
            return self._verify_logical(row, capability)
        candidate = self._next_ids()
        try:
            cursor.execute(
                "INSERT INTO workmanship_base_capability_entries "
                "(capability_gid, capability_id, owner_domain, current_major_version, current_lifecycle_status, first_seen_at, last_seen_at, row_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (candidate, capability.capability_id, capability.owner_domain, capability.major_version,
                 capability.lifecycle_status, _now(), _now(), 1),
            )
            return candidate
        except Exception as exc:
            if not _duplicate_key(exc):
                raise
            recovered = self._select_logical(cursor, capability.capability_id)
            if recovered is None:
                raise ImmutableRecordError("identity_conflict: logical capability was not recoverable") from exc
            return self._verify_logical(recovered, capability)

    def _resolve_major_gid(self, cursor: Any, capability_gid: int, capability: ScannedCapability, first_seen_snapshot_gid: int) -> int:
        row = self._select_major(cursor, capability_gid, capability.major_version)
        if row is not None:
            return self._verify_major(row, capability_gid, capability.major_version)
        candidate = self._next_ids()
        try:
            cursor.execute(
                "INSERT INTO workmanship_base_capability_versions "
                "(capability_version_gid, capability_gid, major_version, semantic_class, business_effect, lifecycle_status, first_seen_snapshot_gid, latest_snapshot_gid, retired_at, row_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (candidate, capability_gid, capability.major_version, capability.semantic_class,
                 capability.business_effect, capability.lifecycle_status, first_seen_snapshot_gid, None, None, 1),
            )
            return candidate
        except Exception as exc:
            if not _duplicate_key(exc):
                raise
            recovered = self._select_major(cursor, capability_gid, capability.major_version)
            if recovered is None:
                raise ImmutableRecordError("identity_conflict: major capability was not recoverable") from exc
            return self._verify_major(recovered, capability_gid, capability.major_version)

    @staticmethod
    def _select_logical(cursor: Any, capability_id: str) -> Any:
        cursor.execute(
            "SELECT capability_gid, capability_id, owner_domain FROM workmanship_base_capability_entries WHERE capability_id = %s",
            (capability_id,),
        )
        return cursor.fetchone()

    @staticmethod
    def _select_snapshot(cursor: Any, snapshot_hash: str) -> Any:
        cursor.execute(
            "SELECT snapshot_gid, scan_run_gid, snapshot_hash, code_revision, catalog_release_id, catalog_hash, descriptor_count "
            "FROM workmanship_base_capability_snapshots WHERE snapshot_hash = %s",
            (snapshot_hash,),
        )
        return cursor.fetchone()

    def _load_existing_snapshot(self, cursor: Any, row: Any, document: SnapshotDocument) -> SnapshotRecord:
        snapshot_gid = int(_row_value(row, "snapshot_gid", 0))
        scan_run_gid = int(_row_value(row, "scan_run_gid", 1))
        if (_row_value(row, "snapshot_hash", 2) != document.snapshot_hash
                or _row_value(row, "code_revision", 3) != document.code_revision
                or _row_value(row, "catalog_release_id", 4) != document.product_release_id
                or _row_value(row, "catalog_hash", 5) != document.catalog_hash
                or int(_row_value(row, "descriptor_count", 6)) != len(document.capabilities)):
            raise ImmutableRecordError("snapshot_hash_conflict")
        cursor.execute(
            "SELECT snapshot_entry_gid, capability_entry.capability_gid, "
            "snapshot_entry.capability_version_gid, capability_entry.capability_id, "
            "capability_version.major_version, capability_entry.owner_domain, "
            "capability_version.semantic_class, capability_version.business_effect, "
            "capability_version.lifecycle_status, snapshot_entry.descriptor_hash "
            "FROM workmanship_base_capability_snapshot_entries AS snapshot_entry "
            "JOIN workmanship_base_capability_versions AS capability_version "
            "ON capability_version.capability_version_gid = snapshot_entry.capability_version_gid "
            "JOIN workmanship_base_capability_entries AS capability_entry "
            "ON capability_entry.capability_gid = capability_version.capability_gid "
            "WHERE snapshot_entry.snapshot_gid = %s",
            (snapshot_gid,),
        )
        entries = tuple(self._entry_from_row(item) for item in cursor.fetchall())
        expected = {(item.capability_id, item.major_version, item.descriptor_hash) for item in document.capabilities}
        actual = {(item.capability_id, item.major_version, item.descriptor_hash) for item in entries}
        if actual != expected:
            raise ImmutableRecordError("snapshot_hash_conflict")
        cursor.execute(
            "SELECT implementation_node_gid, canonical_key FROM workmanship_base_capability_implementation_nodes WHERE snapshot_gid = %s",
            (snapshot_gid,),
        )
        node_gids = {str(_row_value(item, "canonical_key", 1)): int(_row_value(item, "implementation_node_gid", 0)) for item in cursor.fetchall()}
        cursor.execute(
            "SELECT binding_gid FROM workmanship_base_capability_bindings WHERE snapshot_gid = %s",
            (snapshot_gid,),
        )
        binding_gids = tuple(int(_row_value(item, "binding_gid", 0)) for item in cursor.fetchall())
        cursor.execute(
            "SELECT relation_gid FROM workmanship_base_capability_implementation_relations WHERE snapshot_gid = %s",
            (snapshot_gid,),
        )
        relation_gids = tuple(int(_row_value(item, "relation_gid", 0)) for item in cursor.fetchall())
        return SnapshotRecord(snapshot_gid, scan_run_gid, document, entries, node_gids, binding_gids, relation_gids)

    @staticmethod
    def _entry_from_row(row: Any) -> SnapshotEntry:
        return SnapshotEntry(
            snapshot_entry_gid=int(_row_value(row, "snapshot_entry_gid", 0)),
            capability_gid=int(_row_value(row, "capability_gid", 1)),
            capability_version_gid=int(_row_value(row, "capability_version_gid", 2)),
            capability_id=str(_row_value(row, "capability_id", 3)),
            major_version=int(_row_value(row, "major_version", 4)),
            owner_domain=str(_row_value(row, "owner_domain", 5)),
            semantic_class=str(_row_value(row, "semantic_class", 6)),
            business_effect=str(_row_value(row, "business_effect", 7)),
            lifecycle_status=str(_row_value(row, "lifecycle_status", 8)),
            descriptor_hash=str(_row_value(row, "descriptor_hash", 9)),
        )

    @staticmethod
    def _select_major(cursor: Any, capability_gid: int, major_version: int) -> Any:
        cursor.execute(
            "SELECT capability_version_gid, capability_gid, major_version FROM workmanship_base_capability_versions "
            "WHERE capability_gid = %s AND major_version = %s",
            (capability_gid, major_version),
        )
        return cursor.fetchone()

    @staticmethod
    def _verify_logical(row: Any, capability: ScannedCapability) -> int:
        if _row_value(row, "capability_id", 1) != capability.capability_id:
            raise ImmutableRecordError("identity_conflict: logical capability mismatch")
        owner_domain = row.get("owner_domain") if isinstance(row, Mapping) else _row_value(row, "owner_domain", 2)
        if owner_domain not in {None, capability.owner_domain}:
            raise ImmutableRecordError("identity_conflict: logical owner mismatch")
        return int(_row_value(row, "capability_gid", 0))

    @staticmethod
    def _verify_major(row: Any, capability_gid: int, major_version: int) -> int:
        if int(_row_value(row, "capability_gid", 1)) != capability_gid or int(_row_value(row, "major_version", 2)) != major_version:
            raise ImmutableRecordError("identity_conflict: major capability mismatch")
        return int(_row_value(row, "capability_version_gid", 0))

    @staticmethod
    def _ensure_no_duplicate_majors(projections: tuple[CapabilityProjection, ...]) -> None:
        keys = {(item.capability_id, item.major_version) for item in projections}
        if len(keys) != len(projections):
            raise ImmutableRecordError("duplicate_capability_major_in_snapshot")

    @staticmethod
    def _insert_scan_run(cursor: Any, scan_run_gid: int, document: SnapshotDocument, created_at: datetime) -> None:
        cursor.execute(
            "INSERT INTO workmanship_base_capability_scan_runs "
            "(scan_run_gid, environment_key, trigger_type, code_revision, catalog_release_id, requested_by_gid, idempotency_key, status, started_at, finished_at, error_summary) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (scan_run_gid, "test-governance", "import", document.code_revision, document.product_release_id,
             0, document.snapshot_hash, document.scan_status, created_at, created_at,
             "; ".join(finding.message for finding in document.scan_findings)[:1000] or None),
        )

    def _insert_scan_findings(self, cursor: Any, snapshot_gid: int, document: SnapshotDocument) -> None:
        for finding in document.scan_findings:
            fingerprint = _scan_finding_fingerprint(finding)
            cursor.execute(
                "INSERT INTO workmanship_base_capability_findings "
                "(finding_gid, analysis_run_gid, snapshot_gid, finding_type, severity, status, source_type, "
                "confidence, finding_fingerprint, title, summary, recommendation, confirmed_by_gid, confirmed_at, row_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (self._next_ids(), None, snapshot_gid, finding.code, finding.severity, "open", "scanner",
                 1, fingerprint, finding.category, finding.message, finding.source_path, None, None, 1),
            )

    @staticmethod
    def _insert_snapshot(cursor: Any, snapshot_gid: int, scan_run_gid: int, document: SnapshotDocument, created_at: datetime) -> None:
        cursor.execute(
            "INSERT INTO workmanship_base_capability_snapshots "
            "(snapshot_gid, scan_run_gid, snapshot_hash, code_revision, catalog_release_id, catalog_hash, descriptor_count, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (snapshot_gid, scan_run_gid, document.snapshot_hash, document.code_revision,
             document.product_release_id, document.catalog_hash, len(document.capabilities), created_at),
        )

    def _insert_snapshot_entries(self, cursor: Any, snapshot_gid: int, projections: tuple[CapabilityProjection, ...], document: SnapshotDocument, created_at: datetime) -> tuple[SnapshotEntry, ...]:
        entries: list[SnapshotEntry] = []
        for projection, capability in zip(projections, document.capabilities, strict=True):
            snapshot_entry_gid = self._next_ids()
            cursor.execute(
                "INSERT INTO workmanship_base_capability_snapshot_entries "
                "(snapshot_entry_gid, snapshot_gid, capability_version_gid, descriptor_hash, input_schema_hash, output_schema_hash, error_schema_hash, policy_hash, provider_hash, descriptor_json, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (snapshot_entry_gid, snapshot_gid, projection.capability_version_gid, capability.descriptor_hash,
                 capability.input_schema_hash, capability.output_schema_hash, capability.error_schema_hash,
                 capability.policy_hash, capability.provider_hash, _json(capability.to_json()), created_at),
            )
            entries.append(SnapshotEntry(**projection.__dict__, snapshot_entry_gid=snapshot_entry_gid))
        return tuple(entries)

    def _insert_nodes(self, cursor: Any, snapshot_gid: int, document: SnapshotDocument, created_at: datetime) -> dict[str, int]:
        nodes: dict[str, int] = {}
        for node in document.nodes:
            if node.canonical_key in nodes:
                raise ImmutableRecordError("duplicate_implementation_node_in_snapshot")
            node_gid = self._next_ids()
            cursor.execute(
                "INSERT INTO workmanship_base_capability_implementation_nodes "
                "(implementation_node_gid, snapshot_gid, owner_domain, node_type, canonical_key, source_path, source_symbol, http_method, route_path, artifact_hash, metadata_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (node_gid, snapshot_gid, node.owner_domain, node.node_type, node.canonical_key, node.source_path,
                 node.source_symbol, node.http_method, node.route_path, node.artifact_hash, _json(node.to_json()["metadata"])),
            )
            nodes[node.canonical_key] = node_gid
        return nodes

    def _insert_bindings(self, cursor: Any, snapshot_gid: int, projections: tuple[CapabilityProjection, ...], node_gids: Mapping[str, int], document: SnapshotDocument) -> tuple[int, ...]:
        versions = {(item.capability_id, item.major_version): item.capability_version_gid for item in projections}
        result: list[int] = []
        for binding in document.bindings:
            version_gid = versions.get((binding.capability_id, binding.major_version))
            node_gid = node_gids.get(binding.node_canonical_key)
            if version_gid is None or node_gid is None:
                raise ImmutableRecordError("binding_references_unknown_snapshot_entity")
            binding_gid = self._next_ids()
            cursor.execute(
                "INSERT INTO workmanship_base_capability_bindings "
                "(binding_gid, snapshot_gid, capability_version_gid, implementation_node_gid, binding_type, binding_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (binding_gid, snapshot_gid, version_gid, node_gid, binding.binding_type, binding.binding_hash),
            )
            result.append(binding_gid)
        return tuple(result)

    def _insert_relations(self, cursor: Any, snapshot_gid: int, node_gids: Mapping[str, int], document: SnapshotDocument) -> tuple[int, ...]:
        result: list[int] = []
        for relation in document.relations:
            from_gid = node_gids.get(relation.from_canonical_key)
            to_gid = node_gids.get(relation.to_canonical_key)
            if from_gid is None or to_gid is None:
                raise ImmutableRecordError("relation_references_unknown_snapshot_node")
            relation_gid = self._next_ids()
            cursor.execute(
                "INSERT INTO workmanship_base_capability_implementation_relations "
                "(relation_gid, snapshot_gid, from_node_gid, to_node_gid, relation_type, relation_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (relation_gid, snapshot_gid, from_gid, to_gid, relation.relation_type, relation.relation_hash),
            )
            result.append(relation_gid)
        return tuple(result)

    @staticmethod
    def _update_mutable_projections(cursor: Any, snapshot_gid: int, projections: tuple[CapabilityProjection, ...], seen_at: datetime) -> None:
        for projection in projections:
            cursor.execute(
                "UPDATE workmanship_base_capability_entries SET current_lifecycle_status = %s, last_seen_at = %s, row_version = row_version + 1 WHERE capability_gid = %s",
                (projection.lifecycle_status, seen_at, projection.capability_gid),
            )
            cursor.execute(
                "UPDATE workmanship_base_capability_versions SET latest_snapshot_gid = %s, lifecycle_status = %s, row_version = row_version + 1 WHERE capability_version_gid = %s",
                (snapshot_gid, projection.lifecycle_status, projection.capability_version_gid),
            )


def _projection(capability: ScannedCapability, capability_gid: int, capability_version_gid: int) -> CapabilityProjection:
    return CapabilityProjection(
        capability_gid=capability_gid, capability_version_gid=capability_version_gid,
        capability_id=capability.capability_id, major_version=capability.major_version,
        owner_domain=capability.owner_domain, semantic_class=capability.semantic_class,
        business_effect=capability.business_effect, lifecycle_status=capability.lifecycle_status,
        descriptor_hash=capability.descriptor_hash,
    )


def _json(value: Any) -> str:
    from .fingerprint import canonical_json
    return canonical_json(value)


__all__ = ["GovernanceStore", "GovernanceWorkflowPort", "MemoryGovernanceStore", "SqlGovernanceStore"]
