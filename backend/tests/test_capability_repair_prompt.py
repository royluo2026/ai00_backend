from __future__ import annotations

import pytest

from backend.capability_governance_test.prompting import (
    PromptAuthorizationError,
    build_repair_prompt,
)
from backend.capability_governance_test.audit import AuditSink
from backend.capability_governance_test.service import CapabilityGovernanceService


def _finding():
    return {
        "finding_type": "gap", "subject_version_gids": ["7"], "confidence": 0.8,
        "evidence_keys": ["evidence:7"], "recommendation": "add a lifecycle pair", "status": "candidate",
    }


def test_repair_prompt_has_required_sections_and_only_authorized_callers_can_read_text():
    prompt = build_repair_prompt(
        _finding(),
        {"implementation": {"url": "https://user:pass@example.test/private"}},
        {"allowed": ["backend/capabilities"], "forbidden": ["database migrations"], "required_tests": ["pytest"]},
    )

    assert prompt.prompt_hash.startswith("sha256:")
    assert "user:pass" not in repr(prompt.store_record())
    with pytest.raises(PromptAuthorizationError, match="prompt_access_denied"):
        prompt.text_for(authorized=False)
    text = prompt.text_for(authorized=True)
    for section in (
        "snapshot identity", "capability identities", "observed contract", "implementation evidence",
        "finding", "allowed change boundary", "forbidden changes", "required tests", "acceptance criteria",
    ):
        assert section in text.lower()
    assert "user:pass" not in text


def test_repair_prompt_store_record_never_contains_prompt_text():
    prompt = build_repair_prompt(_finding(), {"summary": "safe"}, {"allowed": []})

    assert set(prompt.store_record()) == {"prompt_hash", "redacted_summary"}


def test_service_persists_only_redacted_prompt_metadata_and_audits_generation():
    sink = AuditSink(next_gid=iter(range(1, 10)).__next__)
    service = CapabilityGovernanceService(audit_sink=sink)
    context = type("Context", (), {"user_gid": "actor-1"})()

    prompt = service.generate_repair_prompt(
        _finding(), {"password": "secret"}, {"allowed": []}, context=context, request_id="request-1",
    )

    assert service.prompt_records == {prompt.prompt_hash: prompt.store_record()}
    assert "secret" not in repr(service.prompt_records)
    assert sink.events[0].operation == "prompt_generation"
