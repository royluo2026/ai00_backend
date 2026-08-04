"""Agent-owned persistence boundary. No Base database imports are allowed here."""

from .session_repository import SessionRepository

__all__ = ["SessionRepository"]
