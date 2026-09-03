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


def test_direct_vismockup_capabilities_are_fail_closed_after_simulation_migration():
    registrations = _registrations()
    for capability_id in DIRECT_VISMOCKUP_IDS:
        descriptor = registrations[capability_id].descriptor
        assert descriptor.lifecycle_status.value == "deprecated"
        assert not any(descriptor.exposure.model_dump().values())


def test_deprecation_names_governed_simulation_replacement():
    registrations = _registrations()
    for capability_id in DIRECT_VISMOCKUP_IDS:
        assert "simulation" in registrations[capability_id].descriptor.deprecation_message.lower()
