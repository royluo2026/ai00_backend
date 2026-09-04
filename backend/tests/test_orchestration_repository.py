from contextlib import contextmanager

import pytest

from plugins.agent.agent_backend.orchestration.models import GraphDraft
from plugins.agent.agent_backend.orchestration.repository import (
    InvalidTransition,
    OrchestrationRepository,
    ResourceNotAccessible,
    RevisionConflict,
    UntrustedBindingEvidence,
)


class RecordingCursor:
    def __init__(self, responses=None, fail_on=None):
        self.executions = []
        self.responses = responses or {}
        self.fail_on = fail_on
        self.current_response = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.executions.append((normalized, tuple(params)))
        if self.fail_on and self.fail_on in normalized:
            raise RuntimeError("injected persistence failure")
        self.current_response = next(
            (rows for marker, rows in self.responses.items() if marker in normalized), []
        )

    def fetchone(self):
        return self.current_response[0] if self.current_response else None

    def fetchall(self):
        return self.current_response


class RecordingConnection:
    def __init__(self, cursor):
        self.recording_cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.recording_cursor


def connection_factory(cursor):
    connection = RecordingConnection(cursor)

    @contextmanager
    def factory():
        try:
            yield connection
        except Exception:
            connection.rolled_back = True
            raise
        else:
            connection.committed = True

    factory.connection = connection
    return factory


def owned_version(*, revision=7, status="draft"):
    return [{"panorama_gid": "pan-1", "status": status, "revision": revision, "mode": "fixed"}]


def test_save_graph_guards_owned_draft_revision_before_replacing_children():
    cursor = RecordingCursor({"FROM workmanship_agent_orch_versions v": owned_version()})
    repo = OrchestrationRepository(connection_factory(cursor))

    revision = repo.save_graph(
        "version-1", GraphDraft(nodes=[], edges=[]), expected_revision=7, actor_gid="user-1",
        tenant_gid="tenant-1", project_gid="project-1",
    )

    ownership_sql, ownership_params = cursor.executions[0]
    update_sql, update_params = cursor.executions[1]
    assert "p.owner_user_gid=%s" in ownership_sql and "FOR UPDATE" in ownership_sql
    assert ownership_params == ("version-1", "user-1", "tenant-1", "project-1")
    assert "status='draft'" in update_sql and "revision=%s" in update_sql
    assert update_params == ("fixed", "user-1", "version-1", 7)
    assert revision == 8


def test_save_graph_requires_tenant_and_project_scope_in_owner_guard():
    cursor = RecordingCursor({"FROM workmanship_agent_orch_versions v": owned_version()})
    repo = OrchestrationRepository(connection_factory(cursor))

    repo.save_graph(
        "version-1", GraphDraft(nodes=[], edges=[]), expected_revision=7,
        actor_gid="user-1", tenant_gid="tenant-1", project_gid="project-1",
    )

    ownership_sql, ownership_params = cursor.executions[0]
    assert "p.tenant_gid=%s" in ownership_sql
    assert "p.project_gid=%s" in ownership_sql
    assert ownership_params == ("version-1", "user-1", "tenant-1", "project-1")


def test_write_rejects_missing_scope_before_opening_transaction():
    cursor = RecordingCursor()
    repo = OrchestrationRepository(connection_factory(cursor))

    with pytest.raises(ResourceNotAccessible, match="tenant and project scope"):
        repo.save_graph(
            "version-1", GraphDraft(nodes=[], edges=[]), expected_revision=7,
            actor_gid="user-1", tenant_gid="tenant-1",
        )

    assert cursor.executions == []


@pytest.mark.parametrize("reader,args", [
    ("list_panoramas_for_user", ("user-1",)),
    ("get_metric_for_user", ("pan-1", "2026" , "user-1")),
    ("get_run_state_for_user", ("run-1", "user-1")),
])
def test_all_orchestration_reads_reject_missing_project_scope_before_query(reader, args):
    cursor = RecordingCursor()
    repo = OrchestrationRepository(connection_factory(cursor))
    with pytest.raises(ResourceNotAccessible, match="tenant and project scope"):
        getattr(repo, reader)(*args, tenant_gid="tenant-1", project_gid=None)
    assert cursor.executions == []


