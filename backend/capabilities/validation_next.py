"""Small dependency-free JSON payload validator for capability boundaries."""
from __future__ import annotations
import re
from typing import Any


def validate_payload(schema: dict[str, Any], payload: Any, *, label: str = "payload") -> None:
    """Validate the supported JSON Schema boundary subset without echoing values."""
    if not schema:
        return
    _validate(schema, payload, label)


def _validate(schema: dict[str, Any], payload: Any, label: str) -> None:
    if "allOf" in schema:
        for branch in schema["allOf"]:
            _validate(branch, payload, label)
    if "anyOf" in schema and not _matching_branches(schema["anyOf"], payload, label):
        raise ValueError(f"{label} does not match any allowed schema")
    if "oneOf" in schema and _matching_branches(schema["oneOf"], payload, label) != 1:
        raise ValueError(f"{label} must match exactly one allowed schema")
    if "const" in schema and payload != schema["const"]:
        raise ValueError(f"{label} does not match the required constant")
    # Deprecated compatibility descriptors use enum=[] as an explicit
    # "operation vocabulary not frozen" marker; the Release Gate still
    # blocks those descriptors from new stable publication.
    if schema.get("enum") and payload not in schema["enum"]:
        raise ValueError(f"{label} is not an allowed value")

    expected = schema.get("type")
    if expected and not _is_type(payload, expected):
        raise ValueError(f"{label} must be {_type_label(expected)}")

    if isinstance(payload, str):
        if len(payload) < int(schema.get("minLength", 0)):
            raise ValueError(f"{label} is shorter than minLength")
        if "maxLength" in schema and len(payload) > int(schema["maxLength"]):
            raise ValueError(f"{label} is longer than maxLength")
        if "pattern" in schema and re.search(str(schema["pattern"]), payload) is None:
            raise ValueError(f"{label} does not match the required pattern")

    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        if "minimum" in schema and payload < schema["minimum"]:
            raise ValueError(f"{label} is below minimum")
        if "maximum" in schema and payload > schema["maximum"]:
            raise ValueError(f"{label} exceeds maximum")

    if isinstance(payload, list):
        if len(payload) < int(schema.get("minItems", 0)):
            raise ValueError(f"{label} has fewer items than allowed")
        if "maxItems" in schema and len(payload) > int(schema["maxItems"]):
            raise ValueError(f"{label} has more items than allowed")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(payload):
                _validate(item_schema, value, f"{label}[{index}]")

    if not isinstance(payload, dict):
        return
    properties = schema.get("properties") or {}
    for name in schema.get("required") or []:
        if name not in payload:
            raise ValueError(f"{label} missing required field: {name}")
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(payload) - set(properties))
        if unknown:
            raise ValueError(f"{label} contains unknown field: {unknown[0]}")
    for name, value in payload.items():
        field = properties.get(name)
        if isinstance(field, dict):
            _validate(field, value, f"{label}.{name}")


def _matching_branches(branches: list[dict[str, Any]], payload: Any, label: str) -> int:
    matches = 0
    for branch in branches:
        try:
            _validate(branch, payload, label)
        except ValueError:
            continue
        matches += 1
    return matches


def _is_type(value: Any, expected: str | list[str]) -> bool:
    if isinstance(expected, list):
        return any(_is_type(value, item) for item in expected)
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }.get(expected, lambda: False)()


def _type_label(expected: str | list[str]) -> str:
    if isinstance(expected, list):
        return "one of " + ", ".join(expected)
    article = "an" if expected in {"object", "array", "integer"} else "a"
    return f"{article} {expected}"
