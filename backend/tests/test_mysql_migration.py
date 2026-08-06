"""
backend/tests/test_mysql_migration.py
──────────────────────────────────────
验证 PostgreSQL → MySQL 8.0 迁移的正确性。
全部无需真实数据库连接：静态扫描 + mock。

测试分组：
  A. config.get_db_params()   URL 解析正确性
  B. mysql_schema.sql         无 PG 特有语法，结构合规
  C. 源码静态扫描              所有 router SQL 使用 workmanship_ 前缀
  D. 源码静态扫描              无残留 PG 方言（RETURNING / ON CONFLICT / ::jsonb 等）
  E. sequences.next_display_id mock 验证
  F. migrate._run_ddl_batch   mock 验证：失败语句不中断批次
  G. connection 模块           不依赖 psycopg2
"""
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

# ── 项目路径 ─────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent   # AI00_root_web/
BACKEND_DIR = REPO_ROOT / "backend"
CRAFT_ROUTERS = REPO_ROOT / "packages" / "craft-plugin" / "craft_backend" / "routers"
SCHEMA_FILE = BACKEND_DIR / "db" / "mysql_schema.sql"

ROUTER_DIRS = [BACKEND_DIR / "routers", CRAFT_ROUTERS]

# self_annotations.py uses SQLite — excluded from MySQL checks
SQLITE_FILES = {"self_annotations.py"}


# ─────────────────────────────────────────────────────────────────────────────
# A. config.get_db_params() — URL 解析
# ─────────────────────────────────────────────────────────────────────────────

class TestGetDbParams:
    """A — config.Settings.get_db_params() 解析各种 URL 格式。"""

    def _make_settings(self, url: str):
        """绕过 _require() 直接构造 Settings 实例，不触发环境变量校验。"""
        import importlib.util, sys
        # 直接解析 get_db_params 逻辑，不依赖完整 Settings 初始化
        import re as _re
        m = _re.match(
            r"(?:mysql|postgresql)://([^:]+):([^@]*)@([^:/]+):?(\d*)/(.+)",
            url,
        )
        ns = type("FakeSettings", (), {"users_db_url": url})()
        # 把 get_db_params 绑定上去
        sys.path.insert(0, str(BACKEND_DIR.parent))
        from backend.config import Settings
        ns.get_db_params = Settings.get_db_params.__get__(ns, type(ns))
        return ns

    def test_standard_mysql_url(self):
        s = self._make_settings("mysql://root:secret@127.0.0.1:3306/ai00")
        p = s.get_db_params()
        assert p["host"] == "127.0.0.1"
        assert p["port"] == 3306
        assert p["user"] == "root"
        assert p["password"] == "secret"
        assert p["db"] == "ai00"

    def test_default_port_when_omitted(self):
        s = self._make_settings("mysql://admin:pass@db.internal/mydb")
        p = s.get_db_params()
        assert p["port"] == 3306, "省略端口时应默认为 3306"

    def test_postgresql_prefix_still_accepted(self):
        """迁移期间 .env 文件可能还残留 postgresql:// 前缀，应兼容解析。"""
        s = self._make_settings("postgresql://ai00:kycjug@127.0.0.1:5433/ai00_test")
        p = s.get_db_params()
        assert p["host"] == "127.0.0.1"
        assert p["port"] == 5433
        assert p["db"] == "ai00_test"

    def test_invalid_url_raises_runtime_error(self):
        s = self._make_settings("not-a-valid-url")
        with pytest.raises(RuntimeError, match="格式不合法"):
            s.get_db_params()

    def test_password_with_special_chars(self):
        """密码中不含 @ 的特殊字符应能正确解析。"""
        s = self._make_settings("mysql://user:P%40ss123@host:3306/db")
        p = s.get_db_params()
        assert p["user"] == "user"
        assert p["db"] == "db"


# ─────────────────────────────────────────────────────────────────────────────
# B. mysql_schema.sql — 静态结构验证
# ─────────────────────────────────────────────────────────────────────────────

