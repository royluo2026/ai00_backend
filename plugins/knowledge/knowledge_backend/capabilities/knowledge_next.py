"""Secure read-only knowledge adapters for the Capability Kernel."""
from __future__ import annotations
from typing import Any
from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, EvidenceRef
from plugins.knowledge.knowledge_backend.contracts import ENTRY_SCHEMA, ENTRY_SEARCH_SCHEMA, entry_ref
from plugins.knowledge.knowledge_backend.provider import register_capability

def _json_value(value: Any, default: Any) -> Any:
    if value is None: return default
    if isinstance(value, str):
        import json
        try: return json.loads(value)
        except (TypeError, ValueError): return default
    return value

def _visible_clause(context: CapabilityContext, alias: str = "k") -> tuple[str, list[Any]]:
    """Global, owner, or same-team visibility; project rows stay owner-only."""
    from backend.platform_sdk.identity import get_active_team_member_gids

    members = get_active_team_member_gids(str(context.team_gid or ""))
    clauses = [f"{alias}.share_scope='global'", f"{alias}.creator_gid=%s"]
    params: list[Any] = [context.user_gid]
    if members:
        placeholders = ",".join(["%s"] * len(members))
        clauses.append(f"({alias}.share_scope='team' AND {alias}.creator_gid IN ({placeholders}))")
        params.extend(members)
    return "(" + " OR ".join(clauses) + ")", params

def _entry(row: dict[str, Any], *, include_content: bool = False) -> dict[str, Any]:
    tags = [str(value) for value in (_json_value(row.get("tags"), []) or [])]
    result = {"object_ref": entry_ref(row.get("gid", "")), "gid": row.get("gid", ""), "display_id": row.get("display_id") or "", "title": row.get("title") or "",
              "entry_type": row.get("entry_type") or "guide", "status": row.get("status") or "draft",
              "share_scope": row.get("share_scope") or "team", "tags": tags,
              "creator_gid": row.get("creator_gid") or "", "updated_at": str(row.get("updated_at") or "")}
    if include_content:
        content_ref = _json_value(row.get("content_ref"), {}) or {}
        content_ref = {
            key: str(content_ref[key])
            for key in ("object_key", "ois_url", "sha256", "document_gid", "revision_gid", "proposal_gid")
            if content_ref.get(key) is not None
        }
        attachments = []
        for raw in _json_value(row.get("attachments"), []) or []:
            if not isinstance(raw, dict):
                continue
            attachments.append({
                key: (int(raw[key]) if key == "byte_size" else str(raw[key]))
                for key in ("name", "url", "object_key", "sha256", "media_type", "byte_size")
                if raw.get(key) is not None
            })
        result.update({"content_md": row.get("content_md") or "", "content_ref": content_ref,
                       "related_part_nos": [str(value) for value in (_json_value(row.get("related_part_nos"), []) or [])], "related_operation_gids": [str(value) for value in (_json_value(row.get("related_operation_gids"), []) or [])],
                       "attachments": attachments, "source_gid": str(row["source_gid"]) if row.get("source_gid") is not None else None, "source_label": row.get("source_label") or "", "maintainer_gid": row.get("maintainer_gid") or ""})
    return result

def _entry_evidence(row: dict[str, Any]) -> EvidenceRef:
    ref = _json_value(row.get("content_ref"), {})
    reference = str(ref.get("object_key") or ref.get("ois_url") or f"knowledge://entry/{row.get('gid', '')}")
    if ref.get("object_key") and not reference.startswith("ois://"):
        reference = "ois://" + reference
    digest = str(ref.get("sha256") or "")
    if digest and not digest.startswith("sha256:"):
        digest = "sha256:" + digest
    return EvidenceRef(
        kind="ois.revision" if reference.startswith("ois://") or ref.get("ois_url") else "knowledge.entry",
        reference=reference,
        digest=digest or None,
        summary=str(row.get("title") or "Knowledge entry"),
        metadata={key: ref[key] for key in ("document_gid", "revision_gid", "proposal_gid") if ref.get(key)},
    )
def get_knowledge(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    gid = str(payload.get("gid") or "").strip()
    if not gid: raise ValueError("gid is required")
    from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn as get_conn
    visible, params = _visible_clause(context)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM workmanship_know_entries k WHERE k.gid = %s AND {visible}", [gid, *params])
            row = cur.fetchone()
    if not row: raise LookupError("知识条目不存在或当前用户不可见")
    raw = dict(row)
    return CapabilityOutput(data=_entry(raw, include_content=True), evidence=(_entry_evidence(raw),))

def search_knowledge(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    limit = max(1, min(int(payload.get("limit") or 20), 100))
    entry_type = str(payload.get("entry_type") or "").strip()
    from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn as get_conn
    visible, params = _visible_clause(context)
    clauses = [visible]; query_params: list[Any] = list(params)
    if query:
        clauses.append("(k.title LIKE %s OR k.content_md LIKE %s OR CAST(k.tags AS CHAR) LIKE %s)")
        like = f"%{query}%"; query_params.extend([like, like, like])
    if entry_type: clauses.append("k.entry_type = %s"); query_params.append(entry_type)
    query_params.append(limit)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT k.gid, k.display_id, k.title, k.entry_type, k.status, k.share_scope, k.tags, k.creator_gid, k.updated_at, k.content_md, k.content_ref " + f"FROM workmanship_know_entries k WHERE {' AND '.join(clauses)} ORDER BY k.updated_at DESC LIMIT %s", query_params)
            rows = cur.fetchall()
    items = []
    for raw in rows:
        item = _entry(dict(raw)); item["content_preview"] = str(raw.get("content_md") or "").replace("\n", " ").strip()[:240]; items.append(item)
    return CapabilityOutput(data={"items": items, "total": len(items), "query": query}, evidence=tuple(_entry_evidence(dict(row)) for row in rows))

def register_knowledge_capabilities(registry) -> None:
    from backend.capability_v2.provider_contracts import CapabilitySpec
    from plugins.knowledge.knowledge_backend.operations import KnowledgeOperationsProvider
    from backend.domain_ports.operations import operations_registry

    operations_registry.register(KnowledgeOperationsProvider())
    register_capability(registry, CapabilitySpec(owner="knowledge", id="knowledge.get", version=1, description="读取当前用户有权访问的知识条目及 Markdown 正文.", permissions=("knowledge.view",), plugin_callable=True, input_schema={"type": "object", "required": ["gid"], "properties": {"gid": {"type": "string"}}}, output_schema=ENTRY_SCHEMA, tags=("knowledge", "read")), get_knowledge)
    register_capability(registry, CapabilitySpec(owner="knowledge", id="knowledge.search", version=1, description="按标题、Markdown 正文和标签搜索知识条目.", permissions=("knowledge.view",), plugin_callable=True, input_schema={"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "entry_type": {"type": "string"}}}, output_schema=ENTRY_SEARCH_SCHEMA, tags=("knowledge", "read")), search_knowledge)
