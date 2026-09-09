from __future__ import annotations

import pytest

from backend.base import desktop_actions
from backend.capability_v2.provider_contracts import CapabilityBusinessError


@pytest.mark.parametrize("handler,payload", [
    (desktop_actions.create_team, {"name": "A", "is_active": True, "parent_team_gid": None}),
    (desktop_actions.add_team_member, {"team_gid": "t", "member": {"user_gid": "u"}}),
    (desktop_actions.remove_team_member, {"team_gid": "t", "user_gid": "u"}),
])
def test_team_admin_cannot_mutate_super_managed_org(handler, payload) -> None:
    with pytest.raises(CapabilityBusinessError) as exc:
        handler(payload, {"system_role": "team_admin", "org_role": "member"})
    assert exc.value.code == "permission_denied"
