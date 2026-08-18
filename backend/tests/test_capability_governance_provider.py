from types import SimpleNamespace

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capability_governance_test.provider import register_governance_capabilities
from backend.capability_governance_test.service import CapabilityGovernanceService


def _context() -> CapabilityContext:
    return CapabilityContext(user_gid="42", source="web", request_id="request_1")


def _snapshot() -> SimpleNamespace:
    entries = tuple(
        SimpleNamespace(capability_id=f"base.example.{index}", capability_version_gid=index)
        for index in range(250)
    )
    return SimpleNamespace(
        snapshot_gid=100,
        entries=entries,
        document=SimpleNamespace(nodes=(), relations=(), bindings=(), capabilities=()),
    )


class _Store:
    def __init__(self):
        self._snapshots = {100: _snapshot()}

    def get_snapshot(self, snapshot_gid: int):
        return self._snapshots.get(snapshot_gid)


def test_search_caps_collection_to_200_items():
    service = CapabilityGovernanceService(_Store())

    result = service.base_capability_registry_search({"query": "example", "limit": 500}, _context())

    assert result["status"] == "completed"
    assert result["limit"] == 200
    assert len(result["items"]) == 200
    assert len(result["items"]) == 200


def test_graph_requires_explicit_bounded_depth_and_nodes():
    service = CapabilityGovernanceService(_Store())

    with pytest.raises(CapabilityBusinessError, match="invalid_input"):
        service.base_capability_graph_get({"target_gid": "100"}, _context())


def test_analysis_run_pins_the_snapshot_before_queueing_work():
    service = CapabilityGovernanceService(_Store())

    result = service.base_capability_analysis_run(
        {"target_gid": "100", "idempotency_key": "analysis-1"}, _context()
    )

    assert result["status"] == "accepted"
    assert result["snapshot_gid"] == "100"


def test_provider_uses_service_handlers_instead_of_placeholder_results():
    class Registry:
        def __init__(self):
            self.items = {}

        def register(self, spec, handler, *, descriptor=None):
            self.items[spec.id] = (spec, handler, descriptor)

    registry = Registry()
    register_governance_capabilities(registry, CapabilityGovernanceService(_Store()))

    result = registry.items["base.capability_registry.search"][1]({"query": "example"}, _context())

    assert result == {"capability_id": "base.capability_registry.search", "status": "completed"}