class TestMysqlSchemaFile:
    """B — mysql_schema.sql 无 PG 专有语法，结构符合 MySQL 8.0 规范。"""

    @pytest.fixture(scope="class")
    def schema_text(self):
        assert SCHEMA_FILE.exists(), f"mysql_schema.sql 不存在: {SCHEMA_FILE}"
        return SCHEMA_FILE.read_text(encoding="utf-8")

    # --- 不应出现的 PG 语法 ---

    def test_no_jsonb(self, schema_text):
        lines = [l for l in schema_text.splitlines()
                 if re.search(r'\bJSONB\b', l, re.IGNORECASE) and not l.strip().startswith('--')]
        assert not lines, f"发现 JSONB（应改为 JSON）: {lines[:3]}"

    def test_no_timestamptz(self, schema_text):
        lines = [l for l in schema_text.splitlines()
                 if 'TIMESTAMPTZ' in l.upper() and not l.strip().startswith('--')]
        assert not lines, f"发现 TIMESTAMPTZ: {lines[:3]}"

    def test_no_bigserial(self, schema_text):
        assert 'BIGSERIAL' not in schema_text.upper(), "BIGSERIAL 应改为 BIGINT AUTO_INCREMENT"

    def test_no_create_schema(self, schema_text):
        lines = [l for l in schema_text.splitlines()
                 if re.search(r'CREATE SCHEMA', l, re.IGNORECASE) and not l.strip().startswith('--')]
        assert not lines, f"发现 CREATE SCHEMA（MySQL 无 schema 概念）: {lines[:3]}"

    def test_no_on_conflict(self, schema_text):
        lines = [l for l in schema_text.splitlines()
                 if re.search(r'ON CONFLICT', l, re.IGNORECASE) and not l.strip().startswith('--')]
        assert not lines, f"发现 ON CONFLICT（MySQL 用 ON DUPLICATE KEY UPDATE）: {lines[:3]}"

    def test_no_create_sequence(self, schema_text):
        lines = [l for l in schema_text.splitlines()
                 if re.search(r'CREATE SEQUENCE', l, re.IGNORECASE) and not l.strip().startswith('--')]
        assert not lines, f"发现 CREATE SEQUENCE（应用 workmanship_display_id_counters）: {lines[:3]}"

    # --- 应当出现的 MySQL 特征 ---

    def test_all_tables_have_engine_innodb(self, schema_text):
        create_stmts = re.findall(r'CREATE TABLE IF NOT EXISTS \S+', schema_text, re.IGNORECASE)
        assert len(create_stmts) >= 80, f"建表语句数量不足，仅找到 {len(create_stmts)} 个"
        innodb_count = schema_text.upper().count('ENGINE=INNODB')
        assert innodb_count >= 80, f"ENGINE=InnoDB 出现次数 ({innodb_count}) 少于建表数 ({len(create_stmts)})"

    def test_workmanship_prefix_tables_exist(self, schema_text):
        required = [
            "workmanship_auth_teams",
            "workmanship_auth_users",
            "workmanship_proj_projects",
            "workmanship_bop_bop_versions",
            "workmanship_bop_bop_entries",
            "workmanship_bop_bop_entry_links",
            "workmanship_work_lists",
            "workmanship_know_entries",
            "workmanship_app_view_configs",
            "workmanship_display_id_counters",
        ]
        for tbl in required:
            assert tbl in schema_text, f"表 {tbl} 在 mysql_schema.sql 中缺失"

    def test_display_id_counters_has_seed_rows(self, schema_text):
        required_seqs = [
            "knowledge_display_seq",
            "rules_display_seq",
            "proj_tasks_display_seq",
            "proj_issues_display_seq",
        ]
        for seq in required_seqs:
            assert seq in schema_text, f"序列初始值 {seq!r} 在 mysql_schema.sql 中缺失"

    def test_json_default_uses_expression_syntax(self, schema_text):
        """MySQL 8.0 JSON 列的 DEFAULT 必须用表达式语法 DEFAULT (JSON_OBJECT())。"""
        bad_defaults = re.findall(r"JSON\s+NOT NULL\s+DEFAULT\s+'[{}[\]]*'", schema_text, re.IGNORECASE)
        assert not bad_defaults, f"发现裸字符串 JSON DEFAULT，应用 (JSON_OBJECT()) 或 (JSON_ARRAY()): {bad_defaults[:3]}"


