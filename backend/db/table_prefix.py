"""
backend/db/table_prefix.py
──────────────────────────
Runtime SQL table-prefix rewriting.

When TABLE_PREFIX is set (e.g. ``TABLE_PREFIX=test_``), every SQL statement
executed through the pooled connection has ``workmanship_`` table references
rewritten to ``<prefix>workmanship_`` (e.g. ``test_workmanship_``).

This lets the test branch point at a separate set of tables in the same
OceanBase instance without touching any call-site SQL.

Safety:
  - The regex ``(?<![A-Za-z0-9_])workmanship_`` only matches ``workmanship_``
    as a standalone identifier prefix, never inside ``test_workmanship_``
    (because ``_`` is a word char and the look-behind rejects it).
  - No column names start with ``workmanship_`` in this schema.
  - No SQL string-literal values contain ``workmanship_`` (verified by audit).
"""
from __future__ import annotations

import re
import logging

_log = logging.getLogger("backend.db.table_prefix")

_TABLE_RE = re.compile(r"(?<![A-Za-z0-9_])workmanship_")
_PREFIX: str = ""


def configure_table_prefix(prefix: str) -> None:
    """Set the runtime table prefix.  Empty string = no rewriting."""
    global _PREFIX
    _PREFIX = (prefix or "").strip()
    if _PREFIX:
        _log.info("🔗 TABLE_PREFIX active: workmanship_ → %sworkmanship_", _PREFIX)


def rewrite_sql(sql: str) -> str:
    """Rewrite ``workmanship_`` → ``<prefix>workmanship_`` if prefix is set."""
    if not _PREFIX:
        return sql
    return _TABLE_RE.sub(_PREFIX + "workmanship_", sql)


def table_prefix_active() -> bool:
    return bool(_PREFIX)