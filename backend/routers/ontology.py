"""
backend/routers/ontology.py
────────────────────────────
本体编辑器 CRUD API。

端点：
  GET    /api/ontology/classes              — 树形结构
  POST   /api/ontology/classes              — 创建类
  PATCH  /api/ontology/classes/{gid}        — 更新类（含 entity_table）
  DELETE /api/ontology/classes/{gid}        — 删除类
  GET    /api/ontology/classes/{gid}/full   — 类 + 属性 + 关系 + 公理 + 规则
  POST   /api/ontology/properties           — 创建属性
  PATCH  /api/ontology/properties/{gid}     — 更新属性
  DELETE /api/ontology/properties/{gid}     — 删除属性
  POST   /api/ontology/properties/{gid}/promote — ext → 实列升级
  POST   /api/ontology/relations            — 创建关系
  DELETE /api/ontology/relations/{gid}      — 删除关系
  POST   /api/ontology/axioms               — 创建公理
  DELETE /api/ontology/axioms/{gid}         — 删除公理
  GET    /api/ontology/schema/{node_type}   — Agent 用结构化 schema
  POST   /api/ontology/seed                 — 从 BOP node_types 预填（幂等）
  GET    /api/ontology/graph                — 全量图谱（节点+边）
  GET    /api/bop/entries/{gid}/entity-props  — 读实体属性（固定列+ext）
  PATCH  /api/bop/entries/{gid}/entity-props  — 写实体属性（自动路由固定列/ext）
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.db.pg_to_mysql_migrate import TABLE_MAP as _TABLE_MAP
from backend.routers.deps import get_current_user
from backend.utils.gid import next_gid


def _pg_entity_table_to_mysql(pg_table: str) -> str:
    """将 PG schema.tablename 转换为 MySQL 实际表名（用于 information_schema 查询）。"""
    return _TABLE_MAP.get(pg_table) or pg_table.split(".")[-1]

router = APIRouter(tags=["ontology"])
_log = logging.getLogger(__name__)

_ntc_cache: dict | None = None

def _invalidate_ntc_cache():
    global _ntc_cache
    _ntc_cache = None


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _gid() -> str:
    return str(next_gid())


def _cls_row(r: dict) -> dict:
    return {
        "gid":               r["gid"],
        "name":              r["name"],
        "label_zh":          r["label_zh"],
        "label_en":          r["label_en"],
        "parent_gid":        r["parent_gid"],
        "node_type_binding": r["node_type_binding"],
        "is_abstract":       r["is_abstract"],
        "color":             r["color"],
        "icon":              r["icon"],
        "description":       r["description"],
        "sort_order":        r["sort_order"],
        "entity_table":      r.get("entity_table"),
        "abbr":              r.get("abbr"),
        "ai00_level":        r.get("ai00_level"),
        "display_layer":     r.get("display_layer"),
        "stats_priority":    r.get("stats_priority", 99),
        "is_hidden_in_layout":   r.get("is_hidden_in_layout", False),
        "suggested_child_type":  r.get("suggested_child_type"),
        "created_at":        str(r["created_at"]),
        "updated_at":        str(r["updated_at"]),
    }


def _prop_row(r: dict) -> dict:
    return {
        "gid":              r["gid"],
        "class_gid":        r["class_gid"],
        "name":             r["name"],
        "label_zh":         r["label_zh"],
        "prop_kind":        r["prop_kind"],
        "data_type":        r["data_type"],
        "range_class_gid":  r["range_class_gid"],
        "enum_values":      r["enum_values"] or [],
        "required":         r["required"],
        "min_val":          r["min_val"],
        "max_val":          r["max_val"],
        "description":      r["description"],
        "sort_order":       r["sort_order"],
        "storage_hint":     r.get("storage_hint") or "meta",
        "mapped_column":    r.get("mapped_column"),
        "field_config":     r.get("field_config") or {},
        "show_in_detail":   bool(r["show_in_detail"]) if r.get("show_in_detail") is not None else True,
        "detail_order":     r.get("detail_order", 99),
    }


def _build_tree(rows: list[dict]) -> list[dict]:
    """将平铺的类列表组装成嵌套 children 树。"""
    by_gid = {r["gid"]: {**r, "children": []} for r in rows}
    roots: list[dict] = []
    for r in by_gid.values():
        parent = r.get("parent_gid")
        if parent and parent in by_gid:
            by_gid[parent]["children"].append(r)
        else:
            roots.append(r)
    return roots


# ── 类 CRUD ────────────────────────────────────────────────────────────────────

@router.get("/api/ontology/classes")
def list_classes(_u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_onto_classes ORDER BY sort_order, label_zh"
            )
            rows = [_cls_row(dict(r)) for r in cur.fetchall()]
    return {"data": _build_tree(rows)}


class ClassBody(BaseModel):
    name: str
    label_zh: str = ""
    label_en: str = ""
    parent_gid: Optional[str] = None
    node_type_binding: Optional[str] = None
    is_abstract: bool = False
    color: Optional[str] = None
    icon: Optional[str] = None
    description: str = ""
    sort_order: int = 0
    entity_table: Optional[str] = None


@router.post("/api/ontology/classes", status_code=201)
def create_class(body: ClassBody, _u=Depends(get_current_user)):
    gid = _gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_onto_classes"
                "(gid, name, label_zh, label_en, parent_gid, node_type_binding,"
                " is_abstract, color, icon, description, sort_order, entity_table)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.name, body.label_zh, body.label_en, body.parent_gid,
                 body.node_type_binding, body.is_abstract, body.color, body.icon,
                 body.description, body.sort_order, body.entity_table),
            )
            conn.commit()
            cur.execute("SELECT * FROM workmanship_onto_classes WHERE gid = %s", (gid,))
            row = cur.fetchone()
    return {"data": _cls_row(dict(row))}


_CLS_UPDATABLE = ("name", "label_zh", "label_en", "parent_gid", "node_type_binding",
                  "is_abstract", "color", "icon", "description", "sort_order", "entity_table",
                  "abbr", "ai00_level", "display_layer", "stats_priority",
                  "is_hidden_in_layout", "suggested_child_type")


@router.patch("/api/ontology/classes/{gid}")
def update_class(gid: str, body: dict, _u=Depends(get_current_user)):
    data = {k: v for k, v in body.items() if k in _CLS_UPDATABLE}
    if not data:
        raise HTTPException(400, "无可更新字段")
    sets = ", ".join(f"{k}=%s" for k in data)
    vals = list(data.values()) + [gid]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_onto_classes SET {sets}, updated_at=NOW() WHERE gid=%s",
                vals,
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "类不存在")
            conn.commit()
            _invalidate_ntc_cache()
            cur.execute("SELECT * FROM workmanship_onto_classes WHERE gid = %s", (gid,))
            row = cur.fetchone()
    return {"data": _cls_row(dict(row))}


@router.delete("/api/ontology/classes/{gid}", status_code=204)
def delete_class(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM workmanship_onto_classes WHERE parent_gid = %s",
                (gid,),
            )
            if cur.fetchone()["cnt"] > 0:
                raise HTTPException(400, "请先删除所有子类")
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM workmanship_know_craft_rules WHERE context_class_gid = %s",
                (gid,),
            )
            if cur.fetchone()["cnt"] > 0:
                raise HTTPException(400, "该类仍有关联规则，请先解除绑定")
            cur.execute("DELETE FROM workmanship_onto_classes WHERE gid = %s", (gid,))
            conn.commit()
            _invalidate_ntc_cache()


# ── 类详情（含属性/关系/公理/规则）────────────────────────────────────────────

@router.get("/api/ontology/classes/{gid}/full")
def get_class_full(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_onto_classes WHERE gid = %s", (gid,))
            cls_row = cur.fetchone()
            if not cls_row:
                raise HTTPException(404, "类不存在")

            cur.execute(
                "SELECT * FROM workmanship_onto_properties WHERE class_gid = %s ORDER BY sort_order",
                (gid,),
            )
            props = [_prop_row(dict(r)) for r in cur.fetchall()]

            cur.execute(
                "SELECT * FROM workmanship_onto_relations"
                " WHERE domain_class_gid = %s"
                " ORDER BY sort_order, label_zh",
                (gid,),
            )
            relations = [
                {
                    **dict(r),
                    "show_in_detail": bool(r["show_in_detail"]) if r.get("show_in_detail") is not None else True,
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                "SELECT * FROM workmanship_onto_axioms WHERE class_gid = %s",
                (gid,),
            )
            axioms = [dict(r) for r in cur.fetchall()]

            cur.execute(
                "SELECT gid, name, code, expression, enforcement_level, status"
                " FROM workmanship_know_craft_rules"
                " WHERE context_class_gid = %s ORDER BY created_at",
                (gid,),
            )
            rules = [dict(r) for r in cur.fetchall()]

    return {
        "data": {
            **_cls_row(dict(cls_row)),
            "properties": props,
            "relations":  relations,
            "axioms":     axioms,
            "rules":      rules,
        }
    }


# ── 属性 CRUD ─────────────────────────────────────────────────────────────────

class PropBody(BaseModel):
    class_gid: str
    name: str
    label_zh: str = ""
    prop_kind: str = "data"
    data_type: Optional[str] = None
    range_class_gid: Optional[str] = None
    enum_values: list = []
    required: bool = False
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    description: str = ""
    sort_order: int = 0
    storage_hint: Optional[str] = None  # None = 由后端根据 class.entity_table 自动决定
    mapped_column: Optional[str] = None  # DB 列名；None 表示与 name 相同
    field_config: dict = {}    # 派生属性聚合规则：{"aggregate":"SUM","child_node_type":"operation","child_property":"vd_time"}
    show_in_detail: bool = True
    detail_order:   int  = 99


@router.post("/api/ontology/properties", status_code=201)
def create_property(body: PropBody, _u=Depends(get_current_user)):
    import json
    gid = _gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 自动推断 storage_hint：class 有 entity_table → entity_table，否则 meta
            if body.storage_hint is not None:
                storage_hint = body.storage_hint
            else:
                cur.execute(
                    "SELECT entity_table FROM workmanship_onto_classes WHERE gid=%s",
                    (body.class_gid,),
                )
                cls_row = cur.fetchone()
                storage_hint = "entity_table" if (cls_row and cls_row["entity_table"]) else "meta"

            cur.execute(
                "INSERT INTO workmanship_onto_properties"
                "(gid, class_gid, name, label_zh, prop_kind, data_type, range_class_gid,"
                " enum_values, required, min_val, max_val, description, sort_order,"
                " storage_hint, mapped_column, field_config, show_in_detail, detail_order)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.class_gid, body.name, body.label_zh, body.prop_kind,
                 body.data_type, body.range_class_gid,
                 json.dumps(body.enum_values),
                 body.required, body.min_val, body.max_val, body.description, body.sort_order,
                 storage_hint, body.mapped_column, json.dumps(body.field_config),
                 body.show_in_detail, body.detail_order),
            )
            conn.commit()
            cur.execute("SELECT * FROM workmanship_onto_properties WHERE gid = %s", (gid,))
            row = cur.fetchone()
    return {"data": _prop_row(dict(row))}


_PROP_UPDATABLE = ("name", "label_zh", "prop_kind", "data_type", "range_class_gid",
                   "enum_values", "required", "min_val", "max_val", "description",
                   "sort_order", "storage_hint", "mapped_column", "field_config",
                   "show_in_detail", "detail_order")


@router.patch("/api/ontology/properties/{gid}")
def update_property(gid: str, body: dict, _u=Depends(get_current_user)):
    import json
    data = {k: v for k, v in body.items() if k in _PROP_UPDATABLE}
    if not data:
        raise HTTPException(400, "无可更新字段")
    if "enum_values" in data:
        data["enum_values"] = json.dumps(data["enum_values"]) + ""
    set_parts, vals = [], []
    if "field_config" in data:
        set_parts.append("field_config=%s")
        vals.append(json.dumps(body.get("field_config", {})))
        del data["field_config"]
    for k, v in data.items():
        if k == "enum_values":
            set_parts.append("enum_values=%s")
            vals.append(json.dumps(body["enum_values"]))
        else:
            set_parts.append(f"{k}=%s")
            vals.append(v)
    vals.append(gid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_onto_properties SET {', '.join(set_parts)}, updated_at=NOW() WHERE gid=%s",
                vals,
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "属性不存在")
            conn.commit()
            _invalidate_ntc_cache()
            cur.execute("SELECT * FROM workmanship_onto_properties WHERE gid = %s", (gid,))
            row = cur.fetchone()
    return {"data": _prop_row(dict(row))}


@router.delete("/api/ontology/properties/{gid}", status_code=204)
def delete_property(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_onto_properties WHERE gid = %s", (gid,))
            conn.commit()


# 已知基础设施列，不导入本体
_INFRA_COLS = frozenset({
    'gid', 'id', 'created_at', 'updated_at', 'deleted_at', 'is_deleted',
    'created_by', 'updated_by', 'sort_order', 'meta', 'ext',
    'project_gid', 'version_gid', 'bop_version_gid', 'parent_version_gid',
    'vpps', 'vpps_desc', 'parent_gid', 'parent_bop_gid', 'parent_bop_label',
    'archived_at', 'frozen_at', 'published_at', 'seq_no', 'ai00_level',
    'is_inherited', 'is_deleted', 'node_type', 'title', 'level',
    'bom_row_id', 'bom_row_label', 'bom_row_owner',
})

_PG_TO_ONTO_TYPE = {
    'text': 'string', 'character varying': 'string', 'varchar': 'string',
    'integer': 'integer', 'bigint': 'integer', 'smallint': 'integer',
    'real': 'float', 'double precision': 'float', 'numeric': 'float',
    'boolean': 'boolean', 'date': 'date',
}


@router.get("/api/ontology/db-tables", status_code=200)
def list_db_tables(_u=Depends(get_current_user)):
    """返回数据库中所有业务表（ai00 库），供 entity_table 绑定选择。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TABLE_NAME AS table_name
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = 'ai00'
                  AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
            tables = [r['table_name'] for r in cur.fetchall()]
    return {"data": tables}


