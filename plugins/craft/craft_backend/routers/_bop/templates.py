"""
backend/routers/_bop/templates.py
───────────────────────────────────
模板管理：save-as-template + update-from。
"""
import json
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.utils.gid import next_gid

from ._constants import _WRITE, _VER_COLS, _VER_KEYS, _AI00_LEVEL, _SHARED_ENTITY_LINK_TYPES, _SKIP_LINK_TYPES
from ._helpers import _not_found, _sync_child_vpps, _deep_copy_entity

router = APIRouter(prefix="/api/bop", tags=["bop"])


class SaveAsTemplateBody(BaseModel):
    factory_gid: str
    template_name: str
    copy_operator: bool = False


@router.post("/versions/{src_gid}/save-as-template", status_code=201)
def save_as_template(src_gid: str, body: SaveAsTemplateBody, _u=Depends(_WRITE)):
    user_gid = _u.get('gid') if isinstance(_u, dict) else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (src_gid,))
            src_ver = cur.fetchone()
            if not src_ver:
                raise HTTPException(404, f"源版本 {src_gid} 不存在")
            src_ver = dict(src_ver)
            project_gid = src_ver.get('project_gid')

            if body.copy_operator:
                max_template_level = 3
            else:
                max_template_level = 2

            new_tmpl_gid = str(next_gid())
            cur.execute(
                f"INSERT INTO workmanship_bop_bop_versions "
                f"(gid,version_tag,bop_name,version_family_gid,"
                f" project_gid,factory_gid,maturity,takt_time,"
                f" status,meta,lifecycle_phase,lifecycle_state,visibility,version_type,owner_gid,change_note) "
                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (new_tmpl_gid, body.template_name, body.template_name, new_tmpl_gid,
                 project_gid, body.factory_gid,
                 src_ver.get('maturity', 'concept'), src_ver.get('takt_time', 60),
                 'active', json.dumps({}), 'init', json.dumps({}), 'team',
                 'template', user_gid, f'save-as-template from {src_gid}')
            )
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (new_tmpl_gid,))
            new_tmpl = dict(cur.fetchone())

            cur.execute(
                "SELECT gid, parent_gid, node_type, sort_order, level, ai00_level,"
                " title, vpps, vpps_desc, parent_bop_title, child_vpps, owner_gid, meta"
                " FROM workmanship_bop_bop_entries"
                " WHERE version_gid=%s AND is_deleted = FALSE"
                " ORDER BY sort_order",
                (src_gid,),
            )
            src_entries = [dict(r) for r in cur.fetchall()]

            if not src_entries:
                conn.commit()
                return {"data": new_tmpl, "entries_count": 0}

            filtered = [
                e for e in src_entries
                if _AI00_LEVEL.get(e['node_type'], 99) <= max_template_level
            ]
            gid_map_tmpl: Dict[str, str] = {e['gid']: str(next_gid()) for e in filtered}

            for e in filtered:
                new_gid_t  = gid_map_tmpl[e['gid']]
                new_par_t  = gid_map_tmpl.get(e['parent_gid']) if e['parent_gid'] else None
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entries "
                    "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                    " title, vpps, vpps_desc, parent_bop_title, child_vpps, owner_gid, meta) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (new_gid_t, new_tmpl_gid, new_par_t,
                     e['node_type'], e['sort_order'], e.get('level', 0),
                     _AI00_LEVEL.get(e['node_type']),
                     e.get('title'), e.get('vpps'), e.get('vpps_desc'),
                     e.get('parent_bop_title'),
                     json.dumps(e.get('child_vpps') or []),
                     e.get('owner_gid'), json.dumps(e.get('meta') or {}))
                )

            cur.execute(
                "SELECT entry_gid, link_type, entity_gid, is_primary, is_inherited"
                " FROM workmanship_bop_bop_entry_links"
                " WHERE version_gid=%s AND is_deleted = FALSE",
                (src_gid,),
            )
            src_links_tmpl = [dict(r) for r in cur.fetchall()]

            for lnk in src_links_tmpl:
                if lnk['link_type'] in _SKIP_LINK_TYPES:
                    continue
                new_entry_gid_t = gid_map_tmpl.get(lnk['entry_gid'])
                if not new_entry_gid_t:
                    continue
                if lnk['link_type'] in _SHARED_ENTITY_LINK_TYPES:
                    new_ent_gid_t = lnk['entity_gid']
                else:
                    new_ent_gid_t = _deep_copy_entity(
                        cur, lnk['link_type'], lnk['entity_gid'], project_gid
                    )
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entry_links "
                    "(gid, entry_gid, version_gid, link_type, entity_gid,"
                    " is_primary, is_inherited) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (str(next_gid()), new_entry_gid_t, new_tmpl_gid,
                     lnk['link_type'], new_ent_gid_t,
                     lnk['is_primary'], lnk.get('is_inherited', False)),
                )

            parent_gids_tmpl: set = set()
            for e in filtered:
                if e.get('parent_gid') and gid_map_tmpl.get(e['parent_gid']):
                    parent_gids_tmpl.add(gid_map_tmpl[e['parent_gid']])
            for pg in parent_gids_tmpl:
                _sync_child_vpps(cur, pg, new_tmpl_gid)

            # 补充：工位的 child_vpps 加入源 BOP 下所有工序的 vpps
            # （工序 ai00_level=4，被 filtered 排除，_sync_child_vpps 找不到）
            src_child_map: Dict[str, list] = {}
            for e in src_entries:
                pg = e.get('parent_gid')
                if pg:
                    src_child_map.setdefault(pg, []).append(e)

            station_entries = [e for e in filtered if e['node_type'] == 'station_process']
            for stn in station_entries:
                # BFS 收集源 BOP 该工位下的所有 process 节点
                proc_src: list = []
                queue = list(src_child_map.get(stn['gid'], []))
                while queue:
                    child = queue.pop(0)
                    if child['node_type'] == 'process':
                        proc_src.append(child)
                    queue.extend(src_child_map.get(child['gid'], []))

                if not proc_src:
                    continue

                # 查询有效 vpps：entry.vpps → bop_process.vpps → bop_process.process_code
                proc_gids = [p['gid'] for p in proc_src]
                ph = ','.join(['%s'] * len(proc_gids))
                cur.execute(
                    f"SELECT e.gid,"
                    f" COALESCE(NULLIF(e.vpps,''), pr.vpps, pr.process_code) AS eff_vpps,"
                    f" e.title"
                    f" FROM workmanship_bop_bop_entries e"
                    f" LEFT JOIN workmanship_bop_bop_entry_links lnk"
                    f"   ON lnk.entry_gid=e.gid AND lnk.is_primary=TRUE"
                    f"   AND lnk.link_type='bop_process' AND lnk.is_deleted=FALSE"
                    f" LEFT JOIN workmanship_bop_bop_process pr ON pr.gid=lnk.entity_gid"
                    f" WHERE e.gid IN ({ph})",
                    proc_gids,
                )
                proc_vpps_list = [
                    {"vpps": r['eff_vpps'], "node_type": "process", "title": r['title'] or ''}
                    for r in cur.fetchall() if r['eff_vpps']
                ]

                if not proc_vpps_list:
                    continue

                # 合并到模板工位的 child_vpps（追加到已有条目之后）
                tmpl_stn_gid = gid_map_tmpl[stn['gid']]
                cur.execute(
                    "SELECT child_vpps FROM workmanship_bop_bop_entries WHERE gid=%s",
                    (tmpl_stn_gid,),
                )
                row = cur.fetchone()
                existing = row['child_vpps'] if row and row['child_vpps'] else []
                if not isinstance(existing, list):
                    existing = json.loads(existing) if existing else []
                merged = list(existing) + proc_vpps_list
                cur.execute(
                    "UPDATE workmanship_bop_bop_entries SET child_vpps=%s WHERE gid=%s",
                    (json.dumps(merged), tmpl_stn_gid),
                )

            conn.commit()
            return {"data": new_tmpl, "entries_count": len(gid_map_tmpl)}


