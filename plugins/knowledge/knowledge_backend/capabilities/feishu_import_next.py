"""Review Feishu source candidates against OIS; confirm one atomic metadata transition."""
from __future__ import annotations

import hashlib
import json

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef,
)
from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn
from plugins.knowledge.knowledge_backend.ids import new_knowledge_id
from plugins.knowledge.knowledge_backend.provider import register_capability
from plugins.knowledge.knowledge_backend.revision_store import (
    canonical_markdown, load_markdown_revision, prepare_markdown_revision, store_markdown_revision,
)
from plugins.knowledge.knowledge_backend.source_merge import merge_markdown
from plugins.knowledge.knowledge_backend.storage import get_immutable
from plugins.knowledge.knowledge_backend.contracts import document_ref, revision_ref, space_ref
from .knowledge_documents_next import _require_document_editor, _require_superadmin, _tenant, _trusted_profile


def _snapshot_markdown(row: dict) -> str:
    data = get_immutable(row["object_key"], row["content_sha256"])
    if data is None:
        raise RuntimeError("OIS Feishu source candidate is unavailable")
    return data.decode("utf-8")


def _request_hash(payload: dict) -> str:
    value = {key: payload.get(key) for key in ("source_snapshot_gid", "expected_revision_gid", "markdown", "visuals_reviewed")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def preview_import(payload: dict, context: CapabilityContext) -> dict:
    tenant = _tenant(context)
    _trusted_profile(context, tenant)
    snapshot_gid = str(payload.get("source_snapshot_gid") or "").strip()
    with get_knowledge_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT s.gid,s.source_gid,s.object_key,s.content_sha256,s.complete,src.linked_document_gid "
            "FROM workmanship_know_feishu_snapshots s JOIN workmanship_know_feishu_sources src ON src.gid=s.source_gid "
            "WHERE s.gid=%s AND s.tenant_gid=%s AND src.active=TRUE", (snapshot_gid, tenant),
        )
        snapshot = cur.fetchone()
        if not snapshot:
            raise LookupError("active source candidate not found")
        cur.execute(
            "SELECT snap.gid,snap.object_key,snap.content_sha256 FROM workmanship_know_feishu_baselines b "
            "JOIN workmanship_know_feishu_snapshots snap ON snap.gid=b.snapshot_gid "
            "WHERE b.source_gid=%s AND b.tenant_gid=%s", (snapshot["source_gid"], tenant),
        )
        baseline = cur.fetchone()
        document = None
        if snapshot["linked_document_gid"]:
            cur.execute(
                "SELECT d.gid,d.current_revision_gid,r.object_key,r.content_sha256 "
                "FROM workmanship_know_documents d LEFT JOIN workmanship_know_revisions r ON r.gid=d.current_revision_gid "
                "WHERE d.gid=%s AND d.tenant_gid=%s", (snapshot["linked_document_gid"], tenant),
            )
            document = cur.fetchone()
            if not document:
                raise LookupError("linked Markdown document not found")
    incoming = _snapshot_markdown(snapshot)
    base = _snapshot_markdown(baseline) if baseline else ""
    local = (str(payload["local_markdown"]) if payload.get("local_markdown") is not None
             else load_markdown_revision(document["object_key"], document["content_sha256"]) if document else "")
    merged = merge_markdown(base, incoming, local)
    return {"source_gid": snapshot["source_gid"], "source_snapshot_gid": snapshot_gid,
            "document_gid": snapshot["linked_document_gid"],
            "current_revision_gid": document["current_revision_gid"] if document else None,
            "base_snapshot_gid": baseline["gid"] if baseline else None,
            "base": base, "incoming": incoming, "local": local,
            "merged": merged.merged, "conflicts": merged.conflicts,
            "source_diff": merged.source_diff, "local_diff": merged.local_diff,
            "source_changed": merged.source_changed, "complete": bool(snapshot["complete"])}


def _receipt(row: dict) -> CapabilityOutput:
    data = {"source_gid": row["source_gid"], "source_snapshot_gid": row["snapshot_gid"],
            "document_gid": row["document_gid"], "document_ref": document_ref(row["document_gid"]),
            "revision_gid": row["revision_gid"], "revision_ref": revision_ref(row["revision_gid"]),
            "revision_no": int(row["revision_no"]), "changed": bool(row["changed"])}
    evidence = EvidenceRef(kind="knowledge.source.import", reference=f"knowledge-source-snapshot:{row['snapshot_gid']}",
                           summary="Reviewed Feishu source import")
    return CapabilityOutput(data=data, evidence=(evidence,))


