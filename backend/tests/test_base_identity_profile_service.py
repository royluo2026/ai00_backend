from __future__ import annotations


def test_identity_projection_is_closed_and_omits_credentials_tokens_and_recovery_data():
    from backend.base.identity_profile import IdentityProfileService

    result = IdentityProfileService().get_current(actor={
        "gid": "user_1", "name": "Alice", "tenant_gid": "tenant_1", "team_gids": ["team_1"],
        "locale": "zh-CN", "timezone": "Asia/Shanghai", "permission_ids": ["project.read"],
        "password_hash": "forbidden", "access_token": "forbidden", "recovery_codes": ["forbidden"],
        "authentication_provider": "forbidden", "internal_policy": {"forbidden": True},
    })

    assert set(result["profile"]) == {
        "actor_gid", "display_name", "tenant_gid", "team_gids", "locale", "timezone", "permission_ids",
    }
    assert result["profile"] == {
        "actor_gid": "user_1", "display_name": "Alice", "tenant_gid": "tenant_1", "team_gids": ["team_1"],
        "locale": "zh-CN", "timezone": "Asia/Shanghai", "permission_ids": ["project.read"],
    }