@router.get("/api/ontology/node-type-suggestions", status_code=200)
def list_node_type_suggestions(_u=Depends(get_current_user)):
    """返回 node_type_binding 候选值：bop_entries 已有的 node_type + onto_classes 已有的绑定。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 已用绑定
            cur.execute("SELECT DISTINCT node_type_binding FROM workmanship_onto_classes"
                        " WHERE node_type_binding IS NOT NULL ORDER BY node_type_binding")
            existing = [r["node_type_binding"] for r in cur.fetchall()]
            # bop_entries 实际值（可能有尚未进本体的类型）
            bop_types = []
            try:
                cur.execute("SELECT DISTINCT node_type FROM workmanship_bop_bop_entries"
                            " WHERE node_type IS NOT NULL ORDER BY node_type")
                bop_types = [r["node_type"] for r in cur.fetchall()]
            except Exception:
                pass
    # 合并去重，已绑定的排前面
    seen = set(existing)
    suggestions = existing + [t for t in bop_types if t not in seen]
    return {"data": suggestions}


@router.get("/api/ontology/unbound-classes", status_code=200)
def list_unbound_classes(_u=Depends(get_current_user)):
    """返回有 node_type_binding 但未绑定 entity_table 的类（最可能需要绑定）。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gid, name, label_zh, node_type_binding, entity_table
                FROM workmanship_onto_classes
                WHERE node_type_binding IS NOT NULL
                   OR entity_table IS NULL
                ORDER BY sort_order, name
            """)
            rows = [dict(r) for r in cur.fetchall()]
    return {"data": rows}


@router.get("/api/ontology/classes/{gid}/individuals", status_code=200)
def list_class_individuals(gid: str, limit: int = 20, _u=Depends(get_current_user)):
    """
    返回该类的样本实例：
    - 有 entity_table → 直接查对应表（LIMIT limit），返回 gid/title/name 等主标识列
    - 无 entity_table 但有 node_type_binding → 查 workmanship_bop_bop_entries
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT entity_table, node_type_binding"
                " FROM workmanship_onto_classes WHERE gid=%s", (gid,)
            )
            cls_row = cur.fetchone()
            if not cls_row:
                raise HTTPException(404, "类不存在")
            entity_table    = cls_row["entity_table"]
            node_type_binding = cls_row["node_type_binding"]

            rows = []
            source = None

            if entity_table:
                # 查实体表：尝试常见的标识列
                table_part = entity_table.split(".", 1)[-1]
                cur.execute("""
                    SELECT COLUMN_NAME AS column_name FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA='ai00' AND TABLE_NAME=%s
                """, (table_part,))
                cols = {r["column_name"] for r in cur.fetchall()}

                # 选取最有意义的展示列
                display_cols = ["gid"]
                for c in ["title", "name", "display_id", "label_zh", "code",
                          "asset_no", "vpps", "status"]:
                    if c in cols:
                        display_cols.append(c)
                        if len(display_cols) >= 5:
                            break

                # 过滤软删除（若有相关列）
                where = ""
                if "is_deleted" in cols:
                    where = "WHERE is_deleted = FALSE"
                elif "deleted_at" in cols:
                    where = "WHERE deleted_at IS NULL"

                select_sql = ", ".join(f'"{c}"' for c in display_cols)
                cur.execute(
                    f"SELECT {select_sql} FROM {entity_table} {where}"
                    f" ORDER BY gid DESC LIMIT %s",
                    (limit,)
                )
                rows = [dict(r) for r in cur.fetchall()]
                source = "entity_table"

            elif node_type_binding:
                # fallback：BOP entries
                cur.execute(
                    "SELECT e.gid, e.title, e.node_type, v.version_tag"
                    " FROM workmanship_bop_bop_entries e"
                    " LEFT JOIN workmanship_bop_bop_versions v ON v.gid = e.version_gid"
                    " WHERE e.node_type=%s AND e.deleted_at IS NULL"
                    " ORDER BY e.created_at DESC LIMIT %s",
                    (node_type_binding, limit)
                )
                rows = [dict(r) for r in cur.fetchall()]
                source = "bop_entries"

    return {"data": rows, "source": source,
            "entity_table": entity_table, "node_type_binding": node_type_binding}


@router.post("/api/ontology/classes/{gid}/sync-from-table", status_code=200)
def sync_props_from_table(gid: str, _u=Depends(get_current_user)):
    """
    扫描 onto_classes.entity_table 对应的 DB 表，将尚未在 onto_properties 中的列
    批量导入为属性（跳过基础设施列）。幂等：已存在的列不重复创建。
    """
    import json as _json
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT entity_table FROM workmanship_onto_classes WHERE gid=%s", (gid,)
            )
            cls_row = cur.fetchone()
            if not cls_row:
                raise HTTPException(404, "类不存在")
            entity_table = cls_row["entity_table"]
            if not entity_table:
                raise HTTPException(400, "该类未绑定实体表，请先设置 entity_table")

            # MySQL: entity_table 是完整表名（无 schema 前缀）
            # 兼容旧的 schema.table 格式
            if "." in entity_table:
                _, table_part = entity_table.split(".", 1)
            else:
                table_part = entity_table

            # 查实体表所有列（MySQL 用数据库名 ai00，用别名强制小写列名）
            cur.execute("""
                SELECT COLUMN_NAME AS column_name,
                       DATA_TYPE   AS data_type,
                       IS_NULLABLE AS is_nullable
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = 'ai00' AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """, (table_part,))
            db_cols = {r["column_name"]: dict(r) for r in cur.fetchall()}

            # 查已有属性的 mapped_column 和 name
            cur.execute(
                "SELECT name, COALESCE(mapped_column, name) AS db_key"
                " FROM workmanship_onto_properties WHERE class_gid=%s",
                (gid,)
            )
            existing_keys = set()
            for r in cur.fetchall():
                existing_keys.add(r["name"])
                existing_keys.add(r["db_key"])

            added = []
            skipped_infra = []
            skipped_exists = []

            for col_name, col_info in db_cols.items():
                if col_name in _INFRA_COLS:
                    skipped_infra.append(col_name)
                    continue
                if col_name in existing_keys:
                    skipped_exists.append(col_name)
                    continue

                pg_type = col_info["data_type"]
                onto_type = _PG_TO_ONTO_TYPE.get(pg_type, "string")
                new_gid = _gid()
                cur.execute(
                    "INSERT INTO workmanship_onto_properties"
                    "(gid, class_gid, name, label_zh, prop_kind, data_type,"
                    " required, sort_order, storage_hint, mapped_column,"
                    " field_config, show_in_detail, detail_order)"
                    " VALUES (%s,%s,%s,%s,'data',%s,%s,%s,'entity_table',%s,%s,%s,%s)"
                    "",
                    (new_gid, gid, col_name, col_name, onto_type,
                     col_info["is_nullable"] == "NO",
                     (len(added) + 1) * 10,
                     col_name, _json.dumps({}), True, 99)
                )
                added.append(col_name)

            # ── FK 约束扫描（MySQL 不支持 constraint_column_usage，跳过）──
            fk_rows = []

            # 已有关系：按 (domain_class_gid, name) 去重
            cur.execute(
                "SELECT name FROM workmanship_onto_relations WHERE domain_class_gid=%s",
                (gid,)
            )
            existing_rel_names = {r["name"] for r in cur.fetchall()}

            added_rels = []
            for fk in fk_rows:
                ref_full = f"{fk['ref_schema']}.{fk['ref_table']}"
                col = fk["column_name"]
                rel_name = col  # 用列名作为关系名

                if rel_name in existing_rel_names:
                    continue

                # 查引用表是否有对应的 onto_class
                cur.execute(
                    "SELECT gid, label_zh, name FROM workmanship_onto_classes"
                    " WHERE entity_table=%s LIMIT 1",
                    (ref_full,)
                )
                range_cls = cur.fetchone()
                if not range_cls:
                    continue  # 引用表没有对应本体类，跳过

                range_cls = dict(range_cls)
                label_zh = f"→{range_cls['label_zh'] or range_cls['name']}"
                cur.execute(
                    "INSERT INTO workmanship_onto_relations"
                    "(gid, name, label_zh, domain_class_gid, range_class_gid,"
                    " is_functional, description, sort_order)"
                    " VALUES (%s,%s,%s,%s,%s,TRUE,%s,%s)"
                    "",
                    (_gid(), rel_name, label_zh, gid, range_cls["gid"],
                     f"FK: {entity_table}.{col} → {ref_full}",
                     (len(added_rels) + 1) * 10)
                )
                added_rels.append(rel_name)
                existing_rel_names.add(rel_name)

            # ── 扫描 ext / meta JSONB 列中实际使用的 key，导入为属性 ──────────────
            # ext 存在实体表里 → storage_hint='entity_table'（entity-props API 会读 ext）
            # meta 存在 bop_entries.meta → storage_hint='meta'
            _JSONB_COLS = {'ext': 'entity_table', 'meta': 'meta'}
            for jsonb_col, hint in _JSONB_COLS.items():
                if jsonb_col not in db_cols:
                    continue
                try:
                    cur.execute(
                        f"SELECT DISTINCT k.k AS k"
                        f" FROM {entity_table},"
                        f" JSON_TABLE({jsonb_col}, '$.*' COLUMNS(k VARCHAR(255) PATH '$')) AS k"
                        f" WHERE {jsonb_col} IS NOT NULL AND {jsonb_col} != %s",
                        ('{}',)
                    )
                    jsonb_keys = [r["k"] for r in cur.fetchall()]
                except Exception:
                    jsonb_keys = []

                for key in jsonb_keys:
                    if key in _INFRA_COLS:
                        continue
                    if key in existing_keys:
                        # 已存在：若 storage_hint 不对，顺手修正
                        cur.execute(
                            "UPDATE workmanship_onto_properties SET storage_hint=%s"
                            " WHERE class_gid=%s AND name=%s AND storage_hint!=%s",
                            (hint, gid, key, hint)
                        )
                        continue
                    cur.execute(
                        "INSERT INTO workmanship_onto_properties"
                        "(gid, class_gid, name, label_zh, prop_kind, data_type,"
                        " required, sort_order, storage_hint, mapped_column,"
                        " field_config, show_in_detail, detail_order)"
                        " VALUES (%s,%s,%s,%s,'data','string',FALSE,%s,%s,%s,%s,TRUE,99)"
                        "",
                        (_gid(), gid, key, key,
                         (len(added) + 1) * 10,
                         hint, key, _json.dumps({}))
                    )
                    added.append(f"{jsonb_col}.{key}")
                    existing_keys.add(key)

            conn.commit()
            _invalidate_ntc_cache()

    return {
        "added":          added,
        "skipped_infra":  skipped_infra,
        "skipped_exists": skipped_exists,
        "total_added":    len(added),
        "added_relations": added_rels,
    }


