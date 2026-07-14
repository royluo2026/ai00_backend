"""
backend/tests/test_vpps_audit.py
──────────────────────────────────
VPPS 操作审计测试套件

覆盖范围：
  1. Domain 服务层 (VppsAuditService)     — 纯单元测试，mock repository
  2. Infra 层 (PgVppsOperationRepository) — mock psycopg2，验证 SQL 含 bop.vpps_operations 前缀
  3. Router 端点 (TestClient)             — mock get_conn，验证 HTTP 响应格式和状态码
  4. SQL Schema 前缀                      — 所有端点不得使用裸表名 vpps_operations
  5. 前端 JS 静态检查                     — 验证 ebom.js / list_diff_shell.js 包含关键逻辑
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.domain.vpps_audit.models import VppsOperation
from backend.domain.vpps_audit.service import VppsAuditService
from backend.infra.vpps_audit_pg import PgVppsOperationRepository


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)


def _make_op(**overrides) -> VppsOperation:
    """构造最小化 VppsOperation（默认为已忽略规则4的行）。"""
    defaults = dict(
        gid="op_gid_001",
        pbom_version_gid="ver_001",
        pbom_row_gid="row_001",
        operation_type="rule4_bulk_ignore",
        rule_no=4,
        field_name="vpps_desc",
        original_value="螺栓-轮毂-制动盘",
        new_value=None,
        actor_gid="user_001",
        actor_name="张三",
        created_at=_NOW,
        notes=None,
        is_active=True,
        reverted_at=None,
        reverted_by_gid=None,
        reverted_by_name=None,
    )
    defaults.update(overrides)
    return VppsOperation(**defaults)


def _op_as_db_row(op: VppsOperation) -> dict:
    """把 VppsOperation 转成 psycopg2 RealDictRow（dict）格式。"""
    return {
        "gid":              op.gid,
        "pbom_version_gid": op.pbom_version_gid,
        "pbom_row_gid":     op.pbom_row_gid,
        "operation_type":   op.operation_type,
        "rule_no":          op.rule_no,
        "field_name":       op.field_name,
        "original_value":   op.original_value,
        "new_value":        op.new_value,
        "actor_gid":        op.actor_gid,
        "actor_name":       op.actor_name,
        "created_at":       op.created_at,
        "notes":            op.notes,
        "is_active":        op.is_active,
        "reverted_at":      op.reverted_at,
        "reverted_by_gid":  op.reverted_by_gid,
        "reverted_by_name": op.reverted_by_name,
    }


def _make_cursor_and_conn():
    """构造 mock psycopg2 connection + cursor（支持 with conn.cursor() as cur）。"""
    mc = MagicMock()
    mc.fetchone.return_value = None
    mc.fetchall.return_value = []
    mc.rowcount = 0
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = mc
    conn.__enter__.return_value = conn
    return mc, conn


def _collect_sqls(mc) -> list[str]:
    """从 mock cursor 收集 execute + executemany 调用的 SQL 字符串。"""
    sqls = []
    for c in mc.execute.call_args_list:
        args, _ = c
        if args:
            sqls.append(str(args[0]))
    for c in mc.executemany.call_args_list:
        args, _ = c
        if args:
            sqls.append(str(args[0]))
    return sqls


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def bop_entries_module(monkeypatch):
    project_root = Path(__file__).resolve().parents[2]
    craft_plugin_root = project_root / "plugins" / "craft"
    craft_plugin_root_str = str(craft_plugin_root)
    if craft_plugin_root_str not in sys.path:
        sys.path.insert(0, craft_plugin_root_str)
    module_name = "craft_backend.routers._bop.entries"
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    yield module
    sys.modules.pop(module_name, None)
    if craft_plugin_root_str in sys.path:
        sys.path.remove(craft_plugin_root_str)


@pytest.fixture
def bop_mock_conn():
    mc, conn = _make_cursor_and_conn()
    with patch("craft_backend.routers._bop.entries.get_conn", return_value=conn):
        yield conn, mc


@pytest.fixture
def mock_conn():
    mc, conn = _make_cursor_and_conn()
    with patch("craft_backend.routers.vpps_audit.get_conn", return_value=conn):
        yield conn, mc


@pytest.fixture
def client(mock_conn):
    from backend.main import app
    from backend.routers.deps import get_current_user

    async def _fake_user():
        return {
            "gid": "test_user_gid",
            "system_role": "super_admin",
            "team_id": "test_team",
            "is_active": True,
            "name": "Test User",
            "email": "",
            "avatar_url": "",
            "external_subtype": None,
            "feishu_open_id": "",
            "notification_prefs": {},
        }

    app.dependency_overrides[get_current_user] = _fake_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Domain Service 单元测试
# ─────────────────────────────────────────────────────────────────────────────

class TestVppsAuditService:

    def _repo(self, ignored_gids=None):
        repo = MagicMock()
        repo.get_active_rule4_ignores.return_value = set(ignored_gids or [])
        repo.save_batch.return_value = None
        repo.save.return_value = None
        return repo

    # ── bulk_ignore_rule4 ──────────────────────────────────────────────────────

    def test_creates_one_operation_per_row(self):
        """为每个未被忽略的 row 各创建一条 rule4_bulk_ignore 操作。"""
        svc = VppsAuditService(self._repo())
        rows = [
            {"pbom_row_gid": "row_A", "original_vpps_desc": "螺栓-A-B"},
            {"pbom_row_gid": "row_B", "original_vpps_desc": "螺母-C"},
        ]
        ops = svc.bulk_ignore_rule4("ver_001", rows, "user_001", "张三")

        assert len(ops) == 2
        assert all(op.operation_type == "rule4_bulk_ignore" for op in ops)
        assert all(op.rule_no == 4 for op in ops)
        assert all(op.is_active is True for op in ops)
        assert {op.pbom_row_gid for op in ops} == {"row_A", "row_B"}

    def test_save_batch_called_once(self):
        """save_batch 被调用一次（批量写入）。"""
        repo = self._repo()
        svc = VppsAuditService(repo)
        svc.bulk_ignore_rule4("ver_001", [{"pbom_row_gid": "row_A"}], "u")
        repo.save_batch.assert_called_once()

    def test_idempotent_skips_already_ignored_row(self):
        """已在 DB 中忽略的 row 不重复创建记录。"""
        svc = VppsAuditService(self._repo(ignored_gids={"row_A"}))
        rows = [
            {"pbom_row_gid": "row_A"},  # 已忽略 → 跳过
            {"pbom_row_gid": "row_B"},  # 新增 → 创建
        ]
        ops = svc.bulk_ignore_rule4("ver_001", rows, "u")
        assert len(ops) == 1
        assert ops[0].pbom_row_gid == "row_B"

    def test_empty_rows_does_not_call_save_batch(self):
        """空 rows 列表时不调用 save_batch。"""
        repo = self._repo()
        svc = VppsAuditService(repo)
        ops = svc.bulk_ignore_rule4("ver_001", [], "u")
        assert ops == []
        repo.save_batch.assert_not_called()

    def test_all_already_ignored_does_not_call_save_batch(self):
        """所有 row 已忽略时也不调用 save_batch。"""
        repo = self._repo(ignored_gids={"row_A", "row_B"})
        svc = VppsAuditService(repo)
        ops = svc.bulk_ignore_rule4("ver_001", [{"pbom_row_gid": "row_A"}, {"pbom_row_gid": "row_B"}], "u")
        assert ops == []
        repo.save_batch.assert_not_called()

    def test_operation_fields_are_set_correctly(self):
        """验证生成的 VppsOperation 各字段值。"""
        svc = VppsAuditService(self._repo())
        rows = [{"pbom_row_gid": "row_X", "original_vpps_desc": "螺栓-A-B", "notes": "几何遮挡误报"}]
        ops = svc.bulk_ignore_rule4("ver_XYZ", rows, "user_999", "李四")

        op = ops[0]
        assert op.pbom_version_gid == "ver_XYZ"
        assert op.pbom_row_gid == "row_X"
        assert op.field_name == "vpps_desc"
        assert op.original_value == "螺栓-A-B"
        assert op.new_value is None
        assert op.notes == "几何遮挡误报"
        assert op.actor_name == "李四"
        assert op.gid           # 雪花 GID，非空

    def test_each_operation_has_unique_gid(self):
        """批量创建的操作 GID 互不相同。"""
        svc = VppsAuditService(self._repo())
        rows = [{"pbom_row_gid": f"row_{i}"} for i in range(5)]
        ops = svc.bulk_ignore_rule4("ver_001", rows, "u")
        gids = [op.gid for op in ops]
        assert len(set(gids)) == 5, "存在重复 GID"

    # ── revert_operation ──────────────────────────────────────────────────────

    def test_revert_delegates_to_repo(self):
        """revert_operation 正确调用 repo.revert 并返回其结果。"""
        reverted = _make_op(is_active=False, reverted_by_gid="user_002")
        repo = self._repo()
        repo.revert.return_value = reverted
        svc = VppsAuditService(repo)

        result = svc.revert_operation("op_001", "user_002", "王五")
        repo.revert.assert_called_once_with("op_001", "user_002", "王五")
        assert result is reverted

    def test_revert_not_found_returns_none(self):
        """操作不存在或已撤销时，service 透传 None。"""
        repo = self._repo()
        repo.revert.return_value = None
        svc = VppsAuditService(repo)
        assert svc.revert_operation("nonexistent", "u") is None

    # ── get_active_rule4_ignores ──────────────────────────────────────────────

    def test_get_active_rule4_ignores_delegates_to_repo(self):
        """直接委托给 repository，返回 set。"""
        repo = self._repo(ignored_gids={"row_1", "row_2"})
        svc = VppsAuditService(repo)
        result = svc.get_active_rule4_ignores("ver_001")
        assert result == {"row_1", "row_2"}
        repo.get_active_rule4_ignores.assert_called_once_with("ver_001")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Infra 层 — SQL 正确性验证（mock psycopg2）
# ─────────────────────────────────────────────────────────────────────────────

class TestPgVppsOperationRepository:

    # ── save_batch ────────────────────────────────────────────────────────────

    def test_save_batch_sql_uses_bop_schema(self):
        """save_batch 发出的 SQL 包含 bop.vpps_operations。"""
        mc, conn = _make_cursor_and_conn()
        repo = PgVppsOperationRepository(conn)
        repo.save_batch([_make_op(gid="op_1"), _make_op(gid="op_2", pbom_row_gid="row_002")])

        assert mc.executemany.called
        sql = mc.executemany.call_args[0][0]
        assert "bop.vpps_operations" in sql
        assert "INTO vpps_operations" not in sql   # 无裸表名

    def test_save_batch_row_count_matches_ops(self):
        """save_batch 传给 executemany 的参数行数等于 ops 数量。"""
        mc, conn = _make_cursor_and_conn()
        repo = PgVppsOperationRepository(conn)
        repo.save_batch([_make_op(gid=f"op_{i}") for i in range(3)])
        rows = mc.executemany.call_args[0][1]
        assert len(rows) == 3

    def test_save_batch_empty_skips_db(self):
        """空列表不调用 executemany。"""
        mc, conn = _make_cursor_and_conn()
        repo = PgVppsOperationRepository(conn)
        repo.save_batch([])
        mc.executemany.assert_not_called()

    def test_save_single_sql_uses_bop_schema(self):
        """save 发出的 INSERT SQL 包含 bop.vpps_operations。"""
        mc, conn = _make_cursor_and_conn()
        repo = PgVppsOperationRepository(conn)
        repo.save(_make_op())
        sql = mc.execute.call_args[0][0]
        assert "bop.vpps_operations" in sql

    # ── get_active_rule4_ignores ──────────────────────────────────────────────

    def test_get_rule4_ignores_sql_uses_bop_schema(self):
        """SELECT SQL 包含 bop.vpps_operations。"""
        mc, conn = _make_cursor_and_conn()
        mc.fetchall.return_value = [{"pbom_row_gid": "r1"}, {"pbom_row_gid": "r2"}]
        repo = PgVppsOperationRepository(conn)
        result = repo.get_active_rule4_ignores("ver_001")

        sql = mc.execute.call_args[0][0]
        assert "bop.vpps_operations" in sql
        assert "rule4_bulk_ignore" in sql
        assert result == {"r1", "r2"}

    def test_get_rule4_ignores_filters_by_version_gid(self):
        """SQL 参数中含有传入的 pbom_version_gid。"""
        mc, conn = _make_cursor_and_conn()
        mc.fetchall.return_value = []
        repo = PgVppsOperationRepository(conn)
        repo.get_active_rule4_ignores("ver_SPECIFIC")
        params = mc.execute.call_args[0][1]
        assert "ver_SPECIFIC" in params

    def test_get_rule4_ignores_empty_returns_empty_set(self):
        """DB 无记录时返回空 set。"""
        mc, conn = _make_cursor_and_conn()
        mc.fetchall.return_value = []
        repo = PgVppsOperationRepository(conn)
        assert repo.get_active_rule4_ignores("ver_001") == set()

    # ── get_active_by_version ─────────────────────────────────────────────────

    def test_get_active_by_version_sql_uses_bop_schema(self):
        """不带 operation_type 参数时 SQL 含 bop.vpps_operations。"""
        mc, conn = _make_cursor_and_conn()
        mc.fetchall.return_value = []
        repo = PgVppsOperationRepository(conn)
        repo.get_active_by_version("ver_001")
        sql = mc.execute.call_args[0][0]
        assert "bop.vpps_operations" in sql

    def test_get_active_by_version_with_type_filter_passes_param(self):
        """传入 operation_type 时参数中包含该值。"""
        mc, conn = _make_cursor_and_conn()
        mc.fetchall.return_value = []
        repo = PgVppsOperationRepository(conn)
        repo.get_active_by_version("ver_001", operation_type="rule4_bulk_ignore")
        params = mc.execute.call_args[0][1]
        assert "rule4_bulk_ignore" in params

    # ── revert ────────────────────────────────────────────────────────────────

    def test_revert_sql_uses_bop_schema(self):
        """UPDATE SQL 含 bop.vpps_operations 且有 RETURNING。"""
        mc, conn = _make_cursor_and_conn()
        mc.fetchone.return_value = None
        repo = PgVppsOperationRepository(conn)
        repo.revert("op_001", "user_002", "王五")

        sql = mc.execute.call_args[0][0]
        assert "bop.vpps_operations" in sql
        assert "RETURNING" in sql.upper()

    def test_revert_sql_sets_is_active_false(self):
        """UPDATE SQL 将 is_active 置为 FALSE。"""
        mc, conn = _make_cursor_and_conn()
        mc.fetchone.return_value = None
        repo = PgVppsOperationRepository(conn)
        repo.revert("op_001", "user_002", "王五")
        sql = mc.execute.call_args[0][0].replace(" ", "").upper()
        assert "IS_ACTIVE=FALSE" in sql or "IS_ACTIVE=FALSE" in sql

    def test_revert_returns_none_when_not_found(self):
        """fetchone 为 None 时返回 None。"""
        mc, conn = _make_cursor_and_conn()
        mc.fetchone.return_value = None
        repo = PgVppsOperationRepository(conn)
        assert repo.revert("op_nonexistent", "u", "") is None

    def test_revert_returns_operation_when_found(self):
        """fetchone 返回数据时构造正确的 VppsOperation。"""
        mc, conn = _make_cursor_and_conn()
        mc.fetchone.return_value = _op_as_db_row(
            _make_op(is_active=False, reverted_by_gid="user_002", reverted_by_name="王五")
        )
        repo = PgVppsOperationRepository(conn)
        result = repo.revert("op_001", "user_002", "王五")

        assert isinstance(result, VppsOperation)
        assert result.is_active is False
        assert result.reverted_by_gid == "user_002"
        assert result.reverted_by_name == "王五"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Router 端点测试
# ─────────────────────────────────────────────────────────────────────────────

class TestVppsAuditRoutes:

    # ── POST /api/vpps-operations/rule4-bulk-ignore ───────────────────────────

    def test_bulk_ignore_returns_200_and_created_count(self, client, mock_conn):
        """正常请求返回 200，success=True，created=行数。"""
        _, mc = mock_conn
        mc.fetchall.return_value = []   # 无已忽略行

        resp = client.post("/api/vpps-operations/rule4-bulk-ignore", json={
            "pbom_version_gid": "ver_001",
            "rows": [
                {"pbom_row_gid": "row_A", "original_vpps_desc": "螺栓-A-B"},
                {"pbom_row_gid": "row_B", "original_vpps_desc": "螺母-C"},
            ],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["created"] == 2
        assert len(data["operations"]) == 2

    def test_bulk_ignore_operation_type_is_rule4(self, client, mock_conn):
        """返回的 operation operation_type 为 rule4_bulk_ignore。"""
        _, mc = mock_conn
        mc.fetchall.return_value = []

        resp = client.post("/api/vpps-operations/rule4-bulk-ignore", json={
            "pbom_version_gid": "ver_001",
            "rows": [{"pbom_row_gid": "row_A"}],
        })
        op = resp.json()["operations"][0]
        assert op["operation_type"] == "rule4_bulk_ignore"
        assert op["rule_no"] == 4
        assert op["is_active"] is True

    def test_bulk_ignore_uses_jwt_actor_when_not_provided(self, client, mock_conn):
        """未传 actor_gid 时使用 JWT user.gid。"""
        _, mc = mock_conn
        mc.fetchall.return_value = []

        resp = client.post("/api/vpps-operations/rule4-bulk-ignore", json={
            "pbom_version_gid": "ver_001",
            "rows": [{"pbom_row_gid": "row_A"}],
        })
        op = resp.json()["operations"][0]
        assert op["actor_gid"] == "test_user_gid"

    def test_bulk_ignore_idempotent_skips_already_ignored(self, client, mock_conn):
        """row_A 已在 DB 中，再次提交 created=0。"""
        _, mc = mock_conn
        mc.fetchall.return_value = [{"pbom_row_gid": "row_A"}]  # 已忽略

        resp = client.post("/api/vpps-operations/rule4-bulk-ignore", json={
            "pbom_version_gid": "ver_001",
            "rows": [{"pbom_row_gid": "row_A"}],
        })
        assert resp.status_code == 200
        assert resp.json()["created"] == 0

    def test_bulk_ignore_partial_idempotent(self, client, mock_conn):
        """row_A 已忽略，row_B 未忽略，created=1。"""
        _, mc = mock_conn
        mc.fetchall.return_value = [{"pbom_row_gid": "row_A"}]

        resp = client.post("/api/vpps-operations/rule4-bulk-ignore", json={
            "pbom_version_gid": "ver_001",
            "rows": [{"pbom_row_gid": "row_A"}, {"pbom_row_gid": "row_B"}],
        })
        assert resp.json()["created"] == 1

    def test_bulk_ignore_empty_rows_returns_created_0(self, client, mock_conn):
        """空 rows 时返回 created=0。"""
        _, mc = mock_conn
        mc.fetchall.return_value = []

        resp = client.post("/api/vpps-operations/rule4-bulk-ignore", json={
            "pbom_version_gid": "ver_001",
            "rows": [],
        })
        assert resp.status_code == 200
        assert resp.json()["created"] == 0

    # ── GET /api/vpps-operations ──────────────────────────────────────────────

    def test_list_operations_returns_200(self, client, mock_conn):
        """正常返回 200 + empty data list。"""
        _, mc = mock_conn
        mc.fetchall.return_value = []
        resp = client.get("/api/vpps-operations?pbom_version_gid=ver_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] == []

    def test_list_operations_with_type_filter(self, client, mock_conn):
        """operation_type 参数被接受，不报错。"""
        _, mc = mock_conn
        mc.fetchall.return_value = []
        resp = client.get(
            "/api/vpps-operations"
            "?pbom_version_gid=ver_001&operation_type=rule4_bulk_ignore"
        )
        assert resp.status_code == 200

    def test_list_operations_missing_version_gid_returns_422(self, client, mock_conn):
        """缺少必需的 pbom_version_gid 参数时返回 422 Validation Error。"""
        resp = client.get("/api/vpps-operations")
        assert resp.status_code == 422

    # ── GET /api/vpps-operations/rule4-ignores ────────────────────────────────

    def test_rule4_ignores_returns_gid_set(self, client, mock_conn):
        """返回的 ignored_row_gids 包含 DB 中的所有已忽略行。"""
        _, mc = mock_conn
        mc.fetchall.return_value = [
            {"pbom_row_gid": "row_1"},
            {"pbom_row_gid": "row_2"},
        ]
        resp = client.get("/api/vpps-operations/rule4-ignores?pbom_version_gid=ver_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert set(data["ignored_row_gids"]) == {"row_1", "row_2"}

    def test_rule4_ignores_empty_when_none_ignored(self, client, mock_conn):
        """无已忽略行时返回空列表。"""
        _, mc = mock_conn
        mc.fetchall.return_value = []
        resp = client.get("/api/vpps-operations/rule4-ignores?pbom_version_gid=ver_001")
        assert resp.status_code == 200
        assert resp.json()["ignored_row_gids"] == []

    def test_rule4_ignores_missing_version_gid_returns_422(self, client, mock_conn):
        """缺少 pbom_version_gid 返回 422。"""
        resp = client.get("/api/vpps-operations/rule4-ignores")
        assert resp.status_code == 422

    # ── POST /api/vpps-operations/{gid}/revert ────────────────────────────────

    def test_revert_success_returns_200(self, client, mock_conn):
        """成功撤销返回 200 + 更新后的 operation（is_active=False）。"""
        _, mc = mock_conn
        mc.fetchone.return_value = _op_as_db_row(
            _make_op(is_active=False, reverted_by_gid="test_user_gid", reverted_by_name="Test User",
                     reverted_at=_NOW)
        )
        resp = client.post("/api/vpps-operations/op_001/revert", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["operation"]["is_active"] is False
        assert data["operation"]["gid"] == "op_gid_001"

    def test_revert_not_found_returns_404(self, client, mock_conn):
        """操作不存在或已撤销时返回 404。"""
        _, mc = mock_conn
        mc.fetchone.return_value = None
        resp = client.post("/api/vpps-operations/nonexistent/revert", json={})
        assert resp.status_code == 404

    def test_revert_uses_jwt_actor_when_not_provided(self, client, mock_conn):
        """未传 reverted_by_gid 时使用 JWT user.gid。"""
        _, mc = mock_conn
        mc.fetchone.return_value = _op_as_db_row(
            _make_op(is_active=False, reverted_by_gid="test_user_gid", reverted_at=_NOW)
        )
        resp = client.post("/api/vpps-operations/op_001/revert", json={})
        assert resp.status_code == 200
        # 验证 SQL 参数中包含 JWT user gid
        params = mc.execute.call_args[0][1]
        assert "test_user_gid" in params


class TestBopCreateEntry:
    def test_create_entry_sets_default_version_no_for_operation(self, bop_entries_module, bop_mock_conn):
        _, mc = bop_mock_conn
        mc.fetchone.side_effect = [
            {"status": "active"},
            {"level": 2},
            {"project_gid": "proj_001"},
            {"frozen_at": None},
            {"gid": "entry_gid_001", "entity_gid": "entity_gid_001"},
            None,
        ]
        mc.fetchall.return_value = []

        body = bop_entries_module.CreateEntryBody(
            version_gid="ver_001",
            parent_gid="parent_001",
            node_type="operation",
            sort_order=1,
            title="新加工序",
            vpps="VPPS-001",
            vpps_desc="desc",
        )

        bop_entries_module.create_entry(body, _u={"gid": "user_001", "name": "Tester"})

        sql_to_params = [
            (str(call.args[0]), call.args[1] if len(call.args) > 1 else None)
            for call in mc.execute.call_args_list
        ]
        entity_insert = next(
            params
            for sql, params in sql_to_params
            if "INSERT INTO workmanship_bop_bop_steps" in sql
        )
        assert entity_insert[1:] == (
            "proj_001",
            "01",
            "新加工序",
            "VPPS-001",
            "desc",
            "",
            False,
            "{}",
            "{}",
        )

        entry_insert = next(
            params
            for sql, params in sql_to_params
            if "INSERT INTO workmanship_bop_bop_entries" in sql
        )
        assert entry_insert[7:] == (
            "新加工序",
            "VPPS-001",
            "desc",
            "",
            False,
            "",
            "",
            None,
            "{}",
            None,
        )

    def test_create_entry_sets_default_vpps_part_for_process(self, bop_entries_module, bop_mock_conn):
        _, mc = bop_mock_conn
        mc.fetchone.side_effect = [
            {"status": "active"},
            {"level": 1},
            {"project_gid": "proj_001"},
            {"frozen_at": None},
            {"gid": "entry_gid_002", "entity_gid": "entity_gid_002"},
            None,
        ]
        mc.fetchall.return_value = []

        body = bop_entries_module.CreateEntryBody(
            version_gid="ver_001",
            parent_gid="parent_001",
            node_type="process",
            sort_order=2,
            title="新工序",
            vpps="VPPS-002",
            vpps_desc="process desc",
        )

        bop_entries_module.create_entry(body, _u={"gid": "user_001", "name": "Tester"})

        sql_to_params = [
            (str(call.args[0]), call.args[1] if len(call.args) > 1 else None)
            for call in mc.execute.call_args_list
        ]
        process_insert = next(
            params
            for sql, params in sql_to_params
            if "INSERT INTO workmanship_bop_bop_process" in sql
        )
        assert process_insert[1:] == (
            "proj_001",
            "ver_001",
            "01",
            "新工序",
            "VPPS-002",
            "process desc",
            "",
            False,
            "{}",
            "{}",
        )

    def test_create_entry_sets_default_ext_for_line_process(self, bop_entries_module, bop_mock_conn):
        _, mc = bop_mock_conn
        mc.fetchone.side_effect = [
            {"status": "active"},
            {"project_gid": "proj_001"},
            {"gid": "entry_gid_003", "entity_gid": "entity_gid_003"},
            None,
        ]
        mc.fetchall.return_value = []

        body = bop_entries_module.CreateEntryBody(
            version_gid="ver_001",
            node_type="line_process",
            sort_order=3,
            title="新线体工艺",
            vpps="VPPS-003",
        )

        bop_entries_module.create_entry(body, _u={"gid": "user_001", "name": "Tester"})

        sql_to_params = [
            (str(call.args[0]), call.args[1] if len(call.args) > 1 else None)
            for call in mc.execute.call_args_list
        ]
        line_insert = next(
            params
            for sql, params in sql_to_params
            if "INSERT INTO workmanship_bop_bop_line" in sql
        )
        assert line_insert[1:] == (
            "proj_001",
            "01",
            "新线体工艺",
            "VPPS-003",
            "{}",
        )

    def test_create_entry_sets_default_ext_for_station_process(self, bop_entries_module, bop_mock_conn):
        _, mc = bop_mock_conn
        mc.fetchone.side_effect = [
            {"status": "active"},
            {"project_gid": "proj_001"},
            {"gid": "entry_gid_004", "entity_gid": "entity_gid_004"},
            None,
        ]
        mc.fetchall.return_value = []

        body = bop_entries_module.CreateEntryBody(
            version_gid="ver_001",
            node_type="station_process",
            sort_order=4,
            title="新工位工艺",
            vpps="VPPS-004",
        )

        bop_entries_module.create_entry(body, _u={"gid": "user_001", "name": "Tester"})

        sql_to_params = [
            (str(call.args[0]), call.args[1] if len(call.args) > 1 else None)
            for call in mc.execute.call_args_list
        ]
        station_insert = next(
            params
            for sql, params in sql_to_params
            if "INSERT INTO workmanship_bop_bop_station" in sql
        )
        assert station_insert[1:] == (
            "proj_001",
            "01",
            "新工位工艺",
            "VPPS-004",
            "{}",
        )

    def test_create_entry_sets_position_ext_for_operator_process(self, bop_entries_module, bop_mock_conn):
        _, mc = bop_mock_conn
        mc.fetchone.side_effect = [
            {"status": "active"},
            {"project_gid": "proj_001"},
            {"gid": "entry_gid_005", "entity_gid": "entity_gid_005"},
            None,
        ]
        mc.fetchall.return_value = []

        body = bop_entries_module.CreateEntryBody(
            version_gid="ver_001",
            node_type="operator_process",
            sort_order=5,
            title="新岗位工艺",
            vpps="VPPS-005",
            position="A",
        )

        bop_entries_module.create_entry(body, _u={"gid": "user_001", "name": "Tester"})

        sql_to_params = [
            (str(call.args[0]), call.args[1] if len(call.args) > 1 else None)
            for call in mc.execute.call_args_list
        ]
        operator_insert = next(
            params
            for sql, params in sql_to_params
            if "INSERT INTO workmanship_bop_bop_operator" in sql
        )
        assert operator_insert[1:] == (
            "proj_001",
            "01",
            "新岗位工艺",
            "VPPS-005",
            '{"position": "A"}',
        )

class TestVppsAuditSchemaPrefixes:
    """确认所有端点发出的 SQL 都不含裸表名 vpps_operations（必须有 bop. 前缀）。"""

    def _assert_no_bare_table(self, mc, endpoint_name: str):
        sqls = _collect_sqls(mc)
        assert sqls, f"[{endpoint_name}] 未捕获到任何 SQL 调用"
        for sql in sqls:
            if "vpps_operations" in sql:
                assert "bop.vpps_operations" in sql, (
                    f"[{endpoint_name}] SQL 使用裸表名 vpps_operations（缺少 bop. 前缀）:\n{sql}"
                )

    def test_bulk_ignore_sql_prefix(self, client, mock_conn):
        _, mc = mock_conn
        mc.fetchall.return_value = []
        client.post("/api/vpps-operations/rule4-bulk-ignore", json={
            "pbom_version_gid": "ver_001",
            "rows": [{"pbom_row_gid": "row_A"}],
        })
        self._assert_no_bare_table(mc, "POST /rule4-bulk-ignore")

    def test_list_operations_sql_prefix(self, client, mock_conn):
        _, mc = mock_conn
        mc.fetchall.return_value = []
        client.get("/api/vpps-operations?pbom_version_gid=ver_001")
        self._assert_no_bare_table(mc, "GET /vpps-operations")

    def test_rule4_ignores_sql_prefix(self, client, mock_conn):
        _, mc = mock_conn
        mc.fetchall.return_value = []
        client.get("/api/vpps-operations/rule4-ignores?pbom_version_gid=ver_001")
        self._assert_no_bare_table(mc, "GET /rule4-ignores")

    def test_revert_sql_prefix(self, client, mock_conn):
        _, mc = mock_conn
        mc.fetchone.return_value = None
        client.post("/api/vpps-operations/op_001/revert", json={})
        self._assert_no_bare_table(mc, "POST /revert")


# ─────────────────────────────────────────────────────────────────────────────
# 5. 前端 JS 静态检查（文件内容验证）
# ─────────────────────────────────────────────────────────────────────────────

import re
from pathlib import Path

_WEB = Path(__file__).parents[2] / "web"


class TestFrontendJsStaticCheck:
    """
    不执行 JS，只检查 ebom.js / list_diff_shell.js 的关键代码片段是否存在。
    用于防止意外删除或重构时丢失关键逻辑。
    """

    def _read(self, rel_path: str) -> str:
        return (_WEB / rel_path).read_text(encoding="utf-8")

    # ── ebom.js ───────────────────────────────────────────────────────────────

    def test_ebom_has_vpps_ignored_row_gids_variable(self):
        """ebom.js 中存在 _vppsIgnoredRowGids 全局变量声明。"""
        src = self._read("ebom/ebom.js")
        assert "_vppsIgnoredRowGids" in src

    def test_ebom_fetches_rule4_ignores_api(self):
        """ebom.js 在 run() 中调用 /api/vpps-operations/rule4-ignores 端点。"""
        src = self._read("ebom/ebom.js")
        assert "/api/vpps-operations/rule4-ignores" in src

    def test_ebom_ignores_already_ignored_rows(self):
        """ebom.js rule4 forEach 中包含对 _vppsIgnoredRowGids 的 has() 检查。"""
        src = self._read("ebom/ebom.js")
        assert "_vppsIgnoredRowGids.has(p.gid)" in src

    def test_ebom_collects_rule4_nok_row_map(self):
        """ebom.js 中存在 rule4NokRowMap 用于收集 NOK 零件行。"""
        src = self._read("ebom/ebom.js")
        assert "rule4NokRowMap" in src

    def test_ebom_result_has_ignore_rule4_key(self):
        """ebom.js 的 result 对象中包含 ignoreRule4 回调定义。"""
        src = self._read("ebom/ebom.js")
        assert "ignoreRule4" in src

    def test_ebom_calls_bulk_ignore_api(self):
        """ebom.js 中调用 /api/vpps-operations/rule4-bulk-ignore。"""
        src = self._read("ebom/ebom.js")
        assert "/api/vpps-operations/rule4-bulk-ignore" in src

    def test_ebom_summary_uses_rule4_nok_row_map_size(self):
        """summary 中"主件不一致"的 count 来自 rule4NokRowMap.size（零件行数，而非错误条数）。"""
        src = self._read("ebom/ebom.js")
        # 确认 summary 用的是 rule4NokRowMap.size 而非 rule4Errors.length
        assert re.search(r"主件不一致.*rule4NokRowMap\.size|rule4NokRowMap\.size.*主件不一致", src)

    def test_ebom_ok_uses_rule4_nok_row_map_size(self):
        """ok 判断使用 rule4NokRowMap.size === 0。"""
        src = self._read("ebom/ebom.js")
        assert "rule4NokRowMap.size === 0" in src

    # ── list_diff_shell.js ────────────────────────────────────────────────────

    def test_diff_shell_renders_ignore_rule4_button(self):
        """list_diff_shell.js 的结论面板渲染了 ignoreRule4 按钮。"""
        src = self._read("components/list_diff_shell.js")
        assert "ignoreRule4" in src

    def test_diff_shell_button_class_is_ignore_r4(self):
        """按钮使用 lds-batch-btn-ignore-r4 CSS 类。"""
        src = self._read("components/list_diff_shell.js")
        assert "lds-batch-btn-ignore-r4" in src

    def test_diff_shell_button_calls_run(self):
        """按钮 onclick 调用 ignoreRule4 的 run 函数。"""
        src = self._read("components/list_diff_shell.js")
        assert "ignoreRule4" in src and "await run()" in src

    def test_diff_shell_css_has_ignore_r4_style(self):
        """list_diff_shell.css 中存在 .lds-batch-btn-ignore-r4 样式定义。"""
        css = (_WEB / "components/list_diff_shell.css").read_text(encoding="utf-8")
        assert ".lds-batch-btn-ignore-r4" in css
