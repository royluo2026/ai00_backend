from pathlib import Path


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/fork.py")


def test_fork_preset_crud_routes_use_change_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.fork_preset.change.apply"') == 1
    assert "def _legacy_create_fork_preset" in source
    assert "def _legacy_update_fork_preset" in source
    assert "def _legacy_delete_fork_preset" in source
