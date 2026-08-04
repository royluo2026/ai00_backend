"""Stable public surface consumed by Base HTTP and Capability adapters."""

from .control_plane import (
    activate_device,
    authenticate_device,
    complete_command,
    create_enrollment,
    enqueue_command,
    get_command,
    heartbeat,
    lease_command,
    list_devices,
    revoke_device,
)

__all__ = [
    "activate_device", "authenticate_device", "complete_command", "create_enrollment",
    "enqueue_command", "get_command", "heartbeat", "lease_command", "list_devices", "revoke_device",
]
