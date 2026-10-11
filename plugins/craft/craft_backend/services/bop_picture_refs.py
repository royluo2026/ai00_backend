"""Project immutable screenshot references into the existing BOP picture format."""
from __future__ import annotations

import json
from urllib.parse import quote

from backend.capability_v2.contracts import ArtifactRef


def screenshot_picture(artifact_ref: dict) -> dict:
    reference = ArtifactRef.model_validate(artifact_ref).model_dump(mode="json")
    if not reference["media_type"].startswith("image/"):
        raise ValueError("screenshot_artifact_invalid")
    encoded = quote(json.dumps(reference, ensure_ascii=False, separators=(",", ":")), safe="")
    return {"url": f"artifact:{encoded}/screenshot", "object_key": "", "storage": ""}


def normalize_bop_pictures(items) -> list[dict]:
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except (ValueError, TypeError):
            items = []
    result = []
    for item in items or []:
        if isinstance(item, dict):
            if item.get("artifact_ref"):
                result.append(screenshot_picture(item["artifact_ref"]))
                continue
            picture = {
                "url": str(item.get("url") or "").strip(),
                "object_key": str(item.get("object_key") or "").strip().lstrip("/"),
                "storage": str(item.get("storage") or "").strip(),
            }
            if picture["url"] or picture["object_key"]:
                result.append(picture)
        elif isinstance(item, str) and item.strip():
            result.append({"url": item.strip(), "object_key": "", "storage": ""})
    return result