# ── 关系 CRUD ─────────────────────────────────────────────────────────────────

class RelBody(BaseModel):
    name: str
    label_zh: str = ""
    domain_class_gid: Optional[str] = None
    range_class_gid: Optional[str] = None
    is_functional: bool = False
    inverse_of_gid: Optional[str] = None
    description: str = ""
    sort_order: int = 0
    show_in_detail: bool = True


@router.post("/api/ontology/relations", status_code=201)
def create_relation(body: RelBody, _u=Depends(get_current_user)):
    gid = _gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_onto_relations"
                "(gid, name, label_zh, domain_class_gid, range_class_gid,"
                " is_functional, inverse_of_gid, description, sort_order, show_in_detail)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.name, body.label_zh, body.domain_class_gid, body.range_class_gid,
                 body.is_functional, body.inverse_of_gid, body.description, body.sort_order,
                 body.show_in_detail),
            )
            conn.commit()
    return {"data": {"gid": gid}}


@router.delete("/api/ontology/relations/{gid}", status_code=204)
def delete_relation(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_onto_relations WHERE gid = %s", (gid,))
            conn.commit()


@router.patch("/api/ontology/relations/{gid}", status_code=200)
def update_relation(gid: str, body: dict, _u=Depends(get_current_user)):
    allowed = {"name", "label_zh", "range_class_gid", "is_functional",
               "inverse_of_gid", "description", "link_type_binding",
               "deep_copy_on_fork", "shared_on_fork", "skip_on_fork",
               "snapshot_on_freeze", "sort_order", "show_in_detail"}
    data = {k: v for k, v in body.items() if k in allowed}
    if not data:
        raise HTTPException(400, "无可更新字段")
    sets = ", ".join(f"{k}=%s" for k in data)
    vals = list(data.values()) + [gid]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM workmanship_onto_relations WHERE gid=%s LIMIT 1",
                (gid,),
            )
            if not cur.fetchone():
                raise HTTPException(404, "关系不存在")
            cur.execute(
                f"UPDATE workmanship_onto_relations SET {sets} WHERE gid=%s",
                vals,
            )
            conn.commit()
    return {"ok": True}


# ── 公理 CRUD ─────────────────────────────────────────────────────────────────

class AxiomBody(BaseModel):
    class_gid: str
    axiom_type: str
    target_gid: Optional[str] = None
    expression: Optional[str] = None
    description: str = ""


@router.post("/api/ontology/axioms", status_code=201)
def create_axiom(body: AxiomBody, _u=Depends(get_current_user)):
    gid = _gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_onto_axioms"
                "(gid, class_gid, axiom_type, target_gid, expression, description)"
                " VALUES (%s,%s,%s,%s,%s,%s)",
                (gid, body.class_gid, body.axiom_type, body.target_gid,
                 body.expression, body.description),
            )
            conn.commit()
    return {"data": {"gid": gid}}


@router.delete("/api/ontology/axioms/{gid}", status_code=204)
def delete_axiom(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_onto_axioms WHERE gid = %s", (gid,))
            conn.commit()


# ── Agent 结构化 schema ────────────────────────────────────────────────────────

@router.get("/api/ontology/schema/{node_type}")
def get_class_schema(node_type: str, _u=Depends(get_current_user)):
    """返回 Agent 可用的结构化 schema：类定义 + 属性 + 祖先链上的规则。"""
    from backend.rule_engine.graph import get_ancestor_gids

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_onto_classes WHERE node_type_binding = %s LIMIT 1",
                (node_type,),
            )
            cls_row = cur.fetchone()
            if not cls_row:
                raise HTTPException(404, f"未找到绑定 node_type='{node_type}' 的本体类")

            cur.execute("SELECT gid, parent_gid FROM workmanship_onto_classes")
            class_map = {r["gid"]: dict(r) for r in cur.fetchall()}
            ancestor_gids = get_ancestor_gids(cls_row["gid"], class_map)

            # 属性（含继承）
            _ph = ",".join(["%s"] * len(ancestor_gids))
            cur.execute(
                f"SELECT p.*, c.label_zh AS class_label FROM workmanship_onto_properties p"
                f" JOIN workmanship_onto_classes c ON c.gid = p.class_gid"
                f" WHERE p.class_gid IN ({_ph}) ORDER BY p.sort_order",
                ancestor_gids,
            )
            props = [_prop_row(dict(r)) for r in cur.fetchall()]

            # 规则（含继承）
            cur.execute(
                f"SELECT gid, name, expression, enforcement_level"
                f" FROM workmanship_know_craft_rules"
                f" WHERE context_class_gid IN ({_ph})"
                f"   AND expression IS NOT NULL AND status = 'active'",
                ancestor_gids,
            )
            rules = [dict(r) for r in cur.fetchall()]

            # 关系（含继承，按 domain_class_gid）
            cur.execute(
                f"""SELECT r.gid, r.name, r.label_zh, r.link_type_binding,
                          r.is_functional, r.description, r.sort_order,
                          COALESCE(r.show_in_detail, TRUE) AS show_in_detail,
                          rc.node_type_binding AS range_node_type,
                          rc.label_zh          AS range_label
                   FROM workmanship_onto_relations r
                   LEFT JOIN workmanship_onto_classes rc ON rc.gid = r.range_class_gid
                   WHERE r.domain_class_gid IN ({_ph})
                   ORDER BY r.sort_order, r.label_zh""",
                ancestor_gids,
            )
            relations = [
                {
                    **dict(r),
                    "show_in_detail": bool(r["show_in_detail"]) if r.get("show_in_detail") is not None else True,
                }
                for r in cur.fetchall()
            ]

    return {
        "node_type":  node_type,
        "class":      _cls_row(dict(cls_row)),
        "properties": props,
        "rules":      rules,
        "relations":  relations,
    }


# ── Seed ──────────────────────────────────────────────────────────────────────

