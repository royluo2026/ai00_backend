from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_lifecycle_history_change import apply_bop_lifecycle_history_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/lifecycle.py")


def test_history_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.lifecycle.history.change.apply"') == 1
    assert "def _legacy_undo_line_history" in source
    assert "def _legacy_redo_line_history" in source


def test_history_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of: undo, redo"):
        apply_bop_lifecycle_history_change({"operation": "reset", "version_gid": "v1", "line_gid": "l1"}, object())


def test_history_validates_identifiers_before_io() -> None:
    with pytest.raises(ValueError, match="line_gid is required"):
        apply_bop_lifecycle_history_change({"operation": "undo", "version_gid": "v1"}, object())
