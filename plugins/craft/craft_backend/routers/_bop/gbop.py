"""
backend/routers/_bop/gbop.py
────────────────────────────
GBOP 匹配 preview / confirm / auto-link。
"""
import json
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.utils.gid import next_gid

from ._constants import _WRITE, _READ, _SKIP_LINK_TYPES, _SHARED_ENTITY_LINK_TYPES
from ._helpers import _deep_copy_entity

router = APIRouter(prefix="/api/bop", tags=["bop"])

# ── 幂等补丁（首次请求时执行）────────────────────────────────────
_gbop_migrated = False

def _safe_add_column(cur, sql: str) -> None:
    """执行 ALTER TABLE ADD COLUMN，忽略列已存在错误（1060）"""
    try:
        cur.execute(sql)
    except Exception as e:
        if getattr(e, "args", None) and len(e.args) > 0 and e.args[0] == 1060:
            return
        raise


def _ensure_gbop_tables():
    global _gbop_migrated
    if _gbop_migrated:
        return
    print("[gbop] running _ensure_gbop_tables...")
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # workmanship_bop_pbom 软删除列（gbop_match_preview 需要）
                _safe_add_column(
                    cur,
                    "ALTER TABLE workmanship_bop_pbom "
                    "ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0"
                )
                print("[gbop] is_deleted column OK")
                # gbop_match_staging 中间表
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS workmanship_bop_gbop_match_staging (
                        gid                CHAR(36) PRIMARY KEY,
                        pbom_version_gid   CHAR(36) NOT NULL,
                        gbop_entry_gid     CHAR(36),
                        pbom_entry_gid     CHAR(36) NOT NULL,
                        bop_version_gid    CHAR(36),
                        match_status       TEXT NOT NULL DEFAULT 'pending',
                        extra_entry_gids   JSON NOT NULL DEFAULT (JSON_ARRAY()),
                        created_entry_gid  CHAR(36),
                        confirmed_by       TEXT,
                        confirmed_at       DATETIME(6),
                        created_by         TEXT,
                        created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        UNIQUE KEY uq_gbop_staging (pbom_version_gid, pbom_entry_gid)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_gbop_staging_pbom_ver "
                    "ON workmanship_bop_gbop_match_staging(pbom_version_gid)"
                )
                print("[gbop] gbop_match_staging table OK")
                # 补列（旧表可能缺少）
                _safe_add_column(
                    cur,
                    "ALTER TABLE workmanship_bop_gbop_match_staging "
                    "ADD COLUMN extra_entry_gids JSON NOT NULL DEFAULT (JSON_ARRAY())"
                )
                _safe_add_column(
                    cur,
                    "ALTER TABLE workmanship_bop_gbop_match_staging "
                    "ADD COLUMN created_entry_gid TEXT"
                )
                print("[gbop] gbop_match_staging columns patched")
            conn.commit()
        _gbop_migrated = True
        print("[gbop] _ensure_gbop_tables done")
    except Exception as e:
        import traceback
        print(f"[gbop] migration error: {e}")
        traceback.print_exc()


class GbopMatchConfirmItem(BaseModel):
    pbom_entry_gid: str
    gbop_entry_gid: str          # 主操作（is_primary=True pbom_part link）
    action: Literal['confirm', 'skip']
    extra_entry_gids: List[str] = []   # 附加操作（is_primary=False pbom_part link）


class GbopMatchConfirmBody(BaseModel):
    matches: List[GbopMatchConfirmItem]


