"""
backend/routers/_bop/pbom.py
─────────────────────────────
PBOM 变化点查询（场景 C 关联面板支撑）。
"""
from fastapi import APIRouter, Depends, HTTPException

from backend.db.connection import get_conn

from ._constants import _READ

router = APIRouter(prefix="/api/bop", tags=["bop"])


@router.get("/versions/{gid}/pbom-change-point")
def pbom_change_point(gid: str, _u=Depends(_READ)):
    """
    对比当前阶段与父阶段的 PBOM，返回变化点列表（只读）。
    稳定业务键：bom_row + vpps。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pbom_version_gid, parent_version_gid FROM workmanship_bop_bop_versions WHERE gid=%s",
                (gid,)
            )
            ver = cur.fetchone()
            if not ver:
                raise HTTPException(404, f"BOP 版本 {gid} 不存在")
            ver = dict(ver)

            cur_pbom_gid = ver.get('pbom_version_gid')
            parent_ver_gid = ver.get('parent_version_gid')

            if not cur_pbom_gid:
                return {"data": [], "reason": "当前版本未绑定 PBOM"}
            if not parent_ver_gid:
                return {"data": [], "reason": "当前版本无父版本，无从对比"}

            cur.execute(
                "SELECT pbom_version_gid FROM workmanship_bop_bop_versions WHERE gid=%s",
                (parent_ver_gid,)
            )
            parent_ver = cur.fetchone()
            ref_pbom_gid = dict(parent_ver)['pbom_version_gid'] if parent_ver else None

            if not ref_pbom_gid:
                return {"data": [], "reason": "父版本未绑定 PBOM，无从对比"}

            cur.execute(
                """
                SELECT gid, bom_row, vpps, title, part_no, quantity, unit,
                       node_type, updated_at
                FROM workmanship_bop_pbom
                WHERE snapshot_gid=%s AND is_deleted=FALSE
                """,
                (cur_pbom_gid,)
            )
            cur_rows = {
                (r['bom_row'], r['vpps']): dict(r)
                for r in cur.fetchall()
                if r['bom_row'] or r['vpps']
            }

            cur.execute(
                """
                SELECT gid, bom_row, vpps, title, part_no, quantity, unit,
                       node_type, updated_at
                FROM workmanship_bop_pbom
                WHERE snapshot_gid=%s AND is_deleted=FALSE
                """,
                (ref_pbom_gid,)
            )
            ref_rows = {
                (r['bom_row'], r['vpps']): dict(r)
                for r in cur.fetchall()
                if r['bom_row'] or r['vpps']
            }

            changes = []
            _COMPARE_FIELDS = ('title', 'part_no', 'quantity', 'unit', 'node_type')

            for key, cur_row in cur_rows.items():
                if key not in ref_rows:
                    changes.append({
                        'change_type': 'added',
                        'bom_row': cur_row.get('bom_row'),
                        'vpps': cur_row.get('vpps'),
                        'current': cur_row,
                        'reference': None,
                    })
                else:
                    ref_row = ref_rows[key]
                    diff = {
                        f: (cur_row.get(f), ref_row.get(f))
                        for f in _COMPARE_FIELDS
                        if cur_row.get(f) != ref_row.get(f)
                    }
                    if diff:
                        changes.append({
                            'change_type': 'modified',
                            'bom_row': cur_row.get('bom_row'),
                            'vpps': cur_row.get('vpps'),
                            'current': cur_row,
                            'reference': ref_row,
                            'diff': diff,
                        })

            for key, ref_row in ref_rows.items():
                if key not in cur_rows:
                    changes.append({
                        'change_type': 'deleted',
                        'bom_row': ref_row.get('bom_row'),
                        'vpps': ref_row.get('vpps'),
                        'current': None,
                        'reference': ref_row,
                    })

            return {
                "data": changes,
                "current_pbom_version_gid": cur_pbom_gid,
                "reference_pbom_version_gid": ref_pbom_gid,
                "summary": {
                    "added": sum(1 for c in changes if c['change_type'] == 'added'),
                    "modified": sum(1 for c in changes if c['change_type'] == 'modified'),
                    "deleted": sum(1 for c in changes if c['change_type'] == 'deleted'),
                },
            }
