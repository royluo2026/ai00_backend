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
DOCUMENT_SNAPSHOT_STEP = obj({
    "step_id": STRING,
    "operation_id": {"type": "string", "const": "vismockup.document.snapshot@1"},
    "contract_hash": HASH,
    "depends_on": {"type": "array", "items": STRING, "maxItems": 0},
    "payload": obj({
        "max_nodes": {"type": "integer", "minimum": 1, "maximum": 250000},
        "max_depth": {"type": "integer", "minimum": 1, "maximum": 100},
    }, ("max_nodes", "max_depth")),
    "payload_hash": HASH,
    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 900},
}, ("step_id", "operation_id", "contract_hash", "depends_on", "payload", "payload_hash", "timeout_seconds"))


def connector_plan(step_schema: dict, *, max_steps: int) -> dict:
    return obj({
        "protocol": {"type": "string", "const": "ai00.connector.execution-plan.v1"},
        "plan_id": STRING, "tenant_id": STRING, "user_id": STRING, "device_id": STRING,
        "capability_version_gid": STRING, "business_definition_hash": HASH,
        "adapter_id": STRING, "adapter_major": {"type": "integer", "const": 1},
        "target_product": CONNECTOR_TARGET_PRODUCT,
        "steps": {"type": "array", "items": step_schema, "minItems": 1, "maxItems": max_steps},
        "issued_at": {"type": "string", "format": "date-time"},
        "expires_at": {"type": "string", "format": "date-time"}, "plan_hash": HASH,
    }, (
        "protocol", "plan_id", "tenant_id", "user_id", "device_id",
        "capability_version_gid", "business_definition_hash", "adapter_id", "adapter_major",
        "target_product", "steps", "issued_at", "expires_at", "plan_hash",
    ))


CONNECTOR_PLAN = connector_plan(CONNECTOR_STEP, max_steps=10000)
DOCUMENT_SNAPSHOT_CONNECTOR_PLAN = connector_plan(DOCUMENT_SNAPSHOT_STEP, max_steps=1)

SOURCE_SELECTOR = obj({
    "endpoint_id": {"type":"string","minLength":1,"maxLength":128},
    "object_uid": {"type":"string","minLength":1,"maxLength":128},
    "item_revision_uid": {"type":"string","maxLength":128},
    "bom_view_uid": {"type":"string","maxLength":128},
    "revision_rule": {"type":"string","minLength":1,"maxLength":128},
    "configuration_date": {"type":"string","format":"date-time"},
}, ("endpoint_id", "object_uid", "revision_rule", "configuration_date"))
EXACT_SOURCE_SELECTOR = obj({
    "endpoint_id": {"type":"string", "const":"tc-production"},
    "object_uid": {"type":"string","minLength":1,"maxLength":128},
    "item_revision_uid": {"type":"string","minLength":1,"maxLength":128},
    "bom_view_uid": {"type":"string","minLength":1,"maxLength":128},
    "revision_rule": {"type":"string","minLength":1,"maxLength":128},
    "configuration_date": {"type":"string","format":"date-time"},
}, ("endpoint_id", "object_uid", "item_revision_uid", "bom_view_uid", "revision_rule", "configuration_date"))
TC_SEARCH_INPUT = obj({
    "endpoint_id": {"type": "string", "const": "tc-production"},
    "item_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "revision_id": {"type": "string", "minLength": 1, "maxLength": 64},
    "revision_rule": {"type": "string", "minLength": 1, "maxLength": 128},
    "configuration_date": {"type": "string", "format": "date-time"},
}, ("endpoint_id", "item_id", "revision_id", "revision_rule", "configuration_date"))
TC_OBSERVE_INPUT = obj({"source_selector":SOURCE_SELECTOR,
    "max_nodes":{"type":"integer","minimum":1,"maximum":250000},
    "max_depth":{"type":"integer","minimum":1,"maximum":128},
    "property_projection":{"type":"string","pattern":"^[a-z0-9_.-]{1,64}$"},
}, ("source_selector","max_nodes","max_depth","property_projection"))
TC_PAGE_INPUT = obj({"observation_id":{"type":"string","pattern":"^tcobs:[a-f0-9]{64}$"},
    "cursor":{"type":"integer","minimum":0,"maximum":250000},
    "page_size":{"type":"integer","minimum":1,"maximum":1000}},
    ("observation_id","cursor","page_size"))