def confirm_import(payload: dict, context: CapabilityContext) -> CapabilityOutput:
    tenant = _tenant(context)
    _trusted_profile(context, tenant)
    snapshot_gid = str(payload.get("source_snapshot_gid") or "").strip()
    expected = str(payload.get("expected_revision_gid") or "").strip()
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    markdown = str(payload.get("markdown") or "")
    if not snapshot_gid or not idempotency_key or len(idempotency_key) > 128 or not markdown.strip():
        raise ValueError("snapshot, idempotency key and reviewed Markdown are required")
    if len(markdown.encode("utf-8")) > 5_000_000:
        raise ValueError("reviewed Markdown exceeds 5 MB")
    request_sha = _request_hash(payload)
    with get_knowledge_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT source_gid,snapshot_gid,request_sha256,document_gid,revision_gid,revision_no,changed "
                    "FROM workmanship_know_feishu_imports WHERE tenant_gid=%s AND idempotency_key=%s FOR UPDATE",
                    (tenant, idempotency_key),
                )
                prior = cur.fetchone()
                if prior:
                    if prior["request_sha256"] != request_sha:
                        raise ValueError("idempotency key was already used for another reviewed result")
                    return _receipt(prior)
                cur.execute(
                    "SELECT s.gid AS snapshot_gid,s.source_gid,s.object_key,s.content_sha256,s.complete,s.diagnostics_json,"
                    "src.linked_document_gid,r.title FROM workmanship_know_feishu_snapshots s "
                    "JOIN workmanship_know_feishu_sources src ON src.gid=s.source_gid "
                    "JOIN workmanship_know_feishu_catalog_records r ON r.gid=src.catalog_record_gid "
                    "WHERE s.gid=%s AND s.tenant_gid=%s AND src.active=TRUE FOR UPDATE",
                    (snapshot_gid, tenant),
                )
                snapshot = cur.fetchone()
                if not snapshot:
                    raise LookupError("active source candidate not found")
                if not snapshot["complete"]:
                    raw = snapshot.get("diagnostics_json") or []
                    issues = raw if isinstance(raw, list) else json.loads(raw)
                    visual_codes = {"image_requires_manual_review", "embedded_visual_requires_manual_review"}
                    if not (payload.get("visuals_reviewed") is True and issues
                            and all(issue.get("code") in visual_codes for issue in issues)):
                        raise ValueError("incomplete Feishu source candidate cannot be confirmed")
                source_gid = snapshot["source_gid"]
                document_gid = snapshot.get("linked_document_gid")
                document = None
                if document_gid:
                    cur.execute(
                        "SELECT d.gid,d.created_by,d.space_gid,d.title,d.current_revision_gid,"
                        "r.content_sha256 AS before_sha256,r.object_key AS current_object_key "
                        "FROM workmanship_know_documents d LEFT JOIN workmanship_know_revisions r ON r.gid=d.current_revision_gid "
                        "WHERE d.gid=%s AND d.tenant_gid=%s FOR UPDATE", (document_gid, tenant),
                    )
                    document = cur.fetchone()
                    if not document:
                        raise LookupError("linked Markdown document not found")
                    _require_document_editor(cur, dict(document), context, tenant)
                else:
                    _require_superadmin(context, tenant)
                current_revision_gid = str(document["current_revision_gid"] or "") if document else ""
                if expected != current_revision_gid:
                    raise CapabilityBusinessError(
                        "revision_conflict", "The Markdown document changed after the comparison was opened.",
                        details={"expected_revision_gid": expected, "current_revision_gid": current_revision_gid},
                    )
                # The candidate must still be available and match its immutable digest.
                _snapshot_markdown(snapshot)
                cur.execute(
                    "SELECT b.snapshot_gid,s.content_sha256 FROM workmanship_know_feishu_baselines b "
                    "JOIN workmanship_know_feishu_snapshots s ON s.gid=b.snapshot_gid "
                    "WHERE b.source_gid=%s AND b.tenant_gid=%s FOR UPDATE", (source_gid, tenant),
                )
                baseline = cur.fetchone()
                canonical = canonical_markdown(markdown)
                reviewed_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                source_unchanged = bool(baseline and baseline["content_sha256"] == snapshot["content_sha256"])
                local_unchanged = bool(document and document.get("before_sha256") == reviewed_sha)
                changed = not (source_unchanged and local_unchanged)
                if changed:
                    if document:
                        space_gid = document["space_gid"]
                        title = document["title"]
                        cur.execute("SELECT COALESCE(MAX(revision_no),0) AS n FROM workmanship_know_revisions WHERE document_gid=%s", (document_gid,))
                        revision_no = int(cur.fetchone()["n"]) + 1
                    else:
                        cur.execute("SELECT gid FROM workmanship_know_spaces WHERE tenant_gid=%s AND name=%s FOR UPDATE", (tenant, "飞书知识源"))
                        space = cur.fetchone()
                        space_gid = space["gid"] if space else new_knowledge_id("space")
                        if not space:
                            cur.execute("INSERT INTO workmanship_know_spaces (gid,tenant_gid,name,visibility,created_by) VALUES (%s,%s,%s,'team',%s)",
                                        (space_gid, tenant, "飞书知识源", context.user_gid))
                        document_gid = new_knowledge_id("document")
                        title = str(snapshot["title"] or "飞书文档")[:512]
                        revision_no = 1
                    revision_gid = new_knowledge_id("revision")
                    prepared = prepare_markdown_revision(tenant_gid=tenant, space_gid=space_gid,
                        document_gid=document_gid, revision_gid=revision_gid, markdown=canonical)
                    stored = store_markdown_revision(prepared)
                    if not document:
                        cur.execute(
                            "INSERT INTO workmanship_know_documents "
                            "(gid,tenant_gid,space_gid,title,slug,status,current_revision_gid,published_revision_gid,source_entry_gid,created_by) "
                            "VALUES (%s,%s,%s,%s,%s,'published',%s,%s,%s,%s)",
                            (document_gid, tenant, space_gid, title, f"feishu-{source_gid.lower()}",
                             revision_gid, revision_gid, source_gid, context.user_gid),
                        )
                        cur.execute("UPDATE workmanship_know_feishu_sources SET linked_document_gid=%s WHERE gid=%s AND tenant_gid=%s",
                                    (document_gid, source_gid, tenant))
                    cur.execute(
                        "INSERT INTO workmanship_know_revisions "
                        "(gid,tenant_gid,space_gid,document_gid,revision_no,base_revision_gid,object_key,content_sha256,byte_size,media_type,state,created_by,channel,request_id,before_sha256,after_sha256,change_summary) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'published',%s,'feishu_import',%s,%s,%s,%s)",
                        (revision_gid, tenant, space_gid, document_gid, revision_no, current_revision_gid or None,
                         stored["object_key"], stored["sha256"], stored["byte_size"], stored["media_type"],
                         context.user_gid, context.request_id, document.get("before_sha256") if document else None,
                         stored["sha256"], "Confirmed Feishu source candidate"),
                    )
                    if document:
                        cur.execute("UPDATE workmanship_know_documents SET current_revision_gid=%s,published_revision_gid=%s,status='published',updated_at=NOW() WHERE gid=%s",
                                    (revision_gid, revision_gid, document_gid))
                    cur.execute(
                        "INSERT INTO workmanship_know_domain_outbox (gid,event_type,event_version,subject_ref,payload,status) "
                        "VALUES (%s,'knowledge.document.published.v1',1,%s,%s,'pending')",
                        (new_knowledge_id("outbox"), document_gid,
                         json.dumps({"document_ref": document_ref(document_gid), "revision_ref": revision_ref(revision_gid), "tenant_gid": tenant}, ensure_ascii=False)),
                    )
                else:
                    revision_gid = current_revision_gid
                    cur.execute("SELECT revision_no FROM workmanship_know_revisions WHERE gid=%s AND document_gid=%s", (revision_gid, document_gid))
                    revision_no = int(cur.fetchone()["revision_no"])
                cur.execute(
                    "INSERT INTO workmanship_know_feishu_baselines (source_gid,tenant_gid,snapshot_gid,accepted_revision_gid,updated_by) "
                    "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE snapshot_gid=VALUES(snapshot_gid),"
                    "accepted_revision_gid=VALUES(accepted_revision_gid),updated_by=VALUES(updated_by),updated_at=NOW()",
                    (source_gid, tenant, snapshot_gid, revision_gid, context.user_gid),
                )
                receipt_gid = new_knowledge_id("import")
                cur.execute(
                    "INSERT INTO workmanship_know_feishu_imports "
                    "(gid,tenant_gid,source_gid,snapshot_gid,idempotency_key,request_sha256,document_gid,revision_gid,revision_no,changed,created_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (receipt_gid, tenant, source_gid, snapshot_gid, idempotency_key, request_sha,
                     document_gid, revision_gid, revision_no, changed, context.user_gid),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return _receipt({"source_gid": source_gid, "snapshot_gid": snapshot_gid, "document_gid": document_gid,
                     "revision_gid": revision_gid, "revision_no": revision_no, "changed": changed})


