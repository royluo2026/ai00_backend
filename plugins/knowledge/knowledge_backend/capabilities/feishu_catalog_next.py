"""Knowledge-owned read-only intake from an authoritative Feishu table."""
from __future__ import annotations

from datetime import UTC, datetime

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec
from backend.services.feishu_service import feishu_service
from plugins.knowledge.knowledge_backend.data.connection import get_knowledge_conn
from plugins.knowledge.knowledge_backend.feishu_catalog import (
    catalog_row, fetch_all_records, parse_catalog_url, reconcile_catalog_rows, sheet_catalog_records,
)
from plugins.knowledge.knowledge_backend.ids import new_knowledge_id
from plugins.knowledge.knowledge_backend.provider import register_capability
from .knowledge_documents_next import _require_superadmin, _tenant, _trusted_profile


def get_catalog_config(_payload: dict, context: CapabilityContext) -> dict:
    tenant = _tenant(context)
    _require_superadmin(context, tenant)
    with get_knowledge_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT source_url,updated_at FROM workmanship_know_feishu_catalog_config WHERE tenant_gid=%s", (tenant,))
        row = cur.fetchone()
    return {"configured": bool(row), "url": str(row["source_url"]) if row else None,
            "updated_at": row["updated_at"].isoformat() if row and row.get("updated_at") else None}


def save_catalog_config(payload: dict, context: CapabilityContext) -> dict:
    tenant = _tenant(context)
    _require_superadmin(context, tenant)
    url = str(payload.get("url") or "").strip()
    source_kind, app_token, table_id = parse_catalog_url(url)
    # The existing token columns also hold a Wiki or spreadsheet token and tab selector.
    # Resolve the Wiki only during manual sync so a valid link can be saved offline.
    table_id = table_id or ("总表" if source_kind != "bitable" else None)
    with get_knowledge_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_know_feishu_catalog_config (tenant_gid,source_url,app_token,table_id,updated_by) "
                "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE source_url=VALUES(source_url),"
                "app_token=VALUES(app_token),table_id=VALUES(table_id),updated_by=VALUES(updated_by),updated_at=NOW()",
                (tenant, url, app_token, table_id, context.user_gid),
            )
        conn.commit()
    return {"configured": True, "url": url, "updated_at": datetime.now(UTC).isoformat()}


