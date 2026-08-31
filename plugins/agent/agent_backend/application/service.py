from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import secrets
import uuid
from backend.capability_v2.provider_contracts import CapabilityBusinessError
from dataclasses import asdict, replace
from typing import Any, Callable, Mapping

from .canvas_runtime import (
    CanvasLayout, CanvasOption, CanvasOptionsRequest, CanvasResumeRequest, CanvasStartRequest,
    CollectField, ContextSummaryItem, NodeResult, NodeTestRequest, OutputValue, RunPrincipal,
    RuntimeDispatch, VisibilityRule,
)


_CANVAS_REQUESTS = {
    "agent.workflow.node.test.execute": (NodeTestRequest, "test_node"),
    "agent.canvas.options.resolve": (CanvasOptionsRequest, "resolve_options"),
    "agent.canvas.execution.start": (CanvasStartRequest, "start"),
    "agent.canvas.execution.resume": (CanvasResumeRequest, "resume"),
}
_CANVAS_QUERIES = {"agent.workflow.node.test.execute", "agent.canvas.options.resolve"}
_CANVAS_COMMANDS = {"agent.canvas.execution.start", "agent.canvas.execution.resume"}
_log = logging.getLogger(__name__)


def _json_projection(value):
    if isinstance(value, dict):
        return {key: _json_projection(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_projection(item) for item in value]
    return value


def _runtime_dispatch(value: Mapping[str, Any]) -> RuntimeDispatch:
    def output(item):
        raw = item.get("value")
        return OutputValue(str(item.get("name") or ""), tuple(raw) if isinstance(raw, list) else raw)

    def option(item):
        return CanvasOption(str(item.get("value") or ""), str(item.get("label") or ""))

    def rule(item):
        return VisibilityRule(str(item.get("field_key") or ""), item.get("value"))

    def field(item):
        default = item.get("default")
        return CollectField(
            key=str(item.get("key") or ""), label=str(item.get("label") or ""),
            type=item.get("type"), options=tuple(option(child) for child in item.get("options") or ()),
            default=tuple(default) if isinstance(default, list) else default,
            depends_on=item.get("depends_on"),
            show_when=tuple(rule(child) for child in item.get("show_when") or ()),
        )

    layout = value.get("canvas_layout")
    return RuntimeDispatch(
        status=value.get("status"), run_token=str(value.get("run_token") or ""),
        revision=value.get("revision"), pause_token=value.get("pause_token"),
        halted_node_id=value.get("halted_node_id"), halted_label=value.get("halted_label"),
        halt_reason=value.get("halt_reason"), skill_title=value.get("skill_title"),
        summary=str(value.get("summary") or ""),
        node_results=tuple(NodeResult(
            node_id=str(item.get("node_id") or ""), status=item.get("status"),
            summary=str(item.get("summary") or ""),
            output_values=tuple(output(child) for child in item.get("output_values") or ()),
        ) for item in value.get("node_results") or ()),
        context_summary=tuple(ContextSummaryItem(
            str(item.get("node_id") or ""), str(item.get("text") or ""),
        ) for item in value.get("context_summary") or ()),
        collect_fields=tuple(field(item) for item in value.get("collect_fields") or ()),
        canvas_layout=(CanvasLayout(
            column_labels=tuple(layout.get("column_labels") or ()),
            column_width=layout.get("column_width", 320),
            lane_height=layout.get("lane_height", 60),
            hide_lane_labels=layout.get("hide_lane_labels", False),
        ) if isinstance(layout, Mapping) else None),
    )


def _request_hash(capability_id: str, request: CanvasStartRequest | CanvasResumeRequest) -> str:
    raw = json.dumps(
        {"capability_id": capability_id, "payload": asdict(request)}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class CanvasExecutionCoordinator:
    """Create/replay durable commands; the Agent repository owns each transaction."""

    def __init__(self, repository, *, token_factory: Callable[[str], str] | None = None):
        self._repository = repository
        self._token = token_factory or (lambda kind: f"{kind}_{secrets.token_urlsafe(32)}")

    @staticmethod
    def _key(value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 255:
            raise CapabilityBusinessError("invalid_input", "Agent canvas idempotency key is required")
        return value

    @staticmethod
    def _result(row: Mapping[str, Any]) -> RuntimeDispatch:
        value = row.get("result")
        if not isinstance(value, Mapping):
            raise CapabilityBusinessError(
                "provider_unavailable", "Agent canvas durable result is unavailable", retryable=True,
            )
        return _runtime_dispatch(value)

    def start(
        self, request: CanvasStartRequest, principal: RunPrincipal, idempotency_key: str,
    ) -> RuntimeDispatch:
        key = self._key(idempotency_key)
        run_token = self._token("run")
        invocation_id = self._token("invocation")
        result = RuntimeDispatch("accepted", run_token, 1)
        row, _replayed = self._repository.create_canvas_start({
            "run_id": f"canvas_{uuid.uuid4().hex}", "run_token": run_token,
            "invocation_id": invocation_id, "actor_gid": principal.actor_gid,
            "team_gid": principal.team_gid, "capability_id": "agent.canvas.execution.start",
            "idempotency_key": key,
            "payload_hash": _request_hash("agent.canvas.execution.start", request),
            "target_state": "start", "request": asdict(request), "result": asdict(result),
        })
        return self._result(row)

    def resume(
        self, request: CanvasResumeRequest, principal: RunPrincipal, idempotency_key: str,
    ) -> RuntimeDispatch:
        key = self._key(idempotency_key)
        invocation_id = self._token("invocation")
        result = RuntimeDispatch("accepted", request.run_token, request.expected_revision + 1)
        row, _replayed = self._repository.create_canvas_resume({
            "invocation_id": invocation_id, "actor_gid": principal.actor_gid,
            "team_gid": principal.team_gid, "capability_id": "agent.canvas.execution.resume",
            "idempotency_key": key,
            "payload_hash": _request_hash("agent.canvas.execution.resume", request),
            "target_state": "resume", "request": asdict(request), "result": asdict(result),
        })
        return self._result(row)


class CanvasExecutionDispatcher:
    """Claim one invocation before dispatch and never repeat an uncertain side effect."""

    def __init__(self, repository, runtime, *, token_factory: Callable[[str], str] | None = None):
        self._repository = repository
        self._runtime = runtime
        self._token = token_factory or (lambda kind: f"{kind}_{secrets.token_urlsafe(32)}")

    @staticmethod
    def _request(claim):
        raw = claim["request"]
        return (
            CanvasStartRequest.from_payload(raw)
            if claim["target_state"] == "start"
            else CanvasResumeRequest.from_payload(raw)
        )

    @staticmethod
    def _principal(claim):
        value = claim.get("principal") or claim
        return RunPrincipal(str(value["actor_gid"]), str(value["team_gid"]))

    @staticmethod
    def _unknown(claim) -> RuntimeDispatch:
        return RuntimeDispatch(
            "outcome_unknown", str(claim["run_token"]), int(claim["revision"]),
            summary="The runtime outcome requires reconciliation.",
        )

    async def _execute(self, claim, request, principal):
        method = getattr(self._runtime, "execute_canvas_command", None)
        if method is not None:
            return await method(
                claim["target_state"], request, principal, run_token=claim["run_token"],
                invocation_id=claim["invocation_id"],
            )
        return await getattr(self._runtime, claim["target_state"])(request, principal)

    async def _reconcile(self, claim, request, principal):
        method = getattr(self._runtime, "reconcile_canvas_command", None)
        if method is None:
            return self._unknown(claim)
        return await method(
            claim["target_state"], request, principal, run_token=claim["run_token"],
            invocation_id=claim["invocation_id"],
        )

    async def dispatch_next(self, *, worker_id: str) -> RuntimeDispatch | None:
        claim = self._repository.claim_next_canvas_invocation(worker_id)
        if claim is None:
            return None
        request, principal = self._request(claim), self._principal(claim)
        try:
            if claim.get("reconcile"):
                result = await self._reconcile(claim, request, principal)
            else:
                self._repository.mark_canvas_invocation_dispatched(claim)
                result = await self._execute(claim, request, principal)
            result = replace(
                result, run_token=str(claim["run_token"]), revision=int(claim["revision"]),
                pause_token=(self._token("pause") if result.status == "paused" else None),
            )
            if result.status == "outcome_unknown":
                self._repository.record_canvas_uncertainty(claim, result, "outcome_unknown")
            else:
                self._repository.complete_canvas_invocation(claim, result)
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result = self._unknown(claim)
            self._repository.record_canvas_uncertainty(claim, result, type(exc).__name__)
            return result


class CanvasExecutionWorker:
    """Small poller exposing health through CapabilityRegistry's existing lifecycle API."""

    def __init__(
        self, dispatcher: CanvasExecutionDispatcher, *, worker_id: str = "agent-canvas",
        idle_seconds: float = 0.25,
        supervision_signal: Callable[[Mapping[str, Any]], None] | None = None,
    ):
        self._dispatcher = dispatcher
        self._worker_id = worker_id
        self._idle_seconds = max(0.001, float(idle_seconds))
        self._supervision_signal = supervision_signal
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._health = {
            "status": "stopped", "consecutive_errors": 0, "last_error_code": None,
            "retry_delay_seconds": 0.0, "last_poll_at": None,
            "last_success_at": None, "next_retry_at": None,
        }

    @property
    def health(self) -> Mapping[str, Any]:
        return dict(self._health)

    async def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._health.update(status="starting", last_error_code=None, next_retry_at=None)
            self._task = asyncio.create_task(self._run(), name=self._worker_id)
            self._task.add_done_callback(self._observe_completion)

    async def stop(self) -> None:
        self._stopping.set()
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        if self._health["status"] != "fatal":
            self._health.update(status="stopped", retry_delay_seconds=0.0, next_retry_at=None)

    def _observe_completion(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None and self._supervision_signal is not None:
            self._supervision_signal({
                "event": "lifecycle_worker_failed", "status": "fatal",
                "error_code": type(exc).__name__, "observed_at": datetime.now(UTC).isoformat(),
            })

    @staticmethod
    def _transient(exc: Exception) -> bool:
        return isinstance(exc, (ConnectionError, TimeoutError)) or (
            type(exc).__module__.startswith("pymysql.")
            and type(exc).__name__ in {"InterfaceError", "OperationalError"}
        )

    async def _run(self) -> None:
        while not self._stopping.is_set():
            polled = datetime.now(UTC)
            try:
                consumed = await self._dispatcher.dispatch_next(worker_id=self._worker_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._transient(exc):
                    self._health.update(
                        status="fatal", last_error_code=type(exc).__name__,
                        retry_delay_seconds=0.0, last_poll_at=polled.isoformat(), next_retry_at=None,
                    )
                    _log.error(
                        "agent_canvas_worker_fatal",
                        extra={"event_type": "lifecycle_worker_failed", "worker_status": "fatal",
                               "error_code": type(exc).__name__},
                    )
                    raise
                failures = min(int(self._health["consecutive_errors"]) + 1, 10)
                delay = min(5.0, self._idle_seconds * (2 ** (failures - 1)))
                self._health.update(
                    status="degraded", consecutive_errors=failures,
                    last_error_code=type(exc).__name__, retry_delay_seconds=delay,
                    last_poll_at=polled.isoformat(),
                    next_retry_at=(polled + timedelta(seconds=delay)).isoformat(),
                )
                await asyncio.sleep(delay)
                continue
            self._health.update(
                status="healthy", consecutive_errors=0, last_error_code=None,
                retry_delay_seconds=0.0, last_poll_at=polled.isoformat(),
                last_success_at=datetime.now(UTC).isoformat(), next_retry_at=None,
            )
            await asyncio.sleep(0 if consumed is not None else self._idle_seconds)


class AgentApplication:
    def __init__(
        self, repository, audit_repository=None, session_repository=None, canvas_runtime=None,
        canvas_query_timeout=3.0, canvas_execution=None,
    ):
        if isinstance(canvas_query_timeout, bool) or not isinstance(canvas_query_timeout, (int, float)) or canvas_query_timeout <= 0:
            raise ValueError("canvas_query_timeout must be positive")
        self.repository = repository
        self.audit_repository = audit_repository
        self.session_repository = session_repository
        self.canvas_runtime = canvas_runtime
        self.canvas_query_timeout = float(canvas_query_timeout)
        self.canvas_execution = canvas_execution

    def invoke(self, capability_id: str, payload: dict, context):
        actor = getattr(context, "user_gid", None) or getattr(context, "actor_gid", None)
        tenant = getattr(context, "team_gid", None) or getattr(context, "tenant_gid", None)
        if not actor or not tenant:
            raise CapabilityBusinessError("permission_denied", "Agent access requires actor and tenant context")
        if capability_id in _CANVAS_REQUESTS:
            if self.canvas_runtime is None:
                raise CapabilityBusinessError(
                    "provider_unavailable", "Agent canvas runtime adapter is not configured", retryable=True
                )
            request_type, method_name = _CANVAS_REQUESTS[capability_id]
            try:
                request = request_type.from_payload(payload)
            except (TypeError, ValueError) as exc:
                raise CapabilityBusinessError("invalid_input", str(exc)) from exc
            principal = RunPrincipal(actor_gid=str(actor), team_gid=str(tenant))

            async def invoke_canvas():
                if capability_id in _CANVAS_COMMANDS and self.canvas_execution is not None:
                    idempotency_key = str(getattr(context, "idempotency_key", "") or "")
                    result = getattr(self.canvas_execution, method_name)(request, principal, idempotency_key)
                    return _json_projection(asdict(result))
                operation = getattr(self.canvas_runtime, method_name)(request, principal)
                try:
                    result = await (
                        asyncio.wait_for(operation, timeout=self.canvas_query_timeout)
                        if capability_id in _CANVAS_QUERIES else operation
                    )
                except TimeoutError as exc:
                    raise CapabilityBusinessError(
                        "runtime_timeout", "Agent canvas runtime timed out", retryable=True,
                    ) from exc
                return _json_projection(asdict(result))

            return invoke_canvas()
        family = capability_id.split(".")[1]
        data = {
            **payload,
            "owner_gid": str(actor),
            "tenant_gid": str(tenant),
            "resource_type": family,
            "active_roles": tuple(getattr(context, "active_roles", ()) or ()),
        }
        if family == "audit":
            if self.audit_repository is None:
                raise CapabilityBusinessError("provider_unavailable", "Agent audit provider is not configured")
            if capability_id == "agent.audit.record":
                event = {**payload, "user_gid": str(actor)}
                return {"gid": self.audit_repository.record(event)}
            if "super_admin" not in data["active_roles"]:
                raise CapabilityBusinessError("permission_denied", "Agent audit reads require super_admin")
            limit = payload.get("limit", 50)
            offset = payload.get("offset", 0)
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
                raise ValueError("limit must be between 1 and 500")
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                raise ValueError("offset must be >= 0")
            total, rows = self.audit_repository.list(
                session_gid=str(payload.get("session_gid") or ""),
                user_gid=str(payload.get("user_gid") or ""),
                tool_name=str(payload.get("tool_name") or ""),
                is_write=str(payload.get("is_write") or ""),
                limit=limit,
                offset=offset,
            )
            logs = []
            for row in rows:
                item = dict(row)
                created_at = item.get("created_at")
                if hasattr(created_at, "isoformat"):
                    item["created_at"] = created_at.isoformat()
                logs.append(item)
            return {"logs": logs, "total": int(total), "limit": limit, "offset": offset}
        if family == "session":
            if self.session_repository is None:
                raise CapabilityBusinessError("provider_unavailable", "Agent session provider is not configured")
            operation = str(payload.get("operation") or ("list" if capability_id.endswith(".read") else ""))
            if capability_id == "agent.session.read":
                if operation == "list":
                    return {"sessions": self.session_repository.list_sessions(str(actor))}
                if operation == "get":
                    session_gid = str(payload.get("session_gid") or "").strip()
                    if not session_gid:
                        raise ValueError("session_gid is required")
                    return {"turns": self.session_repository.get_session(session_gid, str(actor))}
            elif capability_id == "agent.session.change.apply":
                if operation == "create":
                    return {"session_gid": self.session_repository.create_session(str(actor))}
                if operation == "delete":
                    session_gid = str(payload.get("session_gid") or "").strip()
                    if not session_gid:
                        raise ValueError("session_gid is required")
                    if not self.session_repository.delete_owned_session(session_gid, str(actor)):
                        raise CapabilityBusinessError(
                            "resource_not_found", "Agent session was not found",
                            details={"session_gid": session_gid},
                        )
                    return {"success": True}
            raise ValueError(f"unsupported session operation: {operation}")
        if family == "flow":
            return self.repository.flow_read(data) if capability_id.endswith(".read") else self.repository.flow_apply(data)
        if family == "skill":
            return self.repository.skill_read(data) if capability_id.endswith(".read") else self.repository.skill_apply(data)
        if capability_id == "agent.script.generate":
            return self.repository.generate_script(data)
        if capability_id == "agent.runtime.config.read":
            return self.repository.runtime_config(data)
        if capability_id == "agent.tool_catalog.read":
            operation = str(payload.get("operation") or "list")
            if operation != "list":
                raise ValueError(f"unsupported tool catalog operation: {operation}")
            from ..ai_assistant.tool_registry import _READ_TOOLS, _WRITE_TOOLS_CONFIRM, _WRITE_TOOLS_NO_CONFIRM, _SYSTEM_TOOLS

            def format_tools(tools, category, need_confirm):
                return [{"name": item["name"], "description": item["description"], "category": category, "need_confirm": need_confirm, "params": list(item["input_schema"].get("properties", {}).keys())} for item in tools]

            return {
                "read": format_tools(_READ_TOOLS, "read", False),
                "write_confirm": format_tools(_WRITE_TOOLS_CONFIRM, "write_confirm", True),
                "write_no_confirm": format_tools(_WRITE_TOOLS_NO_CONFIRM, "write_no_confirm", False),
                "system": format_tools(_SYSTEM_TOOLS, "system", False),
                "total": len(_READ_TOOLS) + len(_WRITE_TOOLS_CONFIRM) + len(_WRITE_TOOLS_NO_CONFIRM) + len(_SYSTEM_TOOLS),
            }
        if capability_id == "agent.interaction.cancel":
            session_gid = str(payload.get("session_gid") or "").strip()
            if not session_gid:
                raise ValueError("session_gid is required")
            if self.session_repository is None:
                raise CapabilityBusinessError("provider_unavailable", "Agent session provider is not configured")
            self.session_repository.get_session(session_gid, str(actor))
            from .interaction_state import request_abort
            request_abort(session_gid)
            return {"ok": True, "session_gid": session_gid}
        if capability_id.endswith(".read"):
            return self.repository.read(data)
        if capability_id == "agent.interaction.request":
            return self.repository.request_interaction(data)
        return self.repository.apply(data)
