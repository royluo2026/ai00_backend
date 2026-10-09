"""One-way Feishu spreadsheet or Bitable catalog intake for Knowledge documents."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_ID = re.compile(r"^[A-Za-z0-9_-]{3,128}$")
_HOST = re.compile(r"(^|\.)(feishu\.cn|larksuite\.com)$", re.I)
_DOCUMENT_FIELDS = ("飞书文档", "文档链接", "文档地址", "document_url", "Document URL", "链接", "URL")
_TITLE_FIELDS = ("名称", "文档名称", "文档标题", "知识名称", "标题", "Name", "Title")


def _url_parts(value: str):
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "https" or not _HOST.search(parsed.hostname or "") or parsed.username or parsed.password or parsed.port:
        raise ValueError("Feishu HTTPS link required")
    return parsed


def parse_bitable_url(value: str) -> tuple[str, str]:
    parsed = _url_parts(value)
    segments = [part for part in parsed.path.split("/") if part]
    table = parse_qs(parsed.query).get("table", [])
    if len(segments) != 2 or segments[0] != "base" or len(table) != 1:
        raise ValueError("Bitable link must include /base/{app_token}?table={table_id}")
    app_token, table_id = segments[1], table[0]
    if not _ID.fullmatch(app_token) or not _ID.fullmatch(table_id):
        raise ValueError("invalid Bitable app or table identifier")
    return app_token, table_id


def parse_catalog_url(value: str) -> tuple[str, str, str | None]:
    """Return source kind, file token and optional tab ID from a Feishu URL."""
    parsed = _url_parts(value)
    segments = [part for part in parsed.path.split("/") if part]
    if len(segments) != 2 or not _ID.fullmatch(segments[1]):
        raise ValueError("飞书清单链接应为 Wiki、电子表格或多维表格链接")
    if segments[0] == "base":
        app, table = parse_bitable_url(value)
        return "bitable", app, table
    if segments[0] == "wiki":
        return "wiki_sheet", segments[1], None
    if segments[0] == "sheets":
        sheet = parse_qs(parsed.query).get("sheet", [])
        if len(sheet) > 1 or (sheet and not _ID.fullmatch(sheet[0])):
            raise ValueError("工作表标识无效")
        return "sheet", segments[1], sheet[0] if sheet else None
    raise ValueError("飞书清单链接应为 Wiki、电子表格或多维表格链接")


def parse_document_url(value: str) -> str:
    parsed = _url_parts(value)
    segments = [part for part in parsed.path.split("/") if part]
    if len(segments) != 2 or segments[0] not in {"docx", "wiki"} or not _ID.fullmatch(segments[1]):
        raise ValueError("Feishu docx or wiki link required")
    return segments[1]


def _field_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "".join(_field_text(part) for part in value).strip()
    if isinstance(value, dict):
        return str(value.get("link") or value.get("url") or value.get("text") or value.get("name") or "").strip()
    return ""


def catalog_row(record: dict) -> dict[str, str | None]:
    record_id = str(record.get("record_id") or "").strip()
    fields = record.get("fields") or {}
    title = next((_field_text(fields.get(key)) for key in _TITLE_FIELDS if _field_text(fields.get(key))), record_id)
    document_url = next((_field_text(fields.get(key)) for key in _DOCUMENT_FIELDS if _field_text(fields.get(key))), "")
    error = None
    token = None
    if not document_url:
        error = "document_link_missing"
    else:
        try:
            token = parse_document_url(document_url)
        except ValueError:
            error = "document_link_invalid"
    return {"record_id": record_id, "title": title, "document_url": document_url or None, "document_token": token, "error": error}


def sheet_catalog_records(values: list[list]) -> list[dict]:
    """Adapt a header-based worksheet to catalog records with stable document identities."""
    if not values:
        raise ValueError("总表为空，缺少表头")
    headers = [_field_text(cell) for cell in values[0]]
    link_headers = [header for header in headers if header in _DOCUMENT_FIELDS]
    if not link_headers:
        # Existing user sheets often use a custom header. Infer a column only when
        # its cells contain unambiguous Feishu document URLs.
        matches = []
        for index, header in enumerate(headers):
            if not header:
                continue
            for cells in values[1:]:
                if index >= len(cells):
                    continue
                try:
                    parse_document_url(_field_text(cells[index]))
                except ValueError:
                    continue
                matches.append(index)
                break
        if len(matches) != 1:
            raise ValueError("总表缺少明确的文档链接列（飞书文档、文档链接或链接）")
        inferred_link_index = matches[0]
    else:
        inferred_link_index = None
    result = []
    counts: dict[str, int] = {}
    for row_number, cells in enumerate(values[1:], start=2):
        if not any(_field_text(cell) for cell in cells):
            continue
        fields = {header: cells[index] if index < len(cells) else "" for index, header in enumerate(headers) if header}
        if inferred_link_index is not None:
            fields["飞书文档"] = cells[inferred_link_index] if inferred_link_index < len(cells) else ""
        explicit_id = next((_field_text(fields.get(name)) for name in ("GID", "gid", "ID", "编号") if _field_text(fields.get(name))), "")
        document_url = next((_field_text(fields.get(name)) for name in _DOCUMENT_FIELDS if _field_text(fields.get(name))), "")
        try:
            document_token = parse_document_url(document_url)
        except ValueError:
            document_token = ""
        identity = explicit_id or (f"sheet:{document_token}" if document_token else f"sheet-row:{row_number}")
        counts[identity] = counts.get(identity, 0) + 1
        # Duplicate links remain visible as errors; they cannot share a record ID.
        if counts[identity] > 1:
            identity = f"{identity}:{row_number}"
        result.append({"record_id": identity[:128], "fields": fields})
    if not result:
        raise ValueError("总表没有可同步的清单行，已取消同步")
    if not any(catalog_row(record)["document_token"] for record in result):
        raise ValueError("总表未读到有效的飞书文档链接，已取消同步以保护现有清单")
    return result


def fetch_all_records(fetch_page, *, max_pages: int = 100, max_records: int = 10000) -> list[dict]:
    records: list[dict] = []
    token = None
    seen = set()
    for _ in range(max_pages):
        if token in seen:
            raise ValueError("incomplete Bitable pagination: repeated page token")
        seen.add(token)
        page = fetch_page(token)
        items = page.get("items")
        if not isinstance(items, list):
            raise ValueError("incomplete Bitable pagination: missing items")
        records.extend(items)
        if len(records) > max_records:
            raise ValueError("Bitable record limit exceeded")
        if not page.get("has_more"):
            return records
        token = page.get("page_token")
        if not token:
            raise ValueError("incomplete Bitable pagination: missing next page")
    raise ValueError("incomplete Bitable pagination: page limit exceeded")


def reconcile_catalog_rows(incoming: list[dict], existing: dict[str, dict], make_gid) -> tuple[list[dict], list[str]]:
    """Plan one complete snapshot without mutating the database."""
    counts: dict[str, int] = {}
    for row in incoming:
        if row.get("document_token") and not row.get("error"):
            counts[row["document_token"]] = counts.get(row["document_token"], 0) + 1
    seen_records = set()
    rows = []
    retired = []
    for row in incoming:
        record_id = str(row.get("record_id") or "")
        if not record_id or record_id in seen_records:
            raise ValueError("duplicate or missing Feishu record ID")
        seen_records.add(record_id)
        old = existing.get(record_id) or {}
        error = row.get("error") or ("document_link_duplicate" if counts.get(row.get("document_token"), 0) > 1 else None)
        token = row.get("document_token") if not error else None
        old_source = old.get("source_gid")
        changed = token != old.get("document_token") or bool(error) or not old_source
        if old_source and changed:
            retired.append(old_source)
        source_gid = (make_gid("source") if token else None) if changed else old_source
        rows.append({**row, "gid": old.get("gid") or make_gid("catalog_record"),
                     "source_gid": source_gid, "source_new": bool(source_gid and changed),
                     "error": error, "active": True})
    for record_id, old in existing.items():
        if record_id not in seen_records and old.get("source_gid"):
            retired.append(old["source_gid"])
    return rows, list(dict.fromkeys(retired))
