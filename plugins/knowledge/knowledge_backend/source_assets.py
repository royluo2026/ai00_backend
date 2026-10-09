"""Read historical tenant-scoped Knowledge image assets."""
from __future__ import annotations

import base64

from .storage import get_immutable

_EXTENSION = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


def asset_data_url(asset: dict) -> str:
    media_type = str(asset["media_type"])
    if media_type not in _EXTENSION or int(asset["byte_size"]) > 10_000_000:
        raise ValueError("unsupported Knowledge image")
    data = get_immutable(str(asset["object_key"]), str(asset["content_sha256"]))
    if data is None or len(data) != int(asset["byte_size"]):
        raise RuntimeError("Knowledge image unavailable")
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"
