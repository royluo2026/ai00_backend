from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from ..application.outcomes import knowledge_outcomes
from ..provider import register_capability


CAPABILITY_IDS = (
    "knowledge.entry.change.apply", "knowledge.space.change.apply",
    "knowledge.document.archive", "knowledge.personalization.change.apply",
    "knowledge.personalization.read", "knowledge.hub.read", "knowledge.hub.change.apply",
)
_STRING = {"type": "string"}
_TAGS = {"type": "array", "items": _STRING, "maxItems": 100}
_LIST = {"type": "array", "items": {"type": "object", "additionalProperties": True}, "maxItems": 500}
_STRING_LIST = {"type": "array", "items": _STRING, "maxItems": 500}
_JSON_OBJECT = {"type": "object", "additionalProperties": True}
_TEXT = {"type": ["string", "null"]}
_BOOL = {"type": ["boolean", "null"]}
_INT = {"type": ["integer", "null"]}
_JSON = {"type": ["object", "array", "string", "null"]}


def _record(properties):
    return {"type": "object", "properties": properties, "additionalProperties": False}


_FOLDER = _record({
    "gid": _TEXT, "parent_gid": _TEXT, "scope_type": _TEXT, "team_gid": _TEXT,
    "name": _TEXT, "sort_order": _INT, "creator_gid": _TEXT,
    "created_at": _TEXT, "updated_at": _TEXT,
})
_ITEM = _record({
    "gid": _TEXT, "folder_gid": _TEXT, "scope_type": _TEXT, "team_gid": _TEXT,
    "item_type": _TEXT, "title": _TEXT, "status": _TEXT,
    "content_body": _JSON, "content_md": _TEXT, "file_path": _TEXT, "url": _TEXT,
    "site_ref": _JSON, "tags": _JSON, "is_system": _BOOL, "is_pinned": _BOOL,
    "is_hidden": _BOOL, "creator_gid": _TEXT, "created_at": _TEXT,
    "updated_at": _TEXT, "personalization_at": _TEXT,
})
_HISTORY = _record({
    "gid": _TEXT, "id": _INT, "author_name": _TEXT, "content": _TEXT,
    "created_at": _TEXT,
})
_GID = _record({"gid": _TEXT})
_CHANGED = _record({"changed": {"type": "boolean"}})
_DELETED = _record({"deleted": {"type": "boolean"}})
_ARCHIVED = _record({"archived": {"type": "boolean"}})

OUTPUT_SCHEMAS = {
    ("knowledge.entry.change.apply", "entries.create"): _GID,
    ("knowledge.entry.change.apply", "entries.update"): _CHANGED,
    ("knowledge.entry.change.apply", "entries.delete"): _DELETED,
    ("knowledge.space.change.apply", "spaces.update"): _CHANGED,
    ("knowledge.space.change.apply", "spaces.archive"): _ARCHIVED,
    ("knowledge.document.archive", "documents.archive"): _ARCHIVED,
    ("knowledge.personalization.change.apply", "favorites.toggle"): _record({"favorite": {"type": "boolean"}}),
    ("knowledge.personalization.change.apply", "recent.record"): _record({"recorded": {"type": "boolean"}}),
    ("knowledge.personalization.read", "favorites.list"): _record({"items": {"type": "array", "maxItems": 200, "items": _ITEM}}),
    ("knowledge.personalization.read", "recent.list"): _record({"items": {"type": "array", "maxItems": 200, "items": _ITEM}}),
    ("knowledge.hub.read", "folders.list"): _record({"items": {"type": "array", "maxItems": 500, "items": _FOLDER}}),
    ("knowledge.hub.read", "items.list"): _record({"items": {"type": "array", "maxItems": 500, "items": _ITEM}}),
    ("knowledge.hub.read", "items.get"): _ITEM,
    ("knowledge.hub.read", "items.history.get"): _record({"items": {"type": "array", "maxItems": 500, "items": _HISTORY}}),
    ("knowledge.hub.change.apply", "folders.create"): _FOLDER,
    ("knowledge.hub.change.apply", "folders.update"): _CHANGED,
    ("knowledge.hub.change.apply", "folders.delete"): _record({"deleted_folders": {"type": "integer"}}),
    ("knowledge.hub.change.apply", "items.create"): _ITEM,
    ("knowledge.hub.change.apply", "items.update"): _CHANGED,
    ("knowledge.hub.change.apply", "items.delete"): _DELETED,
}


