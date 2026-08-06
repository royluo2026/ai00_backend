"""Knowledge Workspace document/revision Capabilities backed by OceanBase metadata and OIS."""
from __future__ import annotations

import re
from typing import Any

from .models_next import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from backend.knowledge.revision_store import (
    load_markdown_revision,
    prepare_markdown_revision,
    store_markdown_revision,
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,254}$")
_PERMISSIONS = {"view", "edit", "admin"}


def _tenant(context: CapabilityContext) -> str:
    tenant = str(context.team_gid or "").strip()
    if not tenant:
        raise PermissionError("Knowledge Workspace requires a team tenant")
    return tenant


def _access_sql(permission: str) -> str:
    allowed = {"view": ("view", "edit", "admin"), "edit": ("edit", "admin"), "admin": ("admin",)}[permission]
    quoted = ",".join(f"'{item}'" for item in allowed)
    return (
        "(d.created_by=%s OR EXISTS (SELECT 1 FROM workmanship_know_document_acl a "
        "WHERE a.document_gid=d.gid AND a.permission IN (" + quoted + ") AND "
        "((a.subject_type='user' AND a.subject_gid=%s) OR "
        "(a.subject_type='team' AND a.subject_gid=%s))))"
    )


def _evidence(row: dict[str, Any]) -> EvidenceRef:
    digest = str(row["content_sha256"])
    return EvidenceRef(
        kind="ois.revision",
        reference=f"ois://{row['object_key']}",
        digest=f"sha256:{digest}",
        summary=f"{row.get('title') or 'Knowledge document'} revision {row['revision_no']}",
        metadata={
            "tenant_gid": row["tenant_gid"],
            "space_gid": row["space_gid"],
            "document_gid": row["document_gid"],
            "revision_gid": row["revision_gid"],
            "revision_no": int(row["revision_no"]),
            "state": row["state"],
        },
    )


def create_space(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    tenant = _tenant(context)
    name = str(payload.get("name") or "").strip()
    visibility = str(payload.get("visibility") or "team")
    if not name or len(name) > 512 or visibility not in {"private", "team"}:
        raise ValueError("valid space name and visibility are required")
    from backend.db.connection import get_conn
    from backend.utils.gid import next_gid
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_know_spaces (gid,tenant_gid,name,visibility,created_by) VALUES (%s,%s,%s,%s,%s)",
                (gid, tenant, name, visibility, context.user_gid),
            )
        conn.commit()
    return {"gid": gid, "tenant_gid": tenant, "name": name, "visibility": visibility}


def list_spaces(_payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    tenant = _tenant(context)
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,name,visibility,created_by,updated_at FROM workmanship_know_spaces "
                "WHERE tenant_gid=%s AND (visibility='team' OR created_by=%s) ORDER BY updated_at DESC",
                (tenant, context.user_gid),
            )
            items = [dict(row) for row in cur.fetchall()]
    return {"items": items, "total": len(items)}
