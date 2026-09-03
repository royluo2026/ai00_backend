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
from .capabilities.connector_runtime import (
    ConnectorHealth, complete_connector_plan, connector_plan_signing_material, get_leased_connector_plan,
    lease_connector_plan, queue_connector_plan, record_connector_heartbeat,
)

__all__ = [
    "activate_device", "authorize_active_lease", "authorize_command_artifact", "authenticate_device", "complete_command", "create_enrollment",
    "enqueue_command", "get_command", "heartbeat", "lease_command", "list_devices", "mark_command_reconciled", "pending_reconciliations", "revoke_device",
    "ConnectorHealth", "connector_plan_signing_material", "queue_connector_plan", "record_connector_heartbeat",
    "complete_connector_plan", "get_leased_connector_plan", "lease_connector_plan",
]
