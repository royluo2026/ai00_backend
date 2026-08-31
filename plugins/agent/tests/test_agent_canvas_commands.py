from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import importlib
import json
import threading
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.agent.agent_backend.application.canvas_runtime import (
    CanvasResumeRequest,
    CanvasStartRequest,
    InputValue,
    NodeResult,
    OutputValue,
    RunPrincipal,
    RuntimeDispatch,
)
from plugins.agent.agent_backend.application.service import (
    CanvasExecutionCoordinator,
    CanvasExecutionDispatcher,
    CanvasExecutionWorker,
)


ROOT = Path(__file__).resolve().parents[3]
PRINCIPAL = RunPrincipal("actor-1", "team-1")
runtime_module = importlib.import_module("plugins.agent.agent_backend.application.canvas_runtime")
CanvasCommandEngine = getattr(runtime_module, "_CanvasCommandEngine", None)
ProductionAgentCanvasRuntime = runtime_module.ProductionAgentCanvasRuntime


def _unknown(run_token: str, revision: int) -> RuntimeDispatch:
    return RuntimeDispatch(
        status="outcome_unknown", run_token=run_token, revision=revision,
        summary="The runtime outcome requires reconciliation.",
    )


class MemoryCanvasExecutionRepository:
    """Transaction-shaped double; the SQL owner is checked separately below."""

    def __init__(self):
        self.lock = threading.Lock()
        self.runs = {}
        self.invocations = {}
        self.scopes = {}
        self.fail_claim = None

    @staticmethod
    def _scope(data):
        return (
            data["actor_gid"], data["team_gid"], data["capability_id"],
            data["idempotency_key"],
        )

    def create_canvas_start(self, data):
        with self.lock:
            scope = self._scope(data)
            existing_id = self.scopes.get(scope)
            if existing_id:
                existing = self.invocations[existing_id]
                if existing["payload_hash"] != data["payload_hash"]:
                    raise CapabilityBusinessError(
                        "idempotency_conflict", "Agent canvas idempotency key conflicts with an earlier request",
                    )
                return dict(existing), True
            run = {
                "run_id": data["run_id"], "run_token": data["run_token"],
                "actor_gid": data["actor_gid"], "team_gid": data["team_gid"],
                "skill_gid": data["request"]["skill_gid"],
                "skill_revision": data["request"]["expected_revision"],
                "status": "accepted", "revision": 1, "pause_token": None,
                "checkpoint": None, "result": dict(data["result"]),
            }
            invocation = {
                **data, "status": "accepted", "revision": 1, "attempt_count": 0,
                "lease_owner": None, "lease_token": None, "lease_expires_at": None,
                "dispatched_at": None, "next_attempt_at": None,
            }
            self.runs[data["run_id"]] = run
            self.invocations[data["invocation_id"]] = invocation
            self.scopes[scope] = data["invocation_id"]
            return dict(invocation), False

    def create_canvas_resume(self, data):
        with self.lock:
            scope = self._scope(data)
            existing_id = self.scopes.get(scope)
            if existing_id:
                existing = self.invocations[existing_id]
                if existing["payload_hash"] != data["payload_hash"]:
                    raise CapabilityBusinessError(
                        "idempotency_conflict", "Agent canvas idempotency key conflicts with an earlier request",
                    )
                return dict(existing), True
            request = data["request"]
            run = next((item for item in self.runs.values() if (
                item["run_token"] == request["run_token"]
                and item["actor_gid"] == data["actor_gid"]
                and item["team_gid"] == data["team_gid"]
            )), None)
            if (
                run is None or run["status"] != "paused"
                or run["pause_token"] != request["pause_token"]
                or run["revision"] != request["expected_revision"]
            ):
                raise CapabilityBusinessError(
                    "resource_not_found", "Agent canvas execution was not found",
                )
            run.update({
                "status": "accepted", "revision": run["revision"] + 1,
                "pause_token": None, "result": dict(data["result"]),
            })
            invocation = {
                **data, "run_id": run["run_id"], "run_token": run["run_token"],
                "status": "accepted", "revision": run["revision"], "attempt_count": 0,
                "lease_owner": None, "lease_token": None, "lease_expires_at": None,
                "dispatched_at": None, "next_attempt_at": None,
            }
            self.invocations[data["invocation_id"]] = invocation
            self.scopes[scope] = data["invocation_id"]
            return dict(invocation), False

    def claim_next_canvas_invocation(self, worker_id, *, now=None):
        if self.fail_claim:
            raise self.fail_claim
        now = now or datetime.now(UTC)
        with self.lock:
            candidates = [item for item in self.invocations.values() if (
                item["status"] == "accepted"
                or (item["status"] == "reconcile_pending" and (item["next_attempt_at"] or now) <= now)
                or (item["status"] == "claimed" and item["lease_expires_at"] <= now)
            )]
            if not candidates:
                return None
            item = min(candidates, key=lambda value: value["invocation_id"])
            item["status"] = "claimed"
            item["lease_owner"] = worker_id
            item["lease_token"] = f"{worker_id}:{item['invocation_id']}:{item['attempt_count']}"
            item["lease_expires_at"] = now + timedelta(seconds=30)
            return {
                **item,
                "reconcile": item["dispatched_at"] is not None,
                "principal": {
                    "actor_gid": item["actor_gid"], "team_gid": item["team_gid"],
                },
            }

    def mark_canvas_invocation_dispatched(self, claim, *, now=None):
        with self.lock:
            item = self.invocations[claim["invocation_id"]]
            assert item["status"] == "claimed" and item["lease_token"] == claim["lease_token"]
            item["dispatched_at"] = now or datetime.now(UTC)
            item["attempt_count"] += 1
            return dict(item)

    def complete_canvas_invocation(self, claim, result):
        with self.lock:
            item = self.invocations[claim["invocation_id"]]
            assert item["status"] == "claimed" and item["lease_token"] == claim["lease_token"]
            item.update({
                "status": result.status, "result": asdict(result), "lease_owner": None,
                "lease_token": None, "lease_expires_at": None, "next_attempt_at": None,
            })
            run = self.runs[item["run_id"]]
            run.update({
                "status": result.status, "revision": result.revision,
                "pause_token": result.pause_token,
                "checkpoint": asdict(result), "result": asdict(result),
            })
            return dict(item)

    def record_canvas_uncertainty(self, claim, result, error_code):
        with self.lock:
            item = self.invocations[claim["invocation_id"]]
            assert item["status"] == "claimed" and item["lease_token"] == claim["lease_token"]
            if not claim.get("reconcile") and item["attempt_count"] == 0:
                item["attempt_count"] = 1
            elif claim.get("reconcile"):
                item["attempt_count"] += 1
            item.update({
                "status": "outcome_unknown" if item["attempt_count"] >= 3 else "reconcile_pending",
                "result": asdict(result), "error_code": error_code, "lease_owner": None,
                "lease_token": None, "lease_expires_at": None,
                "next_attempt_at": datetime.now(UTC),
            })
            self.runs[item["run_id"]].update({
                "status": "outcome_unknown", "result": asdict(result),
            })
            return dict(item)

    def replay(self, actor_gid, team_gid, capability_id, key):
        invocation_id = self.scopes[(actor_gid, team_gid, capability_id, key)]
        return dict(self.invocations[invocation_id])


