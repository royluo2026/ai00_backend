import re

from backend.scripts.verify_domain_db_isolation import _probe_ddl_denial


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeCursor:
    def __init__(self, *, fail_create=False, fail_drop=False):
        self.statements = []
        self.fail_create = fail_create
        self.fail_drop = fail_drop

    def execute(self, statement):
        self.statements.append(statement)
        if statement.startswith("CREATE") and self.fail_create:
            raise RuntimeError(1142, "denied")
        if statement.startswith("DROP") and self.fail_drop:
            raise RuntimeError(1142, "denied")


def test_ddl_probe_uses_unique_names_and_accepts_only_permission_denial():
    connection = FakeConnection()
    cursor = FakeCursor(fail_create=True)
    first = _probe_ddl_denial(cursor, connection, domain="factory", database="workmanship")
    second = _probe_ddl_denial(cursor, connection, domain="factory", database="workmanship")
    assert first.ok and second.ok
    assert first.target != second.target
    assert re.fullmatch(r"workmanship.ai00_permission_probe_factory_[0-9a-f]{16}", first.target)
    assert cursor.statements == [
        f"CREATE TABLE `workmanship`.`{first.target.split('.')[1]}` (id INT PRIMARY KEY)",
        f"CREATE TABLE `workmanship`.`{second.target.split('.')[1]}` (id INT PRIMARY KEY)",
    ]
    assert connection.rollbacks == 2 and connection.commits == 0


def test_successful_ddl_is_always_a_failure_even_after_cleanup():
    connection = FakeConnection()
    cursor = FakeCursor()
    result = _probe_ddl_denial(cursor, connection, domain="base", database="workmanship")
    assert result.ok is False and result.detail.endswith("probe removed")
    assert cursor.statements[0].startswith("CREATE TABLE")
    assert cursor.statements[1] == f"DROP TABLE `workmanship`.`{result.target.split('.')[1]}`"
    assert connection.commits == 2


def test_failed_cleanup_is_reported_as_unverified_not_removed():
    connection = FakeConnection()
    cursor = FakeCursor(fail_drop=True)
    result = _probe_ddl_denial(cursor, connection, domain="agent", database="workmanship")
    assert result.ok is False and "cleanup unverified" in result.detail
    assert result.target.startswith("workmanship.ai00_permission_probe_agent_")
    assert len(cursor.statements) == 2
    assert connection.commits == 1 and connection.rollbacks == 1
