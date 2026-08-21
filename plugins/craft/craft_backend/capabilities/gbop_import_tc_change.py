"""Governed Teamcenter Excel import into GBOP."""
from __future__ import annotations

import base64
import io
from typing import Any

from fastapi import UploadFile

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


async def apply_gbop_import_tc_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    if str(payload.get("operation") or "").strip() != "import_tc_excel":
        raise ValueError("operation must be import_tc_excel")
    version_gid = _required(payload, "version_gid")
    content_b64 = _required(payload, "content_b64")
    try:
        content = base64.b64decode(content_b64, validate=True)
    except Exception as exc:
        raise ValueError("content_b64 is invalid") from exc
    from ..routers import gbop as legacy
    upload = UploadFile(file=io.BytesIO(content), filename=str(payload.get("filename") or "import.xlsx"))
    return {"data": await legacy._legacy_import_tc_excel(version_gid, upload, {"gid": context.user_gid, "name": context.user_gid, "org_role": "member"})}


def register_gbop_import_tc_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.gbop.import.tc.change.apply", owner="craft",
        description="Import a bounded Teamcenter Excel workbook into a GBOP version.",
        use_when="A governed Craft consumer imports a validated Teamcenter workbook into an editable GBOP version.",
        do_not_use_when="The request imports parsed JSON rows or mutates individual GBOP entities.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "version_gid", "content_b64"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object", "additionalProperties": True}}, "additionalProperties": False},
        tags=("craft", "gbop", "import", "teamcenter", "write"),
    ), apply_gbop_import_tc_change)


__all__ = ["apply_gbop_import_tc_change", "register_gbop_import_tc_change_capability"]