TC_LAUNCH_INPUT = obj({"source_selector":SOURCE_SELECTOR,
    "expected_visdoc_uid":{"type":"string","maxLength":128}},
    ("source_selector","expected_visdoc_uid"))
AH_APPLY_INPUT = obj({"document_session":HASH,"hierarchy_gid":{"type":"string","pattern":"^[1-9][0-9]*$"},
    "base_hash":HASH,"desired_hash":HASH,"cursor":{"type":"integer","minimum":0},
    "max_operations":{"type":"integer","minimum":1,"maximum":256}},
    ("document_session","hierarchy_gid","base_hash","desired_hash","cursor","max_operations"))


class AdapterOperation(FrozenModel):
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}@[1-9][0-9]*$")
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
    "simulation.teamcenter.product.search.request": TC_SEARCH_INPUT,
    "simulation.teamcenter.product_structure.observe.request": TC_OBSERVE_INPUT,
    "simulation.teamcenter.product_structure.page.read.request": TC_PAGE_INPUT,
    "simulation.teamcenter.visualization.launch.request": TC_LAUNCH_INPUT,
    "simulation.teamcenter.product_structure.observe": TC_OBSERVE_INPUT,
    "simulation.teamcenter.product.search": TC_SEARCH_INPUT,
    "simulation.teamcenter.product_structure.page.read": TC_PAGE_INPUT,
    "simulation.teamcenter.visualization.launch": TC_LAUNCH_INPUT,
    "simulation.vismockup.document.identity.read.request": obj({}, ()),
    "simulation.vismockup.document.hierarchy_inventory.read.request": obj({
        "document_session": HASH,
        "start_index": {"type": "integer", "minimum": 0},
        "page_size": {"type": "integer", "minimum": 1, "maximum": 16},
        "max_nodes": {"type": "integer", "minimum": 1, "maximum": 100000},
    }, ("document_session", "start_index", "page_size", "max_nodes")),
    "simulation.connector.health.get": obj(CONNECTOR, ("connector_id",)),
    "simulation.connector.plan.queue": obj({"plan": CONNECTOR_PLAN}, ("plan",)),
    ("simulation.connector.plan.queue", 2): obj(
        {"plan": DOCUMENT_SNAPSHOT_CONNECTOR_PLAN}, ("plan",),
    ),
    ("simulation.connector.plan.queue", 3): obj(
        {"plan": CONNECTOR_PLAN}, ("plan",),
    ),
    "simulation.vismockup.application.attach.request": obj({}, ()),
    "simulation.vismockup.application.launch.request": obj({}, ()),
    "simulation.vismockup.model.open.request": obj({"artifact_ref": ARTIFACT_REF}, ("artifact_ref",)),
    "simulation.environment.runtime_package.open.request": obj({"workspace_gid": STRING,"version_gid": STRING,"idempotency_key": STRING}, ("workspace_gid","version_gid","idempotency_key")),
    "simulation.vismockup.model.insert.request": obj({"artifact_ref": ARTIFACT_REF}, ("artifact_ref",)),
    "simulation.vismockup.model.close.request": obj({}, ()),
    "simulation.vismockup.visibility.change.request": obj({"action": {"type": "string", "enum": ["all_on", "all_off"]}}, ("action",)),
    "simulation.vismockup.node.visibility.change.request": obj({
        "node_key": STRING,
        "action": {"type": "string", "enum": ["show", "hide", "toggle_visible", "isolate"]},
    }, ("node_key", "action")),
    "simulation.vismockup.node.selection.change.request": obj({
        "node_key": STRING,
        "action": {"type": "string", "enum": ["highlight", "unhighlight", "select", "deselect"]},
    }, ("node_key", "action")),
    "simulation.vismockup.tree.read.request": obj({
        "max_depth": {"type": "integer", "minimum": 1, "maximum": 8},
        "force_refresh": {"type": "boolean"},
    }, ("max_depth",)),
    "simulation.vismockup.command.get": obj({"operation_id": STRING}, ("operation_id",)),
    "simulation.vismockup.status.get": obj(CONNECTOR, ("connector_id",)),
    "simulation.vismockup.application.launch": obj(CONNECTOR, ("connector_id",)),
    "simulation.vismockup.model.open": obj({**CONNECTOR, "artifact_ref": ARTIFACT_REF}, ("connector_id", "artifact_ref")),
    "simulation.vismockup.model.insert": obj({**CONNECTOR, "artifact_ref": ARTIFACT_REF}, ("connector_id", "artifact_ref")),
    "simulation.vismockup.tree.get": obj({**CONNECTOR, "max_depth": {"type": "integer", "minimum": 1, "maximum": 100}, "force": {"type": "boolean"}}, ("connector_id",)),
    "simulation.vismockup.selection.highlight": obj({**CONNECTOR, "catia_names": {"type": "array", "items": STRING, "minItems": 1, "maxItems": 1000}}, ("connector_id", "catia_names")),
    "simulation.vismockup.visibility.change.apply": obj({**CONNECTOR, "action": {"type": "string", "enum": ["all_on", "all_off", "deselect"]}}, ("connector_id", "action")),
    "simulation.vismockup.node.visibility.change.apply": obj({
        **CONNECTOR, "node_key": STRING,
        "action": {"type": "string", "enum": ["show", "hide", "toggle_visible", "isolate"]},
    }, ("connector_id", "node_key", "action")),
    "simulation.vismockup.node.selection.change.apply": obj({
        **CONNECTOR, "node_key": STRING,
        "action": {"type": "string", "enum": ["highlight", "unhighlight", "select", "deselect"]},
    }, ("connector_id", "node_key", "action")),
    "simulation.vismockup.capture.create": obj(CONNECTOR, ("connector_id",)),
    "simulation.connector.pairing.request": obj({
        "bootstrap_token": STRING, "installation_id": STRING, "verifier_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "device_name": STRING, "runtime_version": STRING,
        "windows_sid_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "masked_windows_user": STRING, "ephemeral_public_key": STRING,
    }, ("bootstrap_token", "installation_id", "verifier_hash", "device_name", "runtime_version", "windows_sid_hash", "masked_windows_user", "ephemeral_public_key")),
    "simulation.connector.pairing.bootstrap.create": obj({}, ()),
    "simulation.connector.pairing.bootstrap.get": obj({"bootstrap_id": STRING}, ("bootstrap_id",)),
    "simulation.connector.pairing.summary.get": {
        **obj({"user_code": STRING, "pairing_id": STRING}, ()),
        "oneOf": [{"required": ["user_code"]}, {"required": ["pairing_id"]}],
    },
    "simulation.connector.pairing.approve": obj({
        "user_code": STRING, "pairing_id": STRING,
        "expected_version": {"type": "integer", "minimum": 1},
    }, ("expected_version",)) | {
        "oneOf": [{"required": ["user_code"]}, {"required": ["pairing_id"]}],
    },
    "simulation.connector.pairing.complete": obj({
        "pairing_id": STRING, "installation_id": STRING, "verifier": STRING,
    }, ("pairing_id", "installation_id", "verifier")),
    "simulation.connector.pairing.activate": obj({
        "pairing_id": STRING, "connector_id": STRING, "activation_proof": STRING,
    }, ("pairing_id", "connector_id", "activation_proof")),
    "simulation.connector.pairing.cancel": obj({
        "bootstrap_id": STRING, "expected_version": {"type": "integer", "minimum": 1},
    }, ("bootstrap_id", "expected_version")),
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
INSERT_RESULT = obj({
    "document_id": STRING, "inserted_path": STRING,
    "inserted_count": {"type": "integer", "minimum": 0},
    "already_present": {"type": "boolean"},
}, ("document_id", "inserted_path", "inserted_count", "already_present"))
TREE_NODE = obj({
    "node_key": STRING, "parent_node_key": {"type": ["string", "null"]},
    "name": {"type": "string"}, "catia_occurrence_name": {"type": "string"},
    "has_more": {"type": "boolean"},
}, ("node_key", "parent_node_key", "name", "catia_occurrence_name", "has_more"))
TREE_RESULT = obj({
    "nodes": {"type": "array", "items": TREE_NODE},
    "max_depth": {"type": "integer"},
    "cache_state": {"type": "string", "enum": ["verified", "verifying"]},
}, ("nodes", "max_depth", "cache_state"))
HIGHLIGHT_RESULT = obj({"matched": {"type": "integer", "minimum": 0}, "not_found": {"type": "array", "items": STRING}}, ("matched", "not_found"))
VISIBILITY_RESULT = obj({"action": {"type": "string", "enum": ["all_on", "all_off", "deselect"]}}, ("action",))
NODE_VISIBILITY_RESULT = obj({"node_key": STRING, "visible": {"type": "boolean"}}, ("node_key", "visible"))
NODE_SELECTION_RESULT = obj({"node_key": STRING, "selected": {"type": "boolean"}}, ("node_key", "selected"))
CAPTURE_RESULT = obj({"artifact_ref": ARTIFACT_REF}, ("artifact_ref",))
TC_OBSERVE_RESULT = obj({"observation_id":{"type":"string","pattern":"^tcobs:[a-f0-9]{64}$"},
    "source_identity_hash":HASH,"captured_at":{"type":"string","format":"date-time"},
    "node_count":{"type":"integer","minimum":1,"maximum":250000},
    "page_count":{"type":"integer","minimum":1,"maximum":250000},"complete":{"type":"boolean"}},
    ("observation_id","source_identity_hash","captured_at","node_count","page_count","complete"))
