"""Immutable Feishu image copies, addressed by a tenant-scoped Knowledge asset GID."""
from __future__ import annotations

import base64
import hashlib
import re

from backend.services.feishu_service import feishu_service
from .ids import new_knowledge_id
from .storage import get_immutable, put_immutable

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_EXTENSION = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


def store_source_image(*, tenant_gid: str, source_gid: str, snapshot_gid: str, feishu_token: str) -> dict:
    if not all(_SEGMENT.fullmatch(part or "") for part in (tenant_gid, source_gid, snapshot_gid)):
        raise ValueError("invalid Knowledge source identity")
    data, media_type = feishu_service.download_doc_media(feishu_token)
    if not data or media_type not in _EXTENSION:
        raise ValueError("unsupported Feishu image")
    digest = hashlib.sha256(data).hexdigest()
    asset_gid = new_knowledge_id("asset")
    key = f"knowledge/{tenant_gid}/sources/{source_gid}/snapshots/{snapshot_gid}/assets/{asset_gid}.{digest}.{_EXTENSION[media_type]}"
    stored = put_immutable(key, data, media_type)
    if not stored or stored.get("object_key") != key or stored.get("sha256") != digest:
        raise RuntimeError("OIS image verification failed")
    return {"gid": asset_gid, "feishu_token": feishu_token, "object_key": key,
            "content_sha256": digest, "byte_size": len(data), "media_type": media_type,
            "markdown_ref": f"knowledge-asset:{asset_gid}"}


def asset_data_url(asset: dict) -> str:
    media_type = str(asset["media_type"])
    if media_type not in _EXTENSION or int(asset["byte_size"]) > 10_000_000:
        raise ValueError("unsupported Knowledge image")
    data = get_immutable(str(asset["object_key"]), str(asset["content_sha256"]))
    if data is None or len(data) != int(asset["byte_size"]):
        raise RuntimeError("Knowledge image unavailable")
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"