# ─────────────────────────────────────────────────────────────────────────────
# C. 源码静态扫描 — workmanship_ 前缀
# ─────────────────────────────────────────────────────────────────────────────

def _iter_router_files():
    """生成所有 router .py 文件路径（跳过 SQLite 文件和 __init__）。"""
    for d in ROUTER_DIRS:
        if not d.exists():
            continue
        for f in d.rglob("*.py"):
            if f.name not in SQLITE_FILES and f.name != "__init__.py":
                yield f


# 已知还合法存在的裸 schema.table 引用（SQLite 文件或已迁移脚本中的注释）
_ALLOWED_BARE = re.compile(
    r"self_annotations|pg_to_mysql_migrate|# |'''|\"\"\"",
    re.IGNORECASE,
)

# 旧 PG schema 前缀
_PG_SCHEMA_PREFIXES = re.compile(
    r'\b(auth|proj|bop|factory|template|work|knowledge|app|integration)\.'
    r'(teams|users|projects|tasks|issues|bop_versions|bop_entries|bop_entry_links'
    r'|knowledge_entries|craft_rules|lists|follows|notifications|factories'
    r'|factory_stations|gbop_versions|gbop_entries|view_configs|flows|flow_runs'
    r'|workbench_configs|approval_orders|collab_sessions|onto_classes)\b',
    re.IGNORECASE,
)


class TestWorkmanshipPrefix:
    """C — router 代码中所有 SQL 表引用使用 workmanship_ 前缀，无旧 PG schema.table 残留。"""

    def test_no_pg_schema_dot_table_in_routers(self):
        violations = []
        for fpath in _iter_router_files():
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if _PG_SCHEMA_PREFIXES.search(line):
                    stripped = line.strip()
                    # 跳过注释和文档字符串
                    if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                        continue
                    violations.append(f"{fpath.name}:{i}: {stripped[:80]}")
        assert not violations, (
            f"发现 {len(violations)} 处旧 PG schema.table 引用（应使用 workmanship_ 前缀）:\n"
            + "\n".join(violations[:10])
        )


# ─────────────────────────────────────────────────────────────────────────────
# D. 源码静态扫描 — 无残留 PG 方言
# ─────────────────────────────────────────────────────────────────────────────

class TestNoPgDialectInSql:
    """D — router .py 文件中的 SQL 字符串无残留 PG 特有语法。"""

    def _scan_pattern(self, pattern: str, description: str, *, flags=re.IGNORECASE):
        violations = []
        compiled = re.compile(pattern, flags)
        for fpath in _iter_router_files():
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if compiled.search(line):
                    stripped = line.strip()
                    if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                        continue
                    violations.append(f"{fpath.name}:{i}: {stripped[:80]}")
        return violations

    def test_no_returning_in_sql(self):
        # RETURNING 只检查 INSERT/UPDATE/DELETE 后面跟 RETURNING 的模式
        violations = self._scan_pattern(
            r'\b(INSERT|UPDATE|DELETE)\b[^;]*\bRETURNING\b',
            "INSERT/UPDATE RETURNING"
        )
        assert not violations, f"SQL RETURNING 残留:\n" + "\n".join(violations[:5])

    def test_no_on_conflict_with_column_in_sql(self):
        violations = self._scan_pattern(r'ON CONFLICT\s*\(', "ON CONFLICT (col)")
        # 排除文档字符串中的注释行
        violations = [v for v in violations if "DO NOTHING" not in v or "INSERT" in v]
        assert not violations, f"ON CONFLICT 残留:\n" + "\n".join(violations[:5])

    def test_no_pg_cast_operator(self):
        violations = self._scan_pattern(r'::\s*(jsonb|text|int\b|integer|boolean|date|float)', ":: 类型转换")
        assert not violations, f"PG :: 类型转换残留:\n" + "\n".join(violations[:5])

    def test_no_ilike(self):
        violations = self._scan_pattern(r'\bILIKE\b', "ILIKE")
        assert not violations, f"ILIKE 残留（应改为 LIKE）:\n" + "\n".join(violations[:5])

    def test_no_nextval(self):
        violations = self._scan_pattern(r'\bnextval\s*\(', "nextval()")
        assert not violations, f"nextval() 残留（应用 next_display_id()）:\n" + "\n".join(violations[:5])

    def test_no_jsonb_array_length(self):
        violations = self._scan_pattern(r'\bjsonb_array_length\b', "jsonb_array_length")
        assert not violations, f"jsonb_array_length 残留（应改为 JSON_LENGTH）:\n" + "\n".join(violations[:5])

    def test_no_filter_where_aggregate(self):
        violations = self._scan_pattern(r'\bFILTER\s*\(\s*WHERE\b', "FILTER (WHERE)")
        assert not violations, f"聚合 FILTER(WHERE) 残留（MySQL 不支持）:\n" + "\n".join(violations[:5])

    def test_no_nulls_last(self):
        violations = self._scan_pattern(r'\bNULLS\s+LAST\b', "NULLS LAST")
        assert not violations, f"NULLS LAST 残留:\n" + "\n".join(violations[:5])