# (name, label_zh, parent_name, node_type_binding, is_abstract, sort_order, color, entity_table)
_SEED_CLASSES = [
    # ── 工艺过程层级 ─────────────────────────────────────────────────────────
    ("ProcessEntity",       "工艺实体",   None,                None,                  True,  0,  "#3b82f6", None),
    ("line_process",        "线体工艺",   "ProcessEntity",     "line_process",        False, 1,  "#60a5fa", "workmanship_bop_bop_line"),
    ("station_process",     "工位工艺",   "ProcessEntity",     "station_process",     False, 2,  "#60a5fa", "workmanship_bop_bop_station"),
    ("operator_process",    "岗位工艺",   "ProcessEntity",     "operator_process",    False, 3,  "#60a5fa", "workmanship_bop_bop_operator"),
    ("process",             "工序",       "ProcessEntity",     "process",             False, 4,  "#93c5fd", "workmanship_bop_bop_process"),
    ("operation",           "操作/工步",  "ProcessEntity",     "operation",           False, 5,  "#bfdbfe", "workmanship_bop_bop_steps"),

    # ── 物理资源（工厂现有实物）────────────────────────────────────────────────
    ("ResourceEntity",      "物理资源",   None,                None,                  True,  10, "#8b5cf6", None),
    ("station_factory",     "实物工位",   "ResourceEntity",    "station_factory",     False, 11, "#a78bfa", "workmanship_factory_factory_stations"),
    ("equipment_factory",   "实物设备",   "ResourceEntity",    "equipment_factory",   False, 12, "#a78bfa", "workmanship_factory_factory_equipments"),
    ("tool_factory",        "实物工具",   "ResourceEntity",    "tool_factory",        False, 13, "#a78bfa", "workmanship_factory_factory_tools"),
    ("fixture_factory",     "实物工装",   "ResourceEntity",    "fixture_factory",     False, 14, "#a78bfa", "workmanship_factory_factory_fixtures"),
    ("man",                 "操作人员",   "ResourceEntity",    "man",                 False, 15, "#c4b5fd", None),

    # ── 需求实体（项目资源需求）────────────────────────────────────────────────
    ("ProjectNeed",         "需求实体",   None,                None,                  True,  20, "#f59e0b", None),
    ("equipment_need",      "需求设备",   "ProjectNeed",       "equipment_need",      False, 21, "#fbbf24", "workmanship_bop_bop_equipments"),
    ("fixture_need",        "需求工装",   "ProjectNeed",       "fixture_need",        False, 22, "#fbbf24", "workmanship_bop_bop_fixtures"),
    ("tool_need",           "需求工具",   "ProjectNeed",       "tool_need",           False, 23, "#fbbf24", "workmanship_bop_bop_tools"),

    # ── 附属信息（控制计划、工艺卡、地面高度、人机姿态）─────────────────────────
    ("SupplementaryEntity", "附属信息",   None,                None,                  True,  25, "#6366f1", None),
    ("floor_height_factory","地面高度",   "SupplementaryEntity","floor_height_factory",False,26, "#818cf8", None),
    ("jack_pos",            "人机姿态",   "SupplementaryEntity","jack_pos",            False,27, "#818cf8", None),
    ("contral_plan",        "控制计划",   "SupplementaryEntity","contral_plan",        False,28, "#818cf8", None),
    ("process_chart",       "工艺卡",     "SupplementaryEntity","process_chart",       False,29, "#818cf8", None),

    # ── 零件实体（系统 → 配置 → 零件，三级抽象 + 四个叶子）─────────────────────
    ("PartEntity",          "零件实体",   None,                None,                  True,  30, "#06b6d4", None),
    ("PartSystem",          "系统",       "PartEntity",        None,                  True,  31, "#0ea5e9", None),
    ("PartConfig",          "配置",       "PartSystem",        None,                  True,  32, "#38bdf8", None),
    ("PartLeaf",            "零件",       "PartConfig",        None,                  True,  33, "#7dd3fc", None),
    ("part",                "零部件",     "PartLeaf",          "part",                False, 34, "#22d3ee", None),
    ("standard_part",       "标准件",     "PartLeaf",          "standard_part",       False, 35, "#22d3ee", None),
    ("non_standard_part",   "非标件",     "PartLeaf",          "non_standard_part",   False, 36, "#22d3ee", None),
    ("support_material",    "辅料",       "PartLeaf",          "support_material",    False, 37, "#22d3ee", None),

    # ── 工作项（任务细分为标准/非标）────────────────────────────────────────────
    ("WorkItem",            "工作项",     None,                None,                  True,  40, "#ef4444", None),
    ("standard_task",       "标准任务",   "WorkItem",          "standard_task",       False, 41, "#f87171", None),
    ("non_standard_task",   "非标任务",   "WorkItem",          "non_standard_task",   False, 42, "#f87171", None),
    ("issue",               "问题",       "WorkItem",          "issue",               False, 43, "#f87171", None),

    # ── 知识实体 ──────────────────────────────────────────────────────────────
    ("KnowledgeEntity",     "知识实体",   None,                None,                  True,  50, "#10b981", None),
    ("knowledge_node",      "知识节点",   "KnowledgeEntity",   "knowledge",           False, 51, "#34d399", None),
    ("rule_node",           "规则节点",   "KnowledgeEntity",   "rule",                False, 52, "#34d399", None),

    # ── 检测 & 防错（物理资源扩展）───────────────────────────────────────────
    ("inspection_gauge",    "检测量具",   "ResourceEntity",    "inspection_gauge",    False, 16, "#c4b5fd", None),
    ("poka_yoke",           "防错装置",   "ResourceEntity",    "poka_yoke",           False, 17, "#c4b5fd", None),

    # ── 质量实体 ──────────────────────────────────────────────────────────────
    ("QualityEntity",       "质量实体",   None,                None,                  True,  60, "#ec4899", None),
    ("quality_check",       "质量检查点", "QualityEntity",     "quality_check",       False, 61, "#f472b6", None),
    ("key_char",            "关键特性",   "QualityEntity",     "key_char",            False, 62, "#f472b6", None),

    # ── 标准作业（GBOP）──────────────────────────────────────────────────────
    ("StdWorkEntity",       "标准作业实体", None,              None,                  True,  70, "#f97316", None),
    ("gbop_entry",          "GBOP条目",   "StdWorkEntity",     "gbop_entry",          False, 71, "#fb923c", None),
]

# node_type_binding → (abbr, ai00_level, display_layer, stats_priority, is_hidden, suggested_child_type)
_SEED_DISPLAY_CONFIG = {
    'line_process':         ('线',   1, None,      1,  False, 'station_process'),
    'station_process':      ('工位', 2, 'station', 2,  False, 'operator_process'),
    'operator_process':     ('岗',   3, 'inner',   3,  False, 'process'),
    'process':              ('工序', 4, 'outer',   5,  False, 'operation'),
    'operation':            ('操作', 5, 'hidden',  20, True,  None),
    'station_factory':      ('工位', 4, 'inner',   10, False, None),
    'equipment_factory':    ('设备', 5, 'middle',  6,  False, None),
    'tool_factory':         ('工具', 5, 'middle',  7,  False, None),
    'fixture_factory':      ('工装', 5, 'middle',  9,  False, None),
    'man':                  ('人',   4, 'inner',   4,  False, None),
    'inspection_gauge':     ('量具', 5, 'middle',  99, False, None),
    'poka_yoke':            ('防错', 5, 'middle',  99, False, None),
    'equipment_need':       ('设需', 5, 'middle',  8,  False, None),
    'fixture_need':         ('工需', 6, 'hidden',  12, True,  None),
    'tool_need':            ('工需', 6, 'hidden',  11, True,  None),
    'floor_height_factory': ('高度', 5, 'hidden',  99, True,  None),
    'jack_pos':             ('姿态', 6, 'hidden',  99, True,  None),
    'contral_plan':         ('控划', 5, 'hidden',  23, True,  None),
    'process_chart':        ('工卡', 5, 'hidden',  24, True,  None),
    'part':                 ('零件', 6, 'hidden',  13, True,  None),
    'standard_part':        ('标件', 6, 'hidden',  15, True,  None),
    'non_standard_part':    ('非标', 6, 'hidden',  14, True,  None),
    'support_material':     ('辅料', 6, 'hidden',  16, True,  None),
    'standard_task':        ('标任', 5, 'hidden',  21, True,  None),
    'non_standard_task':    ('非任', 5, 'hidden',  22, True,  None),
    'issue':                ('问',   5, 'hidden',  19, True,  None),
    'knowledge':            ('知',   5, 'hidden',  17, True,  None),
    'rule':                 ('规',   5, 'hidden',  18, True,  None),
    'quality_check':        ('质检', 5, 'hidden',  99, True,  None),
    'key_char':             ('关特', 5, 'hidden',  99, True,  None),
    'gbop_entry':           ('GBOP', 5, 'hidden',  99, True,  None),
}

# link_type_binding → (deep_copy, shared, skip, snapshot)
_SEED_RELATION_FORK_FLAGS = {
    'bop_line':           (False, False, False, True),
    'bop_station':        (False, False, False, True),
    'bop_process':        (False, False, False, True),
    'bop_steps':          (False, False, False, True),
    'bop_operator':       (False, False, False, True),
    'physical_equipment': (False, True,  False, True),
    'physical_tool':      (False, True,  False, True),
    'physical_fixture':   (False, True,  False, True),
    'physical_station':   (False, True,  False, True),
    'project_equipment':  (True,  False, False, True),
    'project_tooling':    (True,  False, False, True),
    'project_tools':      (True,  False, False, True),
    'project_roles':      (True,  False, False, True),
    'pbom_part':          (False, False, True,  False),
    'issue':              (False, True,  False, False),
    'task_std':           (False, True,  False, False),
    'task_custom':        (False, True,  False, False),
    'knowledge':          (False, True,  False, False),
    'rule_std':           (False, True,  False, False),
}

