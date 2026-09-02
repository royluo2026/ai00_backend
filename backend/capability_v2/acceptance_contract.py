"""Shared, deterministic acceptance case identities for stable Capabilities."""
from __future__ import annotations

import hashlib
from pathlib import Path
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


def canonical_test_source_hash(source: bytes) -> str:
    """Hash UTF-8 test source after normalizing only CRLF line endings."""
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("test source must be valid UTF-8") from exc
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        raise ValueError("test source contains bare CR")
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def mandatory_test_source_revision(root: Path) -> str:
    return canonical_test_source_hash((root / TEST_MODULE).read_bytes())


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


__all__ = [
    "MANDATORY_CASES", "TEST_MODULE", "canonical_test_source_hash",
    "mandatory_test_source_revision", "case_node_id", "coverage_declarations",
]
