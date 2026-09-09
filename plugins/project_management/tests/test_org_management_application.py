from __future__ import annotations

import pytest

from project_management_backend.domain.models import OrgManagementError, decode_org_management, apply_line_change


def test_codec_defaults_and_preserves_unrelated_meta() -> None:
    meta = {"theme": "blue"}
    state = decode_org_management(meta)
    assert state == {"revision": 0, "lines": []}
    updated, line = apply_line_change(
        meta, operation="managed_line.create",
        arguments={"name": " 焊装线 ", "leader_user_gids": ["u2", "u1", "u2"], "bop_line_gid": "b1"},
        expected_revision=0, new_gid=lambda: "line-1",
    )
    assert updated["theme"] == "blue"
    assert line == {"gid": "line-1", "name": "焊装线", "leader_user_gids": ["u1", "u2"], "bop_line_gid": "b1"}
    assert updated["org_management"]["revision"] == 1


def test_update_supports_change_people_clear_mapping_and_later_edit() -> None:
    meta, _ = apply_line_change({}, operation="managed_line.create",
        arguments={"name": "总装", "leader_user_gids": ["u1"], "bop_line_gid": "b1"},
        expected_revision=0, new_gid=lambda: "l1")
    meta, line = apply_line_change(meta, operation="managed_line.update",
        arguments={"line_gid": "l1", "leader_user_gids": ["u2", "u3"], "bop_line_gid": None},
        expected_revision=1, new_gid=lambda: "unused")
    assert line["name"] == "总装"
    assert line["leader_user_gids"] == ["u2", "u3"]
    assert line["bop_line_gid"] is None


def test_codec_rejects_duplicate_names_mappings_limits_and_conflicts() -> None:
    meta, _ = apply_line_change({}, operation="managed_line.create",
        arguments={"name": "A", "leader_user_gids": [], "bop_line_gid": "b1"},
        expected_revision=0, new_gid=lambda: "l1")
    for arguments in (
        {"name": " A ", "leader_user_gids": [], "bop_line_gid": "b2"},
        {"name": "B", "leader_user_gids": [], "bop_line_gid": "b1"},
        {"name": "B", "leader_user_gids": [f"u{i}" for i in range(51)], "bop_line_gid": None},
    ):
        with pytest.raises(OrgManagementError):
            apply_line_change(meta, operation="managed_line.create", arguments=arguments,
                              expected_revision=1, new_gid=lambda: "l2")
    with pytest.raises(OrgManagementError) as exc:
        apply_line_change(meta, operation="managed_line.delete", arguments={"line_gid": "l1"},
                          expected_revision=0, new_gid=lambda: "x")
    assert exc.value.code == "version_conflict"

