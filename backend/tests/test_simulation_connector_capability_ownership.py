from __future__ import annotations

import json
from pathlib import Path

from backend.capabilities.registry_next import CapabilityRegistry
from plugins.device.device_backend.capabilities import (
    register_capabilities as register_device_capabilities,
)
from plugins.simulation.simulation_backend.capabilities import (
    register_capabilities as register_simulation_capabilities,
)
from plugins.simulation.simulation_backend.data import connector_repository
from plugins.simulation.simulation_backend.data.connector_repository import (
    SimulationConnectorRepository,
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
    "simulation.connector.pairing.bootstrap.create",
    "simulation.connector.pairing.bootstrap.get",
    "simulation.connector.pairing.summary.get",
    "simulation.connector.pairing.approve",
    "simulation.connector.pairing.complete",
    "simulation.connector.pairing.activate",
    "simulation.connector.pairing.cancel",
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


def test_connector_pairing_uses_the_simulation_domain_permission() -> None:
    registry = CapabilityRegistry()
    register_simulation_capabilities(registry)

    pairing = {
        item.spec.id: item.spec
        for item in registry.snapshot()
        if item.spec.id.startswith("simulation.connector.pairing.")
        or item.spec.id == "simulation.connector.binding.get"
    }

    assert set(pairing) == {
        "simulation.connector.pairing.request",
        "simulation.connector.pairing.bootstrap.create",
        "simulation.connector.pairing.bootstrap.get",
        "simulation.connector.pairing.summary.get",
        "simulation.connector.pairing.approve",
        "simulation.connector.pairing.complete",
        "simulation.connector.pairing.activate",
        "simulation.connector.pairing.cancel",
        "simulation.connector.binding.get",
    }
    assert {spec.permissions for spec in pairing.values()} == {("simulation.use",)}


def test_bootstrap_is_web_only_and_activation_is_local_runtime_only() -> None:
    registry = CapabilityRegistry()
    register_simulation_capabilities(registry)
    registrations = {item.spec.id: item for item in registry.snapshot()}

    for capability_id in {
        "simulation.connector.pairing.bootstrap.create",
        "simulation.connector.pairing.bootstrap.get",
        "simulation.connector.pairing.cancel",
    }:
        assert registrations[capability_id].descriptor.exposure.model_dump() == {
            "web": True, "api": False, "plugin": False, "agent": False,
            "mcp": False, "local_runtime": False, "worker": False,
        }
    assert registrations["simulation.connector.pairing.activate"].descriptor.exposure.model_dump() == {
        "web": False, "api": False, "plugin": False, "agent": False,
        "mcp": False, "local_runtime": True, "worker": False,
    }


def test_checked_in_catalog_exposes_the_complete_connector_onboarding_contract() -> None:
    release_path = Path(__file__).resolve().parents[2] / "docs/governance/capability-catalog-release.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    descriptors = {
        item["id"]: item
        for item in release["descriptors"]
        if item["id"].startswith("simulation.connector.pairing.")
        or item["id"] == "simulation.connector.binding.get"
    }

    assert set(descriptors) == {
        "simulation.connector.pairing.request",
        "simulation.connector.pairing.bootstrap.create",
        "simulation.connector.pairing.bootstrap.get",
        "simulation.connector.pairing.summary.get",
        "simulation.connector.pairing.approve",
        "simulation.connector.pairing.complete",
        "simulation.connector.pairing.activate",
        "simulation.connector.pairing.cancel",
        "simulation.connector.binding.get",
    }
    assert "activation_challenge" in descriptors[
        "simulation.connector.pairing.complete"
    ]["output_schema"]["required"]
    assert descriptors["simulation.connector.pairing.activate"]["exposure"] == {
        "web": False, "api": False, "plugin": False, "agent": False,
        "mcp": False, "local_runtime": True, "worker": False,
    }


def test_connector_selection_requires_owned_activated_binding(monkeypatch) -> None:
    class Cursor:
        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchone(self):
            connector_id, user_gid, team_gid = self.params
            is_selectable = (
                connector_id == "connector-offline"
                and user_gid == "user-1"
                and team_gid == "team-1"
                and "status IN ('offline','online')" in self.query
            )
            return {"connector_id": connector_id} if is_selectable else None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(connector_repository, "get_simulation_conn", Connection)
    repository = SimulationConnectorRepository()

    assert repository.can_use_connector("connector-offline", user_gid="user-1", team_gid="team-1")
    assert not repository.can_use_connector("connector-pending", user_gid="user-1", team_gid="team-1")
    assert not repository.can_use_connector("connector-offline", user_gid="user-2", team_gid="team-1")


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
