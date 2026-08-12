"""Transport contracts and stable resource references owned by Knowledge."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


SPACE_REF_SCHEMA = {"type": "string", "pattern": r"^knowledge-space:[A-Za-z0-9_.:-]+$"}
DOCUMENT_REF_SCHEMA = {"type": "string", "pattern": r"^knowledge-document:[A-Za-z0-9_.:-]+$"}
REVISION_REF_SCHEMA = {"type": "string", "pattern": r"^knowledge-revision:[A-Za-z0-9_.:-]+$"}
PROPOSAL_REF_SCHEMA = {"type": "string", "pattern": r"^knowledge-proposal:[A-Za-z0-9_.:-]+$"}
OUTBOX_REF_SCHEMA = {"type": "string", "pattern": r"^knowledge-outbox:[A-Za-z0-9_.:-]+$"}
ENTRY_REF_SCHEMA = {"type": "string", "pattern": r"^knowledge-entry:[A-Za-z0-9_.:-]+$"}


def space_ref(gid: object) -> str:
    return f"knowledge-space:{gid}"


def document_ref(gid: object) -> str:
    return f"knowledge-document:{gid}"


def revision_ref(gid: object) -> str:
    return f"knowledge-revision:{gid}"


def proposal_ref(gid: object) -> str:
    return f"knowledge-proposal:{gid}"


def outbox_ref(gid: object) -> str:
    return f"knowledge-outbox:{gid}"


def entry_ref(gid: object) -> str:
    return f"knowledge-entry:{gid}"


def transport_value(value):
    """Normalize database values before they cross the JSON Capability boundary."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {str(key): transport_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [transport_value(item) for item in value]
    return value


def _object(properties: dict, required: tuple[str, ...] = ()) -> dict:
    return {
        "type": "object",
        "properties": properties,
        **({"required": list(required)} if required else {}),
    }


def _nullable(kind: str) -> dict:
    return {"anyOf": [{"type": kind}, {"type": "null"}]}


SPACE_SCHEMA = _object({
    "object_ref": SPACE_REF_SCHEMA,
    "gid": {"type": "string"},
    "tenant_gid": {"type": "string"},
    "name": {"type": "string"},
    "visibility": {"type": "string", "enum": ["team"]},
    "created_by": {"type": "string"},
    "updated_at": _nullable("string"),
}, ("object_ref", "gid", "name", "visibility"))

SPACE_LIST_SCHEMA = _object({
    "items": {"type": "array", "items": SPACE_SCHEMA},
    "total": {"type": "integer", "minimum": 0},
}, ("items", "total"))

REVISION_SCHEMA = _object({
    "object_ref": REVISION_REF_SCHEMA,
    "document_ref": DOCUMENT_REF_SCHEMA,
    "document_gid": {"type": "string"},
    "revision_gid": {"type": "string"},
    "revision_no": {"type": "integer", "minimum": 1},
    "base_revision_gid": _nullable("string"),
    "restored_from_revision_gid": _nullable("string"),
    "content_sha256": {"type": "string"},
    "byte_size": {"type": "integer", "minimum": 0},
    "state": {"type": "string"},
    "created_by": _nullable("string"),
    "created_at": _nullable("string"),
}, ("object_ref", "document_ref", "document_gid", "revision_gid", "revision_no", "state"))

DOCUMENT_SCHEMA = _object({
    "object_ref": DOCUMENT_REF_SCHEMA,
    "revision_ref": REVISION_REF_SCHEMA,
    "space_ref": SPACE_REF_SCHEMA,
    "title": {"type": "string"},
    "tenant_gid": {"type": "string"},
    "space_gid": {"type": "string"},
    "document_gid": {"type": "string"},
    "revision_gid": {"type": "string"},
    "revision_no": {"type": "integer", "minimum": 1},
    "object_key": {"type": "string"},
    "content_sha256": {"type": "string"},
    "state": {"type": "string"},
    "markdown": {"type": "string"},
}, ("object_ref", "revision_ref", "space_ref", "document_gid", "revision_gid", "revision_no", "state"))

