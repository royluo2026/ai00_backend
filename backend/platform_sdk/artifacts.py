"""Base-owned Artifact Service access for official domain providers."""
from __future__ import annotations

from datetime import UTC, datetime

from backend.capability_v2.artifacts import ArtifactService, OisObjectStorage, SqlArtifactStore
from backend.capability_v2.contracts import (
    ActorIdentity,
    ArtifactRef,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    TenantIdentity,
)
from backend.db.connection import get_conn


def require_artifact(ref, context, *, resource_refs=()) -> dict:
    artifact_ref = ArtifactRef.model_validate(ref)
    identity = ConsumerIdentity(
        actor=ActorIdentity(
            user_id=context.user_gid,
            authentication_method="capability-context",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(
            tenant_id=context.team_gid or "default",
            membership="member",
            active_roles=context.active_roles,
        ),
        consumer=ConsumerDescriptor(type=ConsumerType.WORKER, consumer_id="ai00.capability"),
    )
    record = ArtifactService(SqlArtifactStore(get_conn), OisObjectStorage()).authorize_download(
        artifact_ref.artifact_id,
        identity,
        granted_resources=tuple(resource_refs),
    )
    if record.artifact_ref != artifact_ref:
        raise ValueError("artifact reference does not match the immutable artifact record")
    return record.artifact_ref.model_dump(mode="json")


__all__ = ["require_artifact"]
