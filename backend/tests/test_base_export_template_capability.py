from __future__ import annotations

from datetime import UTC, datetime

from backend.base.export_templates import apply_export_template, list_export_templates
from backend.capabilities.models_next import CapabilityContext


def test_export_template_read_is_user_scoped_and_normalizes_rows(monkeypatch):
    rows = [
        {
            "gid": "tpl-1",
            "name": "Craft",
            "module": "craft",
            "owner_gid": "user-1",
            "is_shared": False,
            "config": '{"columns": []}',
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 2, tzinfo=UTC),
        }
    ]
    calls = []

    def fake_list(user_gid: str, module: str = ""):
        calls.append((user_gid, module))
        return rows

    monkeypatch.setattr("backend.base.export_templates._list_export_templates", fake_list)

    result = list_export_templates(
        {"module": "craft", "limit": 10},
        CapabilityContext(user_gid="user-1", team_gid="team-1"),
    )

    assert calls == [("user-1", "craft")]
    assert result["module"] == "craft"
    assert result["total"] == 1
    assert result["items"][0]["config"] == {"columns": []}
    assert result["items"][0]["created_at"].startswith("2026-01-01T00:00:00")


def test_export_template_read_rejects_unbounded_limits():
    import pytest

    with pytest.raises(ValueError, match="limit"):
        list_export_templates(
            {"module": "craft", "limit": 501},
            CapabilityContext(user_gid="user-1"),
        )


def test_export_template_change_create_uses_base_sdk_and_actor(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "backend.base.export_templates._create_export_template",
        lambda user_gid, name, module, config, is_shared: calls.append(
            (user_gid, name, module, config, is_shared)
        ) or "tpl-1",
    )

    result = apply_export_template(
        {
            "operation": "create",
            "name": "Craft",
            "module": "craft",
            "config": {"columns": []},
            "is_shared": False,
        },
        CapabilityContext(user_gid="user-1", active_roles=("member",)),
    )

    assert calls == [("user-1", "Craft", "craft", {"columns": []}, False)]
    assert result == {"operation": "create", "gid": "tpl-1"}


def test_export_template_change_maps_sdk_errors_to_stable_business_errors(monkeypatch):
    import pytest
    from backend.capability_v2.provider_contracts import CapabilityBusinessError

    monkeypatch.setattr(
        "backend.base.export_templates._delete_export_template",
        lambda *_args: (_ for _ in ()).throw(PermissionError("denied")),
    )

    with pytest.raises(CapabilityBusinessError, match="denied") as error:
        apply_export_template(
            {"operation": "delete", "gid": "tpl-1"},
            CapabilityContext(user_gid="user-1"),
        )
    assert error.value.code == "permission_denied"
