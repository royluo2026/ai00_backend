"""Stable public query surface for Base composition adapters."""
from __future__ import annotations

import json

from backend.platform_sdk.ids import next_gid
from plugins.ontology.public import concept as get_ontology_concept
from plugins.ontology.public import concept_labels as get_ontology_concept_labels
from plugins.ontology.public import properties as get_ontology_properties
from .data.connection import get_conn


def list_rule_workbench_items(user_gid: str, list_gids: list[str] | None = None) -> list[dict]:
    clauses = ["owner_user_gid=%s", "status!='archived'"]
    params: list = [user_gid]
    if list_gids:
        clauses.append(f"list_gid IN ({','.join(['%s'] * len(list_gids))})")
        params.extend(list_gids)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 'rule' AS item_type,gid,name AS title,status,NULL AS priority,"
                "scheduled_date,NULL AS due_date,created_at,NULL AS project_name,owner_user_gid "
                f"FROM workmanship_know_craft_rules WHERE {' AND '.join(clauses)} "
                "ORDER BY COALESCE(scheduled_date,'9999-12-31') ASC LIMIT 200",
                params,
            )
            return [dict(row) for row in cur.fetchall()]


def ontology_class_labels(gids) -> dict[str, str]:
    return get_ontology_concept_labels(gids)


def ontology_class(gid: str) -> dict | None:
    return get_ontology_concept(gid)


def ontology_properties(gids) -> dict[str, dict]:
    return get_ontology_properties(gids)


def upsert_external_bop_entries(node_type: str, rows: list[dict], unique_field: str | None = None) -> dict:
    imported = updated = skipped = 0
    errors: list[str] = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            for fields in rows:
                try:
                    existing_gid = None
                    if unique_field == "vpps" and fields.get("vpps") is not None:
                        cur.execute("SELECT gid FROM workmanship_bop_bop_entries WHERE vpps=%s AND node_type=%s LIMIT 1", (str(fields["vpps"]), node_type))
                        found = cur.fetchone()
                        existing_gid = found["gid"] if found else None
                    values = {key: value for key, value in fields.items() if key != "node_type" and value is not None}
                    if "meta" in values:
                        values["meta"] = json.dumps(values["meta"], ensure_ascii=False)
                    if existing_gid:
                        if values:
                            sets = ", ".join(f"{key}=%s" for key in values) + ", updated_at=NOW()"
                            cur.execute(f"UPDATE workmanship_bop_bop_entries SET {sets} WHERE gid=%s", list(values.values()) + [existing_gid])
                        updated += 1
                    else:
                        cur.execute(
                            "INSERT INTO workmanship_bop_bop_entries(gid,node_type,title,vpps,seq_no,meta,ai00_level) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (str(next_gid()), node_type, fields.get("title", ""), fields.get("vpps", ""), fields.get("seq_no") or 0, values.get("meta", "{}"), 5),
                        )
                        imported += 1
                except Exception as exc:
                    errors.append(str(exc)); skipped += 1
        conn.commit()
    return {"imported": imported, "updated": updated, "skipped": skipped, "errors": errors[:10]}

__all__ = ["list_rule_workbench_items", "ontology_class", "ontology_class_labels", "ontology_properties", "upsert_external_bop_entries"]
