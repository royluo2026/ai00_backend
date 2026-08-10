"""Closed schemas for the Digital Model capability provider."""
from __future__ import annotations


def obj(properties: dict, required: tuple[str, ...] = ()) -> dict:
    value = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = list(required)
    return value


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
NUMBER = {"type": "number"}
ARTIFACT_REF = obj({
    "artifact_id": STRING, "media_type": STRING,
    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$", "example": "0" * 64},
    "byte_size": INTEGER, "version": INTEGER,
}, ("artifact_id", "media_type", "sha256", "byte_size", "version"))
GEOMETRY_SUMMARY = obj({
    "volume_mm3": NUMBER, "surface_area_mm2": NUMBER,
    "bounding_box_x_mm": NUMBER, "bounding_box_y_mm": NUMBER, "bounding_box_z_mm": NUMBER,
    "mass_kg": NUMBER,
})
COMPONENT = obj({
    "component_id": STRING, "parent_component_id": STRING, "name": STRING,
    "component_type": STRING, "geometry_summary": GEOMETRY_SUMMARY,
}, ("component_id", "name", "component_type", "geometry_summary"))
SNAPSHOT_REF = obj({
    "model_id": STRING, "version_id": STRING,
    "snapshot_hash": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$", "example": "sha256:" + "0" * 64},
    "artifact_ref": ARTIFACT_REF,
}, ("model_id", "version_id", "snapshot_hash", "artifact_ref"))
MODEL = obj({
    "model_id": STRING, "object_ref": STRING, "name": STRING, "project_ref": STRING,
    "latest_version_id": {"anyOf": [STRING, {"type": "null"}]},
}, ("model_id", "object_ref", "name", "project_ref", "latest_version_id"))

INPUT_SCHEMAS = {
    "digital_model.model.create": obj({"name": STRING, "project_ref": STRING}, ("name", "project_ref")),
    "digital_model.model.get": obj({"model_id": STRING}, ("model_id",)),
    "digital_model.model.search": obj({"query": STRING, "project_ref": STRING, "limit": INTEGER}),
    "digital_model.version.create": obj({
        "model_id": STRING, "version_label": STRING, "expected_head_version_id": STRING,
        "artifact_ref": ARTIFACT_REF, "components": {"type": "array", "items": COMPONENT},
    }, ("model_id", "version_label", "expected_head_version_id", "artifact_ref", "components")),
    "digital_model.snapshot.get": obj({"model_id": STRING, "version_id": STRING}, ("model_id", "version_id")),
    "digital_model.snapshot.compare": obj({
        "model_id": STRING, "from_version_id": STRING, "to_version_id": STRING,
    }, ("model_id", "from_version_id", "to_version_id")),
    "digital_model.component.search": obj({
        "model_id": STRING, "version_id": STRING, "query": STRING, "limit": INTEGER,
    }, ("model_id", "version_id")),
}

OUTPUT_SCHEMAS = {
    "digital_model.model.create": MODEL,
    "digital_model.model.get": MODEL,
    "digital_model.model.search": obj({"items": {"type": "array", "items": MODEL}, "total": INTEGER, "query": STRING}, ("items", "total", "query")),
    "digital_model.version.create": obj({"snapshot_ref": SNAPSHOT_REF, "version_label": STRING, "component_count": INTEGER}, ("snapshot_ref", "version_label", "component_count")),
    "digital_model.snapshot.get": obj({"snapshot_ref": SNAPSHOT_REF, "version_label": STRING, "components": {"type": "array", "items": COMPONENT}}, ("snapshot_ref", "version_label", "components")),
    "digital_model.snapshot.compare": obj({
        "model_id": STRING, "from_version_id": STRING, "to_version_id": STRING,
        "changes": {"type": "array", "items": {}}, "breaking": {"type": "boolean"},
    }, ("model_id", "from_version_id", "to_version_id", "changes", "breaking")),
    "digital_model.component.search": obj({"model_id": STRING, "version_id": STRING, "items": {"type": "array", "items": COMPONENT}, "total": INTEGER}, ("model_id", "version_id", "items", "total")),
}

__all__ = ["INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
