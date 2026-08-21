"""Official Agent Provider entry point."""
from __future__ import annotations

from ..application import AgentApplication
from ..infrastructure import AgentCapabilityRepository
from ..data.audit_repository import AuditRepository
from ..data.session_repository import SessionRepository
from .descriptors import specs
from .provider import descriptor_for
from .interaction_chat_change import register_interaction_chat_change_capability


application = AgentApplication(AgentCapabilityRepository(), AuditRepository(), SessionRepository())


def register_capabilities(registry) -> None:
    for spec in specs():
        capability_id = spec.id
        def handler(payload, context, *, _capability_id=capability_id):
            return {"data": application.invoke(_capability_id, payload, context)}
        governed = spec.model_copy(update={"plugin_callable": True})
        registry.register(governed, handler, descriptor=descriptor_for(governed))
    register_interaction_chat_change_capability(registry)

__all__ = ["register_capabilities"]
