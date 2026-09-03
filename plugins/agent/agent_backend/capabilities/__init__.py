"""Official Agent Provider entry point."""
from __future__ import annotations

import inspect

from ..application import AgentApplication
from ..application.canvas_runtime import ProductionAgentCanvasRuntime
from ..application.service import (
    CanvasExecutionCoordinator, CanvasExecutionDispatcher, CanvasExecutionWorker,
)
from ..infrastructure import AgentCapabilityRepository
from ..data.audit_repository import AuditRepository
from ..data.session_repository import SessionRepository
from .descriptors import specs
from .provider import descriptor_for
from .interaction_chat_change import register_interaction_chat_change_capability
from .catalog_tool_confirmation import register_catalog_tool_confirmation_capability


_DEFAULT_RUNTIME = object()
_CANVAS_CAPABILITIES = {
    "agent.workflow.node.test.execute", "agent.canvas.options.resolve",
    "agent.canvas.execution.start", "agent.canvas.execution.resume",
}


def _validate_canvas_runtime(runtime) -> None:
    methods = ("test_node", "resolve_options", "start", "resume")
    if any(not inspect.iscoroutinefunction(getattr(runtime, name, None)) for name in methods):
        raise RuntimeError("Agent canvas runtime adapter must implement the finite async runtime port")


def register_capabilities(registry, *, canvas_runtime=_DEFAULT_RUNTIME) -> None:
    repository = AgentCapabilityRepository()
    production_composition = canvas_runtime is _DEFAULT_RUNTIME
    runtime = (
        ProductionAgentCanvasRuntime(repository_factory=type(repository))
        if production_composition else canvas_runtime
    )
    if runtime is not None:
        _validate_canvas_runtime(runtime)
    execution = CanvasExecutionCoordinator(repository) if runtime is not None and production_composition else None
    if execution is not None and hasattr(registry, "register_lifecycle"):
        state = {"last_health": {
            "status": "stopped", "consecutive_errors": 0, "last_error_code": None,
            "retry_delay_seconds": 0.0, "last_poll_at": None,
            "last_success_at": None, "next_retry_at": None,
        }}

        def health():
            worker = state.get("worker")
            return worker.health if worker is not None else dict(state["last_health"])

        def supervise(signal):
            registry.publish_lifecycle_signal("agent.canvas-execution-worker", signal)

        async def start():
            worker = CanvasExecutionWorker(
                CanvasExecutionDispatcher(repository, runtime), supervision_signal=supervise,
            )
            state["worker"] = worker
            await worker.start()

        async def stop():
            worker = state.pop("worker", None)
            if worker is not None:
                await worker.stop()
                state["last_health"] = dict(worker.health)

        registry.register_lifecycle(
            "agent.canvas-execution-worker", start, stop, health=health,
        )
    provider = AgentApplication(
        repository, AuditRepository(), SessionRepository(), runtime,
        canvas_execution=execution,
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
    register_catalog_tool_confirmation_capability(registry)

__all__ = ["register_capabilities"]
