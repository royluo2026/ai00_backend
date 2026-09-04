"""Stable domain-facing entry point for table-prefix-aware connections."""

from backend.db.prefixed_cursor import wrap_connection

__all__ = ["wrap_connection"]