class Runtime:
    def __init__(self):
        self.calls = []
        self.reconciliations = []
        self.result = RuntimeDispatch(
            status="completed", run_token="ignored", revision=1,
            summary="Bearer secret.token",
            node_results=(NodeResult(
                "node-1", "ok", "password=hunter2",
                (OutputValue("api_key", "raw-secret"),),
            ),),
        )
        self.fail = None
        self.reconciled_result = None

    async def test_node(self, *_args):
        raise AssertionError("unused")

    async def resolve_options(self, *_args):
        raise AssertionError("unused")

    async def start(self, request, principal):
        return await self.execute_canvas_command(
            "start", request, principal, run_token="fallback", invocation_id="fallback",
        )

    async def resume(self, request, principal):
        return await self.execute_canvas_command(
            "resume", request, principal, run_token=request.run_token, invocation_id="fallback",
        )

    async def execute_canvas_command(
        self, operation, request, principal, *, run_token, invocation_id,
    ):
        self.calls.append((operation, request, principal, run_token, invocation_id))
        if self.fail:
            raise self.fail
        return replace(
            self.result, run_token=run_token,
            revision=1 if operation == "start" else request.expected_revision + 1,
        )

    async def reconcile_canvas_command(
        self, operation, request, principal, *, run_token, invocation_id,
    ):
        self.reconciliations.append((operation, principal, run_token, invocation_id))
        result = self.reconciled_result or _unknown(
            run_token, 1 if operation == "start" else request.expected_revision + 1,
        )
        return replace(result, run_token=run_token)


