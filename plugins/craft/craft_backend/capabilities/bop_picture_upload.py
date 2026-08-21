"""Governed BOP picture upload to the configured blob or local fallback store."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
import uuid

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec

from ..routers._bop._constants import _BOP_PICS_DIR, _BOP_PICS_MAX


def apply_bop_picture_upload(payload: dict[str, Any], _context: CapabilityContext) -> dict[str, Any]:
    filename = str(payload.get("filename") or "").strip()
    mime = str(payload.get("mime") or "").strip().lower()
    data_b64 = payload.get("data_b64")
    if not filename:
        raise ValueError("filename is required")
    if not mime.startswith("image/"):
        raise ValueError("only image MIME types are allowed")
    if not isinstance(data_b64, str):
        raise ValueError("data_b64 must be a string")
    try:
        data = base64.b64decode(data_b64, validate=True)
    except Exception as exc:
        raise ValueError("invalid base64 data") from exc
    if len(data) > _BOP_PICS_MAX:
        raise ValueError("image exceeds the 5MB limit")

    from backend.platform_sdk import blob_storage

    ext = Path(filename).suffix.lower() or {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}.get(mime, ".jpg")
    uploaded = blob_storage.upload(data, ext, mime, prefix="bop_pics")
    if uploaded:
        return {"data": {"url": uploaded}}
    _BOP_PICS_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = uuid.uuid4().hex + ext
    (_BOP_PICS_DIR / stored_name).write_bytes(data)
    return {"data": {"url": f"/static/uploads/bop_pics/{stored_name}"}}


def register_bop_picture_upload_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.picture.upload", owner="craft",
        description="Upload a bounded image asset for BOP picture references.",
        use_when="A governed Craft consumer uploads an image used by a BOP entry or process view.",
        do_not_use_when="The request changes BOP entities, links, or metadata, or uploads non-image artifacts.",
        risk="write", confirmation="user", idempotent=False, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["filename", "mime", "data_b64"], "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "additionalProperties": True},
        tags=("craft", "bop", "picture", "upload"),
    ), apply_bop_picture_upload)


__all__ = ["apply_bop_picture_upload", "register_bop_picture_upload_capability"]