TC_GEOMETRY_REF = obj({
    "dataset_uid": STRING,
    "file_uid": STRING,
    "file_name": {"type": "string"},
    "relation_type": STRING,
}, ("dataset_uid", "file_uid", "file_name", "relation_type"))
TC_OCCURRENCE = obj({
    "occurrence_id": STRING,
    "parent_occurrence_id": {"type": ["string", "null"]},
    "depth": {"type": "integer", "minimum": 0, "maximum": 128},
    "child_order": {"type": "integer", "minimum": 0},
    "name": {"type": "string"},
    "item_uid": {"type": "string"},
    "item_id": {"type": "string"},
    "item_revision_uid": {"type": "string"},
    "revision_id": {"type": "string"},
    "component_type": {"type": "string"},
    "owning_user": {"type": "string"},
    "owning_group": {"type": "string"},
    "transform": {"type": ["array", "null"], "items": {"type": "number"}, "minItems": 16, "maxItems": 16},
    "absolute_transform": {"type": ["array", "null"], "items": {"type": "number"}, "minItems": 16, "maxItems": 16},
    "transform_unit": {"type": "string", "maxLength": 32},
    "transform_convention": {"type": "string", "maxLength": 64},
    "bbox": {"type": ["array", "null"], "items": {"type": "number"}, "minItems": 6, "maxItems": 6},
    "bbox_unit": {"type": "string", "maxLength": 32},
    "torque_raw": {"type": ["string", "null"], "maxLength": 256},
    "torque_importance": {"type": ["string", "null"], "maxLength": 256},
    "weight_raw": {"type": ["string", "null"], "maxLength": 256},
    "unit_weight_raw": {"type": ["string", "null"], "maxLength": 256},
    "geometry_refs": {"type": "array", "items": TC_GEOMETRY_REF, "maxItems": 256},
}, (
    "occurrence_id", "parent_occurrence_id", "depth", "child_order", "name",
    "item_uid", "item_id", "item_revision_uid", "revision_id", "component_type",
    "owning_user", "owning_group", "transform", "absolute_transform", "transform_unit",
    "transform_convention", "bbox", "bbox_unit", "torque_raw", "torque_importance",
    "weight_raw", "unit_weight_raw", "geometry_refs",
))
TC_PAGE_RESULT = obj({"observation_id":{"type":"string","pattern":"^tcobs:[a-f0-9]{64}$"},
    "cursor":{"type":"integer","minimum":0},"next_cursor":{"type":["integer","null"],"minimum":0},
    "nodes":{"type":"array","maxItems":1000,"items":TC_OCCURRENCE},
    "page_hash":HASH}, ("observation_id","cursor","next_cursor","nodes","page_hash"))
