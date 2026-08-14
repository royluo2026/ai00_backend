"""Factory-owned persistence for topology, catalog entries and physical assets."""
from __future__ import annotations

import json

from backend.platform_sdk.ids import next_gid

from .connection import get_factory_conn


def _json(value) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _decode_json_fields(row: dict) -> dict:
    """Normalize OceanBase JSON columns before crossing the Provider boundary."""
    result = dict(row)
    for field in ("attributes", "specification", "meta"):
        value = result.get(field)
        if isinstance(value, str):
            result[field] = json.loads(value)
    return result


class FactoryRepository:
    def structure_create(self, data: dict) -> dict:
        gid = str(next_gid())
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_factory_structures "
                    "(gid,kind,name,parent_gid,tenant_gid,version,attributes) VALUES (%s,%s,%s,%s,%s,1,%s)",
                    (gid, data["kind"], data["name"], data.get("parent_gid"), data["tenant_gid"], _json(data.get("attributes"))),
                )
            conn.commit()
        return {"gid": gid, "version": 1}

    def structure_get(self, gid: str, tenant_gid: str) -> dict | None:
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_factory_structures WHERE gid=%s AND tenant_gid=%s", (gid, tenant_gid))
                row = cur.fetchone()
        return _decode_json_fields(row) if row else None

    def structure_search(self, data: dict) -> list[dict]:
        clauses, params = ["tenant_gid=%s", "archived=FALSE"], [data["tenant_gid"]]
        if data.get("kind"):
            clauses.append("kind=%s"); params.append(data["kind"])
        if data.get("parent_gid"):
            clauses.append("parent_gid=%s"); params.append(data["parent_gid"])
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM workmanship_factory_structures WHERE {' AND '.join(clauses)} ORDER BY name LIMIT %s", (*params, min(int(data.get("limit", 200)), 500)))
                return [_decode_json_fields(row) for row in cur.fetchall()]

    def structure_update(self, gid: str, expected_version: int, updates: dict, tenant_gid: str) -> dict | None:
        allowed = {key: value for key, value in updates.items() if key in {"name", "parent_gid", "attributes"}}
        if "attributes" in allowed:
            allowed["attributes"] = _json(allowed["attributes"])
        if not allowed:
            return self.structure_get(gid, tenant_gid)
        sets = ",".join(f"{key}=%s" for key in allowed)
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE workmanship_factory_structures SET {sets},version=version+1 WHERE gid=%s AND tenant_gid=%s AND version=%s AND archived=FALSE", (*allowed.values(), gid, tenant_gid, expected_version))
                if cur.rowcount != 1:
                    return None
            conn.commit()
        return self.structure_get(gid, tenant_gid)

    def structure_archive(self, gid: str, expected_version: int, tenant_gid: str) -> bool:
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE workmanship_factory_structures SET archived=TRUE,version=version+1 WHERE gid=%s AND tenant_gid=%s AND version=%s AND archived=FALSE", (gid, tenant_gid, expected_version))
                changed = cur.rowcount == 1
            conn.commit()
        return changed

    def catalog_get(self, gid: str, tenant_gid: str) -> dict | None:
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_factory_resource_catalog WHERE gid=%s AND tenant_gid=%s", (gid, tenant_gid)); row = cur.fetchone()
        return _decode_json_fields(row) if row else None

    def catalog_search(self, data: dict) -> list[dict]:
        clauses, params = ["tenant_gid=%s"], [data["tenant_gid"]]
        if data.get("resource_type"):
            clauses.append("resource_type=%s"); params.append(data["resource_type"])
        if data.get("status"):
            clauses.append("status=%s"); params.append(data["status"])
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM workmanship_factory_resource_catalog WHERE {' AND '.join(clauses)} ORDER BY name,revision DESC LIMIT %s", (*params, min(int(data.get("limit", 200)), 500)))
                return [_decode_json_fields(row) for row in cur.fetchall()]

    def catalog_create(self, data: dict) -> dict:
        gid = str(next_gid())
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO workmanship_factory_resource_catalog (gid,resource_type,name,revision,status,specification,tenant_gid) VALUES (%s,%s,%s,1,'draft',%s,%s)", (gid, data["resource_type"], data["name"], _json(data.get("specification")), data["tenant_gid"]))
            conn.commit()
        return {"gid": gid, "revision": 1, "status": "draft"}

    def catalog_revise(self, gid: str, expected_revision: int, data: dict, tenant_gid: str) -> dict | None:
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE workmanship_factory_resource_catalog SET name=COALESCE(%s,name),specification=COALESCE(%s,specification),revision=revision+1,status='draft' WHERE gid=%s AND tenant_gid=%s AND revision=%s", (data.get("name"), _json(data["specification"]) if "specification" in data else None, gid, tenant_gid, expected_revision))
                if cur.rowcount != 1: return None
            conn.commit()
        return self.catalog_get(gid, tenant_gid)

    def catalog_transition(self, gid: str, expected_revision: int, target: str, tenant_gid: str) -> bool:
        expected_status = "draft" if target == "published" else "published"
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE workmanship_factory_resource_catalog SET status=%s,revision=revision+1 WHERE gid=%s AND tenant_gid=%s AND revision=%s AND status=%s", (target, gid, tenant_gid, expected_revision, expected_status)); changed = cur.rowcount == 1
            conn.commit()
        return changed

    def asset_get(self, gid: str, tenant_gid: str) -> dict | None:
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM workmanship_factory_assets WHERE gid=%s AND tenant_gid=%s", (gid, tenant_gid)); row = cur.fetchone()
        return _decode_json_fields(row) if row else None

    def asset_search(self, data: dict) -> list[dict]:
        clauses, params = ["tenant_gid=%s"], [data["tenant_gid"]]
        for key in ("asset_type", "status", "catalog_gid"):
            if data.get(key): clauses.append(f"{key}=%s"); params.append(data[key])
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM workmanship_factory_assets WHERE {' AND '.join(clauses)} ORDER BY asset_no LIMIT %s", (*params, min(int(data.get("limit", 200)), 500)))
                return [_decode_json_fields(row) for row in cur.fetchall()]

    def asset_register(self, data: dict) -> dict:
        gid = str(next_gid())
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO workmanship_factory_assets (gid,asset_no,asset_type,catalog_gid,status,tenant_gid,version,meta) VALUES (%s,%s,%s,%s,'in_use',%s,1,%s)", (gid, data["asset_no"], data["asset_type"], data.get("catalog_gid"), data["tenant_gid"], _json(data.get("meta"))))
            conn.commit()
        return {"gid": gid, "version": 1, "status": "in_use"}

    def asset_update(self, gid: str, expected_version: int, data: dict, tenant_gid: str) -> dict | None:
        allowed = {key: value for key, value in data.items() if key in {"asset_no", "catalog_gid", "meta"}}
        if "meta" in allowed: allowed["meta"] = _json(allowed["meta"])
        if not allowed: return self.asset_get(gid, tenant_gid)
        sets = ",".join(f"{key}=%s" for key in allowed)
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE workmanship_factory_assets SET {sets},version=version+1 WHERE gid=%s AND tenant_gid=%s AND version=%s AND status!='scrapped'", (*allowed.values(), gid, tenant_gid, expected_version))
                if cur.rowcount != 1: return None
            conn.commit()
        return self.asset_get(gid, tenant_gid)

    def asset_transition(self, gid: str, expected_version: int, source: tuple[str, ...], target: str, tenant_gid: str) -> bool:
        placeholders = ",".join(["%s"] * len(source))
        with get_factory_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE workmanship_factory_assets SET status=%s,version=version+1 WHERE gid=%s AND tenant_gid=%s AND version=%s AND status IN ({placeholders})", (target, gid, tenant_gid, expected_version, *source)); changed = cur.rowcount == 1
            conn.commit()
        return changed