def test_save_graph_hides_foreign_version_and_rejects_stale_owned_version():
    foreign = OrchestrationRepository(connection_factory(RecordingCursor()))
    with pytest.raises(ResourceNotAccessible):
        foreign.save_graph("version-1", GraphDraft(nodes=[], edges=[]), expected_revision=7, actor_gid="user-2",
                           tenant_gid="tenant-1", project_gid="project-1")

    stale_cursor = RecordingCursor({"FROM workmanship_agent_orch_versions v": owned_version(revision=8)})
    with pytest.raises(RevisionConflict):
        OrchestrationRepository(connection_factory(stale_cursor)).save_graph(
            "version-1", GraphDraft(nodes=[], edges=[]), expected_revision=7, actor_gid="user-1",
            tenant_gid="tenant-1", project_gid="project-1",
        )


def test_get_graph_rehydrates_only_an_owned_version():
    cursor = RecordingCursor({
        "SELECT v.mode FROM workmanship_agent_orch_versions v": [{"mode": "exploration"}],
        "workmanship_agent_orch_axis_views": [{"x_items_json": '["TG0"]', "y_items_json": '["工艺规划"]'}],
    })
    repo = OrchestrationRepository(connection_factory(cursor))

    graph = repo.get_graph("version-1", actor_gid="user-1", tenant_gid="tenant-1", project_gid="project-1")

    assert graph.mode == "exploration"
    assert graph.axis.x_items == ["TG0"]
    assert graph.axis.y_items == ["工艺规划"]
    assert "p.owner_user_gid=%s" in cursor.executions[0][0]
    assert "p.tenant_gid=%s" in cursor.executions[0][0]
    assert "p.project_gid=%s" in cursor.executions[0][0]


def test_publish_and_delete_binding_require_owner_inside_transaction():
    cursor = RecordingCursor({
        "FROM workmanship_agent_orch_versions v": owned_version(revision=8),
        "SELECT b.gid FROM workmanship_agent_orch_capability_bindings": [{"gid": "binding-1"}],
    })
    repo = OrchestrationRepository(connection_factory(cursor))

    result = repo.publish_version(
        "version-1", expected_revision=8, actor_gid="user-1", resolved_bindings=[],
        tenant_gid="tenant-1", project_gid="project-1",
    )
    repo.delete_binding("binding-1", actor_gid="user-1", tenant_gid="tenant-1", project_gid="project-1")

    assert result == {"version_gid": "version-1", "revision": 9, "status": "published"}
    delete_guard = next(sql for sql, _ in cursor.executions if "SELECT b.gid" in sql)
    assert "p.owner_user_gid=%s" in delete_guard and "FOR UPDATE" in delete_guard
    assert not any("workmanship_base_capability" in sql for sql, _ in cursor.executions)


def test_publish_and_delete_hide_foreign_resources():
    repo = OrchestrationRepository(connection_factory(RecordingCursor()))
    with pytest.raises(ResourceNotAccessible):
        repo.publish_version(
            "version-1", expected_revision=8, actor_gid="user-2", resolved_bindings=[],
            tenant_gid="tenant-1", project_gid="project-1",
        )
    with pytest.raises(ResourceNotAccessible):
        repo.delete_binding("binding-1", actor_gid="user-2", tenant_gid="tenant-1", project_gid="project-1")


def test_create_run_requires_owned_matching_published_version_and_writes_started_event():
    cursor = RecordingCursor({"SELECT v.gid FROM workmanship_agent_orch_versions v": [{"gid": "ver-1"}]})
    repo = OrchestrationRepository(connection_factory(cursor))

    run_gid = repo.create_run_with_started_event(
        panorama_gid="pan-1", version_gid="ver-1", frozen_context={"catalog_release": "rel-1"}, actor_gid="user-1",
        tenant_gid="tenant-1", project_gid="project-1",
    )

    guard_sql, guard_params = cursor.executions[0]
    assert "v.panorama_gid=%s" in guard_sql and "v.status='published'" in guard_sql
    assert "p.owner_user_gid=%s" in guard_sql and "FOR UPDATE" in guard_sql
    assert guard_params == ("ver-1", "pan-1", "user-1", "tenant-1", "project-1")
    assert any("INSERT INTO workmanship_agent_orch_runs" in sql for sql, _ in cursor.executions)
    assert any("INSERT INTO workmanship_agent_orch_run_events" in sql for sql, _ in cursor.executions)
    assert run_gid


