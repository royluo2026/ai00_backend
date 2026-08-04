"""
backend/routers/ext_datasource.py
───────────────────────────────────
外部数据源集成 API

连接管理：
  GET    /api/ext-datasources
  POST   /api/ext-datasources
  PATCH  /api/ext-datasources/{gid}
  DELETE /api/ext-datasources/{gid}
  POST   /api/ext-datasources/{gid}/test
  GET    /api/ext-datasources/{gid}/tables

映射管理：
  GET    /api/ext-mappings?datasource_gid=
  POST   /api/ext-mappings
  PATCH  /api/ext-mappings/{gid}
  DELETE /api/ext-mappings/{gid}
  GET    /api/ext-mappings/{gid}/columns
  GET    /api/ext-mappings/{gid}/preview
  POST   /api/ext-mappings/{gid}/import

字段映射：
  GET    /api/ext-field-mappings?mapping_gid=
  PUT    /api/ext-field-mappings/batch
"""
import ast
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user
from backend.utils.gid import next_gid
from plugins.craft.craft_backend.public import (
    ontology_class, ontology_class_labels, ontology_properties, upsert_external_bop_entries,
)

router = APIRouter(tags=["ext-datasource"])
_log = logging.getLogger(__name__)

# ── 加密工具 ──────────────────────────────────────────────────────────────────

def _get_secret() -> bytes:
    key = os.environ.get("EXT_DS_SECRET", "ai00_ext_ds_default_key_32bytes!!")
    return key[:32].ljust(32).encode()


def _encrypt(plaintext: str) -> str:
    try:
        from cryptography.fernet import Fernet
        import base64, hashlib
        key = base64.urlsafe_b64encode(hashlib.sha256(_get_secret()).digest())
        return Fernet(key).encrypt(plaintext.encode()).decode()
    except Exception:
        return plaintext  # fallback: 无加密（开发环境）


def _decrypt(ciphertext: str) -> str:
    try:
        from cryptography.fernet import Fernet
        import base64, hashlib
        key = base64.urlsafe_b64encode(hashlib.sha256(_get_secret()).digest())
        return Fernet(key).decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext


# ── 数据库连接工具 ─────────────────────────────────────────────────────────────

def _make_ext_conn(ds: dict):
    """根据 datasource 记录建立外部 DB 连接。"""
    password = _decrypt(ds["password_enc"])
    db_type  = ds["db_type"]
    if db_type == "postgresql":
        import psycopg2
        return psycopg2.connect(
            host=ds["host"], port=ds["port"], dbname=ds["database"],
            user=ds["username"], password=password, connect_timeout=8,
        )
    elif db_type == "mysql":
        import pymysql
        return pymysql.connect(
            host=ds["host"], port=ds["port"], database=ds["database"],
            user=ds["username"], password=password, connect_timeout=8,
        )
    elif db_type == "sqlserver":
        import pyodbc
        dsn = (f"DRIVER={{ODBC Driver 17 for SQL Server}};"
               f"SERVER={ds['host']},{ds['port']};"
               f"DATABASE={ds['database']};UID={ds['username']};PWD={password};")
        return pyodbc.connect(dsn, timeout=8)
    else:
        raise ValueError(f"不支持的数据库类型：{db_type}")


def _list_tables(ext_conn, db_type: str) -> list[dict]:
    cur = ext_conn.cursor()
    if db_type == "postgresql":
        cur.execute("""
            SELECT table_schema || '.' || table_name AS full_name, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema','pg_catalog')
            ORDER BY full_name
        """)
    elif db_type == "mysql":
        cur.execute("SHOW TABLES")
        rows = cur.fetchall()
        return [{"full_name": r[0], "table_name": r[0]} for r in rows]
    else:
        cur.execute("""
            SELECT TABLE_SCHEMA + '.' + TABLE_NAME AS full_name, TABLE_NAME AS table_name
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY full_name
        """)
    rows = cur.fetchall()
    return [{"full_name": r[0], "table_name": r[1]} for r in rows]


