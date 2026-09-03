from __future__ import annotations

from typing import Any

from .repository import InvalidTransition


class OrchestrationRuntime:
    def __init__(self, repository: Any):
        self.repository = repository

    def start(
        self,
        *,
        panorama_gid: str,
        version_gid: str,
        frozen_context: dict[str, Any],
        actor_gid: str,
    ) -> str:
        return self.repository.create_run_with_started_event(
            panorama_gid=panorama_gid,
            version_gid=version_gid,
            frozen_context=frozen_context,
            actor_gid=actor_gid,
        )

    def advance(
        self,
        run_gid: str,
        target_status: str,
        *,
        actor_type: str,
        actor_gid: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.repository.transition_run_with_event(
            run_gid,
            target_status=target_status,
            actor_type=actor_type,
            actor_gid=actor_gid,
            payload=payload or {},
        )
