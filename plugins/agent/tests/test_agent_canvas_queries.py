import asyncio
import importlib
import json

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.agent.agent_backend.application.canvas_runtime import (
    CanvasOptionsRequest,
    CanvasResumeRequest,
    CanvasStartRequest,
    InputValue,
    NodeTestRequest,
    RunPrincipal,
)
from plugins.agent.agent_backend.application.service import AgentApplication


ProductionAgentCanvasRuntime = getattr(
    importlib.import_module("plugins.agent.agent_backend.application.canvas_runtime"),
    "ProductionAgentCanvasRuntime",
    None,
)
PRINCIPAL = RunPrincipal("actor-1", "team-1")


def test_production_query_adapter_exists():
    assert ProductionAgentCanvasRuntime is not None


def _flow(*, owner="actor-1", team="team-1", nodes=None):
    return {
        "gid": "flow-1",
        "owner_user_gid": owner,
        "team_gid": team,
        "flowdef": json.dumps({
            "nodes": nodes or [{
                "id": "node-1", "type": "list", "label": "Read list",
                "inputs_schema": {"project_gid": {"type": "string"}},
                "config": {"fixed": "persisted"},
            }],
            "edges": [],
        }),
    }


def _skill(*, owner="team-1", team="team-1", scope="team", options=None):
    return {
        "gid": "skill-1", "owner_gid": owner, "team_gid": team,
        "scope": scope, "status": "active", "revision": 7,
        "content": {
            "nodes": [{
                "id": "human-1", "type": "human",
                "inputs_schema": {"line_gid": {"type": "string"}},
                "params": {"collect_fields": [{
                    "key": "project_gid", "options": options or [
                        {"value": "p2", "label": "Zulu"},
                        {"value": "p1", "label": "alpha"},
                    ],
                }]},
            }],
            "connections": [],
        },
    }


class Executor:
    calls = []
    result = {
        "status": "completed",
        "node_results": {
            "node-1": {
                "_status": "ok",
                "_summary": "Bearer abc.def",
                "count": 2,
                "nested": {
                    "api_token": "raw-secret", "note": "token=raw-secret",
                    "source_tool": "internal.dynamic",
                },
                "tool_name": "persisted-internal-control",
            },
        },
    }

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def execute(self, canvas, init_params=None):
        self.__class__.calls.append((self.kwargs, canvas, init_params))
        return self.__class__.result


def _runtime(records, **kwargs):
    return ProductionAgentCanvasRuntime(
        resource_loader=lambda kind, gid: records.get((kind, gid)),
        executor_factory=Executor,
        **kwargs,
    )


def test_same_team_node_query_executes_only_persisted_node_and_returns_closed_redacted_output():
    Executor.calls = []
    runtime = _runtime({("flow", "flow-1"): _flow()})

    result = asyncio.run(runtime.test_node(
        NodeTestRequest("flow-1", "node-1", (InputValue("project_gid", "p1"),)),
        PRINCIPAL,
    ))

    assert result.status == "completed"
    assert result.summary == "Bearer [redacted]"
    assert [(item.name, item.value) for item in result.output_values] == [
        ("count", 2),
        ("nested", '{"api_token":"[redacted]","note":"[redacted-credential]","source_tool":"[redacted]"}'),
        ("tool_name", "[redacted]"),
    ]
    kwargs, canvas, init_params = Executor.calls.pop()
    assert kwargs == {"auth_mode": "feishu", "auth_token": "", "owner_gid": "actor-1"}
    assert canvas == {"nodes": [{
        "id": "node-1", "type": "list", "label": "Read list",
        "params": {"fixed": "persisted"},
    }]}
    assert init_params == {"project_gid": "p1"}


def test_same_team_options_are_loaded_from_persisted_field_sorted_and_redacted():
    runtime = _runtime({("skill", "skill-1"): _skill(options=[
        {"value": "token=secret", "label": "Zulu", "password": "ignored"},
        {"value": "p1", "label": "alpha"},
        {"value": "p0", "label": "Alpha"},
    ])})

    result = asyncio.run(runtime.resolve_options(
        CanvasOptionsRequest("skill-1", "human-1", "project_gid"), PRINCIPAL
    ))

    assert result.revision == 7
    assert [(item.value, item.label) for item in result.options] == [
        ("p0", "Alpha"), ("p1", "alpha"), ("[redacted-credential]", "Zulu"),
    ]


