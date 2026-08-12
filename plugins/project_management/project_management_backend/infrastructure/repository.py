"""Domain-owned SQL repository boundary."""
from __future__ import annotations

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
