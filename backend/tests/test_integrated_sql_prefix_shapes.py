import pytest

from backend.db.table_prefix import configure_table_prefix, rewrite_sql, validate_runtime_profile


@pytest.fixture(autouse=True)
def reset_prefix():
    configure_table_prefix("")
    yield
    configure_table_prefix("")


def test_rewrite_uses_test_prefix_without_double_prefixing():
    configure_table_prefix("test_")
    assert rewrite_sql("SELECT * FROM workmanship_auth_users") == (
        "SELECT * FROM test_workmanship_auth_users"
    )
    assert rewrite_sql("SELECT * FROM test_workmanship_auth_users") == (
        "SELECT * FROM test_workmanship_auth_users"
    )


def test_invalid_prefix_is_rejected():
    with pytest.raises(ValueError):
        configure_table_prefix("test_; DROP TABLE x")
    with pytest.raises(ValueError, match="supported"):
        configure_table_prefix("other_")
    with pytest.raises(ValueError, match="supported"):
        validate_runtime_profile("", "other_", "http://127.0.0.1:8080")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_rewrite_only_table_identifiers(prefix):
    configure_table_prefix(prefix)
    sql = (
        "SELECT workmanship_label, doc->>'$.workmanship_note' FROM `workmanship_auth_users` u "
        "JOIN workmanship_craft_task t ON u.id=t.id "
        "WHERE u.note='workmanship_auth_users' AND u.kind=\"workmanship_craft_task\" "
        "/* JOIN workmanship_hidden */ -- FROM workmanship_other\n"
        "AND u.id IN (SELECT id FROM workmanship_auth_roles)"
    )
    expected = sql.replace("`workmanship_auth_users`", f"`{prefix}workmanship_auth_users`")
    expected = expected.replace("JOIN workmanship_craft_task", f"JOIN {prefix}workmanship_craft_task")
    expected = expected.replace("FROM workmanship_auth_roles", f"FROM {prefix}workmanship_auth_roles")
    assert rewrite_sql(sql) == expected


def test_prefix_keeps_schema_name_and_existing_physical_table():
    configure_table_prefix("pp_")
    assert rewrite_sql(
        "SELECT * FROM workmanship_schema.workmanship_probe, pp_workmanship_existing"
    ) == "SELECT * FROM workmanship_schema.pp_workmanship_probe, pp_workmanship_existing"


def test_ddl_foreign_keys_and_batch_statements_rewrite_table_positions():
    configure_table_prefix("test_")
    sql = (
        "CREATE TABLE IF NOT EXISTS workmanship_child (id INT, "
        "FOREIGN KEY (id) REFERENCES workmanship_parent(id)); "
        "CREATE INDEX idx_child ON workmanship_child (id); "
        "INSERT INTO workmanship_child (id) SELECT id FROM workmanship_parent; "
        "UPDATE workmanship_child SET id=1 WHERE id=2"
    )
    assert rewrite_sql(sql) == sql.replace("workmanship_child", "test_workmanship_child").replace(
        "workmanship_parent", "test_workmanship_parent"
    )


def test_on_duplicate_key_update_does_not_rewrite_column_name():
    configure_table_prefix("pp_")
    sql = (
        "INSERT INTO workmanship_probe (id) VALUES (1) "
        "ON DUPLICATE KEY UPDATE workmanship_probe_count=workmanship_probe_count+1"
    )
    assert rewrite_sql(sql) == sql.replace(
        "INTO workmanship_probe", "INTO pp_workmanship_probe"
    )


def test_cross_environment_physical_table_is_rejected():
    configure_table_prefix("pp_")
    with pytest.raises(ValueError, match="cross-environment"):
        rewrite_sql("SELECT * FROM test_workmanship_auth_users")


