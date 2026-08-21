from __future__ import annotations

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
            output_schema={"type": "object", "required": ["data"], "properties": {"data": {}}}, tags=("knowledge",), plugin_callable=True,
        )
        def handler(payload, context, *, _id=capability_id): return {"data": knowledge_outcomes.invoke(_id, payload, context)}
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
            atomic_spec = CapabilitySpec(
                id=atomic_id, owner="knowledge", description=f"Execute Knowledge operation {operation}.",
                use_when="A governed consumer needs exactly this Knowledge operation.",
                do_not_use_when="The request selects another operation or domain.",
                risk=CapabilityRisk.READ if capability_id.endswith(".read") else CapabilityRisk.WRITE,
                confirmation="none" if capability_id.endswith(".read") else "user",
                permissions=("knowledge.read",) if capability_id.endswith(".read") else ("knowledge.write",),
                input_schema={"type": "object", "properties": argument_schema.get("properties", {}), "additionalProperties": False},
                output_schema={"type": "object", "required": ["data"], "properties": {"data": {}}},
                tags=("knowledge", "atomic", operation), plugin_callable=True,
            )
            def atomic_handler(payload, context, *, _id=capability_id, _operation=operation):
                arguments = payload.get("arguments", payload) if isinstance(payload, dict) else {}
                return {"data": knowledge_outcomes.invoke(_id, {"operation": _operation, "arguments": arguments}, context)}
            register_capability(registry, atomic_spec, atomic_handler)
