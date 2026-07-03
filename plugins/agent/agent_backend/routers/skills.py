"""
backend/routers/skills.py
─────────────────────────
Skill 库云端 CRUD

GET    /api/skills              — 列出可见 skill
POST   /api/skills              — 创建 skill
PUT    /api/skills/{gid}        — 更新 skill
DELETE /api/skills/{gid}        — 软删除 skill
POST   /api/skills/seed-system  — 写入/更新系统预设 skill（超管或内网调用）
"""
import json
import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user, require_role
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/skills", tags=["skills"])

_NAME_RE = re.compile(r'^[a-z][a-z0-9_]{1,49}$')

# ── 系统预设 ──────────────────────────────────────────────────────────────────

_SYSTEM_SKILLS = [
    {
        "name": "bop_autolink_workflow",
        "title": "BOP Auto-Link 全流程",
        "skill_type": "prompt",
        "description": "指导小柔按正确顺序完成 PBOM 核对→Fork 版本→预览→Auto-Link→画布展示的完整工作流",
        "content": json.dumps({
            "template": (
                "BOP Auto-Link 全流程操作指南：\n\n"
                "【Phase 0 — 确认上下文（必须先完成）】\n"
                "需明确以下信息，缺一必须先用 ask_for_clarification 问用户：\n"
                "  - target_version_gid：已有 BOP 版本（活动状态）的 GID\n"
                "  - 如需 Fork：source_version_gid（工厂模板）+ project_gid（目标项目）\n"
                "  - pbom_snapshot_gid：PBOM 快照 GID\n"
                "  辅助工具：list_bop_versions / list_pbom_snapshots\n\n"
                "【Phase 1 — PBOM 核对（硬前置，失败必须停止）】\n"
                "  → 调用 pbom_vpps_check(snapshot_gid)\n"
                "  → 如有任何规则错误：明确告知用户错误详情，停止全部后续步骤，等人修复后重新触发\n\n"
                "【Phase 2 — 查看/创建 BOP 版本】\n"
                "  → 调用 list_bop_versions(project_gid=...) 确认是否已有 active 版本\n"
                "  → 如需从工厂模板创建：调用 fork_bop_version（等待用户确认）\n\n"
                "【Phase 3 — 预览关联（执行前必须展示给用户）】\n"
                "  → 调用 preview_auto_link(version_gid)\n"
                "  → 调用 generate_canvas 将预览可视化（每个条目作为节点，颜色区分状态：pending=黄，skip=灰，warn=红）\n"
                "  → 如 warn > 0（vpps 缺失）：用 ask_for_clarification 询问用户是否继续\n\n"
                "【Phase 4 — 运行 Auto-Link（等用户确认后执行）】\n"
                "  → 调用 run_auto_link(version_gid, mode='incremental', step='all')\n"
                "  → 必须等确认 token 流程完成\n\n"
                "【Phase 5 — 读取并可视化结果】\n"
                "  → 调用 get_bop_link_status(version_gid)\n"
                "  → 调用 generate_canvas 展示结果热力图：\n"
                "    - 每个工站作为 bop_station 节点\n"
                "    - 节点上挂 ui_badge_group（linked=青色, stale=黄色, missing=红色）\n"
                "  → 如 missing > 0：明确告知哪些工站有未关联条目，建议人工补录\n"
                "  → 如 stale > 0：提示可调用 run_auto_link(mode='repair') 修复\n\n"
                "【核心原则】\n"
                "- PBOM 核对失败必须停止（硬规则，不可跳过）\n"
                "- Fork 和 Auto-Link 都是写操作，必须等用户确认后才执行\n"
                "- 预览先于执行（先 preview_auto_link 再 run_auto_link）\n"
                "- 结果用画布热力图展示，不要只用文字列表\n\n"
                "【用 generate_canvas 展示本流程时的正确结构（重要）】\n"
                "⚠️ generate_canvas 的同一 step 列 = 并行执行。此流程是严格顺序的，\n"
                "每个 Phase 必须用不同的 step 编号，禁止将顺序步骤放在同一 step 列。\n"
                "推荐结构：\n"
                "  lanes: [ {id:'ai', label:'小柔（自动）'}, {id:'user', label:'用户确认'} ]\n"
                "  step_labels: ['选择版本/快照','PBOM核对','规则4让步','执行让步','核对判断','Fork确认','Fork执行','预览关联','运行确认','Auto-Link','查看结果']\n"
                "  节点分配（每步占一个唯一step，不跨step合并）：\n"
                "    step0 → user泳道: human 选择版本/快照\n"
                "    step1 → ai泳道: tool_read PBOM vpps核对\n"
                "    step2 → user泳道: human 规则4让步确认（rule4_flag为空时跳过）\n"
                "    step3 → ai泳道: tool_write 执行规则4让步（rule4_flag为空时跳过）\n"
                "    step4 → ai泳道: condition 核对通过判断\n"
                "    step5 → user泳道: human Fork版本确认\n"
                "    step6 → ai泳道: tool_write Fork BOP版本\n"
                "    step7 → ai泳道: tool_read 预览关联\n"
                "    step8 → user泳道: human 运行确认\n"
                "    step9 → ai泳道: tool_write 执行Auto-Link\n"
                "    step10 → ai泳道: tool_read+ui_badge_group 查看关联结果热力图\n"
                "不要用功能模块（数据准备/版本操作等）作为泳道，这会导致顺序步骤被错误地平铺到同一step列。"
            ),
            "variables": [],
            "system_hint": (
                "严格按 Phase 0→1→2→3→4→5 顺序执行，每个 Phase 完成后汇报状态再进入下一个。"
                "使用 generate_canvas 时：同一step=并行，顺序步骤必须用不同step编号，"
                "泳道用角色（小柔/用户），不用功能模块名。"
                "【自主执行模式必读】调用 run_skill_canvas 时必须在 init_params 中提供："
                " snapshot_gid（PBOM快照GID）、source_gid（工厂模板版本GID，需Fork时）、"
                " version_gid（已有活动版本GID，无需Fork时）、project_gid（目标项目GID，需Fork时）。"
                "缺少任何必要GID时，必须先用 ask_for_clarification 向用户询问，不能直接执行。"
            ),
            "canvas": json.dumps({
                "lanes": [
                    {"id": "ai",   "label": "小柔（自动）"},
                    {"id": "user", "label": "用户确认"},
                ],
                "step_labels": [
                    "选择版本/快照", "PBOM核对", "规则4让步", "执行让步",
                    "核对判断", "Fork确认", "Fork执行",
                    "预览关联", "运行确认", "Auto-Link", "查看结果",
                ],
                "nodes": [
                    {"id": "u0", "lane_id": "user", "step": 0, "type": "human", "label": "选择版本/快照",
                     "params": {
                         "task_desc": "请选择目标项目、PBOM快照和BOP版本",
                         "canvas_layout": {"column_labels": None, "column_width": 320, "lane_height": 60, "hide_lane_labels": True},
                         "collect_fields": [
                             {"key": "project_gid",  "label": "目标项目",        "type": "select",
                              "source_tool": "list_projects"},
                             {"key": "snapshot_gid", "label": "PBOM 快照",       "type": "select",
                              "source_tool": "list_pbom_snapshots", "depends_on": "project_gid"},
                             {"key": "_bop_mode",    "label": "BOP 版本来源",    "type": "radio",
                              "options": [{"value": "existing", "label": "使用已有活动版本"},
                                          {"value": "fork",     "label": "从GBOP Fork新版本"}],
                              "default": "existing"},
                             {"key": "version_gid",  "label": "已有BOP活动版本", "type": "select",
                              "source_tool": "list_bop_versions", "depends_on": "project_gid",
                              "show_when": {"_bop_mode": "existing"}},
                             {"key": "source_gid",   "label": "GBOP模板版本",    "type": "select",
                              "source_tool": "list_gbop_versions",
                              "show_when": {"_bop_mode": "fork"}},
                         ],
                     }},
                    {"id": "n2",   "lane_id": "ai",   "step": 1,  "type": "tool_read",  "label": "PBOM vpps核对",
                     "params": {"tool_name": "pbom_vpps_check", "snapshot_gid": "{{u0.snapshot_gid}}"}},
                    {"id": "n_r4", "lane_id": "ai",   "step": 3,  "type": "tool_write", "label": "执行规则4让步",
                     "params": {
                         "tool_name": "apply_rule4_concession",
                         "snapshot_gid": "{{n2.snapshot_gid}}",
                         "rule4_action": "{{u_r4.rule4_action}}",
                         "rule4_flag": "{{n2.rule4_flag}}",
                         "skip_when_empty": ["rule4_flag"],
                     }},
                    {"id": "n3",   "lane_id": "ai",   "step": 4,  "type": "condition",  "label": "核对通过？",
                     "params": {"condition_expr": "critical_errors == 0", "true_branch": "继续→Fork确认", "false_branch": "停止，告知错误", "halt_on_false": True}},
                    {"id": "n5",   "lane_id": "ai",   "step": 6,  "type": "tool_write", "label": "Fork BOP版本",
                     "params": {"tool_name": "fork_bop_version", "confirm_required": "true",
                                "source_gid": "{{u0.source_gid}}", "project_gid": "{{u0.project_gid}}",
                                "skip_when_empty": ["source_gid"]}},
                    {"id": "n6",   "lane_id": "ai",   "step": 7,  "type": "tool_read",  "label": "预览关联",
                     "params": {"tool_name": "preview_auto_link", "version_gid": "{{n5.gid||u0.version_gid}}"}},
                    {"id": "n9",   "lane_id": "ai",   "step": 9,  "type": "tool_write", "label": "执行Auto-Link",
                     "params": {"tool_name": "run_auto_link", "confirm_required": "true",
                                "version_gid": "{{n5.gid||u0.version_gid}}",
                                "line_gids": "{{u8.line_gids}}"}},
                    {"id": "n10",  "lane_id": "ai",   "step": 10, "type": "tool_read",  "label": "查看结果热力图",
                     "params": {"tool_name": "get_bop_link_status + generate_canvas"}},
                    {"id": "u_r4", "lane_id": "user", "step": 2,  "type": "human",      "label": "规则4让步确认",
                     "params": {
                         "task_desc": "规则4：紧固件主件一致性存在错误，请选择处理方式",
                         "rule4_flag": "{{n2.rule4_flag}}",
                         "skip_when_empty": ["rule4_flag"],
                         "canvas_layout": {"column_labels": ["规则4问题", "处理确认"], "column_width": 260, "lane_height": 60},
                         "collect_fields": [
                             {"key": "rule4_action", "label": "处理方式", "type": "radio",
                              "options": [
                                  {"value": "apply", "label": "一键让步（写入让步表，继续流程）"},
                                  {"value": "skip",  "label": "暂不处理（忽略规则4错误，继续流程）"},
                              ],
                              "default": "apply"},
                         ],
                     }},
                    {"id": "u4",   "lane_id": "user", "step": 5,  "type": "human",      "label": "Fork版本确认",
                     "params": {
                         "task_desc": "确认是否 Fork 新版本进行关联",
                         "canvas_layout": {"column_labels": ["核对结果", "操作确认"], "column_width": 260, "lane_height": 60},
                     }},
                    {"id": "u8",   "lane_id": "user", "step": 8,  "type": "human",      "label": "运行确认",
                     "params": {"task_desc": "确认执行 Auto-Link（写操作不可撤销）",
                                "canvas_layout": {"column_labels": ["预览结果", "操作确认"], "column_width": 280, "lane_height": 80},
                                "collect_fields": [
                                    {"key": "line_scope", "label": "Auto-Link 范围", "type": "radio",
                                     "options": [{"value": "all",      "label": "全部线体"},
                                                 {"value": "selected", "label": "指定线体"}],
                                     "default": "all"},
                                    {"key": "line_gids", "label": "选择线体", "type": "select_multi",
                                     "source_tool": "list_asm_lines",
                                     "source_param": {"version_gid": "{{n5.gid||u0.version_gid}}"},
                                     "show_when": {"line_scope": "selected"}},
                                ]}},
                ],
                "connections": [
                    {"id": "c0",   "from": "u0",   "to": "n2",   "type": "control"},
                    {"id": "c2",   "from": "n2",   "to": "u_r4", "type": "control"},
                    {"id": "cr4a", "from": "u_r4", "to": "n_r4", "type": "control"},
                    {"id": "cr4b", "from": "n_r4", "to": "n3",   "type": "control"},
                    {"id": "c3",   "from": "n3",   "to": "u4",   "type": "control"},
                    {"id": "c4",   "from": "u4",   "to": "n5",   "type": "control"},
                    {"id": "c5",   "from": "n5",   "to": "n6",   "type": "control"},
                    {"id": "c7",   "from": "n6",   "to": "u8",   "type": "control"},
                    {"id": "c8",   "from": "u8",   "to": "n9",   "type": "control"},
                    {"id": "c9",   "from": "n9",   "to": "n10",  "type": "control"},
                ],
            }, ensure_ascii=False),
        }, ensure_ascii=False),
        "icon": "🔗",
        "tags": json.dumps(["BOP", "Auto-Link", "工作流"], ensure_ascii=False),
        "sort_order": 5,
    },
]