def test_ddl_multiple_tables_and_rename_targets_remain_in_one_prefix():
    configure_table_prefix("pp_")
    assert rewrite_sql("DROP TABLE IF EXISTS workmanship_a, workmanship_b") == (
        "DROP TABLE IF EXISTS pp_workmanship_a, pp_workmanship_b"
    )
    assert rewrite_sql("RENAME TABLE workmanship_a TO workmanship_b, workmanship_c TO workmanship_d") == (
        "RENAME TABLE pp_workmanship_a TO pp_workmanship_b, pp_workmanship_c TO pp_workmanship_d"
    )
    assert rewrite_sql("CREATE TABLE workmanship_child LIKE workmanship_parent") == (
        "CREATE TABLE pp_workmanship_child LIKE pp_workmanship_parent"
    )
    assert rewrite_sql("TRUNCATE workmanship_a; TRUNCATE TABLE workmanship_b") == (
        "TRUNCATE pp_workmanship_a; TRUNCATE TABLE pp_workmanship_b"
    )
    assert rewrite_sql("ALTER TABLE workmanship_a RENAME TO workmanship_b") == (
        "ALTER TABLE pp_workmanship_a RENAME TO pp_workmanship_b"
    )
    assert rewrite_sql("ALTER TABLE workmanship_a RENAME COLUMN old_name TO new_name") == (
        "ALTER TABLE pp_workmanship_a RENAME COLUMN old_name TO new_name"
    )


@pytest.mark.parametrize("sql", [
    "DROP TABLE IF EXISTS workmanship_a, test_workmanship_b",
    "RENAME TABLE workmanship_a TO test_workmanship_b",
    "CREATE TABLE workmanship_child LIKE test_workmanship_parent",
    "TRUNCATE TABLE test_workmanship_a",
    "ALTER TABLE workmanship_a RENAME TO test_workmanship_b",
])
def test_ddl_cannot_name_another_environment_in_secondary_table_position(sql):
    configure_table_prefix("pp_")
    with pytest.raises(ValueError, match="cross-environment"):
        rewrite_sql(sql)


def test_multi_table_writes_rewrite_every_table_but_not_set_columns():
    configure_table_prefix("pp_")
    assert rewrite_sql(
        "UPDATE workmanship_a AS a, workmanship_b AS b SET a.flag=1, b.flag=2"
    ) == "UPDATE pp_workmanship_a AS a, pp_workmanship_b AS b SET a.flag=1, b.flag=2"
    assert rewrite_sql(
        "DELETE FROM workmanship_a USING workmanship_a, workmanship_b WHERE workmanship_a.id=1"
    ) == (
        "DELETE FROM pp_workmanship_a USING pp_workmanship_a, pp_workmanship_b "
        "WHERE workmanship_a.id=1"
    )


@pytest.mark.parametrize("sql", [
    "UPDATE workmanship_a AS a, test_workmanship_b AS b SET a.flag=1",
    "DELETE FROM workmanship_a USING test_workmanship_a WHERE 1=1",
])
def test_multi_table_writes_refuse_other_environment(sql):
    configure_table_prefix("pp_")
    with pytest.raises(ValueError, match="cross-environment"):
        rewrite_sql(sql)


def test_view_and_table_lock_identifiers_are_prefixed():
    configure_table_prefix("pp_")
    assert rewrite_sql(
        "CREATE OR REPLACE VIEW workmanship_summary AS "
        "SELECT id FROM workmanship_source"
    ) == (
        "CREATE OR REPLACE VIEW pp_workmanship_summary AS "
        "SELECT id FROM pp_workmanship_source"
    )
    assert rewrite_sql("DROP VIEW IF EXISTS workmanship_first, workmanship_second") == (
        "DROP VIEW IF EXISTS pp_workmanship_first, pp_workmanship_second"
    )
    assert rewrite_sql("LOCK TABLES workmanship_first WRITE, workmanship_second READ") == (
        "LOCK TABLES pp_workmanship_first WRITE, pp_workmanship_second READ"
    )


def test_view_keyword_in_column_or_alias_is_not_a_table_position():
    configure_table_prefix("pp_")
    assert rewrite_sql(
        "CREATE TABLE workmanship_source (`view` VARCHAR(10), workmanship_label INT)"
    ) == (
        "CREATE TABLE pp_workmanship_source (`view` VARCHAR(10), workmanship_label INT)"
    )


def test_quoted_sql_keywords_are_identifiers_not_table_clause_triggers():
    configure_table_prefix("pp_")
    sql = "SELECT `from`, `join`, `workmanship_label` FROM workmanship_source"
    assert rewrite_sql(sql) == (
        "SELECT `from`, `join`, `workmanship_label` FROM pp_workmanship_source"
    )


