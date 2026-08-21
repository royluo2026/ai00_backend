"""Closed transport contracts owned by the Craft provider."""
from __future__ import annotations

from typing import Any


def _object(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


def _fields(*names: str) -> dict[str, Any]:
    # Nullable legacy database columns deliberately use unconstrained leaf values;
    # the public object shape itself remains closed and versioned.
    return {
        name: {"description": "Provider-validated transport value."}
        for name in names
    }


STRING = {"type": "string", "minLength": 1}
INTEGER = {"type": "integer"}
BOOLEAN = {"type": "boolean"}
ARRAY = {
    "type": "array",
    "items": {"description": "Provider-validated transport value."},
}


SchemaKey = str | tuple[str, int]
INPUT_SCHEMAS: dict[SchemaKey, dict[str, Any]] = {
    "craft.bop.version.get": _object({"version_gid": STRING}, required=("version_gid",)),
    "craft.bop.version.list": _object({
        "project_gid": STRING,
        "factory_gid": STRING,
        "status": STRING,
        "query": {"type": "string"},
        "include_archived": BOOLEAN,
        "cursor": STRING,
        "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
    }),
    "craft.bop.execution_structure.get": _object(
        {"version_gid": STRING}, required=("version_gid",)
    ),
    "craft.bop.execution_structure.preview": _object(
        {"version_gid": STRING, "expected_revision": {"type": "integer", "minimum": 1}},
        required=("version_gid", "expected_revision"),
    ),
    "craft.bop.linked_parts.get": _object(
        {"version_gid": STRING}, required=("version_gid",)
    ),
    "craft.bop.work_package.get": _object(
        {
            "version_gid": STRING,
            "scope": _object(
                {"kind": {"type": "string", "enum": ["line", "station", "role"]}, "gid": STRING},
                required=("kind", "gid"),
            ),
        },
        required=("version_gid", "scope"),
    ),
    "craft.bop.version.compare": _object(
        {"from_version_gid": STRING, "to_version_gid": STRING},
        required=("from_version_gid", "to_version_gid"),
    ),
    "craft.pbom.part.search": _object(
        {"snapshot_gid": STRING, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
        required=("snapshot_gid",),
    ),
    "craft.gbop.item.search": _object(
        {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}
    ),
    "craft.gbop.item.usage.get": _object({"item_gid": STRING}, required=("item_gid",)),
    "craft.gbop.item.knowledge.list": _object({"item_gid": STRING}, required=("item_gid",)),
    "craft.bop.draft.change.preview": _object(
        {
            "version_gid": STRING,
            "expected_revision": {"type": "integer", "minimum": 1},
            "commands": ARRAY,
            "idempotency_key": STRING,
        },
        required=("version_gid", "expected_revision", "commands"),
    ),
    "craft.bop.draft.change.apply": _object(
        {"preview_gid": STRING, "idempotency_key": STRING}, required=("preview_gid",)
    ),
    "craft.bop.version.create": _object(
        {
            "source": {"type": "string", "enum": ["empty", "bop_version", "template", "import_preview"]},
            "version_tag": STRING,
            "bop_name": STRING,
            "source_gid": STRING,
            "template_gid": STRING,
            "import_preview_gid": STRING,
            "version_family_gid": STRING,
            "project_gid": STRING,
            "factory_gid": STRING,
            "vehicle_model_gid": STRING,
            "maturity": STRING,
            "takt_time": {"type": "number"},
            "version_type": STRING,
            "pbom_version_gid": STRING,
            "owner_gid": STRING,
            "data_stage": STRING,
        },
        required=("source", "version_tag"),
    ),
    "craft.bop.version.archive": _object(
        {"version_gid": STRING, "expected_revision": {"type": "integer", "minimum": 1}},
        required=("version_gid", "expected_revision"),
    ),
    "craft.bop.import.preview": _object(
        {
            "document": _object({
                "version_tag": {},
                "bop_name": {},
                "entries": ARRAY,
            })
        },
        required=("document",),
    ),
}


_VERSION_DETAIL = (
    "version_gid", "version_tag", "bop_name", "family_gid", "project_gid", "status",
    "lifecycle_phase", "revision", "updated_at", "archived", "factory_gid",
    "vehicle_model_gid", "parent_version_gid", "pbom_version_gid", "owner_gid",
    "version_type", "maturity", "data_stage", "visibility", "takt_time", "change_note",
    "lifecycle", "content_hash", "created_at",
)

_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_VERSION_SUMMARY_PROPERTIES = {
    "version_gid": {"type": "string", "minLength": 1},
    "version_tag": _NULLABLE_STRING,
    "bop_name": _NULLABLE_STRING,
    "family_gid": _NULLABLE_STRING,
    "project_gid": _NULLABLE_STRING,
    "factory_gid": _NULLABLE_STRING,
    "vehicle_model_gid": _NULLABLE_STRING,
    "parent_version_gid": _NULLABLE_STRING,
    "pbom_version_gid": _NULLABLE_STRING,
    "owner_gid": _NULLABLE_STRING,
    "status": _NULLABLE_STRING,
    "lifecycle_phase": _NULLABLE_STRING,
    "revision": {"anyOf": [
        {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "null"},
    ]},
    "version_type": _NULLABLE_STRING,
    "maturity": _NULLABLE_STRING,
    "data_stage": _NULLABLE_STRING,
    "visibility": _NULLABLE_STRING,
    "takt_time": {"description": "Provider-validated transport value."},
    "change_note": _NULLABLE_STRING,
    "frozen_at": _NULLABLE_STRING,
    "published_at": _NULLABLE_STRING,
    "archived_at": _NULLABLE_STRING,
    "created_at": _NULLABLE_STRING,
    "updated_at": _NULLABLE_STRING,
    "archived": {"type": "boolean"},
}
_VERSION_SUMMARY = _object(
    _VERSION_SUMMARY_PROPERTIES,
    required=tuple(_VERSION_SUMMARY_PROPERTIES),
)

OUTPUT_SCHEMAS: dict[SchemaKey, dict[str, Any]] = {
    "craft.bop.version.get": _object(_fields(*_VERSION_DETAIL), required=("version_gid", "revision", "lifecycle")),
    "craft.bop.version.list": _object({
        "items": {"type": "array", "items": _VERSION_SUMMARY},
        "next_cursor": _NULLABLE_STRING,
    }, required=("items", "next_cursor")),
    "craft.bop.execution_structure.get": _object(
        _fields("contract_id", "contract_version", "official", "source", "published_at", "nodes", "operations", "dependencies", "conditions", "content_hash"),
        required=("contract_id", "contract_version", "official", "source", "published_at", "nodes", "operations", "dependencies", "conditions", "content_hash"),
    ),
    "craft.bop.execution_structure.preview": _object(
        _fields("contract_id", "contract_version", "official", "source", "published_at", "nodes", "operations", "dependencies", "conditions", "content_hash"),
        required=("contract_id", "contract_version", "official", "source", "published_at", "nodes", "operations", "dependencies", "conditions", "content_hash"),
    ),
    "craft.bop.linked_parts.get": _object({
        "version_gid": _fields("version_gid")["version_gid"],
        "revision": _fields("revision")["revision"],
        "items": {"type": "array", "maxItems": 500, "items": {"description": "Provider-validated linked part."}},
        "legacy_items": {"type": "array", "maxItems": 500, "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": _fields(
                "gid", "name", "parent_gid", "part_no", "quantity", "unit",
                "snapshot_gid", "material", "meta", "entry_gid", "link_gid", "created_at",
            ),
        }},
        "legacy_pbom_items": {"type": "array", "maxItems": 500, "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": _fields(
                "gid", "title", "vpps", "parent_part_gid", "node_type", "bom_row_id",
                "seq_no", "quantity", "unit", "part_number", "created_at", "updated_at",
            ),
        }},
    }, required=("version_gid", "revision", "items")),
    "craft.bop.work_package.get": _object(
        _fields("version_gid", "revision", "scope", "work_items", "parts", "tools", "fixtures", "equipment_requirements", "knowledge_refs", "rule_refs"),
        required=("version_gid", "revision", "scope", "work_items", "parts", "tools", "fixtures", "equipment_requirements", "knowledge_refs", "rule_refs"),
    ),
    "craft.bop.version.compare": _object(
        _fields("comparability", "from_version_gid", "to_version_gid", "added", "removed", "moved", "changed"),
        required=("comparability", "from_version_gid", "to_version_gid", "added", "removed", "moved", "changed"),
    ),
    "craft.pbom.part.search": _object(_fields("snapshot_gid", "items"), required=("snapshot_gid", "items")),
    "craft.gbop.item.search": _object(_fields("active_release_gid", "items"), required=("active_release_gid", "items")),
    "craft.gbop.item.usage.get": _object(_fields("active_release_gid", "item_gid", "items"), required=("active_release_gid", "item_gid", "items")),
    "craft.gbop.item.knowledge.list": _object(_fields("active_release_gid", "item_gid", "items"), required=("active_release_gid", "item_gid", "items")),
    "craft.bop.draft.change.preview": _object(
        _fields("preview_gid", "version_gid", "base_revision", "commands", "before_hash", "after_hash", "payload_hash", "idempotency_key", "created_at", "expires_at"),
        required=("preview_gid", "version_gid", "base_revision", "commands", "before_hash", "after_hash", "payload_hash", "created_at", "expires_at"),
    ),
    "craft.bop.draft.change.apply": _object(
        _fields("version_gid", "revision", "before_hash", "after_hash", "preview_gid", "idempotency_key"),
        required=("version_gid", "revision", "before_hash", "after_hash", "preview_gid", "idempotency_key"),
    ),
    "craft.bop.version.create": _object(
        _fields("version_gid", "status", "revision", "parent_version_gid", "entries_count"),
        required=("version_gid", "status", "revision", "parent_version_gid", "entries_count"),
    ),
    "craft.bop.version.archive": _object(
        _fields("version_gid", "status", "revision", "before_hash", "after_hash"),
        required=("version_gid", "status", "revision", "before_hash", "after_hash"),
    ),
    "craft.bop.import.preview": _object(
        _fields("import_preview_gid", "content_hash", "entry_count", "expires_at"),
        required=("import_preview_gid", "content_hash", "entry_count", "expires_at"),
    ),
}