def _coordinator(repository):
    return CanvasExecutionCoordinator(repository, token_factory=lambda kind: f"{kind}-{len(repository.invocations) + 1}")


def test_start_idempotency_replays_one_run_and_changed_payload_conflicts():
    repository = MemoryCanvasExecutionRepository()
    coordinator = _coordinator(repository)
    request = CanvasStartRequest("skill-1", 7, (InputValue("project_gid", "p1"),))

    first = coordinator.start(request, PRINCIPAL, "start-key")
    replay = coordinator.start(request, PRINCIPAL, "start-key")

    assert first == replay == RuntimeDispatch(
        status="accepted", run_token="run-1", revision=1,
    )
    assert len(repository.runs) == len(repository.invocations) == 1
    with pytest.raises(CapabilityBusinessError) as error:
        coordinator.start(
            CanvasStartRequest("skill-1", 7, (InputValue("project_gid", "p2"),)),
            PRINCIPAL, "start-key",
        )
    assert error.value.code == "idempotency_conflict"


def test_resume_is_principal_revision_and_pause_bound_single_use_but_replay_safe():
    repository = MemoryCanvasExecutionRepository()
    coordinator = _coordinator(repository)
    start = coordinator.start(CanvasStartRequest("skill-1", 7), PRINCIPAL, "start-key")
    start_claim = repository.claim_next_canvas_invocation("worker")
    repository.mark_canvas_invocation_dispatched(start_claim)
    repository.complete_canvas_invocation(start_claim, RuntimeDispatch(
        status="paused", run_token=start.run_token, revision=1,
        pause_token="pause-secret", halted_node_id="human-1", halted_label="Approve",
    ))
    request = CanvasResumeRequest(start.run_token, "pause-secret", 1, True)

    accepted = coordinator.resume(request, PRINCIPAL, "resume-key")
    replay = coordinator.resume(request, PRINCIPAL, "resume-key")

    assert accepted == replay == RuntimeDispatch(
        status="accepted", run_token=start.run_token, revision=2,
    )
    denials = (
        (request, RunPrincipal("actor-1", "team-2"), "foreign-team"),
        (request, RunPrincipal("actor-2", "team-1"), "foreign-actor"),
        (replace(request, pause_token="stale"), PRINCIPAL, "stale-token"),
        (replace(request, expected_revision=2), PRINCIPAL, "stale-revision"),
    )
    for denied_request, principal, key in denials:
        with pytest.raises(CapabilityBusinessError) as error:
            coordinator.resume(denied_request, principal, key)
        assert (error.value.code, error.value.message, error.value.details) == (
            "resource_not_found", "Agent canvas execution was not found", {},
        )


def test_dispatcher_restores_persisted_principal_and_terminal_replay_is_canonical_and_sanitized():
    repository = MemoryCanvasExecutionRepository()
    coordinator = _coordinator(repository)
    runtime = Runtime()
    accepted = coordinator.start(CanvasStartRequest("skill-1", 7), PRINCIPAL, "start-key")

    result = asyncio.run(CanvasExecutionDispatcher(repository, runtime).dispatch_next(worker_id="worker-1"))
    replay = coordinator.start(CanvasStartRequest("skill-1", 7), PRINCIPAL, "start-key")

    assert result.status == replay.status == "completed"
    assert runtime.calls[0][2] == PRINCIPAL
    assert runtime.calls[0][3:] == (accepted.run_token, "invocation-1")
    assert replay.run_token == accepted.run_token and replay.revision == 1
    assert replay.summary == "Bearer [redacted]"
    assert replay.node_results[0].summary == "[redacted-credential]"
    assert replay.node_results[0].output_values[0].value == "[redacted]"