# (class_name, prop_name, label_zh, data_type, required, min_val, max_val, description, sort_order, storage_hint)
_SEED_PROPERTIES = [
    # ── process（工序）→ workmanship_bop_bop_process（process_code/standard_time 已有固定列）
    ("process", "process_code",   "工序编号",   "string",  False, None, None, "工序唯一编号",       1, "entity_table"),
    ("process", "standard_time",  "标准工时(s)", "float",  False, 0.0,  None, "工序标准工时，单位秒", 2, "entity_table"),

    # ── operation（操作/工步）→ workmanship_bop_bop_steps ────────────────────────────────
    ("operation", "vd_time",            "增值工时(s)",     "float",   False, 0.0, None, "增值工时，单位秒",        1, "entity_table"),
    ("operation", "total_time",         "总工时(s)",       "float",   False, 0.0, None, "总工时，单位秒",          2, "entity_table"),
    ("operation", "floor_height_need",  "地面高度需求(mm)", "integer", False, 0,   None, "操作所需地面高度，单位mm", 3, "entity_table"),
    ("operation", "op_req_height",      "操作需求高度(mm)", "float",   False, 0.0, None, "作业姿态需求高度，单位mm", 4, "entity_table"),

    # ── operator_process（岗位工艺）→ workmanship_bop_bop_operator ──────────────────────
    ("operator_process", "headcount",     "人员数",   "integer", False, 1,    None, "该岗位人员数量", 1, "entity_table"),
    ("operator_process", "operator_code", "岗位代码", "string",  False, None, None, "岗位唯一编号",   2, "entity_table"),

    # ── 物理资源（工厂现有实物）→ factory.*_factory tables ──────────────────
    ("station_factory",   "takt_time", "节拍时间(s)", "float",   False, 0.0, None, "工位节拍时间，单位秒", 1, "entity_table"),
    ("station_factory",   "height_mm", "高度(mm)",    "integer", False, 0,   None, "工位高度，单位mm",     2, "entity_table"),
    ("equipment_factory", "asset_no",  "资产编号",    "string",  True,  None, None, "唯一资产编号",        1, "entity_table"),
    ("equipment_factory", "status",    "状态",        "enum",    False, None, None, "in_use/maintenance/scrapped", 2, "entity_table"),
    ("tool_factory",      "asset_no",  "资产编号",    "string",  True,  None, None, "唯一资产编号",        1, "entity_table"),
    ("tool_factory",      "status",    "状态",        "enum",    False, None, None, "in_use/maintenance/scrapped", 2, "entity_table"),
    ("fixture_factory",   "asset_no",  "资产编号",    "string",  True,  None, None, "唯一资产编号",        1, "entity_table"),
    ("fixture_factory",   "status",    "状态",        "enum",    False, None, None, "in_use/maintenance/scrapped", 2, "entity_table"),
    ("man",               "headcount", "人员数",      "integer", False, 1,    None, "人员数量",            1, "meta"),

    # ── 需求实体 → workmanship_bop_bop_equipments / bop_fixtures / bop_tools ────────────
    ("equipment_need", "spec",     "规格", "string",  False, None, None, "设备规格描述", 1, "entity_table"),
    ("equipment_need", "quantity", "数量", "integer", False, 1,    None, "需求数量",     2, "entity_table"),
    ("equipment_need", "status",   "状态", "enum",    False, None, None, "pending/confirmed/in_use/cancelled", 3, "entity_table"),
    ("fixture_need",   "spec",     "规格", "string",  False, None, None, "工装规格描述", 1, "entity_table"),
    ("fixture_need",   "quantity", "数量", "integer", False, 1,    None, "需求数量",     2, "entity_table"),
    ("fixture_need",   "status",   "状态", "enum",    False, None, None, "pending/confirmed/in_use/cancelled", 3, "entity_table"),
    ("tool_need",      "spec",     "规格", "string",  False, None, None, "工具规格描述", 1, "entity_table"),
    ("tool_need",      "quantity", "数量", "integer", False, 1,    None, "需求数量",     2, "entity_table"),
    ("tool_need",      "status",   "状态", "enum",    False, None, None, "pending/confirmed/in_use/cancelled", 3, "entity_table"),

    # ── 零件（共有属性挂父类，子类继承）─────────────────────────────────────
    ("PartEntity", "part_no",   "零件号",   "string",  True,  None, None, "零件编号",     1, "meta"),
    ("PartEntity", "part_name", "零件名称", "string",  False, None, None, "零件中文名称", 2, "meta"),
    ("PartEntity", "quantity",  "用量",     "integer", False, 1,    None, "单次装配用量", 3, "meta"),

    # ── 工作项 ─────────────────────────────────────────────────────────────
    ("standard_task",    "priority", "优先级",  "enum",   False, None, None, "low/medium/high/urgent",           1, "meta"),
    ("standard_task",    "status",   "状态",    "enum",   False, None, None, "todo/in_progress/done/cancelled",  2, "meta"),
    ("standard_task",    "due_date", "截止日期","string", False, None, None, "截止日期 YYYY-MM-DD",              3, "meta"),
    ("non_standard_task","priority", "优先级",  "enum",   False, None, None, "low/medium/high/urgent",           1, "meta"),
    ("non_standard_task","status",   "状态",    "enum",   False, None, None, "todo/in_progress/done/cancelled",  2, "meta"),
    ("issue", "severity", "严重程度", "enum", False, None, None, "low/medium/high/critical",          1, "meta"),
    ("issue", "status",   "状态",     "enum", False, None, None, "open/in_progress/resolved/closed",  2, "meta"),

    # ── line_process（线体工艺）额外属性 → workmanship_bop_bop_line.ext ──────────────────
    ("line_process", "line_code",         "线体编号",      "string",  False, None, None, "线体唯一编号",                   1, "entity_table"),
    ("line_process", "line_type",         "线体类型",      "enum",    False, None, None, "main/sub/offline",               2, "entity_table"),
    ("line_process", "target_takt_s",     "目标节拍(s)",   "float",   False, 0.0,  None, "目标节拍时间，单位秒",           3, "entity_table"),
    ("line_process", "num_stations",      "工位总数",      "integer", False, 0,    None, "线体工位总数量",                 4, "entity_table"),

    # ── station_process（工位工艺）额外属性 → workmanship_bop_bop_station.ext ─────────────
    ("station_process", "station_code",   "工位编号",      "string",  False, None, None, "工位唯一编号",                   1, "entity_table"),
    ("station_process", "station_seq",    "工位序号",      "integer", False, 0,    None, "工位在线体中的顺序",             2, "entity_table"),
    ("station_process", "cycle_time_s",   "循环时间(s)",   "float",   False, 0.0,  None, "工位实际循环时间，单位秒",       3, "entity_table"),
    ("station_process", "station_type",   "工位类型",      "enum",    False, None, None, "manual/semi_auto/auto/inspection", 4, "entity_table"),

    # ── operator_process（岗位工艺）额外属性 → workmanship_bop_bop_operator.ext ───────────
    ("operator_process", "shift",            "班次",        "enum",    False, None, None, "day/night/rotation",             3, "entity_table"),
    ("operator_process", "qualification_req","所需资质",    "string",  False, None, None, "操作人员所需资质等级",           4, "entity_table"),

    # ── process（工序）额外属性 → workmanship_bop_bop_process.ext ────────────────────────
    ("process", "process_seq",     "工序序号",      "integer", False, 0,    None, "工序顺序号",                     3, "entity_table"),
    ("process", "cycle_time_s",    "循环时间(s)",   "float",   False, 0.0,  None, "工序循环时间，单位秒",           4, "entity_table"),
    ("process", "process_method",  "工艺方法",      "enum",    False, None, None, "assembly/welding/fastening/bonding/inspection/painting/machining/other", 5, "entity_table"),
    ("process", "quality_level",   "质量等级",      "enum",    False, None, None, "general/major/critical/safety",  6, "entity_table"),
    ("process", "safety_notes",    "安全注意事项",  "string",  False, None, None, "操作安全注意事项",               7, "entity_table"),

    # ── operation（操作/工步）额外属性 → workmanship_bop_bop_steps.ext ───────────────────
    ("operation", "op_seq",             "工步序号",      "integer", False, 0,    None, "工步顺序号",                     5, "entity_table"),
    ("operation", "op_type",            "工步类型",      "enum",    False, None, None, "manual/semi_auto/auto/inspection/material_handling", 6, "entity_table"),
    ("operation", "torque_value_nm",    "拧紧力矩(N·m)", "float",   False, 0.0,  None, "螺纹拧紧目标力矩",               7, "entity_table"),
    ("operation", "torque_angle_deg",   "拧紧角度(°)",   "float",   False, 0.0,  None, "螺纹拧紧目标角度",               8, "entity_table"),
    ("operation", "weld_current_a",     "焊接电流(A)",   "float",   False, 0.0,  None, "焊接目标电流，安培",             9, "entity_table"),
    ("operation", "adhesive_code",      "胶水代码",      "string",  False, None, None, "所用胶水的物料代码",             10, "entity_table"),
    ("operation", "inspection_method",  "检测方法",      "enum",    False, None, None, "visual/gauge/scan/camera/none",  11, "entity_table"),

    # ── station_factory（实物工位）额外属性 → workmanship_factory_factory_stations.ext ────
    ("station_factory", "station_code",  "工位代码",     "string",  False, None, None, "实物工位唯一代码",               3, "entity_table"),
    ("station_factory", "station_type",  "工位类型",     "enum",    False, None, None, "manual/semi_auto/auto/inspection", 4, "entity_table"),
    ("station_factory", "area_sqm",      "工位面积(m²)", "float",   False, 0.0,  None, "工位占地面积，平方米",           5, "entity_table"),
    ("station_factory", "max_load_kg",   "最大承重(kg)", "float",   False, 0.0,  None, "工位最大承重，千克",             6, "entity_table"),

    # ── equipment_factory（实物设备）额外属性 → workmanship_factory_factory_equipments.ext
    ("equipment_factory", "model_no",               "型号",          "string",  False, None, None, "设备型号",                       3, "entity_table"),
    ("equipment_factory", "manufacturer",           "制造商",        "string",  False, None, None, "设备制造商名称",                 4, "entity_table"),
    ("equipment_factory", "power_kw",               "功率(kW)",      "float",   False, 0.0,  None, "设备额定功率，千瓦",             5, "entity_table"),
    ("equipment_factory", "maintenance_cycle_days", "保养周期(天)",  "integer", False, 0,    None, "定期保养间隔，天数",             6, "entity_table"),

    # ── tool_factory（实物工具）额外属性 → workmanship_factory_factory_tools.ext ──────────
    ("tool_factory", "tool_type",              "工具类型",    "enum",    False, None, None, "hand_tool/power_tool/pneumatic/torque_wrench/gauge/other", 3, "entity_table"),
    ("tool_factory", "tool_spec",              "规格型号",    "string",  False, None, None, "工具规格描述",                   4, "entity_table"),
    ("tool_factory", "calibration_cycle_days", "校准周期(天)","integer", False, 0,    None, "校准间隔，天数",                 5, "entity_table"),

    # ── fixture_factory（实物工装）额外属性 → workmanship_factory_factory_fixtures.ext ────
    ("fixture_factory", "fixture_type",             "工装类型",    "enum",    False, None, None, "jig/fixture/gauge/mold/die/other", 3, "entity_table"),
    ("fixture_factory", "fixture_spec",             "规格",        "string",  False, None, None, "工装规格描述",                   4, "entity_table"),
    ("fixture_factory", "design_no",                "设计编号",    "string",  False, None, None, "工装设计图号",                   5, "entity_table"),
    ("fixture_factory", "design_clamping_force_n",  "设计夹紧力(N)","float",  False, 0.0,  None, "设计夹紧力，牛顿",               6, "entity_table"),

    # ── man（操作人员）额外属性 ──────────────────────────────────────────────
    ("man", "role_code",         "岗位代码",    "string",  False, None, None, "操作人员岗位代码",               2, "meta"),
    ("man", "shift",             "班次",        "enum",    False, None, None, "day/night/rotation",             3, "meta"),
    ("man", "qualification_level","技能等级",   "enum",    False, None, None, "trainee/junior/senior/expert",   4, "meta"),
    ("man", "max_carry_kg",      "最大搬运(kg)","float",   False, 0.0,  None, "人员最大搬运重量，千克",         5, "meta"),

    # ── PartEntity（零件）额外属性 ────────────────────────────────────────────
    ("PartEntity", "weight_g",      "重量(g)",     "float",   False, 0.0,  None, "零件重量，克",                   4, "meta"),
    ("PartEntity", "drawing_no",    "图号",        "string",  False, None, None, "零件工程图号",                   5, "meta"),
    ("PartEntity", "material",      "材料",        "string",  False, None, None, "零件材料牌号",                   6, "meta"),
    ("PartEntity", "supplier_code", "供应商代码",  "string",  False, None, None, "供应商编码",                     7, "meta"),

    # ── 需求实体额外属性 → 各自实体表 ext ────────────────────────────────────
    ("equipment_need", "preferred_model",   "首选型号",    "string",  False, None, None, "推荐或首选的设备型号",           4, "entity_table"),
    ("equipment_need", "budget_cny",        "预算(元)",    "float",   False, 0.0,  None, "采购预算，人民币元",             5, "entity_table"),
    ("fixture_need",   "design_required",   "需专项设计",  "boolean", False, None, None, "是否需要专项设计工装",           4, "entity_table"),
    ("tool_need",      "calibration_req",   "需校准",      "boolean", False, None, None, "是否需要计量校准",               4, "entity_table"),

    # ── knowledge_node（知识节点）额外属性 ────────────────────────────────────
    ("knowledge_node", "knowledge_type",    "知识类型",    "enum",    False, None, None, "standard/experience/lesson_learned/benchmark", 1, "meta"),
    ("knowledge_node", "reliability",       "可信度",      "enum",    False, None, None, "verified/reviewed/draft",        2, "meta"),
    ("knowledge_node", "source",            "知识来源",    "string",  False, None, None, "知识条目来源说明",               3, "meta"),

    # ── rule_node（规则节点）额外属性 ─────────────────────────────────────────
    ("rule_node", "rule_type",         "规则类型",    "enum",    False, None, None, "mandatory/recommended/guideline", 1, "meta"),
    ("rule_node", "check_method",      "检查方式",    "enum",    False, None, None, "manual/automatic/ai",            2, "meta"),
    ("rule_node", "applicable_scope",  "适用范围",    "string",  False, None, None, "规则适用的工艺范围描述",         3, "meta"),

    # ── inspection_gauge（检测量具）属性 ─────────────────────────────────────
    ("inspection_gauge", "gauge_type",             "量具类型",    "enum",    False, None, None, "caliper/micrometer/cmm/vision/torque_tester/gauge/other", 1, "meta"),
    ("inspection_gauge", "measurement_range",      "量程",        "string",  False, None, None, "量具量程范围",                   2, "meta"),
    ("inspection_gauge", "accuracy_class",         "精度等级",    "string",  False, None, None, "量具精度等级",                   3, "meta"),
    ("inspection_gauge", "asset_no",               "资产编号",    "string",  False, None, None, "唯一资产编号",                   4, "meta"),
    ("inspection_gauge", "calibration_cycle_days", "校准周期(天)","integer", False, 0,    None, "校准间隔，天数",                 5, "meta"),

    # ── poka_yoke（防错装置）属性 ────────────────────────────────────────────
    ("poka_yoke", "poka_type",      "防错类型",    "enum",    False, None, None, "mechanical/sensor/visual/software/procedure", 1, "meta"),
    ("poka_yoke", "detected_defect","防止缺陷",    "string",  False, None, None, "该防错装置防止的缺陷描述",       2, "meta"),
    ("poka_yoke", "asset_no",       "资产编号",    "string",  False, None, None, "唯一资产编号",                   3, "meta"),

    # ── quality_check（质量检查点）属性 ──────────────────────────────────────
    ("quality_check", "check_type",      "检查类型",    "enum",    False, None, None, "visual/dimensional/functional/electrical/leak_test", 1, "meta"),
    ("quality_check", "check_frequency", "检查频次",    "enum",    False, None, None, "every_part/sampling/shift_start/daily", 2, "meta"),
    ("quality_check", "accept_criteria", "合格标准",    "string",  False, None, None, "合格判定标准描述",               3, "meta"),
    ("quality_check", "record_required", "需记录",      "boolean", False, None, None, "是否需要记录检查结果",           4, "meta"),

    # ── key_char（关键特性）属性 ──────────────────────────────────────────────
    ("key_char", "char_type",          "特性类型",    "enum",    False, None, None, "KPC/KCC/safety/critical/major",  1, "meta"),
    ("key_char", "nominal_value",      "标称值",      "string",  False, None, None, "特性标称值",                     2, "meta"),
    ("key_char", "tolerance",          "公差",        "string",  False, None, None, "特性公差范围",                   3, "meta"),
    ("key_char", "measurement_method", "测量方法",    "string",  False, None, None, "特性测量方法说明",               4, "meta"),

    # ── gbop_entry（GBOP条目）属性 ────────────────────────────────────────────
    ("gbop_entry", "gbop_code",          "GBOP编号",    "string",  False, None, None, "标准工序唯一编号",               1, "meta"),
    ("gbop_entry", "process_method",     "工艺方法",    "enum",    False, None, None, "assembly/welding/fastening/bonding/inspection/painting/machining/other", 2, "meta"),
    ("gbop_entry", "standard_time_s",    "标准工时(s)", "float",   False, 0.0,  None, "标准工时，单位秒",               3, "meta"),
    ("gbop_entry", "applicable_models",  "适用车型",    "string",  False, None, None, "适用车型范围描述",               4, "meta"),
]