def _transport(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {
            key: (bool(item) if key in {"is_system", "is_pinned", "is_hidden"} and item is not None else _transport(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_transport(item) for item in value]
    return value


def _data_output(schema):
    output = _record({"data": schema})
    output["required"] = ["data"]
    return output
_ENTRY_UPDATES = {
    "type": "object",
    "properties": {
        "title": _STRING, "entry_type": _STRING, "status": _STRING,
        "share_scope": _STRING, "list_gid": _STRING, "source_gid": _STRING,
        "source_label": _STRING, "maintainer_gid": _STRING,
        "contributors": _LIST, "attachments": _LIST, "tags": _TAGS,
        "content_ref": _JSON_OBJECT, "content_md": _STRING,
        "related_part_nos": _STRING_LIST, "related_operation_gids": _STRING_LIST,
        "context_class_gid": _STRING,
    },
    "additionalProperties": False,
}
_SPACE_UPDATES = {
    "type": "object",
    "properties": {"name": _STRING, "visibility": _STRING},
    "additionalProperties": False,
}
_FOLDER_UPDATES = {
    "type": "object",
    "properties": {"name": {"type": "string", "maxLength": 512}, "sort_order": {"type": "integer", "minimum": -1000000, "maximum": 1000000}, "parent_gid": _STRING},
    "additionalProperties": False,
}
_ITEM_UPDATES = {
    "type": "object",
    "properties": {
        "folder_gid": _STRING, "title": {"type": "string", "maxLength": 512}, "status": _STRING,
        "content_body": {"type": "object", "additionalProperties": True}, "content_md": {"type": "string", "maxLength": 200000},
        "file_path": _STRING, "url": _STRING, "site_ref": {"type": "object", "additionalProperties": True},
        "tags": _TAGS, "is_pinned": {"type": "boolean"}, "is_hidden": {"type": "boolean"},
        "scope_type": _STRING, "team_gid": _STRING,
    },
    "additionalProperties": False,
}


def _schema(operations, properties):
    return {
        "type": "object",
        "required": ["operation", "arguments"],
        "properties": {
            "operation": {"type": "string", "enum": list(operations)},
            "arguments": {
                "type": "object", "properties": properties,
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


SCHEMAS = {
    "knowledge.entry.change.apply": _schema(
        ("entries.create", "entries.update", "entries.delete"),
        {"gid": _STRING, "title": _STRING, "entry_type": _STRING,
         "status": _STRING, "share_scope": _STRING, "list_gid": _STRING,
         "source_gid": _STRING, "source_label": _STRING, "maintainer_gid": _STRING,
         "contributors": _LIST, "attachments": _LIST, "tags": _TAGS,
         "content_ref": _JSON_OBJECT, "content_md": _STRING,
         "related_part_nos": _STRING_LIST, "related_operation_gids": _STRING_LIST,
         "context_class_gid": _STRING, "updates": _ENTRY_UPDATES},
    ),
    "knowledge.space.change.apply": _schema(
        ("spaces.update", "spaces.archive"),
        {"gid": _STRING, "updates": _SPACE_UPDATES},
    ),
    "knowledge.document.archive": _schema(("documents.archive",), {"gid": _STRING}),
    "knowledge.personalization.change.apply": _schema(
        ("favorites.toggle", "recent.record"), {"gid": _STRING}
    ),
    "knowledge.personalization.read": _schema(("favorites.list", "recent.list"), {"limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    "knowledge.hub.read": _schema(
        ("folders.list", "items.list", "items.get", "items.history.get"),
        {"gid": _STRING, "folder_gid": _STRING, "scope_type": _STRING, "team_gid": _STRING,
         "show_hidden": {"type": "boolean"}, "q": _STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
    ),
    "knowledge.hub.change.apply": _schema(
        ("folders.create", "folders.update", "folders.delete", "items.create", "items.update", "items.delete"),
        {"gid": _STRING, "parent_gid": _STRING, "scope_type": _STRING, "team_gid": _STRING,
         "name": {"type": "string", "maxLength": 512}, "sort_order": {"type": "integer", "minimum": -1000000, "maximum": 1000000},
         "folder_gid": _STRING, "item_type": _STRING, "title": {"type": "string", "maxLength": 512},
         "status": _STRING, "content_body": {"type": "object", "additionalProperties": True}, "content_md": {"type": "string", "maxLength": 200000},
         "file_path": _STRING, "url": _STRING, "site_ref": {"type": "object", "additionalProperties": True},
         "tags": _TAGS, "updates": _ITEM_UPDATES},
    ),
}


def register_reviewed_capabilities(registry):
    for capability_id in CAPABILITY_IDS:
        read = capability_id.endswith(".read")
        spec = CapabilitySpec(
            id=capability_id, owner="knowledge", description=f"Execute {capability_id}.",
            use_when="A governed consumer needs this Knowledge outcome.", do_not_use_when="The resource belongs to another domain.",
            risk=CapabilityRisk.READ if read else CapabilityRisk.WRITE, confirmation="none" if read else "user",
            permissions=("knowledge.read",) if read else ("knowledge.write",), input_schema=SCHEMAS[capability_id],
            output_schema=_data_output({"anyOf": [OUTPUT_SCHEMAS[(capability_id, operation)] for operation in SCHEMAS[capability_id]["properties"]["operation"]["enum"]]}), tags=("knowledge",), plugin_callable=True,
        )
        def handler(payload, context, *, _id=capability_id): return {"data": _transport(knowledge_outcomes.invoke(_id, payload, context))}
        register_capability(registry, spec, handler)

    # Publish one fixed-operation capability per reviewed operation.  The
    # historical envelope remains available only as a compatibility facade;
    # new consumers cannot choose an arbitrary operation string.
    for capability_id in CAPABILITY_IDS:
        schema = SCHEMAS[capability_id]
        operation_schema = schema["properties"]["operation"]
        argument_schema = schema["properties"]["arguments"]
        for operation in operation_schema.get("enum", []):
            atomic_id = f"{capability_id}.atomic.{operation.replace('.', '_')}"
            confirmation = (
                "none"
                if capability_id.endswith(".read")
                or (capability_id == "knowledge.personalization.change.apply" and operation == "recent.record")
                else "user"
            )
            atomic_spec = CapabilitySpec(
                id=atomic_id, owner="knowledge", description=f"Execute Knowledge operation {operation}.",
                use_when="A governed consumer needs exactly this Knowledge operation.",
                do_not_use_when="The request selects another operation or domain.",
                risk=CapabilityRisk.READ if capability_id.endswith(".read") else CapabilityRisk.WRITE,
                confirmation=confirmation,
                permissions=("knowledge.read",) if capability_id.endswith(".read") else ("knowledge.write",),
                input_schema={"type": "object", "properties": argument_schema.get("properties", {}), "additionalProperties": False},
                output_schema=_data_output(OUTPUT_SCHEMAS[(capability_id, operation)]),
                tags=("knowledge", "atomic", operation), plugin_callable=True,
            )
            def atomic_handler(payload, context, *, _id=capability_id, _operation=operation):
                arguments = payload.get("arguments", payload) if isinstance(payload, dict) else {}
                return {"data": _transport(knowledge_outcomes.invoke(_id, {"operation": _operation, "arguments": arguments}, context))}
            register_capability(registry, atomic_spec, atomic_handler)
