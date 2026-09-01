"""Fail-closed release reports pinned to immutable governance inputs."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

from backend.plugin_platform.signing import sign
from backend.capability_v2.release_gate import (
    BusinessGateResult,
    BusinessGovernanceConfigurationError,
    build_business_catalog_projection,
    parse_business_governance_result,
)

from .audit import AuditSink


class ReleaseGateError(RuntimeError):
    """Raised when a release-gate write request is incomplete or invalid."""


@dataclass(frozen=True)
class ReleaseCandidate:
    code_revision: str
    product_catalog_release_id: str
    snapshot_gid: int
    test_run_gid: int


@dataclass(frozen=True)
class ReleaseReport:
    release_report_gid: int
    candidate: ReleaseCandidate
    conclusion: Literal["pass", "fail", "expired"]
    blockers: tuple[str, ...]
    business_governance: dict[str, Any]
    report_hash: str
    signing_key_id: str
    signature: str

    def to_document(self) -> dict[str, Any]:
        """Return the portable, signed release-attestation document."""
        return {
            "report_gid": str(self.release_report_gid),
            "code_revision": self.candidate.code_revision,
            "product_catalog_release_id": self.candidate.product_catalog_release_id,
            "snapshot_gid": str(self.candidate.snapshot_gid),
            "test_run_gid": str(self.candidate.test_run_gid),
            "conclusion": self.conclusion,
            "blockers": list(self.blockers),
            "business_governance": self.business_governance,
            "report_hash": self.report_hash,
            "signing_key_id": self.signing_key_id,
            "signature": self.signature,
        }


def _canonical(
    candidate: ReleaseCandidate,
    report_gid: int,
    conclusion: str,
    blockers: Iterable[str],
    business_governance: Mapping[str, Any],
    signing_key_id: str,
) -> bytes:
    payload = {
        "report_gid": str(report_gid),
        "code_revision": candidate.code_revision,
        "product_catalog_release_id": candidate.product_catalog_release_id,
        "snapshot_gid": str(candidate.snapshot_gid),
        "test_run_gid": str(candidate.test_run_gid),
        "conclusion": conclusion,
        "blockers": sorted(set(str(value) for value in blockers)),
        "business_governance": business_governance,
        "signing_key_id": signing_key_id,
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _default_signer(payload: bytes) -> str:
    secret_path = os.environ.get("AI00_GOVERNANCE_RELEASE_SIGNING_KEY_PATH", "").strip()
    if not secret_path:
        raise RuntimeError("release_signing_key_unavailable")
    path = Path(secret_path)
    if not path.is_file():
        raise RuntimeError("release_signing_key_unavailable")
    return sign(path.read_text(encoding="utf-8"), payload)


def _blocking_codes(findings: Iterable[Any]) -> tuple[str, ...]:
    codes: set[str] = set()
    for finding in findings:
        severity = finding.get("severity", "") if isinstance(finding, Mapping) else getattr(finding, "severity", "")
        if str(severity).lower() in {"blocking", "critical"}:
            code = finding.get("code", "blocking_finding") if isinstance(finding, Mapping) else getattr(finding, "code", "blocking_finding")
            codes.add(str(code))
    return tuple(sorted(codes))


def _business_governance_document(
    value: object,
    *,
    candidate: ReleaseCandidate,
    expected_catalog: Mapping[str, object] | None,
    legacy_baseline: Mapping[str, str] | None,
    business_review_lookup: Mapping[tuple[str, str], object] | Callable[[str, str], object] | None,
) -> dict[str, Any]:
    try:
        if expected_catalog is None or legacy_baseline is None or business_review_lookup is None:
            return {}
        projection = build_business_catalog_projection(
            expected_catalog, legacy_baseline=legacy_baseline,
        )
        if candidate.product_catalog_release_id != projection.catalog_release_id:
            return {}
        return parse_business_governance_result(
            value,
            expected_catalog=expected_catalog,
            legacy_baseline=legacy_baseline,
            business_review_lookup=business_review_lookup,
        ).serialized()
    except BusinessGovernanceConfigurationError:
        return {}


class ReleaseGate:
    def __init__(self, *, next_gid: Callable[[], int], signer: Callable[[bytes], str] | None = None, signing_key_id: str | None = None, audit_sink: AuditSink | None = None) -> None:
        self._next_gid = next_gid
        self._signer = signer or _default_signer
        self._signing_key_id = signing_key_id or os.environ.get("AI00_GOVERNANCE_RELEASE_SIGNING_KEY_ID", "")
        self._audit_sink = audit_sink
        self._reports: dict[int, ReleaseReport] = {}
        self._idempotency: dict[str, ReleaseReport] = {}
        self._expiry_reports: dict[int, int] = {}

    def get(self, release_report_gid: int) -> ReleaseReport:
        return self._reports[release_report_gid]

    def resolve(self, release_report_gid: int) -> ReleaseReport:
        """Return the current immutable validity evidence for a report reference."""
        report = self.get(release_report_gid)
        expiry_gid = self._expiry_reports.get(report.release_report_gid)
        return self._reports[expiry_gid] if expiry_gid is not None else report

    def _store(self, report: ReleaseReport, idempotency_key: str | None) -> ReleaseReport:
        self._reports[report.release_report_gid] = report
        if idempotency_key:
            self._idempotency[idempotency_key] = report
        return report

    def _expired_report(self, report: ReleaseReport) -> ReleaseReport:
        """Append a separately signed expiry report without touching prior evidence."""
        report_gid = self._next_gid()
        canonical = _canonical(
            report.candidate,
            report_gid,
            "expired",
            report.blockers,
            report.business_governance,
            report.signing_key_id,
        )
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        try:
            signature = self._signer(canonical)
        except Exception:
            signature = ""
        return ReleaseReport(
            report_gid,
            report.candidate,
            "expired",
            report.blockers,
            report.business_governance,
            digest,
            report.signing_key_id,
            signature,
        )

    def _append_expiry(self, report: ReleaseReport) -> int:
        if report.release_report_gid in self._expiry_reports:
            return self._expiry_reports[report.release_report_gid]
        expiry = self._expired_report(report)
        self._reports[expiry.release_report_gid] = expiry
        self._expiry_reports[report.release_report_gid] = expiry.release_report_gid
        if self._audit_sink is not None:
            self._audit_sink.append(
                operation="release_report_expired", entity_gid=expiry.release_report_gid,
                actor_gid="release_gate", request_gid=f"expire:{report.release_report_gid}",
                detail={"supersedes_release_report_gid": report.release_report_gid, "conclusion": "expired"},
                idempotency_key=f"release_report_expired:{report.release_report_gid}:{expiry.release_report_gid}",
            )
        return expiry.release_report_gid

    def _expire_prior_passes(
        self,
        candidate: ReleaseCandidate,
        business_governance: Mapping[str, Any],
    ) -> tuple[int, ...]:
        expired: list[int] = []
        for gid, report in tuple(self._reports.items()):
            if report.conclusion == "pass" and (
                report.candidate != candidate
                or report.business_governance != business_governance
            ):
                expired.append(self._append_expiry(report))
        return tuple(expired)

    def expire_changed_inputs(self, **candidate_inputs: Any) -> tuple[int, ...]:
        expired: list[int] = []
        for gid, report in tuple(self._reports.items()):
            if report.conclusion != "pass":
                continue
            if any(getattr(report.candidate, field) != value for field, value in candidate_inputs.items()):
                expired.append(self._append_expiry(report))
        return tuple(expired)

    @staticmethod
    def _waiver_value(waiver: Any, name: str, default: Any = None) -> Any:
        return waiver.get(name, default) if isinstance(waiver, Mapping) else getattr(waiver, name, default)

    def _waiver_blocker(self, waiver: Any, *, candidate: ReleaseCandidate, evidence_hash: str, now: datetime) -> str | None:
        status = str(self._waiver_value(waiver, "status", "")).lower()
        if status in {"stale", "revoked"}:
            return "stale_waiver"
        if status == "expired":
            return "expired_waiver"
        if status != "active":
            return "invalid_waiver"
        starts_at, expires_at = self._waiver_value(waiver, "starts_at"), self._waiver_value(waiver, "expires_at")
        if not isinstance(starts_at, datetime) or not isinstance(expires_at, datetime):
            return "invalid_waiver"
        starts_at = starts_at.replace(tzinfo=timezone.utc) if starts_at.tzinfo is None else starts_at.astimezone(timezone.utc)
        expires_at = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at.astimezone(timezone.utc)
        if now >= expires_at:
            return "expired_waiver"
        if now < starts_at:
            return "invalid_waiver"
        if self._waiver_value(waiver, "code_hash") != candidate.code_revision or self._waiver_value(waiver, "catalog_hash") != candidate.product_catalog_release_id or self._waiver_value(waiver, "evidence_hash") != evidence_hash:
            return "stale_waiver"
        return None

    def _audit(self, report: ReleaseReport, *, idempotency_key: str, actor_gid: str) -> None:
        if self._audit_sink is not None:
            self._audit_sink.append(operation="gate", entity_gid=report.release_report_gid, actor_gid=actor_gid, request_gid=idempotency_key, detail={"conclusion": report.conclusion, "blockers": report.blockers}, idempotency_key=f"gate:{idempotency_key}")

    def evaluate(self, candidate: ReleaseCandidate, *, available: bool = True, test_status: str | None = None, findings: Iterable[Any] = (), stale_evidence: bool = False, waivers: Iterable[Any] = (), approvals_complete: bool = False, data_complete: bool = False, evidence_hash: str = "", business_governance: BusinessGateResult | Mapping[str, Any] | None = None, business_catalog: Mapping[str, object] | None = None, legacy_baseline: Mapping[str, str] | None = None, business_review_lookup: Mapping[tuple[str, str], object] | Callable[[str, str], object] | None = None, now: datetime | None = None, idempotency_key: str | None = None, evaluated_by_gid: str = "release_gate", **unknown: Any) -> ReleaseReport:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ReleaseGateError("idempotency_key_required")
        if key in self._idempotency:
            return self._idempotency[key]
        governance_document = _business_governance_document(
            business_governance,
            candidate=candidate,
            expected_catalog=business_catalog,
            legacy_baseline=legacy_baseline,
            business_review_lookup=business_review_lookup,
        )
        self._expire_prior_passes(
            candidate, governance_document,
        )
        blockers: set[str] = set()
        if not available:
            blockers.add("governance_dependency_unavailable")
        if test_status == "unavailable":
            blockers.add("required_test_unavailable")
        elif test_status != "passed":
            blockers.add("required_test_not_passed")
        blockers.update(_blocking_codes(findings))
        if stale_evidence:
            blockers.add("stale_evidence")
        moment = now or datetime.now(timezone.utc)
        moment = moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)
        for waiver in waivers:
            blocker = self._waiver_blocker(waiver, candidate=candidate, evidence_hash=str(evidence_hash), now=moment)
            if blocker:
                blockers.add(blocker)
        if not approvals_complete:
            blockers.add("incomplete_approvals")
        if not data_complete:
            blockers.add("missing_required_data")
        if not governance_document:
            blockers.add("business_governance_missing")
        elif governance_document["status"] == "blocked":
            blockers.add("business_governance_blocked")
        if unknown:
            blockers.add("missing_required_data")
        conclusion: Literal["pass", "fail", "expired"] = "fail" if blockers else "pass"
        report_gid = self._next_gid()
        key_id = self._signing_key_id
        if not key_id:
            key_id = "configured-release-key"
        canonical = _canonical(
            candidate, report_gid, conclusion, blockers,
            governance_document, key_id,
        )
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        signature = ""
        try:
            signature = self._signer(canonical)
        except Exception:
            blockers.add("release_signing_key_unavailable")
            conclusion = "fail"
            canonical = _canonical(
                candidate, report_gid, conclusion, blockers,
                governance_document, key_id,
            )
            digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        report = ReleaseReport(
            report_gid, candidate, conclusion, tuple(sorted(blockers)),
            governance_document,
            digest, key_id, signature,
        )
        report = self._store(report, key)
        self._audit(report, idempotency_key=key, actor_gid=str(evaluated_by_gid))
        return report


__all__ = ["ReleaseCandidate", "ReleaseGate", "ReleaseGateError", "ReleaseReport"]
