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

    assert result["capability_id"] == "base.capability_registry.search"
    assert result["status"] == "completed"
    assert result["items"][0] == {
        "capability_id": "base.example.0", "capability_version_gid": "0",
    }
    assert len(result["items"]) == 200


def test_provider_drops_undeclared_service_response_fields():
    class Service:
        def base_capability_registry_search(self, payload, context):
            return {
                "capability_id": "base.capability_registry.search",
                "status": "completed",
                "items": (SimpleNamespace(capability_id="base.safe", capability_version_gid=17),),
                "secret": "must-not-cross-transport",
            }

    class Registry:
        def register(self, spec, handler, *, descriptor=None):
            if spec.id == "base.capability_registry.search":
                self.handler = handler

    registry = Registry()
    register_governance_capabilities(registry, Service())

    assert registry.handler({"query": "safe"}, _context()) == {
        "capability_id": "base.capability_registry.search",
        "status": "completed",
        "items": [{"capability_id": "base.safe", "capability_version_gid": "17"}],
    }


def test_provider_preserves_the_declared_bounded_response_envelope():
    """Removing an envelope field below would discard a service result."""
    from backend.capabilities.registry_next import CapabilityRegistry

    class Service:
        def base_capability_registry_search(self, payload, context):
            return {
                "capability_id": "base.capability_registry.search",
                "status": "completed",
                "data": {"summary": "one matching capability"},
                "items": ({"capability_id": "base.safe", "capability_version_gid": 17},),
                "nodes": ({"canonical_key": "base.safe"},),
                "findings": ({"code": "governance_check"},),
                "snapshot_gid": 11,
                "run_gid": 12,
                "proposal_gid": 13,
                "waiver_gid": 14,
                "release_report_gid": 15,
                "secret": "must-not-cross-transport",
            }

    registry = CapabilityRegistry()
    register_governance_capabilities(registry, Service())

    result = __import__("asyncio").run(registry.invoke(
        "base.capability_registry.search",
        {"query": "safe"},
        CapabilityContext(user_gid="42", permissions=("system.capability.read",)),
    ))

    assert result.data == {
        "capability_id": "base.capability_registry.search",
        "status": "completed",
        "data": {"summary": "one matching capability"},
        "items": [{"capability_id": "base.safe", "capability_version_gid": "17"}],
        "nodes": [{"canonical_key": "base.safe"}],
        "findings": [{"code": "governance_check"}],
        "snapshot_gid": "11",
        "run_gid": "12",
        "proposal_gid": "13",
        "waiver_gid": "14",
        "release_report_gid": "15",
    }


def test_closed_provider_schema_admits_graph_bounds_required_by_service():
    from backend.capabilities.registry_next import CapabilityRegistry

    registry = CapabilityRegistry()
    register_governance_capabilities(registry, CapabilityGovernanceService(_Store()))

    result = __import__("asyncio").run(registry.invoke(
        "base.capability_graph.get",
        {"target_gid": "100", "max_depth": 4, "max_nodes": 500},
        CapabilityContext(user_gid="42", permissions=("system.capability.read",)),
    ))

    assert result.data == {
        "capability_id": "base.capability_graph.get", "status": "completed",
        "snapshot_gid": "100", "snapshot": {"snapshot_gid": "100"},
        "max_depth": 4, "max_nodes": 500, "nodes": [],
    }


def test_unconfigured_provider_fails_closed_instead_of_returning_empty_results():
    from backend.capabilities.registry_next import CapabilityRegistry

    registry = CapabilityRegistry()
    register_governance_capabilities(registry)

    with pytest.raises(CapabilityBusinessError, match="provider_unavailable"):
        registry.get("base.capability_registry.search").handler({"query": "example"}, _context())
