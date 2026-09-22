"""Closed, domain-separated grants for an already opened local viewer session."""
from datetime import datetime
from typing import Annotated, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.contracts.connector_execution_plan_v2 import (
    HASH_PATTERN, IDENTITY_PATTERN, SAFE_INTEGER_MAX, Signature, Timestamp,
    _decode_signature, _public_key, canonicalize_v2,
)

PROTOCOL = 'ai00.viewer.interaction.grant.v1'
EVENT_PROTOCOL = 'ai00.viewer.interaction.events.v1'
MAX_AUDIT_BYTES = 1024 * 1024
Identity = Annotated[str, Field(pattern=IDENTITY_PATTERN)]
Gid = Annotated[str, Field(pattern=r'^[1-9][0-9]{0,19}$')]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True, revalidate_instances='always')


class GrantedOperation(ClosedModel):
    # Expand deliberately with executor and authorization-policy tests, never reflection.
    id: Literal['vismockup.node.visibility.change@1', 'vismockup.node.selection.change@1']
    contract_hash: str = Field(pattern=HASH_PATTERN)


class ScopeRequest(ClosedModel):
    workspace_gid: Gid
    document_gid: Gid


class AuthorizeRequest(ScopeRequest):
    source_association_id: Identity
    session_nonce: str = Field(pattern=r'^[0-9a-f]{64}$')
    prior_grant_id: Identity | None = None


class SignedGrant(ClosedModel):
    protocol: Literal['ai00.viewer.interaction.grant.v1']
    grant_id: Identity
    grant_generation: int = Field(ge=1, le=SAFE_INTEGER_MAX)
    session_nonce: str = Field(pattern=r'^[0-9a-f]{64}$')
    actor_id: Identity
    tenant_id: Identity
    device_id: Identity
    runtime_instance_id: Identity
    workspace_gid: Gid
    document_gid: Gid
    source_association_id: Identity
    document_session: str = Field(pattern=HASH_PATTERN)
    operations: list[GrantedOperation] = Field(min_length=1, max_length=2)
    policy_version: Identity
    issued_at: Timestamp
    expires_at: Timestamp
    audience: Literal['ai00.connector.viewer-interaction']
    key_id: Identity
    signature: Signature

    @model_validator(mode='after')
    def bounded_scope(self):
        seconds = (datetime.fromisoformat(self.expires_at) - datetime.fromisoformat(self.issued_at)).total_seconds()
        if not 0 < seconds <= 60:
            raise ValueError('grant_interval_invalid')
        if len({op.id for op in self.operations}) != len(self.operations):
            raise ValueError('duplicate_operation')
        return self

    def verify_signature(self, jwk):
        try:
            r, s = _decode_signature(self.signature)
            _public_key(jwk).verify(encode_dss_signature(r, s), grant_signature_bytes(self), ec.ECDSA(hashes.SHA256()))
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False


def grant_signature_bytes(grant):
    raw = grant.model_dump(mode='json') if isinstance(grant, SignedGrant) else dict(grant)
    raw.pop('signature', None)
    return (PROTOCOL + '\n').encode('ascii') + canonicalize_v2(raw)


ErrorCode = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,127}$')]


class AuditTarget(ClosedModel):
    node_ref: Identity
    status: Literal['completed', 'rejected', 'outcome_unknown', 'not_started']
    error_code: ErrorCode | None


class AuditResult(ClosedModel):
    targets: list[AuditTarget] = Field(max_length=256)


class AuditTimings(ClosedModel):
    total_ms: float = Field(ge=0, le=SAFE_INTEGER_MAX, allow_inf_nan=False)
    com_ms: float = Field(ge=0, le=SAFE_INTEGER_MAX, allow_inf_nan=False)
    journal_ms: float = Field(ge=0, le=SAFE_INTEGER_MAX, allow_inf_nan=False)


class AuditOutcome(ClosedModel):
    request_id: Identity
    status: Literal['completed', 'rejected', 'outcome_unknown']
    result: AuditResult | None
    error_code: ErrorCode | None
    timings: AuditTimings


class AuditEvent(ClosedModel):
    grant_id: Identity
    interaction_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    request_id: Identity
    sequence: int = Field(ge=1, le=SAFE_INTEGER_MAX)
    request_digest: str = Field(pattern=HASH_PATTERN)
    operation_id: Literal['vismockup.node.visibility.change@1', 'vismockup.node.selection.change@1']
    outcome: AuditOutcome

    @model_validator(mode='after')
    def matching_request(self):
        if self.outcome.request_id != self.request_id:
            raise ValueError('interaction_audit_request_mismatch')
        return self


class SignedAuditBatch(ClosedModel):
    protocol: Literal['ai00.viewer.interaction.events.v1']
    device_id: Identity
    runtime_instance_id: Identity
    device_key_id: Identity
    events: list[AuditEvent] = Field(min_length=1, max_length=256)
    signature: Signature

    def verify_signature(self, jwk):
        unsigned = self.model_dump(mode='json', exclude={'signature'})
        try:
            r, s = _decode_signature(self.signature)
            _public_key(jwk).verify(encode_dss_signature(r, s),
                (EVENT_PROTOCOL + '\n').encode('ascii') + canonicalize_v2(unsigned), ec.ECDSA(hashes.SHA256()))
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False
