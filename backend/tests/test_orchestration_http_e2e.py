"""HTTP-level proof for the orchestration runtime transaction boundary.

The app below is intentionally a test harness: it injects the real
``OrchestrationRuntime`` and repository with a deterministic fake connection,
so no shared or external database is touched.  The fake connection is scoped
to each test and discarded after the client closes.
"""
from contextlib import contextmanager

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from plugins.agent.agent_backend.orchestration.repository import OrchestrationRepository
from plugins.agent.agent_backend.orchestration.runtime import OrchestrationRuntime


class Cursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 1
        self._response = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, tuple(params)))
        if "SELECT v.gid FROM workmanship_agent_orch_versions" in normalized:
            self._response = [{"gid": "version-1"}]
        elif "SELECT r.status FROM workmanship_agent_orch_runs" in normalized:
            self._response = [{"status": "running"}]
        elif "COALESCE(MAX(sequence_no),0)" in normalized:
            self._response = [{"last_sequence_no": 1}]
        else:
            self._response = []

    def fetchone(self):
        return self._response[0] if self._response else None

    def fetchall(self):
        return self._response


class Connection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj


def make_client():
    cursor = Cursor()
    connection = Connection(cursor)

    @contextmanager
    def factory():
        try:
            yield connection
        except Exception:
            connection.rolled_back = True
            raise
        else:
            connection.committed = True

    runtime = OrchestrationRuntime(OrchestrationRepository(factory))
    router = APIRouter(prefix="/api/orchestration")

    @router.post("/runs")
    def start_run():
        return {
            "run_gid": runtime.start(
                panorama_gid="panorama-1", version_gid="version-1", frozen_context={},
                actor_gid="user-1", tenant_gid="tenant-1", project_gid="project-1",
            )
        }

    @router.post("/runs/{run_gid}/transition")
    def transition(run_gid: str):
        return runtime.advance(
            run_gid, "succeeded", authorized_principal_gid="user-1", actor_type="agent",
            actor_gid="agent-1", tenant_gid="tenant-1", project_gid="project-1",
        )

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), connection, cursor


def test_http_route_runs_real_runtime_start_and_transition_with_scope():
    client, connection, cursor = make_client()

    started = client.post("/api/orchestration/runs")
    assert started.status_code == 200
    run_gid = started.json()["run_gid"]
    transitioned = client.post(f"/api/orchestration/runs/{run_gid}/transition")

    assert transitioned.status_code == 200
    assert transitioned.json()["status"] == "succeeded"
    assert connection.committed is True
    assert connection.rolled_back is False
    guards = [sql for sql, _ in cursor.calls if "p.tenant_gid=%s" in sql]
    assert guards and all("p.project_gid=%s" in sql for sql in guards)
    client.close()
