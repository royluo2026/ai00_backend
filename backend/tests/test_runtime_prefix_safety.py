import pytest
from types import SimpleNamespace

from backend.db.table_prefix import configure_table_prefix, rewrite_sql, validate_runtime_profile


@pytest.fixture(autouse=True)
def reset_prefix():
    configure_table_prefix("")
    yield
    configure_table_prefix("")


@pytest.mark.parametrize("prefix", ["test_", "pp_"])
def test_only_table_positions_are_rewritten(prefix):
    configure_table_prefix(prefix)
    sql = (
        "SELECT workmanship_label, doc->>'$.workmanship_note' "
        "FROM `workmanship_auth_users` a JOIN workmanship_proj_tasks t ON a.id=t.id "
        "WHERE a.note='workmanship_auth_users' "
        "/* FROM workmanship_hidden */ -- JOIN workmanship_comment\n"
        "AND t.id IN (SELECT id FROM workmanship_proj_issues)"
    )
    expected = sql.replace("`workmanship_auth_users`", f"`{prefix}workmanship_auth_users`")
    expected = expected.replace("JOIN workmanship_proj_tasks", f"JOIN {prefix}workmanship_proj_tasks")
    expected = expected.replace("FROM workmanship_proj_issues", f"FROM {prefix}workmanship_proj_issues")
    assert rewrite_sql(sql) == expected


def test_profile_cannot_name_other_environment_table_or_ledger():
    configure_table_prefix("pp_")
    for sql in (
        "SELECT * FROM test_workmanship_auth_users",
        "UPDATE test_workmanship_proj_tasks SET status='done'",
        "SELECT * FROM test_ai00_simulation_schema_migrations",
    ):
        with pytest.raises(ValueError, match="cross-environment"):
            rewrite_sql(sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM TEST_workmanship_auth_users",
    "UPDATE `TeSt_workmanship_proj_tasks` SET status='done'",
    "SELECT * FROM PP_ai00_simulation_schema_migrations",
    "SELECT * FROM workmanship.`TEST_workmanship_auth_users`",
])
def test_case_variant_cross_environment_table_is_refused(sql):
    configure_table_prefix("pp_" if "TEST_" in sql.upper() else "test_")
    with pytest.raises(ValueError, match="cross-environment"):
        rewrite_sql(sql)


def test_case_variant_logical_table_stays_in_current_environment():
    configure_table_prefix("pp_")
    assert rewrite_sql("SELECT * FROM WORKMANSHIP_AUTH_USERS") == (
        "SELECT * FROM pp_WORKMANSHIP_AUTH_USERS"
    )
    assert rewrite_sql("SELECT * FROM AI00_SIMULATION_SCHEMA_MIGRATIONS") == (
        "SELECT * FROM pp_AI00_SIMULATION_SCHEMA_MIGRATIONS"
    )
    assert rewrite_sql("SELECT 'TEST_workmanship_auth_users' FROM WORKMANSHIP_AUTH_USERS") == (
        "SELECT 'TEST_workmanship_auth_users' FROM pp_WORKMANSHIP_AUTH_USERS"
    )
    assert rewrite_sql("SELECT * FROM PP_WORKMANSHIP_AUTH_USERS") == (
        "SELECT * FROM PP_WORKMANSHIP_AUTH_USERS"
    )
    from backend.db.table_prefix import logical_table_name

    assert logical_table_name("PP_WORKMANSHIP_AUTH_USERS") == "WORKMANSHIP_AUTH_USERS"


def test_case_variant_trigger_cannot_name_another_environment():
    configure_table_prefix("pp_")
    with pytest.raises(ValueError, match="cross-environment trigger"):
        rewrite_sql("CREATE TRIGGER TEST_base_historical_uploads_no_delete BEFORE DELETE "
                    "ON workmanship_base_historical_uploads FOR EACH ROW SIGNAL SQLSTATE '45000'")
    assert rewrite_sql("CREATE TRIGGER BASE_HISTORICAL_UPLOADS_NO_DELETE BEFORE DELETE "
                       "ON WORKMANSHIP_BASE_HISTORICAL_UPLOADS FOR EACH ROW SIGNAL SQLSTATE '45000'") == (
        "CREATE TRIGGER pp_BASE_HISTORICAL_UPLOADS_NO_DELETE BEFORE DELETE "
        "ON pp_WORKMANSHIP_BASE_HISTORICAL_UPLOADS FOR EACH ROW SIGNAL SQLSTATE '45000'"
    )


def test_double_quoted_table_name_is_refused_when_sql_mode_is_unknown():
    configure_table_prefix("pp_")
    for sql in (
        'SELECT * FROM "test_workmanship_auth_users"',
        'UPDATE "workmanship_proj_tasks" SET status=1',
        'SELECT * FROM workmanship."test_workmanship_auth_users"',
        'DROP TABLE "test_workmanship_auth_users"',
    ):
        with pytest.raises(ValueError, match="double-quoted table"):
            rewrite_sql(sql)
    assert rewrite_sql('SELECT "workmanship_auth_users" FROM workmanship_proj_tasks') == (
        'SELECT "workmanship_auth_users" FROM pp_workmanship_proj_tasks'
    )
    with pytest.raises(ValueError, match="double-quoted trigger"):
        rewrite_sql('CREATE TRIGGER "TEST_base_historical_uploads_no_delete" BEFORE DELETE '
                    'ON workmanship_base_historical_uploads FOR EACH ROW SIGNAL SQLSTATE \'45000\'')


