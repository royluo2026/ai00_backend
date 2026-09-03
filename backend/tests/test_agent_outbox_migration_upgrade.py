from __future__ import annotations

import hashlib
import re
from pathlib import Path

from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.domain_migrations import (
    apply_domain_migrations, discover_domain_migrations,
)


ROOT = Path(__file__).resolve().parents[2]
OLD_0005_BLOB_SHA1 = "4dcb5ebeff87ebc2671426079f73a9dbbbf1031c"


def _git_blob_sha1(data: bytes) -> str:
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class UpgradeCursor:
    def __init__(self, connection):
        self.connection = connection
        self._one = None
        self._all = []

    def __enter__(self): return self
    def __exit__(self, *_args): return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.connection.statements.append((normalized, params))
        self._one = None
        if "GET_LOCK" in normalized:
            self._one = (1,)
        elif normalized.startswith("SELECT migration_id"):
            self._all = list(self.connection.ledger.values())
        elif "information_schema.COLUMNS" in normalized:
            self._one = (int(params[1] in self.connection.columns),)
        elif "information_schema.STATISTICS" in normalized:
            self._one = (int(params[1] in self.connection.indexes),)
        elif normalized.startswith("ALTER TABLE workmanship_agent_capability_outbox ADD COLUMN"):
            match = re.search(r"ADD COLUMN `?([A-Za-z0-9_]+)`?", normalized, re.I)
            self.connection.columns.add(match.group(1))
        elif normalized.startswith("CREATE UNIQUE INDEX"):
            match = re.search(r"CREATE UNIQUE INDEX `?([A-Za-z0-9_]+)`?", normalized, re.I)
            self.connection.indexes.add(match.group(1))
        elif "UPDATE workmanship_agent_capability_outbox" in normalized:
            self.connection.legacy_row.update({
                "state": "quarantined", "last_error": "legacy_operation_id_ambiguous",
                "outcome_operation_id": None, "async_operation_id": None,
            })
        elif normalized.startswith("INSERT INTO ai00_schema_migrations"):
            migration_id, name, checksum, artifact_version = params
            self.connection.ledger[migration_id] = {
                "migration_id": migration_id, "name": name, "checksum": checksum,
                "artifact_version": artifact_version,
            }

    def fetchone(self): return self._one
    def fetchall(self): return self._all


class UpgradeConnection:
    def __init__(self, ledger):
        self.ledger = {row["migration_id"]: dict(row) for row in ledger}
        self.columns = {
            "event_id", "operation_id", "request_id", "capability_id", "payload_json",
            "state", "attempt_count", "next_attempt_at", "delivered_at", "created_at",
            "updated_at",
        }
        self.indexes = {"idx_agent_capability_outbox_dispatch", "idx_agent_capability_outbox_operation"}
        self.legacy_row = {"operation_id": "operation_ambiguous", "state": "pending"}
        self.statements = []
    def cursor(self): return UpgradeCursor(self)
    def commit(self): pass
    def rollback(self): pass


def test_applied_0005_upgrades_through_0006_without_checksum_rewrite():
    manifest = load_domain_manifests(
        ROOT / "backend/capability_v2/official_domains.json"
    ).require("agent")
    migrations = discover_domain_migrations(ROOT, manifest)
    migration_0005 = next(item for item in migrations if item.migration_id == "0005")
    migration_0006 = next(item for item in migrations if item.migration_id == "0006")
    old_bytes = migration_0005.path.read_bytes()
    assert _git_blob_sha1(old_bytes) == OLD_0005_BLOB_SHA1

    ledger = [
        {
            "migration_id": item.migration_id, "name": item.name,
            "checksum": item.checksum, "artifact_version": item.artifact_version,
        }
        for item in migrations if item.migration_id <= "0005"
    ]
    old_checksum = migration_0005.checksum
    connection = UpgradeConnection(ledger)

    applied = apply_domain_migrations(connection, manifest, migrations)

    assert applied == ("0006",)
    assert connection.ledger["0005"]["checksum"] == old_checksum
    assert connection.ledger["0006"]["checksum"] == migration_0006.checksum
    assert {
        "outcome_operation_id", "async_operation_id", "major_version",
        "lease_owner", "lease_token", "lease_expires_at", "last_error",
    } <= connection.columns
    assert "uq_agent_capability_outbox_outcome" in connection.indexes
    assert connection.legacy_row == {
        "operation_id": "operation_ambiguous", "state": "quarantined",
        "last_error": "legacy_operation_id_ambiguous",
        "outcome_operation_id": None, "async_operation_id": None,
    }
