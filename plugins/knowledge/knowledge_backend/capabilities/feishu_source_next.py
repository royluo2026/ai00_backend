"""Manual Feishu document pull into immutable, unaccepted Knowledge source candidates."""
from __future__ import annotations

import hashlib
import json

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn
from plugins.knowledge.knowledge_backend.feishu_markdown import convert_blocks
from plugins.knowledge.knowledge_backend.feishu_source import read_document_blocks
from plugins.knowledge.knowledge_backend.ids import new_knowledge_id
from plugins.knowledge.knowledge_backend.provider import register_capability
from plugins.knowledge.knowledge_backend.source_assets import asset_data_url, store_source_image
from plugins.knowledge.knowledge_backend.storage import get_immutable, put_immutable
from .knowledge_documents_next import _require_document_editor, _require_superadmin, _tenant, _trusted_profile


def _source_evidence(snapshot_gid: str, source_gid: str, digest: str) -> EvidenceRef:
    return EvidenceRef(kind="knowledge.source.snapshot", reference=f"knowledge-source-snapshot:{snapshot_gid}",
                       digest=f"sha256:{digest}", metadata={"source_gid": source_gid})


def pull_source(payload: dict, context: CapabilityContext) -> CapabilityOutput:
    tenant = _tenant(context)
    source_gid = str(payload.get("source_gid") or "").strip()
    with get_knowledge_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT gid,document_url,document_token,linked_document_gid FROM workmanship_know_feishu_sources "
            "WHERE gid=%s AND tenant_gid=%s AND active=TRUE", (source_gid, tenant),
        )
        source = cur.fetchone()
        if not source:
            raise LookupError("active Feishu source not found")
        source = dict(source)
        linked = source.get("linked_document_gid")
        if linked:
            cur.execute("SELECT gid,created_by FROM workmanship_know_documents WHERE gid=%s AND tenant_gid=%s", (linked, tenant))
            document = cur.fetchone()
            if not document:
                raise LookupError("linked Markdown document not found")
            _require_document_editor(cur, dict(document), context, tenant)
        else:
            _require_superadmin(context, tenant)
    # Read and convert before any metadata write. Failure cannot advance the accepted baseline.
    document_token, blocks = read_document_blocks(source["document_url"])
    snapshot_gid = new_knowledge_id("snapshot")
    assets = []
    def resolve_asset(token: str, kind: str) -> str:
        if kind != "image":
            raise ValueError("unsupported Feishu media kind")
        asset = store_source_image(tenant_gid=tenant, source_gid=source_gid,
                                   snapshot_gid=snapshot_gid, feishu_token=token)
        assets.append(asset)
        return asset["markdown_ref"]
    converted = convert_blocks(blocks, resolve_asset=resolve_asset)
    markdown = converted.markdown
    data = markdown.encode("utf-8")
    if len(data) > 5_000_000:
        raise ValueError("converted Markdown exceeds 5 MB")
    digest = hashlib.sha256(data).hexdigest()
    object_key = f"knowledge/{tenant}/sources/{source_gid}/snapshots/{snapshot_gid}/document.{digest}.md"
    stored = put_immutable(object_key, data, "text/markdown; charset=utf-8")
    if not stored or stored.get("object_key") != object_key or stored.get("sha256") != digest:
        raise RuntimeError("OIS source snapshot verification failed")
    with get_knowledge_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_know_feishu_snapshots "
                "(gid,tenant_gid,source_gid,document_token,object_key,content_sha256,byte_size,anchors_json,diagnostics_json,complete,created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (snapshot_gid, tenant, source_gid, document_token, object_key, digest, len(data),
                 json.dumps(converted.anchors, ensure_ascii=False), json.dumps(converted.diagnostics, ensure_ascii=False),
                 converted.complete, context.user_gid),
            )
            for asset in assets:
                if not asset["new"]:
                    continue
                cur.execute(
                    "INSERT INTO workmanship_know_feishu_assets "
                    "(gid,tenant_gid,snapshot_gid,source_gid,feishu_token,object_key,content_sha256,byte_size,media_type) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (asset["gid"], tenant, snapshot_gid, source_gid, asset["feishu_token"],
                     asset["object_key"], asset["content_sha256"], asset["byte_size"], asset["media_type"]),
                )
        conn.commit()
    result = {"snapshot_gid": snapshot_gid, "source_gid": source_gid, "document_token": document_token,
              "markdown": markdown, "sha256": digest, "anchors": converted.anchors,
              "diagnostics": converted.diagnostics, "complete": converted.complete}
    return CapabilityOutput(data=result, evidence=(_source_evidence(snapshot_gid, source_gid, digest),))


