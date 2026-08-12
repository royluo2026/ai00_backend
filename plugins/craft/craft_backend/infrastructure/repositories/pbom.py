from __future__ import annotations

import json
from typing import Any

from ...data.connection import get_craft_conn
from ...domain.pbom import PbomVersion, PbomVersionStatus


class SqlPbomRepository:
    def get_version(self, version_gid: str) -> PbomVersion | None:
        with get_craft_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT gid,project_ref,version_tag,status,knowledge_revision_ref,ontology_release_ref,"
                "revision_commit_ref,revision FROM workmanship_bop_pbom_versions WHERE gid=%s",
                (version_gid,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        value = dict(row)
        value["status"] = PbomVersionStatus(value["status"])
        return PbomVersion(**value)

    def create_version(self, version: PbomVersion) -> PbomVersion:
        with get_craft_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_bop_pbom_versions "
                "(gid,project_ref,project_gid,version_tag,name,source_type,status,knowledge_revision_ref,"
                "ontology_release_ref,revision_commit_ref,revision) VALUES (%s,%s,%s,%s,%s,'native',%s,%s,%s,%s,%s)",
                (version.gid, version.project_ref, version.project_ref, version.version_tag, version.version_tag,
                 version.status.value, version.knowledge_revision_ref, version.ontology_release_ref,
                 version.revision_commit_ref, version.revision),
            )
            conn.commit()
        return version

    def search_versions(self, project_ref: str | None, limit: int) -> list[PbomVersion]:
        sql = "SELECT gid,project_ref,version_tag,status,knowledge_revision_ref,ontology_release_ref,revision_commit_ref,revision FROM workmanship_bop_pbom_versions"
        params: list[Any] = []
        if project_ref:
            sql += " WHERE project_ref=%s"
            params.append(project_ref)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        with get_craft_conn() as conn, conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [PbomVersion(**{**dict(row), "status": PbomVersionStatus(row["status"])}) for row in rows]

    def list_parts(self, version_gid: str, query: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        where = ["snapshot_gid=%s", "is_deleted=0"]
        params: list[Any] = [version_gid]
        if query:
            where.append("(part_no LIKE %s OR title LIKE %s)")
            params.extend([f"%{query}%", f"%{query}%"])
        params.append(limit)
        with get_craft_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT gid,snapshot_gid,part_no,title,quantity,unit,parent_gid,component_id,meta "
                "FROM workmanship_bop_pbom WHERE " + " AND ".join(where) + " ORDER BY part_no LIMIT %s",
                params,
            )
            return [dict(row) for row in cursor.fetchall()]

    def replace_part(self, version_gid: str, part: dict[str, Any]) -> dict[str, Any]:
        part_gid = str(part.get("gid") or part.get("part_no") or "").strip()
        if not part_gid:
            raise ValueError("part gid or part_no is required")
        with get_craft_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_bop_pbom (gid,snapshot_gid,part_no,title,quantity,unit,meta) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE title=VALUES(title),"
                "quantity=VALUES(quantity),unit=VALUES(unit),meta=VALUES(meta)",
                (part_gid, version_gid, part.get("part_no", part_gid), part.get("title", ""),
                 part.get("quantity", 1), part.get("unit", "pcs"), json.dumps(part.get("meta", {}), ensure_ascii=False)),
            )
            conn.commit()
        return {"version_gid": version_gid, "part_gid": part_gid}

    def set_status(self, version_gid: str, status: PbomVersionStatus, expected_revision: int) -> PbomVersion:
        with get_craft_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "UPDATE workmanship_bop_pbom_versions SET status=%s,revision=revision+1 "
                "WHERE gid=%s AND revision=%s",
                (status.value, version_gid, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ValueError("pbom revision conflict")
            conn.commit()
        version = self.get_version(version_gid)
        if version is None:
            raise ValueError("pbom version disappeared")
        return version


__all__ = ["SqlPbomRepository"]
