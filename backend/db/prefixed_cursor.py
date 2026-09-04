"""backend/db/prefixed_cursor.py - SQL table-prefix rewriting cursor wrapper."""
from __future__ import annotations
from backend.db.table_prefix import rewrite_sql, table_prefix_active


class PrefixedCursor:
    """Delegating cursor that rewrites SQL on execute/executemany."""

    def __init__(self, inner):
        self._inner = inner

    def execute(self, query, args=None):
        return self._inner.execute(rewrite_sql(query), args)

    def executemany(self, query, args):
        return self._inner.executemany(rewrite_sql(query), args)

    def fetchone(self):
        return self._inner.fetchone()

    def fetchall(self):
        return self._inner.fetchall()

    def fetchmany(self, size=None):
        if size is not None:
            return self._inner.fetchmany(size)
        return self._inner.fetchmany()

    @property
    def description(self):
        return self._inner.description

    @property
    def rowcount(self):
        return self._inner.rowcount

    @property
    def lastrowid(self):
        return self._inner.lastrowid

    @property
    def arraysize(self):
        return self._inner.arraysize

    @arraysize.setter
    def arraysize(self, value):
        self._inner.arraysize = value

    def close(self):
        return self._inner.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def wrap_cursor(cursor):
    if table_prefix_active() and not isinstance(cursor, PrefixedCursor):
        return PrefixedCursor(cursor)
    return cursor