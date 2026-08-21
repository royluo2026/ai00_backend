from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_staging_lifecycle_change import apply_bop_staging_lifecycle_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/staging.py")


def test_staging_lifecycle_routes_use_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.staging.lifecycle.change.apply"') == 1
    assert "def _legacy_demote_entry" in source
    assert "def _legacy_promote_staging" in source


def test_staging_lifecycle_validates_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_staging_lifecycle_change({"operation": "copy"}, object())


def test_staging_lifecycle_validates_identifiers_before_io() -> None:
    with pytest.raises(ValueError, match="entry_gid is required"):
        apply_bop_staging_lifecycle_change({"operation": "demote"}, object())