def _create_revision(payload: dict[str, Any], context: CapabilityContext, *, existing: bool) -> CapabilityOutput:
    tenant = _tenant(context)
    title = str(payload.get("title") or "").strip()
    markdown = str(payload.get("markdown") or "")
    if not markdown.strip():
        raise ValueError("markdown is required")
    visibility = str(payload.get("visibility") or "team")
    if not existing and visibility not in {"private", "team"}:
        raise ValueError("visibility must be private or team")
    from backend.db.connection import get_conn
    from backend.utils.gid import next_gid

    with get_conn() as conn:
        with conn.cursor() as cur:
            if existing:
                document_gid = str(payload.get("document_gid") or "").strip()
                cur.execute(
                    "SELECT d.*,r.content_sha256 AS before_sha256 FROM workmanship_know_documents d "
                    "LEFT JOIN workmanship_know_revisions r ON r.gid=d.current_revision_gid "
                    "WHERE d.gid=%s AND d.tenant_gid=%s AND " + _access_sql("edit") + " FOR UPDATE",
                    (document_gid, tenant, context.user_gid, context.user_gid, tenant),
                )
                document = cur.fetchone()
                if not document:
                    raise PermissionError("document not found or edit access denied")
                document = dict(document)
                requested_base = str(payload.get("base_revision_gid") or "").strip()
                current_base = str(document.get("current_revision_gid") or "").strip()
                if requested_base != current_base:
                    raise CapabilityBusinessError(
                        "revision_conflict",
                        "The document changed after the caller loaded it.",
                        details={
                            "document_gid": document_gid,
                            "requested_base_revision_gid": requested_base,
                            "current_revision_gid": current_base,
                        },
                    )
                title = title or str(document["title"])
                cur.execute("SELECT COALESCE(MAX(revision_no),0) AS n FROM workmanship_know_revisions WHERE document_gid=%s", (document_gid,))
                revision_no = int(cur.fetchone()["n"]) + 1
                base_revision_gid = current_base
                before_sha256 = document.get("before_sha256")
                space_gid = str(document["space_gid"])
            else:
                space_gid = str(payload.get("space_gid") or "").strip()
                slug = str(payload.get("slug") or "").strip().lower()
                if not title or not _SLUG_RE.fullmatch(slug):
                    raise ValueError("title and a safe lowercase slug are required")
                cur.execute(
                    "SELECT gid FROM workmanship_know_spaces WHERE gid=%s AND tenant_gid=%s "
                    "AND (visibility='team' OR created_by=%s)",
                    (space_gid, tenant, context.user_gid),
                )
                if not cur.fetchone():
                    raise LookupError("knowledge space not found")
                document_gid = str(next_gid())
                revision_no = 1
                base_revision_gid = None
                before_sha256 = None
            revision_gid = str(next_gid())
            prepared = prepare_markdown_revision(
                tenant_gid=tenant, space_gid=space_gid, document_gid=document_gid,
                revision_gid=revision_gid, markdown=markdown,
            )
            stored = store_markdown_revision(prepared)
            if not existing:
                cur.execute(
                    "INSERT INTO workmanship_know_documents "
                    "(gid,tenant_gid,space_gid,title,slug,status,current_revision_gid,published_revision_gid,created_by) "
                    "VALUES (%s,%s,%s,%s,%s,'published',%s,%s,%s)",
                    (document_gid, tenant, space_gid, title, slug, revision_gid, revision_gid, context.user_gid),
                )
                cur.execute(
                    "INSERT INTO workmanship_know_document_acl "
                    "(document_gid,subject_type,subject_gid,permission,created_by) VALUES (%s,'user',%s,'admin',%s)",
                    (document_gid, context.user_gid, context.user_gid),
                )
                if visibility == "team":
                    cur.execute(
                        "INSERT INTO workmanship_know_document_acl "
                        "(document_gid,subject_type,subject_gid,permission,created_by) VALUES (%s,'team',%s,'edit',%s)",
                        (document_gid, tenant, context.user_gid),
                    )
            channel = str(context.source or "web")[:32]
            delegated_user_gid = getattr(context, "delegated_user_gid", None)
            agent_run_gid = getattr(context, "agent_run_gid", None) or getattr(context, "agent_run_id", None)
            plugin_id = getattr(context, "plugin_id", None)
            plugin_version = getattr(context, "plugin_version", None)
            change_summary = str(payload.get("change_summary") or "").strip()[:2048] or None
            cur.execute(
                "INSERT INTO workmanship_know_revisions "
                "(gid,tenant_gid,space_gid,document_gid,revision_no,base_revision_gid,restored_from_revision_gid,object_key,content_sha256,byte_size,media_type,state,created_by,channel,delegated_user_gid,agent_run_gid,plugin_id,plugin_version,request_id,before_sha256,after_sha256,change_summary) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'published',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (revision_gid, tenant, space_gid, document_gid, revision_no, base_revision_gid, payload.get("_restored_from_revision_gid"), stored["object_key"], stored["sha256"], stored["byte_size"], stored["media_type"], context.user_gid, channel, delegated_user_gid, agent_run_gid, plugin_id, plugin_version, context.request_id, before_sha256, stored["sha256"], change_summary),
            )
            if existing:
                cur.execute(
                    "UPDATE workmanship_know_documents SET title=%s,current_revision_gid=%s,published_revision_gid=%s,status='published',updated_at=NOW() WHERE gid=%s",
                    (title, revision_gid, revision_gid, document_gid),
                )
        conn.commit()
    row = {
        "title": title, "tenant_gid": tenant, "space_gid": space_gid,
        "document_gid": document_gid, "revision_gid": revision_gid,
        "revision_no": revision_no, "state": "published",
        "object_key": stored["object_key"], "content_sha256": stored["sha256"],
    }
    return CapabilityOutput(data=row, evidence=(_evidence(row),))


