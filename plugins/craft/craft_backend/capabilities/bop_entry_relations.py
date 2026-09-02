"""Atomic bounded reads for BOP entry relations and linked entity cards."""
from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Mapping
from typing import Any

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityContext, CapabilityExecutionBudget,
    CapabilityOutput, CapabilitySpec,
)

from ..data.connection import get_craft_conn
from ..services.bop_navigation import (
    BopNavigationRepository, _ENTITY_CARD_EXPRESSION, _entity_card, _transport,
)


_RELATION_JOINS = """
JOIN workmanship_bop_bop_versions v ON v.gid=l.version_gid
LEFT JOIN workmanship_bop_bop_line ln ON ln.gid=l.entity_gid AND l.link_type='bop_line'
LEFT JOIN workmanship_bop_bop_station st ON st.gid=l.entity_gid AND l.link_type='bop_station'
LEFT JOIN workmanship_bop_bop_process pr ON pr.gid=l.entity_gid AND l.link_type='bop_process'
LEFT JOIN workmanship_bop_bop_steps op ON op.gid=l.entity_gid AND l.link_type='bop_steps'
LEFT JOIN workmanship_bop_bop_operator opr ON opr.gid=l.entity_gid AND l.link_type='bop_operator'
LEFT JOIN workmanship_bop_pbom pb ON pb.gid=l.entity_gid AND l.link_type='pbom_part'
LEFT JOIN workmanship_craft_resource_requirements rr ON rr.gid=l.entity_gid
    AND l.link_type IN ('resource_socket','resource_tool','resource_fixture','resource_equipment')
"""


def _error(code: str, message: str, **details: Any) -> CapabilityBusinessError:
    return CapabilityBusinessError(code, message, details=details)


