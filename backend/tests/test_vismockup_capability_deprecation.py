from backend.capabilities.registry_next import CapabilityRegistry
from plugins.device.device_backend.capabilities import register_capabilities


DIRECT_VISMOCKUP_IDS = {
    "vismockup.status",
    "vismockup.launch",
    "vismockup.model.open",
    "vismockup.tree",
    "vismockup.highlight",
    "vismockup.visibility",
    "vismockup.capture",
}


def _registrations():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    return {item.spec.id: item for item in registry.snapshot()}


def test_direct_vismockup_capabilities_are_local_runtime_compatibility_only():
    registrations = _registrations()
    for capability_id in DIRECT_VISMOCKUP_IDS:
        descriptor = registrations[capability_id].descriptor
        assert descriptor.lifecycle_status.value == "deprecated"
        assert descriptor.exposure.local_runtime is True
        assert descriptor.exposure.web is False
        assert descriptor.exposure.api is False
        assert descriptor.exposure.plugin is False
        assert descriptor.exposure.agent is False
        assert descriptor.exposure.mcp is False


def test_deprecation_names_governed_simulation_replacement():
    registrations = _registrations()
    assert "simulation.capture_run.start" in registrations["vismockup.capture"].descriptor.deprecation_message
    for capability_id in DIRECT_VISMOCKUP_IDS - {"vismockup.capture"}:
        assert "simulation.environment.materialize" in registrations[capability_id].descriptor.deprecation_message