def create_document(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    return _create_revision(payload, context, existing=False)


def revise_document(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    return _create_revision(payload, context, existing=True)


def get_document(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    tenant = _tenant(context)
    document_gid = str(payload.get("document_gid") or "").strip()
    revision_gid = str(payload.get("revision_gid") or "").strip()
    if not document_gid:
        raise ValueError("document_gid is required")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.title,d.tenant_gid,d.space_gid,d.gid AS document_gid,r.gid AS revision_gid,r.revision_no,r.object_key,r.content_sha256,r.state "
                "FROM workmanship_know_documents d JOIN workmanship_know_revisions r ON r.document_gid=d.gid "
                "WHERE d.gid=%s AND d.tenant_gid=%s AND r.gid=COALESCE(NULLIF(%s,''),d.published_revision_gid) AND " + _access_sql("view"),
                (document_gid, tenant, revision_gid, context.user_gid, context.user_gid, tenant),
            )
            row = cur.fetchone()
    if not row:
        raise LookupError("document or revision not found, or access denied")
    row = dict(row)
    markdown = load_markdown_revision(row["object_key"], row["content_sha256"])
    data = {**row, "markdown": markdown}
    return CapabilityOutput(data=data, evidence=(_evidence(row),))


def search_documents(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    tenant = _tenant(context)
    query = str(payload.get("query") or "").strip()
    limit = max(1, min(int(payload.get("limit") or 10), 50))
    like = f"%{query}%"
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.title,d.slug,d.tenant_gid,d.space_gid,d.gid AS document_gid,r.gid AS revision_gid,r.revision_no,r.object_key,r.content_sha256,r.state "
                "FROM workmanship_know_documents d JOIN workmanship_know_revisions r ON r.gid=d.published_revision_gid "
                "WHERE d.tenant_gid=%s AND (d.title LIKE %s OR d.slug LIKE %s) AND " + _access_sql("view") +
                " ORDER BY d.updated_at DESC LIMIT %s",
                (tenant, like, like, context.user_gid, context.user_gid, tenant, limit),
            )
            rows = [dict(row) for row in cur.fetchall()]
    items = [
        {key: row[key] for key in ("title", "slug", "space_gid", "document_gid", "revision_gid", "revision_no", "state")}
        for row in rows
    ]
    return CapabilityOutput(data={"items": items, "total": len(items), "query": query}, evidence=tuple(_evidence(row) for row in rows))
def list_document_revisions(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    tenant = _tenant(context)
    document_gid = str(payload.get("document_gid") or "").strip()
    limit = max(1, min(int(payload.get("limit") or 50), 200))
    if not document_gid:
        raise ValueError("document_gid is required")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.title,d.tenant_gid,d.space_gid,d.gid AS document_gid,r.gid AS revision_gid,"
                "r.revision_no,r.base_revision_gid,r.restored_from_revision_gid,r.object_key,"
                "r.content_sha256,r.byte_size,r.state,r.created_by,r.created_at "
                "FROM workmanship_know_documents d JOIN workmanship_know_revisions r ON r.document_gid=d.gid "
                "WHERE d.gid=%s AND d.tenant_gid=%s AND " + _access_sql("view") +
                " ORDER BY r.revision_no DESC LIMIT %s",
                (document_gid, tenant, context.user_gid, context.user_gid, tenant, limit),
            )
            rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        raise LookupError("document not found, or access denied")
    items = [
        {key: row.get(key) for key in (
            "document_gid", "revision_gid", "revision_no", "base_revision_gid",
            "restored_from_revision_gid", "content_sha256", "byte_size", "state",
            "created_by", "created_at",
        )}
        for row in rows
    ]
    return CapabilityOutput(
        data={"document_gid": document_gid, "items": items, "total": len(items)},
        evidence=tuple(_evidence(row) for row in rows),
    )

def diff_document_revisions(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    import difflib

    document_gid = str(payload.get("document_gid") or "").strip()
    from_revision_gid = str(payload.get("from_revision_gid") or "").strip()
    to_revision_gid = str(payload.get("to_revision_gid") or "").strip()
    if not document_gid or not from_revision_gid or not to_revision_gid:
        raise ValueError("document_gid, from_revision_gid and to_revision_gid are required")
    before = get_document({"document_gid": document_gid, "revision_gid": from_revision_gid}, context)
    after = get_document({"document_gid": document_gid, "revision_gid": to_revision_gid}, context)
    before_data = before.data
    after_data = after.data
    diff = "".join(
        difflib.unified_diff(
            str(before_data["markdown"]).splitlines(keepends=True),
            str(after_data["markdown"]).splitlines(keepends=True),
            fromfile=f"revision-{before_data['revision_no']}",
            tofile=f"revision-{after_data['revision_no']}",
        )
    )
    if len(diff) > 200_000:
        raise ValueError("revision diff exceeds 200000 characters")
    return CapabilityOutput(
        data={
            "document_gid": document_gid,
            "from_revision_gid": from_revision_gid,
            "to_revision_gid": to_revision_gid,
            "diff": diff,
        },
        evidence=before.evidence + after.evidence,
    )


def rollback_document(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    document_gid = str(payload.get("document_gid") or "").strip()
    target_revision_gid = str(payload.get("target_revision_gid") or "").strip()
    if not document_gid or not target_revision_gid:
        raise ValueError("document_gid and target_revision_gid are required")
    target = get_document(
        {"document_gid": document_gid, "revision_gid": target_revision_gid}, context
    ).data
    return _create_revision(
        {
            "document_gid": document_gid,
            "title": target.get("title") or "",
            "markdown": target["markdown"],
            "base_revision_gid": str(payload.get("base_revision_gid") or ""),
            "_restored_from_revision_gid": target_revision_gid,
        },
        context,
        existing=True,
    )
def list_document_acl(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    tenant = _tenant(context)
    document_gid = str(payload.get("document_gid") or "").strip()
    if not document_gid:
        raise ValueError("document_gid is required")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.gid FROM workmanship_know_documents d WHERE d.gid=%s AND d.tenant_gid=%s AND " + _access_sql("admin"),
                (document_gid, tenant, context.user_gid, context.user_gid, tenant),
            )
            if not cur.fetchone():
                raise PermissionError("document admin access denied")
            cur.execute(
                "SELECT subject_type,subject_gid,permission,created_by,created_at "
                "FROM workmanship_know_document_acl WHERE document_gid=%s "
                "ORDER BY subject_type,subject_gid",
                (document_gid,),
            )
            items = [dict(row) for row in cur.fetchall()]
    return {"document_gid": document_gid, "items": items, "total": len(items)}


def revoke_document_acl(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    tenant = _tenant(context)
    document_gid = str(payload.get("document_gid") or "").strip()
    subject_type = str(payload.get("subject_type") or "").strip()
    subject_gid = str(payload.get("subject_gid") or "").strip()
    if subject_type not in {"user", "team"} or not subject_gid:
        raise ValueError("invalid ACL subject")
    if subject_type == "team" and subject_gid != tenant:
        raise PermissionError("cannot revoke access from another tenant")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.gid,d.created_by FROM workmanship_know_documents d "
                "WHERE d.gid=%s AND d.tenant_gid=%s AND " + _access_sql("admin") + " FOR UPDATE",
                (document_gid, tenant, context.user_gid, context.user_gid, tenant),
            )
            document = cur.fetchone()
            if not document:
                raise PermissionError("document admin access denied")
            if subject_type == "user" and subject_gid == str(document["created_by"]):
                raise PermissionError("document creator admin access cannot be revoked")
            cur.execute(
                "DELETE FROM workmanship_know_document_acl "
                "WHERE document_gid=%s AND subject_type=%s AND subject_gid=%s",
                (document_gid, subject_type, subject_gid),
            )
            deleted = int(cur.rowcount or 0)
        conn.commit()
    return {
        "document_gid": document_gid,
        "subject_type": subject_type,
        "subject_gid": subject_gid,
        "revoked": deleted > 0,
    }

def grant_document_acl(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    tenant = _tenant(context)
    document_gid = str(payload.get("document_gid") or "").strip()
    subject_type = str(payload.get("subject_type") or "").strip()
    subject_gid = str(payload.get("subject_gid") or "").strip()
    permission = str(payload.get("permission") or "").strip()
    if subject_type not in {"user", "team"} or permission not in _PERMISSIONS or not subject_gid:
        raise ValueError("invalid ACL subject or permission")
    if subject_type == "team" and subject_gid != tenant:
        raise PermissionError("cannot grant access to another tenant")
    if subject_type == "user":
        from backend.platform_sdk.identity import get_user_summaries
        target = get_user_summaries([subject_gid]).get(subject_gid)
        if not target or str(target.get("team_id") or "") != tenant:
            raise PermissionError("target user is not an active member of this tenant")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.gid FROM workmanship_know_documents d WHERE d.gid=%s AND d.tenant_gid=%s AND " + _access_sql("admin"),
                (document_gid, tenant, context.user_gid, context.user_gid, tenant),
            )
            if not cur.fetchone():
                raise PermissionError("document admin access denied")
            cur.execute(
                "INSERT INTO workmanship_know_document_acl (document_gid,subject_type,subject_gid,permission,created_by) "
                "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE permission=VALUES(permission),created_by=VALUES(created_by),created_at=CURRENT_TIMESTAMP(6)",
                (document_gid, subject_type, subject_gid, permission, context.user_gid),
            )
        conn.commit()
    return {"document_gid": document_gid, "subject_type": subject_type, "subject_gid": subject_gid, "permission": permission}


def register_knowledge_document_capabilities(registry) -> None:
    common = {
        "owner": "knowledge",
        "subject_concepts": ("knowledge.document", "knowledge.revision"),
        "plugin_callable": True,
        "output_schema": {"type": "object"},
    }
    registry.register(CapabilitySpec(
        **common, id="knowledge.space.search", description="Search spaces available in the current tenant.",
        use_when="A caller needs a knowledge space.", do_not_use_when="The space gid is already known.",
        effects=("read:knowledge.space",), input_schema={"type": "object"}, tags=("knowledge", "space", "read")), list_spaces)
    registry.register(CapabilitySpec(
        **common, id="knowledge.space.create", description="Create a tenant Knowledge Workspace space.",
        use_when="A new collaboration boundary is required.", do_not_use_when="A suitable space already exists.",
        effects=("create:knowledge.space",), risk="write", confirmation="user", idempotent=False,
        input_schema={"type": "object", "required": ["name"]}, tags=("knowledge", "space", "write")), create_space)
    registry.register(CapabilitySpec(
        **common, id="knowledge.document.get", description="Read one immutable Markdown revision with evidence.",
        use_when="An exact document or revision is required.", do_not_use_when="Only bounded decision context is needed.",
        effects=("read:knowledge.document",), input_schema={"type": "object", "required": ["document_gid"]},
        tags=("knowledge", "document", "read")), get_document)
    registry.register(CapabilitySpec(
        **common, id="knowledge.document.create", description="Create a published Markdown document revision in immutable OIS storage.",
        use_when="A new knowledge document is required.", do_not_use_when="Updating an existing document.",
        effects=("create:knowledge.document", "create:knowledge.revision"), risk="write", confirmation="user", idempotent=False,
        input_schema={"type": "object", "required": ["space_gid", "title", "slug", "markdown"]},
        tags=("knowledge", "document", "write")), create_document)
    registry.register(CapabilitySpec(
        **common, id="knowledge.document.revise", description="Publish a new immutable revision with optimistic concurrency.",
        use_when="Updating a document from a known base revision.", do_not_use_when="The caller has not loaded the current revision.",
        effects=("create:knowledge.revision", "update:knowledge.document_head"), risk="write", confirmation="user", idempotent=False,
        input_schema={"type": "object", "required": ["document_gid", "base_revision_gid", "markdown"]},
        tags=("knowledge", "document", "write")), revise_document)
    registry.register(CapabilitySpec(
        **common, id="knowledge.document.diff", description="Diff two immutable Markdown revisions.",
        use_when="A caller needs exact changes between revisions.", do_not_use_when="Only revision metadata is required.",
        effects=("read:knowledge.revision",), input_schema={"type": "object", "required": ["document_gid", "from_revision_gid", "to_revision_gid"]},
        tags=("knowledge", "document", "read")), diff_document_revisions)
    registry.register(CapabilitySpec(
        **common, id="knowledge.document.history.get", description="List immutable revision metadata for a document.",
        use_when="A caller needs attribution or revision history.", do_not_use_when="The exact revision is already known.",
        effects=("read:knowledge.revision",), input_schema={"type": "object", "required": ["document_gid"]},
        tags=("knowledge", "document", "read")), list_document_revisions)
    registry.register(CapabilitySpec(
        **common, id="knowledge.document.restore", description="Restore historical content by publishing a new immutable revision.",
        use_when="Historical content must become the new head without deleting history.", do_not_use_when="Only reading old content.",
        effects=("create:knowledge.revision", "update:knowledge.document_head"), risk="write", confirmation="user", idempotent=False,
        input_schema={"type": "object", "required": ["document_gid", "base_revision_gid", "target_revision_gid"]},
        tags=("knowledge", "document", "write")), rollback_document)

    aliases = (
        ("knowledge.space.list", "knowledge.space.search", list_spaces, {"type": "object"}, "read"),
        ("knowledge.document.revisions", "knowledge.document.history.get", list_document_revisions, {"type": "object", "required": ["document_gid"]}, "read"),
        ("knowledge.document.rollback", "knowledge.document.restore", rollback_document, {"type": "object", "required": ["document_gid", "base_revision_gid", "target_revision_gid"]}, "write"),
    )
    for alias, replacement, handler, input_schema, risk in aliases:
        registry.register(CapabilitySpec(
            owner="knowledge", id=alias, description=f"Deprecated compatibility alias for {replacement}.",
            use_when="Migrating a legacy internal consumer.", do_not_use_when=f"New callers must use {replacement}.",
            subject_concepts=("knowledge.document", "knowledge.revision"), effects=("compatibility:knowledge",),
            deprecated=True, replaced_by=replacement, plugin_callable=False, risk=risk,
            confirmation="user" if risk == "write" else "none", idempotent=risk != "write",
            input_schema=input_schema, output_schema={"type": "object"}, tags=("knowledge", "deprecated")), handler)