def encode_relation_cursor(source_entry_gid: str, link_gid: str) -> str:
    raw = json.dumps(
        {"link_gid": str(link_gid), "source_entry_gid": str(source_entry_gid), "v": 1},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_relation_cursor(value: str | None) -> tuple[str, str]:
    if not isinstance(value, str) or not value:
        raise _error("invalid_cursor", "Relation cursor is invalid")
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        document = json.loads(raw.decode("utf-8"))
        if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
            raise ValueError("non-canonical cursor")
        if not isinstance(document, dict) or set(document) != {"link_gid", "source_entry_gid", "v"}:
            raise ValueError("invalid cursor fields")
        source, link = document["source_entry_gid"], document["link_gid"]
        if document["v"] != 1 or not isinstance(source, str) or not source or not isinstance(link, str) or not link:
            raise ValueError("invalid cursor values")
        return source, link
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("invalid_cursor", "Relation cursor is invalid") from exc


class BopEntryRelationRepository:
    def __init__(self, connection_factory: Callable[[], Any] = get_craft_conn) -> None:
        self._connection_factory = connection_factory

    def list_relations(
        self, version_gid: str, revision: int, entry_gid: str, *, recursive: bool,
        cursor: str | None, page_size: int,
    ) -> dict[str, Any]:
        size = BopNavigationRepository._page_size(page_size, 200)
        cursor_entry, cursor_link = decode_relation_cursor(cursor) if cursor else ("", "")
        cte = (
            "WITH RECURSIVE scoped(gid,title) AS ("
            " SELECT gid,title FROM workmanship_bop_bop_entries"
            " WHERE version_gid=%s AND gid=%s AND is_deleted=0"
            " UNION ALL SELECT e.gid,e.title FROM workmanship_bop_bop_entries e"
            " JOIN scoped s ON e.parent_gid=s.gid"
            " WHERE e.version_gid=%s AND e.is_deleted=0) "
            if recursive else
            "WITH scoped(gid,title) AS ("
            " SELECT gid,title FROM workmanship_bop_bop_entries"
            " WHERE version_gid=%s AND gid=%s AND is_deleted=0) "
        )
        cte_params: tuple[Any, ...] = (
            (version_gid, entry_gid, version_gid) if recursive else (version_gid, entry_gid)
        )
        select = f"""
SELECT l.gid AS link_gid,s.gid AS source_entry_gid,s.title AS source_entry_title,
       l.link_type,l.entity_gid,l.is_primary,l.is_inherited,l.created_at,
       {_ENTITY_CARD_EXPRESSION} AS entity_data
FROM scoped s
JOIN workmanship_bop_bop_entry_links l ON l.entry_gid=s.gid
{_RELATION_JOINS}
WHERE l.version_gid=%s AND l.is_deleted=0 AND l.deleted_at IS NULL
  AND (s.gid > %s OR (s.gid=%s AND l.gid>%s))
ORDER BY s.gid,l.gid LIMIT %s
"""
        with self._connection_factory() as connection:
            with connection.cursor() as db:
                BopNavigationRepository._assert_revision(db, version_gid, revision)
                db.execute(
                    "SELECT gid FROM workmanship_bop_bop_entries"
                    " WHERE version_gid=%s AND gid=%s AND is_deleted=0",
                    (version_gid, entry_gid),
                )
                if not db.fetchone():
                    raise _error("entry_not_found", "BOP entry was not found", entry_gid=entry_gid)
                db.execute(
                    cte + select,
                    (*cte_params, version_gid, cursor_entry, cursor_entry, cursor_link, size + 1),
                )
                raw = [dict(row) for row in db.fetchall()]
                BopNavigationRepository._assert_revision(db, version_gid, revision)
        page = raw[:size]
        items = [{
            "link_gid": str(row["link_gid"]),
            "source_entry_gid": str(row["source_entry_gid"]),
            "source_entry_title": row.get("source_entry_title"),
            "link_type": str(row.get("link_type") or ""),
            "target_ref": {"type": str(row.get("link_type") or ""), "gid": row.get("entity_gid")},
            "is_primary": bool(row.get("is_primary")),
            "is_inherited": bool(row.get("is_inherited")),
            "target_summary": _entity_card(row.get("entity_data")),
            "created_at": _transport(row.get("created_at")) if row.get("created_at") is not None else None,
        } for row in page]
        next_cursor = (
            encode_relation_cursor(str(page[-1]["source_entry_gid"]), str(page[-1]["link_gid"]))
            if len(raw) > size and page else None
        )
        return {
            "version_gid": version_gid, "revision": revision, "entry_gid": entry_gid,
            "recursive": recursive, "items": items, "next_cursor": next_cursor,
        }

    def get_linked_entity_detail(
        self, version_gid: str, revision: int, link_gid: str,
    ) -> dict[str, Any]:
        select = f"""
SELECT l.gid AS link_gid,l.entry_gid,l.version_gid,l.link_type,l.entity_gid,l.is_primary,
       {_ENTITY_CARD_EXPRESSION} AS entity_data
FROM workmanship_bop_bop_entry_links l
{_RELATION_JOINS}
WHERE l.version_gid=%s AND l.gid=%s AND l.is_deleted=0 AND l.deleted_at IS NULL
LIMIT 1
"""
        with self._connection_factory() as connection:
            with connection.cursor() as db:
                BopNavigationRepository._assert_revision(db, version_gid, revision)
                db.execute(select, (version_gid, link_gid))
                row = db.fetchone()
                if not row:
                    raise _error("link_not_found", "BOP entry link was not found", link_gid=link_gid)
                BopNavigationRepository._assert_revision(db, version_gid, revision)
        link = dict(row)
        card = _entity_card(link.get("entity_data"))
        return {
            "version_gid": version_gid, "revision": revision,
            "link": {
                "link_gid": link.get("link_gid"), "entry_gid": str(link["entry_gid"]),
                "version_gid": str(link["version_gid"]), "link_type": str(link["link_type"]),
                "entity_gid": link.get("entity_gid"), "is_primary": bool(link.get("is_primary")),
            },
            "readable": card is not None, "entity_data": card,
        }


repository = BopEntryRelationRepository()


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unknown input fields: {', '.join(sorted(unknown))}")


def _text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _revision(payload: Mapping[str, Any]) -> int:
    value = payload.get("revision")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("revision must be a positive integer")
    return value


def list_entry_relations(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    _reject_unknown(payload, {"version_gid", "revision", "entry_gid", "recursive", "cursor", "page_size"})
    recursive = payload.get("recursive", False)
    if not isinstance(recursive, bool):
        raise ValueError("recursive must be a boolean")
    page_size = payload.get("page_size", 100)
    data = repository.list_relations(
        _text(payload, "version_gid"), _revision(payload), _text(payload, "entry_gid"),
        recursive=recursive, cursor=payload.get("cursor"), page_size=page_size,
    )
    return CapabilityOutput(data=data)


def get_linked_entity_detail(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    _reject_unknown(payload, {"version_gid", "revision", "link_gid"})
    data = repository.get_linked_entity_detail(
        _text(payload, "version_gid"), _revision(payload), _text(payload, "link_gid"),
    )
    return CapabilityOutput(data=data)


def register_bop_entry_relation_capabilities(registry: Any) -> None:
    common = {
        "owner": "craft", "plugin_callable": True, "permissions": (),
        "subject_concepts": ("craft.bop.version", "craft.bop.entry", "craft.bop.entry_link"),
        "tags": ("craft", "bop", "relation", "bounded", "read"),
    }
    registry.register(CapabilitySpec(
        id="craft.bop.entry.relation.list", version=1,
        description="Read one bounded page of direct or descendant BOP entry relations.",
        use_when="A consumer needs governed relations for one entry or its bounded subtree.",
        do_not_use_when="A consumer needs to attach or detach a relation.",
        effects=("read:craft.bop.entry_relation",),
        execution_budget=CapabilityExecutionBudget(
            memory_class="medium", max_input_bytes=64 * 1024,
            max_output_bytes=1024 * 1024, collection_policy="paged", max_page_size=200,
            max_parallel_per_consumer=2, max_parallel_per_tenant=8,
        ),
        **common,
    ), list_entry_relations)
    registry.register(CapabilitySpec(
        id="craft.bop.linked_entity.detail.get", version=1,
        description="Read one allowlisted linked-entity card through its BOP link identity.",
        use_when="A consumer has a BOP link GID and needs its governed entity card.",
        do_not_use_when="A consumer has only an arbitrary table name or needs to mutate the entity.",
        effects=("read:craft.bop.linked_entity",),
        execution_budget=CapabilityExecutionBudget(
            memory_class="small", max_input_bytes=64 * 1024,
            max_output_bytes=512 * 1024, collection_policy="bounded",
            max_parallel_per_consumer=4, max_parallel_per_tenant=16,
        ),
        **common,
    ), get_linked_entity_detail)


__all__ = [
    "BopEntryRelationRepository", "decode_relation_cursor", "encode_relation_cursor",
    "get_linked_entity_detail", "list_entry_relations", "repository",
    "register_bop_entry_relation_capabilities",
]
