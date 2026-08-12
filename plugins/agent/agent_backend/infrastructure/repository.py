from __future__ import annotations

import json
from backend.platform_sdk.ids import next_gid
from ..data.connection import get_agent_conn


class AgentCapabilityRepository:
    def read(self, data: dict) -> dict:
        with get_agent_conn() as conn:
            with conn.cursor() as cur:
                if data.get("resource_gid"):
                    cur.execute("SELECT resource_gid,resource_type,version,status,content_json FROM workmanship_agent_capability_resources WHERE resource_gid=%s AND tenant_gid=%s AND owner_gid=%s", (data["resource_gid"], data["tenant_gid"], data["owner_gid"]))
                    row = cur.fetchone()
                    return dict(row) if row else {"resource_gid": data["resource_gid"], "version": 0, "status": "not_found", "content": {}}
                cur.execute("SELECT resource_gid,resource_type,version,status,content_json FROM workmanship_agent_capability_resources WHERE resource_type=%s AND tenant_gid=%s AND owner_gid=%s ORDER BY updated_at DESC LIMIT %s", (data["resource_type"], data["tenant_gid"], data["owner_gid"], min(int(data.get("limit", 100)), 200)))
                return {"items": [dict(row) for row in cur.fetchall()]}

    def apply(self, data: dict) -> dict:
        gid = str(data.get("resource_gid") or next_gid())
        with get_agent_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO workmanship_agent_capability_resources (resource_gid,resource_type,tenant_gid,owner_gid,version,status,content_json) VALUES (%s,%s,%s,%s,1,%s,%s) ON DUPLICATE KEY UPDATE version=version+1,status=VALUES(status),content_json=VALUES(content_json)", (gid, data["resource_type"], data["tenant_gid"], data["owner_gid"], data.get("status", "active"), json.dumps(data.get("content", {}))))
            conn.commit()
        return {"resource_gid": gid, "version": int(data.get("expected_version", 0)) + 1, "status": data.get("status", "active")}

    def request_interaction(self, data: dict) -> dict:
        return {"interaction_id": str(next_gid()), "status": "requested"}
