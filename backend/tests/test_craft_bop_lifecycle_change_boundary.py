from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.bop_lifecycle_change import apply_bop_lifecycle_change


ROUTER = Path("plugins/craft/craft_backend/routers/_bop/lifecycle.py")


def test_lifecycle_change_routes_use_one_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.bop.lifecycle.change.apply"') == 1
    for legacy in (
        "_legacy_patch_pbom_match", "_legacy_patch_vehicle_ops_stats",
        "_legacy_generate_pbom_diff_queue", "_legacy_patch_pbom_diff_item",
    ):
        assert f"def {legacy}" in source


def test_lifecycle_change_rejects_unknown_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_bop_lifecycle_change({"operation": "phase.advance"}, object())


def test_lifecycle_change_validates_queue_status_before_io() -> None:
    with pytest.raises(ValueError, match="status must be pending"):
        apply_bop_lifecycle_change({"operation": "pbom_diff_queue.item.update", "item_gid": "i1", "status": "bad"}, object())