def test_ledger_and_trigger_names_remain_prefixed_without_rewriting_literals():
    configure_table_prefix("test_")
    assert rewrite_sql("SELECT * FROM ai00_simulation_schema_migrations") == (
        "SELECT * FROM test_ai00_simulation_schema_migrations"
    )
    assert rewrite_sql("SELECT * FROM test_ai00_simulation_schema_migrations") == (
        "SELECT * FROM test_ai00_simulation_schema_migrations"
    )
    assert rewrite_sql(
        "CREATE TRIGGER base_historical_uploads_no_update BEFORE UPDATE "
        "ON workmanship_base_historical_uploads FOR EACH ROW SIGNAL SQLSTATE '45000'"
    ) == (
        "CREATE TRIGGER test_base_historical_uploads_no_update BEFORE UPDATE "
        "ON test_workmanship_base_historical_uploads FOR EACH ROW SIGNAL SQLSTATE '45000'"
    )


def test_unknown_or_unsafe_prefix_is_refused():
    for prefix in ("other_", "test_; DROP TABLE x"):
        with pytest.raises(ValueError, match="prefix"):
            configure_table_prefix(prefix)


def test_metadata_table_names_are_rewritten_without_touching_values():
    configure_table_prefix("pp_")
    assert rewrite_sql("workmanship_auth_users") == "pp_workmanship_auth_users"
    assert rewrite_sql("ai00_simulation_schema_migrations") == "pp_ai00_simulation_schema_migrations"
    assert rewrite_sql("SELECT * FROM `workmanship_auth_users` WHERE note='workmanship_auth_users'") == (
        "SELECT * FROM `pp_workmanship_auth_users` WHERE note='workmanship_auth_users'"
    )
    with pytest.raises(ValueError, match="prefix"):
        rewrite_sql("SELECT * FROM workmanship_auth_users", "other_")


def test_quoted_trigger_and_nested_table_references():
    configure_table_prefix("pp_")
    sql = (
        "CREATE TRIGGER `base_historical_uploads_no_delete` BEFORE DELETE "
        "ON `workmanship_base_historical_uploads` FOR EACH ROW "
        "SET @source=(SELECT COUNT(*) FROM workmanship_auth_users)"
    )
    expected = sql.replace("`base_historical_uploads_no_delete`", "`pp_base_historical_uploads_no_delete`")
    expected = expected.replace("`workmanship_base_historical_uploads`", "`pp_workmanship_base_historical_uploads`")
    expected = expected.replace("FROM workmanship_auth_users", "FROM pp_workmanship_auth_users")
    assert rewrite_sql(sql) == expected


def test_cross_environment_quoted_table_and_executable_comment_are_refused():
    configure_table_prefix("test_")
    with pytest.raises(ValueError, match="cross-environment"):
        rewrite_sql("SELECT * FROM `pp_workmanship_auth_users`")
    with pytest.raises(ValueError, match="executable comment"):
        rewrite_sql("SELECT 1 /*! FROM workmanship_auth_users */")


def test_schema_qualified_table_cannot_name_the_other_environment():
    configure_table_prefix("pp_")
    for sql in (
        "SELECT * FROM workmanship.test_workmanship_auth_users",
        "SELECT * FROM `workmanship`.`test_workmanship_auth_users`",
        "UPDATE workmanship.test_workmanship_auth_users SET status='x'",
    ):
        with pytest.raises(ValueError, match="cross-environment"):
            rewrite_sql(sql)


@pytest.mark.parametrize(("profile", "prefix", "public_url"), [
    ("production", "test_", "https://workmanship-backend.chehejia.com"),
    ("production", "pp_", "http://127.0.0.1:8080"),
    ("test", "pp_", "http://127.0.0.1:8080"),
    ("test", "test_", "https://workmanship-backend.chehejia.com"),
    ("", "pp_", ""),
    ("", "test_", "https://workmanship-backend.chehejia.com"),
    ("proudction", "pp_", "https://workmanship-backend.chehejia.com"),
    ("test", "test_", ""),
    ("test", "test_", "not-a-url"),
    ("test", "test_", "http://127.0.0.1:8080/other"),
])
def test_runtime_profile_refuses_mismatched_prefix_and_backend(profile, prefix, public_url):
    with pytest.raises(ValueError, match="profile|prefix|URL"):
        validate_runtime_profile(profile, prefix, public_url)


def test_runtime_profile_accepts_both_named_environments_and_legacy_local_test():
    validate_runtime_profile("production", "pp_", "https://workmanship-backend.chehejia.com/")
    validate_runtime_profile("test", "test_", "http://127.0.0.1:8080")
    validate_runtime_profile("test", "test_", "http://pc-pc2l7vve:8080")
    validate_runtime_profile("", "test_", "http://127.0.0.1:8080")


@pytest.mark.parametrize(("profile", "prefix", "url", "file", "message"), [
    ("production", "test_", "https://workmanship-backend.chehejia.com", "prod.env", "production profile"),
    ("test", "pp_", "http://127.0.0.1:8080", "", "production profile"),
    ("production", "pp_", "https://workmanship-backend.chehejia.com", "", "ENV_FILE"),
    ("", "test_", "http://127.0.0.1:8080", "test.env", "managed_deployment_requires_explicit_profile"),
])
def test_base_pool_refuses_wrong_profile_before_connect(monkeypatch, profile, prefix, url, file, message):
    from backend.db import connection

    monkeypatch.delenv("AI00_PYTEST_OFFLINE", raising=False)
    monkeypatch.setenv("AI00_DEPLOY_PROFILE", profile)
    monkeypatch.setenv("TABLE_PREFIX", prefix)
    monkeypatch.setenv("ENV_FILE", file)
    monkeypatch.setattr(connection, "get_settings", lambda: SimpleNamespace(public_url=url))
    monkeypatch.setattr(connection, "PooledDB", lambda **kwargs: pytest.fail("database connection attempted"))
    with pytest.raises((ValueError, RuntimeError), match=message):
        connection.init_pool()
