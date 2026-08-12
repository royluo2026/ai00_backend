"""Domain-owned SQL repository boundary."""
from __future__ import annotations

import json
from typing import Any

from ..data.connection import get_project_management_conn


class ProjectManagementRepository:
    """Executes SQL only with the Project Management runtime credential."""

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with get_project_management_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with get_project_management_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return dict(row) if row else None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    affected = cursor.execute(sql, params)
                connection.commit()
                return int(affected)
            except Exception:
                connection.rollback()
                raise

    def list_item_entries(self, item_type: str, item_gid: str) -> list[dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM workmanship_work_item_entries "
            "WHERE item_type = %s AND item_gid = %s ORDER BY sort_order",
            (item_type, item_gid),
        )

    def replace_item_entries(
        self, item_type: str, item_gid: str, entries: list[dict[str, Any]]
    ) -> None:
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM workmanship_work_item_entries "
                        "WHERE item_type = %s AND item_gid = %s",
                        (item_type, item_gid),
                    )
                    for entry in entries:
                        cursor.execute(
                            "INSERT INTO workmanship_work_item_entries "
                            "(gid,id,item_type,item_gid,parent_id,section,author,"
                            "author_name,author_gid,content,resolved,sort_order,"
                            "read_by_human,ai_status,created_at,updated_at) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())",
                            (
                                entry["gid"], entry.get("id"), item_type, item_gid,
                                entry.get("parent_id"), entry.get("section", "detail"),
                                entry.get("author", "human"), entry.get("author_name", ""),
                                entry.get("author_gid", ""), entry.get("content", ""),
                                bool(entry.get("resolved", False)),
                                float(entry.get("sort_order", 0)),
                                bool(entry.get("read_by_human", True)),
                                entry.get("ai_status", "unread"),
                            ),
                        )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def delete_item_entries(self, item_type: str, item_gid: str) -> None:
        self.execute(
            "DELETE FROM workmanship_work_item_entries "
            "WHERE item_type = %s AND item_gid = %s",
            (item_type, item_gid),
        )

    def get_list_owner(self, list_gid: str) -> str | None:
        row = self.fetch_one(
            "SELECT owner_gid FROM workmanship_work_lists WHERE gid = %s",
            (list_gid,),
        )
        return str(row["owner_gid"]) if row else None

    def get_item_list_owner(self, item_type: str, item_gid: str) -> str | None:
        row = self.fetch_one(
            "SELECT l.owner_gid FROM workmanship_work_item_change_logs cl "
            "JOIN workmanship_work_lists l ON l.gid = cl.list_gid "
            "WHERE cl.item_type = %s AND cl.item_gid = %s LIMIT 1",
            (item_type, item_gid),
        )
        return str(row["owner_gid"]) if row else None

    def list_change_logs_by_list(
        self, list_gid: str, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        return self.fetch_all(
            "SELECT gid,item_type,item_gid,list_gid,changed_by,changed_at,"
            "field_name,old_value,new_value "
            "FROM workmanship_work_item_change_logs WHERE list_gid = %s "
            "ORDER BY changed_at DESC LIMIT %s OFFSET %s",
            (list_gid, limit, offset),
        )

    def list_change_logs_by_item(
        self,
        item_type: str,
        item_gid: str,
        changed_by: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT gid,item_type,item_gid,list_gid,changed_by,changed_at,"
            "field_name,old_value,new_value "
            "FROM workmanship_work_item_change_logs "
            "WHERE item_type = %s AND item_gid = %s"
        )
        params: tuple[Any, ...] = (item_type, item_gid)
        if changed_by is not None:
            sql += " AND changed_by = %s"
            params += (changed_by,)
        sql += " ORDER BY changed_at DESC LIMIT %s OFFSET %s"
        return self.fetch_all(sql, params + (limit, offset))

    def list_collaboration_sessions(
        self, section_gid: str | None
    ) -> list[dict[str, Any]]:
        if section_gid:
            return self.fetch_all(
                "SELECT gid,section_gid,owner_gid,status,participants,created_at,ended_at "
                "FROM workmanship_proj_collab_sessions WHERE section_gid=%s "
                "ORDER BY created_at DESC",
                (section_gid,),
            )
        return self.fetch_all(
            "SELECT gid,section_gid,owner_gid,status,participants,created_at,ended_at "
            "FROM workmanship_proj_collab_sessions WHERE status='active' "
            "ORDER BY created_at DESC"
        )

    def get_collaboration_session(self, gid: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT gid,section_gid,owner_gid,status,participants,meta,created_at,ended_at "
            "FROM workmanship_proj_collab_sessions WHERE gid=%s",
            (gid,),
        )

    def create_collaboration_session(
        self, gid: str, section_gid: str, owner_gid: str
    ) -> None:
        self.execute(
            "INSERT INTO workmanship_proj_collab_sessions "
            "(gid,section_gid,owner_gid,participants,meta) VALUES (%s,%s,%s,%s,%s)",
            (gid, section_gid, owner_gid, json.dumps([owner_gid]), json.dumps({})),
        )

    def join_collaboration_session(self, gid: str, participant_gid: str) -> None:
        participant = json.dumps([participant_gid])
        self.execute(
            "UPDATE workmanship_proj_collab_sessions "
            "SET participants=JSON_MERGE_PRESERVE(participants,%s) "
            "WHERE gid=%s AND status='active' AND NOT JSON_CONTAINS(participants,%s)",
            (participant, gid, participant),
        )

    def end_collaboration_session(self, gid: str, owner_gid: str) -> bool:
        return bool(
            self.execute(
                "UPDATE workmanship_proj_collab_sessions "
                "SET status='ended',ended_at=NOW() WHERE gid=%s AND owner_gid=%s",
                (gid, owner_gid),
            )
        )

    def create_share_link(self, token: str, values: dict[str, Any]) -> dict[str, Any]:
        self.execute(
            "INSERT INTO workmanship_work_share_links "
            "(token,target_type,target_gid,item_type,display_name,created_by,expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (token, values["target_type"], values["target_gid"], values.get("item_type"),
             values.get("display_name", ""), values["created_by"], values.get("expires_at")),
        )
        return self.resolve_share_link(token) or {"token": token, **values}

    def resolve_share_link(self, token: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM workmanship_work_share_links WHERE token=%s "
            "AND (expires_at IS NULL OR expires_at > NOW())", (token,)
        )

    def get_list_access(self, list_gid: str, user_gid: str, team_gid: str | None) -> str:
        row = self.fetch_one(
            "SELECT owner_gid,creator_gid,read_scope,team_id FROM workmanship_work_lists "
            "WHERE gid=%s AND deleted_at IS NULL", (list_gid,)
        )
        if not row:
            return "none"
        if user_gid in {str(row.get("owner_gid") or ""), str(row.get("creator_gid") or "")}:
            return "write"
        share = self.fetch_one(
            "SELECT permission FROM workmanship_work_list_shares WHERE list_gid=%s AND shared_to=%s",
            (list_gid, user_gid),
        )
        if share:
            return str(share["permission"])
        scope = row.get("read_scope") or "team"
        if scope == "global" or (scope == "team" and team_gid and team_gid == row.get("team_id")):
            return "read"
        return "none"

    def delete_share_link(self, token: str, user_gid: str, is_super: bool) -> str:
        row = self.fetch_one(
            "SELECT created_by FROM workmanship_work_share_links WHERE token=%s", (token,)
        )
        if not row:
            return "not_found"
        if str(row["created_by"]) != user_gid and not is_super:
            return "forbidden"
        self.execute("DELETE FROM workmanship_work_share_links WHERE token=%s", (token,))
        return "deleted"

    def create_permission_request(self, gid: str, values: dict[str, Any]) -> dict[str, Any]:
        self.execute(
            "INSERT INTO workmanship_work_permission_requests "
            "(gid,requester_gid,target_type,target_gid,want_permission,message,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,'pending')",
            (gid, values["requester_gid"], values["target_type"], values["target_gid"], values["want_permission"], values["message"]),
        )
        return self.fetch_one("SELECT * FROM workmanship_work_permission_requests WHERE gid=%s", (gid,)) or {"gid": gid, **values, "status": "pending"}

    def list_permission_requests(self, target_gid: str | None, status_filter: str | None) -> list[dict[str, Any]]:
        clauses, params = ["1=1"], []
        if target_gid:
            clauses.append("target_gid=%s"); params.append(target_gid)
        if status_filter:
            clauses.append("status=%s"); params.append(status_filter)
        return self.fetch_all("SELECT * FROM workmanship_work_permission_requests WHERE " + " AND ".join(clauses) + " ORDER BY created_at DESC LIMIT 200", tuple(params))

    def decide_permission_request(self, gid: str, responder_gid: str, decision: str) -> tuple[str, dict[str, Any] | None]:
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM workmanship_work_permission_requests WHERE gid=%s FOR UPDATE", (gid,))
                    raw = cursor.fetchone()
                    if not raw:
                        connection.rollback(); return "not_found", None
                    row = dict(raw)
                    if row["status"] != "pending":
                        connection.rollback(); return "already_decided", row
                    if decision == "approved" and row["target_type"] == "list":
                        cursor.execute(
                            "INSERT INTO workmanship_work_list_shares (gid,list_gid,shared_to,permission,shared_by) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE permission=VALUES(permission)",
                            (str(__import__('uuid').uuid4()), row["target_gid"], row["requester_gid"], row["want_permission"], responder_gid),
                        )
                    cursor.execute("UPDATE workmanship_work_permission_requests SET status=%s,responded_by=%s,responded_at=NOW() WHERE gid=%s", (decision, responder_gid, gid))
                connection.commit(); row["status"] = decision; return "updated", row
            except Exception:
                connection.rollback(); raise

    def is_list_owner(self, list_gid: str, user_gid: str) -> bool:
        row = self.fetch_one("SELECT owner_gid,creator_gid FROM workmanship_work_lists WHERE gid=%s AND deleted_at IS NULL", (list_gid,))
        return bool(row and user_gid in {str(row.get("owner_gid") or ""), str(row.get("creator_gid") or "")})

    def list_list_shares(self, list_gid: str) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT * FROM workmanship_work_list_shares WHERE list_gid=%s ORDER BY created_at", (list_gid,))

    def upsert_list_share(self, gid: str, values: dict[str, Any]) -> dict[str, Any]:
        self.execute("INSERT INTO workmanship_work_list_shares (gid,list_gid,shared_to,permission,shared_by) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE permission=VALUES(permission),shared_by=VALUES(shared_by)", (gid, values["list_gid"], values["shared_to"], values["permission"], values["shared_by"]))
        return self.fetch_one("SELECT * FROM workmanship_work_list_shares WHERE gid=%s", (gid,)) or {"gid": gid, **values}

    def delete_list_share(self, list_gid: str, gid: str) -> None:
        self.execute("DELETE FROM workmanship_work_list_shares WHERE gid=%s AND list_gid=%s", (gid, list_gid))

    def upsert_item_share(self, gid: str, values: dict[str, Any]) -> dict[str, Any]:
        self.execute("INSERT INTO workmanship_work_item_shares (gid,item_type,item_gid,shared_to,permission,shared_by) VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE permission=VALUES(permission),shared_by=VALUES(shared_by)", (gid, values["item_type"], values["item_gid"], values["shared_to"], values["permission"], values["shared_by"]))
        return self.fetch_one("SELECT * FROM workmanship_work_item_shares WHERE gid=%s", (gid,)) or {"gid": gid, **values}

    def delete_item_share(self, gid: str, user_gid: str) -> str:
        row = self.fetch_one("SELECT shared_by FROM workmanship_work_item_shares WHERE gid=%s", (gid,))
        if not row: return "not_found"
        if str(row["shared_by"]) != user_gid: return "forbidden"
        self.execute("DELETE FROM workmanship_work_item_shares WHERE gid=%s", (gid,)); return "deleted"

    def search_lists(self, filters: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]:
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []
        owner_team_gid = filters.get("owner_team_gid")
        if owner_team_gid:
            clauses.extend(["owner_type='team'", "owner_gid=%s"]); params.append(owner_team_gid)
        else:
            visible = ["(owner_type='user' AND owner_gid=%s)", "visibility='public'"]
            params.append(scope["user_gid"])
            for key, clause in (
                ("team_gids", "(owner_type='team' AND owner_gid IN ({p}))"),
                ("team_gids", "(visibility='team' AND shared_team_gid IN ({p}))"),
                ("team_member_gids", "(visibility='team' AND shared_team_gid IS NULL AND creator_gid IN ({p}))"),
                ("project_gids", "(visibility='project' AND project_gid IN ({p}))"),
            ):
                values = list(scope.get(key) or [])
                if values:
                    visible.append(clause.format(p=",".join(["%s"] * len(values)))); params.extend(values)
            clauses.append("(" + " OR ".join(visible) + ")")
        if filters.get("item_type"):
            clauses.append("item_type=%s"); params.append(filters["item_type"])
        if filters.get("q"):
            clauses.append("name LIKE %s"); params.append(f"%{filters['q']}%")
        return self.fetch_all(
            "SELECT * FROM workmanship_work_lists WHERE " + " AND ".join(clauses)
            + " ORDER BY owner_type,sort_order,created_at", tuple(params)
        )

    def create_list(self, gid: str, values: dict[str, Any]) -> None:
        self.execute(
            "INSERT INTO workmanship_work_lists "
            "(gid,name,color,storage_scope,owner_type,owner_gid,creator_gid,visibility,read_scope,write_scope,item_type,sort_order) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (gid, values["name"], values["color"], values["storage_scope"], values["owner_type"],
             values["owner_gid"], values["creator_gid"], values["visibility"], values["read_scope"],
             values["write_scope"], values["item_type"], values["sort_order"]),
        )

    def get_list(self, gid: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM workmanship_work_lists WHERE gid=%s AND deleted_at IS NULL", (gid,)
        )

    def update_list(self, gid: str, updates: dict[str, Any]) -> bool:
        assignments = ", ".join(f"{key}=%s" for key in updates)
        return bool(self.execute(
            f"UPDATE workmanship_work_lists SET {assignments} WHERE gid=%s AND deleted_at IS NULL",
            tuple(updates.values()) + (gid,),
        ))

    def archive_list(self, gid: str) -> bool:
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE workmanship_proj_tasks SET list_gid=NULL WHERE list_gid=%s", (gid,))
                    cursor.execute("UPDATE workmanship_proj_issues SET list_gid=NULL WHERE list_gid=%s", (gid,))
                    affected = cursor.execute("UPDATE workmanship_work_lists SET deleted_at=NOW() WHERE gid=%s", (gid,))
                connection.commit(); return bool(affected)
            except Exception:
                connection.rollback(); raise

    def retarget_list_items(self, gid: str, new_list_gid: str, item_type: str) -> bool:
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    affected = 0
                    if item_type in {"task", ""}:
                        affected += cursor.execute("UPDATE workmanship_proj_tasks SET list_gid=%s WHERE list_gid=%s", (new_list_gid, gid))
                    if item_type in {"issue", ""}:
                        affected += cursor.execute("UPDATE workmanship_proj_issues SET list_gid=%s WHERE list_gid=%s", (new_list_gid, gid))
                connection.commit(); return bool(affected)
            except Exception:
                connection.rollback(); raise

    def search_projects(self, filters: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if not bool(scope.get("is_admin")):
            visible = ["p.share_scope='global'", "p.owner_gid=%s"]; params.append(scope["user_gid"])
            team_gids = list(scope.get("team_gids") or [])
            if team_gids:
                placeholders = ",".join(["%s"] * len(team_gids)); visible.append(f"(p.share_scope='team' AND p.team_id IN ({placeholders}))"); params.extend(team_gids)
            project_gids = list(scope.get("project_gids") or [])
            if project_gids:
                placeholders = ",".join(["%s"] * len(project_gids)); visible.append(f"(p.share_scope IN ('team','project') AND p.gid IN ({placeholders}))"); params.extend(project_gids)
            clauses.append("(" + " OR ".join(visible) + ")")
        if not filters["include_deleted"]: clauses.append("p.is_deleted=FALSE")
        if not filters["include_archived"]: clauses.append("p.is_archived=FALSE")
        return self.fetch_all("SELECT p.* FROM workmanship_proj_projects p WHERE " + (" AND ".join(clauses) or "1=1") + " ORDER BY p.updated_at DESC", tuple(params))

    def create_project(self, gid: str, values: dict[str, Any]) -> None:
        self.execute(
            "INSERT INTO workmanship_proj_projects (gid,name,project_code,model_year,suffix,description,status,vehicle_model_gid,team_id,owner_gid,jph,factory_gid,share_scope,project_type,meta) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active','{}')",
            (gid, values["name"], values["project_code"], values["model_year"], values["suffix"], values["description"], values["status"], values["vehicle_model_gid"], values["team_id"], values["owner_gid"], values["jph"], values["factory_gid"], values["share_scope"]),
        )

    def get_project(self, gid: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM workmanship_proj_projects WHERE gid=%s", (gid,))

    def update_project(self, gid: str, updates: dict[str, Any]) -> bool:
        assignments = [f"{key}=%s" for key in updates]
        params: list[Any] = list(updates.values())
        if "is_archived" in updates:
            assignments.append("archived_at=" + ("NOW()" if updates["is_archived"] else "NULL"))
        assignments.append("updated_at=NOW()"); params.append(gid)
        return bool(self.execute(f"UPDATE workmanship_proj_projects SET {', '.join(assignments)} WHERE gid=%s AND is_deleted=FALSE", tuple(params)))

    def delete_project(self, gid: str) -> bool:
        return bool(self.execute("UPDATE workmanship_proj_projects SET is_deleted=TRUE,deleted_at=NOW(),updated_at=NOW() WHERE gid=%s AND is_deleted=FALSE", (gid,)))

    def list_vehicle_models(self) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT gid,name,brand,platform,vehicle_type,created_at FROM workmanship_proj_vehicle_models ORDER BY created_at DESC")

    def create_vehicle_model(self, gid: str, values: dict[str, Any]) -> None:
        self.execute("INSERT INTO workmanship_proj_vehicle_models (gid,name,brand,platform,vehicle_type,team_id,meta) VALUES (%s,%s,%s,%s,%s,%s,'{}')", (gid, values["name"], values["brand"], values["platform"], values["vehicle_type"], values["team_id"]))

    def update_vehicle_model(self, gid: str, values: dict[str, Any]) -> bool:
        return bool(self.execute("UPDATE workmanship_proj_vehicle_models SET name=%s,brand=%s,platform=%s,vehicle_type=%s WHERE gid=%s", (values["name"], values["brand"], values["platform"], values["vehicle_type"], gid)))

    def delete_vehicle_model(self, gid: str) -> bool:
        return bool(self.execute("DELETE FROM workmanship_proj_vehicle_models WHERE gid=%s", (gid,)))

    def list_task_templates(self) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT gid,name,description,scope,version,is_active,created_at,updated_at FROM workmanship_work_task_templates WHERE is_active=TRUE ORDER BY created_at DESC")

    def create_task_template(self, gid: str, values: dict[str, Any]) -> None:
        self.execute("INSERT INTO workmanship_work_task_templates (gid,name,description,scope,owner_gid) VALUES (%s,%s,%s,%s,%s)", (gid, values["name"], values["description"], values["scope"], values["owner_gid"]))

    def get_task_template(self, gid: str) -> dict[str, Any] | None:
        row = self.fetch_one("SELECT gid,name,description,scope,version,is_active,created_at,updated_at FROM workmanship_work_task_templates WHERE gid=%s", (gid,))
        if row is not None:
            row["items"] = self.fetch_all("SELECT gid,template_gid,title_pattern,description,priority,assignee_role,due_offset_days,share_scope,sort_order FROM workmanship_work_task_template_items WHERE template_gid=%s ORDER BY sort_order", (gid,))
        return row

    def update_task_template(self, gid: str, updates: dict[str, Any]) -> bool:
        assignments = ",".join(f"{key}=%s" for key in updates)
        return bool(self.execute(f"UPDATE workmanship_work_task_templates SET {assignments},updated_at=NOW(),version=version+1 WHERE gid=%s", tuple(updates.values()) + (gid,)))

    def delete_task_template(self, gid: str) -> bool:
        return bool(self.execute("DELETE FROM workmanship_work_task_templates WHERE gid=%s", (gid,)))

    def create_task_template_item(self, gid: str, values: dict[str, Any]) -> None:
        self.execute("INSERT INTO workmanship_work_task_template_items (gid,template_gid,title_pattern,description,priority,assignee_role,due_offset_days,share_scope,sort_order) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (gid, values["template_gid"], values["title_pattern"], values["description"], values["priority"], values["assignee_role"], values["due_offset_days"], values["share_scope"], values["sort_order"]))

    def update_task_template_item(self, gid: str, updates: dict[str, Any]) -> bool:
        assignments = ",".join(f"{key}=%s" for key in updates)
        return bool(self.execute(f"UPDATE workmanship_work_task_template_items SET {assignments} WHERE gid=%s", tuple(updates.values()) + (gid,)))

    def delete_task_template_item(self, gid: str) -> bool:
        return bool(self.execute("DELETE FROM workmanship_work_task_template_items WHERE gid=%s", (gid,)))

    def create_tasks_from_template(self, tasks: list[dict[str, Any]]) -> None:
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    for task in tasks:
                        cursor.execute("INSERT INTO workmanship_proj_tasks (gid,title,description,owner_user_gid,project_gid,priority,share_scope,due_date,template_item_gid,template_source_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (task["gid"], task["title"], task["description"], task["owner_user_gid"], task["project_gid"], task["priority"], task["share_scope"], task["due_date"], task["template_item_gid"], task["template_source_version"]))
                connection.commit()
            except Exception:
                connection.rollback(); raise

    def search_approval_orders(self, filters: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]:
        clauses = ["(applicant_gid=%s OR reviewer_gid=%s)"]; params: list[Any] = [scope["user_gid"], scope["user_gid"]]
        if bool(scope.get("is_admin")): clauses = ["1=1"]; params = []
        if filters.get("status"): clauses.append("status=%s"); params.append(filters["status"])
        if filters.get("project_gid"): clauses.append("project_gid=%s"); params.append(filters["project_gid"])
        return self.fetch_all("SELECT gid,project_gid,order_type,title,applicant_gid,reviewer_gid,status,source_ref,share_scope,created_at,updated_at FROM workmanship_proj_approval_orders WHERE " + " AND ".join(clauses) + " ORDER BY updated_at DESC", tuple(params))

    def create_approval_order(self, gid: str, values: dict[str, Any]) -> None:
        self.execute("INSERT INTO workmanship_proj_approval_orders (gid,title,order_type,project_gid,applicant_gid,reviewer_gid,source_ref,content) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (gid, values["title"], values["order_type"], values["project_gid"], values["applicant_gid"], values["reviewer_gid"], values["source_ref"], json.dumps(values["content"], ensure_ascii=False)))

    def get_approval_order(self, gid: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT gid,project_gid,order_type,title,applicant_gid,reviewer_gid,status,source_ref,content,opinions,meta,created_at,updated_at FROM workmanship_proj_approval_orders WHERE gid=%s", (gid,))

    def transition_approval_order(self, gid: str, action: str, actor_gid: str, comment: str) -> dict[str, Any] | None:
        target = {"start": "in_review", "approve": "approved", "reject": "rejected", "withdraw": "withdrawn"}[action]
        expected = {"start": ("pending",), "approve": ("in_review",), "reject": ("in_review",), "withdraw": ("pending", "in_review")}[action]
        with get_project_management_conn() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM workmanship_proj_approval_orders WHERE gid=%s FOR UPDATE", (gid,)); raw = cursor.fetchone()
                    if not raw: connection.rollback(); return None
                    row = dict(raw)
                    if row["status"] not in expected or (action in {"start", "withdraw"} and str(row["applicant_gid"]) != actor_gid): connection.rollback(); return None
                    opinion = json.dumps([{"actor_gid": actor_gid, "action": action, "comment": comment}], ensure_ascii=False)
                    cursor.execute("UPDATE workmanship_proj_approval_orders SET status=%s,opinions=JSON_MERGE_PRESERVE(COALESCE(opinions,JSON_ARRAY()),%s),updated_at=NOW() WHERE gid=%s", (target, opinion, gid))
                connection.commit(); row["status"] = target; return row
            except Exception:
                connection.rollback(); raise

    def apply_scope_upgrade(self, item_type: str, item_gid: str, target_scope: str) -> bool:
        table = {"project": "workmanship_proj_projects", "approval": "workmanship_proj_approval_orders"}.get(item_type)
        return bool(table and self.execute(f"UPDATE {table} SET share_scope=%s WHERE gid=%s", (target_scope, item_gid)))

    def list_workbenches(self, user_gid: str, team_gid: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[Any, Any]]:
        personal = self.fetch_all("SELECT * FROM workmanship_app_workbench_configs WHERE owner_type='user' AND owner_gid=%s ORDER BY sort_order,created_at", (user_gid,))
        teams = self.fetch_all("SELECT * FROM workmanship_app_workbench_configs WHERE owner_type='team' AND owner_gid=%s ORDER BY sort_order,created_at", (team_gid,)) if team_gid else []
        overrides = {}
        if teams:
            gids = [row["gid"] for row in teams]; placeholders = ",".join(["%s"] * len(gids))
            for row in self.fetch_all(f"SELECT workbench_gid,user_gid,widgets,updated_at FROM workmanship_app_workbench_member_overrides WHERE user_gid=%s AND workbench_gid IN ({placeholders})", tuple([user_gid] + gids)):
                overrides[(row["workbench_gid"], row["user_gid"])] = row
        return personal, teams, overrides

    def count_workbenches(self, owner_type: str, owner_gid: str) -> int:
        row = self.fetch_one("SELECT COUNT(*) AS count FROM workmanship_app_workbench_configs WHERE owner_type=%s AND owner_gid=%s", (owner_type, owner_gid))
        return int((row or {}).get("count", 0))

    def create_workbench(self, gid: str, values: dict[str, Any]) -> None:
        self.execute("INSERT INTO workmanship_app_workbench_configs (gid,owner_type,owner_gid,name,sort_order,widgets) VALUES (%s,%s,%s,%s,%s,%s)", (gid, values["owner_type"], values["owner_gid"], values["name"], values["sort_order"], json.dumps(values["widgets"])))

    def get_workbench(self, gid: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM workmanship_app_workbench_configs WHERE gid=%s", (gid,))

    def update_workbench(self, gid: str, updates: dict[str, Any]) -> bool:
        normalized = {key: json.dumps(value) if key == "widgets" else value for key, value in updates.items()}
        assignments = ",".join(f"{key}=%s" for key in normalized)
        return bool(self.execute(f"UPDATE workmanship_app_workbench_configs SET {assignments},updated_at=NOW() WHERE gid=%s", tuple(normalized.values()) + (gid,)))

    def delete_workbench(self, gid: str) -> bool:
        return bool(self.execute("DELETE FROM workmanship_app_workbench_configs WHERE gid=%s", (gid,)))

    def get_workbench_override(self, gid: str, user_gid: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT widgets,updated_at FROM workmanship_app_workbench_member_overrides WHERE workbench_gid=%s AND user_gid=%s", (gid, user_gid))

    def upsert_workbench_override(self, gid: str, user_gid: str, widgets: list[Any]) -> None:
        self.execute("INSERT INTO workmanship_app_workbench_member_overrides (gid,workbench_gid,user_gid,widgets) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE widgets=VALUES(widgets),updated_at=NOW()", (str(__import__('uuid').uuid4()), gid, user_gid, json.dumps(widgets)))

    def delete_workbench_override(self, gid: str, user_gid: str) -> None:
        self.execute("DELETE FROM workmanship_app_workbench_member_overrides WHERE workbench_gid=%s AND user_gid=%s", (gid, user_gid))
