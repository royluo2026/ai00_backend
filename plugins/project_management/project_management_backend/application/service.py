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


_OPERATIONS = {
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
    ) -> dict[str, Any]:
        operation = str(payload.get("operation") or "")
        if operation not in _OPERATIONS.get(capability_id, frozenset()):
            raise CapabilityBusinessError(
                "operation_not_supported",
                f"{operation or 'empty operation'} is not supported by {capability_id}",
            )
        arguments = payload.get("arguments")
        if not isinstance(arguments, Mapping):
            raise CapabilityBusinessError("invalid_input", "arguments must be an object")
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


__all__ = ["ItemEntryRepository", "ProjectManagementApplication"]
