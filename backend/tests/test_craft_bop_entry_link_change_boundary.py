from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_entry_link_change import apply_bop_entry_link_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/entries.py")


def test_entry_link_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.entry_link.change.apply"') == 1
    assert "def _legacy_create_entry_link" in source
    assert "def _legacy_delete_entry_link" in source


def test_entry_link_change_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_entry_link_change({"operation": "replace"}, object())


def test_entry_link_change_validates_attach_fields_before_io() -> None:
    with pytest.raises(ValueError, match="entry_gid is required"):
        apply_bop_entry_link_change({"operation": "attach"}, object())