def sync_catalog(_payload: dict, context: CapabilityContext) -> dict:
    tenant = _tenant(context)
    _require_superadmin(context, tenant)
    with get_knowledge_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT source_url,app_token,table_id FROM workmanship_know_feishu_catalog_config WHERE tenant_gid=%s", (tenant,))
        config = cur.fetchone()
    if not config:
        raise LookupError("飞书知识清单尚未配置")
    app_token, table_id = str(config["app_token"]), str(config["table_id"])
    # Finish every remote page before opening a write transaction. Partial reads never retire rows.
    source_kind, _, _ = parse_catalog_url(str(config["source_url"]))
    if source_kind == "bitable":
        remote = fetch_all_records(lambda token: feishu_service.list_bitable_records(app_token, table_id, token))
    else:
        spreadsheet_token = app_token
        if source_kind == "wiki_sheet":
            node = feishu_service.resolve_wiki_node(app_token)
            if node.get("obj_type") != "sheet" or not node.get("obj_token"):
                raise ValueError("Wiki 链接未指向飞书电子表格")
            spreadsheet_token = str(node["obj_token"])
        sheets = feishu_service.list_spreadsheet_sheets(spreadsheet_token)
        selected = next((item for item in sheets if item.get("title") == "总表"), None)
        if not selected:
            raise ValueError("电子表格中找不到“总表”工作表")
        sheet_id = str(selected.get("sheet_id") or "")
        properties = selected.get("grid_properties") or {}
        row_count = int(properties.get("row_count") or properties.get("rowCount") or 0)
        if not sheet_id or row_count < 1 or row_count > 10000:
            raise ValueError("无法确定“总表”的完整行数，已取消同步")
        values = []
        for start in range(1, row_count + 1, 500):
            end = min(start + 499, row_count)
            part = feishu_service.read_spreadsheet_values(spreadsheet_token, sheet_id, start, end)
            if len(part) > end - start + 1:
                raise ValueError("电子表格返回的行数超出请求范围")
            values.extend(part)
            values.extend([[] for _ in range(end - start + 1 - len(part))])
        remote = sheet_catalog_records(values)
    parsed = [catalog_row(record) for record in remote]
    with get_knowledge_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_url,app_token,table_id FROM workmanship_know_feishu_catalog_config WHERE tenant_gid=%s FOR UPDATE", (tenant,))
            current = cur.fetchone()
            if not current or (current["source_url"], current["app_token"], current["table_id"]) != (config["source_url"], app_token, table_id):
                raise ValueError("catalog configuration changed during sync")
            cur.execute(
                "SELECT gid,record_id,title,source_gid,document_token,active FROM workmanship_know_feishu_catalog_records "
                "WHERE tenant_gid=%s FOR UPDATE", (tenant,),
            )
            existing = {str(row["record_id"]): dict(row) for row in cur.fetchall()}
            rows, retired = reconcile_catalog_rows(parsed, existing, new_knowledge_id)
            cur.execute("UPDATE workmanship_know_feishu_catalog_records SET active=FALSE WHERE tenant_gid=%s", (tenant,))
            for source_gid in retired:
                cur.execute("UPDATE workmanship_know_feishu_sources SET active=FALSE WHERE gid=%s AND tenant_gid=%s", (source_gid, tenant))
            for row in rows:
                if row["source_new"]:
                    cur.execute(
                        "INSERT INTO workmanship_know_feishu_sources (gid,tenant_gid,catalog_record_gid,document_url,document_token) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (row["source_gid"], tenant, row["gid"], row["document_url"], row["document_token"]),
                    )
                cur.execute(
                    "INSERT INTO workmanship_know_feishu_catalog_records "
                    "(gid,tenant_gid,record_id,title,document_url,document_token,source_gid,error_code,active) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE) ON DUPLICATE KEY UPDATE "
                    "title=VALUES(title),document_url=VALUES(document_url),document_token=VALUES(document_token),"
                    "source_gid=VALUES(source_gid),error_code=VALUES(error_code),active=TRUE,updated_at=NOW()",
                    (row["gid"], tenant, row["record_id"], row["title"][:512], row["document_url"],
                     row["document_token"], row["source_gid"], row["error"]),
                )
        conn.commit()
    return {
        "added": sum(1 for row in rows if row["record_id"] not in existing),
        "updated": sum(1 for row in rows if row["record_id"] in existing and
                       (row["source_new"] or row["title"] != existing[row["record_id"]].get("title"))),
        "inactive": sum(1 for record_id, row in existing.items() if row.get("active") and record_id not in {item["record_id"] for item in rows}),
        "errors": [{"record_id": row["record_id"], "code": row["error"]} for row in rows if row["error"]],
        "checked_at": datetime.now(UTC).isoformat(),
    }