def test_duplicate_workers_cannot_both_execute_one_claimed_invocation():
    repository = MemoryCanvasExecutionRepository()
    runtime = Runtime()
    _coordinator(repository).start(CanvasStartRequest("skill-1", 7), PRINCIPAL, "start-key")
    dispatcher = CanvasExecutionDispatcher(repository, runtime)

    async def run():
        return await asyncio.gather(*(
            dispatcher.dispatch_next(worker_id=f"worker-{index}") for index in range(8)
        ))

    results = asyncio.run(run())

    assert len(runtime.calls) == 1
    assert sum(result is not None for result in results) == 1


def test_pre_dispatch_crash_reclaims_but_post_dispatch_crash_reconciles_same_invocation_without_duplicate():
    repository = MemoryCanvasExecutionRepository()
    runtime = Runtime()
    coordinator = _coordinator(repository)
    coordinator.start(CanvasStartRequest("skill-1", 7), PRINCIPAL, "start-before")
    abandoned = repository.claim_next_canvas_invocation("dead-worker")
    repository.invocations[abandoned["invocation_id"]]["lease_expires_at"] = datetime.now(UTC) - timedelta(seconds=1)

    reclaimed = asyncio.run(CanvasExecutionDispatcher(repository, runtime).dispatch_next(worker_id="worker-2"))

    assert reclaimed.status == "completed"
    assert [call[-1] for call in runtime.calls] == [abandoned["invocation_id"]]

    coordinator.start(CanvasStartRequest("skill-2", 3), PRINCIPAL, "start-after")
    dispatched = repository.claim_next_canvas_invocation("dead-worker")
    repository.mark_canvas_invocation_dispatched(dispatched)
    repository.invocations[dispatched["invocation_id"]]["lease_expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    runtime.reconciled_result = RuntimeDispatch(
        status="completed", run_token="ignored", revision=1, summary="reconciled",
    )

    reconciled = asyncio.run(CanvasExecutionDispatcher(repository, runtime).dispatch_next(worker_id="worker-3"))

    assert reconciled.status == "completed"
    assert len(runtime.calls) == 1
    assert runtime.reconciliations[-1][-1] == dispatched["invocation_id"]


def test_runtime_timeout_is_replayable_outcome_unknown_and_reclaim_reuses_invocation_identity():
    repository = MemoryCanvasExecutionRepository()
    runtime = Runtime()
    runtime.fail = CapabilityBusinessError("runtime_timeout", "timed out", retryable=True)
    coordinator = _coordinator(repository)
    request = CanvasStartRequest("skill-1", 7)
    accepted = coordinator.start(request, PRINCIPAL, "start-key")
    dispatcher = CanvasExecutionDispatcher(repository, runtime)

    unknown = asyncio.run(dispatcher.dispatch_next(worker_id="worker-1"))
    replay = coordinator.start(request, PRINCIPAL, "start-key")

    assert unknown == replay == _unknown(accepted.run_token, 1)
    invocation_id = runtime.calls[-1][-1]
    runtime.fail = None
    runtime.reconciled_result = RuntimeDispatch(
        status="completed", run_token="ignored", revision=1, summary="reconciled",
    )
    reconciled = asyncio.run(dispatcher.dispatch_next(worker_id="worker-2"))

    assert reconciled.status == "completed"
    assert runtime.reconciliations[-1][-1] == invocation_id
    assert coordinator.start(request, PRINCIPAL, "start-key") == reconciled


