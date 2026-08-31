"""Official Agent Provider entry point."""
from __future__ import annotations

import inspect

from ..application import AgentApplication
from ..infrastructure import AgentCapabilityRepository
from ..data.audit_repository import AuditRepository
from ..data.session_repository import SessionRepository
from .descriptors import specs
from .provider import descriptor_for
from .interaction_chat_change import register_interaction_chat_change_capability


application = AgentApplication(AgentCapabilityRepository(), AuditRepository(), SessionRepository())
_CANVAS_CAPABILITIES = {
    "agent.workflow.node.test.execute", "agent.canvas.options.resolve",
    "agent.canvas.execution.start", "agent.canvas.execution.resume",
}


def _validate_canvas_runtime(runtime) -> None:
    methods = ("test_node", "resolve_options", "start", "resume")
    if any(not inspect.iscoroutinefunction(getattr(runtime, name, None)) for name in methods):
        raise RuntimeError("Agent canvas runtime adapter must implement the finite async runtime port")


def register_capabilities(registry, *, canvas_runtime=None) -> None:
    if canvas_runtime is not None:
        _validate_canvas_runtime(canvas_runtime)
    provider = application if canvas_runtime is None else AgentApplication(
        AgentCapabilityRepository(), AuditRepository(), SessionRepository(), canvas_runtime
    )
    for spec in specs():
        capability_id = spec.id
        if capability_id in _CANVAS_CAPABILITIES:
            async def handler(payload, context, *, _capability_id=capability_id):
                return {"data": await provider.invoke(_capability_id, payload, context)}
        else:
            def handler(payload, context, *, _capability_id=capability_id):
                return {"data": provider.invoke(_capability_id, payload, context)}
        governed = spec.model_copy(update={"plugin_callable": True})
        registry.register(governed, handler, descriptor=descriptor_for(governed))
    register_interaction_chat_change_capability(registry)

__all__ = ["register_capabilities"]