TC_LAUNCH_RESULT = obj({"launch_id":{"type":"string","pattern":"^tclaunch:[a-f0-9]{64}$"},
    "runner_started":{"type":"boolean"},"expected_visdoc_uid":{"type":"string","maxLength":128},
    "source_identity_hash":HASH}, ("launch_id","runner_started","expected_visdoc_uid","source_identity_hash"))
TC_SEARCH_ITEM = obj({
    "display_name": {"type": "string", "maxLength": 512},
    "item_id": {"type": "string", "maxLength": 128},
    "revision_id": {"type": "string", "maxLength": 64},
    "component_type": {"type": "string", "maxLength": 256},
    "owning_user": {"type": "string", "maxLength": 256},
    "owning_group": {"type": "string", "maxLength": 256},
    "source_selector": EXACT_SOURCE_SELECTOR,
}, ("display_name", "item_id", "revision_id", "component_type", "owning_user", "owning_group", "source_selector"))
TC_SEARCH_RESULT = obj({
    "items": {"type": "array", "items": TC_SEARCH_ITEM, "maxItems": 20},
}, ("items",))
AH_APPLY_RESULT = obj({"document_session":HASH,"hierarchy_gid":{"type":"string","pattern":"^[1-9][0-9]*$"},
    "applied":{"type":"integer","minimum":0,"maximum":256},"skipped":{"type":"integer","minimum":0,"maximum":256},
    "conflicts":{"type":"array","maxItems":256,"items":{"type":"string","maxLength":256}},
    "next_cursor":{"type":["integer","null"],"minimum":0},"result_hash":HASH},
    ("document_session","hierarchy_gid","applied","skipped","conflicts","next_cursor","result_hash"))
