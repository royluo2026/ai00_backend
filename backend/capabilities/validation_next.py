"""Small dependency-free JSON payload validator for capability boundaries."""
from __future__ import annotations
from typing import Any

def validate_payload(schema: dict[str, Any], payload: Any, *, label: str = "payload") -> None:
    if not schema:
        return
    expected = schema.get("type")
    if expected == "object" and not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    if expected == "array" and not isinstance(payload, list):
        raise ValueError(f"{label} must be an array")
    if expected == "string" and not isinstance(payload, str):
        raise ValueError(f"{label} must be a string")
    if expected == "integer" and (not isinstance(payload, int) or isinstance(payload, bool)):
        raise ValueError(f"{label} must be an integer")
    if not isinstance(payload, dict):
        return
    properties = schema.get("properties") or {}
    for name in schema.get("required") or []:
        if name not in payload:
            raise ValueError(f"{label} missing required field: {name}")
    for name, value in payload.items():
        field = properties.get(name) or {}
        field_type = field.get("type")
        if field_type == "string" and not isinstance(value, str):
            raise ValueError(f"{label} field {name} must be a string")
        if field_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"{label} field {name} must be an integer")
        if field_type == "object" and not isinstance(value, dict):
            raise ValueError(f"{label} field {name} must be an object")
