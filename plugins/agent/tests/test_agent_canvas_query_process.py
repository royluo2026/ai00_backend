import asyncio
import json
import multiprocessing
import time
from pathlib import Path

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.agent.agent_backend.application.canvas_runtime import (
    NodeTestRequest,
    ProductionAgentCanvasRuntime,
    RunPrincipal,
)


class _PersistedRepository:
    def load_canvas_resource(self, kind, gid, actor_gid, team_gid):
        if kind == "flow" and gid == "flow-1" and actor_gid == "actor-1" and team_gid == "team-1":
            return {
                "gid": gid, "owner_user_gid": actor_gid, "team_gid": team_gid,
                "flowdef": json.dumps({
                    "nodes": [{
                        "id": "node-1", "type": "list", "label": "Persisted list",
                        "inputs_schema": {"project_gid": {"type": "string"}},
                    }],
                    "edges": [],
                }),
            }
        if kind == "skill" and gid == "skill-1" and team_gid == "team-1":
            return {
                "gid": gid, "owner_gid": "actor-1", "team_gid": team_gid,
                "scope": "private", "status": "active", "revision": 4,
                "content": {
                    "nodes": [{
                        "id": "human-1", "type": "human",
                        "params": {"collect_fields": [{
                            "key": "project_gid",
                            "options": [{"value": "b", "label": "Zulu"}, {"value": "a", "label": "Alpha"}],
                        }]},
                    }],
                    "edges": [],
                },
            }
        return None


def _send(channel, envelope):
    raw = json.dumps(envelope, separators=(",", ":"))
    channel.send_bytes(raw.encode("utf-8"))


def _successful_worker(channel, payload_json):
    payload = json.loads(payload_json)
    node_id = payload["request"]["node_id"]
    _send(channel, {
        "ok": True,
        "result": {
            "status": "completed",
            "output_values": [{"name": "count", "value": 1}],
            "summary": "ok",
        },
        "node_id": node_id,
    })


def _near_limit_worker(channel, _payload_json):
    _send(channel, {
        "ok": True,
        "result": {
            "status": "completed",
            "output_values": [
                {"name": f"field-{index}", "value": "x" * 4000}
                for index in range(16)
            ],
            "summary": "near limit",
        },
    })


def _oversize_worker(channel, _payload_json):
    _send(channel, {
        "ok": True,
        "result": {
            "status": "completed",
            "output_values": [
                {"name": f"field-{index}", "value": "x" * 4000}
                for index in range(24)
            ],
            "summary": "too large",
        },
    })


def _slow_marker_worker(_result_connection, payload_json):
    marker = Path(json.loads(payload_json)["request"]["flow_gid"])
    time.sleep(0.25)
    marker.write_text("orphan", encoding="utf-8")


def test_production_adapter_returns_json_only_spawned_worker_result():
    runtime = ProductionAgentCanvasRuntime(worker_target=_successful_worker, worker_timeout=5.0)

    result = asyncio.run(runtime.test_node(
        NodeTestRequest("flow-1", "node-1"), RunPrincipal("actor-1", "team-1"),
    ))

    assert result.status == "completed"
    assert [(item.name, item.value) for item in result.output_values] == [("count", 1)]
    assert result.summary == "ok"


def test_near_limit_worker_output_is_drained_before_join_and_repeated_runs_leave_no_workers():
    runtime = ProductionAgentCanvasRuntime(worker_target=_near_limit_worker, worker_timeout=3.0)
    before = {child.pid for child in multiprocessing.active_children()}

    for _ in range(3):
        result = asyncio.run(runtime.test_node(
            NodeTestRequest("flow-1", "node-1"), RunPrincipal("actor-1", "team-1"),
        ))
        assert len(result.output_values) == 16
        assert all(len(item.value) == 4000 for item in result.output_values)

    assert {child.pid for child in multiprocessing.active_children()} <= before


def test_worker_output_larger_than_transport_ceiling_is_rejected_and_cleaned_up():
    runtime = ProductionAgentCanvasRuntime(worker_target=_oversize_worker, worker_timeout=3.0)
    before = {child.pid for child in multiprocessing.active_children()}

    with pytest.raises(CapabilityBusinessError) as error:
        asyncio.run(runtime.test_node(
            NodeTestRequest("flow-1", "node-1"), RunPrincipal("actor-1", "team-1"),
        ))

    assert error.value.code == "invalid_input"
    assert {child.pid for child in multiprocessing.active_children()} <= before


