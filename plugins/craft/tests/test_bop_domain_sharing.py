from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.capability_v2.contracts import CapabilityStatus
from plugins.craft.craft_backend.application.bop import BopService
from plugins.craft.craft_backend.domain.bop import InvalidBopHierarchy, validate_six_level_plan


class TraceClient:
    def __init__(self, result): self.result, self.calls = result, []
    async def invoke(self, invocation, identity, correlation, deadline=None):
        self.calls.append((invocation, identity, correlation, deadline)); return self.result


class Bindings:
    def __init__(self): self.items = []
    def bind_factory_resource(self, bop_ref, resource_ref, provider_version):
        self.items.append((bop_ref, resource_ref, provider_version))


def test_bop_binding_uses_gateway():
    result = SimpleNamespace(ok=True, status=CapabilityStatus.COMPLETED, data={"resource_ref": "factory:station:ST-1", "version": 3}, error=None)
    client, bindings = TraceClient(result), Bindings()
    service = BopService(client, bindings)
    identity = SimpleNamespace(consumer=SimpleNamespace(consumer_id="domain:craft"))
    correlation = SimpleNamespace(request_id="req-1")

    bound = asyncio.run(service.bind_factory_resource("bop-1", "factory:station:ST-1", identity, correlation))

    invocation = client.calls[-1][0]
    assert identity.consumer.consumer_id == "domain:craft"
    assert invocation.capability_id == "factory.resource.read"
    assert invocation.payload == {"resource_ref": "factory:station:ST-1"}
    assert bound["provider_version"] == 3


def test_bop_six_level_hierarchy_is_closed():
    validate_six_level_plan(["bop_version", "line_process", "station_process", "work_position", "process", "operation"])
    with pytest.raises(InvalidBopHierarchy):
        validate_six_level_plan(["bop_version", "station_process", "operation"])


def test_bop_binding_maps_authorization_without_provider_details():
    error = SimpleNamespace(code="permission_denied", message="secret provider policy")
    client = TraceClient(SimpleNamespace(ok=False, data=None, error=error))
    service = BopService(client, Bindings())
    with pytest.raises(Exception, match="factory_resource_denied") as exc:
        asyncio.run(service.bind_factory_resource("bop-1", "factory:station:ST-1", object(), object()))
    assert "secret provider policy" not in str(exc.value)


def test_bop_binding_maps_deadline_exceeded():
    class TimeoutClient:
        async def invoke(self, *_args, **_kwargs): raise TimeoutError("socket details")
    service = BopService(TimeoutClient(), Bindings())
    with pytest.raises(Exception, match="factory_resource_timeout"):
        asyncio.run(service.bind_factory_resource("bop-1", "factory:station:ST-1", object(), object()))
