"""Repair prompts with redacted persistence records and explicit read authorization."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .ai_advisory import AdvisoryFinding, validate_advisory
from .redaction import redact


class PromptAuthorizationError(PermissionError):
    """Raised if a caller tries to read repair text without authorization."""


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _summary(value: Any) -> str:
    rendered = _stable_json(redact(value))
    return rendered[:4000]


@dataclass(frozen=True)
class RedactedPrompt:
    prompt_hash: str
    redacted_summary: str
    _prompt_text: str = field(repr=False, compare=False)

    def text_for(self, *, authorized: bool) -> str:
        if authorized is not True:
            raise PromptAuthorizationError("prompt_access_denied")
        return self._prompt_text

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
    """Build a constrained repair request from only redacted, reviewable context."""
    safe_finding = _finding(finding)
    safe_evidence = redact(evidence)
    safe_boundary = redact(boundary)
    snapshot_identity = safe_boundary.get("snapshot_identity", safe_boundary.get("snapshot_gid", "not supplied"))
    capability_identities = safe_boundary.get("capability_identities", safe_finding.subject_version_gids)
    observed_contract = safe_boundary.get("observed_contract", "review the supplied evidence only")
    required_tests = safe_boundary.get("required_tests", ())
    acceptance = safe_boundary.get("acceptance_criteria", "preserve candidate-only governance controls")
    text = "\n\n".join((
        f"Snapshot identity\n{_summary(snapshot_identity)}",
        f"Capability identities\n{_summary(capability_identities)}",
        f"Observed contract\n{_summary(observed_contract)}",
        f"Implementation evidence\n{_summary(safe_evidence)}",
        f"Finding\n{_summary(safe_finding.model_dump())}",
        f"Allowed change boundary\n{_summary(safe_boundary.get('allowed', ()))}",
        f"Forbidden changes\n{_summary(safe_boundary.get('forbidden', ()))}",
        f"Required tests\n{_summary(required_tests)}",
        f"Acceptance criteria\n{_summary(acceptance)}",
    ))
    prompt_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    return RedactedPrompt(prompt_hash=prompt_hash, redacted_summary=_summary({
        "finding": safe_finding.model_dump(), "evidence": safe_evidence, "boundary": safe_boundary,
    }), _prompt_text=text)


__all__ = ["PromptAuthorizationError", "RedactedPrompt", "build_repair_prompt"]