PAIRING_SUMMARY = obj({
    "pairing_id": STRING, "user_code": STRING, "device_name": STRING,
    "runtime_version": STRING, "masked_windows_user": STRING,
    "status": STRING, "expires_at": {"type": "string", "format": "date-time"},
    "resource_version": {"type": "integer", "minimum": 1},
}, ("pairing_id", "user_code", "device_name", "runtime_version", "masked_windows_user", "status", "expires_at", "resource_version"))

OUTPUT_SCHEMAS = {
    "simulation.teamcenter.product.search.request": OPERATION_REF,
    "simulation.teamcenter.product_structure.observe.request": OPERATION_REF,
    "simulation.teamcenter.product_structure.page.read.request": OPERATION_REF,
    "simulation.teamcenter.visualization.launch.request": OPERATION_REF,
    "simulation.teamcenter.product_structure.observe": TC_OBSERVE_RESULT,
    "simulation.teamcenter.product.search": TC_SEARCH_RESULT,
    "simulation.teamcenter.product_structure.page.read": TC_PAGE_RESULT,
    "simulation.teamcenter.visualization.launch": TC_LAUNCH_RESULT,
    "simulation.vismockup.document.identity.read.request": OPERATION_REF,
    "simulation.vismockup.document.hierarchy_inventory.read.request": OPERATION_REF,
    "simulation.connector.health.get": CONNECTOR_HEALTH,
    "simulation.connector.plan.queue": OPERATION_REF,
    "simulation.vismockup.application.attach.request": OPERATION_REF,
    "simulation.vismockup.application.launch.request": OPERATION_REF,
    "simulation.vismockup.model.open.request": OPERATION_REF,
    "simulation.environment.runtime_package.open.request": OPERATION_REF,
    "simulation.vismockup.model.insert.request": OPERATION_REF,
    "simulation.vismockup.model.close.request": OPERATION_REF,
    "simulation.vismockup.visibility.change.request": OPERATION_REF,
    "simulation.vismockup.node.visibility.change.request": OPERATION_REF,
    "simulation.vismockup.node.selection.change.request": OPERATION_REF,
    "simulation.vismockup.tree.read.request": OPERATION_REF,
    "simulation.vismockup.command.get": obj({
        "operation_id": STRING,
        "status": {"type": "string", "enum": [
            "queued", "leased", "completed", "failed", "cancelled", "outcome_unknown", "expired",
        ]},
        "outcome": {"type": ["object", "null"], "additionalProperties": True},
    }, ("operation_id", "status", "outcome")),
    "simulation.vismockup.status.get": STATUS_RESULT,
    "simulation.vismockup.application.launch": LAUNCH_RESULT,
    "simulation.vismockup.model.open": OPEN_RESULT,
    "simulation.vismockup.model.insert": INSERT_RESULT,
    "simulation.vismockup.tree.get": TREE_RESULT,
    "simulation.vismockup.selection.highlight": HIGHLIGHT_RESULT,
    "simulation.vismockup.visibility.change.apply": VISIBILITY_RESULT,
    "simulation.vismockup.node.visibility.change.apply": NODE_VISIBILITY_RESULT,
    "simulation.vismockup.node.selection.change.apply": NODE_SELECTION_RESULT,
    "simulation.vismockup.capture.create": CAPTURE_RESULT,
    "simulation.connector.pairing.request": obj({
        "pairing_id": STRING, "user_code": STRING, "verification_uri": STRING,
        "status": STRING, "expires_at": {"type": "string", "format": "date-time"},
        "resource_version": {"type": "integer", "minimum": 1}, "bootstrap_id": STRING,
    }, ("pairing_id", "user_code", "verification_uri", "status", "expires_at", "resource_version", "bootstrap_id")),
    "simulation.connector.pairing.bootstrap.create": obj({
        "bootstrap_id": STRING, "bootstrap_token": STRING, "status": STRING,
        "expires_at": {"type": "string", "format": "date-time"},
        "resource_version": {"type": "integer", "minimum": 1},
    }, ("bootstrap_id", "bootstrap_token", "status", "expires_at", "resource_version")),
    "simulation.connector.pairing.bootstrap.get": obj({
        "bootstrap_id": STRING, "status": STRING, "pairing_id": {"type": ["string", "null"]},
        "expires_at": {"type": "string", "format": "date-time"},
        "resource_version": {"type": "integer", "minimum": 1},
    }, ("bootstrap_id", "status", "pairing_id", "expires_at", "resource_version")),
    "simulation.connector.pairing.summary.get": PAIRING_SUMMARY,
    "simulation.connector.pairing.approve": PAIRING_SUMMARY,
    "simulation.connector.pairing.complete": obj({
        "connector_id": STRING, "encrypted_credential_envelope": STRING,
        "envelope_hash": HASH, "activation_challenge": STRING,
    }, ("connector_id", "encrypted_credential_envelope", "envelope_hash", "activation_challenge")),
    "simulation.connector.pairing.activate": PAIRING_SUMMARY,
    "simulation.connector.pairing.cancel": obj({
        "bootstrap_id": STRING, "status": STRING, "pairing_id": {"type": ["string", "null"]},
        "expires_at": {"type": "string", "format": "date-time"},
        "resource_version": {"type": "integer", "minimum": 1},
    }, ("bootstrap_id", "status", "pairing_id", "expires_at", "resource_version")),
    "simulation.connector.binding.get": obj({
        "connector_id": {"type": ["string", "null"]},
        "installation_id": {"type": ["string", "null"]},
    }, ("connector_id", "installation_id")),
}


