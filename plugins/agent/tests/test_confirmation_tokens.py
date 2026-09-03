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


def test_gateway_failure_releases_reserved_token_and_concurrent_replay_is_blocked() -> None:
    name = "cap__project__task__change__apply__v1"
    token = tool_executor.issue_confirm_token(
        name, {"name": "x"}, "session-1", "user-1",
        catalog_release="rel-1", capability_id="project.task.change.apply", major_version=1,
    )
    args = dict(
        catalog_release="rel-1", capability_id="project.task.change.apply", major_version=1,
    )

    assert tool_executor.begin_confirm_token(token, name, "session-1", "user-1", **args)[0] is True
    assert tool_executor.begin_confirm_token(token, name, "session-1", "user-1", **args) == (False, {})
    tool_executor.finish_confirm_token(token, accepted=False)
    assert tool_executor.begin_confirm_token(token, name, "session-1", "user-1", **args)[0] is True
    tool_executor.finish_confirm_token(token, accepted=True)
    assert tool_executor.begin_confirm_token(token, name, "session-1", "user-1", **args) == (False, {})
