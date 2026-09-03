"""Closed schemas for the Simulation Capability provider."""
from __future__ import annotations


def obj(properties: dict, required: tuple[str, ...] = ()) -> dict:
    value = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = list(required)
    return value


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
POSITIVE_INTEGER = {"type": "integer", "minimum": 1}
NONNEGATIVE_INTEGER = {"type": "integer", "minimum": 0}
HASH = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$", "example": "sha256:" + "0" * 64}
ARTIFACT_REF = obj({
    "artifact_id": STRING, "media_type": STRING,
    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$", "example": "0" * 64},
    "byte_size": NONNEGATIVE_INTEGER, "version": POSITIVE_INTEGER,
}, ("artifact_id", "media_type", "sha256", "byte_size", "version"))
EXECUTION_PLAN_REF = obj({"version_gid": STRING, "revision": POSITIVE_INTEGER, "content_hash": HASH}, ("version_gid", "revision", "content_hash"))
MODEL_SNAPSHOT_REF = obj({
    "model_id": STRING, "version_id": STRING, "snapshot_hash": HASH, "artifact_ref": ARTIFACT_REF,
}, ("model_id", "version_id", "snapshot_hash", "artifact_ref"))
PARAMETER_SET_REF = obj({"parameter_set_id": STRING, "version": POSITIVE_INTEGER, "content_hash": HASH}, ("parameter_set_id", "version", "content_hash"))
PROFILE_REF = obj({"profile_id": STRING, "version": POSITIVE_INTEGER, "content_hash": HASH}, ("profile_id", "version", "content_hash"))
PARAMETER = obj({"name": STRING, "value": {"type": ["number", "integer", "string", "boolean"]}, "unit": STRING}, ("name", "value"))
SETTING = obj({"name": STRING, "value": {"type": ["number", "integer", "string", "boolean"]}}, ("name", "value"))
OPERATION_REF = obj({"operation_id": STRING, "status": {"type": "string", "enum": ["accepted", "running", "completed", "failed", "cancelled", "outcome_unknown"]}, "version": POSITIVE_INTEGER}, ("operation_id", "status", "version"))
SOURCE = obj({
    "execution_plan": obj({"version_gid": STRING, "revision": INTEGER, "content_hash": HASH, "craft_commit_ref": STRING, "node_count": INTEGER}, ("version_gid", "revision", "content_hash", "craft_commit_ref")),
    "model_snapshot": MODEL_SNAPSHOT_REF,
    "parameter_set": obj({"parameter_set_id": STRING, "version": INTEGER, "content_hash": HASH, "parameters": {"type": "array", "items": PARAMETER}}, ("parameter_set_id", "version", "content_hash", "parameters")),
    "simulation_profile": obj({"profile_id": STRING, "version": INTEGER, "content_hash": HASH, "solver": STRING, "solver_version": STRING, "settings": {"type": "array", "items": SETTING}}, ("profile_id", "version", "content_hash", "solver", "solver_version", "settings")),
    "source_fingerprint": HASH,
}, ("execution_plan", "model_snapshot", "parameter_set", "simulation_profile", "source_fingerprint"))
ENVIRONMENT = obj({"environment_id": STRING, "name": STRING, "status": STRING, "source": SOURCE}, ("environment_id", "name", "status", "source"))
RUN = obj({
    "run_id": STRING, "environment_id": STRING, "status": STRING, "source_fingerprint": HASH,
    "craft_commit_ref": STRING, "model_snapshot_hash": HASH, "parameter_version": INTEGER,
    "solver_version": STRING, "operation_ref": OPERATION_REF,
}, ("run_id", "environment_id", "status", "source_fingerprint", "craft_commit_ref", "model_snapshot_hash", "parameter_version", "solver_version", "operation_ref"))
PARAMETER_SET = obj({"parameter_set_ref": PARAMETER_SET_REF, "name": STRING, "parameters": {"type": "array", "items": PARAMETER}}, ("parameter_set_ref", "name", "parameters"))
SOLVER_PROFILE = obj({"simulation_profile_ref": PROFILE_REF, "name": STRING, "solver": STRING, "solver_version": STRING, "settings": {"type": "array", "items": SETTING}}, ("simulation_profile_ref", "name", "solver", "solver_version", "settings"))
RESULT_REF = obj({"run_id": STRING, "source_fingerprint": HASH, "result_hash": HASH}, ("run_id", "source_fingerprint", "result_hash"))
RESULT = obj({"result_ref": RESULT_REF, "run_id": STRING, "status": STRING, "source_fingerprint": HASH, "result_artifact_refs": {"type": "array", "items": ARTIFACT_REF}}, ("result_ref", "run_id", "status", "source_fingerprint", "result_artifact_refs"))
RESULT_CHANGE = obj({
    "artifact_id": STRING,
    "change_type": {"type": "string", "enum": ["artifact_added", "artifact_removed", "artifact_changed"]},
    "before_sha256": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    "after_sha256": {"anyOf": [{"type": "string"}, {"type": "null"}]},
}, ("artifact_id", "change_type", "before_sha256", "after_sha256"))

