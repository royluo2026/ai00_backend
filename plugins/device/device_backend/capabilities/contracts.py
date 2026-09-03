"""Closed Local Integration capability schemas."""
from __future__ import annotations


def obj(properties: dict, required: tuple[str, ...] = ()) -> dict:
    value = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = list(required)
    return value


STRING = {"type": "string", "minLength": 1}
DEVICE = {"device_id": STRING}
ARTIFACT_REF = obj({
    "artifact_id": STRING, "media_type": {"type": "string", "enum": ["model/jt", "model/plmxml", "application/vnd.siemens.plmxml+xml", "model/step"]},
    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$", "example": "0" * 64},
    "byte_size": {"type": "integer", "minimum": 0},
    "version": {"type": "integer", "minimum": 1},
}, ("artifact_id", "media_type", "sha256", "byte_size", "version"))
HASH = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
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
    "step_id": STRING,
    "operation_id": STRING,
    "contract_hash": HASH,
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


INPUT_SCHEMAS = {
    "vismockup.status": obj(DEVICE, ("device_id",)),
    "vismockup.launch": obj(DEVICE, ("device_id",)),
    "vismockup.model.open": obj({**DEVICE, "artifact_ref": ARTIFACT_REF}, ("device_id", "artifact_ref")),
    "vismockup.tree": obj({**DEVICE, "max_depth": {"type": "integer", "minimum": 1, "maximum": 100}, "force": {"type": "boolean"}}, ("device_id",)),
    "vismockup.highlight": obj({**DEVICE, "catia_names": {"type": "array", "items": STRING, "minItems": 1, "maxItems": 1000}}, ("device_id", "catia_names")),
    "vismockup.visibility": obj({**DEVICE, "action": {"type": "string", "enum": ["all_on", "all_off", "deselect"]}}, ("device_id", "action")),
    "vismockup.capture": obj(DEVICE, ("device_id",)),
    "local.command.get": obj({"command_id": STRING}, ("command_id",)),
    "local.device.read": obj({"operation": {"type": "string", "enum": []}, "arguments": obj({})}, ("operation", "arguments")),
    "local.device.change.apply": obj({"operation": {"type": "string", "enum": []}, "arguments": obj({})}, ("operation", "arguments")),
    "device.connector.health.get": obj({"device_id": STRING}, ("device_id",)),
    "device.connector.plan.queue": obj({"plan": CONNECTOR_PLAN}, ("plan",)),
}

QUEUED = obj({
    "command_id": STRING, "device_id": STRING,
    "status": {"type": "string", "enum": ["queued"]},
    "expires_in": {"type": "integer", "minimum": 1},
}, ("command_id", "device_id", "status", "expires_in"))
STATUS_RESULT = obj({"connected": {"type": "boolean"}, "platform": {"type": "string", "enum": ["windows"]}}, ("connected", "platform"))
LAUNCH_RESULT = obj({"status": {"type": "string", "enum": ["starting", "already_running"]}}, ("status",))
OPEN_RESULT = obj({"opened": {"type": "boolean"}}, ("opened",))
TREE_NODE = obj({
    "node_key": STRING, "parent_node_key": {"type": ["string", "null"]}, "name": {"type": "string"},
    "catia_occurrence_name": {"type": "string"}, "has_more": {"type": "boolean"},
}, ("node_key", "parent_node_key", "name", "catia_occurrence_name", "has_more"))
TREE_RESULT = obj({"nodes": {"type": "array", "items": TREE_NODE}, "max_depth": {"type": "integer"}}, ("nodes", "max_depth"))
HIGHLIGHT_RESULT = obj({"matched": {"type": "integer", "minimum": 0}, "not_found": {"type": "array", "items": STRING}}, ("matched", "not_found"))
VISIBILITY_RESULT = obj({"action": {"type": "string", "enum": ["all_on", "all_off", "deselect"]}}, ("action",))
CAPTURE_RESULT = obj({"artifact_ref": ARTIFACT_REF}, ("artifact_ref",))
EXECUTION_RESULT = {"anyOf": [
    {"type": "null"}, STATUS_RESULT, LAUNCH_RESULT, OPEN_RESULT, TREE_RESULT,
    HIGHLIGHT_RESULT, VISIBILITY_RESULT, CAPTURE_RESULT,
]}
COMMAND = obj({
    "command_id": STRING, "device_id": STRING, "capability_id": STRING,
    "capability_version": {"type": "integer", "minimum": 1},
    "status": {"type": "string", "enum": ["queued", "leased", "reconciling", "completed", "failed", "outcome_unknown", "expired", "cancelled"]},
    "result": EXECUTION_RESULT, "error_code": {"type": ["string", "null"]},
    "created_at": STRING, "updated_at": STRING,
}, ("command_id", "device_id", "capability_id", "capability_version", "status", "created_at", "updated_at"))

OUTPUT_SCHEMAS = {capability_id: QUEUED for capability_id in INPUT_SCHEMAS if capability_id != "local.command.get"}
OUTPUT_SCHEMAS["local.command.get"] = COMMAND
OUTPUT_SCHEMAS["local.device.read"] = obj({"data": {}}, ("data",))
OUTPUT_SCHEMAS["local.device.change.apply"] = obj({"data": {}}, ("data",))
OUTPUT_SCHEMAS["device.connector.health.get"] = CONNECTOR_HEALTH
OUTPUT_SCHEMAS["device.connector.plan.queue"] = obj({
    "operation_id": STRING,
    "status": {"type": "string", "enum": ["accepted"]},
    "version": {"type": "integer", "minimum": 1},
}, ("operation_id", "status", "version"))

__all__ = ["INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
