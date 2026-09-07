"""Closed cross-language contracts for AI00 Connector protocol v2."""
from __future__ import annotations

import base64
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Annotated, Any, Literal, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


PROTOCOL_V2 = "ai00.connector.execution-plan.v2"
SIGNATURE_ALGORITHM = "ecdsa-p256-sha256"
P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
SAFE_INTEGER_MAX = (1 << 53) - 1

IDENTITY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$"
CAPABILITY_PATTERN = r"^[a-z][a-z0-9_.-]{2,127}$"
OPERATION_PATTERN = r"^[a-z][a-z0-9_.-]{2,127}@[1-9][0-9]*$"
HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"
PLAN_HASH_PATTERN = r"^[0-9a-f]{64}$"
BASE64URL_PATTERN = r"^[A-Za-z0-9_-]+$"
TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,9})?Z$"
)


def _validate_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("json_surrogate_forbidden")
        return value
    if isinstance(value, int):
        if not -SAFE_INTEGER_MAX <= value <= SAFE_INTEGER_MAX:
            raise ValueError("json_safe_integer_required")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("json_finite_number_required")
        return value
    if isinstance(value, list):
        for item in value:
            _validate_json(item)
        return value
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("json_object_key_must_be_string")
            _validate_json(key)
            _validate_json(item)
        return value
    raise ValueError("json_value_required")


JsonValue = Annotated[Any, AfterValidator(_validate_json)]


def _canonical_text(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_canonical_text(item) for item in value) + "]"
    if isinstance(value, Mapping):
        keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return "{" + ",".join(
            _canonical_text(key) + ":" + _canonical_text(value[key]) for key in keys
        ) + "}"
    raise ValueError("json_value_required")


def _canonical_float(value: float) -> str:
    if value == 0:
        return "0"
    negative = value < 0
    raw = repr(abs(value)).lower()
    if "e" not in raw:
        text = raw[:-2] if raw.endswith(".0") else raw
        return "-" + text if negative else text

    mantissa, exponent_text = raw.split("e")
    exponent = int(exponent_text)
    digits = mantissa.replace(".", "").rstrip("0")
    decimal_position = exponent + 1
    if decimal_position <= -6:
        text = digits[0] + (("." + digits[1:]) if len(digits) > 1 else "")
        text += "e" + ("+" if exponent >= 0 else "") + str(exponent)
    elif decimal_position <= 0:
        text = "0." + "0" * -decimal_position + digits
    elif decimal_position <= 21:
        if decimal_position >= len(digits):
            text = digits + "0" * (decimal_position - len(digits))
        else:
            text = digits[:decimal_position] + "." + digits[decimal_position:]
    else:
        text = digits[0] + (("." + digits[1:]) if len(digits) > 1 else "")
        text += "e+" + str(decimal_position - 1)
    return "-" + text if negative else text


