"""Live test-database proof for governed TC import entity/link integrity."""
from __future__ import annotations

import json

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from backend.platform_sdk.ids import next_gid
from plugins.craft.craft_backend.capabilities.bop_entry_bulk_change import apply_bop_entry_bulk_change


pytestmark = pytest.mark.integration


def test_tc_reimport_keeps_entities_links_and_staging_consistent(craft_db) -> None:
    project_gid = None
    version_gid = str(next_gid())
    pbom_version_gid = str(next_gid())
    resource_gids = {kind: str(next_gid()) for kind in ("socket", "tool", "fixture", "equipment")}
    created_entity_gids: set[str] = set()
    old_entity_gids: set[str] = set()
    old_entry_gids: set[str] = set()

    with craft_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid FROM workmanship_proj_projects "
                "WHERE is_deleted=FALSE ORDER BY created_at LIMIT 1"
            )
            project = cur.fetchone()
            if not project:
                pytest.skip("live Craft test requires one existing test project")
            project_gid = str(project["gid"])
            cur.execute(
                "INSERT INTO workmanship_bop_pbom_versions "
                "(gid,project_gid,version_tag,name,source_type,status,meta) "
                "VALUES (%s,%s,'tc-integrity','TC integrity','tc','draft',%s)",
                (pbom_version_gid, project_gid, json.dumps({"test": "tc-import-integrity"})),
            )
            cur.execute(
                "INSERT INTO workmanship_bop_bop_versions "
                "(gid,project_gid,version_tag,bop_name,pbom_version_gid,meta,lifecycle_state) "
                "VALUES (%s,%s,'tc-integrity','TC integrity',%s,%s,%s)",
                (version_gid, project_gid, pbom_version_gid,
                 json.dumps({"test": "tc-import-integrity"}), json.dumps({})),
            )
            for resource_type, gid in resource_gids.items():
                cur.execute(
                    "INSERT INTO workmanship_craft_resource_requirements "
                    "(gid,resource_type,code,name,attributes,source,status,created_by,updated_by) "
                    "VALUES (%s,%s,%s,%s,%s,'test:tc-import-integrity','active','pytest','pytest')",
                    (gid, resource_type, f"TC-{resource_type}-{gid}", resource_type, json.dumps({})),
                )

    rows = [
        {"_level": 1, "node_type": "line_process", "title": "Line"},
        {"_level": 2, "node_type": "station_process", "title": "Station"},
        {"_level": 3, "node_type": "process", "title": "Process"},
        {"_level": 4, "node_type": "operation", "title": "Operation"},
        {"_level": 4, "node_type": "operator_process", "title": "Operator"},
        {"_level": 5, "node_type": "part", "title": "Part", "bom_row_id": "P-1"},
        {"_level": 5, "node_type": "non_standard_part", "title": "NS", "bom_row_id": "P-2"},
        {"_level": 5, "node_type": "standard_part", "title": "STD", "bom_row_id": "P-3"},
        {"_level": 5, "node_type": "support_material", "title": "Material", "bom_row_id": "P-4"},
        *(
            {"_level": 5, "node_type": f"{kind}_need", "title": kind,
             "resource_code": f"TC-{kind}-{resource_gids[kind]}"}
            for kind in ("socket", "tool", "fixture", "equipment")
        ),
        {"_level": 5, "node_type": "equipment_need", "title": "Unmatched",
         "resource_code": f"TC-unmatched-{version_gid}"},
    ]
    context = CapabilityContext(user_gid="pytest", request_id=str(next_gid()), permissions=("craft.write",))

    try:
        first = apply_bop_entry_bulk_change(
            {"operation": "import_tc", "version_gid": version_gid, "rows": rows}, context,
        )["data"]
        assert first == {"count": 14, "skipped": 0, "replaced": 0}

        with craft_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid FROM workmanship_bop_bop_entries "
                    "WHERE version_gid=%s AND is_deleted=FALSE", (version_gid,),
                )
                old_entry_gids = {str(row["gid"]) for row in cur.fetchall()}
                cur.execute(
                    "SELECT entity_gid FROM workmanship_bop_bop_entry_links "
                    "WHERE version_gid=%s AND deleted_at IS NULL", (version_gid,),
                )
                old_entity_gids.update(str(row["entity_gid"]) for row in cur.fetchall())
                created_entity_gids.update(old_entity_gids)
                cur.execute(
                    "SELECT COUNT(*) AS n FROM workmanship_bop_bop_entry_links "
                    "WHERE version_gid=%s AND deleted_at IS NULL AND is_primary=TRUE", (version_gid,),
                )
                assert cur.fetchone()["n"] == 13
                cur.execute(
                    "SELECT match_status,COUNT(*) AS n FROM workmanship_craft_tc_resource_staging "
                    "WHERE version_gid=%s GROUP BY match_status", (version_gid,),
                )
                assert cur.fetchall() == [{"match_status": "unmatched", "n": 1}]

        second = apply_bop_entry_bulk_change(
            {"operation": "import_tc", "version_gid": version_gid, "rows": rows},
            CapabilityContext(user_gid="pytest", request_id=str(next_gid()), permissions=("craft.write",)),
        )["data"]
        assert second == {"count": 14, "skipped": 0, "replaced": 14}

        with craft_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid FROM workmanship_bop_bop_entries "
                    "WHERE version_gid=%s AND is_deleted=FALSE", (version_gid,),
                )
                assert len(cur.fetchall()) == 14
                cur.execute(
                    "SELECT entity_gid FROM workmanship_bop_bop_entry_links "
                    "WHERE version_gid=%s AND deleted_at IS NULL", (version_gid,),
                )
                created_entity_gids.update(str(row["entity_gid"]) for row in cur.fetchall())
                cur.execute(
                    "SELECT entry_gid,COUNT(*) AS n FROM workmanship_bop_bop_entry_links "
                    "WHERE version_gid=%s AND deleted_at IS NULL AND is_primary=TRUE "
                    "GROUP BY entry_gid HAVING COUNT(*)<>1", (version_gid,),
                )
                assert not cur.fetchall()
                for table in (
                    "workmanship_bop_bop_line", "workmanship_bop_bop_station",
                    "workmanship_bop_bop_process", "workmanship_bop_bop_steps",
                    "workmanship_bop_bop_operator",
                ):
                    cur.execute(
                        f"SELECT COUNT(*) AS n FROM {table} "
                        f"WHERE gid IN ({','.join(['%s'] * len(old_entity_gids))}) AND is_deleted=FALSE",
                        tuple(old_entity_gids),
                    )
                    assert cur.fetchone()["n"] == 0
                cur.execute(
                    f"SELECT COUNT(*) AS n FROM workmanship_bop_pbom "
                    f"WHERE gid IN ({','.join(['%s'] * len(old_entity_gids))}) AND is_deleted=FALSE",
                    tuple(old_entity_gids),
                )
                assert cur.fetchone()["n"] == 0
                cur.execute(
                    "SELECT COUNT(*) AS n FROM workmanship_craft_resource_requirements "
                    f"WHERE gid IN ({','.join(['%s'] * len(resource_gids))}) AND status='active'",
                    tuple(resource_gids.values()),
                )
                assert cur.fetchone()["n"] == 4
    finally:
        with craft_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workmanship_craft_tc_resource_staging WHERE version_gid=%s", (version_gid,))
                cur.execute("DELETE FROM workmanship_bop_bop_entry_links WHERE version_gid=%s", (version_gid,))
                cur.execute("DELETE FROM workmanship_bop_bop_entries WHERE version_gid=%s", (version_gid,))
                if created_entity_gids:
                    entity_placeholders = ",".join(["%s"] * len(created_entity_gids))
                    for table in (
                        "workmanship_bop_bop_line", "workmanship_bop_bop_station",
                        "workmanship_bop_bop_process", "workmanship_bop_bop_steps",
                        "workmanship_bop_bop_operator",
                    ):
                        cur.execute(
                            f"DELETE FROM {table} WHERE gid IN ({entity_placeholders})",
                            tuple(created_entity_gids),
                        )
                cur.execute("DELETE FROM workmanship_bop_pbom WHERE snapshot_gid=%s", (pbom_version_gid,))
                cur.execute("DELETE FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
                cur.execute("DELETE FROM workmanship_bop_pbom_versions WHERE gid=%s", (pbom_version_gid,))
                cur.execute(
                    f"DELETE FROM workmanship_craft_resource_requirements "
                    f"WHERE gid IN ({','.join(['%s'] * len(resource_gids))})",
                    tuple(resource_gids.values()),
                )
