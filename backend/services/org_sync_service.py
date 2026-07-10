"""
backend/services/org_sync_service.py
──────────────────────────────────────
飞书组织结构自动同步：
  - sync_user_departments(user_gid, department_ids)  登录时调用，同步该用户所在部门树（最多2级）
  - sync_all_from_feishu()                           超管手动触发，全量拉取飞书成员+部门
"""
from __future__ import annotations

import logging

from backend.db.connection import get_conn, new_gid
from backend.services.feishu_service import feishu_service

_log = logging.getLogger(__name__)


def _upsert_team(dept_id: str, name: str, parent_team_gid: str | None = None) -> str:
    """
    按 feishu_dept_id upsert teams 表。
    返回该团队的 gid。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid FROM workmanship_auth_teams WHERE feishu_dept_id = %s", (dept_id,)
            )
            row = cur.fetchone()
            if row:
                # 更新名称和父级（可能变化）
                cur.execute(
                    "UPDATE workmanship_auth_teams SET name=%s, parent_team_gid=%s WHERE feishu_dept_id=%s",
                    (name, parent_team_gid, dept_id),
                )
                return row["gid"]
            else:
                gid = new_gid()
                cur.execute(
                    """INSERT INTO workmanship_auth_teams (gid, name, feishu_dept_id, parent_team_gid)
                       VALUES (%s, %s, %s, %s)""",
                    (gid, name, dept_id, parent_team_gid),
                )
                return gid


def _assign_user_team(user_gid: str, team_gid: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_auth_users SET team_id=%s, updated_at=NOW() WHERE gid=%s",
                (team_gid, user_gid),
            )


def sync_user_departments(user_gid: str, department_ids: list) -> None:
    """
    登录时调用：同步用户所在部门树（最多走两级，即部门本身 + parent + grandparent）。
    将用户 team_id 设为其主部门。
    """
    if not department_ids:
        return

    primary_dept_id = department_ids[0]
    _log.info("sync_user_departments: user=%s dept=%s", user_gid, primary_dept_id)

    # 收集最多3级部门链（从当前部门往上）
    dept_chain = []   # [(dept_id, name), ...] 从子到父
    dept_id = primary_dept_id
    for _ in range(3):
        if not dept_id or dept_id in ("0", "od-0"):
            break
        info = feishu_service.get_department(dept_id)
        if not info:
            _log.warning("sync_user_departments: get_department(%s) 返回 None，停止向上遍历", dept_id)
            break
        dept_chain.append(info)
        dept_id = info.get("parent_department_id", "")

    if not dept_chain:
        _log.warning("sync_user_departments: 未获取到任何部门信息，跳过（user=%s）", user_gid)
        return

    # 从最顶层开始 upsert（保证父级先存在）
    parent_gid = None
    for info in reversed(dept_chain):
        gid = _upsert_team(info["dept_id"], info["name"], parent_gid)
        parent_gid = gid

    # 主部门 gid = 最底层（dept_chain[0]）
    primary_team_gid = _upsert_team(dept_chain[0]["dept_id"], dept_chain[0]["name"])
    _assign_user_team(user_gid, primary_team_gid)
    _log.info("sync_user_departments: 完成，user=%s team=%s", user_gid, primary_team_gid)


def sync_depts_only_to_db() -> dict:
    """
    仅同步飞书部门到 workmanship_auth_teams（不拉用户）。
    每层 BFS 完成后立即写库（增量），无需等待全部 BFS 跑完。
    返回 {dept_synced: int}
    """
    dept_gid_map: dict = {}   # open_id → team gid（累积，用于设父级）
    total_synced = 0

    # 先读已有部门，避免重复 insert
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid, feishu_dept_id FROM workmanship_auth_teams WHERE feishu_dept_id IS NOT NULL"
                )
                for row in cur.fetchall():
                    dept_gid_map[row["feishu_dept_id"]] = row["gid"]
    except Exception as e:
        _log.warning("sync_depts_only: read existing teams: %s", e)

    def _on_level(level_depts: list):
        nonlocal total_synced
        if not level_depts:
            return

        # ── 批量 upsert（一次事务）──────────────────────────────────────
        rows_to_insert = []
        for dept in level_depts:
            oid  = dept["open_id"]
            name = dept["name"] or oid
            if oid not in dept_gid_map:
                rows_to_insert.append((new_gid(), name, oid))

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if rows_to_insert:
                        cur.executemany(
                            "INSERT INTO workmanship_auth_teams (gid, name, feishu_dept_id) "
                            "VALUES (%s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE name = VALUES(name)",
                            rows_to_insert,
                        )
                    # 把本层所有部门的 gid 刷新到 map（含已存在的）
                    _dept_ids = [d["open_id"] for d in level_depts]
                    _dph = ",".join(["%s"] * len(_dept_ids))
                    cur.execute(
                        f"SELECT gid, feishu_dept_id FROM workmanship_auth_teams WHERE feishu_dept_id IN ({_dph})",
                        _dept_ids,
                    )
                    for row in cur.fetchall():
                        dept_gid_map[row["feishu_dept_id"]] = row["gid"]
                conn.commit()
        except Exception as e:
            print(f"[sync_depts_only] batch upsert 失败: {e}", flush=True)
            return

        # ── 批量设父级（一次事务）──────────────────────────────────────
        parent_updates = []
        for dept in level_depts:
            parent_oid = dept.get("parent_open_id")
            team_gid   = dept_gid_map.get(dept["open_id"])
            parent_gid = dept_gid_map.get(parent_oid) if parent_oid else None
            if team_gid and parent_gid:
                parent_updates.append((parent_gid, team_gid))

        if parent_updates:
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.executemany(
                            "UPDATE workmanship_auth_teams SET parent_team_gid=%s WHERE gid=%s",
                            parent_updates,
                        )
                    conn.commit()
            except Exception as e:
                print(f"[sync_depts_only] batch parent update 失败: {e}", flush=True)

        total_synced += len(level_depts)
        print(f"[sync_depts_only] 已写入本层 {len(level_depts)} 个，累计 {total_synced} 个", flush=True)

    feishu_service.sync_departments_only(level_callback=_on_level, max_depth=5)
    print(f"[sync_depts_only] 全部完成，共同步 {total_synced} 个部门", flush=True)
    return {"dept_synced": total_synced}


def sync_all_from_feishu(root_dept_id: str | None = None) -> dict:
    """
    同步飞书组织到 AI00 teams 表。
    root_dept_id: 指定根部门（open_department_id），只同步该子树；为 None 时全量同步。
    只创建新用户（system_role=external），不降权已有用户。
    返回统计 {created, updated, dept_synced}
    """
    from backend.services.user_service import get_or_create

    if root_dept_id:
        result = feishu_service.sync_org_structure_subtree(root_dept_id)
    else:
        result = feishu_service.sync_org_structure()
    departments = result.get("departments", [])
    users       = result.get("users", [])
    stats = {"created": 0, "updated": 0, "dept_synced": 0,
             "departments": len(departments)}

    # ── 1. Upsert 所有部门到 teams（两轮：先建，再设父级）──────────────────
    dept_gid_map: dict = {}
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT gid, feishu_dept_id FROM workmanship_auth_teams WHERE feishu_dept_id IS NOT NULL"
                )
                for row in cur.fetchall():
                    dept_gid_map[row["feishu_dept_id"]] = row["gid"]
    except Exception as e:
        _log.warning("sync_all: read existing teams: %s", e)

    for dept in departments:
        oid  = dept["open_id"]
        name = dept["name"] or oid
        existing_gid = dept_gid_map.get(oid)
        try:
            gid = _upsert_team(oid, name, parent_team_gid=None)
            dept_gid_map[oid] = gid
            if not existing_gid:
                _log.info("sync_all: new team %s (%s)", name, oid)
        except Exception as e:
            _log.warning("sync_all upsert team %s: %s", oid, e)

    # 第二轮：设 parent_team_gid
    for dept in departments:
        parent_oid = dept.get("parent_open_id")
        if not parent_oid:
            continue
        team_gid   = dept_gid_map.get(dept["open_id"])
        parent_gid = dept_gid_map.get(parent_oid)
        if team_gid and parent_gid:
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE workmanship_auth_teams "
                            "SET parent_team_gid=%s "
                            "WHERE gid=%s AND (parent_team_gid <> %s OR parent_team_gid IS NULL)",
                            (parent_gid, team_gid, parent_gid),
                        )
                    conn.commit()
            except Exception as e:
                _log.warning("sync_all set parent %s: %s", team_gid, e)

    # ── 2. Upsert 用户 + 分配 team_id ─────────────────────────────────────
    for u in users:
        if not u.get("open_id"):
            continue
        existing_count = _count_user(u["open_id"])
        try:
            user = get_or_create(
                open_id=u["open_id"],
                name=u["name"],
                email=u["email"],
                avatar_url=u["avatar_url"],
            )
            if existing_count == 0:
                stats["created"] += 1
            else:
                stats["updated"] += 1
        except Exception as e:
            _log.warning("sync_all get_or_create %s: %s", u.get("open_id"), e)
            continue

        # 取第一个有对应 team 的部门作为 team_id
        dept_open_ids = u.get("department_open_ids", [])
        team_gid = next(
            (dept_gid_map[d] for d in dept_open_ids if d in dept_gid_map),
            None,
        )
        if team_gid:
            try:
                _assign_user_team(user["gid"], team_gid)
                stats["dept_synced"] += 1
            except Exception as e:
                _log.warning("sync_all assign team %s→%s: %s", user["gid"], team_gid, e)

    _log.info("sync_all_from_feishu done: %s", stats)

    # ── 3. 清除手动添加的团队（feishu_dept_id IS NULL）─────────────────────────
    manual_cleared = 0
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE workmanship_auth_teams SET deleted_at = NOW() "
                    "WHERE feishu_dept_id IS NULL AND deleted_at IS NULL"
                )
                manual_cleared = cur.rowcount
            conn.commit()
        if manual_cleared:
            _log.info("sync_all: cleared %d manual teams", manual_cleared)
    except Exception as e:
        _log.warning("sync_all: clear manual teams: %s", e)
    stats["manual_cleared"] = manual_cleared

    return stats


def _count_user(open_id: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total FROM workmanship_auth_users WHERE feishu_open_id=%s", (open_id,)
            )
            return cur.fetchone()["total"]
