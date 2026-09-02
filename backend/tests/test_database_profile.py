from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.capability_v2.database_profile import load_database_profile
from backend.capability_v2.domain_database import (
    DomainDatabaseConfigurationError,
    load_ddl_database_url,
    load_runtime_database_url,
)
from backend.capability_v2.domain_manifest import load_domain_manifests


ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DOMAINS = ROOT / "backend/capability_v2/official_domains.json"
SINGLE_DATABASE_PROFILE = ROOT / "backend/capability_v2/database_profiles/single_database.json"


@pytest.fixture
def manifests():
    return load_domain_manifests(OFFICIAL_DOMAINS)


def test_single_database_profile_maps_every_domain_to_ai00_test(manifests):
    profile = load_database_profile(SINGLE_DATABASE_PROFILE, manifests)
    assert profile.baseline_schema_path == "backend/db/mysql_schema.sql"

    assert profile.isolation_profile == "single_database_domain_tables"
    assert profile.database_name == "ai00_test"
    assert profile.runtime_url_env == "AI00_SHARED_RUNTIME_DB_URL"
    assert profile.domains == tuple(sorted(item.domain_id for item in manifests.domains))


def test_single_database_runtime_accepts_one_shared_url_for_all_domains(manifests):
    profile = load_database_profile(SINGLE_DATABASE_PROFILE, manifests)
    env = {
        "AI00_SHARED_RUNTIME_DB_URL":
            "mysql://runtime:runtime-secret@db.example:2881/ai00_test"
    }

    assert load_runtime_database_url(manifests.require("craft"), env, profile).database == "ai00_test"
    assert load_runtime_database_url(manifests.require("device"), env, profile).username == "runtime"


def test_single_database_runtime_accepts_explicit_deployment_database_name(manifests):
    profile = load_database_profile(SINGLE_DATABASE_PROFILE, manifests)
    env = {
        "AI00_SHARED_RUNTIME_DB_URL":
            "mysql://runtime:runtime-secret@db.example:2881/sht_mes_tool",
        "AI00_SHARED_DATABASE_NAME": "sht_mes_tool",
    }

    url = load_runtime_database_url(manifests.require("craft"), env, profile)

    assert url.database == "sht_mes_tool"


def test_single_database_profile_has_no_runtime_ddl_path(manifests):
    profile = load_database_profile(SINGLE_DATABASE_PROFILE, manifests)

    with pytest.raises(DomainDatabaseConfigurationError, match="ddl_identity_external"):
        load_ddl_database_url(manifests.require("craft"), {}, profile)


def test_base_runtime_connection_uses_single_database_profile(monkeypatch):
    from backend.base import approval

    monkeypatch.delenv("AI00_BASE_DB_URL", raising=False)
    monkeypatch.setenv(
        "AI00_SHARED_RUNTIME_DB_URL",
        "mysql://runtime:runtime-secret@db.example:2881/ai00_test",
    )
    captured = []
    monkeypatch.setattr(
        approval,
        "connect_domain_database",
        lambda url: captured.append(url) or "connection",
    )

    connection = approval._base_runtime_connection()

    assert connection == "connection"
    assert captured[0].database == "ai00_test"
    assert captured[0].username == "runtime"


def test_base_inbox_connection_uses_single_database_profile(monkeypatch):
    from backend.base import inbox

    monkeypatch.delenv("AI00_BASE_DB_URL", raising=False)
    monkeypatch.setenv(
        "AI00_SHARED_RUNTIME_DB_URL",
        "mysql://runtime:runtime-secret@db.example:2881/sht_mes_tool",
    )
    monkeypatch.setenv("AI00_SHARED_DATABASE_NAME", "sht_mes_tool")
    captured = []
    monkeypatch.setattr(
        inbox,
        "connect_domain_database",
        lambda url: captured.append(url) or "connection",
    )

    connection = inbox._base_connection()

    assert connection == "connection"
    assert captured[0].database == "sht_mes_tool"


def test_profile_rejects_incomplete_domain_coverage(tmp_path: Path, manifests):
    document = json.loads(SINGLE_DATABASE_PROFILE.read_text(encoding="utf-8"))
    document["domains"].remove("device")
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="domain_coverage_mismatch"):
        load_database_profile(path, manifests)


def test_official_schema_paths_are_complete_unique_and_include_primary_migration(manifests):
    all_paths = []
    for manifest in manifests.domains:
        assert manifest.database.migration_path in manifest.database.schema_paths
        assert len(manifest.database.schema_paths) == len(set(manifest.database.schema_paths))
        all_paths.extend(manifest.database.schema_paths)
    assert len(all_paths) == len(set(all_paths))


def test_schema_paths_reject_repository_escape(tmp_path: Path):
    document = json.loads(OFFICIAL_DOMAINS.read_text(encoding="utf-8"))
    document["domains"][0]["database"]["schema_paths"] = ["../outside.sql"]
    path = tmp_path / "domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValidationError, match="repository-relative POSIX path"):
        load_domain_manifests(path)