@pytest.mark.parametrize("kind,query,record", [
    ("flow", NodeTestRequest("flow-1", "node-1"), _flow(team="team-2")),
    ("skill", CanvasOptionsRequest("skill-1", "human-1", "project_gid"), _skill(owner="team-2", team="team-2")),
    ("flow", NodeTestRequest("missing", "node-1"), None),
    ("skill", CanvasOptionsRequest("missing", "human-1", "project_gid"), None),
])
def test_cross_team_and_missing_resources_have_one_uniform_denial(kind, query, record):
    records = {(kind, query.flow_gid if kind == "flow" else query.skill_gid): record} if record else {}
    runtime = _runtime(records)

    with pytest.raises(CapabilityBusinessError) as error:
        asyncio.run(runtime.test_node(query, PRINCIPAL) if kind == "flow" else runtime.resolve_options(query, PRINCIPAL))

    assert (error.value.code, error.value.message, error.value.details) == (
        "resource_not_found", "Agent canvas resource was not found", {},
    )


def test_query_capability_fails_closed_when_adapter_is_absent():
    class Context:
        user_gid = "actor-1"
        team_gid = "team-1"

    with pytest.raises(CapabilityBusinessError) as error:
        AgentApplication(object()).invoke(
            "agent.workflow.node.test.execute",
            {"flow_gid": "flow-1", "node_id": "node-1", "input_values": []},
            Context(),
        )
    assert error.value.code == "provider_unavailable"


def test_application_timeout_cancels_runtime_work_without_leaving_an_orphan():
    cancelled = asyncio.Event()

    class Runtime:
        async def test_node(self, _request, _principal):
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

    class Context:
        user_gid = "actor-1"
        team_gid = "team-1"

    async def run():
        app = AgentApplication(object(), canvas_runtime=Runtime(), canvas_query_timeout=0.01)
        with pytest.raises(CapabilityBusinessError) as error:
            await app.invoke(
                "agent.workflow.node.test.execute",
                {"flow_gid": "flow-1", "node_id": "node-1", "input_values": []},
                Context(),
            )
        assert error.value.code == "runtime_timeout"
        assert error.value.retryable is True
        await asyncio.wait_for(cancelled.wait(), 0.1)
        current = asyncio.current_task()
        assert not [task for task in asyncio.all_tasks() if task is not current and not task.done()]

    asyncio.run(run())


def test_graph_input_and_output_caps_apply_before_and_after_execution():
    calls = []

    class CountingExecutor(Executor):
        def execute(self, canvas, init_params=None):
            calls.append(canvas)
            return self.result

    oversized_graph = _flow(nodes=[{"id": f"n{i}", "type": "list"} for i in range(129)])
    runtime = ProductionAgentCanvasRuntime(
        resource_loader=lambda kind, gid: oversized_graph,
        executor_factory=CountingExecutor,
    )
    with pytest.raises(CapabilityBusinessError, match="graph") as graph_error:
        asyncio.run(runtime.test_node(NodeTestRequest("flow-1", "n0"), PRINCIPAL))
    assert graph_error.value.code == "invalid_input"
    assert calls == []

    declared = {f"v{i}": {} for i in range(17)}
    flow = _flow(nodes=[{"id": "node-1", "type": "list", "inputs_schema": declared}])
    runtime = ProductionAgentCanvasRuntime(
        resource_loader=lambda kind, gid: flow,
        executor_factory=CountingExecutor,
    )
    values = tuple(InputValue(f"v{i}", "x" * 4096) for i in range(17))
    with pytest.raises(CapabilityBusinessError, match="input") as input_error:
        asyncio.run(runtime.test_node(NodeTestRequest("flow-1", "node-1", values), PRINCIPAL))
    assert input_error.value.code == "invalid_input"
    assert calls == []

    CountingExecutor.result = {
        "status": "completed",
        "node_results": {"node-1": {"_status": "ok", "_summary": "ok", "blob": "x" * 70_000}},
    }
    runtime = ProductionAgentCanvasRuntime(
        resource_loader=lambda kind, gid: _flow(),
        executor_factory=CountingExecutor,
    )
    with pytest.raises(CapabilityBusinessError, match="output") as output_error:
        asyncio.run(runtime.test_node(NodeTestRequest("flow-1", "node-1"), PRINCIPAL))
    assert output_error.value.code == "invalid_input"


