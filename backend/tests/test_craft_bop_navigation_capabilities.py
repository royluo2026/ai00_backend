from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities import bop_navigation


def _context() -> CapabilityContext:
    return CapabilityContext(user_gid="user1", team_gid="team1")


def _registrations():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    return {(item.spec.id, item.spec.version): item for item in registry.snapshot()}


def test_navigation_descriptors_are_closed_versioned_and_resource_bounded():
    registrations = _registrations()
    expected = {
        ("craft.bop.structure.outline.get", 1): (512 * 1024, 100, 1, 8),
        ("craft.bop.work_package.get", 2): (1024 * 1024, 200, 1, 4),
        ("craft.bop.entry.detail.get", 1): (512 * 1024, None, 4, 16),
    }

    for key, limits in expected.items():
        registration = registrations[key]
        descriptor = registration.descriptor
        assert descriptor.owner_domain == "craft"
        assert descriptor.exposure.web and descriptor.exposure.plugin and descriptor.exposure.agent
        assert descriptor.resource_selectors[0].resource_type == "craft-bop-version"
        assert descriptor.resource_selectors[0].payload_path == "version_gid"
        assert descriptor.input_schema["additionalProperties"] is False
        assert descriptor.output_schema["additionalProperties"] is False
        assert (
            descriptor.execution_budget.max_output_bytes,
            descriptor.execution_budget.max_page_size,
            descriptor.execution_budget.max_parallel_per_consumer,
            descriptor.execution_budget.max_parallel_per_tenant,
        ) == limits

    assert registrations[("craft.bop.work_package.get", 1)].spec.version == 1
    assert registrations[("craft.bop.work_package.get", 2)].spec.input_schema != registrations[
        ("craft.bop.work_package.get", 1)
    ].spec.input_schema


def test_navigation_handlers_delegate_exact_bounded_arguments(monkeypatch):
    calls = []
    repository = SimpleNamespace(
        get_outline_page=lambda *args, **kwargs: calls.append(("outline", args, kwargs)) or {
            "version_gid": "v1", "revision": 3, "root": None, "lines": [],
            "total_lines": 0, "next_cursor": None,
        },
        get_work_package_page=lambda *args, **kwargs: calls.append(("work", args, kwargs)) or {
            "version_gid": "v1", "revision": 3, "scope": {"kind": "line", "gid": "l1"},
            "nodes": [], "links": [], "total_count": 0, "next_cursor": None,
        },
        get_entry_detail=lambda *args, **kwargs: calls.append(("detail", args, kwargs)) or {
            "version_gid": "v1", "revision": 3, "entry": {"gid": "e1"}, "links": [],
        },
    )
    monkeypatch.setattr(bop_navigation, "repository", repository)

    assert bop_navigation.get_outline({"version_gid": "v1", "revision": 3}, _context()).data["lines"] == []
    assert bop_navigation.get_work_package_page({
        "version_gid": "v1", "revision": 3, "scope_kind": "line", "scope_gid": "l1",
        "page_size": 25,
    }, _context()).data["nodes"] == []
    assert bop_navigation.get_entry_detail({
        "version_gid": "v1", "revision": 3, "entry_gid": "e1",
    }, _context()).data["entry"]["gid"] == "e1"

    assert calls == [
        ("outline", ("v1", 3), {"cursor": None, "page_size": 50}),
        ("work", ("v1", 3, "line", "l1"), {"cursor": None, "page_size": 25}),
        ("detail", ("v1", 3, "e1"), {}),
    ]


@pytest.mark.parametrize(
    ("handler", "payload"),
    [
        ("get_outline", {"version_gid": "v1", "revision": 3, "page_size": 101}),
        ("get_work_package_page", {
            "version_gid": "v1", "revision": 3, "scope_kind": "role", "scope_gid": "r1",
        }),
        ("get_entry_detail", {"version_gid": "v1", "revision": 3, "entry_gid": ""}),
    ],
)
def test_navigation_handlers_reject_invalid_contract_inputs(handler, payload):
    with pytest.raises(ValueError):
        getattr(bop_navigation, handler)(payload, _context())
