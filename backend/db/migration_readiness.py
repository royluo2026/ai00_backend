from __future__ import annotations

from pathlib import Path

from .versioned_migrations import LEDGER_TABLE, discover_migrations


class DatabaseNotMigratedError(RuntimeError):
    pass


def assert_migrations_applied(conn, directory: Path | None = None) -> None:
    """Read-only application startup check; this function never creates or alters tables."""
    directory = directory or Path(__file__).with_name("migrations")
    expected = {migration.migration_id: migration.checksum for migration in discover_migrations(directory)}
    if not expected:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT migration_id, checksum, status FROM {LEDGER_TABLE}")
            rows = cur.fetchall()
    except Exception as exc:
        raise DatabaseNotMigratedError(
            "migration ledger is unavailable; run backend/scripts/run_migrations.py with AI00_DDL_DB_URL"
        ) from exc
    applied = {
        (row["migration_id"] if isinstance(row, dict) else row[0]): (
            row["checksum"] if isinstance(row, dict) else row[1],
            row["status"] if isinstance(row, dict) else row[2],
        )
        for row in rows
    }
    missing = sorted(migration_id for migration_id in expected if migration_id not in applied)
    failed = sorted(migration_id for migration_id, (_, status) in applied.items() if migration_id in expected and status != "applied")
    changed = sorted(migration_id for migration_id, checksum in expected.items() if migration_id in applied and applied[migration_id][0] != checksum)
    if missing or failed or changed:
        raise DatabaseNotMigratedError(
            f"database migration readiness failed: missing={missing}, failed={failed}, checksum_changed={changed}"
        )
