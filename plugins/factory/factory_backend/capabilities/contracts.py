"""Closed shared schemas for Factory capabilities."""

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "gid": {"type": "string"},
        "resource_ref": {"type": "string"},
        "expected_version": {"type": "integer", "minimum": 1},
        "expected_revision": {"type": "integer", "minimum": 1},
        "kind": {
            "type": "string",
            "enum": ["factory", "section", "line", "station"],
        },
        "name": {"type": "string", "minLength": 1},
        "parent_gid": {"type": ["string", "null"]},
        "attributes": {"type": ["object"]},
        "updates": {"type": ["object"]},
        "resource_type": {
            "type": "string",
            "enum": ["equipment", "tool", "fixture"],
        },
        "status": {
            "type": "string",
            "enum": ["draft", "published", "deprecated", "in_use", "maintenance", "scrapped"],
        },
        "specification": {"type": ["object"]},
        "asset_no": {"type": "string", "minLength": 1},
        "asset_type": {
            "type": "string",
            "enum": ["equipment", "tool", "fixture"],
        },
        "catalog_gid": {"type": ["string", "null"]},
        "meta": {"type": ["object"]},
        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["data"],
    "properties": {"data": {}},
}
