"""Integration-owned persistence. No target-domain table is reachable here."""
from __future__ import annotations

import json
from backend.platform_sdk.ids import next_gid
from ..data.connection import get_integration_conn


class IntegrationRepository:
    def create_connector(self, data: dict) -> dict:
        gid = str(next_gid())
        values = (gid, data["name"], data["connector_type"], data["host"], data["port"], data["database_name"], data["username"], data["credential_ref"], data["owner_gid"], data.get("team_gid"))
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO workmanship_int_ext_datasources (gid,name,connector_type,host,port,database_name,username,credential_ref,owner_gid,team_gid) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", values)
            conn.commit()
        return {"gid": gid, "revision": 1, "status": "untested"}

    def update_connector(self, data: dict) -> dict:
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE workmanship_int_ext_datasources SET name=COALESCE(%s,name),credential_ref=COALESCE(%s,credential_ref),revision=revision+1 WHERE gid=%s AND revision=%s AND owner_gid=%s AND archived_at IS NULL", (data.get("name"), data.get("credential_ref"), data["gid"], data["expected_revision"], data["owner_gid"]))
                changed = cur.rowcount == 1
            conn.commit()
        return {"gid": data["gid"], "revision": data["expected_revision"] + 1, "changed": changed}

    def archive_connector(self, data: dict) -> dict:
        return self._archive("workmanship_int_ext_datasources", data)

    def search_connectors(self, data: dict) -> list[dict]:
        return self._search("workmanship_int_ext_datasources", data)

    def create_mapping(self, data: dict) -> dict:
        gid = str(next_gid())
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO workmanship_int_ext_mappings (gid,datasource_gid,name,source_object,target_domain,target_capability_id,target_major_version,minimum_catalog_release,field_mappings_json,owner_gid,team_gid) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (gid, data["datasource_gid"], data["name"], data["source_object"], data["target_domain"], data["target_capability_id"], data["target_major_version"], data["minimum_catalog_release"], json.dumps(data.get("field_mappings", [])), data["owner_gid"], data.get("team_gid")))
            conn.commit()
        return {"gid": gid, "revision": 1, "status": "active"}

    def get_mapping(self, data: dict) -> dict | None:
        rows = self._search("workmanship_int_ext_mappings", {**data, "gid": data["gid"], "limit": 1})
        return rows[0] if rows else None

    def update_mapping(self, data: dict) -> dict:
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE workmanship_int_ext_mappings SET field_mappings_json=COALESCE(%s,field_mappings_json),revision=revision+1 WHERE gid=%s AND revision=%s AND owner_gid=%s AND archived_at IS NULL", (json.dumps(data["field_mappings"]) if "field_mappings" in data else None, data["gid"], data["expected_revision"], data["owner_gid"]))
                changed = cur.rowcount == 1
            conn.commit()
        return {"gid": data["gid"], "revision": data["expected_revision"] + 1, "changed": changed}

    def archive_mapping(self, data: dict) -> dict:
        return self._archive("workmanship_int_ext_mappings", data)

    def search_mappings(self, data: dict) -> list[dict]:
        return self._search("workmanship_int_ext_mappings", data)

    def _archive(self, table: str, data: dict) -> dict:
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {table} SET archived_at=NOW(6),revision=revision+1 WHERE gid=%s AND revision=%s AND owner_gid=%s AND archived_at IS NULL", (data["gid"], data["expected_revision"], data["owner_gid"]))
                changed = cur.rowcount == 1
            conn.commit()
        return {"gid": data["gid"], "archived": changed}

    def _search(self, table: str, data: dict) -> list[dict]:
        clauses, params = ["owner_gid=%s", "archived_at IS NULL"], [data["owner_gid"]]
        if data.get("gid"):
            clauses.append("gid=%s"); params.append(data["gid"])
        with get_integration_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {table} WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT %s", (*params, min(int(data.get("limit", 100)), 200)))
                return [dict(row) for row in cur.fetchall()]