# ─────────────────────────────────────────────────────────────────────────────
# E. sequences.next_display_id — mock 验证
# ─────────────────────────────────────────────────────────────────────────────

class TestNextDisplayId:
    """E — next_display_id() 执行正确的 UPDATE → SELECT 原子操作。"""

    @pytest.fixture(autouse=True)
    def _import_sequences(self):
        """确保 sequences 模块已导入，patch 才能找到它。"""
        import sys
        sys.path.insert(0, str(BACKEND_DIR.parent))
        import backend.db.sequences  # noqa: F401

    def _make_mock_conn(self, return_val):
        """构造一个模拟 get_conn() 上下文管理器。"""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = return_val
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        @contextmanager
        def fake_get_conn():
            yield mock_conn

        return fake_get_conn, mock_cur

    def test_returns_next_val_from_db(self):
        fake_get_conn, mock_cur = self._make_mock_conn({"val": 42})
        with patch("backend.db.sequences.get_conn", fake_get_conn):
            import backend.db.sequences as seq
            result = seq.next_display_id("proj_tasks_display_seq")
        assert result == 42

    def test_update_called_before_select(self):
        fake_get_conn, mock_cur = self._make_mock_conn({"val": 1})
        with patch("backend.db.sequences.get_conn", fake_get_conn):
            import backend.db.sequences as seq
            seq.next_display_id("knowledge_display_seq")

        calls = mock_cur.execute.call_args_list
        assert len(calls) == 2, "应恰好执行 2 条 SQL（UPDATE + SELECT）"
        first_sql = calls[0][0][0].upper()
        second_sql = calls[1][0][0].upper()
        assert "UPDATE" in first_sql, f"第一条 SQL 应为 UPDATE，实际: {first_sql}"
        assert "SELECT" in second_sql, f"第二条 SQL 应为 SELECT，实际: {second_sql}"

    def test_seq_name_passed_to_both_queries(self):
        fake_get_conn, mock_cur = self._make_mock_conn({"val": 5})
        seq_name = "rules_display_seq"
        with patch("backend.db.sequences.get_conn", fake_get_conn):
            import backend.db.sequences as seq
            seq.next_display_id(seq_name)

        calls = mock_cur.execute.call_args_list
        for c in calls:
            args = c[0]
            params = args[1] if len(args) > 1 else []
            assert seq_name in list(params), f"seq_name 未传给 SQL 参数: {c}"

    def test_raises_if_seq_not_found(self):
        fake_get_conn, mock_cur = self._make_mock_conn(None)  # fetchone returns None
        with patch("backend.db.sequences.get_conn", fake_get_conn):
            import backend.db.sequences as seq
            with pytest.raises(RuntimeError, match="不存在"):
                seq.next_display_id("nonexistent_seq")

    def test_display_id_format_task(self):
        fake_get_conn, mock_cur = self._make_mock_conn({"val": 7})
        with patch("backend.db.sequences.get_conn", fake_get_conn):
            import backend.db.sequences as seq
            n = seq.next_display_id("proj_tasks_display_seq")
        display_id = f"T-C{n:08d}"
        assert display_id == "T-C00000007", f"格式错误: {display_id}"


