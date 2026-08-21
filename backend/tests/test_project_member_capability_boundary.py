from pathlib import Path


ROUTER = Path("plugins/craft/craft_backend/routers/projects.py")


def test_project_member_routes_use_project_capabilities() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert 'capability_id="project.member.read"' in source
    assert 'capability_id="project.member.change.apply"' in source
    assert "def _legacy_list_project_members" in source
    assert "def _legacy_remove_project_member" in source
