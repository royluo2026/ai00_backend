"""Request-scoped credentials for trusted downstream runtime transport only.

Values never enter Capability payloads, descriptors, evidence or public results.
The authenticated HTTP adapter supplies and clears the scope around invocation.
"""
from contextvars import ContextVar
from contextlib import contextmanager

_credential = ContextVar('authenticated_transport_credential', default='')
_user = ContextVar('authenticated_request_user', default=None)


@contextmanager
def authenticated_transport_scope(credential: str):
    token = _credential.set(credential)
    try:
        yield
    finally:
        _credential.reset(token)


def downstream_runtime_credential() -> str:
    return _credential.get()


@contextmanager
def authenticated_user_scope(user: dict):
    """Reuse the user row already authenticated by the HTTP boundary.

    This is request-local only; it never trusts a client payload and avoids
    repeating the same remote DB lookup inside Gateway authorization.
    """
    token = _user.set(dict(user))
    try:
        yield
    finally:
        _user.reset(token)


def authenticated_request_user(user_gid: str) -> dict | None:
    user = _user.get()
    return dict(user) if user and str(user.get("gid")) == str(user_gid) else None