CAPTURE_PROFILE = obj({
    "format": {"type": "string", "enum": ["png"]},
    "width": {"type": "integer", "enum": [1920]},
    "height": {"type": "integer", "enum": [1080]},
    "background": {"type": "string", "enum": ["current"]},
}, ("format", "width", "height", "background"))
BINDING_PROBLEM = obj({
    "kind": {"type": "string", "enum": ["not_found", "ambiguous"]},
    "source_type": {"type": "string", "enum": ["product", "tool", "equipment", "fixture"]},
    "source_code": STRING,
    "candidates": {"type": "array", "items": STRING, "maxItems": 10000},
}, ("kind", "source_type", "source_code", "candidates"))
PRODUCT_BINDING = obj({"product_ref": STRING, "node_key": STRING}, ("product_ref", "node_key"))
RESOURCE_BINDING = obj({
    "resource_type": {"type": "string", "enum": ["tool", "equipment", "fixture"]},
    "code": STRING, "normalized_code": STRING, "node_key": STRING, "model_ref": MODEL_SNAPSHOT_REF,
}, ("resource_type", "code", "normalized_code", "node_key", "model_ref"))
SCENE = obj({
    "operation_id": STRING,
    "visible_products": {"type": "array", "items": STRING, "maxItems": 10000},
    "visible_resources": {"type": "array", "items": STRING, "maxItems": 500},
    "capture_profile": CAPTURE_PROFILE,
    "scene_hash": HASH,
}, ("operation_id", "visible_products", "visible_resources", "capture_profile", "scene_hash"))
MANIFEST_OPERATION = obj({
    "operation_id": STRING, "sequence": NONNEGATIVE_INTEGER,
    "predecessor_ids": {"type": "array", "items": STRING, "maxItems": 10000},
    "product_node_keys": {"type": "array", "items": STRING, "maxItems": 10000},
    "resource_node_keys": {"type": "array", "items": STRING, "maxItems": 500},
    "scene": SCENE,
}, ("operation_id", "sequence", "predecessor_ids", "product_node_keys", "resource_node_keys", "scene"))
CONNECTOR_OPERATION_REQUIREMENT = obj({"operation_id": STRING, "contract_hash": HASH}, ("operation_id", "contract_hash"))
CONNECTOR_REQUIREMENT = obj({
    "protocol": {"type": "string", "enum": ["ai00.connector.execution-plan.v1"]},
    "adapter_id": {"type": "string", "enum": ["ai00.vismockup"]},
    "adapter_major": {"type": "integer", "enum": [1]},
    "product_id": {"type": "string", "enum": ["siemens.vismockup"]},
    "minimum_product_version": STRING,
    "maximum_product_version_exclusive": STRING,
    "operations": {"type": "array", "items": CONNECTOR_OPERATION_REQUIREMENT, "maxItems": 64},
}, ("protocol", "adapter_id", "adapter_major", "product_id", "minimum_product_version", "maximum_product_version_exclusive", "operations"))
MANIFEST = obj({
    "environment_id": STRING, "environment_version": POSITIVE_INTEGER,
    "execution_source": obj({
        "bop_version_gid": STRING, "revision": POSITIVE_INTEGER, "project_gid": STRING,
        "content_hash": HASH, "execution_plan_uri": STRING,
    }, ("bop_version_gid", "revision", "project_gid", "content_hash", "execution_plan_uri")),
    "document_source": obj({
        "document_id": STRING, "root_node_key": STRING, "source_identity": STRING, "snapshot_hash": HASH,
    }, ("document_id", "root_node_key", "source_identity", "snapshot_hash")),
    "mapping_snapshot_hash": HASH,
    "product_bindings": {"type": "array", "items": PRODUCT_BINDING, "maxItems": 10000},
    "resource_bindings": {"type": "array", "items": RESOURCE_BINDING, "maxItems": 500},
    "operations": {"type": "array", "items": MANIFEST_OPERATION, "maxItems": 10000},
    "capture_profile": CAPTURE_PROFILE,
    "connector_requirement": CONNECTOR_REQUIREMENT,
    "manifest_hash": HASH,
}, ("environment_id", "environment_version", "execution_source", "document_source", "mapping_snapshot_hash", "product_bindings", "resource_bindings", "operations", "capture_profile", "connector_requirement", "manifest_hash"))

