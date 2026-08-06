"""
backend/tests/test_schema_migration_static.py
─────────────────────────────────────────────
纯静态扫描测试 — 遍历所有 backend/ Python 文件，
用正则扫描 SQL 中可能存在的裸表名引用（不含 schema 前缀）。
不需要数据库连接或 mock。

测试策略：
  1. 找到 `backend/` 下所有 .py 文件（排除 tests/ 自身和 venv）
  2. 用正则搜索 `FROM|INTO|UPDATE|DELETE FROM|JOIN|REFERENCES` 后跟裸表名的模式
  3. 裸表名必须在 _TABLE_SCHEMA_MAP 的白名单中存在
  4. 断言：不存在任何不在白名单排他列表中的裸表名引用
"""
import ast
import re
from pathlib import Path

import pytest

# ── 项目根目录 ──
BACKEND_DIR = Path(__file__).resolve().parent.parent

# ── 需要 schema 前缀的已知表名 ──
# 键 = 裸表名，值 = 期望的完整 schema.table
TABLE_SCHEMA_MAP = {
    # auth
    "teams": "auth.teams",
    "users": "auth.users",
    "project_members": "auth.project_members",
    "auth_pending": "auth.auth_pending",
    "bid_sections": "auth.bid_sections",
    "section_owners": "auth.section_owners",
    # proj
    "projects": "proj.projects",
    "vehicle_models": "proj.vehicle_models",
    "collab_sessions": "proj.collab_sessions",
    "approval_orders": "proj.approval_orders",
    # bop
    "bop_versions": "bop.bop_versions",
    "bop_entries": "bop.bop_entries",
    "bop_entry_links": "bop.bop_entry_links",
    "bop_line": "bop.bop_line",
    "bop_station": "bop.bop_station",
    "bop_operator": "bop.bop_operator",
    "bop_steps": "bop.bop_steps",
    "bop_process": "bop.bop_process",
    "bop_equipments": "bop.bop_equipments",
    "bop_fixtures": "bop.bop_fixtures",
    "bop_tools": "bop.bop_tools",
    "bop_floor_height": "bop.bop_floor_height",
    "bop_control_plan": "bop.bop_control_plan",
    "bop_process_charts": "bop.bop_process_charts",
    "bop_jack_pos": "bop.bop_jack_pos",
    "pbom_versions": "bop.pbom_versions",
    "pbom": "bop.pbom",
    "cad_model_instances": "bop.cad_model_instances",
    "canvas_bop_layers": "bop.canvas_bop_layers",
    "bop_fork_presets": "bop.bop_fork_presets",
    "asm_steps": "bop.asm_steps",
    "project_roles": "bop.project_roles",
    # factory
    "factories": "factory.factories",
    "factory_sections": "factory.factory_sections",
    "factory_stations": "factory.factory_stations",
    "factory_layout_templates": "factory.factory_layout_templates",
    "factory_tools": "factory.factory_tools",
    "factory_equipments": "factory.factory_equipments",
    "factory_fixtures": "factory.factory_fixtures",
    "factory_lines": "factory.factory_lines",
    # template
    "gbop": "template.gbop",
    "vpps_tools": "template.vpps_tools",
    "vpps_equipments": "template.vpps_equipments",
    "vpps_fixtures": "template.vpps_fixtures",
    "fastener_spec": "template.fastener_spec",
    "vpps_parts": "template.vpps_parts",
    # work
    "tasks": "work.tasks",
    "issues": "work.issues",
    "lists": "work.lists",
    "item_entries": "work.item_entries",
    "task_templates": "work.task_templates",
    "task_template_items": "work.task_template_items",
    "follows": "work.follows",
    "notifications": "work.notifications",
    # knowledge
    "knowledge_entries": "knowledge.knowledge_entries",
    "knowledge_folders": "knowledge.knowledge_folders",
    "knowledge_items": "knowledge.knowledge_items",
    "knowledge_favorites": "knowledge.knowledge_favorites",
    "knowledge_recent": "knowledge.knowledge_recent",
    "craft_rules": "knowledge.craft_rules",
    # app
    "view_configs": "app.view_configs",
    "export_templates": "app.export_templates",
    "workbench_configs": "app.workbench_configs",
    "workbench_member_overrides": "app.workbench_member_overrides",
    "system_config": "app.system_config",
    "flows": "app.flows",
    "flow_runs": "app.flow_runs",
    "wb_annotations": "app.wb_annotations",
    "bug_tracker_snapshots": "app.bug_tracker_snapshots",
}

