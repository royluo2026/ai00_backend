"""Fail-closed release reports pinned to immutable governance inputs."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

from backend.plugin_platform.signing import sign


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
    report_hash: str
    signing_key_id: str
    signature: str


def _canonical(candidate: ReleaseCandidate, conclusion: str, blockers: Iterable[str]) -> bytes:
    payload = {"candidate": {"code_revision": candidate.code_revision, "product_catalog_release_id": candidate.product_catalog_release_id, "snapshot_gid": candidate.snapshot_gid, "test_run_gid": candidate.test_run_gid}, "conclusion": conclusion, "blockers": sorted(set(str(value) for value in blockers))}
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


class ReleaseGate:
    def __init__(self, *, next_gid: Callable[[], int], signer: Callable[[bytes], str] | None = None, signing_key_id: str | None = None) -> None:
        self._next_gid = next_gid
        self._signer = signer or _default_signer
        self._signing_key_id = signing_key_id or os.environ.get("AI00_GOVERNANCE_RELEASE_SIGNING_KEY_ID", "")
        self._reports: dict[int, ReleaseReport] = {}
        self._idempotency: dict[str, ReleaseReport] = {}

    def get(self, release_report_gid: int) -> ReleaseReport:
        return self._reports[release_report_gid]

    def _store(self, report: ReleaseReport, idempotency_key: str | None) -> ReleaseReport:
        self._reports[report.release_report_gid] = report
        if idempotency_key:
            self._idempotency[idempotency_key] = report
        return report

    def _expired_report(self, report: ReleaseReport) -> ReleaseReport:
        """Re-sign the immutable report payload for its new expired conclusion."""
        canonical = _canonical(report.candidate, "expired", report.blockers)
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        try:
            signature = self._signer(canonical)
        except Exception:
            signature = ""
        return replace(report, conclusion="expired", report_hash=digest, signature=signature)

    def _expire_prior_passes(self, candidate: ReleaseCandidate) -> tuple[int, ...]:
        expired: list[int] = []
        for gid, report in tuple(self._reports.items()):
            if report.conclusion == "pass" and report.candidate != candidate:
                self._reports[gid] = self._expired_report(report)
                expired.append(gid)
        return tuple(expired)

    def expire_changed_inputs(self, **candidate_inputs: Any) -> tuple[int, ...]:
        expired: list[int] = []
        for gid, report in tuple(self._reports.items()):
            if report.conclusion != "pass":
                continue
            if any(getattr(report.candidate, field) != value for field, value in candidate_inputs.items()):
                self._reports[gid] = self._expired_report(report)
                expired.append(gid)
        return tuple(expired)

    def evaluate(self, candidate: ReleaseCandidate, *, available: bool = True, test_status: str | None = None, findings: Iterable[Any] = (), stale_evidence: bool = False, waivers: Iterable[Any] = (), approvals_complete: bool = False, data_complete: bool = False, idempotency_key: str | None = None, **unknown: Any) -> ReleaseReport:
        key = str(idempotency_key or "").strip()
        if key and key in self._idempotency:
            return self._idempotency[key]
        self._expire_prior_passes(candidate)
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
        for waiver in waivers:
            status = waiver.get("status", "") if isinstance(waiver, Mapping) else getattr(waiver, "status", "")
            if str(status).lower() == "expired":
                blockers.add("expired_waiver")
        if not approvals_complete:
            blockers.add("incomplete_approvals")
        if not data_complete:
            blockers.add("missing_required_data")
        if unknown:
            blockers.add("missing_required_data")
        conclusion: Literal["pass", "fail", "expired"] = "fail" if blockers else "pass"
        canonical = _canonical(candidate, conclusion, blockers)
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        signature = ""
        key_id = self._signing_key_id
        try:
            signature = self._signer(canonical)
            if not key_id:
                key_id = "configured-release-key"
        except Exception:
            blockers.add("release_signing_key_unavailable")
            conclusion = "fail"
            canonical = _canonical(candidate, conclusion, blockers)
            digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        report = ReleaseReport(self._next_gid(), candidate, conclusion, tuple(sorted(blockers)), digest, key_id, signature)
        return self._store(report, key or None)


__all__ = ["ReleaseCandidate", "ReleaseGate", "ReleaseReport"]
