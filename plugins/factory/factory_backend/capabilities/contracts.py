"""Closed shared schemas for Factory capabilities."""

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "gid": {"type": "string"},
        "expected_version": {"type": "integer", "minimum": 1},
        "expected_revision": {"type": "integer", "minimum": 1},
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["data"],
    "properties": {"data": {}},
}