COMPOSE_OUTPUT = obj({
    "status": {"type": "string", "enum": ["composed", "unresolved"]},
    "problems": {"type": "array", "items": BINDING_PROBLEM, "maxItems": 10500},
    **MANIFEST["properties"],
}, ("status", "problems"))
PREFLIGHT_PROBLEM = obj({
    "code": STRING, "expected": {"type": ["string", "null"]},
    "actual": {"type": ["string", "null"]},
}, ("code", "expected", "actual"))
CAPTURE_STEP = obj({
    "operation_id": STRING, "sequence": NONNEGATIVE_INTEGER,
    "status": {"type": "string", "enum": ["queued", "running", "completed", "failed", "skipped", "cancelled", "outcome_unknown"]},
    "attempt": POSITIVE_INTEGER,
    "artifact_ref": {"anyOf": [ARTIFACT_REF, {"type": "null"}]},
    "artifact_attached": {"type": "boolean"}, "expected_scene_hash": HASH,
}, ("operation_id", "sequence", "status", "attempt", "artifact_ref", "artifact_attached", "expected_scene_hash"))
CAPTURE_RUN = obj({
    "capture_run_id": STRING, "environment_id": STRING, "environment_version": POSITIVE_INTEGER,
    "manifest_hash": HASH, "device_id": STRING, "plan_id": STRING,
    "status": {"type": "string", "enum": ["queued", "leased", "running", "cancelling", "completed", "partial", "failed", "cancelled", "outcome_unknown"]},
    "operation_ref": OPERATION_REF,
    "steps": {"type": "array", "items": CAPTURE_STEP, "maxItems": 3000},
}, ("capture_run_id", "environment_id", "environment_version", "manifest_hash", "device_id", "plan_id", "status", "operation_ref", "steps"))
DOCUMENT_SNAPSHOT_NODE = obj({
    "node_key": STRING, "parent_key": {"type": ["string", "null"]},
    "product_ref": STRING, "child_order": NONNEGATIVE_INTEGER,
}, ("node_key", "parent_key", "product_ref", "child_order"))
DOCUMENT_SNAPSHOT = obj({
    "document_id": STRING, "root_node_key": STRING, "source_identity": STRING,
    "snapshot_hash": HASH,
    "nodes": {"type": "array", "items": DOCUMENT_SNAPSHOT_NODE, "maxItems": 10000},
}, ("document_id", "root_node_key", "source_identity", "snapshot_hash", "nodes"))
DOCUMENT_SNAPSHOT_REQUEST = obj({
    "snapshot_request_id": STRING, "device_id": STRING, "plan_id": STRING,
    "status": {"type": "string", "enum": ["queued", "completed", "failed", "outcome_unknown"]},
    "snapshot": {"anyOf": [DOCUMENT_SNAPSHOT, {"type": "null"}]},
    "failure_code": STRING, "operation_ref": OPERATION_REF,
}, ("snapshot_request_id", "device_id", "plan_id", "status", "snapshot", "failure_code", "operation_ref"))


