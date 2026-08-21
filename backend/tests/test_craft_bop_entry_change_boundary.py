from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_entry_change import apply_bop_entry_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/entries.py")


def test_entry_change_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.entry.change.apply"') == 1
    assert "def _legacy_update_entry" in source
    assert "def _legacy_delete_entry" in source


def test_entry_change_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_entry_change({"operation": "create"}, object())


def test_entry_change_validates_update_payload_before_io() -> None:
    with pytest.raises(ValueError, match="updates must be a non-empty object"):
        apply_bop_entry_change({"operation": "update", "entry_gid": "e1", "updates": {}}, object())
