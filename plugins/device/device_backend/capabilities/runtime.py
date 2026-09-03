"""Local Integration capability implementations owned by the Device plugin."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef,
)

from .. import public as control_plane


LOCAL_CAPABILITIES = (
    ("vismockup.status", "Read VisMockup connection state.", "read", "none"),
    ("vismockup.launch", "Launch or connect to VisMockup.", "write", "user"),
    ("vismockup.model.open", "Materialize and open an authorized model ArtifactRef.", "write", "user"),
    ("vismockup.tree", "Read the active VisMockup product tree.", "read", "none"),
    ("vismockup.highlight", "Highlight occurrences by CATIA occurrence name.", "write", "user"),
    ("vismockup.visibility", "Change active-view visibility or selection.", "write", "user"),
    ("vismockup.capture", "Capture the active VisMockup view as an ArtifactRef.", "write", "user"),
)


def _enqueue(capability_id: str):
    def invoke(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        raise CapabilityBusinessError(
            "capability_migration_required",
            "Connector and VisMockup moved to the Simulation domain.",
        )
    return invoke


def get_command(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    row = control_plane.get_command(payload["command_id"], context.user_gid)
    return CapabilityOutput(data={
        "command_id": row["gid"], "device_id": row["device_gid"],
        "capability_id": row["capability_id"], "capability_version": row["capability_version"],
        "status": row["status"], "result": row.get("result"), "error_code": row.get("error"),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }, evidence=(EvidenceRef(kind="local.operation", reference=f"local-operation:{row['gid']}"),))


def specs() -> tuple[tuple[CapabilitySpec, Any], ...]:
    common = {"owner": "device", "plugin_callable": True, "permissions": ("agent.run",), "execution": "local", "tags": ("local-runtime", "vismockup")}
    local = tuple((CapabilitySpec(id=capability_id, description=description, risk=risk, confirmation=confirmation, idempotent=False, deprecated=True, **common), _enqueue(capability_id)) for capability_id, description, risk, confirmation in LOCAL_CAPABILITIES)
    query = CapabilitySpec(owner="device", id="local.command.get", description="Read an owned local operation outcome.", plugin_callable=True, permissions=("agent.run",), tags=("local-runtime", "read"))
    return (*local, (query, get_command))


__all__ = ["get_command", "specs"]
