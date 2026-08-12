from __future__ import annotations

import json

from ..data.connection import get_knowledge_conn
from ..ids import new_knowledge_id


class ReferenceDataRepository:
    def publish(self, dataset_gid, expected_version, schema, rows, actor_gid, tenant_gid):
        version_gid = new_knowledge_id("revision")
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_version FROM workmanship_know_reference_datasets WHERE gid=%s AND tenant_gid=%s FOR UPDATE", (dataset_gid, tenant_gid)); current = cur.fetchone()
                if not current or int(current["current_version"]) != int(expected_version): raise ValueError("reference dataset version conflict")
                version_no = int(expected_version) + 1
                cur.execute("INSERT INTO workmanship_know_reference_versions (gid,dataset_gid,version_no,schema_json,rows_json,created_by) VALUES (%s,%s,%s,%s,%s,%s)", (version_gid, dataset_gid, version_no, json.dumps(schema, ensure_ascii=False), json.dumps(rows, ensure_ascii=False), actor_gid))
                cur.execute("UPDATE workmanship_know_reference_datasets SET current_version=%s,published_version_gid=%s,updated_at=NOW() WHERE gid=%s AND tenant_gid=%s AND current_version=%s", (version_no, version_gid, dataset_gid, tenant_gid, expected_version))
                cur.execute("INSERT INTO workmanship_know_domain_outbox (gid,event_type,event_version,subject_ref,payload,status) VALUES (%s,'knowledge.reference_data.published.v1',1,%s,%s,'pending')", (new_knowledge_id("outbox"), dataset_gid, json.dumps({"dataset_ref": f"knowledge-reference-dataset:{dataset_gid}", "dataset_version_ref": f"knowledge-reference-version:{version_gid}"}, ensure_ascii=False)))
            conn.commit()
        return {"dataset_gid": dataset_gid, "version_gid": version_gid, "version_no": version_no, "immutable": True}

    def lookup(self, dataset_gid, version_gid, keys, tenant_gid):
        with get_knowledge_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT v.rows_json FROM workmanship_know_reference_versions v JOIN workmanship_know_reference_datasets d ON d.gid=v.dataset_gid WHERE v.dataset_gid=%s AND v.gid=%s AND d.tenant_gid=%s", (dataset_gid, version_gid, tenant_gid)); row = cur.fetchone()
        if not row: raise LookupError("reference dataset version not found")
        values = row["rows_json"] if isinstance(row["rows_json"], list) else json.loads(row["rows_json"])
        wanted = set(keys)
        return [item for item in values if str(item.get("key")) in wanted]

