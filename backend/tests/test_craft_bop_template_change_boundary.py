from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_template_change import apply_bop_template_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/templates.py")


def test_template_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.template.change.apply"') == 1
    assert "def _legacy_save_as_template" in source
    assert "def _legacy_update_template_from" in source


def test_template_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_template_change({"operation": "delete", "source_version_gid": "v1"}, object())


def test_template_validates_source_identifier_before_io() -> None:
    with pytest.raises(ValueError, match="source_version_gid is required"):
        apply_bop_template_change({"operation": "save_as_template"}, object())