# (domain_class_name, rel_name, label_zh, range_class_name, is_functional, description, link_type_binding)
_SEED_RELATIONS = [
    # ── process（工序）─────────────────────────────────────────────────────
    ("process", "hasOperation",    "包含操作",   "operation",        False, "工序包含的具体操作",       None),
    ("process", "hasIssue",        "关联问题",   "issue",            False, "工序关联的问题",           "issue"),
    ("process", "hasTask",         "关联任务",   "standard_task",    False, "工序关联的任务",           "task_std"),

    # ── operation（操作/工步）─────────────────────────────────────────────
    ("operation", "hasTool",       "使用工具",   "tool_factory",     False, "工步使用的实物工具",       "physical_tool"),
    ("operation", "hasFixture",    "使用工装",   "fixture_factory",  False, "工步使用的实物工装",       "physical_fixture"),
    ("operation", "needsTool",     "需求工具",   "tool_need",        False, "工步工具需求",             "project_tools"),
    ("operation", "needsFixture",  "需求工装",   "fixture_need",     False, "工步工装需求",             "project_tooling"),
    ("operation", "needsRole",     "需求岗位",   "man",              False, "工步岗位需求",             "project_roles"),
    ("operation", "usesPart",      "装配零件",   "PartEntity",       False, "工步装配的零件",           "pbom_part"),
    ("operation", "hasIssue",      "关联问题",   "issue",            False, "工步关联的问题",           "issue"),
    ("operation", "hasTask",       "关联任务",   "standard_task",    False, "工步关联的任务",           "task_std"),
    ("operation", "hasKnowledge",  "引用知识",   "knowledge_node",   False, "工步引用的知识条目",       "knowledge"),
    ("operation", "appliesRule",   "适用规则",   "rule_node",        False, "工步适用的工艺规则",       "rule_std"),

    # ── station_process（工位工艺）────────────────────────────────────────
    ("station_process", "hasPhysicalStation", "关联实物工位", "station_factory",   True,  "工位工艺对应的实物工位",  "physical_station"),
    ("station_process", "hasEquipment",       "使用设备",     "equipment_factory", False, "工位使用的设备",          "physical_equipment"),
    ("station_process", "needsEquipment",     "需求设备",     "equipment_need",    False, "工位设备需求",            "project_equipment"),
    ("station_process", "hasIssue",           "关联问题",     "issue",             False, "工位工艺关联的问题",      "issue"),
    ("station_process", "hasTask",            "关联任务",     "standard_task",     False, "工位工艺关联的任务",      "task_std"),

    # ── operator_process（岗位工艺）──────────────────────────────────────
    ("operator_process", "hasStation",  "所属工位", "station_factory", True, "岗位所在实物工位",    "physical_station"),
    ("operator_process", "hasPerson",   "配置人员", "man",            False, "岗位配置的操作人员",   None),

    # ── 零件反向关系 ──────────────────────────────────────────────────────
    ("PartEntity", "usedIn", "用于工步", "operation", False, "零件被哪个工步装配", None),

    # ── 工艺层级链路（上下级包含关系）────────────────────────────────────────
    ("line_process",     "containsStation",  "包含工位工艺", "station_process",  False, "线体工艺包含的工位工艺",  None),
    ("station_process",  "containsOperator", "包含岗位工艺", "operator_process", False, "工位工艺包含的岗位工艺",  None),
    ("operator_process", "containsProcess",  "包含工序",     "process",          False, "岗位工艺包含的工序",      None),

    # ── 线体工艺：知识 / 规则 / 问题 / 任务 ──────────────────────────────────
    ("line_process", "hasKnowledge", "引用知识", "knowledge_node", False, "线体工艺引用的知识条目", "knowledge"),
    ("line_process", "appliesRule",  "适用规则", "rule_node",      False, "线体工艺适用的工艺规则", "rule_std"),
    ("line_process", "hasIssue",     "关联问题", "issue",          False, "线体工艺关联的问题",     "issue"),
    ("line_process", "hasTask",      "关联任务", "standard_task",  False, "线体工艺关联的任务",     "task_std"),

    # ── 工位工艺：知识 / 规则（问题/任务已有）────────────────────────────────
    ("station_process", "hasKnowledge", "引用知识", "knowledge_node", False, "工位工艺引用的知识条目", "knowledge"),
    ("station_process", "appliesRule",  "适用规则", "rule_node",      False, "工位工艺适用的工艺规则", "rule_std"),

    # ── 岗位工艺：问题 / 任务 / 知识 / 规则 ─────────────────────────────────
    ("operator_process", "hasIssue",     "关联问题", "issue",          False, "岗位工艺关联的问题",     "issue"),
    ("operator_process", "hasTask",      "关联任务", "standard_task",  False, "岗位工艺关联的任务",     "task_std"),
    ("operator_process", "hasKnowledge", "引用知识", "knowledge_node", False, "岗位工艺引用的知识条目", "knowledge"),
    ("operator_process", "appliesRule",  "适用规则", "rule_node",      False, "岗位工艺适用的工艺规则", "rule_std"),

    # ── 工序（process）：知识 / 规则 ─────────────────────────────────────────
    ("process", "hasKnowledge", "引用知识",  "knowledge_node", False, "工序引用的知识条目",     "knowledge"),
    ("process", "appliesRule",  "适用规则",  "rule_node",      False, "工序适用的工艺规则",     "rule_std"),
    ("process", "hasKeyChar",   "含关键特性","key_char",        False, "工序含的关键特性",       None),
    ("process", "basedOnGbop",  "基于GBOP",  "gbop_entry",     False, "工序基于的标准工序模板", None),

    # ── 工步（operation）额外关系 ────────────────────────────────────────────
    ("operation", "usesEquipment",    "使用设备",   "equipment_factory", False, "工步使用的设备",         "physical_equipment"),
    ("operation", "hasQualityCheck",  "含质量检查", "quality_check",      False, "工步含的质量检查点",     None),
    ("operation", "hasKeyChar",       "含关键特性", "key_char",           False, "工步含的关键特性",       None),
    ("operation", "hasGauge",         "使用量具",   "inspection_gauge",   False, "工步使用的检测量具",     None),
    ("operation", "hasPokaYoke",      "防错校验",   "poka_yoke",          False, "工步涉及的防错装置",     None),
    ("operation", "refersGbop",       "引用GBOP",   "gbop_entry",         False, "工步引用的标准工序",     None),

    # ── 工位工艺：量具 & 防错 ────────────────────────────────────────────────
    ("station_process", "hasGauge",    "配置量具", "inspection_gauge", False, "工位配置的检测量具",  None),
    ("station_process", "hasPokaYoke", "配置防错", "poka_yoke",        False, "工位配置的防错装置",  None),
]


