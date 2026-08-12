"""Transport contracts owned by the Base Platform domain."""
from __future__ import annotations


def _object(properties: dict, required: tuple[str, ...] = ()) -> dict:
    value = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = list(required)
    return value


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
BOOLEAN = {"type": "boolean"}
ANY_ARRAY = {"type": "array", "items": {}}
REVIEWED_INPUT = _object(
    {"operation": STRING, "resource": {}, "expected_version": INTEGER},
    ("operation",),
)
REVIEWED_OUTPUT = _object({"result": {}}, ("result",))
APPROVAL_ITEM = _object(
    {
        "approval_id": STRING,
        "subject_ref": STRING,
        "requester_gid": STRING,
        "resource_ref": STRING,
        "revision": STRING,
        "content_hash": STRING,
        "reason": STRING,
        "approver_ids": {"type": "array", "items": STRING},
        "status": STRING,
        "decision_reason": {"anyOf": [STRING, {"type": "null"}]},
        "decided_by": {"anyOf": [STRING, {"type": "null"}]},
        "created_at": STRING,
        "updated_at": STRING,
    },
    (
        "approval_id", "subject_ref", "requester_gid", "resource_ref",
        "revision", "content_hash", "reason", "approver_ids", "status",
        "decision_reason", "decided_by", "created_at", "updated_at",
    ),
)

REVIEWED_READ_CAPABILITIES = {
    "base.annotation.read",
    "base.authorization.grant.read",
    "base.export_template.read",
    "base.identity.session.get",
    "base.plugin.marketplace.search",
    "base.saved_view.read",
    "base.team.read",
}
REVIEWED_WRITE_CAPABILITIES = {
    "base.annotation.change.apply",
    "base.authorization.grant.change.apply",
    "base.export_template.change.apply",
    "base.identity.directory.sync",
    "base.identity.role.assign",
    "base.plugin.marketplace.publisher.register",
    "base.plugin.marketplace.release.change.apply",
    "base.saved_view.change.apply",
    "base.team.change.apply",
    "base.team.membership.change.apply",
}

PLUGIN_ID = _object({"plugin_id": STRING}, ("plugin_id",))
PLUGIN_RELEASE = _object(
    {"plugin_id": STRING, "version": STRING, "granted_capabilities": {"type": "array", "items": STRING}},
    ("plugin_id", "version", "granted_capabilities"),
)
PLUGIN_FINISH = _object({"plugin_id": STRING, "healthy": BOOLEAN}, ("plugin_id", "healthy"))
PLUGIN_STATE = _object({"plugin_id": STRING, "version": STRING, "state": STRING}, ("plugin_id", "version", "state"))
PLUGIN_UPGRADE_STATE = _object(
    {"plugin_id": STRING, "version": STRING, "previous_version": {"anyOf": [STRING, {"type": "null"}]}, "state": STRING},
    ("plugin_id", "version", "state"),
)

STORAGE_KEY = _object({"key": STRING}, ("key",))
STORAGE_LIST = _object({"prefix": STRING, "limit": INTEGER})
STORAGE_MUTATION = _object({"key": STRING, "value": {}, "expected_version": INTEGER}, ("key", "value"))
STORAGE_DELETE = _object({"key": STRING, "expected_version": INTEGER}, ("key",))
STORAGE_VALUE = _object(
    {"key": STRING, "value": {}, "version": INTEGER, "updated_at": STRING},
    ("key", "value", "version", "updated_at"),
)
STORAGE_ITEM = _object({"key": STRING, "version": INTEGER, "updated_at": STRING}, ("key", "version", "updated_at"))

STABLE_REF = _object({
    "object_ref": STRING, "title": STRING, "summary": STRING,
    "match_reason": STRING, "owner": STRING,
}, ("object_ref", "owner"))

