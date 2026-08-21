from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_staging_change import apply_bop_staging_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/staging.py")


def test_staging_crud_routes_use_one_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.staging.change.apply"') == 1
    for legacy in ("_legacy_create_staging", "_legacy_patch_staging", "_legacy_delete_staging"):
        assert f"def {legacy}" in source


def test_staging_change_rejects_unknown_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_staging_change({"operation": "promote"}, object())


def test_staging_update_rejects_unknown_fields_before_io() -> None:
    with pytest.raises(ValueError, match="updates must be an object"):
        apply_bop_staging_change({"operation": "update", "staging_gid": "s1", "updates": []}, object())
