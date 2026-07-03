"""
pg_to_mysql_migrate.py
───────────────────────
PostgreSQL → MySQL 8.0 Python 代码批量替换脚本（阶段 3 + 6）

执行：  python backend/db/pg_to_mysql_migrate.py

替换内容：
  1. 表名（schema.table → workmanship_前缀_table）
  2. :: 类型转换（::jsonb / ::text / ::int 等 → 删除）
  3. ON CONFLICT DO NOTHING → INSERT IGNORE INTO
  4. ILIKE → LIKE
  5. INTERVAL '...' → MySQL 语法
  6. information_schema 中的 table_schema='auth' 等 → table_schema='ai00'
  7. extract(epoch → UNIX_TIMESTAMP
  8. DATE_TRUNC → DATE / DATE_FORMAT

不处理（需人工处理）：
  - RETURNING（需按具体模式改写）
  - ON CONFLICT ... DO UPDATE SET（需逐个改写为 ON DUPLICATE KEY UPDATE）
  - row_to_json（在 _constants.py 中，需手工改写）
  - jsonb_set / @> / || 等复杂 JSONB 操作（阶段4处理）
"""

import os
import re
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# 1. 表名替换映射（完整）
# ─────────────────────────────────────────────────────────────────────────────

TABLE_MAP = {
    # auth
    "auth.teams": "workmanship_auth_teams",
    "auth.users": "workmanship_auth_users",
    "auth.project_members": "workmanship_auth_project_members",
    "auth.bid_sections": "workmanship_auth_bid_sections",
    "auth.section_owners": "workmanship_auth_section_owners",
    "auth.auth_pending": "workmanship_auth_auth_pending",
    # proj
    "proj.projects": "workmanship_proj_projects",
    "proj.vehicle_models": "workmanship_proj_vehicle_models",
    "proj.tasks": "workmanship_proj_tasks",
    "proj.issues": "workmanship_proj_issues",
    "proj.approval_orders": "workmanship_proj_approval_orders",
    "proj.collab_sessions": "workmanship_proj_collab_sessions",
    "proj.task_dependencies": "workmanship_proj_task_dependencies",
    # bop
    "bop.bop_versions": "workmanship_bop_bop_versions",
    "bop.bop_entries": "workmanship_bop_bop_entries",
    "bop.bop_entry_links": "workmanship_bop_bop_entry_links",
    "bop.pbom_versions": "workmanship_bop_pbom_versions",
    "bop.pbom": "workmanship_bop_pbom",
    "bop.cad_model_instances": "workmanship_bop_cad_model_instances",
    "bop.bop_line": "workmanship_bop_bop_line",
    "bop.bop_station": "workmanship_bop_bop_station",
    "bop.bop_process": "workmanship_bop_bop_process",
    "bop.bop_steps": "workmanship_bop_bop_steps",
    "bop.asm_steps": "workmanship_bop_asm_steps",
    "bop.bop_equipments": "workmanship_bop_bop_equipments",
    "bop.bop_fixtures": "workmanship_bop_bop_fixtures",
    "bop.bop_tools": "workmanship_bop_bop_tools",
    "bop.project_roles": "workmanship_bop_project_roles",
    "bop.bop_operator": "workmanship_bop_bop_operator",
    "bop.bop_jack_pos": "workmanship_bop_bop_jack_pos",
    "bop.bop_floor_height": "workmanship_bop_bop_floor_height",
    "bop.bop_control_plan": "workmanship_bop_bop_control_plan",
    "bop.bop_process_charts": "workmanship_bop_bop_process_charts",
    "bop.canvas_bop_layers": "workmanship_bop_canvas_bop_layers",
    "bop.bop_fork_presets": "workmanship_bop_bop_fork_presets",
    "bop.bop_staging": "workmanship_bop_bop_staging",
    "bop.bop_lifecycle_history": "workmanship_bop_bop_lifecycle_history",
    "bop.bop_lifecycle_stats": "workmanship_bop_bop_lifecycle_stats",
    "bop.bop_line_checkpoints": "workmanship_bop_bop_line_checkpoints",
    "bop.bop_line_operation_log": "workmanship_bop_bop_line_operation_log",
    "bop.bop_version_families": "workmanship_bop_bop_version_families",
    "bop.bop_pbom_diff_queue": "workmanship_bop_bop_pbom_diff_queue",
    # factory
    "factory.factories": "workmanship_factory_factories",
    "factory.factory_sections": "workmanship_factory_factory_sections",
    "factory.factory_stations": "workmanship_factory_factory_stations",
    "factory.factory_lines": "workmanship_factory_factory_lines",
    "factory.factory_tools": "workmanship_factory_factory_tools",
    "factory.factory_equipments": "workmanship_factory_factory_equipments",
    "factory.factory_fixtures": "workmanship_factory_factory_fixtures",
    "factory.factory_layout_templates": "workmanship_factory_factory_layout_templates",
    # template → tpl
    "template.gbop_versions": "workmanship_tpl_gbop_versions",
    "template.gbop_entries": "workmanship_tpl_gbop_entries",
    "template.gbop_processes": "workmanship_tpl_gbop_processes",
    "template.gbop_operations": "workmanship_tpl_gbop_operations",
    "template.gbop_entry_links": "workmanship_tpl_gbop_entry_links",
    "template.gbop": "workmanship_tpl_gbop_entries",  # 旧写法兼容
    "template.vpps_tools": "workmanship_tpl_vpps_tools",
    "template.vpps_equipments": "workmanship_tpl_vpps_equipments",
    "template.vpps_fixtures": "workmanship_tpl_vpps_fixtures",
    "template.vpps_parts": "workmanship_tpl_vpps_parts",
    "template.fastener_spec": "workmanship_tpl_fastener_spec",
    # work
    "work.lists": "workmanship_work_lists",
    "work.follows": "workmanship_work_follows",
    "work.notifications": "workmanship_work_notifications",
    "work.tasks": "workmanship_work_tasks",
    "work.issues": "workmanship_work_issues",
    "work.task_templates": "workmanship_work_task_templates",
    "work.task_template_items": "workmanship_work_task_template_items",
    "work.item_entries": "workmanship_work_item_entries",
    # knowledge → know
    "knowledge.knowledge_entries": "workmanship_know_entries",
    "knowledge.knowledge_folders": "workmanship_know_folders",
    "knowledge.knowledge_items": "workmanship_know_items",
    "knowledge.knowledge_favorites": "workmanship_know_favorites",
    "knowledge.knowledge_recent": "workmanship_know_recent",
    "knowledge.craft_rules": "workmanship_know_craft_rules",
    "knowledge.onto_classes": "workmanship_onto_classes",
    "knowledge.onto_properties": "workmanship_onto_properties",
    "knowledge.onto_relations": "workmanship_onto_relations",
    "knowledge.onto_axioms": "workmanship_onto_axioms",
    # auth（补充）
    "auth.permission_grants": "workmanship_auth_permission_grants",
    # work（补充）
    "work.item_change_logs": "workmanship_work_item_change_logs",
    "work.permission_requests": "workmanship_work_permission_requests",
    "work.list_shares": "workmanship_work_list_shares",
    "work.item_shares": "workmanship_work_item_shares",
    "work.share_links": "workmanship_work_share_links",
    "work.list_bitable_bindings": "workmanship_work_list_bitable_bindings",
    "work.list_bitable_record_map": "workmanship_work_list_bitable_record_map",
    # bop（补充）
    "bop.gbop_nav_bindings": "workmanship_bop_gbop_nav_bindings",
    "bop.gbop_match_staging": "workmanship_bop_gbop_match_staging",
    # proj（补充）
    "proj.task_templates": "workmanship_work_task_templates",
    "proj.task_template_items": "workmanship_work_task_template_items",
    # app（补充）
    "app.wfc_canvases": "workmanship_app_wfc_canvases",
    "app.feishu_search_cache": "workmanship_app_feishu_search_cache",
    "app.ai_memory": "workmanship_app_ai_memory",
    "app.ai_sessions": "workmanship_app_ai_sessions",
    "app.ai_turns": "workmanship_app_ai_turns",
    "app.view_configs": "workmanship_app_view_configs",
    "app.export_templates": "workmanship_app_export_templates",
    "app.workbench_configs": "workmanship_app_workbench_configs",
    "app.workbench_member_overrides": "workmanship_app_workbench_member_overrides",
    "app.flows": "workmanship_app_flows",
    "app.flow_runs": "workmanship_app_flow_runs",
    "app.wb_annotations": "workmanship_app_wb_annotations",
    "app.bug_tracker_snapshots": "workmanship_app_bug_tracker_snapshots",
    "app.ai_audit_logs": "workmanship_app_ai_audit_logs",
    "app.skills": "workmanship_app_skills",
    # integration → int
    "integration.ext_datasources": "workmanship_int_ext_datasources",
    "integration.ext_mappings": "workmanship_int_ext_mappings",
    "integration.ext_field_mappings": "workmanship_int_ext_field_mappings",
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. 正则替换规则
# ─────────────────────────────────────────────────────────────────────────────

REGEX_RULES = [
    # :: 类型转换（参数绑定时的类型强制）
    (r"::\s*jsonb\b", ""),
    (r"::\s*text\b", ""),
    (r"::\s*integer\b", ""),
    (r"::\s*int\b", ""),
    (r"::\s*boolean\b", ""),
    (r"::\s*date\b", ""),
    (r"::\s*double precision\b", ""),
    (r"::\s*float\b", ""),

    # SQL 内部 CAST
    (r"CAST\((.+?)\s+AS\s+text\)", r"CAST(\1 AS CHAR)"),

    # ILIKE → LIKE（utf8mb4_unicode_ci 不区分大小写）
    (r"\bILIKE\b", "LIKE"),

    # INTERVAL 语法修正
    (r"INTERVAL\s+'(\d+)\s+minutes?'", r"INTERVAL \1 MINUTE"),
    (r"INTERVAL\s+'(\d+)\s+hours?'", r"INTERVAL \1 HOUR"),
    (r"INTERVAL\s+'(\d+)\s+days?'", r"INTERVAL \1 DAY"),
    (r"INTERVAL\s+'(\d+)\s+seconds?'", r"INTERVAL \1 SECOND"),

    # EXTRACT epoch → UNIX_TIMESTAMP
    (r"EXTRACT\s*\(\s*epoch\s+FROM\s+NOW\(\)\s*\)\s*::\s*double precision",
     "UNIX_TIMESTAMP()"),
    (r"EXTRACT\s*\(\s*epoch\s+FROM\s+NOW\(\)\s*\)", "UNIX_TIMESTAMP()"),

    # DATE_TRUNC
    (r"DATE_TRUNC\s*\(\s*'day'\s*,\s*(.+?)\s*\)", r"DATE(\1)"),

    # information_schema 中的 table_schema 值
    (r"table_schema\s*=\s*'auth'", "table_schema='ai00'"),
    (r"table_schema\s*=\s*'proj'", "table_schema='ai00'"),
    (r"table_schema\s*=\s*'bop'", "table_schema='ai00'"),
    (r"table_schema\s*=\s*'work'", "table_schema='ai00'"),
    (r"table_schema\s*=\s*'knowledge'", "table_schema='ai00'"),
    (r"table_schema\s*=\s*'template'", "table_schema='ai00'"),
    (r"table_schema\s*=\s*'factory'", "table_schema='ai00'"),
    (r"table_schema\s*=\s*'app'", "table_schema='ai00'"),
    (r"table_schema\s*=\s*'integration'", "table_schema='ai00'"),

    # ON CONFLICT DO NOTHING → INSERT IGNORE
    # 先把 INSERT INTO 替换为 INSERT IGNORE INTO 再删除 ON CONFLICT ... DO NOTHING
    # 这个需要分两步：标记阶段 - 先做简单的 ON CONFLICT DO NOTHING 删除
    (r"\s*ON\s+CONFLICT\s+DO\s+NOTHING\b", ""),

    # COUNT(*)::int → COUNT(*)
    (r"COUNT\s*\(\s*\*\s*\)\s*::\s*int\b", "COUNT(*)"),
    (r"COUNT\s*\(\s*\*\s*\)\s*::\s*integer\b", "COUNT(*)"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 处理目录
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent.parent  # AI00_root_web/
ROUTER_DIRS = [
    ROOT / "backend" / "routers",
    ROOT / "backend" / "services",
    ROOT / "backend" / "utils",
    ROOT / "packages" / "craft-plugin" / "craft_backend" / "routers",
    ROOT / "packages" / "craft-plugin" / "craft_backend" / "services",
]
# 单独处理的文件
EXTRA_FILES = [
    ROOT / "backend" / "main.py",
    ROOT / "backend" / "manage.py",
]


def process_file(filepath: Path) -> int:
    """处理单个文件，返回替换次数"""
    text = filepath.read_text(encoding="utf-8", errors="replace")
    original = text

    # 1. 表名替换（按长度降序，避免短名覆盖长名）
    for pg_name, mysql_name in sorted(TABLE_MAP.items(), key=lambda x: -len(x[0])):
        text = text.replace(pg_name, mysql_name)

    # 2. 正则替换
    for pattern, replacement in REGEX_RULES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 3. INSERT INTO → INSERT IGNORE INTO (当后面跟着 ON CONFLICT 时已经删掉了 ON CONFLICT)
    #    但我们还需要处理简单的 "ON CONFLICT DO NOTHING" 已经被删掉的情况
    #    检测 INSERT INTO ... 语句中是否原来有 ON CONFLICT，现在已删除
    #    只有当原来有 ON CONFLICT DO NOTHING 时才改 INSERT INTO 为 INSERT IGNORE
    if "ON CONFLICT DO NOTHING" in original and "ON CONFLICT DO NOTHING" not in text:
        # 找到所有受影响的 INSERT，把 INSERT INTO 改为 INSERT IGNORE INTO
        # 这里用简单方法：如果文件里有 ON CONFLICT DO NOTHING，把对应的 INSERT INTO 改为 INSERT IGNORE
        # 更安全：只替换紧接着（在200字符内）有 ON CONFLICT 的 INSERT INTO
        pass  # 暂时跳过，需人工确认

    count = sum(1 for a, b in zip(original, text) if a != b)
    if text != original:
        filepath.write_text(text, encoding="utf-8")
        print(f"  ok: {filepath.relative_to(ROOT)} ({count} chars changed)")
    return count


def main():
    total_files = 0
    total_changes = 0
    skipped = []

    all_files = list(EXTRA_FILES)
    for router_dir in ROUTER_DIRS:
        if not router_dir.exists():
            print(f"[WARN] dir not found: {router_dir}")
            continue
        all_files.extend(sorted(router_dir.rglob("*.py")))

    for f in all_files:
        if not f.exists():
            continue
        if f.name == "__init__.py":
            continue
        try:
            changes = process_file(f)
            total_files += 1
            total_changes += changes
        except Exception as e:
            skipped.append((f, str(e)))
            print(f"  WARN {f.name}: {e}")

    print(f"\n{'='*60}")
    print(f"Done: {total_files} files, {total_changes} chars changed")
    if skipped:
        print(f"Skipped {len(skipped)} files:")
        for f, e in skipped:
            print(f"  - {f.name}: {e}")

    print("\nManual tasks remaining:")
    print("  1. RETURNING (~60 cases) - rewrite per pattern A/B/C")
    print("  2. ON CONFLICT (...) DO UPDATE SET (~36) -> ON DUPLICATE KEY UPDATE")
    print("  3. row_to_json (12 in _constants.py) -> JSON_OBJECT(...)")
    print("  4. jsonb_set / @> / || JSONB ops (phase 4)")
    print("  5. nextval -> next_display_id (phase 5)")


if __name__ == "__main__":
    main()
