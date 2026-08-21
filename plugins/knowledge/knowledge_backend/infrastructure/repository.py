"""Knowledge-owned compatibility persistence; consumers never receive SQL access."""
from __future__ import annotations

import json

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from ..data.connection import get_knowledge_conn
from ..ids import new_knowledge_id


class KnowledgeRepository:
    @staticmethod
    def _can_manage(permissions=(), active_roles=()) -> bool:
        return bool({"knowledge.manage", "knowledge.write"} & set(permissions)) or "super_admin" in set(active_roles)

    def _next_display_id(self) -> str:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_know_display_counters (seq_name,val) VALUES (%s,1) "
                    "ON DUPLICATE KEY UPDATE val=LAST_INSERT_ID(val+1)",
                    ("knowledge_display_seq",),
                )
                cur.execute(
                    "SELECT val FROM workmanship_know_display_counters WHERE seq_name=%s",
                    ("knowledge_display_seq",),
                )
                value = int(cur.fetchone()["val"])
            conn.commit()
        return f"K-C{value:08d}"

    @staticmethod
    def _normalize_legacy_scope(scope_type: str | None, requested_team: str | None, user_gid: str, team_gid: str | None) -> tuple[str, str | None]:
        scope = str(scope_type or "personal")
        if scope not in {"personal", "team", "public"}:
            raise CapabilityBusinessError("invalid_input", "Unsupported knowledge scope")
        if scope == "team":
            current_team = str(team_gid or "")
            if not current_team or (requested_team and str(requested_team) != current_team):
                raise CapabilityBusinessError("permission_denied", "Cannot access another team knowledge scope")
            return scope, current_team
        return scope, None

    @classmethod
    def _legacy_visible_sql(cls, alias: str = "f") -> str:
        return f"({alias}.scope_type='public' OR ({alias}.scope_type='personal' AND {alias}.creator_gid=%s) OR ({alias}.scope_type='team' AND {alias}.team_gid=%s AND {alias}.team_gid<>''))"

    def folder_list(self, data: dict, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> list[dict]:
        scope_type = data.get("scope_type")
        requested_team = data.get("team_gid")
        params: list = [user_gid, str(team_gid or "")]
        clauses = [self._legacy_visible_sql("f")]
        if scope_type:
            scope, normalized_team = self._normalize_legacy_scope(scope_type, requested_team, user_gid, team_gid)
            clauses.append("f.scope_type=%s"); params.append(scope)
            if scope == "team": clauses.append("f.team_gid=%s"); params.append(normalized_team or "")
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT f.* FROM workmanship_know_folders f WHERE " + " AND ".join(clauses) + " ORDER BY f.sort_order,f.created_at", params)
                return [dict(row) for row in cur.fetchall()]

    def _legacy_mutable(self, row: dict, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> None:
        scope = str(row.get("scope_type") or "personal")
        if scope == "personal" and str(row.get("creator_gid") or "") == str(user_gid): return
        if scope == "team" and str(row.get("team_gid") or "") == str(team_gid or "") and (str(row.get("creator_gid") or "") == str(user_gid) or self._can_manage(permissions, active_roles)): return
        if scope == "public" and self._can_manage(permissions, active_roles): return
        raise CapabilityBusinessError("permission_denied", "Knowledge folder is not writable by this user")

    def folder_create(self, data: dict, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> dict:
        scope, normalized_team = self._normalize_legacy_scope(data.get("scope_type"), data.get("team_gid"), user_gid, team_gid)
        if scope == "public" and not self._can_manage(permissions, active_roles): raise CapabilityBusinessError("permission_denied", "Public knowledge requires knowledge.manage")
        parent_gid = data.get("parent_gid")
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                if parent_gid:
                    cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (parent_gid,)); parent = cur.fetchone()
                    if not parent: raise CapabilityBusinessError("resource_not_found", "Parent folder was not found")
                    self._legacy_mutable(dict(parent), user_gid, team_gid, permissions=permissions, active_roles=active_roles)
                    if parent["scope_type"] != scope or str(parent.get("team_gid") or "") != str(normalized_team or ""): raise CapabilityBusinessError("invalid_input", "Parent folder scope mismatch")
                gid = str(new_knowledge_id("folder"))
                cur.execute("INSERT INTO workmanship_know_folders (gid,parent_gid,scope_type,team_gid,name,sort_order,creator_gid,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())", (gid, parent_gid, scope, normalized_team, data.get("name") or "新建文件夹", int(data.get("sort_order") or 0), user_gid))
                conn.commit(); cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (gid,)); return dict(cur.fetchone())

    def folder_update(self, gid: str, updates: dict, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> bool:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (gid,)); existing = cur.fetchone()
        if not existing: raise CapabilityBusinessError("resource_not_found", "Knowledge folder was not found")
        existing = dict(existing); self._legacy_mutable(existing, user_gid, team_gid, permissions=permissions, active_roles=active_roles)
        if "parent_gid" in updates and updates["parent_gid"] is not None:
            parent_gid = str(updates["parent_gid"])
            if parent_gid == gid: raise CapabilityBusinessError("invalid_input", "Folder cannot be its own parent")
            with get_knowledge_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (parent_gid,)); parent = cur.fetchone()
            if not parent: raise CapabilityBusinessError("resource_not_found", "Parent folder was not found")
            self._legacy_mutable(dict(parent), user_gid, team_gid, permissions=permissions, active_roles=active_roles)
            if parent["scope_type"] != existing["scope_type"] or str(parent.get("team_gid") or "") != str(existing.get("team_gid") or ""): raise CapabilityBusinessError("invalid_input", "Parent folder scope mismatch")
        allowed = {key: updates[key] for key in ("name", "sort_order", "parent_gid") if key in updates}
        if not allowed: return True
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE workmanship_know_folders SET {','.join(f'{key}=%s' for key in allowed)},updated_at=NOW() WHERE gid=%s", (*allowed.values(), gid)); changed = cur.rowcount == 1
            conn.commit()
        return changed

    def folder_delete(self, gid: str, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> dict:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (gid,)); root = cur.fetchone()
                if not root: raise CapabilityBusinessError("resource_not_found", "Knowledge folder was not found")
                self._legacy_mutable(dict(root), user_gid, team_gid, permissions=permissions, active_roles=active_roles)
                folder_gids = [gid]; frontier = [gid]
                while frontier:
                    placeholders = ",".join(["%s"] * len(frontier)); cur.execute(f"SELECT * FROM workmanship_know_folders WHERE parent_gid IN ({placeholders})", frontier)
                    children = [dict(row) for row in cur.fetchall()]
                    for child in children: self._legacy_mutable(child, user_gid, team_gid, permissions=permissions, active_roles=active_roles)
                    frontier = [str(child["gid"]) for child in children if str(child["gid"]) not in folder_gids]; folder_gids.extend(frontier)
                placeholders = ",".join(["%s"] * len(folder_gids)); cur.execute(f"SELECT * FROM workmanship_know_items WHERE folder_gid IN ({placeholders})", folder_gids)
                for item in cur.fetchall(): self._legacy_mutable(dict(item), user_gid, team_gid, permissions=permissions, active_roles=active_roles)
                cur.execute(f"DELETE FROM workmanship_know_items WHERE folder_gid IN ({placeholders})", folder_gids); cur.execute(f"DELETE FROM workmanship_know_folders WHERE gid IN ({placeholders})", folder_gids); conn.commit()
                return {"deleted_folders": len(folder_gids)}

    def item_list(self, data: dict, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> list[dict]:
        params: list = [user_gid, str(team_gid or "")]; clauses = [self._legacy_visible_sql("ki")]
        if data.get("folder_gid"): clauses.append("ki.folder_gid=%s"); params.append(data["folder_gid"])
        if data.get("scope_type"):
            scope, normalized_team = self._normalize_legacy_scope(data["scope_type"], data.get("team_gid"), user_gid, team_gid)
            clauses.append("ki.scope_type=%s"); params.append(scope)
            if scope == "team": clauses.append("ki.team_gid=%s"); params.append(normalized_team or "")
        if data.get("q"): clauses.append("ki.title LIKE %s"); params.append(f"%{data['q']}%")
        if not data.get("show_hidden") or not self._can_manage(permissions, active_roles): clauses.append("(ki.is_hidden=FALSE OR ki.is_hidden IS NULL)")
        limit = max(1, min(int(data.get("limit") or 200), 200)); params.append(limit)
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ki.gid,ki.folder_gid,ki.scope_type,ki.team_gid,ki.item_type,ki.title,ki.status,ki.file_path,ki.url,ki.site_ref,ki.tags,ki.is_system,ki.is_pinned,ki.is_hidden,ki.creator_gid,ki.created_at,ki.updated_at FROM workmanship_know_items ki WHERE " + " AND ".join(clauses) + " ORDER BY ki.is_pinned DESC,ki.is_system DESC,ki.updated_at DESC LIMIT %s", params)
                return [dict(row) for row in cur.fetchall()]

    def item_get(self, gid: str, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> dict:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_know_items ki WHERE ki.gid=%s AND " + self._legacy_visible_sql("ki"), (gid, user_gid, str(team_gid or ""))); row = cur.fetchone()
        if not row: raise CapabilityBusinessError("resource_not_found", "Knowledge item was not found")
        return dict(row)

    def item_history(self, gid: str, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> list[dict]:
        self.item_get(gid, user_gid, team_gid, permissions=permissions, active_roles=active_roles)
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT gid,id,author_name,content,created_at FROM workmanship_know_item_history WHERE item_gid=%s ORDER BY created_at DESC", (gid,)); rows = [dict(row) for row in cur.fetchall()]
        return rows

    def item_create(self, data: dict, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> dict:
        scope, normalized_team = self._normalize_legacy_scope(data.get("scope_type"), data.get("team_gid"), user_gid, team_gid)
        if scope == "public" and not self._can_manage(permissions, active_roles): raise CapabilityBusinessError("permission_denied", "Public knowledge requires knowledge.manage")
        folder_gid = data.get("folder_gid")
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                if folder_gid:
                    cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (folder_gid,)); folder = cur.fetchone()
                    if not folder: raise CapabilityBusinessError("resource_not_found", "Knowledge folder was not found")
                    self._legacy_mutable(dict(folder), user_gid, team_gid, permissions=permissions, active_roles=active_roles)
                    if folder["scope_type"] != scope or str(folder.get("team_gid") or "") != str(normalized_team or ""): raise CapabilityBusinessError("invalid_input", "Folder scope mismatch")
                gid = str(new_knowledge_id("item")); cur.execute("INSERT INTO workmanship_know_items (gid,folder_gid,scope_type,team_gid,item_type,title,status,content_body,content_md,file_path,url,site_ref,tags,creator_gid,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())", (gid, folder_gid, scope, normalized_team, data.get("item_type") or "richtext", data.get("title") or "未命名文档", data.get("status") or "draft", json.dumps(data.get("content_body"), ensure_ascii=False) if data.get("content_body") is not None else None, data.get("content_md") or "", data.get("file_path") or "", data.get("url") or "", json.dumps(data.get("site_ref"), ensure_ascii=False) if data.get("site_ref") is not None else None, json.dumps(data.get("tags") or [], ensure_ascii=False), user_gid)); conn.commit(); cur.execute("SELECT * FROM workmanship_know_items WHERE gid=%s", (gid,)); return dict(cur.fetchone())

    def item_update(self, gid: str, updates: dict, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> bool:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_know_items WHERE gid=%s", (gid,)); existing = cur.fetchone()
        if not existing: raise CapabilityBusinessError("resource_not_found", "Knowledge item was not found")
        existing = dict(existing); self._legacy_mutable(existing, user_gid, team_gid, permissions=permissions, active_roles=active_roles)
        if "scope_type" in updates or "team_gid" in updates:
            raise CapabilityBusinessError("invalid_input", "Knowledge item scope is immutable; copy into the target scope instead")
        if "folder_gid" in updates and updates["folder_gid"] is not None:
            with get_knowledge_conn() as conn:
                with conn.cursor() as cur: cur.execute("SELECT * FROM workmanship_know_folders WHERE gid=%s", (updates["folder_gid"],)); folder = cur.fetchone()
            if not folder: raise CapabilityBusinessError("resource_not_found", "Knowledge folder was not found")
            self._legacy_mutable(dict(folder), user_gid, team_gid, permissions=permissions, active_roles=active_roles)
            if folder["scope_type"] != existing["scope_type"] or str(folder.get("team_gid") or "") != str(existing.get("team_gid") or ""): raise CapabilityBusinessError("invalid_input", "Folder scope mismatch")
        allowed_names = {"folder_gid", "title", "status", "content_md", "file_path", "url", "content_body", "site_ref", "tags", "is_pinned", "is_hidden"}; allowed = {key: value for key, value in updates.items() if key in allowed_names}
        if not allowed: return True
        for key in ("content_body", "site_ref", "tags"):
            if key in allowed: allowed[key] = json.dumps(allowed[key], ensure_ascii=False)
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur: cur.execute(f"UPDATE workmanship_know_items SET {','.join(f'{key}=%s' for key in allowed)},updated_at=NOW() WHERE gid=%s", (*allowed.values(), gid)); changed = cur.rowcount == 1
            conn.commit()
        return changed

    def item_delete(self, gid: str, user_gid: str, team_gid: str | None, *, permissions=(), active_roles=()) -> bool:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_know_items WHERE gid=%s", (gid,)); existing = cur.fetchone()
                if not existing: raise CapabilityBusinessError("resource_not_found", "Knowledge item was not found")
                self._legacy_mutable(dict(existing), user_gid, team_gid, permissions=permissions, active_roles=active_roles)
                if existing.get("is_system") and "super_admin" not in set(active_roles): raise CapabilityBusinessError("permission_denied", "System knowledge item requires super_admin")
                cur.execute("DELETE FROM workmanship_know_favorites WHERE item_gid=%s", (gid,)); cur.execute("DELETE FROM workmanship_know_recent WHERE item_gid=%s", (gid,)); cur.execute("DELETE FROM workmanship_know_items WHERE gid=%s", (gid,)); changed = cur.rowcount == 1; conn.commit()
        return changed

    def entry_create(
        self,
        data: dict,
        user_gid: str,
        team_gid: str | None,
        *,
        permissions=(),
        active_roles=(),
    ) -> dict:
        share_scope = str(data.get("share_scope") or "team")
        if share_scope not in {"local", "team", "global"}:
            raise CapabilityBusinessError("invalid_input", "Unsupported knowledge share scope")
        if share_scope == "global" and not self._can_manage(permissions, active_roles):
            raise CapabilityBusinessError("permission_denied", "Global knowledge requires knowledge.manage")
        gid = new_knowledge_id("entry")
        display_id = self._next_display_id()
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_know_entries ("
                    "gid,display_id,title,entry_type,status,share_scope,list_gid,source_gid,source_label,"
                    "maintainer_gid,contributors,attachments,tags,content_ref,content_md,related_part_nos,"
                    "related_operation_gids,context_class_gid,creator_gid,team_id"
                    ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        gid,
                        display_id,
                        data["title"],
                        data.get("entry_type", "guide"),
                        data.get("status", "draft"),
                        share_scope,
                        data.get("list_gid"),
                        data.get("source_gid"),
                        data.get("source_label", ""),
                        data.get("maintainer_gid", ""),
                        json.dumps(data.get("contributors", []), ensure_ascii=False),
                        json.dumps(data.get("attachments", []), ensure_ascii=False),
                        json.dumps(data.get("tags", []), ensure_ascii=False),
                        json.dumps(data.get("content_ref", {}), ensure_ascii=False),
                        data.get("content_md", ""),
                        json.dumps(data.get("related_part_nos", []), ensure_ascii=False),
                        json.dumps(data.get("related_operation_gids", []), ensure_ascii=False),
                        data.get("context_class_gid"),
                        user_gid,
                        team_gid,
                    ),
                )
            conn.commit()
        return {"gid": gid}

    def entry_update(
        self,
        gid: str,
        updates: dict,
        user_gid: str,
        *,
        permissions=(),
        active_roles=(),
    ) -> bool:
        allowed_names = {
            "title", "entry_type", "status", "share_scope", "list_gid", "source_gid",
            "source_label", "maintainer_gid", "contributors", "attachments", "tags",
            "content_ref", "related_part_nos", "related_operation_gids", "context_class_gid",
        }
        allowed = {key: value for key, value in updates.items() if key in allowed_names}
        if not allowed:
            raise CapabilityBusinessError("invalid_input", "No writable knowledge fields were supplied")
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT creator_gid,share_scope FROM workmanship_know_entries WHERE gid=%s", (gid,))
                row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", "Knowledge entry was not found")
        if str(row.get("creator_gid") or "") != str(user_gid) and not self._can_manage(permissions, active_roles):
            raise CapabilityBusinessError("permission_denied", "Knowledge entry is not writable by this user")
        if "share_scope" in allowed:
            share_scope = str(allowed["share_scope"] or "")
            if share_scope not in {"local", "team", "global"}:
                raise CapabilityBusinessError("invalid_input", "Unsupported knowledge share scope")
            if share_scope == "global" and not self._can_manage(permissions, active_roles):
                raise CapabilityBusinessError("permission_denied", "Global knowledge requires knowledge.manage")
        json_fields = {"contributors", "attachments", "tags", "content_ref", "related_part_nos", "related_operation_gids"}
        for key in json_fields:
            if key in allowed:
                allowed[key] = json.dumps(allowed[key], ensure_ascii=False)
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE workmanship_know_entries SET {','.join(f'{key}=%s' for key in allowed)},updated_at=NOW() WHERE gid=%s AND creator_gid=%s", (*allowed.values(), gid, user_gid)); changed = cur.rowcount == 1
            conn.commit()
        if not changed and self._can_manage(permissions, active_roles):
            with get_knowledge_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"UPDATE workmanship_know_entries SET {','.join(f'{key}=%s' for key in allowed)},updated_at=NOW() WHERE gid=%s", (*allowed.values(), gid)); changed = cur.rowcount == 1
                conn.commit()
        if not changed:
            raise CapabilityBusinessError("resource_not_found", "Knowledge entry was not found")
        return changed

    def entry_delete(self, gid: str, user_gid: str, *, permissions=(), active_roles=()) -> bool:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT creator_gid FROM workmanship_know_entries WHERE gid=%s", (gid,))
                row = cur.fetchone()
                if not row:
                    raise CapabilityBusinessError("resource_not_found", "Knowledge entry was not found")
                if str(row.get("creator_gid") or "") != str(user_gid) and not self._can_manage(permissions, active_roles):
                    raise CapabilityBusinessError("permission_denied", "Knowledge entry is not writable by this user")
                cur.execute("DELETE FROM workmanship_know_entries WHERE gid=%s", (gid,)); changed = cur.rowcount == 1
            conn.commit()
        if not changed:
            raise CapabilityBusinessError("resource_not_found", "Knowledge entry was not found")
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

    @staticmethod
    def _legacy_item_visible_sql() -> str:
        return "(ki.scope_type='public' OR (ki.scope_type='personal' AND ki.creator_gid=%s) OR (ki.scope_type='team' AND ki.team_gid=%s AND ki.team_gid<>''))"

    def favorite_toggle(self, item_gid: str, user_gid: str, team_gid: str | None = None) -> dict:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM workmanship_know_items ki WHERE ki.gid=%s AND " + self._legacy_item_visible_sql(),
                    (item_gid, user_gid, team_gid or ""),
                )
                if not cur.fetchone():
                    raise CapabilityBusinessError("resource_not_found", "Knowledge item was not found")
                cur.execute("SELECT 1 FROM workmanship_know_favorites WHERE user_gid=%s AND item_gid=%s", (user_gid, item_gid))
                if cur.fetchone(): cur.execute("DELETE FROM workmanship_know_favorites WHERE user_gid=%s AND item_gid=%s", (user_gid, item_gid)); favorite = False
                else: cur.execute("INSERT INTO workmanship_know_favorites (user_gid,item_gid) VALUES (%s,%s)", (user_gid, item_gid)); favorite = True
            conn.commit()
        return {"favorite": favorite}

    def recent_record(self, item_gid: str, user_gid: str, team_gid: str | None = None) -> dict:
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM workmanship_know_items ki WHERE ki.gid=%s AND " + self._legacy_item_visible_sql(),
                    (item_gid, user_gid, team_gid or ""),
                )
                if not cur.fetchone():
                    raise CapabilityBusinessError("resource_not_found", "Knowledge item was not found")
                cur.execute("INSERT INTO workmanship_know_recent (user_gid,item_gid,accessed_at) VALUES (%s,%s,NOW()) ON DUPLICATE KEY UPDATE accessed_at=NOW()", (user_gid, item_gid))
            conn.commit()
        return {"recorded": True}

    def personalization_read(self, kind: str, user_gid: str, team_gid: str | None = None, limit: int | None = None) -> list[dict]:
        table, time_col = ("workmanship_know_favorites", "created_at") if kind == "favorites" else ("workmanship_know_recent", "accessed_at")
        bounded_limit = max(1, min(int(limit or 200), 200))
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT ki.*, p.{time_col} AS personalization_at FROM {table} p "
                    "JOIN workmanship_know_items ki ON ki.gid=p.item_gid "
                    f"WHERE p.user_gid=%s AND {self._legacy_item_visible_sql()} ORDER BY p.{time_col} DESC LIMIT %s",
                    (user_gid, user_gid, team_gid or "", bounded_limit),
                )
                return [dict(row) for row in cur.fetchall()]