def test_worker_health_and_fatal_signal_use_registry_lifecycle_surface_without_agent_health_capability():
    repository = MemoryCanvasExecutionRepository()
    repository.fail_claim = ValueError("secret tenant configuration")
    signals = []
    worker = CanvasExecutionWorker(
        CanvasExecutionDispatcher(repository, Runtime()),
        supervision_signal=signals.append, idle_seconds=0.001,
    )

    async def run():
        await worker.start()
        for _ in range(50):
            if worker.health["status"] == "fatal":
                break
            await asyncio.sleep(0.001)
        assert worker.health["status"] == "fatal"
        assert worker.health["last_error_code"] == "ValueError"
        assert "secret" not in repr((worker.health, signals))
        assert signals[-1]["event"] == "lifecycle_worker_failed"
        await worker.stop()

    asyncio.run(run())


def test_default_provider_registers_canvas_worker_lifecycle_and_replays_terminal_result(monkeypatch):
    from plugins.agent.agent_backend import capabilities

    repository = MemoryCanvasExecutionRepository()
    runtime = Runtime()
    monkeypatch.setattr(capabilities, "AgentCapabilityRepository", lambda: repository)
    monkeypatch.setattr(capabilities, "ProductionAgentCanvasRuntime", lambda **_kwargs: runtime)
    class Registry:
        def __init__(self):
            self.handlers = {}
            self.lifecycles = {}
            self.health_providers = {}
            self.signals = {}

        def register(self, spec, handler, **_kwargs):
            self.handlers[spec.id] = handler

        def get(self, capability_id):
            return SimpleNamespace(handler=self.handlers[capability_id])

        def register_lifecycle(self, name, start, stop, *, health):
            self.lifecycles[name] = (start, stop)
            self.health_providers[name] = health
            self.signals[name] = []

        def publish_lifecycle_signal(self, name, signal):
            self.signals[name].append(dict(signal))

        def lifecycle_names(self):
            return tuple(sorted(self.lifecycles))

        def lifecycle_health(self, name):
            return dict(self.health_providers[name]())

        async def start_lifecycles(self):
            for name in self.lifecycle_names():
                await self.lifecycles[name][0]()

        async def stop_lifecycles(self):
            for name in reversed(self.lifecycle_names()):
                await self.lifecycles[name][1]()

    registry = Registry()
    capabilities.register_capabilities(registry)
    context = SimpleNamespace(user_gid="actor-1", team_gid="team-1", idempotency_key="start-key")
    payload = {"skill_gid": "skill-1", "expected_revision": 7, "input_values": []}

    accepted = asyncio.run(registry.get("agent.canvas.execution.start").handler(payload, context))

    async def run():
        await registry.start_lifecycles()
        for _ in range(50):
            if repository.replay("actor-1", "team-1", "agent.canvas.execution.start", "start-key")["status"] == "completed":
                break
            await asyncio.sleep(0.002)
        await registry.stop_lifecycles()

    asyncio.run(run())
    replay = asyncio.run(registry.get("agent.canvas.execution.start").handler(payload, context))

    assert registry.lifecycle_names() == ("agent.canvas-execution-worker",)
    assert accepted["data"]["status"] == "accepted"
    assert replay["data"]["status"] == "completed"
    assert registry.lifecycle_health("agent.canvas-execution-worker")["status"] == "stopped"


def test_agent_0003_and_sql_repository_pin_one_transaction_state_machine_and_atomic_claims():
    migration = ROOT / "backend/db/migrations/domains/agent/0003_canvas_execution_control.sql"
    sql = migration.read_text(encoding="utf-8").lower()
    repository_source = (
        ROOT / "plugins/agent/agent_backend/infrastructure/repository.py"
    ).read_text(encoding="utf-8").lower()

    assert "workmanship_agent_canvas_runs" in sql
    assert "workmanship_agent_canvas_invocations" in sql
    assert "workmanship_agent_canvas_audit_events" in sql
    assert "unique key uq_agent_canvas_invocation_idempotency" in sql
    assert all(field in sql for field in (
        "actor_gid", "team_gid", "payload_hash", "run_token_hash", "pause_token_hash",
        "target_state", "revision", "lease_owner", "lease_token", "lease_expires_at",
        "attempt_count", "result_json",
    ))
    assert "for update skip locked" in repository_source
    assert "status='claimed'" in repository_source
    assert "lease_token=%s" in repository_source
    assert "target_dispatched_at" in repository_source