@router.get("/pbom-versions/{pbom_gid}/gbop-match-preview")
def gbop_match_preview(pbom_gid: str, _u=Depends(_READ)):
    """
    车型工序导航卡：返回 PBOM 零件与 GBOP 工序/操作的匹配预览（只读）。
    按 vpps 在 GBOP 参考版本中匹配工序/操作 entry，合并已有确认状态。
    """
    print(f"[gbop] gbop_match_preview pbom_gid={pbom_gid!r}")
    _ensure_gbop_tables()
    with get_conn() as conn:
        with conn.cursor() as cur:
            print(f"[gbop] step1: query pbom_versions")
            cur.execute("SELECT gid, status FROM workmanship_bop_pbom_versions WHERE gid=%s", (pbom_gid,))
            pbom_ver = cur.fetchone()
            if not pbom_ver:
                raise HTTPException(404, f"PBOM 版本 {pbom_gid} 不存在")
            print(f"[gbop] step2: pbom_ver status={pbom_ver['status']!r}")

            print(f"[gbop] step3: query workmanship_bop_pbom (is_deleted)")
            cur.execute(
                """
                SELECT p.gid, p.vpps, p.title, p.part_no, p.bom_row,
                       p.parent_gid, p.level,
                       p.parent_bom_row, p.parent_vpps
                FROM workmanship_bop_pbom p
                WHERE p.snapshot_gid=%s
                  AND p.is_deleted = FALSE
                ORDER BY p.level , p.bom_row , p.vpps 
                """,
                (pbom_gid,),
            )
            pbom_parts = [dict(r) for r in cur.fetchall()]
            print(f"[gbop] step4: pbom_parts count={len(pbom_parts)}")

            if not pbom_parts:
                return {"data": [], "pbom_version_gid": pbom_gid}

            # 若 parent_gid 为空，用 parent_bom_row → bom_row 推算层级关系
            bom_row_to_gid = {p['bom_row']: p['gid'] for p in pbom_parts if p.get('bom_row')}
            vpps_to_gid    = {}
            for p in pbom_parts:
                if p.get('vpps') and p['vpps'] not in vpps_to_gid:
                    vpps_to_gid[p['vpps']] = p['gid']
            resolved = 0
            for p in pbom_parts:
                if not p.get('parent_gid'):
                    if p.get('parent_bom_row'):
                        p['parent_gid'] = bom_row_to_gid.get(p['parent_bom_row'])
                        if p['parent_gid']: resolved += 1
                    elif p.get('parent_vpps'):
                        p['parent_gid'] = vpps_to_gid.get(p['parent_vpps'])
                        if p['parent_gid']: resolved += 1
            print(f"[gbop] step4b: parent_gid resolved from bom_row/vpps: {resolved}/{len(pbom_parts)}"
                  f" | sample parent_bom_rows={[p.get('parent_bom_row') for p in pbom_parts[:3]]}")

            print(f"[gbop] step5: query bop_entries (template)")
            cur.execute(
                """
                SELECT e.gid AS entry_gid, e.vpps, e.node_type, e.title, e.version_gid,
                       COALESCE(
                           (SELECT l.is_primary FROM workmanship_bop_bop_entry_links l
                            WHERE l.entry_gid = e.gid AND l.link_type='pbom_part'
                              AND l.is_deleted=FALSE LIMIT 1),
                           FALSE
                       ) AS is_primary_feed
                FROM workmanship_bop_bop_entries e
                JOIN workmanship_bop_bop_versions v ON v.gid = e.version_gid
                WHERE v.version_type = 'template'
                  AND v.is_deleted = FALSE
                  AND e.is_deleted = FALSE
                  AND e.vpps IS NOT NULL
                """,
            )
            gbop_entries = [dict(r) for r in cur.fetchall()]
            print(f"[gbop] step6: gbop_entries count={len(gbop_entries)}")

            vpps_to_gbop: dict = {}
            for ge in gbop_entries:
                vpps_to_gbop.setdefault(ge['vpps'], []).append(ge)

            print(f"[gbop] step7: query gbop_match_staging")
            cur.execute(
                "SELECT pbom_entry_gid, gbop_entry_gid, match_status"
                " FROM workmanship_bop_gbop_match_staging"
                " WHERE pbom_version_gid=%s",
                (pbom_gid,),
            )
            staging_map: dict = {
                r['pbom_entry_gid']: dict(r) for r in cur.fetchall()
            }
            print(f"[gbop] step8: staging_map size={len(staging_map)}, building result")
            result = []
            for part in pbom_parts:
                vpps = part.get('vpps')
                matched = vpps_to_gbop.get(vpps, []) if vpps else []
                if len(matched) == 0:
                    match_status = 'unmatched'
                elif len(matched) == 1:
                    match_status = 'matched_1'
                else:
                    match_status = 'matched_n'

                staging = staging_map.get(part['gid'])
                confirmed_status = staging['match_status'] if staging else None

                result.append({
                    'pbom_entry_gid': part['gid'],
                    'vpps': vpps,
                    'part_title': part.get('title'),
                    'part_number': part.get('part_no'),
                    'parent_gid': part.get('parent_gid'),
                    'level': part.get('level'),
                    'match_status': match_status,
                    'confirmed_status': confirmed_status,
                    'gbop_matches': [
                        {'entry_gid': ge['entry_gid'], 'node_type': ge['node_type'],
                         'title': ge['title'], 'version_gid': ge['version_gid'],
                         'is_primary_feed': ge.get('is_primary_feed', False)}
                        for ge in matched
                    ],
                })

            # Step 9: Also check workmanship_bop_gbop_nav_bindings (new Auto-Link system)
            try:
                cur.execute(
                    """
                    SELECT pbom_entry_gid, COUNT(*) AS cnt
                    FROM workmanship_bop_gbop_nav_bindings
                    WHERE pbom_version_gid = %s
                    GROUP BY pbom_entry_gid
                    """,
                    (pbom_gid,),
                )
                nav_cnts = {r['pbom_entry_gid']: r['cnt'] for r in cur.fetchall()}
                for item in result:
                    cnt = nav_cnts.get(item['pbom_entry_gid'], 0)
                    if cnt > 0:
                        if item['match_status'] == 'unmatched':
                            item['match_status'] = 'matched_1' if cnt == 1 else 'matched_n'
                        if not item['confirmed_status']:
                            item['confirmed_status'] = 'confirmed'
            except Exception:
                pass  # table may not exist yet

            print(f"[gbop] step9: returning {len(result)} items OK")
            return {"data": result, "pbom_version_gid": pbom_gid}