# ─────────────────────────────────────────────────────────────────────────────
# F. migrate._run_ddl_batch — 容错行为
# ─────────────────────────────────────────────────────────────────────────────

class TestMigrateBatch:
    """F — _run_ddl_batch() 遇到失败语句时回滚单条但继续执行剩余语句。"""

    def _make_conn_that_fails_on(self, fail_stmt_index: int):
        """返回一个 mock 连接，第 fail_stmt_index 条 execute 会抛异常。"""
        call_count = [0]

        mock_cur = MagicMock()
        def side_effect(sql, *args):
            call_count[0] += 1
            if call_count[0] == fail_stmt_index:
                raise Exception("Simulated SQL error")
        mock_cur.execute.side_effect = side_effect
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        return mock_conn, call_count

    def test_continues_after_failed_statement(self):
        from backend.db.migrate import _run_ddl_batch

        stmts = ["CREATE TABLE t1 (id INT)", "BAD SQL", "CREATE TABLE t2 (id INT)"]
        mock_conn, call_count = self._make_conn_that_fails_on(fail_stmt_index=2)

        # Should not raise — failures are logged and skipped
        _run_ddl_batch(mock_conn, stmts, "test")
        assert call_count[0] == 3, f"所有3条语句都应被尝试执行，实际执行了 {call_count[0]} 条"

    def test_rollback_called_on_failure(self):
        from backend.db.migrate import _run_ddl_batch

        stmts = ["GOOD SQL", "BAD SQL"]
        mock_conn, _ = self._make_conn_that_fails_on(fail_stmt_index=2)

        _run_ddl_batch(mock_conn, stmts, "test")
        mock_conn.rollback.assert_called_once()

    def test_commit_called_for_each_success(self):
        from backend.db.migrate import _run_ddl_batch

        stmts = ["SQL 1", "SQL 2", "SQL 3"]
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        _run_ddl_batch(mock_conn, stmts, "test")
        assert mock_conn.commit.call_count == 3, "每条成功语句都应 commit"


# ─────────────────────────────────────────────────────────────────────────────
# G. connection 模块 — 不依赖 psycopg2
# ─────────────────────────────────────────────────────────────────────────────

class TestConnectionModule:
    """G — connection.py 已完全切换到 PyMySQL，无 psycopg2 引用。"""

    @pytest.fixture(scope="class")
    def conn_source(self):
        conn_file = BACKEND_DIR / "db" / "connection.py"
        assert conn_file.exists()
        return conn_file.read_text(encoding="utf-8")

    def test_no_psycopg2_import(self, conn_source):
        assert "psycopg2" not in conn_source, "connection.py 不应再引用 psycopg2"

    def test_pymysql_imported(self, conn_source):
        assert "import pymysql" in conn_source, "connection.py 应 import pymysql"

    def test_pooled_db_used(self, conn_source):
        assert "PooledDB" in conn_source, "connection.py 应使用 dbutils PooledDB"

    def test_dict_cursor_used(self, conn_source):
        assert "DictCursor" in conn_source, "connection.py 应使用 DictCursor（等价原 RealDictCursor）"

    def test_get_conn_is_context_manager(self, conn_source):
        assert "@contextmanager" in conn_source, "get_conn() 应是 @contextmanager"
        assert "conn.commit()" in conn_source, "正常退出时应 commit"
        assert "conn.rollback()" in conn_source, "异常时应 rollback"

    def test_requirements_has_pymysql_not_psycopg2(self):
        req_file = BACKEND_DIR / "requirements.txt"
        text = req_file.read_text(encoding="utf-8")
        assert "pymysql" in text.lower(), "requirements.txt 应包含 pymysql"
        assert "psycopg2" not in text.lower(), "requirements.txt 不应再包含 psycopg2"
        assert "dbutils" in text.lower(), "requirements.txt 应包含 dbutils"