DOCUMENT_WRITE_SCHEMA = _object({
    key: value for key, value in DOCUMENT_SCHEMA["properties"].items() if key != "markdown"
}, ("object_ref", "revision_ref", "space_ref", "document_gid", "revision_gid", "revision_no", "state"))

REVISION_HISTORY_SCHEMA = _object({
    "document_ref": DOCUMENT_REF_SCHEMA,
    "document_gid": {"type": "string"},
    "items": {"type": "array", "items": REVISION_SCHEMA, "maxItems": 200},
    "total": {"type": "integer", "minimum": 0},
}, ("document_ref", "document_gid", "items", "total"))

DOCUMENT_DIFF_SCHEMA = _object({
    "document_ref": DOCUMENT_REF_SCHEMA,
    "document_gid": {"type": "string"},
    "from_revision_ref": REVISION_REF_SCHEMA,
    "from_revision_gid": {"type": "string"},
    "to_revision_ref": REVISION_REF_SCHEMA,
    "to_revision_gid": {"type": "string"},
    "diff": {"type": "string", "maxLength": 200000},
}, ("document_ref", "from_revision_ref", "to_revision_ref", "diff"))

ENTRY_SCHEMA = _object({
    "object_ref": ENTRY_REF_SCHEMA,
    "gid": {"type": "string"},
    "display_id": {"type": "string"},
    "title": {"type": "string"},
    "entry_type": {"type": "string"},
    "status": {"type": "string"},
    "share_scope": {"type": "string"},
    "tags": {"type": "array", "items": {"type": "string"}},
    "creator_gid": {"type": "string"},
    "updated_at": {"type": "string"},
    "content_md": {"type": "string"},
    "content_ref": {"type": "object", "properties": {
        "object_key": {"type": "string"}, "ois_url": {"type": "string"},
        "sha256": {"type": "string"}, "document_gid": {"type": "string"},
        "revision_gid": {"type": "string"}, "proposal_gid": {"type": "string"},
    }},
    "related_part_nos": {"type": "array", "items": {"type": "string"}},
    "related_operation_gids": {"type": "array", "items": {"type": "string"}},
    "attachments": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "url": {"type": "string"},
        "object_key": {"type": "string"}, "sha256": {"type": "string"},
        "media_type": {"type": "string"}, "byte_size": {"type": "integer"},
    }}},
    "source_gid": _nullable("string"),
    "source_label": {"type": "string"},
    "maintainer_gid": {"type": "string"},
    "content_preview": {"type": "string"},
}, ("object_ref", "gid", "title", "status"))

ENTRY_SEARCH_SCHEMA = _object({
    "items": {"type": "array", "items": ENTRY_SCHEMA, "maxItems": 100},
    "total": {"type": "integer", "minimum": 0},
    "query": {"type": "string"},
}, ("items", "total", "query"))

PROPOSAL_SCHEMA = _object({
    "object_ref": PROPOSAL_REF_SCHEMA,
    "gid": {"type": "string"},
    "proposal_gid": {"type": "string"},
    "base_gid": _nullable("string"),
    "title": {"type": "string"},
    "content_md": {"type": "string"},
    "summary": {"type": "string"},
    "tags": {"type": "array", "items": {"type": "string"}},
    "status": {"type": "string", "enum": ["pending", "publishing", "approved", "rejected"]},
    "creator_gid": {"type": "string"},
    "team_gid": _nullable("string"),
    "reviewer_gid": _nullable("string"),
    "review_note": _nullable("string"),
    "reviewed_at": _nullable("string"),
    "published_gid": _nullable("string"),
    "published_ref": {"anyOf": [ENTRY_REF_SCHEMA, {"type": "null"}]},
    "ois_url": _nullable("string"),
    "created_at": _nullable("string"),
    "updated_at": _nullable("string"),
    "message": {"type": "string"},
}, ("object_ref", "status"))

