import asyncio
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.agent.agent_backend.infrastructure.repository import AgentCapabilityRepository


ROOT = Path(__file__).resolve().parents[3]


class Cursor:
    def __init__(self, rows=()):
        self.rows = [dict(row) for row in rows]
        self.statements = []
        self.rowcount = 1
        self._one = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.statements.append((" ".join(sql.split()), tuple(params)))
        if sql.lstrip().upper().startswith("SELECT"):
            gid, actor, team = params
            owner_key = "owner_user_gid" if "workmanship_app_flows" in sql else "owner_gid"
            self._one = next((
                row for row in self.rows
                if row.get("gid") == gid and row.get("team_gid") == team
                and (
                    row.get(owner_key) == actor
                    or (owner_key == "owner_gid" and row.get("scope") == "team")
                    or (owner_key == "owner_gid" and row.get("scope") == "global" and row.get("status") == "active")
                )
            ), None)

    def fetchone(self):
        return self._one


class Connection:
    def __init__(self, rows=()):
        self.cursor_value = Cursor(rows)

    def cursor(self):
        return self.cursor_value


def connection_factory(rows=()):
    connection = Connection(rows)

    @contextmanager
    def factory():
        yield connection

    return connection, factory


def test_agent_0002_persists_nullable_team_binding_and_reserves_0003_for_task3():
    path = ROOT / "backend/db/migrations/domains/agent/0002_canvas_query_tenant.sql"
    sql = path.read_text(encoding="utf-8").lower()

    assert "alter table workmanship_app_flows" in sql
    assert "alter table workmanship_app_skills" in sql
    assert sql.count("add column if not exists team_gid varchar(191) null") == 2
    assert "update workmanship_app_" not in sql
    assert not (path.parent / "0003_canvas_query_tenant.sql").exists()


def test_repository_canvas_load_requires_persisted_actor_and_team(monkeypatch):
    rows = ({
        "gid": "flow-1", "owner_user_gid": "actor-1", "team_gid": "team-1",
        "flowdef": json.dumps({"nodes": []}),
    }, {
        "gid": "legacy-flow", "owner_user_gid": "actor-1", "team_gid": None,
        "flowdef": json.dumps({"nodes": []}),
    })
    connection, factory = connection_factory(rows)
    monkeypatch.setattr(
        "plugins.agent.agent_backend.infrastructure.repository.get_agent_conn", factory,
    )
    repository = AgentCapabilityRepository()

    assert repository.load_canvas_resource("flow", "flow-1", "actor-1", "team-1")["gid"] == "flow-1"
    assert repository.load_canvas_resource("flow", "flow-1", "actor-1", "team-2") is None
    assert repository.load_canvas_resource("flow", "legacy-flow", "actor-1", "team-1") is None
    assert all("team_gid=%s" in sql and "owner_user_gid=%s" in sql for sql, _ in connection.cursor_value.statements)


def test_new_flow_and_skill_creates_persist_context_team(monkeypatch):
    connection, factory = connection_factory()
    monkeypatch.setattr(
        "plugins.agent.agent_backend.infrastructure.repository.get_agent_conn", factory,
    )
    repository = AgentCapabilityRepository()

    repository.flow_apply({
        "operation": "create", "owner_gid": "actor-1", "tenant_gid": "team-1",
        "name": "Flow", "flowdef": "{}",
    })
    repository.skill_apply({
        "operation": "create", "owner_gid": "actor-1", "tenant_gid": "team-1",
        "name": "skill", "title": "Skill", "scope": "team",
    })

    flow_sql, flow_params = connection.cursor_value.statements[0]
    skill_sql, skill_params = connection.cursor_value.statements[1]
    assert "team_gid" in flow_sql and "team-1" in flow_params
    assert "team_gid" in skill_sql and "team-1" in skill_params


def test_default_registered_query_composes_runtime_and_uniformly_denies_cross_team(monkeypatch):
    from plugins.agent.agent_backend import capabilities
    from plugins.agent.agent_backend.application.canvas_runtime import RunPrincipal

    rows = ({
        "gid": "flow-1", "owner_user_gid": "actor-1", "team_gid": "team-1",
        "flowdef": json.dumps({"nodes": [{"id": "node-1", "type": "list"}], "edges": []}),
    },)
    _connection, factory = connection_factory(rows)
    monkeypatch.setattr(
        "plugins.agent.agent_backend.infrastructure.repository.get_agent_conn", factory,
    )

    class InlineRuntime:
        def __init__(self, *, repository_factory):
            self.repository = repository_factory()

        async def test_node(self, request, principal):
            row = self.repository.load_canvas_resource(
                "flow", request.flow_gid, principal.actor_gid, principal.team_gid,
            )
            if row is None:
                raise CapabilityBusinessError(
                    "resource_not_found", "Agent canvas resource was not found",
                )
            from plugins.agent.agent_backend.application.canvas_runtime import NodeTestResult
            return NodeTestResult("completed", summary="ok")

        async def resolve_options(self, *_args):
            raise AssertionError("unused")

        async def start(self, *_args):
            raise AssertionError("unused")

        async def resume(self, *_args):
            raise AssertionError("unused")

    monkeypatch.setattr(capabilities, "ProductionAgentCanvasRuntime", InlineRuntime, raising=False)

    class Registry:
        def __init__(self):
            self.handlers = {}

        def register(self, spec, handler, **_kwargs):
            self.handlers[spec.id] = handler

    class SameTeam:
        user_gid = "actor-1"
        team_gid = "team-1"

    class OtherTeam:
        user_gid = "actor-1"
        team_gid = "team-2"

    registry = Registry()
    capabilities.register_capabilities(registry)
    payload = {"flow_gid": "flow-1", "node_id": "node-1", "input_values": []}

    assert asyncio.run(registry.handlers["agent.workflow.node.test.execute"](payload, SameTeam())) == {
        "data": {"status": "completed", "output_values": [], "summary": "ok"},
    }
    denials = []
    for context in (OtherTeam(), SameTeam()):
        denied_payload = payload if isinstance(context, OtherTeam) else {**payload, "flow_gid": "missing"}
        with pytest.raises(CapabilityBusinessError) as error:
            asyncio.run(registry.handlers["agent.workflow.node.test.execute"](denied_payload, context))
        denials.append((error.value.code, error.value.message, error.value.details))
    assert denials == [
        ("resource_not_found", "Agent canvas resource was not found", {}),
        ("resource_not_found", "Agent canvas resource was not found", {}),
    ]
    assert RunPrincipal("actor-1", "team-1").team_gid == "team-1"
