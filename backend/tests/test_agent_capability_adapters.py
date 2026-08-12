from types import SimpleNamespace

import pytest

from backend.capability_v2.contracts import CorrelationRef
from plugins.agent.agent_backend.ai_assistant.catalog_tools import CatalogToolRegistry, tool_name_for


@pytest.mark.anyio
async def test_catalog_agent_adapter_preserves_gateway_result_and_evidence():
    expected = {"data": {"nodes": []}, "evidence": [{"reference": "craft://bop/v1"}]}

    class Client:
        async def invoke(self, invocation, identity, correlation):
            assert invocation.capability_id == "craft.bop.execution_structure.get"
            return expected

    descriptor = SimpleNamespace(
        id="craft.bop.execution_structure.get", major_version=1, description="read bop",
        input_schema={}, output_schema={}, agent_output_schema=None,
        side_effect_level=SimpleNamespace(value="read"), automation_level=SimpleNamespace(value="A2"),
        confirmation_policy="none", exposure=SimpleNamespace(agent=True),
    )
    registry = CatalogToolRegistry(SimpleNamespace(descriptors=(descriptor,)), client=Client())
    result = await registry.execute(
        tool_name_for(descriptor.id, 1), {"version_gid": "v1"},
        identity=object(), correlation=CorrelationRef(request_id="req_1"),
    )
    assert result is expected
    assert result["evidence"][0]["reference"] == "craft://bop/v1"
