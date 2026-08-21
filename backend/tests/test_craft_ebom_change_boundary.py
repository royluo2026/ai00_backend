from pathlib import Path

import pytest

from plugins.craft.craft_backend.capabilities.ebom_change import apply_ebom_change
from backend.tests.capability_completion_support import registered_descriptor_ids


ROUTER = Path("plugins/craft/craft_backend/routers/ebom.py")


def test_ebom_change_routes_share_one_gateway_capability() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count('capability_id="craft.ebom.change.apply"') == 1
    for legacy in (
        "_legacy_delete_snapshot", "_legacy_patch_snapshot", "_legacy_patch_vpps_stats",
        "_legacy_patch_snapshot_status", "_legacy_add_part", "_legacy_add_parts_batch",
        "_legacy_update_part", "_legacy_delete_part",
    ):
        assert f"def {legacy}" in source


def test_ebom_change_rejects_unknown_operation_before_io() -> None:
    with pytest.raises(ValueError, match="operation must be one of"):
        apply_ebom_change({"operation": "snapshot.drop_everything"}, object())


def test_ebom_change_validates_status_before_io() -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        apply_ebom_change({"operation": "snapshot.status.patch", "snapshot_gid": "s1", "status": "published"}, object())


def test_ebom_atomic_capabilities_are_registered_independently() -> None:
    actual = registered_descriptor_ids("plugins.craft.craft_backend.capabilities")
    assert {
        "craft.ebom.snapshot.delete", "craft.ebom.snapshot.update",
        "craft.ebom.snapshot.status.update", "craft.ebom.snapshot.vpps_stats.update",
        "craft.ebom.part.create", "craft.ebom.part.bulk_create",
        "craft.ebom.part.update", "craft.ebom.part.delete",
    } <= actual
