from plugins.agent.agent_backend.ai_assistant import tool_executor


def setup_function() -> None:
    tool_executor._CONFIRM_TOKENS.clear()


def test_confirmation_token_is_bound_and_bad_attempt_does_not_consume_it() -> None:
    token = tool_executor.issue_confirm_token("cap__project__task__change__apply__v1", {"name": "x"}, "session-1", "user-1")

    assert tool_executor.consume_confirm_token(token, "cap__project__task__change__apply__v1", "session-2", "user-1") == (False, {})
    assert tool_executor.consume_confirm_token(token, "cap__project__task__change__apply__v1", "session-1", "user-2") == (False, {})

    valid, pending = tool_executor.consume_confirm_token(token, "cap__project__task__change__apply__v1", "session-1", "user-1")
    assert valid is True
    assert pending["inputs"] == {"name": "x"}
    assert tool_executor.consume_confirm_token(token, "cap__project__task__change__apply__v1", "session-1", "user-1") == (False, {})
