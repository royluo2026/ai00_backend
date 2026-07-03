"""
backend/routers/annotations.py
───────────────────────────────
工作台标注数据云端持久化（wb_annotations）

GET  /api/annotations/{key}   → { data: ... }
PUT  /api/annotations/{key}   → { success: true }
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Any
import logging

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user

router = APIRouter(prefix="/api/annotations", tags=["annotations"])
_log = logging.getLogger(__name__)


class AnnotationPutBody(BaseModel):
    data: Any = None


@router.get("/{key}")
def get_annotation(key: str, current_user=Depends(get_current_user)):
    import json as _json
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT data FROM workmanship_app_wb_annotations WHERE key = %s", (key,))
        row = cur.fetchone()
        if not row:
            return {"data": None}
        try:
            parsed = _json.loads(row["data"] or '{}')
        except Exception:
            _log.warning("get_annotation: JSON 解析失败 key=%s", key, exc_info=True)
            parsed = row["data"]
        return {"data": parsed}


@router.put("/{key}")
def put_annotation(key: str, body: AnnotationPutBody, current_user=Depends(get_current_user)):
    import json as _json
    data_str = _json.dumps(body.data) if body.data is not None else "{}"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO workmanship_app_wb_annotations (key, data, updated_at)
            VALUES (%s, %s, NOW())
            ON DUPLICATE KEY UPDATE
              data       = VALUES(data),
              updated_at = NOW()
            """,
            (key, data_str),
        )
        conn.commit()
    return {"success": True}
