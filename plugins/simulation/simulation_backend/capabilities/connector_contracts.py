"""Closed contracts for Simulation-owned Connector and VisMockup atoms."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from backend.capability_v2.contracts import FrozenModel
from backend.domain_ports.local_integration import HASH_PATTERN


def obj(properties: dict, required: tuple[str, ...] = ()) -> dict:
    value = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = list(required)
    return value


STRING = {"type": "string", "minLength": 1}
HASH = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
CONNECTOR = {"connector_id": STRING}
ARTIFACT_REF = obj({
    "artifact_id": STRING,
    "media_type": {"type": "string", "enum": [
        "model/jt", "model/plmxml", "application/vnd.siemens.plmxml+xml", "model/step",
        "image/png",
    ]},
    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "byte_size": {"type": "integer", "minimum": 0},
    "version": {"type": "integer", "minimum": 1},
}, ("artifact_id", "media_type", "sha256", "byte_size", "version"))
CONNECTOR_OPERATION = obj({"operation_id": STRING, "contract_hash": HASH}, ("operation_id", "contract_hash"))
CONNECTOR_ADAPTER = obj({
    "adapter_id": STRING,
    "adapter_major": {"type": "integer", "const": 1},
    "product_id": STRING,
    "product_version": STRING,
    "operations": {"type": "array", "items": CONNECTOR_OPERATION, "maxItems": 256},
}, ("adapter_id", "adapter_major", "product_id", "product_version", "operations"))
CONNECTOR_HEALTH = obj({
    "connector_version": STRING,
    "protocol_versions": {"type": "array", "items": STRING, "maxItems": 16},
    "bound_user_id": STRING,
    "session_id": STRING,
    "user_session_present": {"type": "boolean"},
    "session_host_ready": {"type": "boolean"},
    "system_awake": {"type": "boolean"},
    "adapters": {"type": "array", "items": CONNECTOR_ADAPTER, "maxItems": 32},
    "reported_at": {"type": "string", "format": "date-time"},
}, (
    "connector_version", "protocol_versions", "bound_user_id", "session_id",
    "user_session_present", "session_host_ready", "system_awake", "adapters", "reported_at",
))
CONNECTOR_TARGET_PRODUCT = obj({
    "product_id": STRING, "minimum_version": STRING, "maximum_version_exclusive": STRING,
}, ("product_id", "minimum_version", "maximum_version_exclusive"))
CONNECTOR_STEP = obj({
    "step_id": STRING, "operation_id": STRING, "contract_hash": HASH,
    "depends_on": {"type": "array", "items": STRING},
    "payload": {"type": "object", "additionalProperties": True},
    "payload_hash": HASH,
    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
}, ("step_id", "operation_id", "contract_hash", "depends_on", "payload", "payload_hash", "timeout_seconds"))
CONNECTOR_PLAN = obj({
    "protocol": {"type": "string", "const": "ai00.connector.execution-plan.v1"},
    "plan_id": STRING, "tenant_id": STRING, "user_id": STRING, "device_id": STRING,
    "capability_version_gid": STRING, "business_definition_hash": HASH,
    "adapter_id": STRING, "adapter_major": {"type": "integer", "const": 1},
    "target_product": CONNECTOR_TARGET_PRODUCT,
    "steps": {"type": "array", "items": CONNECTOR_STEP, "minItems": 1, "maxItems": 10000},
    "issued_at": {"type": "string", "format": "date-time"},
    "expires_at": {"type": "string", "format": "date-time"}, "plan_hash": HASH,
}, (
    "protocol", "plan_id", "tenant_id", "user_id", "device_id",
    "capability_version_gid", "business_definition_hash", "adapter_id", "adapter_major",
    "target_product", "steps", "issued_at", "expires_at", "plan_hash",
))


class AdapterOperation(FrozenModel):
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}@1$")
    contract_hash: str = Field(pattern=HASH_PATTERN)


class AdapterAdvertisement(FrozenModel):
    adapter_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    adapter_major: Literal[1]
    product_id: str = Field(min_length=1, max_length=128)
    product_version: str = Field(min_length=1, max_length=64)
    operations: tuple[AdapterOperation, ...] = Field(max_length=256)

    @model_validator(mode="after")
    def unique_operations(self) -> "AdapterAdvertisement":
        if len(self.operations) != len({item.operation_id for item in self.operations}):
            raise ValueError("duplicate_adapter_operation")
        return self


class ConnectorHealth(FrozenModel):
    connector_version: str = Field(min_length=1, max_length=64)
    protocol_versions: tuple[str, ...] = Field(max_length=16)
    bound_user_id: str = Field(min_length=1, max_length=191)
    session_id: str = Field(min_length=1, max_length=128)
    user_session_present: bool
    session_host_ready: bool
    system_awake: bool
    adapters: tuple[AdapterAdvertisement, ...] = Field(max_length=32)
    reported_at: datetime

    @model_validator(mode="after")
    def validate_advertisement(self) -> "ConnectorHealth":
        ids = {(item.adapter_id, item.adapter_major) for item in self.adapters}
        if len(ids) != len(self.adapters):
            raise ValueError("duplicate_adapter")
        if self.reported_at.tzinfo is None or self.reported_at.utcoffset() is None:
            raise ValueError("reported_at must be timezone-aware")
        return self


INPUT_SCHEMAS = {
    "simulation.connector.health.get": obj(CONNECTOR, ("connector_id",)),
    "simulation.connector.plan.queue": obj({"plan": CONNECTOR_PLAN}, ("plan",)),
    "simulation.vismockup.status.get": obj(CONNECTOR, ("connector_id",)),
    "simulation.vismockup.application.launch": obj(CONNECTOR, ("connector_id",)),
    "simulation.vismockup.model.open": obj({**CONNECTOR, "artifact_ref": ARTIFACT_REF}, ("connector_id", "artifact_ref")),
    "simulation.vismockup.tree.get": obj({**CONNECTOR, "max_depth": {"type": "integer", "minimum": 1, "maximum": 100}, "force": {"type": "boolean"}}, ("connector_id",)),
    "simulation.vismockup.selection.highlight": obj({**CONNECTOR, "catia_names": {"type": "array", "items": STRING, "minItems": 1, "maxItems": 1000}}, ("connector_id", "catia_names")),
    "simulation.vismockup.visibility.change.apply": obj({**CONNECTOR, "action": {"type": "string", "enum": ["all_on", "all_off", "deselect"]}}, ("connector_id", "action")),
    "simulation.vismockup.capture.create": obj(CONNECTOR, ("connector_id",)),
    "simulation.connector.pairing.request": obj({
        "installation_id": STRING, "verifier_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "device_name": STRING, "runtime_version": STRING,
        "windows_sid_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "masked_windows_user": STRING, "ephemeral_public_key": STRING,
    }, ("installation_id", "verifier_hash", "device_name", "runtime_version", "windows_sid_hash", "masked_windows_user", "ephemeral_public_key")),
    "simulation.connector.pairing.summary.get": obj({"user_code": STRING}, ("user_code",)),
    "simulation.connector.pairing.approve": obj({
        "user_code": STRING, "expected_version": {"type": "integer", "minimum": 1},
    }, ("user_code", "expected_version")),
    "simulation.connector.pairing.complete": obj({
        "pairing_id": STRING, "installation_id": STRING, "verifier": STRING,
    }, ("pairing_id", "installation_id", "verifier")),
    "simulation.connector.binding.get": obj({}, ()),
}

OPERATION_REF = obj({
    "operation_id": STRING,
    "status": {"type": "string", "enum": ["accepted"]},
    "version": {"type": "integer", "minimum": 1},
}, ("operation_id", "status", "version"))
STATUS_RESULT = obj({"connected": {"type": "boolean"}, "platform": {"type": "string", "enum": ["windows"]}}, ("connected", "platform"))
LAUNCH_RESULT = obj({"status": {"type": "string", "enum": ["starting", "already_running"]}}, ("status",))
OPEN_RESULT = obj({"opened": {"type": "boolean"}}, ("opened",))
TREE_NODE = obj({
    "node_key": STRING, "parent_node_key": {"type": ["string", "null"]},
    "name": {"type": "string"}, "catia_occurrence_name": {"type": "string"},
    "has_more": {"type": "boolean"},
}, ("node_key", "parent_node_key", "name", "catia_occurrence_name", "has_more"))
TREE_RESULT = obj({"nodes": {"type": "array", "items": TREE_NODE}, "max_depth": {"type": "integer"}}, ("nodes", "max_depth"))
HIGHLIGHT_RESULT = obj({"matched": {"type": "integer", "minimum": 0}, "not_found": {"type": "array", "items": STRING}}, ("matched", "not_found"))
VISIBILITY_RESULT = obj({"action": {"type": "string", "enum": ["all_on", "all_off", "deselect"]}}, ("action",))
CAPTURE_RESULT = obj({"artifact_ref": ARTIFACT_REF}, ("artifact_ref",))
PAIRING_SUMMARY = obj({
    "pairing_id": STRING, "user_code": STRING, "device_name": STRING,
    "runtime_version": STRING, "masked_windows_user": STRING,
    "status": STRING, "expires_at": {"type": "string", "format": "date-time"},
    "resource_version": {"type": "integer", "minimum": 1},
}, ("pairing_id", "user_code", "device_name", "runtime_version", "masked_windows_user", "status", "expires_at", "resource_version"))

OUTPUT_SCHEMAS = {
    "simulation.connector.health.get": CONNECTOR_HEALTH,
    "simulation.connector.plan.queue": OPERATION_REF,
    "simulation.vismockup.status.get": STATUS_RESULT,
    "simulation.vismockup.application.launch": LAUNCH_RESULT,
    "simulation.vismockup.model.open": OPEN_RESULT,
    "simulation.vismockup.tree.get": TREE_RESULT,
    "simulation.vismockup.selection.highlight": HIGHLIGHT_RESULT,
    "simulation.vismockup.visibility.change.apply": VISIBILITY_RESULT,
    "simulation.vismockup.capture.create": CAPTURE_RESULT,
    "simulation.connector.pairing.request": obj({
        "pairing_id": STRING, "user_code": STRING, "verification_uri": STRING,
        "status": STRING, "expires_at": {"type": "string", "format": "date-time"},
        "resource_version": {"type": "integer", "minimum": 1},
    }, ("pairing_id", "user_code", "verification_uri", "status", "expires_at", "resource_version")),
    "simulation.connector.pairing.summary.get": PAIRING_SUMMARY,
    "simulation.connector.pairing.approve": PAIRING_SUMMARY,
    "simulation.connector.pairing.complete": obj({
        "connector_id": STRING, "encrypted_credential_envelope": STRING,
        "envelope_hash": HASH,
    }, ("connector_id", "encrypted_credential_envelope", "envelope_hash")),
    "simulation.connector.binding.get": obj({
        "connector_id": {"type": ["string", "null"]},
        "installation_id": {"type": ["string", "null"]},
    }, ("connector_id", "installation_id")),
}


__all__ = [
    "AdapterAdvertisement", "AdapterOperation", "ConnectorHealth",
    "INPUT_SCHEMAS", "OUTPUT_SCHEMAS",
]