INPUT_SCHEMAS = {
    "system.echo": _object({"echo": {}}),
    "plugin.install": PLUGIN_RELEASE,
    "plugin.enable": PLUGIN_ID,
    "plugin.disable": PLUGIN_ID,
    "plugin.upgrade": PLUGIN_RELEASE,
    "plugin.upgrade.finish": PLUGIN_FINISH,
    "plugin.rollback": PLUGIN_ID,
    "plugin.revoke": PLUGIN_ID,
    "plugin.uninstall": PLUGIN_ID,
    "plugin.storage.get": STORAGE_KEY,
    "plugin.storage.list": STORAGE_LIST,
    "plugin.storage.put": STORAGE_MUTATION,
    "plugin.storage.delete": STORAGE_DELETE,
    "system.search": _object({"query": STRING, "limit": INTEGER}, ("query",)),
    "system.activity.search": _object({"limit": INTEGER}),
    "system.job.get": _object({"job_gid": STRING, "owner": STRING}, ("job_gid", "owner")),
    "system.job.cancel": _object({"job_gid": STRING, "owner": STRING}, ("job_gid", "owner")),
    "identity.principal.search": _object({"query": STRING, "limit": INTEGER}, ("query",)),
    "system.lineage.get": _object({"object_ref": STRING}, ("object_ref",)),
    "system.change_impact.preview": _object({"change_ref": STRING}, ("change_ref",)),
    "semantic.context.get": _object({"named_view": STRING, "depth": INTEGER, "limit": INTEGER}, ("named_view",)),
    "system.worker.outbox.health": _object({}),
    **{
        capability_id: REVIEWED_INPUT
        for capability_id in REVIEWED_READ_CAPABILITIES | REVIEWED_WRITE_CAPABILITIES
    },
    "base.approval.request.create": _object(
        {
            "subject_ref": STRING,
            "resource_ref": STRING,
            "revision": STRING,
            "content_hash": STRING,
            "reason": STRING,
            "approver_ids": {"type": "array", "items": STRING},
        },
        (
            "subject_ref", "resource_ref", "revision", "content_hash",
            "reason", "approver_ids",
        ),
    ),
    "base.approval.request.get": _object(
        {"approval_id": STRING}, ("approval_id",)
    ),
    "base.approval.request.search": _object(
        {"subject_ref": STRING, "status": STRING}
    ),
    "base.approval.request.decide": _object(
        {
            "approval_id": STRING,
            "expected_state": STRING,
            "decision": STRING,
            "reason": STRING,
        },
        ("approval_id", "expected_state", "decision", "reason"),
    ),
    "base.approval.request.cancel": _object(
        {"approval_id": STRING, "expected_state": STRING},
        ("approval_id", "expected_state"),
    ),
}

OUTPUT_SCHEMAS = {
    "system.echo": _object({"echo": {}}),
    **{capability_id: PLUGIN_STATE for capability_id in (
        "plugin.install", "plugin.enable", "plugin.disable", "plugin.upgrade.finish",
        "plugin.rollback", "plugin.revoke", "plugin.uninstall",
    )},
    "plugin.upgrade": PLUGIN_UPGRADE_STATE,
    "plugin.storage.get": STORAGE_VALUE,
    "plugin.storage.list": _object({"items": {"type": "array", "items": STORAGE_ITEM}, "limit": INTEGER}, ("items", "limit")),
    "plugin.storage.put": _object({"key": STRING, "version": INTEGER}, ("key", "version")),
    "plugin.storage.delete": _object({"key": STRING, "deleted": BOOLEAN}, ("key", "deleted")),
    "system.search": _object({"items": {"type": "array", "items": STABLE_REF}, "total": INTEGER, "query": STRING}, ("items", "total", "query")),
    "system.activity.search": _object({"items": ANY_ARRAY, "total": INTEGER}, ("items", "total")),
    "system.job.get": _object({"job_gid": STRING, "status": STRING, "owner": STRING, "rolled_back": BOOLEAN}, ("job_gid", "status", "owner", "rolled_back")),
    "system.job.cancel": _object({"job_gid": STRING, "status": STRING, "owner": STRING, "rolled_back": BOOLEAN}, ("job_gid", "status", "owner", "rolled_back")),
    "identity.principal.search": _object({"items": ANY_ARRAY, "total": INTEGER}, ("items", "total")),
    "system.lineage.get": _object({"object_ref": STRING, "events": ANY_ARRAY, "breaks": ANY_ARRAY, "complete": BOOLEAN}, ("object_ref", "events", "breaks", "complete")),
    "system.change_impact.preview": _object({"change_ref": STRING, "items": ANY_ARRAY, "unknown": ANY_ARRAY}, ("change_ref", "items", "unknown")),
    "semantic.context.get": _object({"named_view": STRING, "items": ANY_ARRAY, "depth": INTEGER}, ("named_view", "items", "depth")),
    "system.worker.outbox.health": _object({
        "heartbeat": {"anyOf": [
            {"type": "null"},
            _object({
                "worker_name": STRING, "worker_id": STRING, "status": STRING,
                "details": {}, "heartbeat_at": STRING, "started_at": STRING,
            }, ("worker_name", "worker_id", "status", "heartbeat_at", "started_at")),
        ]},
        "outbox_counts": _object({
            "pending": INTEGER, "publishing": INTEGER, "completed": INTEGER, "dead": INTEGER,
        }),
        "open_alerts": INTEGER,
    }, ("heartbeat", "outbox_counts", "open_alerts")),
    **{
        capability_id: REVIEWED_OUTPUT
        for capability_id in REVIEWED_READ_CAPABILITIES | REVIEWED_WRITE_CAPABILITIES
    },
    "base.approval.request.create": APPROVAL_ITEM,
    "base.approval.request.get": APPROVAL_ITEM,
    "base.approval.request.search": _object(
        {"items": {"type": "array", "items": APPROVAL_ITEM}}, ("items",)
    ),
    "base.approval.request.decide": APPROVAL_ITEM,
    "base.approval.request.cancel": APPROVAL_ITEM,
}

__all__ = ["INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
