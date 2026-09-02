from __future__ import annotations

import subprocess
from pathlib import Path

from backend.db.versioned_migrations import apply_migrations, discover_migrations


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "backend/db/migrations"
HISTORICAL_0004 = "242f329f"


def _git_bytes(revision: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def test_applied_0004_checksum_remains_the_historical_object_checksum():
    """A database ledger created at 242f329f must accept the checked-in 0004."""
    path = "backend/db/migrations/202608280004_base_plugin_lifecycle_idempotency_scope.sql"
    current = (ROOT / path).read_bytes()

    assert current == _git_bytes(HISTORICAL_0004, path)
    migration = next(item for item in discover_migrations(MIGRATIONS) if item.migration_id == "202608280004")
    assert migration.checksum == __import__("hashlib").sha256(current.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def test_upgrade_chain_contains_one_forward_only_historical_tenant_repair():
    migrations = discover_migrations(MIGRATIONS)

    assert [item.migration_id for item in migrations][-6:] == [
        "202608280005",
        "202608280006",
        "202608310001",
        "202609010001",
        "202609010002",
        "202609010003",
    ]
    repair = next(item for item in migrations if item.migration_id == "202608280006")
    assert repair.name == "historical_tenant_repair"
    assert "202608280006" in repair.sql


def test_upgrade_chain_adds_forward_only_craft_rule_identity_compatibility():
    migration = next(
        item for item in discover_migrations(MIGRATIONS)
        if item.migration_id == "202609010001"
    )

    assert migration.migration_id == "202609010001"
    assert migration.name == "rule_identity_compatibility"
    assert "ADD COLUMN IF NOT EXISTS creator_gid" in migration.sql


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.one = None
        self.all = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.connection.statements.append((normalized, params))
        if "GET_LOCK" in normalized:
            self.one = (1,)
        elif normalized.startswith("SELECT migration_id"):
            self.all = list(self.connection.ledger.values())
        elif "information_schema.COLUMNS" in normalized:
            self.one = (0,) if "COUNT(*)" in normalized else ("YES",)
        elif "information_schema.STATISTICS" in normalized:
            self.one = (0,) if "COUNT(*)" in normalized else None
            self.all = []
        elif normalized.startswith("INSERT INTO workmanship_base_schema_migrations"):
            self.connection.ledger[params[0]] = {
                "migration_id": params[0],
                "checksum": params[3],
                "status": "applied",
            }

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.all


class _Connection:
    def __init__(self, ledger=()):
        self.ledger = {row["migration_id"]: row for row in ledger}
        self.statements = []

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_pre_0004_and_original_0004_ledgers_apply_only_the_forward_migrations_once():
    migrations = discover_migrations(MIGRATIONS)
    old_0004 = next(item for item in migrations if item.migration_id == "202608280004")
    prior_ledger = tuple(
        {"migration_id": item.migration_id, "checksum": item.checksum, "status": "applied"}
        for item in migrations
        if item.migration_id < "202608280004"
    )

    for ledger, expected in (
        (prior_ledger, ["202608280004", "202608280005", "202608280006", "202608310001", "202609010001", "202609010002", "202609010003"]),
        (prior_ledger + ({"migration_id": "202608280004", "checksum": old_0004.checksum, "status": "applied"},), ["202608280005", "202608280006", "202608310001", "202609010001", "202609010002", "202609010003"]),
    ):
        connection = _Connection(ledger)
        assert apply_migrations(connection, directory=MIGRATIONS) == expected
        assert apply_migrations(connection, directory=MIGRATIONS) == []
        assert any("information_schema.COLUMNS" in sql for sql, _ in connection.statements)
