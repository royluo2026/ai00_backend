from __future__ import annotations

from backend.capabilities.registry_next import CapabilityRegistry
from plugins.device.device_backend.capabilities import (
    register_capabilities as register_device_capabilities,
)
from plugins.simulation.simulation_backend.capabilities import (
    register_capabilities as register_simulation_capabilities,
)


SIMULATION_CONNECTOR_IDS = {
    "simulation.connector.health.get",
    "simulation.connector.plan.queue",
    "simulation.vismockup.status.get",
    "simulation.vismockup.application.launch",
    "simulation.vismockup.model.open",
    "simulation.vismockup.tree.get",
    "simulation.vismockup.selection.highlight",
    "simulation.vismockup.visibility.change.apply",
    "simulation.vismockup.capture.create",
    "simulation.connector.pairing.request",
    "simulation.connector.pairing.summary.get",
    "simulation.connector.pairing.approve",
    "simulation.connector.pairing.complete",
    "simulation.connector.binding.get",
}

LEGACY_IDS = {
    ("device.connector.health.get", 1),
    ("device.connector.plan.queue", 1),
    ("device.connector.plan.queue", 2),
    ("vismockup.status", 1),
    ("vismockup.launch", 1),
    ("vismockup.model.open", 1),
    ("vismockup.tree", 1),
    ("vismockup.highlight", 1),
    ("vismockup.visibility", 1),
    ("vismockup.capture", 1),
}


def test_connector_and_vismockup_are_owned_only_by_simulation() -> None:
    registry = CapabilityRegistry()
    register_simulation_capabilities(registry)

    registrations = {
        item.spec.id: item
        for item in registry.snapshot()
        if item.spec.id in SIMULATION_CONNECTOR_IDS
    }

    assert set(registrations) == SIMULATION_CONNECTOR_IDS
    assert {item.spec.owner for item in registrations.values()} == {"simulation"}
    assert {
        item.descriptor.owner_domain for item in registrations.values()
    } == {"simulation"}


def test_old_device_connector_ids_are_deprecated_and_fail_closed() -> None:
    registry = CapabilityRegistry()
    register_device_capabilities(registry)

    registrations = {
        (item.spec.id, item.spec.version): item for item in registry.snapshot()
    }
    assert LEGACY_IDS <= set(registrations)
    for key in LEGACY_IDS:
        descriptor = registrations[key].descriptor
        assert descriptor.lifecycle_status.value == "deprecated"
        assert not any(descriptor.exposure.model_dump().values())
