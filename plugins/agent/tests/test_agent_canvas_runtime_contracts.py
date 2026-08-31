import asyncio
import importlib
import importlib.util
import inspect

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.agent.agent_backend.application.service import AgentApplication
from plugins.agent.agent_backend.capabilities.descriptors import specs
from plugins.agent.agent_backend.capabilities.provider import descriptor_for
from plugins.agent.agent_backend.capabilities import register_capabilities


CAPABILITIES = {
    "agent.workflow.node.test.execute": ("write", "user", "agent.write"),
    "agent.canvas.options.resolve": ("read", "none", "agent.read"),
    "agent.canvas.execution.start": ("write", "user", "agent.write"),
    "agent.canvas.execution.resume": ("write", "user", "agent.write"),
}
FORBIDDEN_FIELDS = {
    "auth_token", "credential", "credentials", "env", "environment",
    "import_path", "source", "tool_name", "canvas", "graph", "nodes",
}


def _walk_property_names(schema):
    names = set(schema.get("properties", ()))
    for child in schema.values():
        if isinstance(child, dict):
            names.update(_walk_property_names(child))
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    names.update(_walk_property_names(item))
    return names


def test_runtime_contract_module_defines_the_four_finite_typed_operations():
    spec = importlib.util.find_spec(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    assert spec is not None, "Agent canvas runtime port is missing"
    module = importlib.import_module(spec.name)

    for name in ("test_node", "resolve_options", "start", "resume"):
        method = getattr(module.AgentCanvasRuntime, name)
        assert inspect.iscoroutinefunction(method)
        assert list(inspect.signature(method).parameters) == ["self", "request", "principal"]
    principal = module.RunPrincipal(actor_gid="actor-1", team_gid="team-1")
    assert principal.actor_gid == "actor-1"
    with pytest.raises(ValueError, match="actor_gid"):
        module.RunPrincipal(actor_gid="", team_gid="team-1")
    with pytest.raises(ValueError, match="team_gid"):
        module.RunPrincipal(actor_gid="actor-1", team_gid="")


def test_request_dataclasses_are_bounded_and_reject_legacy_executable_payloads():
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    value = module.InputValue(name="project_gid", value="project-1")
    request = module.NodeTestRequest(
        flow_gid="flow-1", node_id="node-1", input_values=(value,)
    )
    assert request.input_values == (value,)
    multi = module.InputValue.from_payload({"name": "line_gids", "value": ["line-1", "line-2"]})
    assert multi.value == ("line-1", "line-2")
    with pytest.raises(TypeError):
        module.NodeTestRequest(
            flow_gid="flow-1", node_id="node-1", input_values=(), tool_name="x"
        )
    with pytest.raises(ValueError, match="at most"):
        module.CanvasStartRequest(
            skill_gid="skill-1", expected_revision=1,
            input_values=tuple(module.InputValue(name=f"v{i}", value=i) for i in range(65)),
        )
    with pytest.raises(ValueError, match="4096"):
        module.InputValue(name="text", value="x" * 4097)


def test_result_dataclasses_bound_runtime_projection():
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    with pytest.raises(ValueError, match="4096"):
        module.OutputValue(name="text", value="x" * 4097)
    with pytest.raises(ValueError, match="128"):
        module.NodeTestResult(
            status="completed",
            output_values=tuple(module.OutputValue(name=f"v{i}", value=i) for i in range(129)),
        )
    with pytest.raises(ValueError, match="200"):
        module.CanvasOptionsResult(
            revision=1,
            options=tuple(module.CanvasOption(value=str(i), label=str(i)) for i in range(201)),
        )
    with pytest.raises(ValueError, match="pause_token"):
        module.RuntimeDispatch(status="paused", run_token="run-1", revision=1)


def test_capability_contracts_are_exact_closed_and_bounded():
    from plugins.agent.agent_backend.capabilities.contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS

    expected_inputs = {
        "agent.workflow.node.test.execute": {"flow_gid", "node_id", "input_values"},
        "agent.canvas.options.resolve": {"skill_gid", "node_id", "field_key", "input_values"},
        "agent.canvas.execution.start": {"skill_gid", "expected_revision", "input_values"},
        "agent.canvas.execution.resume": {
            "run_token", "pause_token", "expected_revision", "approved", "input_values",
        },
    }
    for capability_id, properties in expected_inputs.items():
        input_schema = INPUT_SCHEMAS[capability_id]
        output_schema = OUTPUT_SCHEMAS[capability_id]
        assert input_schema["additionalProperties"] is False
        assert output_schema["additionalProperties"] is False
        assert set(input_schema["properties"]) == properties
        assert not (_walk_property_names(input_schema) & FORBIDDEN_FIELDS)
        assert input_schema["properties"]["input_values"]["maxItems"] == 64


def test_descriptors_publish_v1_with_exact_sync_and_write_policies():
    selected = {spec.id: spec for spec in specs() if spec.id in CAPABILITIES}
    assert set(selected) == set(CAPABILITIES)
    for capability_id, (risk, confirmation, permission) in CAPABILITIES.items():
        spec = selected[capability_id]
        descriptor = descriptor_for(spec)
        assert spec.risk.value == risk
        assert spec.confirmation == confirmation
        assert spec.permissions == (permission,)
        assert descriptor.major_version == 1
        assert descriptor.lifecycle_status == "stable"
        if capability_id.endswith((".start", ".resume")):
            assert descriptor.execution_mode == "cloud_async"
            assert descriptor.operation_policy == "required"
            assert descriptor.idempotency_policy == "required"
        else:
            assert descriptor.execution_mode == "cloud_sync"
            assert descriptor.operation_policy == "none"
            assert descriptor.idempotency_policy == "none"


def test_application_fails_closed_without_canvas_runtime_adapter():
    class Context:
        user_gid = "actor-1"
        team_gid = "team-1"

    app = AgentApplication(repository=object(), canvas_runtime=None)
    with pytest.raises(CapabilityBusinessError) as error:
        result = app.invoke(
            "agent.canvas.execution.start",
            {"skill_gid": "skill-1", "expected_revision": 1, "input_values": []},
            Context(),
        )
        if hasattr(result, "__await__"):
            asyncio.run(result)
    assert error.value.code == "provider_unavailable"


def test_provider_composition_rejects_an_adapter_without_the_finite_runtime_port():
    class Registry:
        def register(self, *_args, **_kwargs):
            pass

    with pytest.raises(RuntimeError, match="canvas runtime adapter"):
        register_capabilities(Registry(), canvas_runtime=object())
