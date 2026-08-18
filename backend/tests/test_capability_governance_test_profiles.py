from __future__ import annotations

import pytest

from backend.capability_governance_test.test_runner import (
    RegisteredTestCase,
    TestPolicyError,
    run_fast_profile,
    run_release_e2e_profile,
)


def test_periodic_profile_refuses_write_cases() -> None:
    write_case = RegisteredTestCase("case-write", operation="write", runner=lambda: {"status": "passed"})

    with pytest.raises(TestPolicyError, match="write_probe_forbidden"):
        run_fast_profile([write_case])


def test_fast_profile_runs_only_read_and_static_cases() -> None:
    read_case = RegisteredTestCase("case-read", operation="read", runner=lambda: {"status": "passed", "token": "secret"})
    static_case = RegisteredTestCase("case-static", operation="static", runner=lambda: {"status": "passed"})

    result = run_fast_profile([read_case, static_case])

    assert result.profile.name == "fast"
    assert [item.status for item in result.results] == ["passed", "passed"]
    assert result.results[0].runtime_result["token"] == "<redacted>"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({}, "release_candidate_gid_required"),
        ({"release_candidate_gid": "42"}, "system.capability.release_required"),
        ({"release_candidate_gid": "42", "caller_permissions": {"system.capability.release"}}, "isolated_fixture_ids_required"),
        ({"release_candidate_gid": "42", "caller_permissions": {"system.capability.release"}, "fixture_ids": ("E2E-42-run-1",)}, "exact_cleanup_plan_required"),
    ],
)
def test_release_e2e_profile_fails_closed_without_authorization_or_cleanup(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(TestPolicyError, match=message):
        run_release_e2e_profile([], **kwargs)


def test_release_e2e_records_exceptions_and_skips_as_failures() -> None:
    failing = RegisteredTestCase("case-failing", operation="write", runner=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    skipped = RegisteredTestCase("case-skipped", operation="write", runner=lambda: {"status": "skipped"})

    result = run_release_e2e_profile(
        [failing, skipped], release_candidate_gid="42",
        caller_permissions={"system.capability.release"}, fixture_ids=("E2E-42-run-1",),
        cleanup_plan={"E2E-42-run-1": "DELETE FROM test_resources WHERE id = 'E2E-42-run-1'"},
    )

    assert [item.status for item in result.results] == ["failed", "failed"]
    assert result.results[0].runtime_result["error"] == "RuntimeError: boom"
    assert result.results[1].runtime_result["reason"] == "release_e2e_skip_forbidden"