PROPOSAL_LIST_SCHEMA = _object({
    "items": {"type": "array", "items": PROPOSAL_SCHEMA, "maxItems": 200},
    "total": {"type": "integer", "minimum": 0},
    "status": {"type": "string"},
}, ("items", "total", "status"))

OUTBOX_SCHEMA = _object({
    "object_ref": OUTBOX_REF_SCHEMA,
    "gid": {"type": "string"},
    "outbox_gid": {"type": "string"},
    "proposal_gid": {"type": "string"},
    "proposal_ref": PROPOSAL_REF_SCHEMA,
    "status": {"type": "string"},
    "attempts": {"type": "integer", "minimum": 0},
    "next_retry_at": _nullable("string"),
    "last_error": _nullable("string"),
    "created_at": _nullable("string"),
    "updated_at": _nullable("string"),
    "published_gid": _nullable("string"),
    "published_ref": {"anyOf": [ENTRY_REF_SCHEMA, {"type": "null"}]},
    "sha256": _nullable("string"),
    "idempotent": {"type": "boolean"},
}, ("object_ref", "status"))

OUTBOX_LIST_SCHEMA = _object({
    "items": {"type": "array", "items": OUTBOX_SCHEMA, "maxItems": 200},
    "total": {"type": "integer", "minimum": 0},
}, ("items", "total"))

MIGRATION_STATUS_SCHEMA = _object({
    "inventory": {"type": "object", "properties": {
        "scanned": {"type": "integer"}, "scan_limit": {"type": "integer"},
        "scan_truncated": {"type": "boolean"}, "eligible": {"type": "integer"},
        "eligible_bytes": {"type": "integer"}, "migrated": {"type": "integer"},
        "pending": {"type": "integer"}, "quarantined": {"type": "integer"},
        "other_tenant": {"type": "integer"}, "source_retained": {"type": "boolean"},
    }},
    "runs": {"type": "array", "items": {"type": "object", "properties": {
        "gid": {"type": "string"}, "space_gid": _nullable("string"), "actor_gid": _nullable("string"), "status": {"type": "string"},
        "source_count": _nullable("integer"), "source_bytes": _nullable("integer"), "copied_count": _nullable("integer"), "skipped_count": _nullable("integer"),
        "failed_count": _nullable("integer"), "verified_count": _nullable("integer"), "last_error": _nullable("string"), "started_at": _nullable("string"),
        "finished_at": _nullable("string"), "created_at": _nullable("string"),
    }}},
    "selected_run_gid": _nullable("string"),
    "items": {"type": "array", "items": {"type": "object", "properties": {
        "entry_gid": {"type": "string"}, "document_gid": _nullable("string"), "revision_gid": _nullable("string"),
        "status": {"type": "string"}, "source_sha256": _nullable("string"), "object_key": _nullable("string"),
        "content_sha256": _nullable("string"), "error_message": _nullable("string"), "started_at": _nullable("string"), "finished_at": _nullable("string"),
    }}},
}, ("inventory", "runs", "items"))

CONTEXT_RETRIEVAL_SCHEMA = _object({
    "items": {"type": "array", "items": {"type": "object", "properties": {
        "document_ref": DOCUMENT_REF_SCHEMA, "revision_ref": REVISION_REF_SCHEMA,
        "document_gid": {"type": "string"}, "revision_gid": {"type": "string"},
        "title": _nullable("string"), "summary": {"type": "string"}, "retrieval_method": {"type": "string"},
    }, "required": ["document_ref", "revision_ref", "document_gid", "revision_gid", "retrieval_method"]}, "maxItems": 10},
    "query": {"type": "string"},
}, ("items", "query"))


__all__ = [name for name in globals() if name.endswith("_SCHEMA") or name.endswith("_ref")]
