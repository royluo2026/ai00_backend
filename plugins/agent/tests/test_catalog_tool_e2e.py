import asyncio
from datetime import UTC, datetime

import pytest

from backend.capability_v2.catalog import load_catalog_release
from backend.capability_v2.contracts import ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, CorrelationRef, TenantIdentity
from plugins.agent.agent_backend.ai_assistant.catalog_tools import CatalogToolRegistry, tool_name_for
from plugins.agent.agent_backend.ai_assistant import tool_executor, tool_registry


def test_tool_name_is_deterministic_and_bounded():
    assert tool_name_for("craft.bop.version.get", 1) == "cap__craft__bop__version__get__v1"
    with pytest.raises(ValueError, match="128"):
        tool_name_for("x." + "y" * 130, 1)


def test_agent_tools_equal_pinned_catalog_exposure():
    release = load_catalog_release(open("docs/governance/capability-catalog-release.json", encoding="utf-8").read())
    registry = CatalogToolRegistry(release)
    expected = {tool_name_for(item.id, item.major_version) for item in release.descriptors if item.exposure.agent}
    assert set(registry.names()) == expected
    assert all(tool.capability_id for tool in registry.tools())


def test_catalog_tool_executes_stored_reverse_mapping_through_domain_client():
    calls = []
    class Client:
        async def invoke(self, invocation, identity, correlation, deadline=None):
            calls.append((invocation, identity, correlation)); return {"status": "succeeded"}
    release = load_catalog_release(open("docs/governance/capability-catalog-release.json", encoding="utf-8").read())
    registry = CatalogToolRegistry(release, client=Client())
    tool = next(item for item in registry.tools() if item.capability_id == "system.search")
    identity = ConsumerIdentity(
        actor=ActorIdentity(service_id="agent-runtime", authentication_method="service-token", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="tenant-1", membership="service"),
        consumer=ConsumerDescriptor(type=ConsumerType.AGENT, consumer_id="domain.agent", agent_run_id="run-1"),
    )
    asyncio.run(registry.execute(tool.name, {}, identity=identity, correlation=CorrelationRef(request_id="r1", trace_id="t1")))
    invocation, _, _ = calls[-1]
    assert invocation.capability_id == "system.search"
    assert invocation.major_version == 1


def test_runtime_registry_and_executor_use_catalog_records_without_name_inference():
    release = load_catalog_release(open("docs/governance/capability-catalog-release.json", encoding="utf-8").read())
    registry = tool_registry.build_catalog_tool_registry(release)
    definitions = tool_registry.catalog_tools_openai(registry)
    assert {item["function"]["name"] for item in definitions} == set(registry.names())
    assert hasattr(tool_executor, "execute_catalog_tool")
