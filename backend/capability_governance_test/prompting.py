"""Repair prompts with allow-listed persistence records and service-side authorization."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .ai_advisory import AdvisoryFinding, validate_advisory
from .redaction import sanitize_evidence, sanitize_repair_boundary


class PromptAuthorizationError(PermissionError):
    """Raised if a caller tries to read repair text without authorization."""


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _summary(value: Any) -> str:
    return _stable_json(value)[:4000]


@dataclass(frozen=True)
class RedactedPrompt:
    prompt_hash: str
    redacted_summary: str

    def store_record(self) -> dict[str, str]:
        """The only persistence representation; it deliberately omits prompt text."""
        return {"prompt_hash": self.prompt_hash, "redacted_summary": self.redacted_summary}


def _finding(value: AdvisoryFinding | Mapping[str, Any]) -> AdvisoryFinding:
    if isinstance(value, AdvisoryFinding):
        return value
    return validate_advisory({"findings": [value]}).findings[0]


def build_repair_prompt(
    finding: AdvisoryFinding | Mapping[str, Any],
    evidence: Mapping[str, Any],
    boundary: Mapping[str, Any],
) -> RedactedPrompt:
    """Return only prompt metadata; text is never held by this public value object."""
    return _render_repair_prompt(finding, evidence, boundary)[0]


def _render_repair_prompt(
    finding: AdvisoryFinding | Mapping[str, Any],
    evidence: Mapping[str, Any],
    boundary: Mapping[str, Any],
) -> tuple[RedactedPrompt, str]:
    """Build all nine sections from only fixed, reviewable governance metadata."""
    safe_finding = _finding(finding)
    safe_evidence = sanitize_evidence(evidence)
    safe_boundary = sanitize_repair_boundary(boundary)
    snapshot_identity = {key: safe_boundary[key] for key in ("snapshot_gid", "snapshot_hash") if key in safe_boundary}
    capability_identities = {
        "capability_ids": safe_boundary.get("capability_ids", ()),
        "capability_version_gids": safe_boundary.get("capability_version_gids", safe_finding.subject_version_gids),
    }
    finding_summary = {
        "finding_type": safe_finding.finding_type,
        "subject_version_gids": safe_finding.subject_version_gids,
        "confidence": safe_finding.confidence,
        "evidence_keys": safe_finding.evidence_keys,
        "status": safe_finding.status,
    }
    text = "\n\n".join((
        f"Snapshot identity\n{_summary(snapshot_identity)}",
        f"Capability identities\n{_summary(capability_identities)}",
        f"Observed contract\n{_summary(safe_boundary.get('observed_contract_hashes', {}))}",
        f"Implementation evidence\n{_summary(safe_evidence)}",
        f"Finding\n{_summary(finding_summary)}",
        f"Allowed change boundary\n{_summary(safe_boundary.get('allowed_change_ids', ()))}",
        f"Forbidden changes\n{_summary(safe_boundary.get('forbidden_change_ids', ()))}",
        f"Required tests\n{_summary(safe_boundary.get('required_test_ids', ()))}",
        f"Acceptance criteria\n{_summary(safe_boundary.get('acceptance_criteria_ids', ()))}",
    ))
    prompt_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    return RedactedPrompt(prompt_hash=prompt_hash, redacted_summary=_summary({
        "finding": finding_summary, "evidence": safe_evidence, "boundary": safe_boundary,
    })), text


__all__ = ["PromptAuthorizationError", "RedactedPrompt", "build_repair_prompt"]