class CommandExecutor:
    calls = []
    result = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def execute(self, canvas, init_params=None, restore_results=None):
        self.__class__.calls.append((self.kwargs, canvas, init_params, restore_results))
        return self.__class__.result


def _command_skill():
    return {
        "gid": "skill-1", "owner_gid": "actor-1", "team_gid": "team-1",
        "scope": "private", "status": "active", "revision": 7, "title": "Approval flow",
        "content": {
            "inputs_schema": {"properties": {"project_gid": {"type": "string"}}},
            "nodes": [{
                "id": "human-1", "type": "human", "label": "Approve",
                "inputs_schema": {"properties": {"decision": {"type": "string"}}},
                "params": {
                    "task_desc": "approve",
                    "collect_fields": [{
                        "key": "decision", "label": "Decision", "type": "radio",
                        "options": [{"value": "yes", "label": "Yes"}],
                    }],
                    "canvas_layout": {
                        "column_labels": ["Review"], "column_width": 280,
                        "lane_height": 60, "hide_lane_labels": False,
                    },
                },
            }],
            "edges": [],
        },
    }


def test_production_command_engine_executes_persisted_skill_and_projects_bounded_pause():
    assert CanvasCommandEngine is not None
    CommandExecutor.calls = []
    CommandExecutor.result = {
        "status": "paused", "halted_node_id": "human-1", "halted_label": "Approve",
        "halt_reason": "Bearer abc.def", "summary": "password=hunter2",
        "node_results": {
            "human-1": {
                "_status": "pending_approval", "_summary": "token=raw-secret",
                "api_key": "raw-secret",
            },
        },
    }
    engine = CanvasCommandEngine(
        resource_loader=lambda kind, gid: _command_skill(),
        execution_loader=lambda *_args: None,
        executor_factory=CommandExecutor,
    )

    result = asyncio.run(engine.start(
        CanvasStartRequest("skill-1", 7, (InputValue("project_gid", "p1"),)),
        PRINCIPAL, run_token="run-opaque",
    ))

    assert result.status == "paused" and result.run_token == "run-opaque"
    assert result.revision == 1 and result.pause_token
    assert result.halted_node_id == "human-1" and result.halted_label == "Approve"
    assert result.halt_reason == "Bearer [redacted]"
    assert result.summary == "[redacted-credential]"
    assert result.node_results[0].summary == "[redacted-credential]"
    assert result.node_results[0].output_values[0].value == "[redacted]"
    assert result.collect_fields[0].key == "decision"
    assert result.canvas_layout.column_width == 280
    kwargs, canvas, init_params, restore = CommandExecutor.calls.pop()
    assert kwargs == {"auth_mode": "feishu", "auth_token": "", "owner_gid": "actor-1"}
    assert canvas == _command_skill()["content"]
    assert init_params == {"project_gid": "p1"} and restore is None


def test_production_command_engine_restores_checkpoint_principal_and_resume_input_once():
    assert CanvasCommandEngine is not None
    checkpoint = asdict(RuntimeDispatch(
        status="paused", run_token="run-opaque", revision=1,
        pause_token="pause-opaque", halted_node_id="human-1", halted_label="Approve",
        node_results=(NodeResult(
            "human-1", "pending_approval", "waiting",
            (OutputValue("api_key", "already-redacted"),),
        ),),
    ))
    state = {
        "skill_gid": "skill-1", "skill_revision": 7, "revision": 2,
        "checkpoint": checkpoint,
    }
    CommandExecutor.calls = []
    CommandExecutor.result = {
        "status": "completed", "summary": "done",
        "node_results": {
            "human-1": {"_status": "ok", "_summary": "approved", "decision": "yes"},
        },
    }
    engine = CanvasCommandEngine(
        resource_loader=lambda kind, gid: _command_skill(),
        execution_loader=lambda run, actor, team: state if (
            run, actor, team
        ) == ("run-opaque", "actor-1", "team-1") else None,
        executor_factory=CommandExecutor,
    )
    request = CanvasResumeRequest(
        "run-opaque", "pause-opaque", 1, True, (InputValue("decision", "yes"),),
    )

    result = asyncio.run(engine.resume(request, PRINCIPAL, run_token="run-opaque"))

    assert result.status == "completed" and result.revision == 2
    _kwargs, _canvas, init_params, restore = CommandExecutor.calls.pop()
    assert init_params is None
    assert restore["human-1"] == {
        "_status": "ok", "_summary": "Approved", "api_key": "[redacted]", "decision": "yes",
    }

    denied = asyncio.run(engine.resume(replace(request, approved=False), PRINCIPAL, run_token="run-opaque"))
    assert denied.status == "halted" and denied.revision == 2
    assert CommandExecutor.calls == []


