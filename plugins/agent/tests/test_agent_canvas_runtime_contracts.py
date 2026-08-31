import asyncio
import importlib
import importlib.util
import inspect
import math

import pytest
from jsonschema import ValidationError, validate

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


def _payloads():
    return {
        "agent.workflow.node.test.execute": {
            "flow_gid": "flow-1", "node_id": "node-1", "input_values": [],
        },
        "agent.canvas.options.resolve": {
            "skill_gid": "skill-1", "node_id": "node-1", "field_key": "project_gid",
            "input_values": [],
        },
        "agent.canvas.execution.start": {
            "skill_gid": "skill-1", "expected_revision": 1, "input_values": [],
        },
        "agent.canvas.execution.resume": {
            "run_token": "run-1", "pause_token": "pause-1", "expected_revision": 2,
            "approved": True, "input_values": [],
        },
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


@pytest.mark.parametrize("name", [
    "auth", "authorization", "auth_token", "Auth-Token", "a.u.t.h_t-o-k-e-n",
    "token", "credential", "credentials", "credentialRef", "password", "passwd",
    "pwd", "secret", "api-key", "access_key", "private-key", "tool", "tool_name",
    "TOOL.NAME", "environment", "environment_id", "env", "source", "source_gid",
    "import", "import_path", "IMPORT-path", "path", "code", "python_code", "script",
    "sql", "rawSQL", "control", "controlFlag", "command", "exec", "executable",
    "pass_word", "canvas", "graph", "nodes",
])
def test_input_value_rejects_semantic_execution_control_aliases(name):
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    from plugins.agent.agent_backend.capabilities.contracts import INPUT_SCHEMAS

    with pytest.raises(ValueError, match="reserved"):
        module.InputValue(name=name, value="blocked")
    with pytest.raises(ValidationError):
        validate(
            {"flow_gid": "flow-1", "node_id": "node-1", "input_values": [{"name": name, "value": "blocked"}]},
            INPUT_SCHEMAS["agent.workflow.node.test.execute"],
        )


@pytest.mark.parametrize("name", [
    "resource_gid", "author_gid", "tooling_notes", "environmental_score",
    "sourcebook_gid", "codebook_gid", "graphical_label", "node_id",
])
def test_input_value_allows_declared_business_names_containing_control_fragments(name):
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    from plugins.agent.agent_backend.capabilities.contracts import INPUT_SCHEMAS

    value = module.InputValue(name=name, value="business-value")
    assert module.validated_init_params((value,), (name,)) == {name: "business-value"}
    assert module.CanvasOptionsRequest(
        skill_gid="skill-1", node_id="node-1", field_key=name,
    ).field_key == name
    validate(
        {"flow_gid": "flow-1", "node_id": "node-1", "input_values": [{"name": name, "value": "business-value"}]},
        INPUT_SCHEMAS["agent.workflow.node.test.execute"],
    )


def test_adapter_helper_allows_only_persisted_declared_inputs():
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    values = (
        module.InputValue(name="project_gid", value="project-1"),
        module.InputValue(name="line_gids", value=("line-1", "line-2")),
    )
    assert module.validated_init_params(values, ("project_gid", "line_gids")) == {
        "project_gid": "project-1", "line_gids": ["line-1", "line-2"],
    }
    with pytest.raises(ValueError, match="not declared"):
        module.validated_init_params(values, ("project_gid",))


@pytest.mark.parametrize("value", [
    math.nan, math.inf, -math.inf, 1_000_000_000_001, -1_000_000_000_001,
    10 ** 1000,
])
def test_numeric_values_are_finite_and_bounded(value):
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    with pytest.raises(ValueError, match="finite numeric domain"):
        module.InputValue(name="quantity", value=value)
    with pytest.raises(ValueError, match="finite numeric domain"):
        module.OutputValue(name="quantity", value=value)


def test_numeric_domain_accepts_exact_boundaries_and_schema_matches():
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    from plugins.agent.agent_backend.capabilities.contracts import INPUT_SCHEMAS

    for value in (-1_000_000_000_000, 1_000_000_000_000):
        item = module.InputValue(name="quantity", value=value)
        validate(
            {"flow_gid": "flow-1", "node_id": "node-1", "input_values": [{"name": item.name, "value": item.value}]},
            INPUT_SCHEMAS["agent.workflow.node.test.execute"],
        )
    with pytest.raises(ValidationError):
        validate(
            {"flow_gid": "flow-1", "node_id": "node-1", "input_values": [{"name": "quantity", "value": 1_000_000_000_001}]},
            INPUT_SCHEMAS["agent.workflow.node.test.execute"],
        )


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


def test_runtime_dispatch_preserves_closed_bounded_safe_pause_projection():
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    result = module.RuntimeDispatch(
        status="paused", run_token="run-1", revision=2, pause_token="pause-1",
        halted_node_id="human-1", halted_label="Approve", skill_title="Skill",
        summary="token=secret-value waiting",
        node_results=(module.NodeResult(
            node_id="read-1", status="ok", summary="Bearer abc.def",
            output_values=(module.OutputValue(name="count", value=3),),
        ),),
        context_summary=(module.ContextSummaryItem(node_id="read-1", text="done"),),
        collect_fields=(module.CollectField(
            key="project_gid", label="Project", type="radio",
            options=(module.CanvasOption(value="p1", label="Project 1"),),
            show_when=(module.VisibilityRule(field_key="project_gid", value="token=secret-value"),),
        ),),
        canvas_layout=module.CanvasLayout(
            column_labels=("Result", "Approval"), column_width=320, lane_height=60,
            hide_lane_labels=True,
        ),
    )
    assert result.status == "paused"
    assert result.summary == "[redacted-credential] waiting"
    assert result.node_results[0].summary == "Bearer [redacted]"
    assert result.collect_fields[0].show_when[0].value == "[redacted-credential]"
    assert module.OutputValue(name="api_token", value="opaque-secret").value == "[redacted]"
    for status in ("accepted", "completed", "halted", "error", "outcome_unknown"):
        assert module.RuntimeDispatch(status=status, run_token="run-1", revision=2).status == status


@pytest.mark.parametrize("field,value", [
    ("column_width", 320.5), ("lane_height", 60.5),
    ("column_width", True), ("lane_height", True),
])
def test_canvas_layout_rejects_non_integer_dimensions_in_dataclass_and_schema(field, value):
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    from plugins.agent.agent_backend.capabilities.contracts import OUTPUT_SCHEMAS

    with pytest.raises(ValueError, match=field):
        module.CanvasLayout(**{field: value})
    layout = {
        "column_labels": [], "column_width": 320, "lane_height": 60,
        "hide_lane_labels": False, field: value,
    }
    result = {
        "status": "accepted", "run_token": "run-1", "revision": 1,
        "pause_token": None, "halted_node_id": None, "halted_label": None,
        "halt_reason": None, "skill_title": None, "summary": "",
        "node_results": [], "context_summary": [], "collect_fields": [],
        "canvas_layout": layout,
    }
    with pytest.raises(ValidationError):
        validate(result, OUTPUT_SCHEMAS["agent.canvas.execution.start"])


@pytest.mark.parametrize("field,values", [
    ("column_width", (120, 1000)), ("lane_height", (40, 500)),
])
def test_canvas_layout_accepts_integer_boundaries(field, values):
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    from plugins.agent.agent_backend.capabilities.contracts import CANVAS_LAYOUT

    for value in values:
        assert getattr(module.CanvasLayout(**{field: value}), field) == value
        layout = {
            "column_labels": [], "column_width": 320, "lane_height": 60,
            "hide_lane_labels": False, field: value,
        }
        validate(layout, CANVAS_LAYOUT)


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


def test_registered_handlers_fail_closed_for_all_four_capabilities_without_adapter():
    class Registry:
        def __init__(self):
            self.handlers = {}

        def register(self, spec, handler, **_kwargs):
            self.handlers[spec.id] = handler

    class Context:
        user_gid = "actor-1"
        team_gid = "team-1"

    registry = Registry()
    register_capabilities(registry, canvas_runtime=None)
    for capability_id, payload in _payloads().items():
        with pytest.raises(CapabilityBusinessError) as error:
            asyncio.run(registry.handlers[capability_id](payload, Context()))
        assert error.value.code == "provider_unavailable"


def test_registered_handlers_propagate_principal_and_serialize_schema_valid_results():
    module = importlib.import_module(
        "plugins.agent.agent_backend.application.canvas_runtime"
    )
    from plugins.agent.agent_backend.capabilities.contracts import OUTPUT_SCHEMAS

    class Runtime:
        def __init__(self):
            self.calls = []

        async def test_node(self, request, principal):
            self.calls.append(("test_node", request, principal))
            return module.NodeTestResult(
                status="completed", output_values=(module.OutputValue("count", 1),), summary="ok"
            )

        async def resolve_options(self, request, principal):
            self.calls.append(("resolve_options", request, principal))
            return module.CanvasOptionsResult(
                revision=1, options=(module.CanvasOption("p1", "Project 1"),)
            )

        async def start(self, request, principal):
            self.calls.append(("start", request, principal))
            return module.RuntimeDispatch(status="accepted", run_token="run-1", revision=1)

        async def resume(self, request, principal):
            self.calls.append(("resume", request, principal))
            return module.RuntimeDispatch(
                status="paused", run_token="run-1", revision=2, pause_token="pause-2",
                halted_node_id="human-2", halted_label="Approve",
                node_results=(module.NodeResult(
                    "read-1", "ok", "done",
                    output_values=(module.OutputValue("api_token", "opaque-secret"),),
                ),),
                context_summary=(module.ContextSummaryItem("read-1", "done"),),
                collect_fields=(module.CollectField("project_gid", "Project", "select"),),
                canvas_layout=module.CanvasLayout(column_width=320, lane_height=60),
            )

    class Registry:
        def __init__(self):
            self.items = {}

        def register(self, spec, handler, *, descriptor=None):
            self.items[spec.id] = (handler, descriptor)

    class Context:
        user_gid = "actor-1"
        team_gid = "team-1"

    runtime = Runtime()
    registry = Registry()
    register_capabilities(registry, canvas_runtime=runtime)
    results = {}
    for capability_id, payload in _payloads().items():
        handler, registered_descriptor = registry.items[capability_id]
        risk, confirmation, permission = CAPABILITIES[capability_id]
        assert registered_descriptor.side_effect_level.value == risk
        assert registered_descriptor.confirmation_policy == confirmation
        assert registered_descriptor.authorization_policy == f"agent.v2:{permission}"
        result = asyncio.run(handler(payload, Context()))["data"]
        validate(result, OUTPUT_SCHEMAS[capability_id])
        results[capability_id] = result

    assert [name for name, _, _ in runtime.calls] == ["test_node", "resolve_options", "start", "resume"]
    assert all(call[2] == module.RunPrincipal("actor-1", "team-1") for call in runtime.calls)
    assert results["agent.canvas.execution.resume"]["status"] == "paused"
    assert results["agent.canvas.execution.resume"]["halted_node_id"] == "human-2"
    assert isinstance(results["agent.canvas.execution.resume"]["node_results"], list)
    assert results["agent.canvas.execution.resume"]["node_results"][0]["output_values"][0]["value"] == "[redacted]"
