"""Compatibility export for the Agent-owned session repository."""

from ..data.session_repository import SessionRepository

SessionStore = SessionRepository
_store = SessionRepository()
