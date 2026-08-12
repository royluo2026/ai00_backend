from __future__ import annotations

from ..domain import ReplayGuard


class LocalRuntimeApplication:
    """Accepts a verified signed operation exactly once on the runtime side."""

    def __init__(self, replay_guard: ReplayGuard | None = None):
        self.replay_guard = replay_guard or ReplayGuard()

    def accept_verified_operation(self, envelope) -> None:
        self.replay_guard.accept(envelope.operation_id, expires_at=envelope.expires_at)
