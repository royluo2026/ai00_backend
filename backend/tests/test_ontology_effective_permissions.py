from backend.platform_sdk.effective_identity import build_effective_profile
from backend.routers import deps


def test_authenticated_members_can_propose_reviewed_ontology_changes():
    profile = build_effective_profile(
        {"gid": "member-1", "system_role": "member", "org_role": "member"},
        [],
    )

    assert "ontology.propose" in profile["permissions"]


def test_external_users_cannot_propose_ontology_changes():
    profile = build_effective_profile(
        {"gid": "external-1", "system_role": "external", "org_role": "external"},
        [],
    )

    assert "ontology.propose" not in profile["permissions"]


def test_gateway_profile_projects_ontology_proposal_permission(monkeypatch):
    monkeypatch.setattr(deps, "_get_user_grants", lambda _gid: [])

    profile = deps.build_profile(
        {"gid": "member-1", "system_role": "member", "org_role": "member"}
    )

    assert "ontology.propose" in profile["permissions"]
