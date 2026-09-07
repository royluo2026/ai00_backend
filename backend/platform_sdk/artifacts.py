"""Base-owned Artifact Service access for official domain providers."""
from __future__ import annotations

from datetime import UTC, datetime

from backend.capability_v2.artifacts import ArtifactService, configured_object_storage, SqlArtifactStore
from backend.capability_v2.contracts import (
    ActorIdentity,
    ArtifactRef,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    TenantIdentity,
)
from backend.db.connection import get_conn


def artifact_identity(context):
    return ConsumerIdentity(
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


def artifact_service():
    return ArtifactService(SqlArtifactStore(get_conn), configured_object_storage())


def require_artifact(ref, context, *, resource_refs=()) -> dict:
    artifact_ref = ArtifactRef.model_validate(ref)
    record = artifact_service().authorize_download(
        artifact_ref.artifact_id,
        artifact_identity(context),
        granted_resources=tuple(resource_refs),
    )
    if record.artifact_ref != artifact_ref:
        raise ValueError("artifact reference does not match the immutable artifact record")
    return record.artifact_ref.model_dump(mode="json")


def read_artifact(ref, context, *, maximum=5*1024*1024):
    return artifact_service().read(ArtifactRef.model_validate(ref),artifact_identity(context),maximum=maximum)


def create_artifact(data,media_type,context):
    import hashlib, io
    if len(data)>5*1024*1024: raise ValueError('generated artifact exceeds 5 MiB')
    service=artifact_service();identity=artifact_identity(context)
    digest=hashlib.sha256(data).hexdigest()
    session=service.create_upload(identity,media_type=media_type,expected_sha256=digest,expected_byte_size=len(data))
    service.upload_stream(session.upload_id,identity,io.BytesIO(data))
    return service.finalize(session.upload_id,identity,reported_sha256=digest).model_dump(mode='json')


__all__ = ["require_artifact","read_artifact","create_artifact"]
