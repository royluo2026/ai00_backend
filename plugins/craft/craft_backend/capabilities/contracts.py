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
    return {name: {} for name in names}


STRING = {"type": "string", "minLength": 1}
INTEGER = {"type": "integer"}
BOOLEAN = {"type": "boolean"}
ARRAY = {"type": "array", "items": {}}


INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "craft.bop.version.get": _object({"version_gid": STRING}, required=("version_gid",)),
    "craft.bop.version.list": _object({
        "project_gid": STRING,
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
            "source_gid": STRING,
            "template_gid": STRING,
            "import_preview_gid": STRING,
            "version_family_gid": STRING,
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
    "status": _NULLABLE_STRING,
    "lifecycle_phase": _NULLABLE_STRING,
    "revision": {"anyOf": [
        {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "null"},
    ]},
    "updated_at": _NULLABLE_STRING,
    "archived": {"type": "boolean"},
}
_VERSION_SUMMARY = _object(
    _VERSION_SUMMARY_PROPERTIES,
    required=tuple(_VERSION_SUMMARY_PROPERTIES),
)

OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "craft.bop.version.get": _object(_fields(*_VERSION_DETAIL), required=("version_gid", "revision", "lifecycle")),
    "craft.bop.version.list": _object({
        "items": {"type": "array", "items": _VERSION_SUMMARY},
        "next_cursor": _NULLABLE_STRING,
    }, required=("items", "next_cursor")),
    "craft.bop.execution_structure.get": _object(
        _fields("contract_id", "contract_version", "official", "source", "nodes", "operations", "dependencies", "conditions", "content_hash"),
        required=("contract_id", "contract_version", "official", "source", "nodes", "operations", "dependencies", "conditions", "content_hash"),
    ),
    "craft.bop.execution_structure.preview": _object(
        _fields("contract_id", "contract_version", "official", "source", "nodes", "operations", "dependencies", "conditions", "content_hash"),
        required=("contract_id", "contract_version", "official", "source", "nodes", "operations", "dependencies", "conditions", "content_hash"),
    ),
    "craft.bop.linked_parts.get": _object(_fields("version_gid", "revision", "items"), required=("version_gid", "revision", "items")),
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
    "craft.pbom.version.create": _object(_fields("project_ref", "version_tag", "knowledge_revision_ref", "ontology_release_ref", "revision_commit_ref"), required=("project_ref", "version_tag")),
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
    "craft.pbom.version.create": _object(_fields("gid", "project_ref", "version_tag", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.get": _object(_fields("gid", "project_ref", "version_tag", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.search": _object({"items": ARRAY}, required=("items",)),
    "craft.pbom.version.submit": _object(_fields("gid", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.publish": _object(_fields("gid", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.archive": _object(_fields("gid", "status", "revision"), required=("gid", "status", "revision")),
    "craft.pbom.version.compare": _object(_fields("added", "removed", "changed"), required=("added", "removed", "changed")),
    "craft.pbom.draft.change.preview": _object(_fields("preview_gid", "version_gid", "changes"), required=("preview_gid", "version_gid", "changes")),
    "craft.pbom.draft.change.apply": _object(_fields("version_gid", "applied", "results"), required=("version_gid", "applied", "results")),
    "craft.pbom.part.search": _object(_fields("version_gid", "items"), required=("version_gid", "items")),
    "craft.pbom.import.preview": _object(_fields("import_preview_gid", "content_sha256", "part_count"), required=("import_preview_gid", "content_sha256", "part_count")),
})

from .gbop_descriptors import GBOP_CAPABILITY_IDS
from .rule_descriptors import RULE_CAPABILITY_IDS
for _capability_id in (*GBOP_CAPABILITY_IDS, *RULE_CAPABILITY_IDS):
    INPUT_SCHEMAS.setdefault(_capability_id, _object(_fields("ref", "release_ref", "lineage_refs", "evidence", "item_gid", "query", "limit")))
    OUTPUT_SCHEMAS.setdefault(_capability_id, _object(_fields("capability_id", "ref", "release_ref", "status", "lineage_refs", "evidence", "active_release_gid", "item_gid", "items"), required=("status",) if _capability_id not in {"craft.gbop.item.search", "craft.gbop.item.usage.get", "craft.gbop.item.knowledge.list"} else ("items",)))

from .reviewed_ids import CRAFT_REVIEWED_CAPABILITIES
for _capability_id in CRAFT_REVIEWED_CAPABILITIES:
    INPUT_SCHEMAS.setdefault(
        _capability_id,
        _object(
            {"operation": STRING, "arguments": {}, "expected_version": INTEGER},
            required=("operation", "arguments"),
        ),
    )
    OUTPUT_SCHEMAS.setdefault(
        _capability_id,
        _object({"data": {}}, required=("data",)),
    )


__all__ = ["INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
