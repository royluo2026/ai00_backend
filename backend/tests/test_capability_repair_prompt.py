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
    service = CapabilityGovernanceService()
    prompt = service.generate_repair_prompt(
        _finding(),
        {"implementation": {"url": "https://user:pass@example.test/private"}},
        {"allowed": ["backend/capabilities"], "forbidden": ["database migrations"], "required_tests": ["pytest"]},
        context=type("Context", (), {"user_gid": "actor-1"})(), request_id="request-1",
    )

    assert prompt.prompt_hash.startswith("sha256:")
    assert "user:pass" not in repr(prompt.store_record())
    with pytest.raises(PromptAuthorizationError, match="prompt_access_denied"):
        service.read_repair_prompt(prompt, context=type("Context", (), {"user_gid": "actor-1"})())
    text = service.read_repair_prompt(prompt, context=type("Context", (), {
        "user_gid": "actor-1", "governance_permissions": ("base.capability_repair_prompt.read",),
    })())
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
    assert dict(sink.events[0].detail) == {"prompt_hash": prompt.prompt_hash}


def test_service_authorizes_prompt_read_and_drops_benign_business_evidence_and_boundary_content():
    service = CapabilityGovernanceService()
    prompt = service.generate_repair_prompt(
        _finding(),
        {"evidence_keys": ["evidence:7"], "friendly_note": "customer Alice order 123"},
        {"snapshot_gid": "9", "allowed_change_ids": ["capability.contract"], "friendly_note": "source code text"},
        context=type("Context", (), {"user_gid": "actor-1"})(), request_id="request-1",
    )
    unauthorized = type("Context", (), {"user_gid": "actor-1", "governance_permissions": ()})()
    authorized = type("Context", (), {
        "user_gid": "actor-1", "governance_permissions": ("base.capability_repair_prompt.read",),
    })()

    with pytest.raises(PromptAuthorizationError, match="prompt_access_denied"):
        service.read_repair_prompt(prompt, context=unauthorized)
    text = service.read_repair_prompt(prompt, context=authorized)
    assert "Alice" not in text
    assert "source code text" not in text


def test_prompt_holder_cannot_self_authorize_text_access():
    prompt = build_repair_prompt(_finding(), {"evidence_keys": ["evidence:7"]}, {"snapshot_gid": "9"})

    assert not hasattr(prompt, "text_for")
