"""
backend/tests/test_schema_migration_mock.py
───────────────────────────────────────────
Mock 集成测试 — mock psycopg2，用 TestClient 调用各 router 端点，
验证发出的 SQL 字符串包含正确 schema.table 前缀（无需真实 PG 数据库）。

测试策略：
  - mock `backend.db.connection.get_conn` → 虚拟连接
  - 用 `app.dependency_overrides` 替换认证依赖（get_current_user / get_current_user_optional）
  - 调用典型端点，捕获 cursor.execute() 的 SQL 参数 → 断言含 schema 前缀
"""
import re
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── 白名单：所有允许出现裸表名的模式（不含 schema 前缀的 SQL 片段） ──
# 这些是 DDL 操作、search_path 设置、临时表等，不需要 schema 前缀。
_ALLOWED_BARE_TABLE_PATTERNS = re.compile(
    r"|".join([
        r"pg_catalog",
        r"information_schema",
        r"pg_table",
        r"search_path",
        r"DROP TABLE IF EXISTS public\.",  # migration 脚本删 V1 旧表
        r"FROM pg_",
        r"WHERE table_schema",
        r"bop_steps\b",   # DROP TABLE 中出现的 V1 旧表名
        r"bop_operations\b",
        r"bop_posts\b",
        r"work_plans\b",
        r"sections\b",
        r"operation_flat\b",
        r"operation_resources\b",
        r"step_resources\b",
        r"nextval\(",      # 序列调用
        r"nextval ",       # 序列调用
    ]),
    re.IGNORECASE,
)

# ── schema.table 映射（旧裸表名 → 正确 schema 前缀） ──
_TABLE_SCHEMA_MAP = {
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
    "tasks": "proj.tasks",
    "issues": "proj.issues",
    "lists": "work.lists",
    "item_entries": "work.item_entries",
    "task_templates": "proj.task_templates",
    "task_template_items": "proj.task_template_items",
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

# ── 旧表名（已重命名，旧名不应出现） ──
_OLD_TABLE_NAMES = {
    "project_roles",
    "asm_line_processes",
    "asm_station_processes",
    "asm_operator_processes",
    "asm_operations",
    "project_equipment",
    "project_tooling",
    "project_tools",
    "project_floor_heights",
    "project_control_plans",
    "project_process_charts",
    "project_jack_pos",
    "bom_snapshots",
    "part_entries",
    "part_model_instances",
    "physical_tools",
    "physical_equipments",
    "physical_fixtures",
    "std_operations",
    "tool_templates",
    "equipment_templates",
    "fixture_templates",
    "standard_fasteners",
    "standard_part_names",
}


def _find_bare_table_refs(sql: str) -> list[str]:
    """从 SQL 字符串中找出所有裸表名引用（不含 schema 前缀）。"""
    found = []
    for bare_name, qualified_name in _TABLE_SCHEMA_MAP.items():
        # 匹配 FROM / INTO / UPDATE / DELETE FROM / JOIN / REFERENCES / ALTER TABLE / CREATE TABLE
        # 后面跟着裸表名（非 schema.table 格式）
        pattern = re.compile(
            r"(?<!\w)" + re.escape(bare_name) + r"(?!\.\w)",
            re.IGNORECASE,
        )
        # 但我们只需要找裸名出现且不在 ALLOWED 中的情况
        # 且该裸名前有 SQL 关键字指示它是表引用
        keyword_pattern = re.compile(
            r"(?i)(?:FROM|INTO|UPDATE|TABLE|JOIN|REFERENCES)\s+"
            + re.escape(bare_name) + r"(?:\s|;|$|,\s)",
        )
        if keyword_pattern.search(sql):
            # 如果这个裸名出现 + 前面有关键字
            # 检查是否不在 ALLOWED 中
            if _ALLOWED_BARE_TABLE_PATTERNS.search(sql):
                continue
            # 还需要排除 schema.table 形式前面的关键字
            # 例如 "FROM work.tasks" 不应该匹配
            # keyword_pattern 已经匹配的是裸表名前面有关键字的情况
            found.append(bare_name)
    return found


# =====================================================================
# Mock fixtures
# =====================================================================

@pytest.fixture
def mock_conn():
    """mock backend.db.connection.get_conn → 返回 MagicMock cursor"""
    mock_cursor = MagicMock()
    sequence_rows = {
        "proj_tasks_display_seq": {"val": 1001},
        "proj_issues_display_seq": {"val": 2001},
    }

    def _fetchone_side_effect():
        if not mock_cursor.execute.call_args_list:
            return None
        args, _ = mock_cursor.execute.call_args_list[-1]
        sql = str(args[0]) if args else ""
        params = args[1] if len(args) > 1 else []
        if "SELECT val FROM workmanship_display_id_counters" in sql and params:
            return sequence_rows.get(params[0])
        return None

    mock_cursor.fetchone.side_effect = _fetchone_side_effect
    mock_cursor.fetchall.return_value = []
    mock_cursor.rowcount = 0

    mock_connection = MagicMock()
    mock_connection.cursor.return_value = mock_cursor
    mock_connection.__enter__.return_value = mock_connection
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    # Plugin routes are loaded by their declared top-level package names.
    # Load registrations before patching the connection aliases they own.
    from backend.main import app as _registered_app  # noqa: F401

    targets = (
        "backend.db.connection.get_conn",
        "backend.db.sequences.get_conn",
        "backend.platform_sdk.access.get_conn",
        "backend.routers.annotations.get_conn",
        "backend.routers.follows.get_conn",
        "backend.routers.knowledge.get_conn",
        "backend.routers.knowledge_hub.get_conn",
        "backend.routers.notifications.get_conn",
        "backend.routers.views.get_conn",
        "backend.routers.workbenches.get_conn",
        "agent_backend.routers.flows.get_agent_conn",
        "craft_backend.routers.lists.get_conn",
        "craft_backend.routers.promotion.get_conn",
        "craft_backend.routers.rules.get_conn",
        "craft_backend.routers.task_templates.get_conn",
    )
    with ExitStack() as stack:
        for target in targets:
            stack.enter_context(patch(target, return_value=mock_connection))
        yield mock_connection, mock_cursor


@pytest.fixture
def client(mock_conn):
    """FastAPI TestClient，替换认证依赖。mock_conn 先执行以 patch get_conn。"""
    from backend.main import app

    # 替换所有认证依赖为 fake local user
    async def _fake_user():
        return {
            "gid": "test_user_gid",
            "system_role": "super_admin",
            "team_id": "test_team_gid",
            "is_active": True,
            "name": "Test User",
            "email": "",
            "avatar_url": "",
            "external_subtype": None,
            "feishu_open_id": "",
            "notification_prefs": {},
        }

    async def _fake_user_optional():
        return {
            "gid": "test_user_gid",
            "system_role": "super_admin",
            "team_id": "test_team_gid",
            "role": "super_admin",
        }

    from backend.routers.deps import get_current_user, get_current_user_optional

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_current_user_optional] = _fake_user_optional

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# =====================================================================
# 测试 — 静态 SQL 字符串验证
# =====================================================================