@router.post("/versions/{template_gid}/update-from/{src_gid}", status_code=200)
def update_template_from(template_gid: str, src_gid: str, _u=Depends(_WRITE)):
    user_gid = _u.get('gid') if isinstance(_u, dict) else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (template_gid,))
            tmpl_ver = cur.fetchone()
            if not tmpl_ver:
                raise HTTPException(404, f"模板版本 {template_gid} 不存在")
            tmpl_ver = dict(tmpl_ver)
            if tmpl_ver.get('version_type') != 'template':
                raise HTTPException(400, "目标版本不是 template 类型")
            if tmpl_ver.get('owner_gid') and tmpl_ver['owner_gid'] != user_gid:
                raise HTTPException(403, "只有模板 owner 可以执行 update-from")

            cur.execute(
                "UPDATE workmanship_bop_bop_entry_links SET is_deleted=TRUE, deleted_at=NOW()"
                " WHERE version_gid=%s",
                (template_gid,)
            )
            cur.execute(
                "UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE, deleted_at=NOW()"
                " WHERE version_gid=%s",
                (template_gid,)
            )

            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (src_gid,))
            src_ver = cur.fetchone()
            if not src_ver:
                raise HTTPException(404, f"源版本 {src_gid} 不存在")
            project_gid = dict(src_ver).get('project_gid')

            cur.execute(
                "SELECT gid, parent_gid, node_type, sort_order, level, ai00_level,"
                " title, vpps, vpps_desc, parent_bop_title, child_vpps, owner_gid, meta"
                " FROM workmanship_bop_bop_entries"
                " WHERE version_gid=%s AND is_deleted = FALSE ORDER BY sort_order",
                (src_gid,),
            )
            src_entries = [dict(r) for r in cur.fetchall()]
            gid_map_uf: Dict[str, str] = {e['gid']: str(next_gid()) for e in src_entries}

            for e in src_entries:
                new_gid_uf = gid_map_uf[e['gid']]
                new_par_uf = gid_map_uf.get(e['parent_gid']) if e['parent_gid'] else None
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entries "
                    "(gid, version_gid, parent_gid, node_type, sort_order, level, ai00_level,"
                    " title, vpps, vpps_desc, parent_bop_title, child_vpps, owner_gid, meta) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (new_gid_uf, template_gid, new_par_uf,
                     e['node_type'], e['sort_order'], e.get('level', 0),
                     _AI00_LEVEL.get(e['node_type']),
                     e.get('title'), e.get('vpps'), e.get('vpps_desc'),
                     e.get('parent_bop_title'),
                     json.dumps(e.get('child_vpps') or []),
                     e.get('owner_gid'), json.dumps(e.get('meta') or {}))
                )

            cur.execute(
                "SELECT entry_gid, link_type, entity_gid, is_primary, is_inherited"
                " FROM workmanship_bop_bop_entry_links"
                " WHERE version_gid=%s AND is_deleted = FALSE",
                (src_gid,),
            )
            for lnk in cur.fetchall():
                lnk = dict(lnk)
                if lnk['link_type'] in _SKIP_LINK_TYPES:
                    continue
                new_ent_uf = gid_map_uf.get(lnk['entry_gid'])
                if not new_ent_uf:
                    continue
                if lnk['link_type'] in _SHARED_ENTITY_LINK_TYPES:
                    ent_gid_uf = lnk['entity_gid']
                else:
                    ent_gid_uf = _deep_copy_entity(
                        cur, lnk['link_type'], lnk['entity_gid'], project_gid
                    )
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entry_links "
                    "(gid, entry_gid, version_gid, link_type, entity_gid,"
                    " is_primary, is_inherited) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (str(next_gid()), new_ent_uf, template_gid,
                     lnk['link_type'], ent_gid_uf,
                     lnk['is_primary'], lnk.get('is_inherited', False)),
                )

            parent_gids_uf: set = set()
            for e in src_entries:
                if e.get('parent_gid') and gid_map_uf.get(e['parent_gid']):
                    parent_gids_uf.add(gid_map_uf[e['parent_gid']])
            for pg in parent_gids_uf:
                _sync_child_vpps(cur, pg, template_gid)

            cur.execute(
                f"UPDATE workmanship_bop_bop_versions SET updated_at=NOW() WHERE gid=%s",
                (template_gid,)
            )
            cur.execute(f"SELECT {_VER_COLS} FROM workmanship_bop_bop_versions WHERE gid=%s", (template_gid,))
            updated = dict(cur.fetchone())
            conn.commit()
            return {"data": updated, "entries_count": len(gid_map_uf)}
