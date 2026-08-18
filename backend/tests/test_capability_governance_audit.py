import pytest

from backend.capability_governance_test.audit import AuditError, AuditSink


@pytest.mark.parametrize("operation", ("scan", "analysis", "confirmation", "rejection", "proposal", "review", "waiver", "test", "gate", "prompt_generation", "agent_invocation"))
def test_audit_sink_appends_one_redacted_event_for_each_governance_operation(operation):
    sink = AuditSink(next_gid=iter(range(1, 100)).__next__)

    event = sink.append(operation=operation, entity_gid=9, actor_gid="agent-1", request_gid="request-1", detail={"password": "p@ss", "api_token": "token-value", "endpoint_url": "https://user:secret@example.test/path", "safe": "value"}, idempotency_key=operation)

    assert sink.events == (event,)
    assert event.detail["safe"] == "value"
    rendered = repr(event.detail).lower()
    assert "p@ss" not in rendered
    assert "token-value" not in rendered
    assert "user:secret" not in rendered


def test_audit_events_are_append_only_and_idempotent():
    sink = AuditSink(next_gid=iter(range(1, 100)).__next__)
    first = sink.append(operation="scan", entity_gid=9, actor_gid="agent-1", request_gid="request-1", detail={}, idempotency_key="scan-1")

    assert sink.append(operation="scan", entity_gid=9, actor_gid="agent-1", request_gid="request-1", detail={}, idempotency_key="scan-1") == first
    with pytest.raises(AuditError, match="append_only"):
        sink.update(first.audit_event_gid, detail={})