@router.post("/api/ontology/seed", status_code=201)
def seed_from_bop(_u=Depends(get_current_user)):
    import json

    with get_conn() as conn:
        with conn.cursor() as cur:
            # ── 1. 类 ──────────────────────────────────────────────────────────
            name_to_gid: dict[str, str] = {}
            for name, label_zh, parent_name, binding, is_abstract, sort_order, color, entity_table in _SEED_CLASSES:
                cur.execute("SELECT gid FROM workmanship_onto_classes WHERE name = %s LIMIT 1", (name,))
                existing = cur.fetchone()
                if existing:
                    name_to_gid[name] = existing["gid"]
                    cur.execute(
                        "UPDATE workmanship_onto_classes SET color=%s, entity_table=%s WHERE gid=%s",
                        (color, entity_table, existing["gid"]),
                    )
                    continue
                gid = _gid()
                name_to_gid[name] = gid
                parent_gid = name_to_gid.get(parent_name) if parent_name else None
                cur.execute(
                    "INSERT INTO workmanship_onto_classes"
                    "(gid, name, label_zh, parent_gid, node_type_binding, is_abstract, sort_order, color, entity_table)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (gid, name, label_zh, parent_gid, binding, is_abstract, sort_order, color, entity_table),
                )

            # ── 2. 数据属性（幂等：class_gid+name 已存在则跳过）──────────────
            prop_count = 0
            for cls_name, prop_name, label_zh, data_type, required, min_val, max_val, desc, sort_order, storage_hint in _SEED_PROPERTIES:
                cls_gid = name_to_gid.get(cls_name)
                if not cls_gid:
                    continue
                cur.execute(
                    "SELECT 1 FROM workmanship_onto_properties WHERE class_gid=%s AND name=%s LIMIT 1",
                    (cls_gid, prop_name),
                )
                if cur.fetchone():
                    cur.execute(
                        "UPDATE workmanship_onto_properties SET storage_hint=%s WHERE class_gid=%s AND name=%s",
                        (storage_hint, cls_gid, prop_name),
                    )
                    continue
                cur.execute(
                    "INSERT INTO workmanship_onto_properties"
                    "(gid, class_gid, name, label_zh, prop_kind, data_type,"
                    " required, min_val, max_val, description, sort_order, storage_hint)"
                    " VALUES (%s,%s,%s,%s,'data',%s,%s,%s,%s,%s,%s,%s)",
                    (_gid(), cls_gid, prop_name, label_zh, data_type,
                     required, min_val, max_val, desc, sort_order, storage_hint),
                )
                prop_count += 1

            # ── 3. 对象属性/关系（幂等：已存在则更新 link_type_binding）──────
            rel_count = 0
            for domain_name, rel_name, label_zh, range_name, is_functional, desc, lt_binding in _SEED_RELATIONS:
                domain_gid = name_to_gid.get(domain_name)
                range_gid  = name_to_gid.get(range_name)
                if not domain_gid:
                    continue
                cur.execute(
                    "SELECT gid FROM workmanship_onto_relations WHERE domain_class_gid=%s AND name=%s LIMIT 1",
                    (domain_gid, rel_name),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        "UPDATE workmanship_onto_relations SET link_type_binding=%s WHERE gid=%s",
                        (lt_binding, existing["gid"]),
                    )
                    continue
                cur.execute(
                    "INSERT INTO workmanship_onto_relations"
                    "(gid, name, label_zh, domain_class_gid, range_class_gid,"
                    " is_functional, description, link_type_binding)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (_gid(), rel_name, label_zh, domain_gid, range_gid,
                     is_functional, desc, lt_binding),
                )
                rel_count += 1

            # ── 显示配置（新字段，按 node_type_binding 更新现有记录）
            for nt, (abbr, ai00_level, display_layer, stats_priority, is_hidden, suggested_child) in _SEED_DISPLAY_CONFIG.items():
                cur.execute(
                    """UPDATE workmanship_onto_classes SET
                           abbr=%s, ai00_level=%s, display_layer=%s,
                           stats_priority=%s, is_hidden_in_layout=%s, suggested_child_type=%s
                       WHERE node_type_binding=%s""",
                    (abbr, ai00_level, display_layer, stats_priority, is_hidden, suggested_child, nt)
                )

            # ── 关系 Fork/Snapshot 行为（按 link_type_binding 更新现有记录）
            for lt, (deep_copy, shared, skip, snapshot) in _SEED_RELATION_FORK_FLAGS.items():
                cur.execute(
                    """UPDATE workmanship_onto_relations SET
                           deep_copy_on_fork=%s, shared_on_fork=%s,
                           skip_on_fork=%s, snapshot_on_freeze=%s
                       WHERE link_type_binding=%s""",
                    (deep_copy, shared, skip, snapshot, lt)
                )

            conn.commit()
            _invalidate_ntc_cache()

    return {
        "success": True,
        "message": f"Seed 完成：{len(_SEED_CLASSES)} 个类，新增 {prop_count} 个数据属性，{rel_count} 个对象属性",
    }


@router.get("/api/ontology/graph")
def get_graph(_u=Depends(get_current_user)):
    """返回全量类节点 + 继承边 + 对象属性边，供图谱渲染。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, name, label_zh, parent_gid, color, is_abstract, entity_table"
                " FROM workmanship_onto_classes ORDER BY sort_order"
            )
            classes = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT gid, name, label_zh, domain_class_gid, range_class_gid"
                " FROM workmanship_onto_relations"
                " WHERE domain_class_gid IS NOT NULL AND range_class_gid IS NOT NULL"
            )
            relations = [dict(r) for r in cur.fetchall()]
    return {"classes": classes, "relations": relations}



# 由 onto_classes.entity_table DB 字段驱动，不再硬编码映射表

_ENTITY_PROP_DENY = frozenset({
    "gid", "created_at", "updated_at", "deleted_at", "project_gid",
    "bop_version_gid", "version_gid", "vpps", "created_by", "title",
})


def _get_entity_table_and_gid(cur, entry_gid: str):
    """查询 bop_entry 对应的实体表名和实体 gid，返回 (node_type, entity_table, entity_gid)。"""
    cur.execute("SELECT node_type FROM workmanship_bop_bop_entries WHERE gid=%s AND is_deleted=FALSE", (entry_gid,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "bop_entry 不存在")
    node_type = row["node_type"]

    cur.execute(
        "SELECT entity_table FROM workmanship_onto_classes"
        " WHERE node_type_binding=%s LIMIT 1",
        (node_type,),
    )
    cls_row = cur.fetchone()
    if not cls_row or not cls_row["entity_table"]:
        return node_type, None, None

    entity_table = cls_row["entity_table"]

    cur.execute(
        "SELECT entity_gid FROM workmanship_bop_bop_entry_links"
        " WHERE entry_gid=%s AND is_primary=TRUE AND deleted_at IS NULL LIMIT 1",
        (entry_gid,),
    )
    link_row = cur.fetchone()
    entity_gid = link_row["entity_gid"] if link_row else None
    return node_type, entity_table, entity_gid


def _get_real_cols(cur, entity_table: str) -> set:
    """查询实体表实际列集合（information_schema）。"""
    table_part = entity_table.split(".", 1)[-1]
    cur.execute(
        "SELECT COLUMN_NAME AS column_name FROM information_schema.COLUMNS"
        " WHERE TABLE_SCHEMA='ai00' AND TABLE_NAME=%s",
        (table_part,),
    )
    return {r["column_name"] for r in cur.fetchall()}


@router.get("/api/bop/entries/{entry_gid}/entity-props")
def get_entity_props(entry_gid: str, _u=Depends(get_current_user)):
    """读取 bop_entry 对应实体表的字段值（固定列 + ext 展开合并，使用 mapped_column 做列名映射）。"""
    import json as _json
    with get_conn() as conn:
        with conn.cursor() as cur:
            node_type, entity_table, entity_gid = _get_entity_table_and_gid(cur, entry_gid)
            if not entity_table:
                return {"data": {}, "node_type": node_type, "entity_gid": None}
            if not entity_gid:
                return {"data": {}, "node_type": node_type, "entity_gid": None}

            real_cols = _get_real_cols(cur, entity_table)
            has_ext = "ext" in real_cols

            # 查本体属性：prop_name → db_key（COALESCE(mapped_column, name)）
            cur.execute(
                "SELECT p.name, COALESCE(p.mapped_column, p.name) AS db_key"
                " FROM workmanship_onto_properties p"
                " JOIN workmanship_onto_classes c ON c.gid = p.class_gid"
                " WHERE c.node_type_binding=%s AND p.storage_hint='entity_table' AND p.prop_kind='data'",
                (node_type,),
            )
            prop_key_map = {r["name"]: r["db_key"] for r in cur.fetchall()}
            db_keys = list(prop_key_map.values())

            select_cols = [k for k in db_keys if k in real_cols]
            if has_ext and "ext" not in select_cols:
                select_cols.append("ext")
            if not select_cols:
                return {"data": {}, "node_type": node_type, "entity_gid": entity_gid}

            cols_sql = ", ".join(f'"{c}"' for c in select_cols)
            cur.execute(f"SELECT {cols_sql} FROM {entity_table} WHERE gid=%s", (entity_gid,))
            entity = cur.fetchone()
            if not entity:
                return {"data": {}, "node_type": node_type, "entity_gid": entity_gid}

            # 返回时用 prop_name 做 key（反向映射），保持前端接口一致
            db_key_to_prop = {v: k for k, v in prop_key_map.items()}
            data = {}
            for col in select_cols:
                if col == "ext":
                    continue
                prop_name = db_key_to_prop.get(col, col)
                data[prop_name] = entity[col]
            if has_ext and entity.get("ext"):
                ext_val = entity["ext"]
                if isinstance(ext_val, str):
                    try:
                        ext_val = _json.loads(ext_val) if ext_val.strip() else {}
                    except (_json.JSONDecodeError, ValueError):
                        ext_val = {}
                if isinstance(ext_val, dict):
                    # ext 里的 key 是 db_key，同样反向映射
                    for db_k, val in ext_val.items():
                        prop_name = db_key_to_prop.get(db_k, db_k)
                        data[prop_name] = val

    return {"data": data, "node_type": node_type, "entity_gid": entity_gid}


@router.patch("/api/bop/entries/{entry_gid}/entity-props")
def patch_entity_props(entry_gid: str, body: dict, _u=Depends(get_current_user)):
    """写入 bop_entry 对应实体表（mapped_column 映射列名；属性约束校验；CEL 规则校验）。"""
    import json as _json
    with get_conn() as conn:
        with conn.cursor() as cur:
            node_type, entity_table, entity_gid = _get_entity_table_and_gid(cur, entry_gid)
            if not entity_table:
                raise HTTPException(400, f"node_type '{node_type}' 无对应实体表")
            if not entity_gid:
                raise HTTPException(404, "未找到 is_primary 实体链接")

            real_cols = _get_real_cols(cur, entity_table)
            has_ext = "ext" in real_cols

            # 查本体属性：prop_name → {db_key, data_type, required, min_val, max_val, enum_values}
            cur.execute(
                "SELECT p.name, COALESCE(p.mapped_column, p.name) AS db_key,"
                "       p.data_type, p.required, p.min_val, p.max_val, p.enum_values"
                " FROM workmanship_onto_properties p"
                " JOIN workmanship_onto_classes c ON c.gid = p.class_gid"
                " WHERE c.node_type_binding=%s AND p.prop_kind='data'",
                (node_type,),
            )
            prop_map = {r["name"]: dict(r) for r in cur.fetchall()}

            # ── 属性约束校验 ──────────────────────────────────────────────────
            errors: dict[str, str] = {}
            for prop_name, v in body.items():
                if prop_name in _ENTITY_PROP_DENY or prop_name.startswith("_"):
                    continue
                p = prop_map.get(prop_name)
                if p and p.get("storage_hint") == "derived":
                    continue  # 派生属性只读，不允许直接写入
                if not p:
                    continue
                if v is None or v == "":
                    if p["required"]:
                        errors[prop_name] = "必填"
                    continue
                dt = p["data_type"]
                if dt in ("integer", "float"):
                    try:
                        num = float(v)
                        if p["min_val"] is not None and num < float(p["min_val"]):
                            errors[prop_name] = f"不能小于 {p['min_val']}"
                        elif p["max_val"] is not None and num > float(p["max_val"]):
                            errors[prop_name] = f"不能大于 {p['max_val']}"
                    except (TypeError, ValueError):
                        errors[prop_name] = "必须是数字"
                elif dt == "enum":
                    ev = p["enum_values"] or []
                    if isinstance(ev, str):
                        ev = _json.loads(ev)
                    if ev and v not in ev:
                        errors[prop_name] = f"必须是 {ev} 之一"
            if errors:
                raise HTTPException(422, {"validation_errors": errors})

            # ── 字段分类：prop_name → db_key，路由到固定列或 ext ───────────────
            fixed_updates: dict = {}
            ext_updates: dict = {}
            for prop_name, v in body.items():
                if prop_name in _ENTITY_PROP_DENY or prop_name.startswith("_"):
                    continue
                p = prop_map.get(prop_name)
                if p and p.get("storage_hint") == "derived":
                    continue  # 派生属性只读，不允许直接写入
                db_key = p["db_key"] if p else prop_name
                if db_key in real_cols:
                    fixed_updates[db_key] = v
                elif has_ext:
                    ext_updates[db_key] = v

            # ── CEL 规则校验（commit 前）──────────────────────────────────────
            try:
                from backend.rule_engine.checker import validate_with_proposed
                proposed_vals = {**{k: v for k, v in fixed_updates.items()},
                                 **{k: v for k, v in ext_updates.items()}}
                rule_violations = validate_with_proposed(node_type, entry_gid, proposed_vals, conn=conn)
                mandatory_fails = [v for v in rule_violations if v["enforcement_level"] == "mandatory"]
                if mandatory_fails:
                    raise HTTPException(422, {"validation_errors": {}, "rule_violations": mandatory_fails})
                advisory = [v for v in rule_violations if v["enforcement_level"] != "mandatory"]
            except ImportError:
                advisory = []

            # ── 写入 ──────────────────────────────────────────────────────────
            if fixed_updates:
                sets = ", ".join(f'"{k}"=%s' for k in fixed_updates)
                vals = list(fixed_updates.values()) + [entity_gid]
                cur.execute(f"UPDATE {entity_table} SET {sets}, updated_at=NOW() WHERE gid=%s", vals)

            for k, v in ext_updates.items():
                if v is None:
                    cur.execute(
                        f"UPDATE {entity_table} SET ext = ext - %s, updated_at=NOW() WHERE gid=%s",
                        (k, entity_gid),
                    )
                else:
                    cur.execute(
                        f"UPDATE {entity_table}"
                        f" SET ext = JSON_SET(IFNULL(ext,'{{}}'), CONCAT('$.', %s), CAST(%s AS JSON)),"
                        f"     updated_at=NOW()"
                        f" WHERE gid=%s",
                        (k, _json.dumps(v, ensure_ascii=False), entity_gid),
                    )

            conn.commit()

    return {"success": True, "warnings": advisory}


# ── 本体-数据库映射同步状态 ───────────────────────────────────────────────────

@router.get("/api/ontology/schema-diff")
def schema_diff(_u=Depends(get_current_user)):
    """
    对比 onto_properties 与 information_schema，返回每个实体属性的映射同步状态。
    sync_status: 'column'（有固定列）| 'ext'（只有 ext，无固定列）
    可用于本体编辑器显示 DB映射 列、DBA 了解哪些属性待建列。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 拉取属性 + 类信息（不做 information_schema JOIN，在 Python 侧解析）
            cur.execute("""
                SELECT
                    p.gid,
                    p.name,
                    p.label_zh,
                    COALESCE(p.mapped_column, p.name) AS db_key,
                    p.mapped_column,
                    c.name  AS class_name,
                    c.entity_table
                FROM workmanship_onto_properties p
                JOIN workmanship_onto_classes c ON c.gid = p.class_gid
                WHERE c.entity_table IS NOT NULL
                  AND p.storage_hint = 'entity_table'
                  AND p.prop_kind = 'data'
                ORDER BY c.sort_order, p.sort_order
            """)
            rows = [dict(r) for r in cur.fetchall()]

            # 收集所有涉及的 MySQL 表名，批量查询 information_schema
            mysql_tables = {_pg_entity_table_to_mysql(r["entity_table"]) for r in rows}
            existing_cols: dict[str, set] = {}  # mysql_table → set of column_names
            if mysql_tables:
                ph = ','.join(['%s'] * len(mysql_tables))
                cur.execute(
                    f"SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name"
                    f" FROM information_schema.COLUMNS"
                    f" WHERE TABLE_SCHEMA='ai00' AND TABLE_NAME IN ({ph})",
                    list(mysql_tables),
                )
                for col_row in cur.fetchall():
                    tbl = col_row["table_name"]
                    col = col_row["column_name"]
                    existing_cols.setdefault(tbl, set()).add(col)

    # 打标：属性的 db_key 是否真实存在于对应 MySQL 表
    for row in rows:
        mysql_tbl = _pg_entity_table_to_mysql(row["entity_table"])
        db_key = row["db_key"]
        cols_in_table = existing_cols.get(mysql_tbl, set())
        row["sync_status"] = "column" if db_key in cols_in_table else "ext"

    return {"data": rows}