def list_catalog(payload: dict, context: CapabilityContext) -> dict:
    tenant = _tenant(context)
    _trusted_profile(context, tenant)
    limit = max(1, min(int(payload.get("limit") or 100), 500))
    offset = max(0, int(payload.get("offset") or 0))
    with get_knowledge_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT r.gid,r.record_id,r.title,r.document_url,r.source_gid,r.error_code,r.active,r.updated_at,"
            "s.linked_document_gid FROM workmanship_know_feishu_catalog_records r "
            "LEFT JOIN workmanship_know_feishu_sources s ON s.gid=r.source_gid "
            "WHERE r.tenant_gid=%s ORDER BY r.active DESC,r.title,r.record_id LIMIT %s OFFSET %s", (tenant, limit, offset),
        )
        rows = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT COUNT(*) AS n FROM workmanship_know_feishu_catalog_records WHERE tenant_gid=%s", (tenant,))
        total = int(cur.fetchone()["n"])
    for row in rows:
        row["updated_at"] = row["updated_at"].isoformat() if row.get("updated_at") else None
        row["active"] = bool(row["active"])
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def register_feishu_catalog_capabilities(registry) -> None:
    common = {"owner": "knowledge", "subject_concepts": ("knowledge.document", "knowledge.source"), "plugin_callable": True}
    config_output = {"type": "object", "additionalProperties": False, "required": ["configured", "url", "updated_at"],
                     "properties": {"configured": {"type": "boolean"}, "url": {"type": ["string", "null"]}, "updated_at": {"type": ["string", "null"]}}}
    sync_output = {"type": "object", "additionalProperties": False, "required": ["added", "updated", "inactive", "errors", "checked_at"],
                   "properties": {"added": {"type": "integer"}, "updated": {"type": "integer"}, "inactive": {"type": "integer"},
                                  "errors": {"type": "array", "items": {"type": "object", "required": ["record_id", "code"], "properties": {"record_id": {"type": "string"}, "code": {"type": "string"}}}},
                                  "checked_at": {"type": "string"}}}
    item = {"type": "object", "additionalProperties": False,
            "required": ["gid", "record_id", "title", "document_url", "source_gid", "linked_document_gid", "error_code", "active", "updated_at"],
            "properties": {"gid": {"type": "string"}, "record_id": {"type": "string"}, "title": {"type": "string"},
                           "document_url": {"type": ["string", "null"]}, "source_gid": {"type": ["string", "null"]}, "linked_document_gid": {"type": ["string", "null"]},
                           "error_code": {"type": ["string", "null"]}, "active": {"type": "boolean"}, "updated_at": {"type": ["string", "null"]}}}
    list_output = {"type": "object", "additionalProperties": False, "required": ["items", "total", "limit", "offset"],
                   "properties": {"items": {"type": "array", "items": item}, "total": {"type": "integer"},
                                  "limit": {"type": "integer"}, "offset": {"type": "integer"}}}
    register_capability(registry, CapabilitySpec(
        **common, id="knowledge.source.catalog.config.get", description="Read the configured authoritative Feishu catalog link.",
        use_when="A superadmin opens Knowledge source settings.", do_not_use_when="Browsing catalog rows.",
        effects=("read:knowledge.source_catalog_config",), input_schema={"type": "object"}, output_schema=config_output,
        tags=("knowledge", "source", "catalog", "read")), get_catalog_config)
    register_capability(registry, CapabilitySpec(
        **common, id="knowledge.source.catalog.config.change.apply", description="Set the authoritative Feishu catalog link.",
        use_when="A superadmin changes Knowledge's Feishu catalog.", do_not_use_when="Editing Feishu rows or documents.",
        effects=("update:knowledge.source_catalog_config",), risk="write", confirmation="user", idempotent=False,
        input_schema={"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}}}, output_schema=config_output,
        tags=("knowledge", "source", "catalog", "write")), save_catalog_config)
    register_capability(registry, CapabilitySpec(
        **common, id="knowledge.source.catalog.sync", description="Pull a complete one-way Feishu catalog snapshot into Knowledge.",
        use_when="A superadmin manually refreshes the Knowledge source list.", do_not_use_when="Pulling document content.",
        effects=("update:knowledge.source_catalog",), risk="write", confirmation="user", idempotent=False,
        input_schema={"type": "object"}, output_schema=sync_output, tags=("knowledge", "source", "catalog", "write")), sync_catalog)
    register_capability(registry, CapabilitySpec(
        **common, id="knowledge.source.catalog.list", description="List imported Feishu catalog rows and conversion status.",
        use_when="A user browses Feishu knowledge sources.", do_not_use_when="Reading a Markdown revision.",
        effects=("read:knowledge.source_catalog",),
        input_schema={"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500}, "offset": {"type": "integer", "minimum": 0}}},
        output_schema=list_output, tags=("knowledge", "source", "catalog", "read")), list_catalog)
