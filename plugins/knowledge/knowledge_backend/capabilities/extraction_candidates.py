"""Knowledge-owned drafts for evidence-bound knowledge, rule and ontology suggestions."""
from __future__ import annotations

import hashlib
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from plugins.knowledge.knowledge_backend.capabilities.knowledge_documents_next import _require_document_editor, _tenant
from plugins.knowledge.knowledge_backend.contracts import document_ref, transport_value
from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn
from plugins.knowledge.knowledge_backend.ids import new_knowledge_id
from plugins.knowledge.knowledge_backend.provider import register_capability
from plugins.knowledge.knowledge_backend.revision_store import load_markdown_revision


CARD_TYPES = {"knowledge", "rule", "ontology"}
FIELDS = ("gid", "document_gid", "revision_gid", "card_type", "title", "body", "evidence_text",
          "evidence_from", "evidence_to", "evidence_sha256", "target_gid", "status",
          "created_by", "updated_by", "created_at", "updated_at")
CARD_SCHEMA = {"type": "object", "additionalProperties": False, "required": list(FIELDS),
    "properties": {key: ({"type": "integer", "minimum": 0} if key in {"evidence_from", "evidence_to"}
                        else {"anyOf": [{"type": "string"}, {"type": "null"}]} if key in {"target_gid", "created_at", "updated_at"}
                        else {"type": "string"}) for key in FIELDS}}
LIST_SCHEMA = {"type": "object", "additionalProperties": False,
    "required": ["document_gid", "items", "total"],
    "properties": {"document_gid": {"type": "string"}, "items": {"type": "array", "items": CARD_SCHEMA},
                   "total": {"type": "integer", "minimum": 0}}}


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    return transport_value({key: row.get(key) for key in FIELDS})


def _evidence(row: dict[str, Any]) -> EvidenceRef:
    return EvidenceRef(kind="knowledge.extraction_candidate", reference=f"knowledge-candidate:{row['gid']}",
        digest=f"sha256:{row['evidence_sha256']}", summary=f"{row['card_type']} candidate from {row['revision_gid']}",
        metadata={"document_gid": row["document_gid"], "revision_gid": row["revision_gid"]})


def _selection_matches(markdown: str, start: int, end: int, expected: str) -> bool:
    # CodeMirror positions count UTF-16 units; Python string indices count Unicode code points.
    encoded = markdown.encode("utf-16-le")
    if end * 2 > len(encoded):
        return False
    try:
        return encoded[start * 2:end * 2].decode("utf-16-le") == expected
    except UnicodeDecodeError:
        return False