# ── node-type-config API ──────────────────────────────────────────────────────

@router.get("/api/ontology/node-type-config", status_code=200)
def get_node_type_config(_u=Depends(get_current_user)):
    """返回前端替代所有硬编码 JS 常量所需的完整节点类型配置（服务端模块级缓存）。"""
    global _ntc_cache
    if _ntc_cache is not None:
        return _ntc_cache

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.gid, c.name, c.label_zh, c.label_en, c.node_type_binding,
                       c.parent_gid, c.entity_table, c.color, c.icon,
                       c.abbr, c.ai00_level, c.display_layer, c.stats_priority,
                       c.is_hidden_in_layout, c.suggested_child_type,
                       c.is_abstract, c.description,
                       pc.node_type_binding AS parent_node_type
                FROM workmanship_onto_classes c
                LEFT JOIN workmanship_onto_classes pc ON pc.gid = c.parent_gid
                ORDER BY c.sort_order, c.name
            """)
            all_classes = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT p.class_gid, p.name, p.label_zh, p.prop_kind,
                       p.data_type, p.required, p.min_val, p.max_val,
                       p.enum_values, p.description,
                       p.field_widget, p.field_config,
                       p.show_in_create_dialog, p.dialog_order
                FROM workmanship_onto_properties p
                JOIN workmanship_onto_classes c ON c.gid = p.class_gid
                WHERE c.node_type_binding IS NOT NULL
                  AND p.show_in_create_dialog = TRUE
                  AND p.prop_kind = 'data'
                ORDER BY p.class_gid, p.dialog_order, p.sort_order
            """)
            all_props = [dict(r) for r in cur.fetchall()]

    props_by_class: dict[str, list] = {}
    for p in all_props:
        props_by_class.setdefault(p['class_gid'], []).append(p)

    class_by_gid = {c['gid']: c for c in all_classes}
    types_config: dict = {}
    child_map: dict = {}
    parent_map: dict = {}

    for cls in all_classes:
        nt = cls.get('node_type_binding')
        if not nt:
            continue

        dialog_fields = []
        seen_names: set = set()
        curr = cls
        while curr:
            for prop in props_by_class.get(curr['gid'], []):
                if prop['name'] not in seen_names:
                    seen_names.add(prop['name'])
                    field = {
                        'name':         prop['name'],
                        'label':        prop['label_zh'],
                        'widget':       prop.get('field_widget') or 'text',
                        'required':     prop.get('required') or False,
                        'dialog_order': prop.get('dialog_order', 99),
                    }
                    if prop.get('min_val') is not None:
                        field['min'] = prop['min_val']
                    if prop.get('max_val') is not None:
                        field['max'] = prop['max_val']
                    if prop.get('enum_values'):
                        field['options'] = prop['enum_values']
                    if prop.get('field_config'):
                        field.update(prop['field_config'])
                    dialog_fields.append(field)
            parent_gid = curr.get('parent_gid')
            curr = class_by_gid.get(parent_gid) if parent_gid else None

        dialog_fields.sort(key=lambda f: f.get('dialog_order', 99))

        types_config[nt] = {
            'gid':                  cls['gid'],
            'abbr':                 cls.get('abbr') or nt[:3],
            'label':                cls.get('label_zh') or nt,
            'color':                cls.get('color') or '#6c7086',
            'icon':                 cls.get('icon'),
            'ai00_level':           cls.get('ai00_level'),
            'display_layer':        cls.get('display_layer'),
            'stats_priority':       cls.get('stats_priority', 99),
            'is_hidden_in_layout':  cls.get('is_hidden_in_layout', False),
            'suggested_child_type': cls.get('suggested_child_type'),
            'entity_table':         cls.get('entity_table'),
            'is_abstract':          cls.get('is_abstract', False),
            'parent_node_type':     cls.get('parent_node_type'),
            'create_dialog_fields': dialog_fields,
        }

        if cls.get('suggested_child_type'):
            child_map[nt] = cls['suggested_child_type']
        if cls.get('parent_node_type'):
            parent_map[nt] = cls['parent_node_type']

    ordered_types = sorted(
        [nt for nt in types_config if not types_config[nt]['is_abstract']],
        key=lambda nt: (types_config[nt].get('ai00_level') or 99,
                        types_config[nt].get('stats_priority') or 99)
    )

    layer_groups = {
        'inner':   [nt for nt, c in types_config.items() if c['display_layer'] == 'inner'],
        'middle':  [nt for nt, c in types_config.items() if c['display_layer'] == 'middle'],
        'outer':   [nt for nt, c in types_config.items() if c['display_layer'] == 'outer'],
        'station': [nt for nt, c in types_config.items() if c['display_layer'] == 'station'],
        'hidden':  [nt for nt, c in types_config.items() if c['is_hidden_in_layout']],
    }

    stats_priority_list = sorted(
        [nt for nt in types_config if not types_config[nt]['is_hidden_in_layout']],
        key=lambda nt: types_config[nt].get('stats_priority', 99)
    )

    result = {
        'types':               types_config,
        'ordered_types':       ordered_types,
        'child_map':           child_map,
        'parent_map':          parent_map,
        'layer_groups':        layer_groups,
        'stats_priority_list': stats_priority_list,
    }
    _ntc_cache = result
    return result


# ── 推理 API ──────────────────────────────────────────────────────────────────

@router.post("/api/ontology/validate/{entry_gid}", status_code=200)
def validate_entry(entry_gid: str, _u=Depends(get_current_user)):
    """对 BOP 条目执行结构性一致性检查（基数约束）。Agent 写入后调用自检。"""
    from backend.rule_engine.reasoner import consistency_check
    return consistency_check(entry_gid)


@router.get("/api/ontology/agent-schema", status_code=200)
def get_agent_schema(_u=Depends(get_current_user)):
    """返回供 Agent session 注入的完整本体世界模型。"""
    from backend.rule_engine.reasoner import build_agent_schema
    return {"schema": build_agent_schema()}


@router.get("/api/ontology/classes/{gid}/axioms", status_code=200)
def list_class_axioms(gid: str, include_inherited: bool = True, _u=Depends(get_current_user)):
    """返回该类（及父类）的全部公理。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if include_inherited:
                from backend.rule_engine.reasoner import get_ancestor_gids
                class_gids = get_ancestor_gids(gid, cur)
            else:
                class_gids = [gid]
            ph = ','.join(['%s'] * len(class_gids))
            cur.execute(
                f"SELECT a.*, p.name AS prop_name, p.label_zh AS prop_label,"
                f" tc.node_type_binding AS child_nt, tc.label_zh AS child_label"
                f" FROM workmanship_onto_axioms a"
                f" LEFT JOIN workmanship_onto_properties p ON p.gid=a.property_gid"
                f" LEFT JOIN workmanship_onto_classes tc ON tc.gid=a.target_gid"
                f" WHERE a.class_gid IN ({ph})"
                f" ORDER BY a.axiom_type, a.created_at",
                class_gids
            )
            return {"data": [dict(r) for r in cur.fetchall()]}