def get_source_snapshot(payload: dict, context: CapabilityContext) -> CapabilityOutput:
    tenant = _tenant(context)
    _trusted_profile(context, tenant)
    gid = str(payload.get("snapshot_gid") or "").strip()
    with get_knowledge_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT gid,source_gid,document_token,object_key,content_sha256,anchors_json,diagnostics_json,complete "
            "FROM workmanship_know_feishu_snapshots WHERE gid=%s AND tenant_gid=%s", (gid, tenant),
        )
        row = cur.fetchone()
    if not row:
        raise LookupError("source snapshot not found")
    markdown = get_immutable(row["object_key"], row["content_sha256"])
    if markdown is None:
        raise RuntimeError("OIS source snapshot unavailable")
    anchors = row["anchors_json"] if isinstance(row["anchors_json"], list) else json.loads(row["anchors_json"])
    diagnostics = row["diagnostics_json"] if isinstance(row["diagnostics_json"], list) else json.loads(row["diagnostics_json"])
    result = {"snapshot_gid": gid, "source_gid": row["source_gid"], "document_token": row["document_token"],
              "markdown": markdown.decode("utf-8"), "sha256": row["content_sha256"],
              "anchors": anchors, "diagnostics": diagnostics,
              "complete": bool(row["complete"])}
    return CapabilityOutput(data=result, evidence=(_source_evidence(gid, row["source_gid"], row["content_sha256"]),))


def get_source_asset(payload: dict, context: CapabilityContext) -> dict:
    tenant = _tenant(context)
    _trusted_profile(context, tenant)
    gid = str(payload.get("asset_gid") or "").strip()
    with get_knowledge_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT object_key,content_sha256,byte_size,media_type FROM workmanship_know_feishu_assets "
            "WHERE gid=%s AND tenant_gid=%s", (gid, tenant),
        )
        row = cur.fetchone()
    if not row:
        raise LookupError("Knowledge source image not found")
    return {"asset_gid": gid, "data_url": asset_data_url(dict(row))}


def register_feishu_source_capabilities(registry) -> None:
    common = {"owner": "knowledge", "subject_concepts": ("knowledge.source", "knowledge.document"), "plugin_callable": True}
    candidate = {"type": "object", "additionalProperties": False,
        "required": ["snapshot_gid", "source_gid", "document_token", "markdown", "sha256", "anchors", "diagnostics", "complete"],
        "properties": {"snapshot_gid": {"type": "string"}, "source_gid": {"type": "string"}, "document_token": {"type": "string"},
                       "markdown": {"type": "string"}, "sha256": {"type": "string"},
                       "anchors": {"type": "array", "items": {"type": "object"}},
                       "diagnostics": {"type": "array", "items": {"type": "object"}}, "complete": {"type": "boolean"}}}
    register_capability(registry, CapabilitySpec(
        **common, id="knowledge.source.pull", description="Pull one Feishu document into an unaccepted immutable Markdown source candidate.",
        use_when="An editor manually checks one linked Feishu document for changes.", do_not_use_when="Confirming a candidate as a Markdown revision.",
        effects=("read:feishu.document", "create:knowledge.source_snapshot"), risk="write", confirmation="user", idempotent=False,
        input_schema={"type": "object", "required": ["source_gid"], "properties": {"source_gid": {"type": "string"}}},
        output_schema=candidate, tags=("knowledge", "source", "pull")), pull_source)
    register_capability(registry, CapabilitySpec(
        **common, id="knowledge.source.snapshot.get", description="Read an immutable Feishu-converted Markdown candidate.",
        use_when="Comparing a pulled source with the accepted baseline.", do_not_use_when="Reading a confirmed document revision.",
        effects=("read:knowledge.source_snapshot",),
        input_schema={"type": "object", "required": ["snapshot_gid"], "properties": {"snapshot_gid": {"type": "string"}}},
        output_schema=candidate, tags=("knowledge", "source", "read")), get_source_snapshot)
    register_capability(registry, CapabilitySpec(
        **common, id="knowledge.source.asset.get", description="Read one tenant-scoped copied Feishu image.",
        use_when="A Markdown preview needs an image referred to by a source snapshot.", do_not_use_when="Fetching arbitrary Feishu URLs.",
        effects=("read:knowledge.source_asset",),
        input_schema={"type": "object", "required": ["asset_gid"], "properties": {"asset_gid": {"type": "string"}}},
        output_schema={"type": "object", "additionalProperties": False, "required": ["asset_gid", "data_url"],
                       "properties": {"asset_gid": {"type": "string"}, "data_url": {"type": "string"}}},
        tags=("knowledge", "source", "asset", "read")), get_source_asset)
