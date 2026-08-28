from __future__ import annotations


def test_identity_projection_is_closed_and_omits_credentials_tokens_and_recovery_data():
    from backend.base.identity_profile import IdentityProfileService

    trusted = {
        "gid": "user_1", "name": "Alice", "tenant_gid": "tenant_1", "team_gids": ["team_1"],
        "locale": "zh-CN", "timezone": "Asia/Shanghai", "permission_ids": ["project.read"],
        "password_hash": "forbidden", "access_token": "forbidden", "recovery_codes": ["forbidden"],
        "authentication_provider": "forbidden", "internal_policy": {"forbidden": True},
    }
    port = type("Port", (), {"resolve": lambda self, **_kwargs: trusted})()
    result = IdentityProfileService(identity_port=port).get_current(actor={"gid": "user_1", "tenant_gid": "tenant_1"})

    assert set(result["profile"]) == {
        "actor_gid", "display_name", "tenant_gid", "team_gids", "locale", "timezone", "permission_ids",
    }
    assert result["profile"] == {
        "actor_gid": "user_1", "display_name": "Alice", "tenant_gid": "tenant_1", "team_gids": ["team_1"],
        "locale": "zh-CN", "timezone": "Asia/Shanghai", "permission_ids": ["project.read"],
    }


def test_identity_projection_resolves_one_trusted_effective_profile_for_rest_and_gateway_shapes():
    from backend.base.identity_profile import IdentityProfileService

    class EffectiveIdentityPort:
        def __init__(self):
            self.calls = []

        def resolve(self, *, actor_gid, tenant_gid):
            self.calls.append((actor_gid, tenant_gid))
            return {
                "gid": actor_gid, "name": "Alice", "team_id": tenant_gid,
                "locale": "zh-CN", "timezone": "Asia/Shanghai",
                "permissions": ["project.read", "craft.read"],
            }

    port = EffectiveIdentityPort()
    service = IdentityProfileService(identity_port=port)
    rest = service.get_current(actor={"gid": "user_1", "team_id": "tenant_1", "access_token": "forbidden"})
    gateway = service.get_current(actor={"gid": "user_1", "tenant_gid": "tenant_1"})

    expected = {"profile": {
        "actor_gid": "user_1", "display_name": "Alice", "tenant_gid": "tenant_1",
        "team_gids": ["tenant_1"], "locale": "zh-CN", "timezone": "Asia/Shanghai",
        "permission_ids": ["craft.read", "project.read"],
    }}
    assert rest == gateway == expected
    assert port.calls == [("user_1", "tenant_1"), ("user_1", "tenant_1")]