def list_candidates(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    document_gid = str(payload.get("document_gid") or "").strip()
    if not document_gid:
        raise ValueError("document_gid is required")
    tenant = _tenant(context)
    with get_knowledge_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid FROM workmanship_know_documents WHERE gid=%s AND tenant_gid=%s", (document_gid, tenant))
            if not cur.fetchone():
                raise LookupError("document not found")
            cur.execute("SELECT " + ",".join(FIELDS) + " FROM workmanship_know_extraction_candidates "
                        "WHERE tenant_gid=%s AND document_gid=%s ORDER BY created_at DESC LIMIT 200",
                        (tenant, document_gid))
            rows = [dict(row) for row in cur.fetchall()]
    return CapabilityOutput(data={"document_gid": document_gid, "items": [_serialize(row) for row in rows],
                                  "total": len(rows)}, evidence=tuple(_evidence(row) for row in rows))


def save_candidate(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    tenant = _tenant(context)
    document_gid = str(payload.get("document_gid") or "").strip()
    revision_gid = str(payload.get("revision_gid") or "").strip()
    candidate_gid = str(payload.get("candidate_gid") or "").strip()
    card_type = str(payload.get("card_type") or "").strip()
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    target_gid = str(payload.get("target_gid") or "").strip() or None
    start, end = payload.get("evidence_from"), payload.get("evidence_to")
    evidence_text = str(payload.get("evidence_text") or "")
    if card_type not in CARD_TYPES or not title or len(title) > 255 or not body or len(body) > 10000:
        raise ValueError("card type, title and body are required within limits")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start or len(evidence_text) > 5000:
        raise ValueError("a bounded source selection is required")
    if target_gid and len(target_gid) > 128:
        raise ValueError("target_gid is too long")
    with get_knowledge_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid,created_by,published_revision_gid FROM workmanship_know_documents WHERE gid=%s AND tenant_gid=%s FOR UPDATE",
                        (document_gid, tenant))
            document = cur.fetchone()
            if not document:
                raise LookupError("document not found")
            _require_document_editor(cur, dict(document), context, tenant)
            if str(document["published_revision_gid"]) != revision_gid:
                raise ValueError("source revision changed; reload before extracting")
            cur.execute("SELECT object_key,content_sha256 FROM workmanship_know_revisions WHERE gid=%s AND document_gid=%s AND tenant_gid=%s",
                        (revision_gid, document_gid, tenant))
            revision = cur.fetchone()
            if not revision:
                raise LookupError("revision not found")
            markdown = load_markdown_revision(revision["object_key"], revision["content_sha256"])
            if not _selection_matches(markdown, start, end, evidence_text):
                raise ValueError("selection no longer matches the saved Markdown revision")
            digest = hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
            if candidate_gid:
                cur.execute("SELECT " + ",".join(FIELDS) + " FROM workmanship_know_extraction_candidates "
                            "WHERE gid=%s AND tenant_gid=%s AND document_gid=%s FOR UPDATE",
                            (candidate_gid, tenant, document_gid))
                existing = cur.fetchone()
                if not existing or existing["status"] != "draft":
                    raise PermissionError("candidate draft cannot be edited")
                if str(existing["revision_gid"]) != revision_gid or existing["card_type"] != card_type or existing["evidence_sha256"] != digest:
                    raise ValueError("candidate source identity cannot change")
                cur.execute("UPDATE workmanship_know_extraction_candidates SET title=%s,body=%s,target_gid=%s,updated_by=%s,updated_at=NOW() WHERE gid=%s",
                            (title, body, target_gid, context.user_gid, candidate_gid))
            else:
                candidate_gid = new_knowledge_id("candidate")
                cur.execute("INSERT INTO workmanship_know_extraction_candidates "
                            "(gid,tenant_gid,document_gid,revision_gid,card_type,title,body,evidence_text,evidence_from,evidence_to,evidence_sha256,target_gid,status,created_by,updated_by) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s)",
                            (candidate_gid, tenant, document_gid, revision_gid, card_type, title, body,
                             evidence_text, start, end, digest, target_gid, context.user_gid, context.user_gid))
            cur.execute("SELECT " + ",".join(FIELDS) + " FROM workmanship_know_extraction_candidates WHERE gid=%s", (candidate_gid,))
            row = dict(cur.fetchone())
        conn.commit()
    return CapabilityOutput(data=_serialize(row), evidence=(_evidence(row),))


def submit_candidate(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    tenant = _tenant(context)
    candidate_gid = str(payload.get("candidate_gid") or "").strip()
    with get_knowledge_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT " + ",".join(FIELDS) + " FROM workmanship_know_extraction_candidates WHERE gid=%s AND tenant_gid=%s FOR UPDATE",
                        (candidate_gid, tenant))
            row = cur.fetchone()
            if not row:
                raise LookupError("candidate not found")
            cur.execute("SELECT gid,created_by FROM workmanship_know_documents WHERE gid=%s AND tenant_gid=%s",
                        (row["document_gid"], tenant))
            document = cur.fetchone()
            if not document:
                raise LookupError("document not found")
            _require_document_editor(cur, dict(document), context, tenant)
            if row["status"] != "draft":
                raise ValueError("only draft candidates can be submitted")
            cur.execute("UPDATE workmanship_know_extraction_candidates SET status='submitted',updated_by=%s,updated_at=NOW() WHERE gid=%s",
                        (context.user_gid, candidate_gid))
            row = dict(row) | {"status": "submitted", "updated_by": context.user_gid}
        conn.commit()
    return CapabilityOutput(data=_serialize(row), evidence=(_evidence(row),))


def register_extraction_candidate_capabilities(registry) -> None:
    common = {"owner": "knowledge", "version": 1, "tags": ("knowledge", "candidate"), "permissions": ()}
    register_capability(registry, CapabilitySpec(**common, id="knowledge.extraction.candidate.list",
        description="List evidence-bound semantic card suggestions for one Markdown document.",
        use_when="The document's candidate sidebar is opened.", do_not_use_when="A formal semantic object is needed.",
        effects=("read:knowledge.extraction_candidate",),
        input_schema={"type": "object", "required": ["document_gid"], "properties": {"document_gid": {"type": "string"}}},
        output_schema=LIST_SCHEMA), list_candidates)
    register_capability(registry, CapabilitySpec(**common, id="knowledge.extraction.candidate.save",
        description="Save one draft semantic card suggestion tied to an exact Markdown selection.",
        use_when="A document editor reviews a selected passage and records a suggestion.", do_not_use_when="Publishing a formal object.",
        effects=("write:knowledge.extraction_candidate",), risk="write", confirmation="none", idempotent=False,
        input_schema={"type": "object", "additionalProperties": False,
            "required": ["document_gid", "revision_gid", "card_type", "title", "body", "evidence_text", "evidence_from", "evidence_to"],
            "properties": {"document_gid": {"type": "string"}, "revision_gid": {"type": "string"},
                "candidate_gid": {"type": "string"}, "card_type": {"type": "string", "enum": sorted(CARD_TYPES)},
                "title": {"type": "string"}, "body": {"type": "string"}, "target_gid": {"type": "string"},
                "evidence_text": {"type": "string"}, "evidence_from": {"type": "integer", "minimum": 0},
                "evidence_to": {"type": "integer", "minimum": 1}}},
        output_schema=CARD_SCHEMA), save_candidate)
    register_capability(registry, CapabilitySpec(**common, id="knowledge.extraction.candidate.submit",
        description="Submit a reviewed semantic card candidate for domain follow-up; never publish a formal object.",
        use_when="An editor finishes reviewing a candidate draft.", do_not_use_when="Publishing a formal object.",
        effects=("update:knowledge.extraction_candidate",), risk="write", confirmation="user", idempotent=False,
        input_schema={"type": "object", "required": ["candidate_gid"], "properties": {"candidate_gid": {"type": "string"}}},
        output_schema=CARD_SCHEMA), submit_candidate)
