"""Bounded service boundary for the test-only governance capability extension."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from backend.capabilities.models_next import CapabilityBusinessError

from .analysis import AnalysisRequest, run_deterministic_analysis


_MAX_SEARCH = 200
_MAX_GRAPH_DEPTH = 4
_MAX_GRAPH_NODES = 500


def _business_error(code: str) -> CapabilityBusinessError:
    return CapabilityBusinessError(code, code)


def _gid(value: object, *, field: str = "target_gid") -> int:
    try:
        candidate = int(str(value))
    except (TypeError, ValueError) as exc:
        raise _business_error("invalid_input") from exc
    if candidate < 1:
        raise _business_error("invalid_input")
    return candidate


def _context_user(context: object) -> str:
    return str(getattr(context, "user_gid", ""))


@dataclass(frozen=True)
class GovernedRun:
    run_gid: str
    snapshot_gid: str
    kind: str
    requested_by: str
    idempotency_key: str
    status: str = "queued"


class CapabilityGovernanceService:
    """Small service port with explicit bounds and idempotent in-process test state.

    Persistence ports may implement ``get_snapshot`` and are deliberately kept
    separate from capability transport and Gateway identity objects.
    """

    def __init__(
        self,
        store: Any | None = None,
        *,
        scanner: Any | None = None,
        analysis_runner: Callable[..., Any] = run_deterministic_analysis,
    ) -> None:
        self._store = store
        self._scanner = scanner
        self._analysis_runner = analysis_runner
        self._runs: dict[tuple[str, str, str], GovernedRun] = {}
        self._mutations: dict[tuple[str, str], dict[str, str]] = {}
        self._next_run_gid = 1

    def base_capability_registry_search(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        requested = payload.get("limit", _MAX_SEARCH)
        try:
            limit = min(max(1, int(requested)), _MAX_SEARCH)
        except (TypeError, ValueError) as exc:
            raise _business_error("invalid_input") from exc
        query = str(payload.get("query", "")).strip().lower()
        entries = sorted(self._entries(), key=lambda item: str(getattr(item, "capability_id", "")))
        matches = [item for item in entries if not query or query in str(getattr(item, "capability_id", "")).lower()]
        return self._completed("base.capability_registry.search", limit=limit, items=tuple(matches[:limit]))

    def base_capability_registry_get(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        target = _gid(payload.get("target_gid"))
        for entry in self._entries():
            if str(getattr(entry, "capability_version_gid", "")) == str(target):
                return self._completed("base.capability_registry.get", item=entry)
        raise _business_error("resource_not_found")

    def base_capability_graph_get(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        snapshot = self._snapshot(payload)
        depth = payload.get("max_depth")
        nodes = payload.get("max_nodes")
        if depth is None or nodes is None:
            raise _business_error("invalid_input")
        try:
            max_depth, max_nodes = int(depth), int(nodes)
        except (TypeError, ValueError) as exc:
            raise _business_error("invalid_input") from exc
        if not 1 <= max_depth <= _MAX_GRAPH_DEPTH or not 1 <= max_nodes <= _MAX_GRAPH_NODES:
            raise _business_error("invalid_input")
        document = getattr(snapshot, "document", None)
        graph_nodes = tuple(getattr(document, "nodes", ()))[:max_nodes]
        return self._completed(
            "base.capability_graph.get", snapshot_gid=str(getattr(snapshot, "snapshot_gid")),
            max_depth=max_depth, max_nodes=max_nodes, nodes=graph_nodes,
        )

    def base_capability_finding_search(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._completed("base.capability_finding.search", items=())

    def base_capability_analysis_get(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        target = str(payload.get("target_gid", ""))
        run = next((item for item in self._runs.values() if item.run_gid == target), None)
        if run is None:
            raise _business_error("resource_not_found")
        return self._completed("base.capability_analysis.get", run=run)

    def base_capability_analysis_run(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._queue("base.capability_analysis.run", payload, context, kind="analysis")

    def base_capability_repair_prompt_generate(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        snapshot = self._snapshot(payload)
        return self._completed(
            "base.capability_repair_prompt.generate", snapshot_gid=str(getattr(snapshot, "snapshot_gid")),
        )

    def base_capability_scan_run(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        self._idempotency(payload)
        if self._scanner is not None:
            self._scanner.scan(str(payload.get("code_revision", "")))
        return self._accepted("base.capability_scan.run")

    def base_capability_test_run(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._queue("base.capability_test.run", payload, context, kind="test")

    def base_capability_proposal_submit(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._mutate("base.capability_proposal.submit", payload, require_version=False)

    def base_capability_review_decide(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._mutate("base.capability_review.decide", payload, require_version=True)

    def base_capability_waiver_grant(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._mutate("base.capability_waiver.grant", payload, require_version=False)

    def base_capability_waiver_revoke(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._mutate("base.capability_waiver.revoke", payload, require_version=True)

    def base_capability_release_gate_evaluate(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._completed("base.capability_release_gate.evaluate")

    def run_analysis(self, snapshot_gid: str | int) -> Any:
        """Execute only the snapshot that was pinned when the run was queued."""
        snapshot = self._snapshot({"target_gid": str(snapshot_gid)})
        return self._analysis_runner(getattr(snapshot, "document"), AnalysisRequest())

    def _queue(self, capability_id: str, payload: Mapping[str, Any], context: object, *, kind: str) -> dict[str, Any]:
        key = self._idempotency(payload)
        snapshot = self._snapshot(payload)
        snapshot_gid = str(getattr(snapshot, "snapshot_gid"))
        run_key = (kind, snapshot_gid, key)
        run = self._runs.get(run_key)
        if run is None:
            run = GovernedRun(str(self._next_run_gid), snapshot_gid, kind, _context_user(context), key)
            self._next_run_gid += 1
            self._runs[run_key] = run
        return self._accepted(capability_id, run_gid=run.run_gid, snapshot_gid=run.snapshot_gid)

    def _mutate(self, capability_id: str, payload: Mapping[str, Any], *, require_version: bool) -> dict[str, Any]:
        key = self._idempotency(payload)
        if require_version and not str(payload.get("row_version") or payload.get("expected_resource_version") or "").strip():
            raise _business_error("version_conflict")
        mutation_key = (capability_id, key)
        self._mutations.setdefault(mutation_key, {"idempotency_key": key})
        return self._accepted(capability_id)

    def _snapshot(self, payload: Mapping[str, Any]) -> Any:
        if self._store is None or not hasattr(self._store, "get_snapshot"):
            raise _business_error("resource_not_found")
        snapshot = self._store.get_snapshot(_gid(payload.get("target_gid")))
        if snapshot is None:
            raise _business_error("resource_not_found")
        return snapshot

    def _entries(self) -> tuple[Any, ...]:
        if self._store is None:
            return ()
        snapshots = getattr(self._store, "_snapshots", {})
        if isinstance(snapshots, Mapping):
            return tuple(entry for snapshot in snapshots.values() for entry in getattr(snapshot, "entries", ()))
        snapshot = getattr(self._store, "latest_snapshot", lambda: None)()
        return tuple(getattr(snapshot, "entries", ())) if snapshot is not None else ()

    @staticmethod
    def _idempotency(payload: Mapping[str, Any]) -> str:
        value = str(payload.get("idempotency_key", "")).strip()
        if not value:
            raise _business_error("idempotency_conflict")
        return value

    @staticmethod
    def _completed(capability_id: str, **data: Any) -> dict[str, Any]:
        return {"capability_id": capability_id, "status": "completed", **data}

    @staticmethod
    def _accepted(capability_id: str, **data: Any) -> dict[str, Any]:
        return {"capability_id": capability_id, "status": "accepted", **data}


__all__ = ["CapabilityGovernanceService", "GovernedRun"]
