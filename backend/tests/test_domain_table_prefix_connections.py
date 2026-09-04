from backend.db.prefixed_cursor import wrap_connection
from backend.db.table_prefix import configure_table_prefix


class Cursor:
    def __init__(self):
        self.query = None

    def execute(self, query, args=None):
        self.query = query


class Connection:
    def __init__(self):
        self.created = []

    def cursor(self):
        cursor = Cursor()
        self.created.append(cursor)
        return cursor


def test_wrap_connection_rewrites_once():
    configure_table_prefix("test_")
    connection = Connection()
    assert wrap_connection(connection) is connection
    assert wrap_connection(connection) is connection
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM workmanship_proj_projects")
    assert cursor._inner.query == "SELECT * FROM test_workmanship_proj_projects"