def _list_columns(ext_conn, table: str, db_type: str) -> list[dict]:
    """返回 [{column_name, data_type}]"""
    schema, tname = (table.split(".", 1) + [""])[:2] if "." in table else ("public", table)
    cur = ext_conn.cursor()
    if db_type == "postgresql":
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """, (schema, tname))
    elif db_type == "mysql":
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = %s ORDER BY ORDINAL_POSITION
        """, (tname,))
    else:
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = %s ORDER BY ORDINAL_POSITION
        """, (tname,))
    return [{"column_name": r[0], "data_type": r[1]} for r in cur.fetchall()]


# ── 转换表达式安全执行 ─────────────────────────────────────────────────────────

_SAFE_OPS = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
             ast.USub, ast.UAdd, ast.Num, ast.Constant, ast.BinOp, ast.UnaryOp,
             ast.Expression, ast.Load}
_SAFE_FUNCS = {"round", "int", "float", "str", "abs"}


def _safe_transform(expr: str, value: Any) -> Any:
    if not expr or not expr.strip():
        return value
    try:
        tree = ast.parse(expr.strip(), mode="eval")
        for node in ast.walk(tree):
            if type(node) not in _SAFE_OPS:
                if isinstance(node, ast.Call):
                    if not (isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS):
                        raise ValueError(f"不允许的函数调用")
                elif isinstance(node, ast.Name) and node.id != "value":
                    raise ValueError(f"不允许的变量：{node.id}")
        return eval(compile(tree, "<string>", "eval"), {"value": value, **{f: getattr(__builtins__, f, None) for f in _SAFE_FUNCS if hasattr(__builtins__, f)}})
    except Exception as e:
        _log.debug("transform eval error: %s | expr=%s | value=%s", e, expr, value)
        return value


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def _gid() -> str:
    return str(next_gid())



def _enrich_mapping_classes(rows: list[dict]) -> list[dict]:
    labels = ontology_class_labels(row.get("onto_class_gid") for row in rows)
    for row in rows:
        row["class_label"] = labels.get(str(row.get("onto_class_gid")))
    return rows


def _enrich_field_properties(rows: list[dict]) -> list[dict]:
    properties = ontology_properties(row.get("onto_property_gid") for row in rows)
    for row in rows:
        prop = properties.get(str(row.get("onto_property_gid")), {})
        row["prop_name"] = prop.get("name")
        row["prop_label"] = prop.get("label_zh")
        row["storage_hint"] = prop.get("storage_hint")
    return rows

def _ds_row(r: dict) -> dict:
    d = dict(r)
    d.pop("password_enc", None)  # 不返回加密密码
    return d


# ── 连接管理 ──────────────────────────────────────────────────────────────────

class DatasourceBody(BaseModel):
    name: str
    db_type: str
    host: str
    port: int
    database: str
    username: str
    password: str = ""


@router.get("/api/ext-datasources")
def list_datasources(_u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_int_ext_datasources ORDER BY created_at")
            rows = [_ds_row(dict(r)) for r in cur.fetchall()]
    return {"data": rows}


@router.post("/api/ext-datasources", status_code=201)
def create_datasource(body: DatasourceBody, _u=Depends(get_current_user)):
    gid = _gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_int_ext_datasources"
                "(gid,name,db_type,host,port,database,username,password_enc,created_by)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.name, body.db_type, body.host, body.port,
                 body.database, body.username, _encrypt(body.password),
                 _u.get("gid",""))
            )
            conn.commit()
            cur.execute("SELECT * FROM workmanship_int_ext_datasources WHERE gid=%s", (gid,))
            row = cur.fetchone()
    return {"data": _ds_row(dict(row))}


@router.patch("/api/ext-datasources/{gid}")
def update_datasource(gid: str, body: dict, _u=Depends(get_current_user)):
    allowed = {"name", "db_type", "host", "port", "database", "username"}
    data = {k: v for k, v in body.items() if k in allowed}
    if "password" in body and body["password"]:
        data["password_enc"] = _encrypt(body["password"])
    if not data:
        raise HTTPException(400, "无可更新字段")
    sets = ", ".join(f"{k}=%s" for k in data) + ", updated_at=NOW(), status='untested'"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_int_ext_datasources SET {sets} WHERE gid=%s",
                        list(data.values()) + [gid])
            conn.commit()
            cur.execute("SELECT * FROM workmanship_int_ext_datasources WHERE gid=%s", (gid,))
            row = cur.fetchone()
    return {"data": _ds_row(dict(row))}


@router.delete("/api/ext-datasources/{gid}", status_code=204)
def delete_datasource(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_int_ext_datasources WHERE gid=%s", (gid,))
            conn.commit()


@router.post("/api/ext-datasources/{gid}/test")
def test_datasource(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_int_ext_datasources WHERE gid=%s", (gid,))
            ds = cur.fetchone()
    if not ds:
        raise HTTPException(404, "连接不存在")
    ds = dict(ds)
    try:
        import time
        t0 = time.monotonic()
        ext = _make_ext_conn(ds)
        latency_ms = int((time.monotonic() - t0) * 1000)
        ext.close()
        status, err = "ok", None
    except Exception as e:
        status, err, latency_ms = "error", str(e), None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_int_ext_datasources SET status=%s, last_tested_at=NOW(), last_error=%s, updated_at=NOW() WHERE gid=%s",
                (status, err, gid)
            )
            conn.commit()
    return {"status": status, "latency_ms": latency_ms, "error": err}


@router.get("/api/ext-datasources/{gid}/tables")
def list_ext_tables(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_int_ext_datasources WHERE gid=%s", (gid,))
            ds = cur.fetchone()
    if not ds:
        raise HTTPException(404, "连接不存在")
    ds = dict(ds)
    try:
        ext = _make_ext_conn(ds)
        tables = _list_tables(ext, ds["db_type"])
        ext.close()
        return {"data": tables}
    except Exception as e:
        raise HTTPException(400, f"获取表列表失败：{e}")


# ── 映射管理 ──────────────────────────────────────────────────────────────────

class MappingBody(BaseModel):
    datasource_gid: str
    ext_table: str
    onto_class_gid: str
    filter_sql: Optional[str] = None
    unique_key_col: Optional[str] = None


@router.get("/api/ext-mappings")
def list_mappings(datasource_gid: Optional[str] = Query(None), _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if datasource_gid:
                cur.execute("SELECT m.* FROM workmanship_int_ext_mappings m WHERE m.datasource_gid=%s ORDER BY m.created_at", (datasource_gid,))
            else:
                cur.execute("SELECT m.* FROM workmanship_int_ext_mappings m ORDER BY m.created_at")
            rows = [dict(r) for r in cur.fetchall()]
    return {"data": _enrich_mapping_classes(rows)}


@router.post("/api/ext-mappings", status_code=201)
def create_mapping(body: MappingBody, _u=Depends(get_current_user)):
    gid = _gid()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_int_ext_mappings(gid,datasource_gid,ext_table,onto_class_gid,filter_sql,unique_key_col,created_by)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.datasource_gid, body.ext_table, body.onto_class_gid,
                 body.filter_sql, body.unique_key_col, _u.get("gid",""))
            )
            conn.commit()
            cur.execute("SELECT m.* FROM workmanship_int_ext_mappings m WHERE m.gid=%s", (gid,))
            row = cur.fetchone()
    return {"data": _enrich_mapping_classes([dict(row)])[0]}


@router.patch("/api/ext-mappings/{gid}")
def update_mapping(gid: str, body: dict, _u=Depends(get_current_user)):
    allowed = {"ext_table", "onto_class_gid", "filter_sql", "unique_key_col"}
    data = {k: v for k, v in body.items() if k in allowed}
    if not data:
        raise HTTPException(400, "无可更新字段")
    sets = ", ".join(f"{k}=%s" for k in data)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_int_ext_mappings SET {sets} WHERE gid=%s", list(data.values()) + [gid])
            conn.commit()
            cur.execute("SELECT m.* FROM workmanship_int_ext_mappings m WHERE m.gid=%s", (gid,))
            row = cur.fetchone()
    return {"data": _enrich_mapping_classes([dict(row)])[0]}


@router.delete("/api/ext-mappings/{gid}", status_code=204)
def delete_mapping(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_int_ext_mappings WHERE gid=%s", (gid,))
            conn.commit()


@router.get("/api/ext-mappings/{gid}/columns")
def get_mapping_columns(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT m.*, d.db_type, d.host, d.port, d.database, d.username, d.password_enc FROM workmanship_int_ext_mappings m JOIN workmanship_int_ext_datasources d ON d.gid=m.datasource_gid WHERE m.gid=%s", (gid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(404)
    row = dict(row)
    try:
        ext = _make_ext_conn(row)
        cols = _list_columns(ext, row["ext_table"], row["db_type"])
        ext.close()
        return {"data": cols}
    except Exception as e:
        raise HTTPException(400, f"获取列信息失败：{e}")


@router.get("/api/ext-mappings/{gid}/preview")
def preview_mapping(gid: str, limit: int = Query(5, le=50), _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.*, d.db_type, d.host, d.port, d.database, d.username, d.password_enc "
                "FROM workmanship_int_ext_mappings m "
                "JOIN workmanship_int_ext_datasources d ON d.gid=m.datasource_gid WHERE m.gid=%s", (gid,))
            mapping = cur.fetchone()
            if not mapping:
                raise HTTPException(404)
            mapping = dict(mapping)
            cur.execute("SELECT * FROM workmanship_int_ext_field_mappings WHERE mapping_gid=%s ORDER BY sort_order", (gid,))
            field_maps = [dict(r) for r in cur.fetchall()]

    try:
        ext = _make_ext_conn(mapping)
        where = f"WHERE {mapping['filter_sql']}" if mapping.get("filter_sql") else ""
        # psycopg2 / pymysql 参数化 LIMIT 差异处理
        cur2 = ext.cursor()
        cur2.execute(f"SELECT * FROM {mapping['ext_table']} {where} LIMIT {int(limit)}")
        cols = [d[0] for d in cur2.description]
        raw_rows = [dict(zip(cols, r)) for r in cur2.fetchall()]
        ext.close()
    except Exception as e:
        raise HTTPException(400, f"查询外部数据失败：{e}")

    # 应用转换
    result = []
    for raw in raw_rows:
        mapped = {}
        for fm in field_maps:
            if fm.get("is_ignored"):
                continue
            col = fm["ext_column"]
            val = raw.get(col)
            mapped[col] = {
                "raw": val,
                "transformed": _safe_transform(fm.get("transform_expr", ""), val)
                if fm.get("transform_expr") else val,
                "target": fm.get("bop_field") or fm.get("onto_property_gid", ""),
            }
        result.append(mapped)

    return {"data": result, "columns": cols, "raw_rows": raw_rows[:limit]}


@router.post("/api/ext-mappings/{gid}/import")
def execute_import(gid: str, _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.*,d.db_type,d.host,d.port,d.database,d.username,d.password_enc "
                "FROM workmanship_int_ext_mappings m JOIN workmanship_int_ext_datasources d ON d.gid=m.datasource_gid "
                "WHERE m.gid=%s",
                (gid,),
            )
            mapping = cur.fetchone()
            if not mapping:
                raise HTTPException(404)
            mapping = dict(mapping)
            cur.execute(
                "SELECT fm.* FROM workmanship_int_ext_field_mappings fm "
                "WHERE fm.mapping_gid=%s AND fm.is_ignored=FALSE ORDER BY fm.sort_order",
                (gid,),
            )
            field_maps = _enrich_field_properties([dict(row) for row in cur.fetchall()])

    class_info = ontology_class(mapping["onto_class_gid"])
    node_type = class_info.get("node_type_binding") if class_info else None
    if not node_type:
        raise HTTPException(400, "本体类未绑定 node_type，无法导入")

    try:
        ext = _make_ext_conn(mapping)
        where = f"WHERE {mapping['filter_sql']}" if mapping.get("filter_sql") else ""
        cur2 = ext.cursor()
        cur2.execute(f"SELECT * FROM {mapping['ext_table']} {where}")
        cols = [desc[0] for desc in cur2.description]
        raw_rows = [dict(zip(cols, row)) for row in cur2.fetchall()]
        ext.close()
    except Exception as exc:
        raise HTTPException(400, f"读取外部数据失败：{exc}") from exc

    bop_rows: list[dict] = []
    for raw in raw_rows:
        bop_fields: dict = {"node_type": node_type}
        meta_fields: dict = {}
        for field_map in field_maps:
            value = raw.get(field_map["ext_column"])
            if field_map.get("transform_expr"):
                value = _safe_transform(field_map["transform_expr"], value)
            if value is None:
                continue
            if field_map["target_type"] == "bop_field" and field_map.get("bop_field"):
                bop_fields[field_map["bop_field"]] = value
            elif field_map.get("prop_name"):
                if field_map.get("storage_hint") == "entity_table":
                    bop_fields[field_map["prop_name"]] = value
                else:
                    meta_fields[field_map["prop_name"]] = value
        bop_fields["meta"] = meta_fields
        bop_rows.append(bop_fields)

    unique_bop_field = None
    if mapping.get("unique_key_col"):
        unique_bop_field = next(
            (fm.get("bop_field") for fm in field_maps if fm["ext_column"] == mapping["unique_key_col"]),
            None,
        )
    result = upsert_external_bop_entries(node_type, bop_rows, unique_bop_field)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_int_ext_mappings SET last_import_at=NOW(),last_import_count=%s WHERE gid=%s",
                (result["imported"] + result["updated"], gid),
            )
        conn.commit()
    return result


# ── 字段映射 ──────────────────────────────────────────────────────────────────

@router.get("/api/ext-field-mappings")
def list_field_mappings(mapping_gid: str = Query(...), _u=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT fm.* FROM workmanship_int_ext_field_mappings fm WHERE fm.mapping_gid=%s ORDER BY fm.sort_order", (mapping_gid,))
            rows = [dict(r) for r in cur.fetchall()]
    return {"data": _enrich_field_properties(rows)}


class FieldMappingItem(BaseModel):
    ext_column: str
    target_type: str = "property"
    onto_property_gid: Optional[str] = None
    bop_field: Optional[str] = None
    transform_expr: Optional[str] = None
    is_ignored: bool = False
    sort_order: int = 0


@router.put("/api/ext-field-mappings/batch")
def batch_save_field_mappings(
    mapping_gid: str,
    items: list[FieldMappingItem],
    _u=Depends(get_current_user)
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_int_ext_field_mappings WHERE mapping_gid=%s", (mapping_gid,))
            for item in items:
                cur.execute(
                    "INSERT INTO workmanship_int_ext_field_mappings"
                    "(gid,mapping_gid,ext_column,target_type,onto_property_gid,bop_field,transform_expr,is_ignored,sort_order)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (_gid(), mapping_gid, item.ext_column, item.target_type,
                     item.onto_property_gid or None, item.bop_field or None,
                     item.transform_expr or None, item.is_ignored, item.sort_order)
                )
            conn.commit()
    return {"success": True, "count": len(items)}
