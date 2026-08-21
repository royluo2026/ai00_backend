"""Governed Lark Sheets and Bitable data-exchange capabilities."""
from __future__ import annotations

from typing import Any

import httpx

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec


MAX_ROWS = 5000
MAX_COLUMNS = 200
MAX_PAGE_SIZE = 500
READ_OPERATIONS = ("sheets.read", "bitable.read")
WRITE_OPERATIONS = ("sheets.write", "bitable.write")


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _api_error(response: httpx.Response) -> None:
    if response.status_code != 200:
        raise CapabilityBusinessError("external_service_error", f"Lark API HTTP error: {response.text}", retryable=True)
    try:
        data = response.json()
    except ValueError as exc:
        raise CapabilityBusinessError("external_service_error", "Lark API returned invalid JSON", retryable=True) from exc
    if data.get("code") != 0:
        raise CapabilityBusinessError("external_service_error", f"Lark API error: {data.get('msg')}", retryable=True)


def _col_letter(n: int) -> str:
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result or "A"


def _bitable_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("name") or item))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    return str(value)


def read_lark_data(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in READ_OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(READ_OPERATIONS)}")
    token = _required(payload, "user_access_token")
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30) as client:
        if operation == "sheets.read":
            spreadsheet = _required(payload, "spreadsheet_token")
            sheet_range = _required(payload, "sheet_range")
            response = client.get(f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet}/values/{sheet_range}", headers=headers)
            _api_error(response)
            values = response.json().get("data", {}).get("valueRange", {}).get("values", [])
            if len(values) > MAX_ROWS or any(len(row) > MAX_COLUMNS for row in values):
                raise CapabilityBusinessError("response_limit_exceeded", "Lark sheet response exceeds bounded limits", details={"max_rows": MAX_ROWS, "max_columns": MAX_COLUMNS})
        else:
            app_token = _required(payload, "app_token")
            table_id = _required(payload, "table_id")
            page_size = payload.get("page_size", MAX_PAGE_SIZE)
            if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= MAX_PAGE_SIZE:
                raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
            url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
            records: list[dict[str, Any]] = []
            page_token = None
            while True:
                params: dict[str, Any] = {"page_size": page_size}
                if page_token:
                    params["page_token"] = page_token
                response = client.get(url, headers=headers, params=params)
                _api_error(response)
                data = response.json().get("data", {})
                records.extend(data.get("items", []))
                if len(records) > MAX_ROWS:
                    raise CapabilityBusinessError("response_limit_exceeded", "Lark bitable response exceeds bounded limits", details={"max_rows": MAX_ROWS})
                if not data.get("has_more"):
                    break
                page_token = data.get("page_token")
                if not page_token:
                    break
            if not records:
                values = []
            else:
                fields = list((records[0].get("fields") or {}).keys())[:MAX_COLUMNS]
                values = [fields] + [[_bitable_value((record.get("fields") or {}).get(field)) for field in fields] for record in records]
    if not values:
        return {"data": {"headers": [], "rows": [], "warnings": ["表格为空"]}}
    headers_row = [str(value) if value is not None else f"列{i + 1}" for i, value in enumerate(values[0])]
    rows = [[str(value) if value is not None else "" for value in row] for row in values[1:]]
    return {"data": {"headers": headers_row, "rows": rows, "warnings": []}}


def write_lark_data(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in WRITE_OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(WRITE_OPERATIONS)}")
    token = _required(payload, "user_access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60) as client:
        if operation == "sheets.write":
            spreadsheet = _required(payload, "spreadsheet_token")
            sheet_id = _required(payload, "sheet_id")
            values = payload.get("values")
            if not isinstance(values, list) or not values:
                raise ValueError("values must be a non-empty array")
            if len(values) > MAX_ROWS or len(values[0]) > MAX_COLUMNS:
                raise ValueError("values exceeds bounded limits")
            response = client.put(
                f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet}/values",
                headers=headers,
                json={"valueRange": {"range": f"{sheet_id}!A1:{_col_letter(len(values[0]))}{len(values)}", "values": values}},
            )
            _api_error(response)
            return {"data": {"success": True, "written_rows": max(0, len(values) - 1)}}

        app_token = _required(payload, "app_token")
        table_id = _required(payload, "table_id")
        records = payload.get("records")
        if not isinstance(records, list) or len(records) > MAX_ROWS:
            raise ValueError(f"records must be an array with at most {MAX_ROWS} items")
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
        written = 0
        for offset in range(0, len(records), MAX_PAGE_SIZE):
            chunk = records[offset:offset + MAX_PAGE_SIZE]
            if any(not isinstance(record, dict) for record in chunk):
                raise ValueError("each record must be an object")
            response = client.post(url, headers=headers, json={"records": [{"fields": record} for record in chunk]})
            _api_error(response)
            written += len(chunk)
    return {"data": {"success": True, "written_records": written}}


def register_lark_exchange_capabilities(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.data_exchange.lark.read", owner="craft",
        description="Read bounded Lark Sheets or Bitable tabular data.",
        use_when="A governed Craft consumer reads a user-authorized Lark data source.",
        do_not_use_when="The request writes Lark data or exports a Craft-owned dataset.",
        risk="read", permissions=("craft.read",), input_schema={"type": "object", "required": ["operation"]},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True}, tags=("craft", "data-exchange", "lark", "read"),
    ), read_lark_data)
    registry.register(CapabilitySpec(
        id="craft.data_exchange.lark.write", owner="craft",
        description="Write bounded rows to user-authorized Lark Sheets or Bitable tables.",
        use_when="A governed Craft consumer writes an approved Lark data target.",
        do_not_use_when="The request reads Lark data or mutates Craft business entities.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",), input_schema={"type": "object", "required": ["operation"]},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True}, tags=("craft", "data-exchange", "lark", "write"),
    ), write_lark_data)


__all__ = ["read_lark_data", "write_lark_data", "register_lark_exchange_capabilities"]
