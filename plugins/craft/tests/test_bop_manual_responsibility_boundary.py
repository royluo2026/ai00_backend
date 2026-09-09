from pathlib import Path


def test_ordinary_org_roles_do_not_bypass_bop_scope() -> None:
    source = (Path(__file__).parents[1] / "craft_backend/routers/_bop/_helpers.py").read_text(encoding="utf-8")
    assert "org_role == 'super_admin'" in source
    assert "'member', 'team_admin'" not in source