# ── 已重命名的旧表名（这些旧名在任何 SQL 中都不应出现） ──
DEPRECATED_TABLE_NAMES = {
    "project_roles",  # → section_owners
    "asm_line_processes",  # → bop_line
    "asm_station_processes",  # → bop_station
    "asm_operator_processes",  # → bop_operator
    "asm_operations",  # → bop_steps
    "project_equipment",  # → bop_equipments
    "project_tooling",  # → bop_fixtures
    "project_tools",  # → bop_tools
    "project_floor_heights",  # → bop_floor_height
    "project_control_plans",  # → bop_control_plan
    "project_process_charts",  # → bop_process_charts
    "project_jack_pos",  # → bop_jack_pos
    "bom_snapshots",  # → pbom_versions
    "part_entries",  # → pbom
    "part_model_instances",  # → cad_model_instances
    "physical_tools",  # → factory_tools
    "physical_equipments",  # → factory_equipments
    "physical_fixtures",  # → factory_fixtures
    "std_operations",  # → gbop
    "tool_templates",  # → vpps_tools
    "equipment_templates",  # → vpps_equipments
    "fixture_templates",  # → vpps_fixtures
    "standard_fasteners",  # → fastener_spec
    "standard_part_names",  # → vpps_parts
}

# ── 允许出现裸表名的上下文（例外的白名单模式） ──
_SAFE_PATTERNS = [
    # 序列/系统目录
    r"pg_catalog",
    r"information_schema",
    r"pg_table",
    r"pg_tables",
    r"FROM pg_",
    r"WHERE table_schema",
    r"WHERE schemaname",
    # 序列 nextval
    r"nextval\(",
    r"nextval ",
    r"setval\(",
    # 注释和字符串中的表名（非 SQL）
    r"#.*FROM\s+\w+",  # Python 注释中的 SQL
    # V1 废弃表（DROP TABLE 操作）
    r"DROP TABLE IF EXISTS public\.",
    r"DROP TABLE IF EXISTS bop_steps\b",
    r"DROP TABLE IF EXISTS bop_operations\b",
    r"DROP TABLE IF EXISTS bop_posts\b",
    r"DROP TABLE IF EXISTS work_plans\b",
    r"DROP TABLE IF EXISTS sections\b",
    r"DROP TABLE IF EXISTS operation_flat\b",
    r"DROP TABLE IF EXISTS operation_resources\b",
    r"DROP TABLE IF EXISTS step_resources\b",
    # 注释中的旧表引用
    r"#\s*(?:旧|old|V1)",
    # _TABLE_SCHEMA_MAP 常量定义本身（代码中赋值给 dict）
    r"\"project_roles\"",  # 在 _TABLE_SCHEMA_MAP 键中出现的
    # 文件路径中包含旧表名（纯描述性）
    r"old_table",
]
_SAFE_RE = re.compile("|".join(_SAFE_PATTERNS), re.IGNORECASE)
_SQL_KEYWORD_TABLE_RE = re.compile(
    r"(?:"
    r"(?:FROM|INTO|TABLE|DELETE\s+FROM)\s+(\w+)"
    r"|"
    r"(?:UPDATE|JOIN)\s+(\w+)"
    r"|"
    r"(?:REFERENCES)\s+(\w+)"
    r")",
    re.IGNORECASE,
)


def _extract_table_refs_from_file(filepath: Path) -> list[dict]:
    """提取文件中所有引用了分隔表中的裸表名（未加 schema 前缀）的 SQL 片段。"""
    text = filepath.read_text(encoding="utf-8")
    results = []

    for match in _SQL_KEYWORD_TABLE_RE.finditer(text):
        raw = match.group(1) or match.group(2) or match.group(3)
        if not raw:
            continue
        tbl = raw.strip()
        # 跳过已经是 schema.table 格式的
        if "." in tbl:
            continue
        # 跳过 SQL 函数、关键字
        if tbl.upper() in ("TRUE", "FALSE", "NULL", "NOW", "EXISTS",
                           "DEFAULT", "SET", "VALUES", "WHERE", "AND", "OR",
                           "ON", "AS", "NOT", "IN", "IS", "CASCADE"):
            continue
        # 跳过数字
        if tbl.isdigit() or tbl.startswith("'"):
            continue
        # 检查是否在已知表名映射中
        if tbl in TABLE_SCHEMA_MAP:
            # 检查是否在白名单上下文中
            ln_start = max(0, match.start() - 60)
            context = text[ln_start:match.end()]
            if _SAFE_RE.search(context):
                continue
            results.append({
                "table": tbl,
                "expected": TABLE_SCHEMA_MAP[tbl],
                "position": match.start(),
                "context": text[max(0, match.start() - 40):match.end() + 20].strip(),
            })

    # 检查已重命名的旧表名
    for old_name in DEPRECATED_TABLE_NAMES:
        pattern = re.compile(
            r"(?i)(?:FROM|INTO|UPDATE|TABLE|JOIN|REFERENCES)\s+" + re.escape(old_name),
        )
        for match in pattern.finditer(text):
            ln_start = max(0, match.start() - 60)
            context = text[ln_start:match.end()]
            if _SAFE_RE.search(context):
                continue
            results.append({
                "table": old_name,
                "expected": f"(DEPRECATED → {TABLE_SCHEMA_MAP.get(old_name, '?')})",
                "position": match.start(),
                "context": text[max(0, match.start() - 40):match.end() + 20].strip(),
            })

    results.sort(key=lambda x: x["position"])
    return results