INPUT_SCHEMAS = {
    "simulation.parameter_set.create": obj({"name": STRING, "parameters": {"type": "array", "items": PARAMETER}}, ("name", "parameters")),
    "simulation.parameter_set.get": obj({"parameter_set_ref": PARAMETER_SET_REF}, ("parameter_set_ref",)),
    "simulation.parameter_set.search": obj({"query": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    "simulation.solver_profile.create": obj({"name": STRING, "solver": STRING, "solver_version": STRING, "settings": {"type": "array", "items": SETTING}}, ("name", "solver", "solver_version", "settings")),
    "simulation.solver_profile.get": obj({"simulation_profile_ref": PROFILE_REF}, ("simulation_profile_ref",)),
    "simulation.solver_profile.search": obj({"query": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    "simulation.environment.create": obj({"name": STRING, "execution_plan_ref": EXECUTION_PLAN_REF, "model_snapshot_ref": MODEL_SNAPSHOT_REF, "parameter_set_ref": PARAMETER_SET_REF, "simulation_profile_ref": PROFILE_REF}, ("name", "execution_plan_ref", "model_snapshot_ref", "parameter_set_ref", "simulation_profile_ref")),
    "simulation.environment.get": obj({"environment_id": STRING}, ("environment_id",)),
    "simulation.environment.search": obj({"limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    "simulation.environment.archive": obj({"environment_id": STRING}, ("environment_id",)),
    "simulation.run.start": obj({"environment_id": STRING}, ("environment_id",)),
    "simulation.run.get": obj({"run_id": STRING}, ("run_id",)),
    "simulation.run.search": obj({"environment_id": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    "simulation.result.get": obj({"run_id": STRING}, ("run_id",)),
    "simulation.result.compare": obj({"left_result_ref": RESULT_REF, "right_result_ref": RESULT_REF}, ("left_result_ref", "right_result_ref")),
    "simulation.environment.compose": obj({
        "name": STRING, "device_id": STRING, "execution_plan_ref": EXECUTION_PLAN_REF,
        "snapshot_request_id": STRING, "capture_profile": CAPTURE_PROFILE,
    }, ("name", "device_id", "execution_plan_ref", "snapshot_request_id", "capture_profile")),
    "simulation.document_snapshot.request": obj({"device_id": STRING, "request_key": STRING}, ("device_id", "request_key")),
    "simulation.document_snapshot.get": obj({"snapshot_request_id": STRING}, ("snapshot_request_id",)),
    "simulation.environment.manifest.get": obj({"environment_id": STRING, "environment_version": POSITIVE_INTEGER}, ("environment_id", "environment_version")),
    "simulation.environment.manifest.search": obj({"limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    "simulation.environment.manifest.archive": obj({"environment_id": STRING}, ("environment_id",)),
    "simulation.environment.preflight": obj({"environment_id": STRING, "environment_version": POSITIVE_INTEGER, "device_id": STRING}, ("environment_id", "environment_version", "device_id")),
    "simulation.environment.materialize": obj({"environment_id": STRING, "environment_version": POSITIVE_INTEGER, "device_id": STRING}, ("environment_id", "environment_version", "device_id")),
    "simulation.capture_run.start": obj({"environment_id": STRING, "environment_version": POSITIVE_INTEGER, "device_id": STRING}, ("environment_id", "environment_version", "device_id")),
    "simulation.capture_run.get": obj({"capture_run_id": STRING}, ("capture_run_id",)),
    "simulation.capture_run.cancel": obj({"capture_run_id": STRING}, ("capture_run_id",)),
    "simulation.capture_step.retry": obj({"capture_run_id": STRING, "operation_id": STRING}, ("capture_run_id", "operation_id")),
}

OUTPUT_SCHEMAS = {
    "simulation.document_snapshot.request": DOCUMENT_SNAPSHOT_REQUEST,
    "simulation.document_snapshot.get": DOCUMENT_SNAPSHOT_REQUEST,
    "simulation.parameter_set.create": PARAMETER_SET,
    "simulation.parameter_set.get": PARAMETER_SET,
    "simulation.parameter_set.search": obj({"items": {"type": "array", "items": PARAMETER_SET}, "total": INTEGER, "query": STRING}, ("items", "total", "query")),
    "simulation.solver_profile.create": SOLVER_PROFILE,
    "simulation.solver_profile.get": SOLVER_PROFILE,
    "simulation.solver_profile.search": obj({"items": {"type": "array", "items": SOLVER_PROFILE}, "total": INTEGER, "query": STRING}, ("items", "total", "query")),
    "simulation.environment.create": ENVIRONMENT,
    "simulation.environment.get": ENVIRONMENT,
    "simulation.environment.search": obj({"items": {"type": "array", "items": ENVIRONMENT}, "total": INTEGER}, ("items", "total")),
    "simulation.environment.archive": ENVIRONMENT,
    "simulation.run.start": RUN,
    "simulation.run.get": RUN,
    "simulation.run.search": obj({"items": {"type": "array", "items": RUN}, "total": INTEGER}, ("items", "total")),
    "simulation.result.get": RESULT,
    "simulation.result.compare": obj({"left_result_ref": RESULT_REF, "right_result_ref": RESULT_REF, "same_inputs": {"type": "boolean"}, "changes": {"type": "array", "items": RESULT_CHANGE}}, ("left_result_ref", "right_result_ref", "same_inputs", "changes")),
    "simulation.environment.compose": COMPOSE_OUTPUT,
    "simulation.environment.manifest.get": MANIFEST,
    "simulation.environment.manifest.search": obj({"items": {"type": "array", "items": MANIFEST, "maxItems": 200}, "total": NONNEGATIVE_INTEGER}, ("items", "total")),
    "simulation.environment.manifest.archive": obj({"environment_id": STRING, "status": {"type": "string", "enum": ["archived"]}}, ("environment_id", "status")),
    "simulation.environment.preflight": obj({"compatible": {"type": "boolean"}, "problems": {"type": "array", "items": PREFLIGHT_PROBLEM, "maxItems": 128}}, ("compatible", "problems")),
    "simulation.environment.materialize": obj({
        "run_id": STRING, "environment_id": STRING, "environment_version": POSITIVE_INTEGER,
        "manifest_hash": HASH, "device_id": STRING, "plan_id": STRING,
        "status": {"type": "string", "enum": ["queued"]}, "operation_ref": OPERATION_REF,
    }, ("run_id", "environment_id", "environment_version", "manifest_hash", "device_id", "plan_id", "status", "operation_ref")),
    "simulation.capture_run.start": CAPTURE_RUN,
    "simulation.capture_run.get": CAPTURE_RUN,
    "simulation.capture_run.cancel": obj({"capture_run_id": STRING, "status": {"type": "string", "enum": ["cancelling", "cancelled"]}}, ("capture_run_id", "status")),
    "simulation.capture_step.retry": obj({
        "capture_run_id": STRING, "operation_id": STRING, "attempt": POSITIVE_INTEGER,
        "plan_id": STRING, "status": {"type": "string", "enum": ["queued"]},
    }, ("capture_run_id", "operation_id", "attempt", "plan_id", "status")),
}

__all__ = ["INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
