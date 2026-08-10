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


INPUT_SCHEMAS = {
    "simulation.parameter_set.create": obj({"name": STRING, "parameters": {"type": "array", "items": PARAMETER}}, ("name", "parameters")),
    "simulation.parameter_set.get": obj({"parameter_set_ref": PARAMETER_SET_REF}, ("parameter_set_ref",)),
    "simulation.profile.create": obj({"name": STRING, "solver": STRING, "solver_version": STRING, "settings": {"type": "array", "items": SETTING}}, ("name", "solver", "solver_version", "settings")),
    "simulation.profile.get": obj({"simulation_profile_ref": PROFILE_REF}, ("simulation_profile_ref",)),
    "simulation.environment.create": obj({"name": STRING, "execution_plan_ref": EXECUTION_PLAN_REF, "model_snapshot_ref": MODEL_SNAPSHOT_REF, "parameter_set_ref": PARAMETER_SET_REF, "simulation_profile_ref": PROFILE_REF}, ("name", "execution_plan_ref", "model_snapshot_ref", "parameter_set_ref", "simulation_profile_ref")),
    "simulation.environment.get": obj({"environment_id": STRING}, ("environment_id",)),
    "simulation.environment.list": obj({"limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    "simulation.run.start": obj({"environment_id": STRING}, ("environment_id",)),
    "simulation.run.get": obj({"run_id": STRING}, ("run_id",)),
    "simulation.result.get": obj({"run_id": STRING}, ("run_id",)),
}

OUTPUT_SCHEMAS = {
    "simulation.parameter_set.create": obj({"parameter_set_ref": PARAMETER_SET_REF, "name": STRING, "parameters": {"type": "array", "items": PARAMETER}}, ("parameter_set_ref", "name", "parameters")),
    "simulation.parameter_set.get": obj({"parameter_set_ref": PARAMETER_SET_REF, "name": STRING, "parameters": {"type": "array", "items": PARAMETER}}, ("parameter_set_ref", "name", "parameters")),
    "simulation.profile.create": obj({"simulation_profile_ref": PROFILE_REF, "name": STRING, "solver": STRING, "solver_version": STRING, "settings": {"type": "array", "items": SETTING}}, ("simulation_profile_ref", "name", "solver", "solver_version", "settings")),
    "simulation.profile.get": obj({"simulation_profile_ref": PROFILE_REF, "name": STRING, "solver": STRING, "solver_version": STRING, "settings": {"type": "array", "items": SETTING}}, ("simulation_profile_ref", "name", "solver", "solver_version", "settings")),
    "simulation.environment.create": ENVIRONMENT,
    "simulation.environment.get": ENVIRONMENT,
    "simulation.environment.list": obj({"items": {"type": "array", "items": ENVIRONMENT}, "total": INTEGER}, ("items", "total")),
    "simulation.run.start": RUN,
    "simulation.run.get": RUN,
    "simulation.result.get": obj({"run_id": STRING, "status": STRING, "source_fingerprint": HASH, "result_artifact_refs": {"type": "array", "items": ARTIFACT_REF}}, ("run_id", "status", "source_fingerprint", "result_artifact_refs")),
}

__all__ = ["INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