def test_cte_prefixed_multi_table_writes_reject_other_environment():
    configure_table_prefix("pp_")
    cte = "WITH selected AS (SELECT id FROM workmanship_source) "
    assert rewrite_sql(cte + "UPDATE workmanship_a AS a, workmanship_b AS b SET a.flag=1") == (
        "WITH selected AS (SELECT id FROM pp_workmanship_source) "
        "UPDATE pp_workmanship_a AS a, pp_workmanship_b AS b SET a.flag=1"
    )
    for statement in (
        "UPDATE workmanship_a AS a, test_workmanship_b AS b SET a.flag=1",
        "DELETE FROM workmanship_a USING test_workmanship_a WHERE 1=1",
    ):
        with pytest.raises(ValueError, match="cross-environment"):
            rewrite_sql(cte + statement)
    assert rewrite_sql(
        "CREATE VIEW workmanship_summary AS SELECT id AS `view`, workmanship_label "
        "FROM workmanship_source"
    ) == (
        "CREATE VIEW pp_workmanship_summary AS SELECT id AS `view`, workmanship_label "
        "FROM pp_workmanship_source"
    )


@pytest.mark.parametrize("sql", [
    "/*!50000 UPDATE test_workmanship_orders SET status=1 */",
    "SELECT 1 /*!50000 UNION SELECT id FROM test_workmanship_auth_users */",
    "/*M!100100 DELETE FROM test_workmanship_auth_users */",
])
def test_executable_comments_cannot_bypass_table_prefix(sql):
    configure_table_prefix("pp_")
    with pytest.raises(ValueError, match="executable comment"):
        rewrite_sql(sql)


def test_executable_comment_text_in_a_string_is_not_rejected():
    configure_table_prefix("pp_")
    assert rewrite_sql("SELECT '/*! FROM test_workmanship_auth_users */' FROM workmanship_auth_users") == (
        "SELECT '/*! FROM test_workmanship_auth_users */' FROM pp_workmanship_auth_users"
    )


@pytest.mark.parametrize("sql", [
    "CREATE VIEW test_workmanship_summary AS SELECT 1",
    "DROP VIEW IF EXISTS workmanship_first, test_workmanship_second",
    "LOCK TABLES workmanship_first WRITE, test_workmanship_second READ",
])
def test_view_and_table_lock_refuse_other_environment(sql):
    configure_table_prefix("pp_")
    with pytest.raises(ValueError, match="cross-environment"):
        rewrite_sql(sql)


@pytest.mark.parametrize(("sql", "expected"), [
    (
        "LOAD DATA LOCAL INFILE %s INTO TABLE workmanship_auth_users (id)",
        "LOAD DATA LOCAL INFILE %s INTO TABLE pp_workmanship_auth_users (id)",
    ),
    ("HANDLER workmanship_auth_users OPEN", "HANDLER pp_workmanship_auth_users OPEN"),
    (
        "DESCRIBE workmanship_auth_users workmanship_label",
        "DESCRIBE pp_workmanship_auth_users workmanship_label",
    ),
    ("DESC workmanship_auth_users", "DESC pp_workmanship_auth_users"),
])
def test_additional_table_positions_use_active_prefix(sql, expected):
    configure_table_prefix("pp_")
    assert rewrite_sql(sql) == expected


@pytest.mark.parametrize("sql", [
    "LOAD DATA LOCAL INFILE %s INTO TABLE test_workmanship_auth_users (id)",
    "HANDLER test_workmanship_auth_users OPEN",
    "DESCRIBE test_workmanship_auth_users workmanship_label",
    "DESC test_workmanship_auth_users",
])
def test_additional_table_positions_refuse_other_environment(sql):
    configure_table_prefix("pp_")
    with pytest.raises(ValueError, match="cross-environment"):
        rewrite_sql(sql)


def test_show_create_view_rewrites_logical_name_and_refuses_other_prefix():
    configure_table_prefix("pp_")
    assert rewrite_sql("SHOW CREATE VIEW workmanship_summary") == (
        "SHOW CREATE VIEW pp_workmanship_summary"
    )
    assert rewrite_sql("SHOW CREATE VIEW `workmanship_summary`") == (
        "SHOW CREATE VIEW `pp_workmanship_summary`"
    )
    for sql in (
        "SHOW CREATE VIEW test_workmanship_summary",
        "SHOW CREATE VIEW `test_workmanship_summary`",
        "SHOW CREATE VIEW workmanship.test_workmanship_summary",
    ):
        with pytest.raises(ValueError, match="cross-environment"):
            rewrite_sql(sql)
