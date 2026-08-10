"""Stable public surface consumed by Base HTTP and Capability adapters."""

from .control_plane import (
    activate_device,
    authorize_command_artifact,
    authorize_active_lease,
    authenticate_device,
    complete_command,
    create_enrollment,
    enqueue_command,
    get_command,
    heartbeat,
    lease_command,
    list_devices,
    mark_command_reconciled,
    pending_reconciliations,
    revoke_device,
)

__all__ = [
    "activate_device", "authorize_active_lease", "authorize_command_artifact", "authenticate_device", "complete_command", "create_enrollment",
    "enqueue_command", "get_command", "heartbeat", "lease_command", "list_devices", "mark_command_reconciled", "pending_reconciliations", "revoke_device",
]