# ── 待扫描文件列表 ──
def _get_python_files() -> list[Path]:
    """收集 backend/ 下所有需要扫描的 .py 文件（排除 tests/）。"""
    files = []
    for pyfile in BACKEND_DIR.rglob("*.py"):
        rel = pyfile.relative_to(BACKEND_DIR)
        # 排除 tests/ 自身和 __pycache__
        if "tests" in rel.parts:
            continue
        if "__pycache__" in rel.parts:
            continue
        if ".venv" in rel.parts or "venv" in rel.parts:
            continue
        files.append(pyfile)
    return sorted(files)


# =====================================================================
# 测试
# =====================================================================

@pytest.mark.parametrize("filepath", _get_python_files(), ids=lambda p: str(p.relative_to(BACKEND_DIR)))
def test_no_bare_table_names_in_sql(filepath: Path):
    """
    断言：文件中所有 SQL 关键字（FROM/INTO/UPDATE/JOIN 等）后面的表名
    都使用 schema.table 格式，不存在裸表名。
    """
    violations = _extract_table_refs_from_file(filepath)
    if violations:
        rel = filepath.relative_to(BACKEND_DIR)
        msg = f"\n{rel} 中存在裸表名引用（应加 schema 前缀）:\n"
        for v in violations:
            msg += f"  [{v['table']}] → 应为 {v['expected']}\n"
            msg += f"    上下文: ...{v['context']}...\n"
        pytest.fail(msg)


def test_no_deprecated_table_names():
    """
    专项测试：全局扫描是否任何文件包含已重命名的旧表名。
    这个测试将文件内容整体搜索，找到就报错。
    """
    bad = []
    for pyfile in _get_python_files():
        text = pyfile.read_text(encoding="utf-8")
        for old_name in DEPRECATED_TABLE_NAMES:
            # 在 SQL 字符串中搜索旧表名
            # 检查是否在字符串中（引号内）
            pattern = re.compile(
                r"['\"]" + re.escape(old_name) + r"['\"]",
            )
            for match in pattern.finditer(text):
                # 排除注释
                ln_start = max(0, match.start() - 30)
                context = text[ln_start:match.end() + 30]
                if _SAFE_RE.search(context):
                    continue
                bad.append((pyfile.relative_to(BACKEND_DIR), old_name, context))
    if bad:
        msg = "以下文件包含已重命名的旧表名:\n"
        for f, tbl, ctx in bad:
            msg += f"  {f}: [{tbl}] ...{ctx.strip()}...\n"
        pytest.fail(msg)


def test_table_map_covers_all_routers():
    """Reject legacy schema qualification in SQL executed by Base or plugin routers."""
    project_root = BACKEND_DIR.parent
    router_dirs = [BACKEND_DIR / "routers"]
    router_dirs.extend(
        path for path in (project_root / "plugins").glob("*/*_backend/routers")
        if path.is_dir()
    )
    legacy_ref = re.compile(
        r"\b(auth|proj|bop|factory|template|work|knowledge|app)"
        r"\.[A-Za-z_][A-Za-z0-9_]*\b",
        re.IGNORECASE,
    )

    def literal_sql(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(
                value.value
                for value in node.values
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = literal_sql(node.left)
            right = literal_sql(node.right)
            return None if left is None or right is None else left + right
        return None

    violations = []
    for router_dir in router_dirs:
        for pyfile in router_dir.rglob("*.py"):
            tree = ast.parse(pyfile.read_text(encoding="utf-8"), filename=str(pyfile))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute) or func.attr not in {"execute", "executemany"}:
                    continue
                sql = literal_sql(node.args[0])
                if not sql:
                    continue
                for match in legacy_ref.finditer(sql):
                    violations.append(
                        (pyfile.relative_to(project_root), node.lineno, match.group(0))
                    )

    assert not violations, (
        "OceanBase single-schema SQL contains legacy schema qualification:\n"
        + "\n".join(f"  - {path}:{line}: {ref}" for path, line, ref in violations)
    )
