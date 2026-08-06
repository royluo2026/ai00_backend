from pathlib import Path
from unittest.mock import patch

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities.bop_versions import (
    BopVersionQuery,
    get_bop_version,
    repository,
)


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    register_capabilities(registry)
    return registry


def test_all_authenticated_users_can_list_all_bop_versions():
    spec = _registry().get("craft.bop.version.list").spec

    assert spec.permissions == ()
    assert spec.risk.value == "read"
    assert spec.owner == "craft"


def test_get_and_list_have_different_output_contracts():
    registry = _registry()
    get_required = registry.get("craft.bop.version.get").spec.output_schema["required"]
    list_required = registry.get("craft.bop.version.list").spec.output_schema["required"]

    assert "revision" in get_required
    assert "items" not in get_required
    assert "items" in list_required
    assert "revision" not in list_required


def test_list_query_is_bounded_and_cursor_is_validated():
    with pytest.raises(ValueError, match="page_size"):
        BopVersionQuery.from_payload({"page_size": 101})
    with pytest.raises(ValueError, match="cursor"):
        BopVersionQuery.from_payload({"cursor": "not-a-cursor"})


def test_get_returns_identity_lifecycle_and_evidence():
    row = {
        "gid": "v1",
        "version_family_gid": "family-1",
        "project_gid": "project-1",
        "version_tag": "V3",
        "version_no": "3",
        "bop_name": "总装 BOP",
        "status": "baseline",
        "lifecycle_phase": "released",
        "lifecycle_state": '{"gate":"passed"}',
        "meta": '{"content_hash":"sha256:abc"}',
        "created_at": "2026-08-01 10:00:00",
        "updated_at": "2026-08-02 10:00:00",
    }
    with patch.object(repository, "get_version", return_value=row):
        result = get_bop_version(
            {"version_gid": "v1"},
            CapabilityContext(user_gid="user-1"),
        )

    assert result.data["version_gid"] == "v1"
    assert result.data["revision"] == "3"
    assert result.data["lifecycle"]["phase"] == "released"
    assert result.data["content_hash"] == "sha256:abc"
    assert result.evidence[0].reference == "craft://bop/version/v1"
    assert result.evidence[0].digest == "sha256:abc"


def test_get_uses_stable_business_error_for_missing_version():
    with patch.object(repository, "get_version", return_value=None):
        with pytest.raises(CapabilityBusinessError) as caught:
            get_bop_version(
                {"version_gid": "missing"},
                CapabilityContext(user_gid="user-1"),
            )

    assert caught.value.code == "bop_version_not_found"


def test_repository_sql_is_oceanbase_mysql_and_has_no_membership_filter():
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "plugins/craft/craft_backend/capabilities/bop_versions.py"
    ).read_text(encoding="utf-8")

    assert "workmanship_bop_bop_versions" in source
    assert "RETURNING" not in source.upper()
    assert "::" not in source
    assert "project_member" not in source
    assert "pbom." not in source
