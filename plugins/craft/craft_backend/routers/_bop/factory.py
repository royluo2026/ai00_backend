"""
backend/routers/_bop/factory.py
────────────────────────────────
工厂 / 工段 / 工位 + 布局模板路由。
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.utils.gid import next_gid

from ._constants import _ADMIN, _READ, _SEC_COLS, _SEC_KEYS, _STA_COLS, _STA_KEYS, _LTPL_COLS, _LTPL_KEYS
from ._helpers import _row, _rows, _not_found

router = APIRouter(prefix="/api/bop", tags=["bop"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class CreateFactoryBody(BaseModel):
    name: str
    team_id: Optional[str] = None


class UpdateFactoryBody(BaseModel):
    name: Optional[str] = None
    team_id: Optional[str] = None


class CreateSectionBody(BaseModel):
    name: str
    sort_order: int = 0
    color: str = '#7287fd'
    canvas_x: float = 0
    canvas_y: float = 0
    canvas_w: float = 400
    canvas_h: float = 300


class UpdateSectionBody(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    color: Optional[str] = None
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None
    canvas_w: Optional[float] = None
    canvas_h: Optional[float] = None
    owner_gid: Optional[str] = None


class CreateStationBody(BaseModel):
    code: str
    name: str = ''
    canvas_x: float = 0
    canvas_y: float = 0
    takt_time: float = 60
    height_mm: int = 1200


class UpdateStationBody(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None
    takt_time: Optional[float] = None
    height_mm: Optional[int] = None


class CreateLayoutTemplateBody(BaseModel):
    name: str
    team_id: Optional[str] = None
    stations: list = []


class ApplyLayoutTemplateBody(BaseModel):
    factory_section_gid: str
    drop_x: float = 0
    drop_y: float = 0


# ══════════════════════════════════════════════════════════════
# 工厂
# ══════════════════════════════════════════════════════════════

@router.get("/factories")
def list_factories(_u=Depends(_READ)):
    keys = ['gid','name','team_id','meta','created_at']
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid,name,team_id,meta,created_at FROM workmanship_factory_factories ORDER BY created_at")
            return {"data": _rows(cur, keys)}


@router.post("/factories", status_code=201)
def create_factory(body: CreateFactoryBody, _u=Depends(_ADMIN)):
    gid = str(next_gid())
    keys = ['gid','name','team_id','meta','created_at']
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_factory_factories (gid,name,team_id,meta) VALUES (%s,%s,%s,%s)",
                (gid, body.name, body.team_id, '{}')
            )
            conn.commit()
            cur.execute("SELECT gid,name,team_id,meta,created_at FROM workmanship_factory_factories WHERE gid=%s", (gid,))
            return {"data": _row(cur, keys)}


@router.get("/factories/{gid}")
def get_factory(gid: str, _u=Depends(_READ)):
    keys = ['gid','name','team_id','meta','created_at']
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid,name,team_id,meta,created_at FROM workmanship_factory_factories WHERE gid=%s", (gid,))
            row = _row(cur, keys)
            if not row: _not_found(gid)
            return {"data": row}


@router.patch("/factories/{gid}")
def update_factory(gid: str, body: UpdateFactoryBody, _u=Depends(_ADMIN)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "无更新字段")
    set_clause = ", ".join(f"{k}=%s" for k in updates)
    keys = ['gid','name','team_id','meta','created_at']
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_factory_factories SET {set_clause} WHERE gid=%s",
                list(updates.values()) + [gid]
            )
            cur.execute("SELECT gid,name,team_id,meta,created_at FROM workmanship_factory_factories WHERE gid=%s", (gid,))
            row = _row(cur, keys)
            if not row: _not_found(gid)
            conn.commit()
            return {"data": row}


@router.delete("/factories/{gid}", status_code=204)
def delete_factory(gid: str, _u=Depends(_ADMIN)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_factory_factories WHERE gid=%s", (gid,))
            if cur.rowcount == 0: _not_found(gid)
            conn.commit()


# ══════════════════════════════════════════════════════════════
# 工段
# ══════════════════════════════════════════════════════════════

@router.get("/factories/{factory_gid}/sections")
def list_sections(factory_gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_SEC_COLS} FROM workmanship_factory_factory_sections WHERE factory_gid=%s ORDER BY sort_order", (factory_gid,))
            return {"data": _rows(cur, _SEC_KEYS)}


@router.post("/factories/{factory_gid}/sections", status_code=201)
def create_section(factory_gid: str, body: CreateSectionBody, _u=Depends(_ADMIN)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO workmanship_factory_factory_sections (gid,name,factory_gid,sort_order,color,canvas_x,canvas_y,canvas_w,canvas_h) "
                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.name, factory_gid, body.sort_order, body.color,
                 body.canvas_x, body.canvas_y, body.canvas_w, body.canvas_h)
            )
            conn.commit()
            cur.execute(f"SELECT {_SEC_COLS} FROM workmanship_factory_factory_sections WHERE gid=%s", (gid,))
            return {"data": _row(cur, _SEC_KEYS)}


@router.patch("/factory_sections/{gid}")
def update_section(gid: str, body: UpdateSectionBody, _u=Depends(_ADMIN)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "无更新字段")
    set_clause = ", ".join(f"{k}=%s" for k in updates)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_factory_factory_sections SET {set_clause} WHERE gid=%s",
                list(updates.values()) + [gid]
            )
            cur.execute(f"SELECT {_SEC_COLS} FROM workmanship_factory_factory_sections WHERE gid=%s", (gid,))
            row = _row(cur, _SEC_KEYS)
            if not row: _not_found(gid)
            conn.commit()
            return {"data": row}


@router.delete("/factory_sections/{gid}", status_code=204)
def delete_section(gid: str, _u=Depends(_ADMIN)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_factory_factory_sections WHERE gid=%s", (gid,))
            if cur.rowcount == 0: _not_found(gid)
            conn.commit()


# ══════════════════════════════════════════════════════════════
# 工位
# ══════════════════════════════════════════════════════════════

@router.get("/factory_sections/{section_gid}/stations")
def list_stations(section_gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_STA_COLS} FROM workmanship_factory_factory_stations WHERE factory_section_gid=%s ORDER BY canvas_x", (section_gid,))
            return {"data": _rows(cur, _STA_KEYS)}


@router.post("/factory_sections/{section_gid}/stations", status_code=201)
def create_station(section_gid: str, body: CreateStationBody, _u=Depends(_ADMIN)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO workmanship_factory_factory_stations (gid,code,name,factory_section_gid,canvas_x,canvas_y,takt_time,height_mm) "
                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (gid, body.code, body.name, section_gid, body.canvas_x, body.canvas_y, body.takt_time, body.height_mm)
            )
            conn.commit()
            cur.execute(f"SELECT {_STA_COLS} FROM workmanship_factory_factory_stations WHERE gid=%s", (gid,))
            return {"data": _row(cur, _STA_KEYS)}


@router.patch("/factory_stations/{gid}")
def update_station(gid: str, body: UpdateStationBody, _u=Depends(_ADMIN)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "无更新字段")
    set_clause = ", ".join(f"{k}=%s" for k in updates)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE workmanship_factory_factory_stations SET {set_clause} WHERE gid=%s",
                list(updates.values()) + [gid]
            )
            cur.execute(f"SELECT {_STA_COLS} FROM workmanship_factory_factory_stations WHERE gid=%s", (gid,))
            row = _row(cur, _STA_KEYS)
            if not row: _not_found(gid)
            conn.commit()
            return {"data": row}


@router.delete("/factory_stations/{gid}", status_code=204)
def delete_station(gid: str, _u=Depends(_ADMIN)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_factory_factory_stations WHERE gid=%s", (gid,))
            if cur.rowcount == 0: _not_found(gid)
            conn.commit()


# ══════════════════════════════════════════════════════════════
# 工厂布局模板
# ══════════════════════════════════════════════════════════════

@router.get("/factories/{factory_gid}/layout_templates")
def list_layout_templates(factory_gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_LTPL_COLS} FROM workmanship_factory_factory_layout_templates WHERE factory_gid=%s ORDER BY created_at DESC",
                (factory_gid,)
            )
            return {"data": _rows(cur, _LTPL_KEYS)}


@router.post("/factories/{factory_gid}/layout_templates", status_code=201)
def create_layout_template(factory_gid: str, body: CreateLayoutTemplateBody, _u=Depends(_ADMIN)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO workmanship_factory_factory_layout_templates (gid,name,factory_gid,team_id,stations) "
                f"VALUES (%s,%s,%s,%s,%s)",
                (gid, body.name, factory_gid, body.team_id, json.dumps(body.stations))
            )
            conn.commit()
            cur.execute(f"SELECT {_LTPL_COLS} FROM workmanship_factory_factory_layout_templates WHERE gid=%s", (gid,))
            return {"data": _row(cur, _LTPL_KEYS)}


@router.get("/layout_templates/{gid}")
def get_layout_template(gid: str, _u=Depends(_READ)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_LTPL_COLS} FROM workmanship_factory_factory_layout_templates WHERE gid=%s", (gid,))
            row = _row(cur, _LTPL_KEYS)
            if not row: _not_found(gid)
            return {"data": row}


@router.patch("/layout_templates/{gid}")
def update_layout_template(gid: str, body: dict, _u=Depends(_ADMIN)):
    sets, vals = [], []
    for col in ('name', 'stations'):
        if col in body:
            sets.append(f"{col}=%s")
            vals.append(json.dumps(body[col]) if col == 'stations' else body[col])
    if not sets:
        raise HTTPException(400, "无更新字段")
    vals.append(gid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE workmanship_factory_factory_layout_templates SET {','.join(sets)} WHERE gid=%s", vals)
            cur.execute(f"SELECT {_LTPL_COLS} FROM workmanship_factory_factory_layout_templates WHERE gid=%s", (gid,))
            row = _row(cur, _LTPL_KEYS)
            if not row: _not_found(gid)
            conn.commit()
            return {"data": row}


@router.delete("/layout_templates/{gid}", status_code=204)
def delete_layout_template(gid: str, _u=Depends(_ADMIN)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_factory_factory_layout_templates WHERE gid=%s", (gid,))
            if cur.rowcount == 0: _not_found(gid)
            conn.commit()


@router.post("/layout_templates/{gid}/apply", status_code=201)
def apply_layout_template(gid: str, body: ApplyLayoutTemplateBody, _u=Depends(_ADMIN)):
    """将模板中的相对坐标工位批量创建到指定工段，返回创建的工位列表"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stations FROM workmanship_factory_factory_layout_templates WHERE gid=%s", (gid,))
            row = cur.fetchone()
            if not row: _not_found(gid)
            station_defs = row[0] or []

            created = []
            for s in station_defs:
                sgid = str(next_gid())
                abs_x = body.drop_x + s.get('rel_x', 0)
                abs_y = body.drop_y + s.get('rel_y', 0)
                cur.execute(
                    f"INSERT INTO workmanship_factory_factory_stations (gid,code,name,factory_section_gid,canvas_x,canvas_y,takt_time,height_mm) "
                    f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (sgid, s.get('code',''), s.get('name',''),
                     body.factory_section_gid, abs_x, abs_y,
                     s.get('takt_time', 60), s.get('height_mm', 1200))
                )
                cur.execute(f"SELECT {_STA_COLS} FROM workmanship_factory_factory_stations WHERE gid=%s", (sgid,))
                created.append(_row(cur, _STA_KEYS))
            conn.commit()
            return {"data": created}