@router.post("/pbom-versions/{pbom_gid}/gbop-match-confirm", status_code=200)
def gbop_match_confirm(pbom_gid: str, body: GbopMatchConfirmBody, _u=Depends(_WRITE)):
    """
    整批确认匹配结果，幂等写入 gbop_match_staging。
    bop_version_gid 为 NULL，由后续 auto-link 填入。
    """
    _ensure_gbop_tables()
    user_gid = _u.get('gid') if isinstance(_u, dict) else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid FROM workmanship_bop_pbom_versions WHERE gid=%s", (pbom_gid,))
            if not cur.fetchone():
                raise HTTPException(404, f"PBOM 版本 {pbom_gid} 不存在")

            for item in body.matches:
                status_val = 'confirmed' if item.action == 'confirm' else 'skipped'
                cur.execute(
                    """
                    INSERT INTO workmanship_bop_gbop_match_staging
                        (gid, pbom_version_gid, gbop_entry_gid, pbom_entry_gid,
                         match_status, extra_entry_gids, confirmed_by, confirmed_at, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),%s)
                    ON DUPLICATE KEY UPDATE
                        gbop_entry_gid    = VALUES(gbop_entry_gid),
                        match_status      = VALUES(match_status),
                        extra_entry_gids  = VALUES(extra_entry_gids),
                        confirmed_by      = VALUES(confirmed_by),
                        confirmed_at      = NOW()
                    """,
                    (str(next_gid()), pbom_gid,
                     item.gbop_entry_gid, item.pbom_entry_gid,
                     status_val, json.dumps(item.extra_entry_gids), user_gid, user_gid),
                )
            conn.commit()
            return {"ok": True, "count": len(body.matches)}