__all__ = [
    "AdapterAdvertisement", "AdapterOperation", "ConnectorHealth",
    "INPUT_SCHEMAS", "OUTPUT_SCHEMAS",
]

# App v2 user actions remain governed; device transport is not a business Capability.
INPUT_SCHEMAS['simulation.connector.runtime.takeover'] = obj({
    'device_id': {'type': 'string', 'minLength': 1, 'maxLength': 256},
    'expected_generation': {'type': 'integer', 'minimum': 1},
    'runtime_instance_id': {'type': 'string', 'minLength': 1, 'maxLength': 256},
    'reason': {'type': 'string', 'minLength': 1, 'maxLength': 1024},
}, ('device_id', 'expected_generation', 'runtime_instance_id', 'reason'))
OUTPUT_SCHEMAS['simulation.connector.runtime.takeover'] = obj({
    'device_id': STRING, 'runtime_generation': {'type': 'integer', 'minimum': 1},
    'runtime_instance_id': STRING, 'audit_ref': STRING,
}, ('device_id', 'runtime_generation', 'runtime_instance_id', 'audit_ref'))
for _action in ('approve', 'summary.get', 'cancel'):
    _id = 'simulation.connector.pairing.' + _action
    _properties = {'pairing_id': {'type': 'string', 'minLength': 1, 'maxLength': 256}}
    if _action != 'summary.get':
        _properties['expected_version'] = {'type': 'integer', 'minimum': 1}
    INPUT_SCHEMAS[(_id, 2)] = obj(_properties, tuple(_properties))
    OUTPUT_SCHEMAS[(_id, 2)] = obj({
        'pairing_id': STRING, 'status': {'type': 'string', 'enum': ['created', 'user_bound', 'activated', 'cancelled', 'expired']},
        'resource_version': {'type': 'integer', 'minimum': 1},
        'expires_at': {'type': 'string', 'format': 'date-time'}, 'device_key_id': STRING,
    }, ('pairing_id', 'status', 'resource_version', 'expires_at', 'device_key_id'))
