"""Governed read Capabilities for BOP version identity and discovery."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from backend.capabilities.models_next import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilitySpec,
    EvidenceRef,
)

from ..data.connection import get_craft_conn


_VERSION_COLUMNS = """
gid, project_gid, factory_gid, vehicle_model_gid,
version_tag, version_no, bop_name, version_family_gid,
parent_version_gid, change_note, maturity, takt_time, status,
frozen_at, published_at, archived_at, version_type, pbom_version_gid,
owner_gid, data_stage, visibility, lifecycle_phase, lifecycle_state,
meta, snapshot_data, created_at, updated_at
""".strip()

_LIST_FIELDS = frozenset(
    {
        "project_gid",
        "status",
        "query",
        "include_archived",
        "cursor",
        "page_size",
    }
)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _transport_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _optional_text(payload: Mapping[str, Any], name: str) -> str | None:
    value = payload.get(name)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value.strip() or None


def _required_text(payload: Mapping[str, Any], name: str) -> str:
    value = _optional_text(payload, name)
    if value is None:
        raise ValueError(f"{name} is required")
    return value


def _encode_cursor(created_at: Any, gid: str) -> str:
    raw = json.dumps(
        {"created_at": _transport_value(created_at), "gid": gid},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> tuple[str, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        created_at = decoded["created_at"]
        gid = decoded["gid"]
        if not isinstance(created_at, str) or not created_at:
            raise ValueError
        if not isinstance(gid, str) or not gid:
            raise ValueError
        return created_at, gid
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cursor is invalid") from exc


@dataclass(frozen=True)
class BopVersionQuery:
    project_gid: str | None = None
    status: str | None = None
    query: str | None = None
    include_archived: bool = False
    cursor: tuple[str, str] | None = None
    page_size: int = 50

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        maximum_page_size: int = 100,
    ) -> "BopVersionQuery":
        unknown = sorted(set(payload) - _LIST_FIELDS)
        if unknown:
            raise ValueError(f"unsupported fields: {', '.join(unknown)}")
        page_size = payload.get("page_size", 50)
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            raise ValueError("page_size must be an integer")
        if page_size < 1 or page_size > maximum_page_size:
            raise ValueError(f"page_size must be between 1 and {maximum_page_size}")
        include_archived = payload.get("include_archived", False)
        if not isinstance(include_archived, bool):
            raise ValueError("include_archived must be a boolean")
        cursor_value = _optional_text(payload, "cursor")
        return cls(
            project_gid=_optional_text(payload, "project_gid"),
            status=_optional_text(payload, "status"),
            query=_optional_text(payload, "query"),
            include_archived=include_archived,
            cursor=_decode_cursor(cursor_value) if cursor_value else None,
            page_size=page_size,
        )


class BopVersionRepository:
    def get_version(self, version_gid: str) -> dict[str, Any] | None:
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT {_VERSION_COLUMNS} "
                    "FROM workmanship_bop_bop_versions "
                    "WHERE gid = %s AND is_deleted = 0",
                    (version_gid,),
                )
                row = cursor.fetchone()
        return dict(row) if row else None

    def search_versions(
        self,
        query: BopVersionQuery,
    ) -> tuple[list[dict[str, Any]], str | None]:
        where = ["is_deleted = 0"]
        params: list[Any] = []
        if not query.include_archived:
            where.extend(["archived_at IS NULL", "is_archived = 0"])
        if query.project_gid:
            where.append("project_gid = %s")
            params.append(query.project_gid)
        if query.status:
            where.append("status = %s")
            params.append(query.status)
        if query.query:
            where.append("(bop_name LIKE %s OR version_tag LIKE %s)")
            pattern = f"%{query.query}%"
            params.extend([pattern, pattern])
        if query.cursor:
            created_at, gid = query.cursor
            where.append("(created_at > %s OR (created_at = %s AND gid > %s))")
            params.extend([created_at, created_at, gid])

        params.append(query.page_size + 1)
        sql = (
            f"SELECT {_VERSION_COLUMNS} "
            "FROM workmanship_bop_bop_versions "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY created_at ASC, gid ASC LIMIT %s"
        )
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                rows = [dict(row) for row in cursor.fetchall()]

        has_more = len(rows) > query.page_size
        page = rows[: query.page_size]
        next_cursor = None
        if has_more and page:
            next_cursor = _encode_cursor(page[-1].get("created_at"), str(page[-1]["gid"]))
        return page, next_cursor


repository = BopVersionRepository()


def _revision(row: Mapping[str, Any]) -> Any:
    meta = _json_object(row.get("meta"))
    return meta.get("revision") or row.get("version_no") or row.get("version_tag")


def _content_hash(row: Mapping[str, Any]) -> str | None:
    for source in (_json_object(row.get("snapshot_data")), _json_object(row.get("meta"))):
        for name in ("content_hash", "sha256", "digest"):
            value = source.get(name)
            if isinstance(value, str) and value:
                return value
    return None


def _lifecycle(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": row.get("status"),
        "phase": row.get("lifecycle_phase"),
        "state": _json_object(row.get("lifecycle_state")),
        "frozen_at": _transport_value(row.get("frozen_at")),
        "published_at": _transport_value(row.get("published_at")),
        "archived_at": _transport_value(row.get("archived_at")),
    }


def _summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "version_gid": str(row["gid"]),
        "version_tag": row.get("version_tag"),
        "bop_name": row.get("bop_name"),
        "family_gid": row.get("version_family_gid"),
        "project_gid": row.get("project_gid"),
        "status": row.get("status"),
        "lifecycle_phase": row.get("lifecycle_phase"),
        "revision": _revision(row),
        "updated_at": _transport_value(row.get("updated_at")),
        "archived": bool(row.get("archived_at")),
    }


def _detail(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_summary(row),
        "factory_gid": row.get("factory_gid"),
        "vehicle_model_gid": row.get("vehicle_model_gid"),
        "parent_version_gid": row.get("parent_version_gid"),
        "pbom_version_gid": row.get("pbom_version_gid"),
        "owner_gid": row.get("owner_gid"),
        "version_type": row.get("version_type"),
        "maturity": row.get("maturity"),
        "data_stage": row.get("data_stage"),
        "visibility": row.get("visibility"),
        "takt_time": row.get("takt_time"),
        "change_note": row.get("change_note"),
        "lifecycle": _lifecycle(row),
        "content_hash": _content_hash(row),
        "created_at": _transport_value(row.get("created_at")),
    }


def _version_evidence(row: Mapping[str, Any]) -> EvidenceRef:
    gid = str(row["gid"])
    lifecycle = _lifecycle(row)
    return EvidenceRef(
        kind="craft.bop.version",
        reference=f"craft://bop/version/{gid}",
        digest=_content_hash(row),
        summary=f"BOP version {row.get('version_tag') or gid}",
        metadata={
            "version_gid": gid,
            "revision": _revision(row),
            "status": lifecycle["status"],
            "phase": lifecycle["phase"],
        },
    )


def get_bop_version(
    payload: dict[str, Any],
    _context: CapabilityContext,
) -> CapabilityOutput:
    unknown = sorted(set(payload) - {"version_gid"})
    if unknown:
        raise ValueError(f"unsupported fields: {', '.join(unknown)}")
    version_gid = _required_text(payload, "version_gid")
    row = repository.get_version(version_gid)
    if row is None:
        raise CapabilityBusinessError(
            "bop_version_not_found",
            "BOP version not found",
            details={"version_gid": version_gid},
        )
    return CapabilityOutput(data=_detail(row), evidence=(_version_evidence(row),))


def list_bop_versions(
    payload: dict[str, Any],
    _context: CapabilityContext,
) -> CapabilityOutput:
    query = BopVersionQuery.from_payload(payload, maximum_page_size=100)
    rows, next_cursor = repository.search_versions(query)
    return CapabilityOutput(
        data={"items": [_summary(row) for row in rows], "next_cursor": next_cursor}
    )


_GET_OUTPUT_SCHEMA = {
    "type": "object",
    "required": [
        "version_gid",
        "revision",
        "family_gid",
        "project_gid",
        "lifecycle",
        "content_hash",
    ],
}

_LIST_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["items", "next_cursor"],
    "properties": {"items": {"type": "array"}},
}


def register_bop_version_capabilities(registry: Any) -> None:
    registry.register(
        CapabilitySpec(
            id="craft.bop.version.get",
            owner="craft",
            description="Read one BOP version identity, lifecycle and revision evidence.",
            use_when="The caller already has an exact BOP version GID.",
            do_not_use_when="The caller needs to discover or compare versions.",
            subject_concepts=("craft.bop.version",),
            effects=("read:craft.bop.version",),
            plugin_callable=True,
            input_schema={
                "type": "object",
                "required": ["version_gid"],
                "properties": {"version_gid": {"type": "string"}},
                "additionalProperties": False,
            },
            output_schema=_GET_OUTPUT_SCHEMA,
            tags=("craft", "bop", "version", "read"),
        ),
        get_bop_version,
    )
    registry.register(
        CapabilitySpec(
            id="craft.bop.version.list",
            owner="craft",
            description="Discover BOP version summaries with bounded cursor pagination.",
            use_when="The caller needs to find BOP versions by project, state or text.",
            do_not_use_when="The caller already has one exact version GID.",
            subject_concepts=("craft.bop.version", "base.project"),
            effects=("read:craft.bop.version",),
            plugin_callable=True,
            input_schema={
                "type": "object",
                "properties": {
                    "project_gid": {"type": "string"},
                    "status": {"type": "string"},
                    "query": {"type": "string"},
                    "include_archived": {"type": "boolean"},
                    "cursor": {"type": "string"},
                    "page_size": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            output_schema=_LIST_OUTPUT_SCHEMA,
            tags=("craft", "bop", "version", "read", "search"),
        ),
        list_bop_versions,
    )
