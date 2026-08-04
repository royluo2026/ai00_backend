"""Stable public query surface for Base composition adapters."""
from __future__ import annotations

import json

from backend.platform_sdk.ids import next_gid
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


_FOLLOW_OWNER_FIELDS = {
    "project": ("workmanship_proj_projects", "owner_gid"),
    "std_op": ("workmanship_tpl_gbop_entries", "created_by"),
    "approval": ("workmanship_proj_approval_orders", "applicant_gid"),
}


def get_follow_item_owner(item_type: str, item_gid: str) -> str | None:
    """Resolve a Craft-owned item's owner without exposing Craft table names."""
    target = _FOLLOW_OWNER_FIELDS.get(item_type)
    if not target:
        return None
    table, column = target
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {column} FROM {table} WHERE gid=%s", (item_gid,))
            row = cur.fetchone()
    return str(row[column]) if row and row.get(column) else None


def append_item_history(item_type: str, item_gid: str, author_name: str, author_gid: str, content: str) -> dict:
    gid, entry_id = str(next_gid()), str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_work_item_entries "
                "(gid,id,item_type,item_gid,section,author,author_name,author_gid,content,sort_order,read_by_human,resolved,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,'history','human',%s,%s,%s,UNIX_TIMESTAMP(),TRUE,FALSE,NOW(),NOW())",
                (gid, entry_id, item_type, item_gid, author_name, author_gid, content),
            )
        conn.commit()
    return {"gid": gid, "id": entry_id}


def list_item_history(item_type: str, item_gid: str) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,id,author_name,content,created_at FROM workmanship_work_item_entries "
                "WHERE item_type=%s AND item_gid=%s AND section='history' ORDER BY created_at DESC",
                (item_type, item_gid),
            )
            return [dict(row) for row in cur.fetchall()]


def ontology_class_labels(gids) -> dict[str, str]:
    values = tuple(sorted({str(gid) for gid in gids if gid}))
    if not values:
        return {}
    placeholders = ",".join(["%s"] * len(values))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT gid,label_zh FROM workmanship_onto_classes WHERE gid IN ({placeholders})", values)
            return {str(row["gid"]): row.get("label_zh") for row in cur.fetchall()}


def ontology_class(gid: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid,label_zh,node_type_binding FROM workmanship_onto_classes WHERE gid=%s", (gid,))
            row = cur.fetchone()
    return dict(row) if row else None


def ontology_properties(gids) -> dict[str, dict]:
    values = tuple(sorted({str(gid) for gid in gids if gid}))
    if not values:
        return {}
    placeholders = ",".join(["%s"] * len(values))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT gid,name,label_zh,storage_hint FROM workmanship_onto_properties WHERE gid IN ({placeholders})", values)
            return {str(row["gid"]): dict(row) for row in cur.fetchall()}


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

__all__ = ["append_item_history", "get_follow_item_owner", "list_item_history", "list_rule_workbench_items", "ontology_class", "ontology_class_labels", "ontology_properties", "upsert_external_bop_entries"]