def test_production_runtime_uses_existing_worker_boundary_with_stable_invocation_and_nonexecuting_reconcile():
    runtime = ProductionAgentCanvasRuntime(worker_timeout=5.0)
    request = CanvasStartRequest("skill-1", 7)
    calls = []

    async def run_process(operation, sent_request, principal, **metadata):
        calls.append((operation, sent_request, principal, metadata))
        return {
            "status": "completed", "run_token": metadata["run_token"], "revision": 1,
            "pause_token": None, "halted_node_id": None, "halted_label": None,
            "halt_reason": None, "skill_title": None, "summary": metadata["invocation_id"],
            "node_results": [], "context_summary": [], "collect_fields": [],
            "canvas_layout": None,
        }

    runtime._run_process = run_process

    result = asyncio.run(runtime.execute_canvas_command(
        "start", request, PRINCIPAL, run_token="run-opaque", invocation_id="invocation-stable",
    ))
    unknown = asyncio.run(runtime.reconcile_canvas_command(
        "start", request, PRINCIPAL, run_token="run-opaque", invocation_id="invocation-stable",
    ))

    assert result == RuntimeDispatch(
        status="completed", run_token="run-opaque", revision=1, summary="invocation-stable",
    )
    assert calls == [("start", request, PRINCIPAL, {
        "run_token": "run-opaque", "invocation_id": "invocation-stable",
    })]
    assert unknown.status == "outcome_unknown"
    assert unknown.run_token == "run-opaque" and unknown.revision == 1


def test_sql_repository_serializes_slotted_terminal_result_inside_claim_transaction(monkeypatch):
    from plugins.agent.agent_backend.infrastructure.repository import AgentCapabilityRepository

    class Cursor:
        rowcount = 1

        def __init__(self):
            self.statements = []
            self.selected = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=()):
            self.statements.append((" ".join(sql.split()), tuple(params)))
            if sql.lstrip().upper().startswith("SELECT"):
                self.selected = {
                    "invocation_id": "invocation-1", "run_id": "run-1",
                    "actor_gid": "actor-1", "team_gid": "team-1",
                    "status": "claimed", "revision": 1, "lease_token": "lease-1",
                }

        def fetchone(self):
            return self.selected

    cursor = Cursor()

    class Connection:
        def cursor(self):
            return cursor

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(
        "plugins.agent.agent_backend.infrastructure.repository.get_agent_conn", connection,
    )
    result = RuntimeDispatch(
        status="completed", run_token="run-opaque", revision=1, summary="done",
    )

    AgentCapabilityRepository().complete_canvas_invocation({
        "invocation_id": "invocation-1", "lease_token": "lease-1",
    }, result)

    updates = [(sql, params) for sql, params in cursor.statements if sql.startswith("UPDATE")]
    assert len(updates) == 2
    stored = json.loads(updates[0][1][1])
    assert stored == {
        "status": "completed", "run_token": "run-opaque", "revision": 1,
        "pause_token": None, "halted_node_id": None, "halted_label": None,
        "halt_reason": None, "skill_title": None, "summary": "done",
        "node_results": [], "context_summary": [], "collect_fields": [],
        "canvas_layout": None,
    }
    assert any("workmanship_agent_canvas_audit_events" in sql for sql, _ in cursor.statements)
