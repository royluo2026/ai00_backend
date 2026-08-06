from __future__ import annotations

from dataclasses import dataclass, replace

POLICY_KINDS = frozenset({"draft_check", "publish_check", "simulation_check", "workstation_check"})
SEVERITIES = frozenset({"block", "warning", "hint"})
REPLAY_EVIDENCE = frozenset({"positive", "negative", "boundary", "historical_replay"})


class PolicyGovernanceError(ValueError): pass


@dataclass(frozen=True)
class PolicyCheck:
    check_id: str
    severity: str
    source_ref: str
    owner: str
    scope: str
    mechanism: str
    version: str
    verified: bool
    source_kind: str = "standard"
    threshold: str = ""
    algorithm: str = ""


@dataclass(frozen=True)
class ValidationPolicy:
    kind: str
    version: str
    checks: tuple[PolicyCheck, ...]
    test_evidence: tuple[str, ...] = ()


def normalize_check(check: PolicyCheck) -> PolicyCheck:
    if check.source_kind == "experience" and not check.verified and check.severity != "hint":
        return replace(check, severity="hint")
    return check


def publish_policy(policy: ValidationPolicy) -> ValidationPolicy:
    if policy.kind not in POLICY_KINDS or not policy.version or not policy.checks:
        raise PolicyGovernanceError("valid policy kind, version and checks are required")
    normalized = tuple(normalize_check(check) for check in policy.checks)
    errors = []
    required = ("source_ref", "owner", "scope", "severity", "mechanism", "version", "threshold", "algorithm")
    for check in normalized:
        missing = [field for field in required if not str(getattr(check, field, "") or "").strip()]
        if check.severity not in SEVERITIES: missing.append("valid severity")
        if check.severity == "block" and not check.verified: missing.append("verified")
        if missing: errors.append(f"{check.check_id}: " + ", ".join(missing))
    if policy.kind == "publish_check":
        missing_evidence = sorted(REPLAY_EVIDENCE - set(policy.test_evidence))
        if missing_evidence: errors.append("test_evidence: " + ", ".join(missing_evidence))
    if errors: raise PolicyGovernanceError("; ".join(errors))
    return replace(policy, checks=normalized)
