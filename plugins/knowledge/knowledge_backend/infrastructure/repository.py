"""Knowledge-owned compatibility persistence; consumers never receive SQL access."""
from __future__ import annotations

import json

from ..data.connection import get_knowledge_conn
from ..ids import new_knowledge_id


class KnowledgeRepository:
    def entry_create(self, data: dict, user_gid: str, team_gid: str | None) -> dict:
        gid = new_knowledge_id("entry")
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_know_entries (gid,title,entry_type,status,share_scope,tags,creator_gid,team_id,content_md) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (gid, data["title"], data.get("entry_type", "knowledge"), data.get("status", "draft"), data.get("share_scope", "personal"), json.dumps(data.get("tags", []), ensure_ascii=False), user_gid, team_gid, data.get("content_md", "")),
                )
            conn.commit()
        return {"gid": gid}

    def entry_update(self, gid: str, updates: dict, user_gid: str) -> bool:
        allowed = {key: value for key, value in updates.items() if key in {"title", "entry_type", "status", "share_scope", "tags", "content_md"}}
        if "tags" in allowed: allowed["tags"] = json.dumps(allowed["tags"], ensure_ascii=False)
        if not allowed: return True
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE workmanship_know_entries SET {','.join(f'{key}=%s' for key in allowed)},updated_at=NOW() WHERE gid=%s AND creator_gid=%s", (*allowed.values(), gid, user_gid)); changed = cur.rowcount == 1
            conn.commit()
        return changed

    def entry_delete(self, gid: str, user_gid: str) -> bool:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workmanship_know_entries WHERE gid=%s AND creator_gid=%s", (gid, user_gid)); changed = cur.rowcount == 1
            conn.commit()
        return changed

    def space_update(self, gid: str, updates: dict, tenant_gid: str, user_gid: str) -> bool:
        allowed = {key: value for key, value in updates.items() if key in {"name", "visibility"}}
        if not allowed: return True
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE workmanship_know_spaces SET {','.join(f'{key}=%s' for key in allowed)},updated_at=NOW() WHERE gid=%s AND tenant_gid=%s AND created_by=%s", (*allowed.values(), gid, tenant_gid, user_gid)); changed = cur.rowcount == 1
            conn.commit()
        return changed

    def space_archive(self, gid: str, tenant_gid: str, user_gid: str) -> bool:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE workmanship_know_spaces SET archived=TRUE,updated_at=NOW() WHERE gid=%s AND tenant_gid=%s AND created_by=%s", (gid, tenant_gid, user_gid)); changed = cur.rowcount == 1
            conn.commit()
        return changed

    def document_archive(self, gid: str, tenant_gid: str, user_gid: str) -> bool:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE workmanship_know_documents SET status='archived',updated_at=NOW() WHERE gid=%s AND tenant_gid=%s AND created_by=%s AND status!='archived'", (gid, tenant_gid, user_gid)); changed = cur.rowcount == 1
            conn.commit()
        return changed

    def favorite_toggle(self, item_gid: str, user_gid: str) -> dict:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM workmanship_know_favorites WHERE user_gid=%s AND item_gid=%s", (user_gid, item_gid))
                if cur.fetchone(): cur.execute("DELETE FROM workmanship_know_favorites WHERE user_gid=%s AND item_gid=%s", (user_gid, item_gid)); favorite = False
                else: cur.execute("INSERT INTO workmanship_know_favorites (user_gid,item_gid) VALUES (%s,%s)", (user_gid, item_gid)); favorite = True
            conn.commit()
        return {"favorite": favorite}

    def recent_record(self, item_gid: str, user_gid: str) -> dict:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO workmanship_know_recent (user_gid,item_gid,accessed_at) VALUES (%s,%s,NOW()) ON DUPLICATE KEY UPDATE accessed_at=NOW()", (user_gid, item_gid))
            conn.commit()
        return {"recorded": True}

    def personalization_read(self, kind: str, user_gid: str) -> list[dict]:
        table, time_col = ("workmanship_know_favorites", "created_at") if kind == "favorites" else ("workmanship_know_recent", "accessed_at")
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT item_gid,{time_col} FROM {table} WHERE user_gid=%s ORDER BY {time_col} DESC LIMIT 200", (user_gid,))
                return [dict(row) for row in cur.fetchall()]

