"""Project Management application service and operation dispatch."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol
from uuid import uuid4

from backend.capability_v2.provider_contracts import CapabilityBusinessError


class ItemEntryRepository(Protocol):
    def list_item_entries(self, item_type: str, item_gid: str) -> list[dict[str, Any]]: ...
    def replace_item_entries(
        self, item_type: str, item_gid: str, entries: list[dict[str, Any]]
    ) -> None: ...
    def delete_item_entries(self, item_type: str, item_gid: str) -> None: ...
    def get_list_owner(self, list_gid: str) -> str | None: ...
    def get_item_list_owner(self, item_type: str, item_gid: str) -> str | None: ...
    def list_change_logs_by_list(
        self, list_gid: str, limit: int, offset: int
    ) -> list[dict[str, Any]]: ...
    def list_change_logs_by_item(
        self,
        item_type: str,
        item_gid: str,
        changed_by: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]: ...


_OPERATIONS = {
    "project.change_log.read": frozenset({"change_logs.search"}),
    "project.list.read": frozenset({"item_entries.get"}),
    "project.list.change.apply": frozenset(
        {"item_entries.replace", "item_entries.delete"}
    ),
}


def _required_text(arguments: Mapping[str, Any], name: str) -> str:
    value = str(arguments.get(name) or "").strip()
    if not value:
        raise CapabilityBusinessError("invalid_input", f"{name} is required")
    return value


def _bounded_int(
    arguments: Mapping[str, Any], name: str, *, default: int, minimum: int, maximum: int
) -> int:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CapabilityBusinessError("invalid_input", f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise CapabilityBusinessError(
            "invalid_input", f"{name} must be between {minimum} and {maximum}"
        )
    return value


def _entry(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "gid": row.get("gid", ""),
        "parent_id": row.get("parent_id"),
        "section": row.get("section", "detail"),
        "author": row.get("author", "human"),
        "author_name": row.get("author_name", ""),
        "author_gid": row.get("author_gid", ""),
        "content": row.get("content", ""),
        "resolved": bool(row.get("resolved", False)),
        "sort_order": float(row.get("sort_order", 0)),
        "read_by_human": bool(row.get("read_by_human", True)),
        "ai_status": row.get("ai_status", "unread"),
        "created_at": row.get("created_at", 0),
    }


class ProjectManagementApplication:
    def __init__(
        self,
        repository: ItemEntryRepository,
        *,
        next_id: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._next_id = next_id or (lambda: str(uuid4()))

    def invoke(
        self,
        capability_id: str,
        payload: dict[str, Any],
        _context: object,
    ) -> Any:
        operation = str(payload.get("operation") or "")
        if operation not in _OPERATIONS.get(capability_id, frozenset()):
            raise CapabilityBusinessError(
                "operation_not_supported",
                f"{operation or 'empty operation'} is not supported by {capability_id}",
            )
        arguments = payload.get("arguments")
        if not isinstance(arguments, Mapping):
            raise CapabilityBusinessError("invalid_input", "arguments must be an object")
        if operation == "change_logs.search":
            return self._search_change_logs(arguments, _context)
        item_type = _required_text(arguments, "item_type")
        item_gid = _required_text(arguments, "item_gid")
        if operation == "item_entries.get":
            rows = self._repository.list_item_entries(item_type, item_gid)
            return {"entries": [_entry(row) for row in rows]}
        if operation == "item_entries.delete":
            self._repository.delete_item_entries(item_type, item_gid)
            return {"success": True}

        entries = arguments.get("entries")
        if not isinstance(entries, list):
            raise CapabilityBusinessError("invalid_input", "entries must be an array")
        saved = [
            {**dict(entry), "gid": str(entry.get("gid") or self._next_id())}
            for entry in entries
            if isinstance(entry, Mapping)
        ]
        if len(saved) != len(entries):
            raise CapabilityBusinessError("invalid_input", "every entry must be an object")
        self._repository.replace_item_entries(item_type, item_gid, saved)
        return {"success": True, "count": len(saved), "entries": saved}

    def _search_change_logs(
        self, arguments: Mapping[str, Any], context: object
    ) -> list[dict[str, Any]]:
        list_gid = str(arguments.get("list_gid") or "").strip()
        item_gid = str(arguments.get("item_gid") or "").strip()
        if not list_gid and not item_gid:
            raise CapabilityBusinessError(
                "invalid_input", "item_gid or list_gid is required"
            )
        limit = _bounded_int(
            arguments, "limit", default=100, minimum=1, maximum=500
        )
        offset = _bounded_int(
            arguments, "offset", default=0, minimum=0, maximum=1_000_000
        )
        user_gid = str(getattr(context, "user_gid", "") or "")
        active_roles = frozenset(getattr(context, "active_roles", ()) or ())
        can_read_all = "super_admin" in active_roles
        if list_gid:
            owner_gid = self._repository.get_list_owner(list_gid)
            if not can_read_all and owner_gid != user_gid:
                raise CapabilityBusinessError(
                    "forbidden", "only the list owner can read complete change history"
                )
            return self._repository.list_change_logs_by_list(list_gid, limit, offset)

        item_type = _required_text(arguments, "item_type")
        owner_gid = self._repository.get_item_list_owner(item_type, item_gid)
        changed_by = None if can_read_all or owner_gid == user_gid else user_gid
        return self._repository.list_change_logs_by_item(
            item_type, item_gid, changed_by, limit, offset
        )


__all__ = ["ItemEntryRepository", "ProjectManagementApplication"]
