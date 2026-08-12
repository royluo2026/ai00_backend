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
