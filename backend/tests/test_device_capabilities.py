"""Native Local Integration provider acceptance tests."""
from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.device.device_backend.capabilities import register_capabilities
from plugins.device.device_backend.capabilities import runtime


def test_local_handlers_bind_command_identity_to_gateway_operation(monkeypatch):
    captured = {}

    def enqueue(capability_id, version, payload, user_gid, ttl_seconds=300, operation_id=None, team_gid=None):
        captured.update(capability_id=capability_id, payload=payload, operation_id=operation_id, team_gid=team_gid)
        return {"command_gid": operation_id, "device_gid": payload["device_id"], "status": "queued", "expires_in": 300}

    monkeypatch.setattr(runtime.control_plane, "enqueue_command", enqueue)
    registry = CapabilityRegistry()
    register_capabilities(registry)
    registration = next(item for item in registry.snapshot() if item.spec.id == "vismockup.visibility")
    output = registration.handler(
        {"device_id": "device-1", "action": "all_on"},
        CapabilityContext(user_gid="user-1", team_gid="tenant-a", operation_id="operation-1"),
    )
    assert output.data["command_id"] == "operation-1"
    assert captured == {"capability_id": "vismockup.visibility", "payload": {"device_id": "device-1", "action": "all_on"}, "operation_id": "operation-1", "team_gid": "tenant-a"}


def test_every_local_action_uses_durable_operation_and_device_resource_selector():
    registry = CapabilityRegistry()
    register_capabilities(registry)
    for registration in registry.snapshot():
        descriptor = registration.descriptor
        if not descriptor.id.startswith("vismockup."):
            continue
        assert descriptor.operation_policy == "required"
        assert descriptor.execution_mode.value == "local"
        assert any(selector.resource_type == "device" and selector.payload_path == "device_id" for selector in descriptor.resource_selectors)


def test_device_lifecycle_outcomes_execute_in_the_cloud_control_plane():
    registry = CapabilityRegistry()
    register_capabilities(registry)

    descriptors = {
        item.descriptor.id: item.descriptor
        for item in registry.snapshot()
        if item.descriptor.id.startswith("local.device.")
    }

    assert set(descriptors) == {"local.device.change.apply", "local.device.read"}
    assert all(item.execution_mode.value == "cloud_sync" for item in descriptors.values())
    assert descriptors["local.device.read"].operation_policy == "none"
    assert descriptors["local.device.change.apply"].operation_policy == "optional"
    assert descriptors["local.device.change.apply"].idempotency_policy == "required"
