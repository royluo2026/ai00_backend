from unittest.mock import Mock

import pytest

from plugins.agent.agent_backend.orchestration.runtime import InvalidTransition, OrchestrationRuntime


def test_runtime_starts_run_and_event_through_one_atomic_repository_call():
    repo = Mock()
    repo.create_run_with_started_event.return_value = "run-1"
    runtime = OrchestrationRuntime(repo)

    run_gid = runtime.start(
        panorama_gid="pan-1",
        version_gid="ver-7",
        frozen_context={"catalog_release": "rel-1", "capability_versions": ["cv2-1"]},
        actor_gid="u1",
        tenant_gid="tenant-1",
        project_gid="project-1",
    )

    assert run_gid == "run-1"
    repo.create_run_with_started_event.assert_called_once_with(
        panorama_gid="pan-1",
        version_gid="ver-7",
        frozen_context={"catalog_release": "rel-1", "capability_versions": ["cv2-1"]},
        actor_gid="u1",
        tenant_gid="tenant-1",
        project_gid="project-1",
    )


def test_runtime_delegates_transition_and_event_to_one_atomic_repository_call():
    repo = Mock()
    repo.transition_run_with_event.return_value = {"status": "waiting_human", "sequence_no": 2}
    runtime = OrchestrationRuntime(repo)

    result = runtime.advance(
        "run-1", "waiting_human", authorized_principal_gid="owner-1",
        actor_type="agent", actor_gid="agent-1", payload={"reason": "review"},
        tenant_gid="tenant-1", project_gid="project-1",
    )

    assert result == {"status": "waiting_human", "sequence_no": 2}
    repo.transition_run_with_event.assert_called_once_with(
        "run-1",
        target_status="waiting_human",
        authorized_principal_gid="owner-1",
        actor_type="agent",
        event_actor_gid="agent-1",
        payload={"reason": "review"},
        tenant_gid="tenant-1",
        project_gid="project-1",
    )


def test_runtime_preserves_repository_transition_failure():
    repo = Mock()
    repo.transition_run_with_event.side_effect = InvalidTransition("terminal")

    with pytest.raises(InvalidTransition):
        OrchestrationRuntime(repo).advance(
            "run-1", "running", authorized_principal_gid="owner-1",
            actor_type="human", actor_gid="approver-1",
            tenant_gid="tenant-1", project_gid="project-1",
        )