def register_feishu_import_capabilities(registry) -> None:
    common = {"owner": "knowledge", "subject_concepts": ("knowledge.source", "knowledge.document", "knowledge.revision"), "plugin_callable": True}
    preview_output = {"type": "object", "additionalProperties": False,
        "required": ["source_gid", "source_snapshot_gid", "document_gid", "current_revision_gid", "base_snapshot_gid",
                     "base", "incoming", "local", "merged", "conflicts", "source_diff", "local_diff", "source_changed", "complete"],
        "properties": {"source_gid": {"type": "string"}, "source_snapshot_gid": {"type": "string"},
            "document_gid": {"type": ["string", "null"]}, "current_revision_gid": {"type": ["string", "null"]},
            "base_snapshot_gid": {"type": ["string", "null"]}, "base": {"type": "string"}, "incoming": {"type": "string"},
            "local": {"type": "string"}, "merged": {"type": ["string", "null"]}, "conflicts": {"type": "array", "items": {"type": "object"}},
            "source_diff": {"type": "string"}, "local_diff": {"type": "string"}, "source_changed": {"type": "boolean"}, "complete": {"type": "boolean"}}}
    receipt_output = {"type": "object", "additionalProperties": False,
        "required": ["source_gid", "source_snapshot_gid", "document_gid", "document_ref", "revision_gid", "revision_ref", "revision_no", "changed"],
        "properties": {key: {"type": "string"} for key in ("source_gid", "source_snapshot_gid", "document_gid", "document_ref", "revision_gid", "revision_ref")}
        | {"revision_no": {"type": "integer"}, "changed": {"type": "boolean"}}}
    register_capability(registry, CapabilitySpec(
        **common, id="knowledge.source.import.preview", description="Compare accepted Feishu, incoming Feishu and current Markdown without writing.",
        use_when="An editor reviews a pulled Feishu candidate.", do_not_use_when="Publishing an accepted revision.",
        effects=("read:knowledge.source_snapshot", "read:knowledge.document"),
        input_schema={"type": "object", "required": ["source_snapshot_gid"], "properties": {"source_snapshot_gid": {"type": "string"}, "local_markdown": {"type": "string"}}},
        output_schema=preview_output, tags=("knowledge", "source", "diff", "read")), preview_import)
    register_capability(registry, CapabilitySpec(
        **common, id="knowledge.source.import.confirm", description="Confirm reviewed Markdown as one immutable OIS revision and advance the Feishu baseline.",
        use_when="An authorized editor accepts a complete candidate, or explicitly reviews every visual reference before confirming.", do_not_use_when="A comparison is stale or has unresolved non-visual content.",
        effects=("create:knowledge.revision", "update:knowledge.document_head", "update:knowledge.source_baseline"),
        risk="write", confirmation="user", idempotent=True,
        input_schema={"type": "object", "required": ["source_snapshot_gid", "expected_revision_gid", "markdown", "idempotency_key"],
            "properties": {"source_snapshot_gid": {"type": "string"}, "expected_revision_gid": {"type": "string"},
                           "markdown": {"type": "string", "minLength": 1}, "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128},
                           "visuals_reviewed": {"type": "boolean"}}},
        output_schema=receipt_output, tags=("knowledge", "source", "import", "write")), confirm_import)
