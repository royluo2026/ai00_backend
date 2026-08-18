"""Policy-constrained runners for periodic checks and release E2E evidence."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .evidence import EvidenceRecord


class TestPolicyError(RuntimeError):
    """Raised when a governance profile's explicit security policy is violated."""

    __test__ = False


@dataclass(frozen=True)
class RegisteredTestCase:
    test_case_id: str
    operation: str
    runner: Callable[[], Mapping[str, Any] | None]
    fixture_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TestProfile:
    name: str
    allowed_operations: tuple[str, ...]
    requires_release_authorization: bool = False


@dataclass(frozen=True)
class TestRun:
    profile: TestProfile
    results: tuple[EvidenceRecord, ...]


_FAST_PROFILE = TestProfile("fast", ("read", "static"))
_RELEASE_E2E_PROFILE = TestProfile("release_e2e", ("read", "static", "write"), True)


def _result(case: RegisteredTestCase, *, level: str, force_no_skip: bool = False) -> EvidenceRecord:
    try:
        payload = dict(case.runner() or {})
        status = str(payload.pop("status", "passed")).strip().lower()
        if force_no_skip and status == "skipped":
            status = "failed"
            payload = {"reason": "release_e2e_skip_forbidden", **payload}
        return EvidenceRecord(level=level, status=status, runtime_result=payload, test_case_id=case.test_case_id,
                              fixture_ids=case.fixture_ids)
    except Exception as exc:  # Record the test failure; never re-label it as a skip.
        return EvidenceRecord(level=level, status="failed", runtime_result={"error": f"{type(exc).__name__}: {exc}"},
                              test_case_id=case.test_case_id, fixture_ids=case.fixture_ids)


def run_fast_profile(cases: Iterable[RegisteredTestCase]) -> TestRun:
    """Execute only bounded read/static checks; writes are rejected before execution."""
    materialized = tuple(cases)
    if any(case.operation not in _FAST_PROFILE.allowed_operations for case in materialized):
        raise TestPolicyError("write_probe_forbidden")
    return TestRun(_FAST_PROFILE, tuple(_result(case, level="runtime_probe") for case in materialized))


def _permissions(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        value = value.get("permissions", ())
    return {str(item) for item in (value or ())}


def _validate_release_request(
    *, release_candidate_gid: str | int | None,
    caller_permissions: Any,
    fixture_ids: Iterable[str] | None,
    cleanup_plan: Mapping[str, str] | None,
) -> tuple[str, tuple[str, ...]]:
    candidate = str(release_candidate_gid or "").strip()
    if not candidate:
        raise TestPolicyError("release_candidate_gid_required")
    if "system.capability.release" not in _permissions(caller_permissions):
        raise TestPolicyError("system.capability.release_required")
    fixtures = tuple(sorted(set(str(value) for value in (fixture_ids or ()))))
    if not fixtures or any(not value.startswith(f"E2E-{candidate}-") for value in fixtures):
        raise TestPolicyError("isolated_fixture_ids_required")
    plan = cleanup_plan or {}
    if set(plan) != set(fixtures) or any(not str(plan[fixture]).strip() or fixture not in str(plan[fixture]) for fixture in fixtures):
        raise TestPolicyError("exact_cleanup_plan_required")
    return candidate, fixtures


def _validate_release_cases(
    cases: tuple[RegisteredTestCase, ...], *, candidate: str, fixture_ids: tuple[str, ...], cleanup_plan: Mapping[str, str],
) -> None:
    planned = set(fixture_ids)
    owned_by_case: set[str] = set()
    for case in cases:
        if str(case.operation).strip().lower() not in _RELEASE_E2E_PROFILE.allowed_operations:
            raise TestPolicyError("release_operation_forbidden")
        owned = tuple(sorted(set(str(value) for value in case.fixture_ids)))
        if not owned or any(not value.startswith(f"E2E-{candidate}-") for value in owned):
            raise TestPolicyError("case_fixture_ids_required")
        if not set(owned).issubset(planned) or any(value not in cleanup_plan for value in owned):
            raise TestPolicyError("case_fixture_cleanup_mismatch")
        if owned_by_case.intersection(owned):
            raise TestPolicyError("case_fixture_ids_overlap")
        owned_by_case.update(owned)
    if owned_by_case != planned:
        raise TestPolicyError("case_fixture_coverage_mismatch")


def run_release_e2e_profile(
    cases: Iterable[RegisteredTestCase],
    *,
    release_candidate_gid: str | int | None = None,
    caller_permissions: Any = (),
    fixture_ids: Iterable[str] | None = None,
    cleanup_plan: Mapping[str, str] | None = None,
) -> TestRun:
    """Run authorized release checks, preserving each exception or skip as failure evidence."""
    materialized = tuple(cases)
    candidate, fixtures = _validate_release_request(
        release_candidate_gid=release_candidate_gid, caller_permissions=caller_permissions,
        fixture_ids=fixture_ids, cleanup_plan=cleanup_plan,
    )
    assert cleanup_plan is not None
    _validate_release_cases(materialized, candidate=candidate, fixture_ids=fixtures, cleanup_plan=cleanup_plan)
    return TestRun(_RELEASE_E2E_PROFILE, tuple(_result(case, level="runtime_e2e", force_no_skip=True) for case in materialized))


__all__ = [
    "RegisteredTestCase", "TestPolicyError", "TestProfile", "TestRun",
    "run_fast_profile", "run_release_e2e_profile",
]