INPUT_SCHEMAS.update({
    "craft.pbom.version.create": _object(_fields("project_ref", "project_gid", "version_tag", "name", "source_type", "knowledge_revision_ref", "ontology_release_ref", "revision_commit_ref"), required=("project_ref", "version_tag")),
    "craft.pbom.version.get": _object({"version_gid": STRING}, required=("version_gid",)),
    "craft.pbom.version.search": _object(_fields("project_ref", "limit")),
    "craft.pbom.version.submit": _object({"version_gid": STRING}, required=("version_gid",)),
    "craft.pbom.version.publish": _object({"version_gid": STRING}, required=("version_gid",)),
    "craft.pbom.version.archive": _object({"version_gid": STRING}, required=("version_gid",)),
    "craft.pbom.version.compare": _object({"from_version_gid": STRING, "to_version_gid": STRING}, required=("from_version_gid", "to_version_gid")),
    "craft.pbom.draft.change.preview": _object(_fields("version_gid", "changes"), required=("version_gid", "changes")),
    "craft.pbom.draft.change.apply": _object(_fields("version_gid", "preview_gid", "changes"), required=("version_gid", "preview_gid", "changes")),
    "craft.pbom.part.search": _object(_fields("version_gid", "query", "limit"), required=("version_gid",)),
    "craft.pbom.import.preview": _object({"document": {}}, required=("document",)),
})

