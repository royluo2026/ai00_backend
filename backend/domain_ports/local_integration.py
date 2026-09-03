"""Versioned cross-language contracts owned by Local Integration."""
from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
import json
from typing import Any, Literal, Mapping

from pydantic import Field, model_validator

from backend.capability_v2.contracts import FrozenModel, IDENTITY_PATTERN


PROTOCOL_V2 = "ai00.local-operation.v2"
CONNECTOR_PLAN_PROTOCOL_V1 = "ai00.connector.execution-plan.v1"
HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"


def canonical_json_bytes(value: Any) -> bytes:
    """Canonical UTF-8 JSON shared with the .NET Local Runtime."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class LocalOperationEnvelope(FrozenModel):
    protocol: str = Field(pattern=r"^ai00\.local-operation\.v2$")
    operation_id: str = Field(pattern=IDENTITY_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    payload: Mapping[str, Any]
    payload_hash: str = Field(pattern=HASH_PATTERN)
    key_id: str = Field(pattern=IDENTITY_PATTERN)
    issued_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def verify_envelope(self) -> "LocalOperationEnvelope":
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("operation timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("operation envelope must expire after it is issued")
        if self.payload_hash != content_hash(self.payload):
            raise ValueError("payload_hash_mismatch")
        return self


class LocalOperationOutcome(FrozenModel):
    protocol: str = Field(pattern=r"^ai00\.local-operation\.v2$")
    operation_id: str = Field(pattern=IDENTITY_PATTERN)
    status: Literal["completed", "failed", "outcome_unknown"]
    result: Any = None
    error_code: str = Field(default="", pattern=r"^[a-z0-9_.-]{0,128}$")
    reported_at: datetime

    @model_validator(mode="after")
    def verify_outcome(self) -> "LocalOperationOutcome":
        if self.reported_at.tzinfo is None:
            raise ValueError("outcome timestamp must be timezone-aware")
        if self.status != "completed" and not self.error_code:
            raise ValueError("error_code_required")
        if self.status == "completed" and self.error_code:
            raise ValueError("completed outcome cannot contain error_code")
        return self


def sign_operation_envelope(envelope: LocalOperationEnvelope, secret: str) -> str:
    if len(secret.encode("utf-8")) < 32:
        raise ValueError("operation signing secret must contain at least 32 UTF-8 bytes")
    digest = hmac.new(
        secret.encode("utf-8"),
        canonical_json_bytes(envelope.model_dump(mode="json")),
        hashlib.sha256,
    ).hexdigest()
    return "hmac-sha256:" + digest


def verify_operation_signature(envelope: LocalOperationEnvelope, signature: str, secrets: Mapping[str, str]) -> bool:
    secret = secrets.get(envelope.key_id)
    return bool(secret) and hmac.compare_digest(sign_operation_envelope(envelope, secret), signature)


def sign_operation_outcome(outcome: LocalOperationOutcome, device_secret: str) -> str:
    if len(device_secret.encode("utf-8")) < 32:
        raise ValueError("device signing secret must contain at least 32 UTF-8 bytes")
    digest = hmac.new(device_secret.encode("utf-8"), canonical_json_bytes(outcome.model_dump(mode="json")), hashlib.sha256).hexdigest()
    return "hmac-sha256:" + digest


def verify_operation_outcome(outcome: LocalOperationOutcome, signature: str, device_secret: str) -> bool:
    return hmac.compare_digest(sign_operation_outcome(outcome, device_secret), signature)


__all__ = [
    "CONNECTOR_PLAN_PROTOCOL_V1", "LocalOperationEnvelope", "LocalOperationOutcome", "PROTOCOL_V2", "canonical_json_bytes", "content_hash",
    "sign_operation_envelope", "sign_operation_outcome", "verify_operation_outcome", "verify_operation_signature",
]
