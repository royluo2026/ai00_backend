"""Request-scoped credentials for trusted downstream runtime transport only.

Values never enter Capability payloads, descriptors, evidence or public results.
The authenticated HTTP adapter supplies and clears the scope around invocation.
"""
from contextvars import ContextVar
from contextlib import contextmanager

_credential = ContextVar('authenticated_transport_credential', default='')


@contextmanager
def authenticated_transport_scope(credential: str):
    token = _credential.set(credential)
    try:
        yield
    finally:
        _credential.reset(token)


def downstream_runtime_credential() -> str:
    return _credential.get()