OUTPUT_SCHEMAS.update({
    "craft.pbom.version.create": _object(_fields("gid", "project_ref", "project_gid", "version_tag", "name", "source_type", "created_at", "meta", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.get": _object(_fields("gid", "project_ref", "project_gid", "version_tag", "name", "source_type", "created_at", "meta", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.search": _object({"items": ARRAY}, required=("items",)),
    "craft.pbom.version.submit": _object(_fields("gid", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.publish": _object(_fields("gid", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.archive": _object(_fields("gid", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.compare": _object(_fields("added", "removed", "changed"), required=("added", "removed", "changed")),
    "craft.pbom.draft.change.preview": _object(_fields("preview_gid", "version_gid", "changes"), required=("preview_gid", "version_gid", "changes")),
    "craft.pbom.draft.change.apply": _object(_fields("version_gid", "applied", "results"), required=("version_gid", "applied", "results")),
    "craft.pbom.part.search": _object({
        "version_gid": {"type": "string", "minLength": 1},
        "items": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    }, required=("version_gid", "items")),
    "craft.pbom.import.preview": _object(_fields("import_preview_gid", "content_sha256", "part_count"), required=("import_preview_gid", "content_sha256", "part_count")),
})

from .gbop_descriptors import GBOP_CAPABILITY_IDS
from .rule_descriptors import RULE_CAPABILITY_IDS
for _capability_id in (*GBOP_CAPABILITY_IDS, *RULE_CAPABILITY_IDS):
    INPUT_SCHEMAS.setdefault(_capability_id, _object(_fields("ref", "release_ref", "lineage_refs", "evidence", "item_gid", "query", "limit")))
    OUTPUT_SCHEMAS.setdefault(_capability_id, _object(_fields("capability_id", "ref", "release_ref", "status", "lineage_refs", "evidence", "active_release_gid", "item_gid", "items"), required=("status",) if _capability_id not in {"craft.gbop.item.search", "craft.gbop.item.usage.get", "craft.gbop.item.knowledge.list"} else ("items",)))

_GBOP_VERSION = _object(
    _fields(
        "gid", "name", "version_family_gid", "status", "frozen_at", "archived_at",
        "vehicle_model", "team_id", "created_by", "created_at", "updated_at",
    ),
    required=("gid", "name", "version_family_gid", "status"),
)
INPUT_SCHEMAS["craft.gbop.release.search"] = _object({"include_archived": BOOLEAN})
OUTPUT_SCHEMAS["craft.gbop.release.search"] = _object(
    {"items": {"type": "array", "items": _GBOP_VERSION, "maxItems": 500}},
    required=("items",),
)

from .reviewed_ids import CRAFT_REVIEWED_CAPABILITIES, DEPRECATED_REVIEWED_CAPABILITIES
for _capability_id in CRAFT_REVIEWED_CAPABILITIES:
    _operation_schema = {
        "type": "string",
        "enum": [] if _capability_id in DEPRECATED_REVIEWED_CAPABILITIES else None,
    }
    if _operation_schema["enum"] is None:
        _operation_schema.pop("enum")
    INPUT_SCHEMAS.setdefault(
        _capability_id,
        _object(
            {"operation": _operation_schema, "arguments": {"type": "object", "properties": {}, "additionalProperties": False}, "expected_version": INTEGER},
            required=("operation", "arguments"),
        ),
    )
    OUTPUT_SCHEMAS.setdefault(
        _capability_id,
        _object({"data": {}}, required=("data",)),
    )

INPUT_SCHEMAS["craft.data_exchange.export"] = _object(
    {
        "operation": {"type": "string", "enum": ["excel", "diff_report", "diff_lark_sheet"]},
        "template_config": {"type": "object"},
        "rows": {"type": "array", "maxItems": 5000},
        "filename": {"type": "string"},
        "columns": {"type": "array", "maxItems": 200},
        "diff_rows": {"type": "array", "maxItems": 5000},
        "label_a": {"type": "string"},
        "label_b": {"type": "string"},
        "user_access_token": {"type": "string", "minLength": 1},
        "spreadsheet_token": {"type": "string", "minLength": 1},
        "sheet_id": {"type": "string"},
    },
    required=("operation",),
)
OUTPUT_SCHEMAS["craft.data_exchange.export"] = _object(
    {
        "file_b64": {"type": "string"},
        "filename": {"type": "string"},
        "written_rows": {"type": "integer", "minimum": 0},
        "spreadsheet_token": {"type": "string"},
        "sheet_id": {"type": "string"},
    }
)

INPUT_SCHEMAS["craft.bop.fork_preset.change.apply"] = _object(
    {
        "operation": {"type": "string", "enum": ["create", "update", "delete"]},
        "gid": STRING,
        "name": STRING,
        "description": {"type": ["string", "null"]},
        "include_node_types": {"type": ["array", "null"]},
        "field_rules": {"type": "object"},
        "meta_key_rules": {"type": "object"},
        "team_gid": {"type": ["string", "null"]},
        "updates": {"type": "object"},
    },
    required=("operation",),
)
OUTPUT_SCHEMAS["craft.bop.fork_preset.change.apply"] = _object(
    {"data": {"type": "object"}}, required=("data",)
)

INPUT_SCHEMAS["craft.bop.lifecycle.change.apply"] = _object(
    {
        "operation": {"type": "string", "enum": [
            "pbom_match.update", "vehicle_ops_stats.update",
            "pbom_diff_queue.generate", "pbom_diff_queue.item.update",
        ]},
        "version_gid": STRING,
        "pbom_version_gid": STRING,
        "unlinked_ignored": {"type": "integer", "minimum": 0},
        "confirmed": {"type": "integer", "minimum": 0},
        "skipped": {"type": "integer", "minimum": 0},
        "total": {"type": "integer", "minimum": 0},
        "pbom_base_gid": {"type": ["string", "null"]},
        "pbom_target_gid": STRING,
        "item_gid": STRING,
        "status": {"type": "string", "enum": ["pending", "done", "ignored"]},
        "note": {"type": ["string", "null"]},
    },
    required=("operation",),
)
OUTPUT_SCHEMAS["craft.bop.lifecycle.change.apply"] = _object({
    "success": {"type": "boolean"}, "pbom_match": {"type": "object"},
    "vehicle_ops_prep": {"type": "object"}, "item_gid": STRING,
    "status": {"type": "string"}, "inserted": {"type": "integer", "minimum": 0},
    "version_gid": STRING,
})


_NULLABLE_CURSOR = {"anyOf": [STRING, {"type": "null"}]}
_COUNT_PROPERTIES = {
    name: {"type": "integer", "minimum": 0}
    for name in ("stations", "roles", "processes", "operations", "parts", "resources")
}
_COUNT_SCHEMA = _object(_COUNT_PROPERTIES, required=tuple(_COUNT_PROPERTIES))
_OUTLINE_NODE = _object({
    "gid": STRING,
    "parent_gid": _NULLABLE_STRING,
    "node_type": STRING,
    "sort_order": {"type": "number"},
    "title": _NULLABLE_STRING,
})
_OUTLINE_LINE = _object({
    **_OUTLINE_NODE["properties"],
    "counts": _COUNT_SCHEMA,
}, required=("gid", "parent_gid", "node_type", "sort_order", "title", "counts"))
_REF_ARRAY = {"type": "array", "items": STRING}
_WORK_NODE = _object({
    "gid": STRING, "parent_gid": _NULLABLE_STRING, "node_type": STRING,
    "sort_order": {"type": "number"}, "title": _NULLABLE_STRING,
    "vpps": _NULLABLE_STRING,
    **{name: _REF_ARRAY for name in (
        "part_refs", "tool_refs", "fixture_refs", "equipment_refs",
        "knowledge_refs", "rule_refs",
    )},
}, required=(
    "gid", "parent_gid", "node_type", "sort_order", "title", "vpps",
    "part_refs", "tool_refs", "fixture_refs", "equipment_refs", "knowledge_refs", "rule_refs",
))
_LINK = _object({
    "entry_gid": STRING, "link_type": STRING, "entity_gid": _NULLABLE_STRING,
    "is_primary": {"anyOf": [{"type": "boolean"}, {"type": "integer"}]},
}, required=("entry_gid", "link_type", "entity_gid", "is_primary"))
_ANY_JSON = {"type": ["object", "array", "string", "number", "boolean", "null"]}

INPUT_SCHEMAS.update({
    ("craft.bop.structure.outline.get", 1): _object({
        "version_gid": STRING, "revision": {"type": "integer", "minimum": 1},
        "cursor": STRING, "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
    }, required=("version_gid", "revision")),
    ("craft.bop.work_package.get", 2): _object({
        "version_gid": STRING, "revision": {"type": "integer", "minimum": 1},
        "scope_kind": {"type": "string", "enum": ["line", "station"]},
        "scope_gid": STRING, "cursor": STRING,
        "page_size": {"type": "integer", "minimum": 1, "maximum": 200},
    }, required=("version_gid", "revision", "scope_kind", "scope_gid")),
    ("craft.bop.entry.detail.get", 1): _object({
        "version_gid": STRING, "revision": {"type": "integer", "minimum": 1},
        "entry_gid": STRING,
    }, required=("version_gid", "revision", "entry_gid")),
})
OUTPUT_SCHEMAS.update({
    ("craft.bop.structure.outline.get", 1): _object({
        "version_gid": STRING, "revision": {"type": "integer", "minimum": 1},
        "root": {"anyOf": [_OUTLINE_NODE, {"type": "null"}]},
        "lines": {"type": "array", "maxItems": 100, "items": _OUTLINE_LINE},
        "total_lines": {"type": "integer", "minimum": 0}, "next_cursor": _NULLABLE_CURSOR,
    }, required=("version_gid", "revision", "root", "lines", "total_lines", "next_cursor")),
    ("craft.bop.work_package.get", 2): _object({
        "version_gid": STRING, "revision": {"type": "integer", "minimum": 1},
        "scope": _object({"kind": STRING, "gid": STRING}, required=("kind", "gid")),
        "nodes": {"type": "array", "maxItems": 200, "items": _WORK_NODE},
        "links": {"type": "array", "items": _LINK},
        "total_count": {"type": "integer", "minimum": 0}, "next_cursor": _NULLABLE_CURSOR,
    }, required=("version_gid", "revision", "scope", "nodes", "links", "total_count", "next_cursor")),
    ("craft.bop.entry.detail.get", 1): _object({
        "version_gid": STRING, "revision": {"type": "integer", "minimum": 1},
        "entry": _object({
            **_fields(
                "gid", "version_gid", "parent_gid", "node_type", "sort_order", "level",
                "ai00_level", "title", "vpps", "vpps_desc", "owner_gid", "created_at", "updated_at",
            ),
            "meta": _ANY_JSON, "process_flow_pic": _ANY_JSON, "process_chart_pic": _ANY_JSON,
        }, required=("gid", "version_gid", "node_type", "sort_order", "meta")),
        "links": {"type": "array", "maxItems": 500, "items": _object({
            **_LINK["properties"], "snapshot_data": _ANY_JSON,
        }, required=("entry_gid", "link_type", "entity_gid", "is_primary", "snapshot_data"))},
    }, required=("version_gid", "revision", "entry", "links")),
})

INPUT_SCHEMAS[("craft.library.read", 1)] = _object({
    "operation": {"type": "string", "enum": [
        "tools.list", "equipments.list", "fixtures.list", "fasteners.list", "part_names.list",
    ]},
    "q": {"type": "string", "maxLength": 200},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.library.read", 1)] = _object({
    "items": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "total": {"type": "integer", "minimum": 0, "maximum": 500},
    "operation": {"type": "string"},
}, required=("items", "total", "operation"))
_LIBRARY_CHANGE_OPERATIONS = [
    "tools.create", "tools.update", "tools.delete", "tools.obsolete",
    "equipments.create", "equipments.update", "equipments.obsolete",
    "fixtures.create", "fixtures.update", "fixtures.obsolete",
    "fasteners.create", "fasteners.update", "fasteners.delete",
    "part_names.create", "part_names.update", "part_names.delete",
    "part_names.batch_add_from_pbom", "part_names.batch_accept_alias", "part_names.accept_alias",
]
INPUT_SCHEMAS[("craft.library.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": _LIBRARY_CHANGE_OPERATIONS},
    "gid": {"type": "string", "maxLength": 128},
    "record": {"type": "object", "maxProperties": 40, "additionalProperties": True},
    "items": {"type": "array", "maxItems": 500, "items": {"type": "object", "maxProperties": 40, "additionalProperties": True}},
    "meta": {"type": "object", "maxProperties": 20, "additionalProperties": True},
    "alias": {"type": "string", "maxLength": 500},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.library.change.apply", 1)] = _object({
    "success": {"type": "boolean"}, "data": {"type": "object", "additionalProperties": True},
    "added": {"type": "integer", "minimum": 0}, "skipped": {"type": "integer", "minimum": 0},
    "processed": {"type": "integer", "minimum": 0}, "failed": {"type": "integer", "minimum": 0},
    "accepted_by": {"type": "string"}, "accepted_at": {"type": "string"},
}, required=("success",))
INPUT_SCHEMAS[("craft.canvas.read", 1)] = _object({
    "operation": {"type": "string", "enum": ["list", "get"]}, "gid": STRING,
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.canvas.read", 1)] = _object({
    "items": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "gid": STRING, "owner_gid": STRING, "title": {"type": "string"}, "is_shared": BOOLEAN,
    "updated_at": {"type": "string"}, "data": {"type": "object", "additionalProperties": True},
})
INPUT_SCHEMAS[("craft.canvas.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["save", "delete", "toggle_shared"]}, "gid": STRING,
    "record": {"type": "object", "maxProperties": 10, "additionalProperties": True},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.canvas.change.apply", 1)] = _object({"success": {"type": "boolean"}, "gid": STRING}, required=("success", "gid"))
INPUT_SCHEMAS[("craft.standard_operation.read", 1)] = _object({
    "operation": {"type": "string", "enum": ["list", "get"]}, "gid": STRING, "status": STRING,
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.standard_operation.read", 1)] = _object({
    "items": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "gid": STRING, "data": {"type": "object", "additionalProperties": True},
})
INPUT_SCHEMAS[("craft.standard_operation.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["create", "update", "delete", "publish", "deprecate"]},
    "gid": STRING, "record": {"type": "object", "maxProperties": 30, "additionalProperties": True},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.standard_operation.change.apply", 1)] = _object({"success": {"type": "boolean"}, "gid": STRING}, required=("success", "gid"))
INPUT_SCHEMAS[("craft.vpps_audit.read", 1)] = _object({
    "operation": {"type": "string", "enum": ["list", "rule4_ignores"]}, "pbom_version_gid": STRING, "operation_type": STRING,
}, required=("operation", "pbom_version_gid"))
OUTPUT_SCHEMAS[("craft.vpps_audit.read", 1)] = _object({
    "success": {"type": "boolean"}, "items": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "ignored_row_gids": {"type": "array", "maxItems": 500, "items": STRING}, "operations": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
})
INPUT_SCHEMAS[("craft.vpps_audit.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["rule4_bulk_ignore", "revert"]}, "gid": STRING, "pbom_version_gid": STRING,
    "rows": {"type": "array", "maxItems": 500, "items": {"type": "object", "maxProperties": 10, "additionalProperties": True}}, "actor_gid": STRING, "actor_name": STRING,
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.vpps_audit.change.apply", 1)] = _object({"success": {"type": "boolean"}, "created": {"type": "integer", "minimum": 0}, "operations": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "operation": {"type": "object", "additionalProperties": True}}, required=("success",))
INPUT_SCHEMAS[("craft.rule.engine.evaluate", 1)] = _object({
    "operation": {"type": "string", "enum": ["check", "audit"]}, "rule_gid": STRING,
    "context": {"type": "object", "maxProperties": 50, "additionalProperties": True}, "version_gid": STRING,
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.rule.engine.evaluate", 1)] = _object({
    "rule_gid": STRING, "rule_name": STRING, "result": STRING, "message": STRING, "enforcement_level": STRING,
    "version_gid": STRING, "total_entries": {"type": "integer", "minimum": 0}, "violation_count": {"type": "integer", "minimum": 0},
    "violations": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
})
INPUT_SCHEMAS[("craft.bop.pbom.change_point.get", 1)] = _object({
    "operation": {"type": "string", "enum": ["get"]}, "version_gid": STRING,
}, required=("operation", "version_gid"))
OUTPUT_SCHEMAS[("craft.bop.pbom.change_point.get", 1)] = _object({
    "data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "reason": STRING, "current_pbom_version_gid": STRING, "reference_pbom_version_gid": STRING,
    "summary": {"type": "object", "additionalProperties": True},
}, required=("data",))
INPUT_SCHEMAS[("craft.rule.library.read", 1)] = _object({
    "operation": {"type": "string", "enum": ["list", "get"]}, "gid": STRING, "status": STRING, "list_gid": STRING,
    "q": {"type": "string", "maxLength": 200}, "limit": {"type": "integer", "minimum": 1, "maximum": 500},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.rule.library.read", 1)] = _object({"success": {"type": "boolean"}, "data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("success", "data"))
INPUT_SCHEMAS[("craft.rule.library.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["create", "update", "delete"]}, "gid": STRING, "record": {"type": "object", "maxProperties": 20, "additionalProperties": True},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.rule.library.change.apply", 1)] = _object({"success": {"type": "boolean"}, "data": {"type": "object", "additionalProperties": True}}, required=("success",))
INPUT_SCHEMAS[("craft.gbop.catalog.read", 1)] = _object({
    "operation": {"type": "string", "enum": ["entries.list", "processes.list", "operations.list", "entry_links.list"]}, "version_gid": STRING, "entry_gid": STRING,
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.gbop.catalog.read", 1)] = _object({
    "items": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "total": {"type": "integer", "minimum": 0, "maximum": 500}, "operation": STRING,
}, required=("items", "total", "operation"))
INPUT_SCHEMAS[("craft.gbop.navigation.read", 1)] = _object({
    "operation": {"type": "string", "enum": ["link_summary", "auto_link_status"]}, "pbom_version_gid": STRING,
}, required=("operation", "pbom_version_gid"))
OUTPUT_SCHEMAS[("craft.gbop.navigation.read", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.gbop.process_hierarchy.read", 1)] = _object({"pbom_version_gid": {"type": "string"}}, required=("pbom_version_gid",))
OUTPUT_SCHEMAS[("craft.gbop.process_hierarchy.read", 1)] = _object({"data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("data",))
INPUT_SCHEMAS[("craft.gbop.navigation.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["confirm", "auto_link"]}, "pbom_version_gid": {"type": "string"}}, required=("operation", "pbom_version_gid",))
OUTPUT_SCHEMAS[("craft.gbop.navigation.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.entry.search", 1)] = _object({"q": {"type": "string"}, "node_types": {"type": "array", "items": {"type": "string"}, "maxItems": 20}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}})
OUTPUT_SCHEMAS[("craft.bop.entry.search", 1)] = _object({"data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.alt_hierarchy.read", 1)] = _object({"version_gid": {"type": "string"}}, required=("version_gid",))
OUTPUT_SCHEMAS[("craft.bop.alt_hierarchy.read", 1)] = _object({"entries": {"type": "array", "maxItems": 1000, "items": {"type": "object", "additionalProperties": True}}}, required=("entries",))
INPUT_SCHEMAS[("craft.bop.line_operation_catia.read", 1)] = _object({"line_entry_gid": {"type": "string"}}, required=("line_entry_gid",))
OUTPUT_SCHEMAS[("craft.bop.line_operation_catia.read", 1)] = _object({"ok": {"type": "boolean"}, "data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("ok", "data"))
INPUT_SCHEMAS[("craft.bop.pbom_lifecycle.read", 1)] = _object({"operation": {"type": "string", "enum": ["link_stats", "diff_queue"]}, "gid": {"type": "string"}, "status": {"type": "string"}}, required=("operation", "gid"))
OUTPUT_SCHEMAS[("craft.bop.pbom_lifecycle.read", 1)] = _object({"linked": {"type": "integer"}, "total": {"type": "integer"}, "pbom_version_gid": {"type": "string"}, "data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}})
INPUT_SCHEMAS[("craft.bop.lifecycle.read", 1)] = _object({"operation": {"type": "string", "enum": ["history", "checkpoints", "line_history", "operation_log"]}, "gid": {"type": "string"}, "line_gid": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, required=("operation", "gid"))
OUTPUT_SCHEMAS[("craft.bop.lifecycle.read", 1)] = _object({"data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "latest_active_batch_id": {"type": ["string", "null"]}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.lifecycle.state.read", 1)] = _object({"version_gid": {"type": "string"}}, required=("version_gid",))
INPUT_SCHEMAS[("craft.bop.version.lifecycle.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["publish", "archive_family", "unarchive_family"]},
    "version_gid": {"type": "string"}, "family_gid": {"type": "string"},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.version.lifecycle.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.version.layout.change.apply", 1)] = _object({"version_gid": STRING, "config": {"type": "object", "additionalProperties": True}}, required=("version_gid", "config"))
OUTPUT_SCHEMAS[("craft.bop.version.layout.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.version.freeze.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["freeze", "unfreeze"]}, "version_gid": STRING}, required=("operation", "version_gid"))
OUTPUT_SCHEMAS[("craft.bop.version.freeze.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.entry_link.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["attach", "detach"]}, "entry_gid": STRING, "link_gid": STRING, "link_type": STRING, "entity_gid": STRING, "is_primary": BOOLEAN}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.entry_link.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.staging.lifecycle.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["demote", "promote"]}, "entry_gid": STRING, "staging_gid": STRING, "parent_gid": {"type": ["string", "null"]}, "sort_order": {"type": "number"}}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.staging.lifecycle.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.entry.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["update", "delete"]}, "entry_gid": STRING, "updates": {"type": "object", "additionalProperties": True}}, required=("operation", "entry_gid"))
OUTPUT_SCHEMAS[("craft.bop.entry.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}, "version_gid": STRING}, required=("data",))
INPUT_SCHEMAS[("craft.bop.picture.upload", 1)] = _object({"filename": STRING, "mime": STRING, "data_b64": STRING}, required=("filename", "mime", "data_b64"))
OUTPUT_SCHEMAS[("craft.bop.picture.upload", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.lifecycle.state.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["init.update", "phase.confirm"]}, "version_gid": STRING, "route": {"type": ["string", "null"]}, "checklist": {"type": "object", "additionalProperties": True}, "note": {"type": ["string", "null"]}}, required=("operation", "version_gid"))
OUTPUT_SCHEMAS[("craft.bop.lifecycle.state.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.lifecycle.checkpoint.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["create"]}, "version_gid": STRING, "line_gid": STRING, "label": {"type": ["string", "null"]}}, required=("operation", "version_gid", "line_gid"))
OUTPUT_SCHEMAS[("craft.bop.lifecycle.checkpoint.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.lifecycle.checkpoint.rollback.apply", 1)] = _object({"version_gid": STRING, "line_gid": STRING, "checkpoint_gid": STRING}, required=("version_gid", "line_gid", "checkpoint_gid"))
OUTPUT_SCHEMAS[("craft.bop.lifecycle.checkpoint.rollback.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.lifecycle.history.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["undo", "redo"]}, "version_gid": STRING, "line_gid": STRING}, required=("operation", "version_gid", "line_gid"))
OUTPUT_SCHEMAS[("craft.bop.lifecycle.history.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.lifecycle.step.rollback.apply", 1)] = _object({"version_gid": STRING, "step_key": {"type": "string", "enum": ["lines_added", "stations_added", "processes_added", "vpps_imported", "pbom_vpps_checked"]}, "pbom_version_gid": {"type": ["string", "null"]}}, required=("version_gid", "step_key"))
OUTPUT_SCHEMAS[("craft.bop.lifecycle.step.rollback.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.lifecycle.stats.refresh.apply", 1)] = _object({"version_gid": STRING}, required=("version_gid",))
OUTPUT_SCHEMAS[("craft.bop.lifecycle.stats.refresh.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.template.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["save_as_template", "update_from"]}, "source_version_gid": STRING, "template_gid": STRING, "factory_gid": STRING, "template_name": STRING, "copy_operator": {"type": "boolean"}}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.template.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}, "entries_count": INTEGER}, required=("data",))
INPUT_SCHEMAS[("craft.bop.version.snapshot.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["freeze_snapshot", "promote"]}, "version_gid": STRING, "target_data_stage": {"type": ["string", "null"]}, "change_note": {"type": ["string", "null"]}, "promote_to_m": {"type": "boolean"}, "bump_version_tag": {"type": "boolean"}, "same_stage": {"type": "boolean"}}, required=("operation", "version_gid"))
OUTPUT_SCHEMAS[("craft.bop.version.snapshot.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.fork.change.apply", 1)] = _object({"operation": {"type": "string", "enum": ["fork", "smart_fork", "stage_advance"]}, "source_version_gid": STRING, "target_version_tag": STRING, "target_bop_name": {"type": "string"}, "target_version_family_gid": {"type": ["string", "null"]}, "change_note": {"type": ["string", "null"]}, "include_node_types": {"type": ["array", "null"], "items": STRING}, "field_rules": {"type": "object", "additionalProperties": {"type": "string", "enum": ["inherit", "reset"]}}, "meta_key_rules": {"type": "object", "additionalProperties": {"type": "string", "enum": ["inherit", "reset"]}}, "version_type": {"type": ["string", "null"]}, "mode": {"type": ["string", "null"], "enum": ["minor_facelift", "new_model", None]}, "changed_part_gids": {"type": "array", "items": STRING}, "pbom_version_gid": {"type": ["string", "null"]}, "copy_depth": {"type": ["string", "null"]}, "stage_name": {"type": ["string", "null"]}}, required=("operation", "source_version_gid"))
OUTPUT_SCHEMAS[("craft.bop.fork.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}, "entries_count": INTEGER}, required=("data",))
INPUT_SCHEMAS[("craft.bop.entry.bulk.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["create", "purge", "import_tc", "copy", "copy_from_gbop", "auto_link", "entity_detail.patch", "history.rollback"]},
    "version_gid": STRING, "bop_version_gid": STRING, "source_gid": STRING, "gid": STRING, "log_gid": STRING,
    "mode": STRING, "step": STRING, "rows": {"type": "array", "maxItems": 5000, "items": {"type": "object", "additionalProperties": True}},
    "link_type": STRING, "ref_gid": STRING, "fields": {"type": "object", "additionalProperties": True},
    "parent_gid": {"type": ["string", "null"]}, "node_type": STRING, "sort_order": {"type": "number"}, "title": STRING,
    "vpps": {"type": ["string", "null"]}, "vpps_desc": {"type": ["string", "null"]}, "parent_bop_title": {"type": ["string", "null"]},
    "position": {"type": ["string", "null"]}, "meta": {"type": ["object", "null"], "additionalProperties": True},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.entry.bulk.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.gbop.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["match_confirm", "auto_link"]},
    "pbom_gid": STRING, "bop_gid": STRING,
    "matches": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.gbop.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.gbop.version.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["create", "update", "freeze", "archive_family", "unarchive_family", "fork"]},
    "gid": STRING, "family_gid": STRING, "source_gid": STRING, "updates": {"type": "object", "additionalProperties": True},
    "name": {"type": "string"}, "version_family_gid": {"type": ["string", "null"]}, "vehicle_model": {"type": "string"},
    "target_version_tag": {"type": "string"}, "target_bop_name": {"type": "string"}, "include_node_types": {"type": ["array", "null"], "items": STRING},
    "field_rules": {"type": "object", "additionalProperties": {"type": "string"}}, "meta_key_rules": {"type": "object", "additionalProperties": {"type": "string"}},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.gbop.version.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.gbop.entity.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["entry.create", "entry.update", "entry.delete", "process.create", "process.update", "process.delete", "operation.create", "operation.update", "operation.delete", "link.create", "link.delete"]},
    "gid": STRING, "version_gid": STRING, "updates": {"type": "object", "additionalProperties": True},
    "entry_gid": STRING, "link_type": STRING, "ref_gid": STRING, "is_primary": BOOLEAN,
    "parent_gid": {"type": ["string", "null"]}, "node_type": STRING, "seq_no": {"type": "number"}, "vpps": {"type": ["string", "null"]},
    "vpps_desc": {"type": "string"}, "op_code": {"type": "string"}, "op_name": {"type": "string"}, "process_gid": STRING,
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.gbop.entity.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.gbop.import.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["import_vpps_parts", "import_entries"]}, "version_gid": STRING,
    "levels": {"type": "array", "maxItems": 10, "items": INTEGER}, "entries": {"type": "array", "maxItems": 5000, "items": {"type": "object", "additionalProperties": True}},
}, required=("operation", "version_gid"))
OUTPUT_SCHEMAS[("craft.gbop.import.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.gbop.station_autolink.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["apply", "undo"]}, "bop_gid": STRING, "pbom_version_gid": {"type": ["string", "null"]},
    "line_gids": {"type": ["array", "null"], "items": STRING}, "mode": {"type": "string", "enum": ["soft", "hard"]},
}, required=("operation", "bop_gid"))
OUTPUT_SCHEMAS[("craft.gbop.station_autolink.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.gbop.import.tc.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["import_tc_excel"]}, "version_gid": STRING, "filename": STRING, "content_b64": STRING,
}, required=("operation", "version_gid", "content_b64"))
OUTPUT_SCHEMAS[("craft.gbop.import.tc.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.staging.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["create", "update", "delete"]}, "version_gid": STRING,
    "staging_gid": STRING, "node_type": STRING, "title": {"type": "string"}, "vpps": {"type": ["string", "null"]},
    "source_type": {"type": ["string", "null"]}, "source_ref_gid": {"type": ["string", "null"]}, "meta": {"type": "object", "additionalProperties": True},
    "sort_order": {"type": "number"}, "updates": {"type": "object", "additionalProperties": True},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.staging.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
OUTPUT_SCHEMAS[("craft.bop.lifecycle.state.read", 1)] = _object({"lifecycle_phase": {"type": ["string", "null"]}, "lifecycle_state": {"type": "object", "additionalProperties": True}, "bop_name": {"type": ["string", "null"]}, "version_tag": {"type": ["string", "null"]}, "data_stage": {"type": ["string", "null"]}, "version_family_gid": {"type": "string"}, "stats": {"type": ["object", "null"], "additionalProperties": True}, "line_stats": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "history": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "lines": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "pbom_match": {"type": "object", "additionalProperties": True}, "pbom_vpps_check": {"type": "object", "additionalProperties": True}, "family_lifecycle_phase": {"type": "string"}, "pbom_diff_queue_pending": {"type": "integer"}, "vehicle_ops_prep": {"type": "object", "additionalProperties": True}, "all_versions_in_family": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("lifecycle_phase", "lifecycle_state", "version_family_gid"))
INPUT_SCHEMAS[("craft.ebom.change.apply", 1)] = _object({
    "operation": {"type": "string", "enum": ["snapshot.delete", "snapshot.patch", "snapshot.status.patch", "snapshot.vpps_stats.patch", "part.add", "part.add_batch", "part.update", "part.delete"]},
    "snapshot_gid": STRING, "status": STRING, "nok": INTEGER, "ignored": INTEGER, "total": INTEGER,
    "changes": {"type": "object", "additionalProperties": True},
    "part_gid": STRING, "part": {"type": "object", "additionalProperties": True}, "parts": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
}, required=("operation",))
OUTPUT_SCHEMAS[("craft.ebom.change.apply", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.ebom.snapshot.delete", 1)] = _object({"snapshot_gid": STRING}, required=("snapshot_gid",))
OUTPUT_SCHEMAS[("craft.ebom.snapshot.delete", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.ebom.snapshot.update", 1)] = _object({"snapshot_gid": STRING, "changes": {"type": "object", "additionalProperties": True}}, required=("snapshot_gid", "changes"))
OUTPUT_SCHEMAS[("craft.ebom.snapshot.update", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.ebom.snapshot.status.update", 1)] = _object({"snapshot_gid": STRING, "status": STRING}, required=("snapshot_gid", "status"))
OUTPUT_SCHEMAS[("craft.ebom.snapshot.status.update", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.ebom.snapshot.vpps_stats.update", 1)] = _object({"snapshot_gid": STRING, "nok": INTEGER, "ignored": INTEGER, "total": INTEGER}, required=("snapshot_gid",))
OUTPUT_SCHEMAS[("craft.ebom.snapshot.vpps_stats.update", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.ebom.part.create", 1)] = _object({"snapshot_gid": STRING, "part": {"type": "object", "additionalProperties": True}}, required=("snapshot_gid", "part"))
OUTPUT_SCHEMAS[("craft.ebom.part.create", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.ebom.part.bulk_create", 1)] = _object({"snapshot_gid": STRING, "parts": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("snapshot_gid", "parts"))
OUTPUT_SCHEMAS[("craft.ebom.part.bulk_create", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.ebom.part.update", 1)] = _object({"part_gid": STRING, "changes": {"type": "object", "additionalProperties": True}}, required=("part_gid", "changes"))
OUTPUT_SCHEMAS[("craft.ebom.part.update", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.ebom.part.delete", 1)] = _object({"part_gid": STRING}, required=("part_gid",))
OUTPUT_SCHEMAS[("craft.ebom.part.delete", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.data_exchange.lark.read", 1)] = _object({
    "operation": {"type": "string", "enum": ["sheets.read", "bitable.read"]}, "user_access_token": STRING,
    "spreadsheet_token": STRING, "sheet_range": STRING, "app_token": STRING, "table_id": STRING, "page_size": INTEGER,
}, required=("operation", "user_access_token"))
OUTPUT_SCHEMAS[("craft.data_exchange.lark.read", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.data_exchange.lark.write", 1)] = _object({
    "operation": {"type": "string", "enum": ["sheets.write", "bitable.write"]}, "user_access_token": STRING,
    "spreadsheet_token": STRING, "sheet_id": STRING, "values": {"type": "array", "maxItems": 5000, "items": {"type": "array"}},
    "app_token": STRING, "table_id": STRING, "records": {"type": "array", "maxItems": 5000, "items": {"type": "object", "additionalProperties": True}},
}, required=("operation", "user_access_token"))
OUTPUT_SCHEMAS[("craft.data_exchange.lark.write", 1)] = _object({"data": {"type": "object", "additionalProperties": True}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.version.legacy_read", 1)] = _object({"operation": {"type": "string", "enum": ["layout_config", "bop_tree", "station_part_map"]}, "version_gid": {"type": "string"}}, required=("operation", "version_gid"))
OUTPUT_SCHEMAS[("craft.bop.version.legacy_read", 1)] = _object({"config": {"type": ["object", "string", "null"], "additionalProperties": True}, "tree": {"type": "array", "maxItems": 1000, "items": {"type": "object", "additionalProperties": True}}, "stations": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}})
INPUT_SCHEMAS[("craft.bop.entry.legacy_read", 1)] = _object({"operation": {"type": "string", "enum": ["auto_link_preview", "entry_links", "link_summary", "entity_detail", "resolve_gids", "pbom_search", "pbom_snapshots", "project_bop_lines", "line_operations", "version_history", "entry_history"]}, "version_gid": {"type": "string"}, "entry_gid": {"type": "string"}, "line_entry_gid": {"type": "string"}, "link_type": {"type": "string"}, "ref_gid": {"type": "string"}, "gids": {"type": "object", "additionalProperties": {"type": "string"}}, "recursive": {"type": "boolean"}, "q": {"type": ["string", "null"]}, "vpps": {"type": ["string", "null"]}, "snapshot_gid": {"type": ["string", "null"]}, "project_gid": {"type": ["string", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.entry.legacy_read", 1)] = _object({"ok": {"type": "boolean"}, "data": {"type": ["array", "object"], "additionalProperties": True}, "total": {"type": "integer"}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.gbop.legacy_read", 1)] = _object({"operation": {"type": "string", "enum": ["match_preview", "list_pbom_versions"]}, "pbom_gid": {"type": "string"}, "project_gid": {"type": "string"}}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.gbop.legacy_read", 1)] = _object({"data": {"type": ["array", "object"], "additionalProperties": True}, "pbom_version_gid": {"type": "string"}}, required=("data",))
INPUT_SCHEMAS[("craft.bop.staging.read", 1)] = _object({"operation": {"type": "string", "enum": ["list"]}, "version_gid": {"type": "string"}}, required=("operation", "version_gid"))
OUTPUT_SCHEMAS[("craft.bop.staging.read", 1)] = _object({"data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("data",))
INPUT_SCHEMAS[("craft.gbop.station_autolink.preview", 1)] = _object({"operation": {"type": "string", "enum": ["preview"]}, "bop_gid": STRING, "pbom_version_gid": STRING}, required=("operation", "bop_gid"))
OUTPUT_SCHEMAS[("craft.gbop.station_autolink.preview", 1)] = _object({"pbom_version": {"type": "object", "additionalProperties": True}, "lines": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "need_select": BOOLEAN, "pbom_versions": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("pbom_version", "lines", "data"))
INPUT_SCHEMAS[("craft.ebom.legacy_read", 1)] = _object({"operation": {"type": "string", "enum": ["diff"]}, "base_gid": STRING, "target_gid": STRING}, required=("operation", "base_gid", "target_gid"))
OUTPUT_SCHEMAS[("craft.ebom.legacy_read", 1)] = _object({"base": {"type": "object", "additionalProperties": True}, "target": {"type": "object", "additionalProperties": True}, "summary": {"type": "object", "additionalProperties": True}, "added": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "deleted": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "modified": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("base", "target", "summary", "added", "deleted", "modified"))
INPUT_SCHEMAS[("craft.ebom.vpps_check.read", 1)] = _object({"operation": {"type": "string", "enum": ["check"]}, "snapshot_gid": STRING}, required=("operation", "snapshot_gid"))
OUTPUT_SCHEMAS[("craft.ebom.vpps_check.read", 1)] = _object({"snapshot": {"type": "object", "additionalProperties": True}, "summary": {"type": "object", "additionalProperties": True}, "errors": {"type": "object", "additionalProperties": True}, "alias_matches": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}, "rule4_ignored": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("snapshot", "summary", "errors", "alias_matches", "rule4_ignored"))
INPUT_SCHEMAS[("craft.bop.fork_preset.read", 1)] = _object({"operation": {"type": "string", "enum": ["list", "get"]}, "gid": STRING, "team_gid": STRING}, required=("operation",))
OUTPUT_SCHEMAS[("craft.bop.fork_preset.read", 1)] = _object({"data": {"type": ["array", "object"], "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, required=("data",))


def input_schema_for(capability_id: str, major_version: int) -> dict[str, Any]:
    return INPUT_SCHEMAS.get((capability_id, major_version)) or INPUT_SCHEMAS[capability_id]


def output_schema_for(capability_id: str, major_version: int) -> dict[str, Any]:
    return OUTPUT_SCHEMAS.get((capability_id, major_version)) or OUTPUT_SCHEMAS[capability_id]


__all__ = [
    "INPUT_SCHEMAS", "OUTPUT_SCHEMAS", "input_schema_for", "output_schema_for",
]
