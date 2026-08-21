from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.gbop_entity_change import apply_gbop_entity_change


ROUTER = Path("plugins/craft/craft_backend/routers/gbop.py")


def test_gbop_entity_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.gbop.entity.change.apply"') == 1
    for name in ("create_entry", "update_entry", "delete_entry", "create_process", "update_process", "delete_process", "create_operation", "update_operation", "delete_operation", "create_entry_link", "delete_entry_link"):
        assert f"def _legacy_{name}" in source


def test_gbop_entity_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_gbop_entity_change({"operation": "entry.read"}, object())
