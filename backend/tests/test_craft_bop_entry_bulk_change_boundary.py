from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_entry_bulk_change import apply_bop_entry_bulk_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/entries.py")


def test_entry_bulk_routes_use_one_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.entry.bulk.change.apply"') == 1
    for name in ("create_entry", "purge_version_entries", "import_tc_entries", "copy_entries_from", "copy_entries_from_gbop", "auto_link_entries", "patch_entity_detail", "rollback_entry_history"):
        assert f"def _legacy_{name}" in source


def test_entry_bulk_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_entry_bulk_change({"operation": "delete"}, object())


def test_entry_bulk_validates_required_fields_before_io() -> None:
    with pytest.raises(ValueError, match="version_gid is required"):
        apply_bop_entry_bulk_change({"operation": "import_tc"}, object())