def _ensure_skills_table(cur):
    """确保 app.skills 表存在（防止新部署未手动执行 schema.sql）。"""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app.skills (
            gid         TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            title       TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            skill_type  TEXT NOT NULL,
            scope       TEXT NOT NULL DEFAULT 'private',
            status      TEXT NOT NULL DEFAULT 'draft',
            owner_gid   TEXT NOT NULL DEFAULT '',
            is_system   BOOLEAN NOT NULL DEFAULT FALSE,
            content     JSONB NOT NULL DEFAULT '{}',
            icon        TEXT NOT NULL DEFAULT '',
            tags        JSONB NOT NULL DEFAULT '[]',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            is_pinned   BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at  TIMESTAMPTZ DEFAULT NULL
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_name
        ON app.skills(name) WHERE deleted_at IS NULL
    """)


def _row_to_dict(r) -> dict:
    return {
        "gid":         r["gid"],
        "name":        r["name"],
        "title":       r["title"],
        "description": r["description"],
        "skill_type":  r["skill_type"],
        "scope":       r["scope"],
        "status":      r["status"],
        "owner_gid":   r["owner_gid"],
        "is_system":   r["is_system"],
        "content":     json.dumps(r["content"], ensure_ascii=False) if isinstance(r["content"], (dict, list)) else (r["content"] or "{}"),
        "icon":        r["icon"],
        "tags":        json.dumps(r["tags"], ensure_ascii=False) if isinstance(r["tags"], list) else (r["tags"] or "[]"),
        "sort_order":  r["sort_order"],
        "is_pinned":   r["is_pinned"],
        "created_at":  r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at":  r["updated_at"].isoformat() if r["updated_at"] else None,
    }


# ── 列表 ───────────────────────────────────────────────────────────────────────

@router.get("")
def list_skills(
    scope_filter: str = Query(default="all"),   # all | mine | team | global
    user: dict = Depends(get_current_user),
):
    owner_gid = user.get("gid", "")
    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_skills_table(cur)
            cur.execute("""
                SELECT * FROM app.skills
                WHERE deleted_at IS NULL
                ORDER BY sort_order, created_at
            """)
            rows = cur.fetchall()

    result = []
    for r in rows:
        if r["scope"] == "private" and r["owner_gid"] != owner_gid and r["owner_gid"] != "__system__":
            continue
        if scope_filter == "mine" and r["owner_gid"] != owner_gid and r["owner_gid"] != "__system__":
            continue
        if scope_filter == "team" and r["scope"] != "team":
            continue
        if scope_filter == "global" and r["scope"] != "global":
            continue
        result.append(_row_to_dict(r))
    return result


# ── 创建 ───────────────────────────────────────────────────────────────────────

@router.post("")
def create_skill(body: dict, user: dict = Depends(get_current_user)):
    name = (body.get("name") or "").strip()
    title = (body.get("title") or "").strip()
    if not name or not title:
        raise HTTPException(400, "name 和 title 不能为空")
    if not _NAME_RE.match(name):
        raise HTTPException(400, "name 格式错误：小写字母/数字/下划线，2-50位，字母开头")
    skill_type = body.get("skill_type", "prompt")
    if skill_type not in ("prompt", "tool", "flow"):
        raise HTTPException(400, "skill_type 必须是 prompt / tool / flow")

    gid = str(next_gid())
    owner_gid = user.get("gid", "")
    content_raw = body.get("content", "{}")
    try:
        content_obj = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
    except Exception:
        content_obj = {}
    tags_raw = body.get("tags", "[]")
    try:
        tags_obj = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
    except Exception:
        tags_obj = []

    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_skills_table(cur)
            try:
                cur.execute("""
                    INSERT INTO app.skills
                        (gid, name, title, description, skill_type, scope, status,
                         owner_gid, is_system, content, icon, tags, sort_order, is_pinned)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    gid, name, title,
                    body.get("description", ""),
                    skill_type,
                    body.get("scope", "private"),
                    "draft",
                    owner_gid,
                    False,
                    json.dumps(content_obj, ensure_ascii=False),
                    body.get("icon", ""),
                    json.dumps(tags_obj, ensure_ascii=False),
                    body.get("sort_order", 0),
                    False,
                ))
            except Exception as e:
                if "idx_skills_name" in str(e):
                    raise HTTPException(409, f"Skill name '{name}' 已存在")
                raise
    return {"gid": gid, "success": True}


