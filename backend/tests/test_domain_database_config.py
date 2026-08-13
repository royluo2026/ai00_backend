from __future__ import annotations

from pathlib import Path

import pytest

from backend.capability_v2.domain_database import (
    DomainDatabaseConfigurationError,
    connect_ddl,
    connect_runtime,
    load_domain_database_config,
    load_runtime_database_url,
)
from backend.capability_v2.domain_manifest import load_domain_manifests


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def craft_manifest():
    manifests = load_domain_manifests(ROOT / "backend/capability_v2/official_domains.json")
    return manifests.require("craft")


def test_domain_database_requires_both_explicit_urls(craft_manifest):
    with pytest.raises(DomainDatabaseConfigurationError, match="AI00_CRAFT_DB_URL"):
        load_domain_database_config(craft_manifest, {"AI00_DB_URL": "mysql://global:x@db/ai00_craft"})


def test_domain_database_rejects_wrong_database_name(craft_manifest):
    env = {
        "AI00_CRAFT_DB_URL": "mysql://runtime:runtime-secret@db/ai00_base",
        "AI00_CRAFT_DDL_DB_URL": "mysql://ddl:ddl-secret@db/ai00_craft",
    }
    with pytest.raises(DomainDatabaseConfigurationError, match="database_name_mismatch"):
        load_domain_database_config(craft_manifest, env)


def test_domain_database_rejects_same_runtime_and_ddl_user(craft_manifest):
    env = {
        "AI00_CRAFT_DB_URL": "mysql://craft:runtime-secret@db/ai00_craft",
        "AI00_CRAFT_DDL_DB_URL": "mysql://craft:ddl-secret@db/ai00_craft",
    }
    with pytest.raises(DomainDatabaseConfigurationError, match="credential_separation_required"):
        load_domain_database_config(craft_manifest, env)


def test_domain_database_rejects_incomplete_or_unsupported_urls_without_leaking_secret(craft_manifest):
    env = {
        "AI00_CRAFT_DB_URL": "postgresql://runtime:runtime-secret@db/ai00_craft",
        "AI00_CRAFT_DDL_DB_URL": "mysql://ddl:ddl-secret@db/ai00_craft",
    }
    with pytest.raises(DomainDatabaseConfigurationError) as error:
        load_domain_database_config(craft_manifest, env)
    assert "runtime-secret" not in str(error.value)


def test_domain_database_connectors_use_separate_validated_credentials(craft_manifest, monkeypatch):
    env = {
        "AI00_CRAFT_DB_URL": "mysql+pymysql://craft_runtime:runtime%2Bsecret@db.example:2881/ai00_craft",
        "AI00_CRAFT_DDL_DB_URL": "mysql://craft_ddl:ddl%2Bsecret@db.example:2881/ai00_craft",
    }
    config = load_domain_database_config(craft_manifest, env)
    calls = []

    def fake_connect(**kwargs):
        calls.append(kwargs)
        return kwargs["user"]

    monkeypatch.setattr("pymysql.connect", fake_connect)

    assert connect_runtime(config) == "craft_runtime"
    assert connect_ddl(config) == "craft_ddl"
    assert calls == [
        {
            "host": "db.example",
            "port": 2881,
            "user": "craft_runtime",
            "password": "runtime+secret",
            "database": "ai00_craft",
            "charset": "utf8mb4",
            "autocommit": False,
        },
        {
            "host": "db.example",
            "port": 2881,
            "user": "craft_ddl",
            "password": "ddl+secret",
            "database": "ai00_craft",
            "charset": "utf8mb4",
            "autocommit": False,
        },
    ]
    assert "runtime+secret" not in repr(config)
    assert "ddl+secret" not in repr(config)


def test_legacy_per_domain_runtime_loader_remains_available(craft_manifest):
    env = {
        "AI00_CRAFT_DB_URL": "mysql://craft_runtime:runtime-secret@db/ai00_craft",
    }

    url = load_runtime_database_url(craft_manifest, env)

    assert url.database == "ai00_craft"
    assert url.username == "craft_runtime"
