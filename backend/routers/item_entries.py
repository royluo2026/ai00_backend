"""
backend/routers/item_entries.py
───────────────────────────────
条目沟通历史云端持久化（item_entries）

GET  /api/item-entries/{item_type}/{item_gid}   → { entries: [...] }
PUT  /api/item-entries/{item_type}/{item_gid}   → { success, count, entries }
DELETE /api/item-entries/{item_type}/{item_gid} → { success }
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/item-entries", tags=["item_entries"])


class EntryPutBody(BaseModel):
    entries: list = []


def _row_to_entry(r) -> dict:
    return {
        "id":            r["id"],
        "gid":           r.get("gid", ""),
        "parent_id":     r.get("parent_id"),
        "section":       r.get("section", "detail"),
        "author":        r.get("author", "human"),
        "author_name":   r.get("author_name", ""),
        "author_gid":    r.get("author_gid", ""),
        "content":       r.get("content", ""),
        "resolved":      bool(r.get("resolved", False)),
        "sort_order":    float(r.get("sort_order", 0)),
        "read_by_human": bool(r.get("read_by_human", True)),
        "ai_status":     r.get("ai_status", "unread"),
        "created_at":    r.get("created_at", 0),
    }


@router.get("/{item_type}/{item_gid}")
def get_item_entries(item_type: str, item_gid: str,
                     current_user=Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM workmanship_work_item_entries WHERE item_type = %s AND item_gid = %s "
            "ORDER BY sort_order",
            (item_type, item_gid),
        )
        rows = cur.fetchall()
        return {"entries": [_row_to_entry(r) for r in rows]}


@router.put("/{item_type}/{item_gid}")
def put_item_entries(item_type: str, item_gid: str, body: EntryPutBody,
                     current_user=Depends(get_current_user)):
    entries = body.entries or []
    with get_conn() as conn:
        cur = conn.cursor()
        # 事务内全量替换
        cur.execute(
            "DELETE FROM workmanship_work_item_entries WHERE item_type = %s AND item_gid = %s",
            (item_type, item_gid),
        )
        saved = []
        for e in entries:
            gid = e.get("gid") or str(next_gid())
            cur.execute(
                """
                INSERT INTO workmanship_work_item_entries
                  (gid, id, item_type, item_gid, parent_id, section, author,
                   author_name, author_gid, content, resolved, sort_order,
                   read_by_human, ai_status, created_at, updated_at)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (
                    gid,
                    e.get("id"),
                    item_type,
                    item_gid,
                    e.get("parent_id"),
                    e.get("section", "detail"),
                    e.get("author", "human"),
                    e.get("author_name", ""),
                    e.get("author_gid", ""),
                    e.get("content", ""),
                    bool(e.get("resolved", False)),
                    float(e.get("sort_order", 0)),
                    bool(e.get("read_by_human", True)),
                    e.get("ai_status", "unread"),
                ),
            )
            saved.append({**e, "gid": gid})
        conn.commit()
    return {"success": True, "count": len(entries), "entries": saved}


@router.delete("/{item_type}/{item_gid}")
def delete_item_entries(item_type: str, item_gid: str,
                        current_user=Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM workmanship_work_item_entries WHERE item_type = %s AND item_gid = %s",
            (item_type, item_gid),
        )
        conn.commit()
    return {"success": True}