class TestSqlSchemaPrefix:
    """
    测试各 router 端点发出的 SQL 是否包含正确 schema 前缀。
    通过 mock get_conn + 捕获 execute() 调用来验证。
    """

    def _get_executed_sqls(self, mock_cursor) -> list[str]:
        """从 mock cursor 提取所有 execute() 调用的 SQL 字符串。"""
        sqls = []
        for call_args in mock_cursor.execute.call_args_list:
            args, _ = call_args
            if args:
                sqls.append(str(args[0]))
        return sqls

    def _assert_all_sql_have_schema(self, executed_sqls: list[str], endpoint_name: str):
        """断言所有 SQL 中的表引用都有 schema 前缀。"""
        failures = []
        for sql in executed_sqls:
            bare_refs = _find_bare_table_refs(sql)
            if bare_refs:
                failures.append((sql, bare_refs))
        if failures:
            msg = f"\n端点 [{endpoint_name}] 发出的 SQL 中存在裸表名:\n"
            for sql, refs in failures:
                msg += f"  裸表: {refs}\n  SQL: {sql[:200]}\n"
            pytest.fail(msg)

    # ── lists ──

    def test_lists_get(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/lists")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/lists")

    def test_lists_post(self, client, mock_conn):
        _, mc = mock_conn
        client.post("/api/lists", json={"name": "Test List"})
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "POST /api/lists")

    def test_lists_patch(self, client, mock_conn):
        _, mc = mock_conn
        client.patch("/api/lists/fake-gid", json={"name": "Renamed"})
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "PATCH /api/lists/{gid}")

    def test_lists_delete(self, client, mock_conn):
        _, mc = mock_conn
        client.delete("/api/lists/fake-gid")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "DELETE /api/lists/{gid}")

    # ── task_templates ──

    def test_task_templates_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/task-templates")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/task-templates")

    def test_task_templates_create(self, client, mock_conn):
        _, mc = mock_conn
        client.post("/api/task-templates", json={"name": "Test Template"})
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "POST /api/task-templates")

    def test_task_templates_get(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/task-templates/fake-gid")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/task-templates/{gid}")

    # ── promotion (tasks / issues) ──

    def test_tasks_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/tasks")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/tasks")

    def test_tasks_create(self, client, mock_conn):
        _, mc = mock_conn
        client.post("/api/tasks", json={"title": "Test Task"})
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "POST /api/tasks")

    def test_issues_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/issues")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/issues")

    def test_issues_create(self, client, mock_conn):
        _, mc = mock_conn
        client.post("/api/issues", json={"title": "Test Issue"})
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "POST /api/issues")

    # ── views ──

    def test_views_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/views?module=task")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/views")

    def test_views_create(self, client, mock_conn):
        _, mc = mock_conn
        client.post("/api/views", json={"name": "My View", "module": "task"})
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "POST /api/views")

    # ── follows ──

    def test_follows_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/follows")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/follows")

    # ── notifications ──

    def test_notifications_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/notifications")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/notifications")

    # ── workbenches ──

    def test_workbenches_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/workbenches")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/workbenches")

    # ── knowledge ──

    def test_knowledge_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/knowledge?project_gid=fake")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/knowledge")

    # ── rules ──

    def test_rules_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/rules?project_gid=fake")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/rules")

    # ── flows ──

    def test_flows_list(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/flows")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/flows")

    # ── annotations ──

    def test_annotations_get(self, client, mock_conn):
        _, mc = mock_conn
        client.get("/api/annotations/test-key")
        sqls = self._get_executed_sqls(mc)
        self._assert_all_sql_have_schema(sqls, "GET /api/annotations/{key}")
