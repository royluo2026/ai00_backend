"""Bounded Knowledge context retrieval returning immutable revision refs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models_next import CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef

_METHODS = frozenset({"explicit_attachment", "ontology_relation", "metadata", "fulltext", "semantic_similarity"})


@dataclass(frozen=True)
class ContextRequest:
    query: str
    limit: int
    attachments: tuple[Mapping[str, Any], ...]
    concept_refs: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, max_limit: int = 10) -> "ContextRequest":
        query = payload.get("query", "")
        if not isinstance(query, str): raise ValueError("query must be a string")
        limit = payload.get("limit", 5)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= max_limit:
            raise ValueError(f"limit must be between 1 and {max_limit}")
        attachments = payload.get("attachments", [])
        if not isinstance(attachments, list) or any(not isinstance(item, Mapping) for item in attachments):
            raise ValueError("attachments must be an object array")
        concepts = payload.get("concept_refs", [])
        if not isinstance(concepts, list) or any(not isinstance(item, str) for item in concepts):
            raise ValueError("concept_refs must be a string array")
        return cls(query=query.strip(), limit=limit, attachments=tuple(attachments), concept_refs=tuple(concepts))


def _candidate(raw: Mapping[str, Any], method: str) -> dict[str, Any] | None:
    document_gid = raw.get("document_gid"); revision_gid = raw.get("revision_gid")
    if not document_gid or not revision_gid or method not in _METHODS: return None
    return {
        "document_gid": str(document_gid), "revision_gid": str(revision_gid),
        "title": raw.get("title"), "summary": str(raw.get("summary") or "")[:1000],
        "retrieval_method": method, "evidence": raw.get("evidence"),
    }


def explicit_attachment_candidates(request: ContextRequest, _context: CapabilityContext) -> list[dict[str, Any]]:
    return [item for raw in request.attachments if (item := _candidate(raw, "explicit_attachment"))]


def ontology_relation_candidates(request: ContextRequest, _context: CapabilityContext, *, exclude: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Ontology provider integration is registered in Tasks 7-10; no relation is invented here.
    return []


def scoped_text_candidates(request: ContextRequest, context: CapabilityContext, *, exclude: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tenant = str(context.team_gid or "").strip()
    if not tenant or not request.query: return []
    from backend.db.connection import get_conn
    pattern = f"%{request.query}%"
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT d.gid AS document_gid, d.title, r.gid AS revision_gid "
                "FROM workmanship_know_documents d JOIN workmanship_know_revisions r "
                "ON r.gid = d.published_revision_gid WHERE d.tenant_gid = %s "
                "AND (d.title LIKE %s OR d.slug LIKE %s) ORDER BY d.updated_at DESC LIMIT %s",
                (tenant, pattern, pattern, request.limit),
            )
            rows = [dict(row) for row in cursor.fetchall()]
    return [item for raw in rows if (item := _candidate({**raw, "summary": raw.get("title")}, "metadata"))]


def semantic_candidates(request: ContextRequest, context: CapabilityContext, *, exclude: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Semantic index is optional. Returning no candidates is honest and keeps retrieval bounded.
    return []


def retrieve_context(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    request = ContextRequest.from_payload(payload, max_limit=10)
    candidates = explicit_attachment_candidates(request, context)
    candidates += ontology_relation_candidates(request, context, exclude=candidates)
    if len(candidates) < request.limit: candidates += scoped_text_candidates(request, context, exclude=candidates)
    if len(candidates) < request.limit: candidates += semantic_candidates(request, context, exclude=candidates)
    selected = []; seen = set()
    for item in candidates:
        normalized = _candidate(item, str(item.get("retrieval_method") or ""))
        if normalized is None: continue
        key = (normalized["document_gid"], normalized["revision_gid"])
        if key in seen: continue
        seen.add(key); selected.append(normalized)
        if len(selected) == request.limit: break
    evidence = tuple(item["evidence"] for item in selected if isinstance(item.get("evidence"), EvidenceRef))
    for item in selected: item.pop("evidence", None)
    return CapabilityOutput(data={"items": selected, "query": request.query}, evidence=evidence)


def register_knowledge_context_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="knowledge.context.retrieve", owner="knowledge", description="Retrieve bounded immutable Knowledge revision references for one task.",
        use_when="A person or model needs decision context, not whole documents.", do_not_use_when="The caller already knows an exact document revision.",
        subject_concepts=("knowledge.document", "knowledge.revision"), effects=("read:knowledge.context",), plugin_callable=True,
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}},
        output_schema={"type": "object", "required": ["items", "query"]}, tags=("knowledge", "context", "read")), retrieve_context)
