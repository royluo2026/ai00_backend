"""backend/db/prefixed_cursor.py - SQL table-prefix rewriting cursor wrapper."""
from __future__ import annotations
from backend.db.table_prefix import current_table_prefix, rewrite_sql


class PrefixedCursor:
    """Delegating cursor that rewrites SQL on execute/executemany."""

    def __init__(self, inner, prefix=None, owner_alive=None):
        self._inner = inner
        self._prefix = current_table_prefix() if prefix is None else prefix
        self._owner_alive = owner_alive or (lambda: True)
        self._closed = False

    def _ensure_open(self):
        if self._closed or not self._owner_alive():
            raise RuntimeError("prefixed cursor is closed")

    def execute(self, query, args=None):
        self._ensure_open()
        rendered = rewrite_sql(query, self._prefix)
        if args is None:
            return self._inner.execute(rendered)
        return self._inner.execute(rendered, args)

    def executemany(self, query, args):
        self._ensure_open()
        return self._inner.executemany(rewrite_sql(query, self._prefix), args)

    def fetchone(self):
        self._ensure_open()
        return self._inner.fetchone()

    def fetchall(self):
        self._ensure_open()
        return self._inner.fetchall()

    def fetchmany(self, size=None):
        self._ensure_open()
        if size is not None:
            return self._inner.fetchmany(size)
        return self._inner.fetchmany()

    @property
    def description(self):
        self._ensure_open()
        return self._inner.description

    @property
    def rowcount(self):
        self._ensure_open()
        return self._inner.rowcount

    @property
    def lastrowid(self):
        self._ensure_open()
        return self._inner.lastrowid

    @property
    def arraysize(self):
        self._ensure_open()
        return self._inner.arraysize

    @arraysize.setter
    def arraysize(self, value):
        self._ensure_open()
        self._inner.arraysize = value

    def close(self):
        if self._closed:
            return None
        self._closed = True
        return self._inner.close()

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, *exc):
        try:
            exit_method = getattr(self._inner, "__exit__", None)
            if exit_method is not None:
                return exit_method(*exc)
            return self._inner.close()
        finally:
            self._closed = True

class PrefixedConnection:
    def __init__(self, inner, prefix):
        self._inner = inner
        self._prefix = prefix
        self._closed = False

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("prefixed connection is closed")

    def cursor(self, *args, **kwargs):
        self._ensure_open()
        return PrefixedCursor(self._inner.cursor(*args, **kwargs), self._prefix,
                              lambda: not self._closed)

    def begin(self):
        self._ensure_open()
        return self._inner.begin()

    def commit(self):
        self._ensure_open()
        return self._inner.commit()

    def rollback(self):
        self._ensure_open()
        return self._inner.rollback()

    def close(self):
        if self._closed:
            return None
        self._closed = True
        return self._inner.close()

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, *exc):
        try:
            exit_method = getattr(self._inner, "__exit__", None)
            if exit_method is not None:
                return exit_method(*exc)
            if exc[0] is None:
                self._inner.commit()
            else:
                self._inner.rollback()
            return self._inner.close()
        finally:
            self._closed = True

def wrap_cursor(cursor):
    if isinstance(cursor, PrefixedCursor) or not current_table_prefix():
        return cursor
    return PrefixedCursor(cursor)


def wrap_connection(connection):
    if isinstance(connection, PrefixedConnection):
        connection._ensure_open()
        if connection._prefix != current_table_prefix():
            raise ValueError("connection prefix differs from active prefix")
        return connection
    if not hasattr(connection, "cursor"):
        return connection
    return PrefixedConnection(connection, current_table_prefix())
