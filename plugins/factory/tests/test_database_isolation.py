from __future__ import annotations

from pathlib import Path

import pytest

from plugins.factory.factory_backend.infrastructure.connection import _params


ROOT = Path(__file__).resolve().parents[3]


def test_factory_database_never_falls_back_to_shared_credentials(monkeypatch):
    monkeypatch.delenv("AI00_FACTORY_DB_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "mysql://base:secret@db/base")

    with pytest.raises(RuntimeError, match="AI00_FACTORY_DB_URL"):
        _params()


def test_factory_has_an_independent_migration_stream():
    migration = ROOT / "backend/db/migrations/domains/factory/0001_factory.sql"
    assert migration.is_file()
    sql = migration.read_text(encoding="utf-8")
    assert "workmanship_factory_schema_migrations" in sql
    assert "workmanship_bop_" not in sql
    assert "workmanship_proj_" not in sql

