"""Retired legacy migration entrypoint.

Schema changes must be immutable files in ``backend/db/migrations`` and must be
executed by ``backend/scripts/run_migrations.py`` with the dedicated DDL account.
"""
from __future__ import annotations

import logging

_log = logging.getLogger("backend.db.migrate.retired")


def run_safe_migrations(_conn) -> None:
    raise RuntimeError(
        "run_safe_migrations is retired; use the versioned deployment migration runner"
    )


def _run_ddl_batch(conn, stmts: list, label: str) -> None:
    """Deprecated compatibility helper retained only for historical unit tests."""
    _log.warning("deprecated unversioned DDL batch invoked: %s", label)
    for stmt in stmts:
        try:
            with conn.cursor() as cur:
                cur.execute(stmt)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            _log.debug("retired migrate[%s] statement failed: %s", label, exc)