def test_undeclared_input_and_disallowed_node_kind_never_reach_executor():
    Executor.calls = []
    runtime = _runtime({("flow", "flow-1"): _flow()})
    with pytest.raises(CapabilityBusinessError, match="declared") as undeclared:
        asyncio.run(runtime.test_node(
            NodeTestRequest("flow-1", "node-1", (InputValue("other_gid", "x"),)), PRINCIPAL
        ))
    assert undeclared.value.code == "invalid_input"

    condition = _flow(nodes=[{"id": "node-1", "type": "condition", "config": {"condition_expr": "1 == 1"}}])
    runtime = _runtime({("flow", "flow-1"): condition})
    with pytest.raises(CapabilityBusinessError, match="node kind") as node_kind:
        asyncio.run(runtime.test_node(NodeTestRequest("flow-1", "node-1"), PRINCIPAL))
    assert node_kind.value.code == "invalid_input"
    assert Executor.calls == []


def test_runtime_never_exceeds_its_concurrency_cap():
    active = 0
    maximum = 0

    class AsyncExecutor(Executor):
        async def execute(self, canvas, init_params=None):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            try:
                await asyncio.sleep(0.01)
                return {"status": "completed", "node_results": {"node-1": {"_status": "ok"}}}
            finally:
                active -= 1

    runtime = ProductionAgentCanvasRuntime(
        resource_loader=lambda kind, gid: _flow(),
        executor_factory=AsyncExecutor,
        max_concurrency=2,
    )

    async def run():
        await asyncio.gather(*(
            runtime.test_node(NodeTestRequest("flow-1", "node-1"), PRINCIPAL)
            for _ in range(6)
        ))

    asyncio.run(run())
    assert maximum == 2


def test_option_collection_is_bounded_before_projection():
    runtime = _runtime({("skill", "skill-1"): _skill(options=[
        {"value": str(i), "label": str(i)} for i in range(201)
    ])})

    with pytest.raises(CapabilityBusinessError, match="options") as error:
        asyncio.run(runtime.resolve_options(
            CanvasOptionsRequest("skill-1", "human-1", "project_gid"), PRINCIPAL
        ))
    assert error.value.code == "invalid_input"


def test_dynamic_option_tool_configuration_is_never_executed():
    skill = _skill()
    skill["content"]["nodes"][0]["params"]["collect_fields"][0]["source_tool"] = "project.list"
    runtime = _runtime({("skill", "skill-1"): skill})

    with pytest.raises(CapabilityBusinessError, match="executable resolver") as error:
        asyncio.run(runtime.resolve_options(
            CanvasOptionsRequest("skill-1", "human-1", "project_gid"), PRINCIPAL
        ))
    assert error.value.code == "invalid_input"


def test_option_inputs_must_be_declared_by_the_persisted_node_schema():
    runtime = _runtime({("skill", "skill-1"): _skill()})

    with pytest.raises(CapabilityBusinessError, match="declared") as error:
        asyncio.run(runtime.resolve_options(
            CanvasOptionsRequest(
                "skill-1", "human-1", "project_gid",
                (InputValue("other_gid", "outside-schema"),),
            ),
            PRINCIPAL,
        ))
    assert error.value.code == "invalid_input"


def test_query_adapter_keeps_unimplemented_durable_commands_fail_closed():
    runtime = _runtime({})
    commands = (
        ("start", CanvasStartRequest("skill-1", 1)),
        ("resume", CanvasResumeRequest("run-1", "pause-1", 1, True)),
    )
    for method, request in commands:
        with pytest.raises(CapabilityBusinessError) as error:
            asyncio.run(getattr(runtime, method)(request, PRINCIPAL))
        assert error.value.code == "provider_unavailable"
        assert error.value.retryable is True