def test_default_registered_handlers_use_production_repository_and_executor_path(monkeypatch):
    from plugins.agent.agent_backend import capabilities

    monkeypatch.setattr(capabilities, "AgentCapabilityRepository", _PersistedRepository)

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

    class Transaction:
        def record_outbox(self, *_args): pass
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    registry = Registry()
    capabilities.register_capabilities(registry, transaction_factory=Transaction)
    node_payload = {
        "flow_gid": "flow-1", "node_id": "node-1",
        "input_values": [{"name": "project_gid", "value": "p1"}],
    }
    options_payload = {
        "skill_gid": "skill-1", "node_id": "human-1",
        "field_key": "project_gid", "input_values": [],
    }

    node_output = asyncio.run(registry.handlers["agent.workflow.node.test.execute"](node_payload, SameTeam()))
    node = node_output.data
    options = asyncio.run(registry.handlers["agent.canvas.options.resolve"](options_payload, SameTeam()))
    assert node["status"] == "completed"
    assert options == {
        "revision": 4,
        "options": [{"value": "a", "label": "Alpha"}, {"value": "b", "label": "Zulu"}],
    }

    denials = []
    for context, payload in ((OtherTeam(), node_payload), (SameTeam(), {**node_payload, "flow_gid": "missing"})):
        with pytest.raises(CapabilityBusinessError) as error:
            asyncio.run(registry.handlers["agent.workflow.node.test.execute"](payload, context))
        denials.append((error.value.code, error.value.message, error.value.details))
    assert denials == [
        ("resource_not_found", "Agent canvas resource was not found", {}),
        ("resource_not_found", "Agent canvas resource was not found", {}),
    ]


def test_production_timeout_terminates_resource_worker_and_repeated_timeouts_do_not_grow_workers(tmp_path):
    marker = tmp_path / "late-resource-load.txt"
    runtime = ProductionAgentCanvasRuntime(worker_target=_slow_marker_worker, worker_timeout=0.02)
    before = {child.pid for child in multiprocessing.active_children()}

    for _ in range(3):
        with pytest.raises(CapabilityBusinessError) as error:
            asyncio.run(runtime.test_node(
                NodeTestRequest(str(marker), "node-1"), RunPrincipal("actor-1", "team-1"),
            ))
        assert error.value.code == "runtime_timeout"

    time.sleep(0.3)
    assert not marker.exists()
    assert {child.pid for child in multiprocessing.active_children()} <= before


def test_application_timeout_cancellation_also_terminates_spawned_worker(tmp_path):
    from plugins.agent.agent_backend.application.service import AgentApplication

    marker = tmp_path / "cancelled-resource-load.txt"
    runtime = ProductionAgentCanvasRuntime(worker_target=_slow_marker_worker, worker_timeout=5.0)
    before = {child.pid for child in multiprocessing.active_children()}

    class Context:
        user_gid = "actor-1"
        team_gid = "team-1"

    async def run():
        app = AgentApplication(object(), canvas_runtime=runtime, canvas_query_timeout=0.02)
        with pytest.raises(CapabilityBusinessError) as error:
            await app.invoke(
                "agent.workflow.node.test.execute",
                {"flow_gid": str(marker), "node_id": "node-1", "input_values": []},
                Context(),
            )
        assert error.value.code == "runtime_timeout"

    asyncio.run(run())
    time.sleep(0.3)
    assert not marker.exists()
    assert {child.pid for child in multiprocessing.active_children()} <= before


def test_production_adapter_caps_spawned_query_concurrency():
    runtime = ProductionAgentCanvasRuntime(max_concurrency=2)
    active = 0
    maximum = 0

    async def fake_process(_operation, _request, _principal):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.01)
            return {"status": "completed", "output_values": [], "summary": "ok"}
        finally:
            active -= 1

    runtime._run_process = fake_process

    async def run():
        await asyncio.gather(*(
            runtime.test_node(
                NodeTestRequest("flow-1", "node-1"), RunPrincipal("actor-1", "team-1"),
            )
            for _ in range(6)
        ))

    asyncio.run(run())
    assert maximum == 2