def test_publish_requires_exact_catalog_evidence_for_every_stored_binding():
    cursor = RecordingCursor({
        "FROM workmanship_agent_orch_versions v": owned_version(revision=8),
        "SELECT gid,capability_version_gid": [
            {"gid": "binding-1", "capability_version_gid": "cv2_1"}
        ],
    })
    repo = OrchestrationRepository(connection_factory(cursor))

    with pytest.raises(UntrustedBindingEvidence):
        repo.publish_version(
            "version-1", expected_revision=8, actor_gid="user-1", resolved_bindings=[],
            tenant_gid="tenant-1", project_gid="project-1",
        )


def test_create_run_rejects_foreign_or_mismatched_version():
    repo = OrchestrationRepository(connection_factory(RecordingCursor()))
    with pytest.raises(ResourceNotAccessible):
        repo.create_run_with_started_event(
            panorama_gid="pan-1", version_gid="ver-other", frozen_context={}, actor_gid="user-1"
            , tenant_gid="tenant-1", project_gid="project-1"
        )


def test_start_rolls_back_run_when_started_event_fails():
    cursor = RecordingCursor(
        {"SELECT v.gid FROM workmanship_agent_orch_versions v": [{"gid": "ver-1"}]},
        fail_on="INSERT INTO workmanship_agent_orch_run_events",
    )
    factory = connection_factory(cursor)
    repo = OrchestrationRepository(factory)

    with pytest.raises(RuntimeError, match="injected persistence failure"):
        repo.create_run_with_started_event(
            panorama_gid="pan-1", version_gid="ver-1", frozen_context={}, actor_gid="user-1",
            tenant_gid="tenant-1", project_gid="project-1",
        )

    assert factory.connection.rolled_back is True
    assert factory.connection.committed is False


def test_transition_locks_owned_run_allocates_sequence_and_appends_event():
    cursor = RecordingCursor({
        "SELECT r.status FROM workmanship_agent_orch_runs r": [{"status": "running"}],
        "SELECT COALESCE(MAX(sequence_no),0)": [{"last_sequence_no": 7}],
    })
    repo = OrchestrationRepository(connection_factory(cursor))

    result = repo.transition_run_with_event(
        "run-1", target_status="succeeded", authorized_principal_gid="user-1",
        actor_type="agent", event_actor_gid="agent-1", payload={"accepted": True},
        tenant_gid="tenant-1", project_gid="project-1",
    )

    assert "FOR UPDATE" in cursor.executions[0][0]
    assert "p.owner_user_gid=%s" in cursor.executions[0][0]
    assert result["sequence_no"] == 8 and result["status"] == "succeeded"
    event_params = next(params for sql, params in cursor.executions if "INSERT INTO workmanship_agent_orch_run_events" in sql)
    assert event_params[6] == "agent-1"
    assert '"from":"running"' in event_params[7]
    assert '"to":"succeeded"' in event_params[7]


def test_transition_rolls_back_run_when_event_append_fails():
    cursor = RecordingCursor(
        {
            "SELECT r.status FROM workmanship_agent_orch_runs r": [{"status": "running"}],
            "SELECT COALESCE(MAX(sequence_no),0)": [{"last_sequence_no": 3}],
        },
        fail_on="INSERT INTO workmanship_agent_orch_run_events",
    )
    factory = connection_factory(cursor)
    repo = OrchestrationRepository(factory)

    with pytest.raises(RuntimeError, match="injected persistence failure"):
        repo.transition_run_with_event(
            "run-1", target_status="succeeded", authorized_principal_gid="user-1",
            actor_type="agent", event_actor_gid="agent-1", payload={"accepted": True},
            tenant_gid="tenant-1", project_gid="project-1",
        )

    assert factory.connection.rolled_back is True
    assert factory.connection.committed is False


def test_transition_rejects_foreign_and_terminal_runs():
    foreign = OrchestrationRepository(connection_factory(RecordingCursor()))
    with pytest.raises(ResourceNotAccessible):
        foreign.transition_run_with_event(
            "run-1", target_status="failed", authorized_principal_gid="user-2",
            actor_type="agent", event_actor_gid="agent-1", payload={},
            tenant_gid="tenant-1", project_gid="project-1",
        )

    terminal_cursor = RecordingCursor({"SELECT r.status FROM workmanship_agent_orch_runs r": [{"status": "succeeded"}]})
    terminal = OrchestrationRepository(connection_factory(terminal_cursor))
    with pytest.raises(InvalidTransition):
        terminal.transition_run_with_event(
            "run-1", target_status="running", authorized_principal_gid="user-1",
            actor_type="human", event_actor_gid="approver-1", payload={},
            tenant_gid="tenant-1", project_gid="project-1",
        )
