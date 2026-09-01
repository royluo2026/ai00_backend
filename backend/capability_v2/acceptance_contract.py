"""Shared, deterministic acceptance case identities for stable Capabilities."""
from __future__ import annotations

from typing import Any


MANDATORY_CASES = (
    "success",
    "invalid_input",
    "unauthenticated",
    "resource_denied",
    "output_contract",
    "consumer_contract",
    "version_pin",
)
TEST_MODULE = "backend/tests/acceptance/test_mandatory_cases.py"


def case_node_id(case: str, capability_id: str, major_version: int) -> str:
    if case not in MANDATORY_CASES:
        raise ValueError(f"unknown mandatory acceptance case: {case}")
    return f"{TEST_MODULE}::test_{case}_case[{capability_id}@{major_version}]"


def coverage_declarations(
    capability_id: str,
    major_version: int,
    *,
    code_revision: str,
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "test_type": "contract",
            "test_node_id": case_node_id(case, capability_id, major_version),
            "code_revision": code_revision,
            "path": TEST_MODULE,
        }
        for case in MANDATORY_CASES
    )


__all__ = ["MANDATORY_CASES", "TEST_MODULE", "case_node_id", "coverage_declarations"]
