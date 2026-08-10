"""Stable, bounded Project Management references for cross-domain consumers."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_project_management_conn


PROJECT_REF_SCHEMA = {
    "type": "object",
    "required": ["object_ref", "title", "owner"],
    "properties": {
        "object_ref": {"type": "string", "pattern": r"^project:[A-Za-z0-9_.:-]+$"},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "match_reason": {"type": "string"},
        "owner": {"type": "string", "const": "project_management"},
    },
}

PROJECT_SEARCH_SCHEMA = {
    "type": "object",
    "required": ["items", "total", "query"],
    "properties": {
        "items": {"type": "array", "items": PROJECT_REF_SCHEMA, "maxItems": 50},
        "total": {"type": "integer", "minimum": 0},
        "query": {"type": "string"},
    },
}


class ProjectRepository:
    def search(self, query: str, limit: int, context: CapabilityContext) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        with get_project_management_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid,name,project_code,status FROM workmanship_proj_projects "
                    "WHERE is_deleted=FALSE AND (owner_gid=%s OR team_id=%s) "
                    "AND (name LIKE %s OR project_code LIKE %s) "
                    "ORDER BY updated_at DESC,gid ASC LIMIT %s",
                    (context.user_gid, context.team_gid, pattern, pattern, limit),
                )
                return [dict(row) for row in cursor.fetchall()]


repository = ProjectRepository()


def search_projects(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    query = str(payload.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    limit = payload.get("limit", 20)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    rows = repository.search(query, limit, context)
    items = [
        {
            "object_ref": f"project:{row['gid']}",
            "title": str(row.get("name") or row.get("project_code") or row["gid"]),
            "summary": str(row.get("status") or ""),
            "match_reason": "name_or_code",
            "owner": "project_management",
        }
        for row in rows
    ]
    return CapabilityOutput(data={"items": items, "total": len(items), "query": query})


def register_project_capabilities(registry: Any) -> None:
    registry.register(
        CapabilitySpec(
            id="base.project.search",
            owner="project_management",
            plugin_callable=True,
            description="Search visible Project Management refs by name or code.",
            use_when="A caller needs a stable project reference before invoking another domain.",
            do_not_use_when="A project reference is already known or project rows are requested.",
            subject_concepts=("project_management.project",),
            effects=("read:project_management.project_ref",),
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 200},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            output_schema=PROJECT_SEARCH_SCHEMA,
            tags=("project_management", "project", "read"),
        ),
        search_projects,
    )