# ── 更新 ───────────────────────────────────────────────────────────────────────

@router.put("/{gid}")
def update_skill(gid: str, body: dict, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_skills_table(cur)
            cur.execute("SELECT * FROM app.skills WHERE gid=%s AND deleted_at IS NULL", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Skill 不存在")
            if row["is_system"]:
                raise HTTPException(403, "系统预设 Skill 不可修改")
            if row["owner_gid"] != user.get("gid", "") and user.get("role") not in ("super_admin", "team_admin"):
                raise HTTPException(403, "无权修改此 Skill")

            sets, params = [], []
            for field in ("title", "description", "scope", "status", "icon", "sort_order"):
                if field in body:
                    sets.append(f"{field}=%s")
                    params.append(body[field])
            if "content" in body:
                sets.append("content=%s")
                raw = body["content"]
                try:
                    obj = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    obj = {}
                params.append(json.dumps(obj, ensure_ascii=False))
            if "tags" in body:
                sets.append("tags=%s")
                raw = body["tags"]
                try:
                    obj = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    obj = []
                params.append(json.dumps(obj, ensure_ascii=False))
            if "is_pinned" in body:
                sets.append("is_pinned=%s")
                params.append(bool(body["is_pinned"]))

            if not sets:
                return {"success": True}

            sets.append("updated_at=NOW()")
            params.append(gid)
            cur.execute(f"UPDATE app.skills SET {','.join(sets)} WHERE gid=%s", params)
    return {"success": True}


# ── 删除（软删除）──────────────────────────────────────────────────────────────

@router.delete("/{gid}")
def delete_skill(gid: str, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_skills_table(cur)
            cur.execute("SELECT is_system, owner_gid FROM app.skills WHERE gid=%s AND deleted_at IS NULL", (gid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Skill 不存在")
            if row["is_system"]:
                raise HTTPException(403, "系统预设 Skill 不可删除")
            if row["owner_gid"] != user.get("gid", "") and user.get("role") not in ("super_admin", "team_admin"):
                raise HTTPException(403, "无权删除此 Skill")
            cur.execute("UPDATE app.skills SET deleted_at=NOW() WHERE gid=%s", (gid,))
    return {"success": True}


# ── 写入系统预设（幂等）────────────────────────────────────────────────────────

@router.post("/seed-system", include_in_schema=False)
def seed_system_skills():
    """写入/更新系统预设 skill（幂等，name 冲突时更新内容）。内网调用，无需鉴权。"""
    seeded = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_skills_table(cur)
            for sk in _SYSTEM_SKILLS:
                content_obj = json.loads(sk["content"]) if isinstance(sk["content"], str) else sk["content"]
                tags_obj = json.loads(sk["tags"]) if isinstance(sk["tags"], str) else sk["tags"]

                cur.execute("SELECT gid FROM app.skills WHERE name=%s AND deleted_at IS NULL", (sk["name"],))
                existing = cur.fetchone()
                if existing:
                    cur.execute("""
                        UPDATE app.skills
                        SET title=%s, description=%s, content=%s, icon=%s, tags=%s,
                            sort_order=%s, is_system=TRUE, scope='global', status='active',
                            updated_at=NOW()
                        WHERE gid=%s
                    """, (
                        sk["title"], sk["description"],
                        json.dumps(content_obj, ensure_ascii=False),
                        sk.get("icon", ""),
                        json.dumps(tags_obj, ensure_ascii=False),
                        sk.get("sort_order", 0),
                        existing["gid"],
                    ))
                    seeded.append({"name": sk["name"], "action": "updated", "gid": existing["gid"]})
                else:
                    gid = str(next_gid())
                    cur.execute("""
                        INSERT INTO app.skills
                            (gid, name, title, description, skill_type, scope, status,
                             owner_gid, is_system, content, icon, tags, sort_order)
                        VALUES (%s,%s,%s,%s,%s,'global','active','__system__',TRUE,%s,%s,%s,%s)
                    """, (
                        gid, sk["name"], sk["title"], sk["description"], sk["skill_type"],
                        json.dumps(content_obj, ensure_ascii=False),
                        sk.get("icon", ""),
                        json.dumps(tags_obj, ensure_ascii=False),
                        sk.get("sort_order", 0),
                    ))
                    seeded.append({"name": sk["name"], "action": "created", "gid": gid})
    return {"success": True, "seeded": seeded}