@router.post("/versions/{bop_gid}/gbop-auto-link", status_code=201)
def gbop_auto_link(bop_gid: str, _u=Depends(_WRITE)):
    """
    BOP 版本创建后，从 gbop_match_staging 批量写入 bop_entries + 实体表（三表联动）。
    幂等：created_entry_gid IS NULL 的记录才处理，避免重复执行。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT project_gid, pbom_version_gid FROM workmanship_bop_bop_versions WHERE gid=%s",
                (bop_gid,)
            )
            bop_ver = cur.fetchone()
            if not bop_ver:
                raise HTTPException(404, f"BOP 版本 {bop_gid} 不存在")
            bop_ver = dict(bop_ver)
            pbom_version_gid = bop_ver.get('pbom_version_gid')
            project_gid = bop_ver.get('project_gid')

            if not pbom_version_gid:
                raise HTTPException(400, "BOP 版本未绑定 pbom_version_gid")

            cur.execute(
                """
                SELECT gid, gbop_entry_gid, pbom_entry_gid, extra_entry_gids
                FROM workmanship_bop_gbop_match_staging
                WHERE pbom_version_gid=%s
                  AND match_status='confirmed'
                  AND created_entry_gid IS NULL
                """,
                (pbom_version_gid,),
            )
            staging_rows = [dict(r) for r in cur.fetchall()]

            if not staging_rows:
                return {"ok": True, "count": 0}

            created_entries = []

            for row in staging_rows:
                gbop_entry_gid = row['gbop_entry_gid']
                pbom_entry_gid = row['pbom_entry_gid']

                cur.execute(
                    "SELECT gid, parent_gid, node_type, sort_order, level, ai00_level,"
                    " title, vpps, vpps_desc, parent_bop_title, child_vpps, version_gid"
                    " FROM workmanship_bop_bop_entries WHERE gid=%s AND is_deleted=FALSE",
                    (gbop_entry_gid,),
                )
                gbop_entry = cur.fetchone()
                if not gbop_entry:
                    continue
                gbop_entry = dict(gbop_entry)

                new_entry_gid = str(next_gid())
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entries "
                    "(gid, version_gid, node_type, sort_order, level, ai00_level,"
                    " title, vpps, vpps_desc, child_vpps, meta) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}')",
                    (new_entry_gid, bop_gid,
                     gbop_entry['node_type'], gbop_entry['sort_order'],
                     gbop_entry.get('level', 0), gbop_entry.get('ai00_level', 5),
                     gbop_entry.get('title'), gbop_entry.get('vpps'),
                     gbop_entry.get('vpps_desc'),
                     json.dumps(gbop_entry.get('child_vpps') or []))
                )

                cur.execute(
                    "SELECT link_type, entity_gid, is_primary, is_inherited"
                    " FROM workmanship_bop_bop_entry_links"
                    " WHERE entry_gid=%s AND is_deleted=FALSE",
                    (gbop_entry_gid,),
                )
                gbop_links = [dict(r) for r in cur.fetchall()]

                for lnk in gbop_links:
                    if lnk['link_type'] in _SKIP_LINK_TYPES:
                        continue
                    if lnk['link_type'] in _SHARED_ENTITY_LINK_TYPES:
                        new_ent_gid = lnk['entity_gid']
                    else:
                        new_ent_gid = _deep_copy_entity(
                            cur, lnk['link_type'], lnk['entity_gid'], project_gid
                        )
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_entry_links "
                        "(gid, entry_gid, version_gid, link_type, entity_gid,"
                        " is_primary, is_inherited) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (str(next_gid()), new_entry_gid, bop_gid,
                         lnk['link_type'], new_ent_gid,
                         lnk['is_primary'], lnk.get('is_inherited', False)),
                    )

                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entry_links "
                    "(gid, entry_gid, version_gid, link_type, entity_gid,"
                    " is_primary, is_inherited) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (str(next_gid()), new_entry_gid, bop_gid,
                     'pbom_part', pbom_entry_gid, False, False),
                )

                cur.execute(
                    "UPDATE workmanship_bop_gbop_match_staging "
                    "SET bop_version_gid=%s, created_entry_gid=%s "
                    "WHERE gid=%s",
                    (bop_gid, new_entry_gid, row['gid']),
                )

                # 处理附加操作 extra_entry_gids（is_primary=False pbom_part link）
                extra_gids = row.get('extra_entry_gids') or []
                if isinstance(extra_gids, str):
                    extra_gids = json.loads(extra_gids)
                for extra_gbop_gid in extra_gids:
                    cur.execute(
                        "SELECT gid, node_type, sort_order, level, ai00_level,"
                        " title, vpps, vpps_desc, child_vpps, version_gid"
                        " FROM workmanship_bop_bop_entries WHERE gid=%s AND is_deleted=FALSE",
                        (extra_gbop_gid,),
                    )
                    extra_ge = cur.fetchone()
                    if not extra_ge:
                        continue
                    extra_ge = dict(extra_ge)

                    extra_entry_gid = str(next_gid())
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_entries "
                        "(gid, version_gid, node_type, sort_order, level, ai00_level,"
                        " title, vpps, vpps_desc, child_vpps, meta) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}')",
                        (extra_entry_gid, bop_gid,
                         extra_ge['node_type'], extra_ge['sort_order'],
                         extra_ge.get('level', 0), extra_ge.get('ai00_level', 5),
                         extra_ge.get('title'), extra_ge.get('vpps'),
                         extra_ge.get('vpps_desc'),
                         json.dumps(extra_ge.get('child_vpps') or []))
                    )

                    cur.execute(
                        "SELECT link_type, entity_gid, is_primary, is_inherited"
                        " FROM workmanship_bop_bop_entry_links"
                        " WHERE entry_gid=%s AND is_deleted=FALSE",
                        (extra_gbop_gid,),
                    )
                    for lnk in [dict(r) for r in cur.fetchall()]:
                        if lnk['link_type'] in _SKIP_LINK_TYPES:
                            continue
                        if lnk['link_type'] in _SHARED_ENTITY_LINK_TYPES:
                            ent_gid = lnk['entity_gid']
                        else:
                            ent_gid = _deep_copy_entity(
                                cur, lnk['link_type'], lnk['entity_gid'], project_gid
                            )
                        cur.execute(
                            "INSERT INTO workmanship_bop_bop_entry_links "
                            "(gid, entry_gid, version_gid, link_type, entity_gid,"
                            " is_primary, is_inherited) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (str(next_gid()), extra_entry_gid, bop_gid,
                             lnk['link_type'], ent_gid,
                             lnk['is_primary'], lnk.get('is_inherited', False)),
                        )

                    # pbom_part link（附加操作，is_primary=False）
                    cur.execute(
                        "INSERT INTO workmanship_bop_bop_entry_links "
                        "(gid, entry_gid, version_gid, link_type, entity_gid,"
                        " is_primary, is_inherited) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (str(next_gid()), extra_entry_gid, bop_gid,
                         'pbom_part', pbom_entry_gid, False, False),
                    )

                    created_entries.append(extra_entry_gid)

                created_entries.append(new_entry_gid)

            conn.commit()
            return {"ok": True, "count": len(created_entries),
                    "created_entry_gids": created_entries}


@router.get("/pbom-versions")
def list_pbom_versions(project_gid: str, _u=Depends(_READ)):
    """列出指定项目下 status='ready' 的 PBOM 版本，供车型工序导航卡选择。"""
    print(f"[gbop] list_pbom_versions project_gid={project_gid!r}")
    _ensure_gbop_tables()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT gid,
                       COALESCE(NULLIF(name,''), NULLIF(version_tag,''), gid) AS title,
                       status, created_at
                FROM workmanship_bop_pbom_versions
                WHERE project_gid=%s AND status='ready'
                ORDER BY created_at DESC
                """,
                (project_gid,),
            )
            rows = [dict(r) for r in cur.fetchall()]
            print(f"[gbop] list_pbom_versions -> {len(rows)} versions")
            return {"data": rows}
