from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock

from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    TenantIdentity,
)
from backend.plugin_platform.storage import _authorize_storage_key
from backend.plugin_platform.service import _authorize_plugin_installation
from plugins.craft.craft_backend.capabilities import _authorize_bop_version
from plugins.digital_model.digital_model_backend.capabilities import (
    _authorize_model,
    _authorize_model_version,
)


def _identity(consumer_type: ConsumerType = ConsumerType.PLUGIN) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(
            user_id="user-1",
            authentication_method="test",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(tenant_id="team-1", membership="member"),
        consumer=ConsumerDescriptor(
            type=consumer_type,
            consumer_id=("devteam.ai00.project-readiness" if consumer_type is ConsumerType.PLUGIN else "consumer-1"),
            installation_id=("install-1" if consumer_type is ConsumerType.PLUGIN else None),
            mount_session_id=("mount-1" if consumer_type is ConsumerType.PLUGIN else None),
            agent_run_id=("run-1" if consumer_type is ConsumerType.AGENT else None),
        ),
    )


def test_plugin_storage_key_authorizer_accepts_only_safe_trusted_namespaces():
    assert _authorize_storage_key("history/v1", _identity()) is True
    assert _authorize_storage_key("history/v1", _identity(ConsumerType.AGENT)) is True
    assert _authorize_storage_key("history/v1", _identity(ConsumerType.WEB)) is False
    assert _authorize_storage_key("../foreign/history", _identity()) is False
    assert _authorize_storage_key("/absolute", _identity()) is False


def test_plugin_installation_authorizer_allows_only_authenticated_web_managers():
    assert _authorize_plugin_installation(
        "devteam.ai00.project-readiness", _identity(ConsumerType.WEB)
    ) is True
    assert _authorize_plugin_installation(
        "devteam.ai00.project-readiness", _identity(ConsumerType.PLUGIN)
    ) is False
    assert _authorize_plugin_installation("../foreign", _identity(ConsumerType.WEB)) is False

    service_identity = _identity(ConsumerType.WEB).model_copy(
        update={
            "actor": ActorIdentity(
                service_id="service-1",
                authentication_method="service",
                authenticated_at=datetime.now(UTC),
            )
        }
    )
    assert _authorize_plugin_installation(
        "devteam.ai00.project-readiness", service_identity
    ) is False


def test_craft_bop_resource_matches_existing_authenticated_read_boundary():
    assert _authorize_bop_version("213828139200024576", _identity()) is True

    anonymous = _identity().model_copy(
        update={
            "actor": ActorIdentity(
                service_id="service-1",
                authentication_method="service",
                authenticated_at=datetime.now(UTC),
            )
        }
    )
    assert _authorize_bop_version("213828139200024576", anonymous) is False
    assert _authorize_bop_version("", _identity()) is False


def test_digital_model_authorizers_enforce_owner_or_team_visibility(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [{"allowed": 1}, {"allowed": 1}, None]
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(
        "plugins.digital_model.digital_model_backend.capabilities.models.get_digital_model_conn",
        fake_connection,
    )

    identity = _identity()
    assert _authorize_model("mdl-1", identity) is True
    assert _authorize_model_version("mdv-1", identity) is True
    assert _authorize_model("mdl-foreign", identity) is False

    first_sql, first_params = cursor.execute.call_args_list[0].args
    second_sql, second_params = cursor.execute.call_args_list[1].args
    assert "workmanship_model_models" in first_sql
    assert first_params == ("mdl-1", "user-1", "team-1", "team-1")
    assert "workmanship_model_versions" in second_sql
    assert "JOIN workmanship_model_models" in second_sql
    assert second_params == ("mdv-1", "user-1", "team-1", "team-1")