def canonicalize_v2(value: Any) -> bytes:
    """Return RFC 8785 UTF-8 bytes for values accepted by the protocol schema."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    _validate_json(value)
    return _canonical_text(value).encode("utf-8")


def _wire_mapping(value: Mapping[str, Any] | BaseModel) -> Mapping[str, Any]:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def compute_plan_hash(value: Mapping[str, Any] | BaseModel) -> str:
    source = _wire_mapping(value)
    projected = {key: item for key, item in source.items() if key not in {"plan_hash", "signature"}}
    return hashlib.sha256(canonicalize_v2(projected)).hexdigest()


def plan_signature_bytes(value: Mapping[str, Any] | BaseModel) -> bytes:
    source = _wire_mapping(value)
    return canonicalize_v2({key: item for key, item in source.items() if key != "signature"})


def outcome_signature_bytes(value: Mapping[str, Any] | BaseModel) -> bytes:
    source = _wire_mapping(value)
    return canonicalize_v2({key: item for key, item in source.items() if key != "signature"})


def _decode_base64url(value: str, *, size: int) -> bytes:
    if not re.fullmatch(BASE64URL_PATTERN, value) or "=" in value:
        raise ValueError("unpadded_base64url_required")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as error:
        raise ValueError("invalid_base64url") from error
    if len(decoded) != size:
        raise ValueError("base64url_length_invalid")
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        raise ValueError("non_canonical_base64url")
    return decoded


def _decode_signature(value: str) -> tuple[int, int]:
    raw = _decode_base64url(value, size=64)
    r, s = int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
    if not 0 < r < P256_ORDER or not 0 < s <= P256_ORDER // 2:
        raise ValueError("low_s_p1363_signature_required")
    return r, s


def _validate_signature(value: str) -> str:
    _decode_signature(value)
    return value


def _validate_timestamp(value: str) -> str:
    if not TIMESTAMP_PATTERN.fullmatch(value):
        raise ValueError("canonical_utc_timestamp_required")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("canonical_utc_timestamp_required") from error
    return value


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


Signature = Annotated[str, Field(pattern=BASE64URL_PATTERN), AfterValidator(_validate_signature)]
Timestamp = Annotated[str, AfterValidator(_validate_timestamp)]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ConnectorTargetProductV2(_ClosedModel):
    product_id: str = Field(pattern=CAPABILITY_PATTERN)
    minimum_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){1,3}$")
    maximum_version_exclusive: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){1,3}$")

    @model_validator(mode="after")
    def verify_range(self) -> "ConnectorTargetProductV2":
        parse = lambda value: tuple(int(part) for part in value.split("."))
        if parse(self.minimum_version) >= parse(self.maximum_version_exclusive):
            raise ValueError("target_product_version_range_invalid")
        return self


class ConnectorStepV2(_ClosedModel):
    step_id: str = Field(pattern=IDENTITY_PATTERN)
    operation_id: str = Field(pattern=OPERATION_PATTERN)
    contract_hash: str = Field(pattern=HASH_PATTERN)
    depends_on: list[str]
    payload: JsonValue
    payload_hash: str = Field(pattern=HASH_PATTERN)
    timeout_seconds: int = Field(ge=1, le=900)
    side_effect_classification: Literal["read", "write", "destructive"]
    post_condition_probe_id: str | None

    @model_validator(mode="after")
    def verify_step(self) -> "ConnectorStepV2":
        expected_hash = "sha256:" + hashlib.sha256(canonicalize_v2(self.payload)).hexdigest()
        if self.payload_hash != expected_hash:
            raise ValueError("payload_hash_mismatch")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("duplicate_step_dependency")
        if self.side_effect_classification != "read" and self.post_condition_probe_id is None:
            raise ValueError("post_condition_probe_required")
        return self


class ConnectorExecutionPlanV2(_ClosedModel):
    protocol: Literal["ai00.connector.execution-plan.v2"]
    plan_id: str = Field(pattern=IDENTITY_PATTERN)
    capability_id: str = Field(pattern=CAPABILITY_PATTERN)
    major_version: int = Field(ge=1)
    capability_version_gid: str = Field(pattern=IDENTITY_PATTERN)
    business_definition_hash: str = Field(pattern=HASH_PATTERN)
    catalog_release: str = Field(pattern=IDENTITY_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    actor_id: str = Field(pattern=IDENTITY_PATTERN)
    device_id: str = Field(pattern=IDENTITY_PATTERN)
    runtime_generation: int = Field(ge=1)
    runtime_instance_id: str = Field(pattern=IDENTITY_PATTERN)
    adapter_id: str = Field(pattern=CAPABILITY_PATTERN)
    adapter_major: int = Field(ge=1)
    target_product: ConnectorTargetProductV2
    normalized_input_hash: str = Field(pattern=HASH_PATTERN)
    confirmation_receipt_id: str | None
    idempotency_key: str = Field(pattern=IDENTITY_PATTERN)
    steps: list[ConnectorStepV2] = Field(min_length=1, max_length=10_000)
    issued_at: Timestamp
    expires_at: Timestamp
    plan_hash: str = Field(pattern=PLAN_HASH_PATTERN)
    signature_algorithm: Literal["ecdsa-p256-sha256"]
    key_id: str = Field(pattern=IDENTITY_PATTERN)
    signature: Signature

    def compute_hash(self) -> str:
        return compute_plan_hash(self)

    def verify_signature(self, jwk: Mapping[str, Any]) -> bool:
        return verify_plan_signature(self, jwk)

    @model_validator(mode="after")
    def verify_plan(self) -> "ConnectorExecutionPlanV2":
        if _timestamp(self.expires_at) <= _timestamp(self.issued_at):
            raise ValueError("plan_expiry_must_follow_issue_time")
        seen: set[str] = set()
        for step in self.steps:
            if step.step_id in seen:
                raise ValueError("duplicate_step_id")
            if any(dependency not in seen for dependency in step.depends_on):
                raise ValueError("invalid_step_dependency")
            seen.add(step.step_id)
        if self.plan_hash != self.compute_hash():
            raise ValueError("plan_hash_mismatch")
        return self


class ConnectorStepResultV2(_ClosedModel):
    step_id: str = Field(pattern=IDENTITY_PATTERN)
    started_at: Timestamp
    completed_at: Timestamp
    status: Literal["succeeded", "failed_without_effect", "outcome_unknown", "manual_review_required"]
    result: JsonValue
    result_hash: str | None = Field(pattern=HASH_PATTERN)
    error_code: str | None = Field(pattern=r"^[a-z0-9_.-]{1,128}$")
    reconciliation_state: Literal[
        "not_required", "pending", "succeeded", "failed_without_effect", "manual_review_required"
    ]

    @model_validator(mode="after")
    def verify_result(self) -> "ConnectorStepResultV2":
        if _timestamp(self.completed_at) < _timestamp(self.started_at):
            raise ValueError("step_completion_precedes_start")
        if self.status == "succeeded":
            expected_hash = "sha256:" + hashlib.sha256(canonicalize_v2(self.result)).hexdigest()
            if self.result_hash != expected_hash:
                raise ValueError("result_hash_mismatch")
            if self.error_code is not None:
                raise ValueError("succeeded_step_has_error")
        elif self.error_code is None:
            raise ValueError("error_code_required")
        return self


class ConnectorPlanOutcomeV2(_ClosedModel):
    protocol: Literal["ai00.connector.execution-plan.v2"]
    plan_id: str = Field(pattern=IDENTITY_PATTERN)
    plan_hash: str = Field(pattern=PLAN_HASH_PATTERN)
    lease_id: str = Field(pattern=IDENTITY_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    device_id: str = Field(pattern=IDENTITY_PATTERN)
    runtime_generation: int = Field(ge=1)
    runtime_instance_id: str = Field(pattern=IDENTITY_PATTERN)
    overall_status: Literal[
        "succeeded", "failed_without_effect", "outcome_unknown", "manual_review_required"
    ]
    steps: list[ConnectorStepResultV2] = Field(min_length=1, max_length=10_000)
    journal_sequence: int = Field(ge=1)
    reported_at: Timestamp
    signature_algorithm: Literal["ecdsa-p256-sha256"]
    device_key_id: str = Field(pattern=IDENTITY_PATTERN)
    signature: Signature

    def verify_signature(self, jwk: Mapping[str, Any]) -> bool:
        return verify_outcome_signature(self, jwk)

    @model_validator(mode="after")
    def verify_steps(self) -> "ConnectorPlanOutcomeV2":
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("duplicate_step_result")
        return self


class _PublicP256Jwk(_ClosedModel):
    kty: Literal["EC"]
    crv: Literal["P-256"]
    x: str
    y: str

    @field_validator("x", "y")
    @classmethod
    def validate_coordinate(cls, value: str) -> str:
        _decode_base64url(value, size=32)
        return value


def _public_key(jwk: Mapping[str, Any]) -> ec.EllipticCurvePublicKey:
    parsed = _PublicP256Jwk.model_validate(jwk)
    x = int.from_bytes(_decode_base64url(parsed.x, size=32), "big")
    y = int.from_bytes(_decode_base64url(parsed.y, size=32), "big")
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def _verify(value: Mapping[str, Any] | BaseModel, jwk: Mapping[str, Any], *, outcome: bool) -> bool:
    try:
        raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
        model = ConnectorPlanOutcomeV2.model_validate(raw) if outcome else ConnectorExecutionPlanV2.model_validate(raw)
        r, s = _decode_signature(model.signature)
        data = outcome_signature_bytes(model) if outcome else plan_signature_bytes(model)
        _public_key(jwk).verify(encode_dss_signature(r, s), data, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, TypeError, ValueError):
        return False


def verify_plan_signature(
    plan: Mapping[str, Any] | ConnectorExecutionPlanV2, jwk: Mapping[str, Any],
) -> bool:
    return _verify(plan, jwk, outcome=False)


def verify_outcome_signature(
    outcome: Mapping[str, Any] | ConnectorPlanOutcomeV2, jwk: Mapping[str, Any],
) -> bool:
    return _verify(outcome, jwk, outcome=True)


__all__ = [
    "ConnectorExecutionPlanV2", "ConnectorPlanOutcomeV2", "ConnectorStepResultV2",
    "ConnectorStepV2", "ConnectorTargetProductV2", "PROTOCOL_V2", "SIGNATURE_ALGORITHM",
    "canonicalize_v2", "compute_plan_hash", "outcome_signature_bytes",
    "plan_signature_bytes", "verify_outcome_signature", "verify_plan_signature",
]
