"""Bounded service boundary for the test-only governance capability extension."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import inspect
from typing import Any

from backend.capabilities.models_next import CapabilityBusinessError
from backend.domain_ports.capability_governance_ai import GovernanceAdvisorPort

from .analysis import AnalysisRequest, run_deterministic_analysis
from .prompting import PromptAuthorizationError, RedactedPrompt, _render_repair_prompt
from .release_gate import ReleaseCandidate, ReleaseGate, ReleaseGateError
from .workflow import ProposalService, ReviewerContext, WaiverService, WorkflowError


_MAX_SEARCH = 200
_MAX_GRAPH_DEPTH = 4
_MAX_GRAPH_NODES = 500
_PROMPT_READ_PERMISSION = "base.capability_repair_prompt.read"
_DEFAULT_PORT = object()


class _InlineGovernanceWorker:
    """Deterministic local worker used only when no worker port is supplied.

    Production/test deployments should inject :class:`LeasedGovernanceWorker`;
    this adapter keeps direct unit calls executable while still running the
    supplied callback instead of returning an accepted no-op.
    """

    @staticmethod
    def run_once(kind: str, run_gid: str, execute: Callable[..., Any]) -> bool:
        execute()
        return True


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


def _mutation_actor(context: object) -> str:
    actor = _context_user(context).strip()
    if not actor:
        raise _business_error("invalid_input")
    return actor


def _context_values(context: object, *fields: str) -> tuple[str, ...]:
    values: list[str] = []
    for field in fields:
        value = getattr(context, field, ())
        if value is not None:
            values.extend(str(item) for item in value)
    return tuple(values)


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = str(payload.get(field, "")).strip()
    if not value:
        raise _business_error("invalid_input")
    return value


def _payload_gid(payload: Mapping[str, Any], *fields: str) -> int:
    for field in fields:
        if payload.get(field) is not None:
            return _gid(payload.get(field), field=field)
    raise _business_error("invalid_input")


def _row_version(payload: Mapping[str, Any]) -> int:
    value = payload.get("row_version") or payload.get("expected_resource_version")
    if value is None or not str(value).strip():
        raise _business_error("version_conflict")
    return _gid(value, field="row_version")


def _optional_bool(payload: Mapping[str, Any], field: str, *, default: bool) -> bool:
    value = payload.get(field)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise _business_error("invalid_input")
    return value


def _items(payload: Mapping[str, Any], field: str) -> tuple[Any, ...]:
    value = payload.get(field, ())
    if isinstance(value, (str, bytes, Mapping)):
        raise _business_error("invalid_input")
    try:
        return tuple(value)
    except TypeError as exc:
        raise _business_error("invalid_input") from exc


def _timestamp(payload: Mapping[str, Any], field: str) -> datetime | None:
    value = payload.get(field)
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise _business_error("invalid_input")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _business_error("invalid_input") from exc


def _workflow_error(exc: WorkflowError | ReleaseGateError) -> CapabilityBusinessError:
    code = str(exc)
    return _business_error(code if code else "invalid_input")


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
        analysis_runner: Callable[..., Any] | None | object = _DEFAULT_PORT,
        test_runner: Any | None = None,
        worker: Any | None | object = _DEFAULT_PORT,
        advisor: GovernanceAdvisorPort | None = None,
        audit_sink: Any | None = None,
        proposal_service: ProposalService | None = None,
        waiver_service: WaiverService | None = None,
        release_gate: ReleaseGate | None = None,
        release_evidence_port: Any | None = None,
        workflow_port: Any | None = None,
    ) -> None:
        self._store = store
        self._scanner = scanner
        self._analysis_runner = run_deterministic_analysis if analysis_runner is _DEFAULT_PORT else analysis_runner
        self._test_runner = test_runner
        self._worker = _InlineGovernanceWorker() if worker is _DEFAULT_PORT else worker
        self._advisor = advisor
        self._audit_sink = audit_sink
        self._runs: dict[tuple[str, str, str], GovernedRun] = {}
        self._prompt_records: dict[str, dict[str, str]] = {}
        self._prompt_texts: dict[str, str] = {}
        self._finding_gids: dict[str, int] = {}
        self._next_run_gid = 1
        self._next_governance_gid_value = 1
        self._proposals = proposal_service or ProposalService(
            next_gid=self._next_governance_gid, audit_sink=audit_sink,
        )
        self._waivers = waiver_service or WaiverService(
            next_gid=self._next_governance_gid, audit_sink=audit_sink,
        )
        # Release evidence is deliberately a separate, service-owned port.  A
        # Gateway caller may identify a candidate, but cannot supply the
        # statuses, findings, approvals, or hashes that authorize a pass.
        self._release_evidence_port = release_evidence_port
        # SQL snapshots survive a process restart, but the small workflow
        # implementations are intentionally in-memory test components.  Do
        # not let a persistent runtime silently report a mutation that would
        # disappear on restart; the launcher must inject a workflow port.
        self._workflow_port = workflow_port
        self._workflow_persistence_required = bool(getattr(store, "persistent", False)) and workflow_port is None
        if workflow_port is not None:
            # A persistent adapter may expose the durable state machines
            # directly.  Keeping this as a narrow port avoids coupling the
            # service to a particular SQL driver or schema implementation.
            self._proposals = getattr(workflow_port, "proposal_service", self._proposals)
            self._waivers = getattr(workflow_port, "waiver_service", self._waivers)
        self._release_gate = release_gate or ReleaseGate(
            next_gid=self._next_governance_gid, audit_sink=audit_sink,
        )
        if workflow_port is not None:
            self._release_gate = getattr(workflow_port, "release_gate", self._release_gate)

    def bind_registry_snapshot(self, snapshot: Any) -> None:
        """Bind the registry used by the scanner to the serving registry."""
        if self._scanner is None:
            return
        binder = getattr(self._scanner, "bind_registry_snapshot", None)
        if not callable(binder):
            raise RuntimeError("governance_scanner_registry_binding_unavailable")
        binder(snapshot)

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

    def base_capability_proposal_search(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        """Return a bounded, read-only projection of governance proposals."""
        limit = self._bounded_limit(payload.get("limit", _MAX_SEARCH))
        query = str(payload.get("query", "")).strip().lower()
        domain = str(payload.get("domain", "")).strip().lower()
        stage = str(payload.get("stage", "")).strip().lower()
        proposals = self._proposal_records()
        def matches(item: Mapping[str, Any]) -> bool:
            if domain and domain not in str(item.get("domain", "")).lower():
                return False
            if stage and stage != str(item.get("status", "")).lower():
                return False
            if query and query not in " ".join(str(item.get(field, "")) for field in ("proposal_gid", "capability_id", "status", "domain")).lower():
                return False
            return True
        items = tuple(item for item in proposals if matches(item))[:limit]
        return self._completed(
            "base.capability_proposal.search", items=items,
            data={"available": self._workflow_port is not None or not self._workflow_persistence_required,
                  "checked_at": self._now_iso(), "next_cursor": None},
        )

    def base_capability_health_get(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        """Calculate per-domain health from one pinned snapshot and its findings."""
        requested = payload.get("domains")
        if requested is None:
            domains = tuple(sorted({str(getattr(entry, "owner_domain", "")) for entry in self._entries() if getattr(entry, "owner_domain", None)}))
            if not domains:
                domains = ("base", "agent", "craft", "digital_model", "factory", "integration", "project_management", "simulation", "ontology", "knowledge", "device")
        elif isinstance(requested, (str, bytes, Mapping)):
            raise _business_error("invalid_input")
        else:
            domains = tuple(dict.fromkeys(str(value).strip() for value in requested if str(value).strip()))[:11]
        snapshot = None
        if payload.get("snapshot_gid") is not None:
            snapshot = self._snapshot({"target_gid": payload.get("snapshot_gid")})
        else:
            snapshot = self._latest_snapshot()
        if snapshot is None:
            return self._completed(
                "base.capability_health.get",
                items=tuple({"domain": domain, "status": "unverified", "reason": "snapshot_unavailable", "checked_at": self._now_iso(), "entry_count": 0, "finding_count": 0, "severities": []} for domain in domains),
                data={"available": False, "checked_at": self._now_iso()},
            )
        findings = self._load_findings(snapshot, payload, context)
        grouped: dict[str, list[Mapping[str, Any]]] = {domain: [] for domain in domains}
        for finding in findings:
            values = finding.get("domains", ()) if isinstance(finding, Mapping) else getattr(finding, "domains", ())
            for domain in values or ():
                if str(domain) in grouped:
                    grouped[str(domain)].append(finding)
        entries_by_domain = {domain: 0 for domain in domains}
        for entry in getattr(snapshot, "entries", ()):
            owner = str(getattr(entry, "owner_domain", ""))
            if owner in entries_by_domain:
                entries_by_domain[owner] += 1
        checked_at = self._now_iso()
        items = []
        for domain in domains:
            domain_findings = grouped[domain]
            severities = sorted({str((finding.get("severity") if isinstance(finding, Mapping) else getattr(finding, "severity", "warning"))) for finding in domain_findings})
            if not entries_by_domain[domain]:
                status, reason = "blocked", "no_capabilities_in_snapshot"
            elif domain_findings:
                status, reason = "attention", "open_findings"
            else:
                status, reason = "healthy", "snapshot_verified"
            items.append({
                "domain": domain, "status": status, "snapshot_gid": str(getattr(snapshot, "snapshot_gid")),
                "checked_at": checked_at, "entry_count": entries_by_domain[domain],
                "finding_count": len(domain_findings), "severities": severities, "reason": reason,
            })
        return self._completed(
            "base.capability_health.get", items=tuple(items),
            data={"available": True, "snapshot_gid": str(getattr(snapshot, "snapshot_gid")), "checked_at": checked_at},
        )

    def base_capability_audit_search(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        """Search only redacted audit projections from the configured sink."""
        limit = self._bounded_limit(payload.get("limit", _MAX_SEARCH))
        actor = str(payload.get("actor", "")).strip()
        capability = str(payload.get("capability", "")).strip().lower()
        event_type = str(payload.get("event_type", "")).strip().lower()
        result = str(payload.get("result", "")).strip().lower()
        events = self._audit_events()
        items: list[dict[str, Any]] = []
        for event in reversed(events):
            item = self._audit_record(event)
            if actor and actor != item.get("actor_gid"):
                continue
            if capability and capability not in str(item.get("capability_id", "")).lower():
                continue
            if event_type and event_type not in str(item.get("event_type", item.get("operation", ""))).lower():
                continue
            if result and result != str(item.get("status", "")).lower():
                continue
            items.append(item)
            if len(items) >= limit:
                break
        return self._completed(
            "base.capability_audit.search", items=tuple(items),
            data={"available": self._audit_sink is not None, "checked_at": self._now_iso(), "next_cursor": None},
        )

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
        source_nodes = tuple(getattr(document, "nodes", ()))[:max_nodes]
        node_gids = getattr(snapshot, "node_gids", {})
        graph_nodes = tuple(
            {**getattr(node, "__dict__", {}), "implementation_node_gid": node_gids.get(getattr(node, "canonical_key", ""))}
            if node_gids.get(getattr(node, "canonical_key", "")) is not None else node
            for node in source_nodes
        )
        result = self._completed(
            "base.capability_graph.get", snapshot_gid=str(getattr(snapshot, "snapshot_gid")),
            max_depth=max_depth, max_nodes=max_nodes, nodes=graph_nodes,
        )
        bindings = tuple(getattr(document, "bindings", ()))
        relations = tuple(getattr(document, "relations", ()))
        binding_gids = tuple(getattr(snapshot, "binding_gids", ()))
        relation_gids = tuple(getattr(snapshot, "relation_gids", ()))
        if bindings:
            result["bindings"] = tuple(
                {**getattr(binding, "__dict__", {}), "binding_gid": binding_gids[index]}
                if index < len(binding_gids) else binding
                for index, binding in enumerate(bindings[:_MAX_GRAPH_NODES])
            )
        if relations:
            result["relations"] = tuple(
                {**getattr(relation, "__dict__", {}), "relation_gid": relation_gids[index]}
                if index < len(relation_gids) else relation
                for index, relation in enumerate(relations[:_MAX_GRAPH_NODES])
            )
        return result

    def base_capability_finding_search(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        requested = payload.get("limit", _MAX_SEARCH)
        try:
            limit = min(max(1, int(requested)), _MAX_SEARCH)
        except (TypeError, ValueError) as exc:
            raise _business_error("invalid_input") from exc
        snapshot = None
        if payload.get("target_gid") is not None:
            snapshot = self._snapshot(payload)
        elif self._store is not None:
            snapshot = self._latest_snapshot()
        findings: tuple[Any, ...] = ()
        if snapshot is not None:
            custom_loader = getattr(self._store, "get_findings", None)
            if callable(custom_loader):
                findings = tuple(custom_loader(int(getattr(snapshot, "snapshot_gid"))) or ())[:_MAX_SEARCH]
            else:
                if self._analysis_runner is None:
                    raise _business_error("governance_dependency_unavailable")
                analysis = self._invoke_port(
                    self._analysis_runner, snapshot=snapshot, payload=payload, context=context,
                    kind="analysis", run_gid=str(getattr(snapshot, "snapshot_gid")),
                    request=AnalysisRequest(),
                )
                findings = self._finding_records(snapshot, getattr(analysis, "findings", ()))
        query = str(payload.get("query", "")).strip().lower()
        if query:
            def field(item: Any, name: str) -> Any:
                if isinstance(item, Mapping):
                    return item.get(name, "")
                return getattr(item, name, "")
            findings = tuple(item for item in findings if query in str(field(item, "code")).lower()
                             or query in str(field(item, "fingerprint")).lower())
        return self._completed("base.capability_finding.search", findings=tuple(findings[:limit]))

    def base_capability_analysis_get(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        target = str(payload.get("target_gid", ""))
        run = next((item for item in self._runs.values() if item.run_gid == target), None)
        if run is None:
            raise _business_error("resource_not_found")
        return self._completed("base.capability_analysis.get", run=run)

    def base_capability_analysis_run(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._start_and_execute(
            "base.capability_analysis.run", payload, context, kind="analysis",
            runner=self._analysis_runner,
        )

    def base_capability_repair_prompt_generate(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        snapshot = self._snapshot(payload)
        # A target-only request remains a useful bounded discovery operation for
        # the local acceptance probe, but it must not pretend that a prompt was
        # generated.  A real prompt requires the structured candidate finding
        # and evidence boundary below; arbitrary free-form prompt text is never
        # accepted at this transport boundary.
        if not all(field in payload for field in ("finding", "evidence", "boundary")):
            return self._completed(
                "base.capability_repair_prompt.generate", snapshot_gid=str(getattr(snapshot, "snapshot_gid")),
                prompt_status="input_required",
            )
        finding = payload.get("finding")
        evidence = payload.get("evidence")
        boundary = payload.get("boundary")
        if not isinstance(finding, Mapping) or not isinstance(evidence, Mapping) or not isinstance(boundary, Mapping):
            raise _business_error("invalid_input")
        prompt = self.generate_repair_prompt(
            finding, evidence, {**boundary, "snapshot_gid": str(getattr(snapshot, "snapshot_gid"))},
            context=context, request_id=str(payload.get("request_id", "repair-prompt")),
        )
        return self._completed(
            "base.capability_repair_prompt.generate",
            snapshot_gid=str(getattr(snapshot, "snapshot_gid")),
            prompt={"prompt_hash": prompt.prompt_hash, "redacted_summary": prompt.redacted_summary},
            prompt_status="generated",
        )

    def base_capability_scan_run(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        self._idempotency(payload)
        if self._scanner is None:
            raise _business_error("governance_dependency_unavailable")
        code_revision = _required_text(payload, "code_revision")
        try:
            document = self._scanner.scan(code_revision)
            snapshot = self._persist_scanned_snapshot(document)
        except CapabilityBusinessError:
            raise
        except Exception as exc:
            raise _business_error("governance_dependency_unavailable") from exc
        return self._completed(
            "base.capability_scan.run",
            snapshot_gid=str(getattr(snapshot, "snapshot_gid")),
            scan_run_gid=str(getattr(snapshot, "scan_run_gid", "")),
        )

    def base_capability_test_run(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        return self._start_and_execute(
            "base.capability_test.run", payload, context, kind="test",
            runner=self._test_runner,
        )

    def base_capability_proposal_submit(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        self._require_workflow_persistence()
        key = self._idempotency(payload)
        try:
            if payload.get("proposal_gid") is not None or payload.get("target_gid") is not None:
                proposal = self._proposals.submit(
                    _payload_gid(payload, "proposal_gid", "target_gid"),
                    expected_row_version=_row_version(payload),
                    idempotency_key=f"proposal-submit:{key}",
                )
            else:
                proposal = self._proposals.detect(
                    capability_id=_required_text(payload, "capability_id"),
                    capability_version_gid=_payload_gid(payload, "capability_version_gid"),
                    base_snapshot_gid=_payload_gid(payload, "base_snapshot_gid"),
                    previous_hash=_required_text(payload, "previous_hash"),
                    proposed_descriptor_hash=_required_text(payload, "proposed_descriptor_hash"),
                    evidence_hash=_required_text(payload, "evidence_hash"),
                    submitted_by_gid=_mutation_actor(context),
                    idempotency_key=f"proposal-detect:{key}",
                )
                draft = self._proposals.transition(
                    proposal.proposal_gid, "draft", expected_row_version=proposal.row_version,
                    idempotency_key=f"proposal-draft:{key}",
                )
                proposal = self._proposals.submit(
                    draft.proposal_gid, expected_row_version=draft.row_version,
                    idempotency_key=f"proposal-submit:{key}",
                )
        except WorkflowError as exc:
            raise _workflow_error(exc) from exc
        return self._accepted("base.capability_proposal.submit", proposal=proposal)

    def base_capability_review_decide(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        self._require_workflow_persistence()
        key = self._idempotency(payload)
        reviewer = ReviewerContext(
            gid=_mutation_actor(context),
            roles=_context_values(context, "active_roles", "governance_roles"),
            permissions=_context_values(context, "permissions", "governance_permissions"),
            owned_domains=_context_values(context, "owned_domains", "governance_owned_domains"),
        )
        try:
            proposal = self._proposals.decide(
                _payload_gid(payload, "proposal_gid", "target_gid"),
                stage=_required_text(payload, "stage"),
                decision=_required_text(payload, "decision"),
                reviewer_context=reviewer,
                expected_row_version=_row_version(payload),
                idempotency_key=f"proposal-review:{key}",
                decided_at=_timestamp(payload, "decided_at"),
            )
        except WorkflowError as exc:
            raise _workflow_error(exc) from exc
        return self._accepted("base.capability_review.decide", proposal=proposal)

    def base_capability_waiver_grant(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        self._require_workflow_persistence()
        key = self._idempotency(payload)
        try:
            waiver = self._waivers.grant(
                finding_gid=_payload_gid(payload, "finding_gid", "target_gid"),
                capability_version_gid=_payload_gid(payload, "capability_version_gid"),
                scope=_required_text(payload, "scope"),
                reason=_required_text(payload, "reason"),
                granted_by_gid=_mutation_actor(context),
                code_hash=_required_text(payload, "code_hash"),
                catalog_hash=_required_text(payload, "catalog_hash"),
                evidence_hash=_required_text(payload, "evidence_hash"),
                starts_at=_timestamp(payload, "starts_at"),
                expires_at=_timestamp(payload, "expires_at"),
                idempotency_key=f"waiver-grant:{key}",
            )
        except WorkflowError as exc:
            raise _workflow_error(exc) from exc
        return self._accepted("base.capability_waiver.grant", waiver=waiver)

    def base_capability_waiver_revoke(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        self._require_workflow_persistence()
        key = self._idempotency(payload)
        try:
            waiver = self._waivers.revoke(
                _payload_gid(payload, "waiver_gid", "target_gid"),
                expected_row_version=_row_version(payload),
                idempotency_key=f"waiver-revoke:{key}",
                revoked_at=_timestamp(payload, "revoked_at"),
            )
        except (KeyError, WorkflowError) as exc:
            if isinstance(exc, KeyError):
                raise _business_error("resource_not_found") from exc
            raise _workflow_error(exc) from exc
        return self._accepted("base.capability_waiver.revoke", waiver=waiver)

    def base_capability_release_gate_evaluate(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        self._require_workflow_persistence()
        key = self._idempotency(payload)
        candidate = self._release_candidate(payload)
        evidence = self._load_release_evidence(candidate, payload)
        try:
            report = self._release_gate.evaluate(
                candidate,
                available=evidence["available"],
                test_status=evidence["test_status"],
                findings=evidence["findings"],
                stale_evidence=evidence["stale_evidence"],
                waivers=evidence["waivers"],
                approvals_complete=evidence["approvals_complete"],
                data_complete=evidence["data_complete"],
                evidence_hash=evidence["evidence_hash"],
                idempotency_key=f"release-gate:{key}",
                evaluated_by_gid=_mutation_actor(context),
            )
        except ReleaseGateError as exc:
            raise _workflow_error(exc) from exc
        return self._completed("base.capability_release_gate.evaluate", release=report)

    def _release_candidate(self, payload: Mapping[str, Any]) -> ReleaseCandidate:
        """Resolve a target-only UI request against the pinned snapshot.

        Code/catalog identities come from the service-owned snapshot when the
        caller omits them.  A test-run resolver is likewise service-owned;
        without one, the zero sentinel guarantees a fail-closed report rather
        than inventing a run identity from request data.
        """
        snapshot_gid = _payload_gid(payload, "snapshot_gid", "target_gid")
        snapshot = None
        if self._store is not None and hasattr(self._store, "get_snapshot"):
            try:
                snapshot = self._store.get_snapshot(snapshot_gid)
            except Exception:
                snapshot = None
        document = getattr(snapshot, "document", None) if snapshot is not None else None
        code_revision = str(payload.get("code_revision", "")).strip() or str(getattr(document, "code_revision", "")).strip()
        product_catalog_release_id = str(payload.get("product_catalog_release_id", "")).strip() or str(getattr(document, "product_release_id", "")).strip()
        if not code_revision or not product_catalog_release_id:
            raise _business_error("invalid_input")
        test_run_value = payload.get("test_run_gid")
        if test_run_value is None and snapshot is not None and self._release_evidence_port is not None:
            resolver = getattr(self._release_evidence_port, "resolve_test_run_gid", None)
            if callable(resolver):
                try:
                    test_run_value = resolver(snapshot)
                except Exception:
                    test_run_value = None
        try:
            test_run_gid = _gid(test_run_value, field="test_run_gid") if test_run_value is not None else 0
        except CapabilityBusinessError:
            test_run_gid = 0
        return ReleaseCandidate(code_revision, product_catalog_release_id, snapshot_gid, test_run_gid)

    def _load_release_evidence(self, candidate: ReleaseCandidate, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Load all release inputs from service-owned authority, failing closed.

        ``payload`` is accepted only for backwards-compatible diagnostic
        blockers when no authority is configured.  It is never used to make a
        release pass.  A configured port must return a complete, pinned
        evidence record; partial or mismatched records are treated as an
        unavailable governance dependency.
        """
        fallback = {
            "available": False,
            # Preserve the useful distinction in existing diagnostics while
            # forcing the dependency blocker that prevents a caller-supplied
            # all-green payload from becoming a signed pass.
            "test_status": str(payload.get("test_status", "")) or None,
            "findings": (),
            "stale_evidence": True,
            "waivers": (),
            "approvals_complete": False,
            "data_complete": False,
            "evidence_hash": "",
        }
        # These caller values may enrich a fail-closed diagnostic, but the
        # forced ``available=False`` below means they can never authorize a
        # pass.  Keeping them preserves actionable legacy blocker details.
        try:
            fallback.update(
                findings=_items(payload, "findings"),
                stale_evidence=_optional_bool(payload, "stale_evidence", default=True),
                waivers=_items(payload, "waivers"),
                approvals_complete=_optional_bool(payload, "approvals_complete", default=False),
                data_complete=_optional_bool(payload, "data_complete", default=False) and bool(str(payload.get("evidence_hash", "")).strip()),
                evidence_hash=str(payload.get("evidence_hash", "")).strip(),
            )
        except CapabilityBusinessError:
            pass
        if self._store is None or not hasattr(self._store, "get_snapshot"):
            return fallback
        try:
            snapshot = self._store.get_snapshot(candidate.snapshot_gid)
        except Exception:
            return fallback
        document = getattr(snapshot, "document", None) if snapshot is not None else None
        if document is None:
            return fallback
        if (
            str(getattr(document, "code_revision", "")) != candidate.code_revision
            or str(getattr(document, "product_release_id", "")) != candidate.product_catalog_release_id
        ):
            return fallback
        port = self._release_evidence_port
        if port is None:
            return fallback
        loader = getattr(port, "load_release_evidence", None)
        if not callable(loader):
            return fallback
        try:
            evidence = loader(candidate, snapshot)
        except Exception:
            return fallback
        if not isinstance(evidence, Mapping):
            return fallback
        required = {
            "snapshot_gid", "test_run_gid", "code_revision", "product_catalog_release_id",
            "snapshot_hash", "test_status", "findings", "stale_evidence", "waivers",
            "approvals_complete", "data_complete", "evidence_hash",
        }
        if not required.issubset(evidence):
            return fallback
        if (
            str(evidence.get("snapshot_gid")) != str(candidate.snapshot_gid)
            or str(evidence.get("test_run_gid")) != str(candidate.test_run_gid)
            or str(evidence.get("code_revision")) != candidate.code_revision
            or str(evidence.get("product_catalog_release_id")) != candidate.product_catalog_release_id
            or str(evidence.get("snapshot_hash")) != str(getattr(document, "snapshot_hash", ""))
        ):
            return fallback
        try:
            findings = _items(evidence, "findings")
            waivers = _items(evidence, "waivers")
            test_status = str(evidence["test_status"]).strip() or None
            stale_evidence = evidence["stale_evidence"]
            approvals_complete = evidence["approvals_complete"]
            data_complete = evidence["data_complete"]
            evidence_hash = str(evidence["evidence_hash"]).strip()
            if not isinstance(stale_evidence, bool) or not isinstance(approvals_complete, bool) or not isinstance(data_complete, bool):
                return fallback
            if not evidence_hash:
                return fallback
        except (CapabilityBusinessError, TypeError, ValueError):
            return fallback
        return {
            "available": True,
            "test_status": test_status,
            "findings": findings,
            "stale_evidence": stale_evidence,
            "waivers": waivers,
            "approvals_complete": approvals_complete,
            "data_complete": data_complete,
            "evidence_hash": evidence_hash,
        }

    def run_analysis(self, snapshot_gid: str | int) -> Any:
        """Execute only the snapshot that was pinned when the run was queued."""
        snapshot = self._snapshot({"target_gid": str(snapshot_gid)})
        if self._analysis_runner is None:
            raise _business_error("governance_dependency_unavailable")
        return self._invoke_port(
            self._analysis_runner, snapshot=snapshot, payload={}, context=None,
            kind="analysis", run_gid=str(snapshot_gid), request=AnalysisRequest(),
        )

    async def review_advisory(self, package: Mapping[str, Any], *, context: object, request_id: str) -> Any:
        """Request non-authoritative advice and retain only audit-safe metadata."""
        if self._advisor is None:
            raise _business_error("resource_not_found")
        identity = getattr(context, "identity", None)
        if identity is None:
            raise _business_error("invalid_input")
        result = await self._advisor.review(package, identity=identity, request_id=request_id)
        self._audit(
            operation="agent_invocation", request_id=request_id, context=context,
            detail={
                "status": result.status,
                "finding_count": len(result.findings),
                "finding_types": tuple(finding.finding_type for finding in result.findings),
            },
        )
        return result

    def generate_repair_prompt(
        self,
        finding: Mapping[str, Any],
        evidence: Mapping[str, Any],
        boundary: Mapping[str, Any],
        *,
        context: object,
        request_id: str,
    ) -> RedactedPrompt:
        """Create a prompt without persisting text; callers must authorize each read."""
        prompt, prompt_text = _render_repair_prompt(finding, evidence, boundary)
        self._prompt_records[prompt.prompt_hash] = prompt.store_record()
        self._prompt_texts[prompt.prompt_hash] = prompt_text
        self._audit(
            operation="prompt_generation", request_id=request_id, context=context,
            detail=prompt.store_record(),
        )
        return prompt

    def read_repair_prompt(self, prompt_hash: str, *, context: object) -> str:
        """Return ephemeral text only after service-owned governance authorization."""
        if not self._can_read_repair_prompt(context):
            raise PromptAuthorizationError("prompt_access_denied")
        prompt_text = self._prompt_texts.get(str(prompt_hash))
        if prompt_text is None:
            raise _business_error("resource_not_found")
        return prompt_text

    @property
    def prompt_records(self) -> Mapping[str, Mapping[str, str]]:
        """Return persistence-safe prompt metadata only, never repair text."""
        return {key: dict(value) for key, value in self._prompt_records.items()}

    def _start_and_execute(
        self,
        capability_id: str,
        payload: Mapping[str, Any],
        context: object,
        *,
        kind: str,
        runner: Any | None,
    ) -> dict[str, Any]:
        """Pin a snapshot and execute through the service-owned worker port.

        Governance operations must never return an accepted no-op.  The test
        profile may provide either the leased worker facade (``run_once``) or a
        queue adapter (``submit``/``enqueue``); without both a caller receives a
        dependency error and no run record is created.
        """
        if runner is None or self._worker is None:
            raise _business_error("governance_dependency_unavailable")
        key = self._idempotency(payload)
        snapshot = self._snapshot(payload)
        snapshot_gid = str(getattr(snapshot, "snapshot_gid"))
        run_key = (kind, snapshot_gid, key)
        run = self._runs.get(run_key)
        if run is not None:
            return self._accepted(
                capability_id, run_gid=run.run_gid, snapshot_gid=run.snapshot_gid,
                run_status=run.status,
            )
        run = GovernedRun(str(self._next_run_gid), snapshot_gid, kind, _context_user(context), key)
        self._next_run_gid += 1
        self._runs[run_key] = run

        def execute(heartbeat: Any | None = None) -> Any:
            return self._invoke_port(
                runner, snapshot=snapshot, payload=payload, context=context,
                kind=kind, run_gid=run.run_gid, request=AnalysisRequest(),
                heartbeat=heartbeat,
            )

        try:
            completed = self._run_worker(kind, run.run_gid, execute)
        except CapabilityBusinessError:
            self._runs[run_key] = replace(run, status="failed")
            raise
        except Exception as exc:
            self._runs[run_key] = replace(run, status="failed")
            raise _business_error("governance_dependency_unavailable") from exc
        if completed is False:
            self._runs[run_key] = replace(run, status="failed")
            raise _business_error("governance_worker_failed")
        status = "completed" if completed is True else "queued"
        self._runs[run_key] = replace(run, status=status)
        return self._accepted(
            capability_id, run_gid=run.run_gid, snapshot_gid=run.snapshot_gid,
            run_status=status,
        )

    def _run_worker(self, kind: str, run_gid: str, execute: Callable[..., Any]) -> bool | None:
        worker = self._worker
        run_once = getattr(worker, "run_once", None)
        if callable(run_once):
            result = run_once(kind, run_gid, execute)
            return bool(result)
        for method_name in ("submit", "enqueue", "start"):
            submit = getattr(worker, method_name, None)
            if callable(submit):
                result = submit(kind, run_gid, execute)
                # Queue adapters may return an operation reference or None;
                # only an explicit False is a failed submission.
                return False if result is False else None
        if callable(worker):
            result = worker(kind, run_gid, execute)
            return False if result is False else (True if result is True else None)
        raise _business_error("governance_dependency_unavailable")

    @staticmethod
    def _invoke_port(
        port: Any,
        *,
        snapshot: Any,
        payload: Mapping[str, Any],
        context: object | None,
        kind: str,
        run_gid: str,
        request: Any,
        heartbeat: Any | None = None,
    ) -> Any:
        """Call a bounded injected port without allowing arbitrary arguments."""
        method = port
        for name in ("run", "execute", "invoke"):
            candidate = getattr(port, name, None)
            if callable(candidate):
                method = candidate
                break
        if not callable(method):
            raise _business_error("governance_dependency_unavailable")
        try:
            signature = inspect.signature(method)
        except (TypeError, ValueError) as exc:
            raise _business_error("governance_dependency_unavailable") from exc
        values = {
            # The historical analysis port consumes the immutable document;
            # a port that needs persistence metadata can request the explicit
            # ``snapshot_record`` name instead.
            "snapshot": getattr(snapshot, "document", snapshot),
            "snapshot_record": snapshot,
            "document": getattr(snapshot, "document", None),
            "payload": payload,
            "context": context,
            "kind": kind,
            "run_gid": run_gid,
            "request": request,
            "heartbeat": heartbeat,
        }
        kwargs: dict[str, Any] = {}
        positional: list[Any] = []
        has_var_kwargs = any(item.kind == inspect.Parameter.VAR_KEYWORD for item in signature.parameters.values())
        for parameter in signature.parameters.values():
            if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if parameter.name in values:
                if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                    positional.append(values[parameter.name])
                else:
                    kwargs[parameter.name] = values[parameter.name]
            elif parameter.default is inspect.Parameter.empty:
                raise _business_error("governance_dependency_unavailable")
        if has_var_kwargs:
            for name, value in values.items():
                kwargs.setdefault(name, value)
        return method(*positional, **kwargs)

    def _persist_scanned_snapshot(self, document: Any) -> Any:
        if self._store is None:
            raise _business_error("governance_dependency_unavailable")
        for method_name in ("import_snapshot", "save_snapshot"):
            persist = getattr(self._store, method_name, None)
            if callable(persist):
                snapshot = persist(document)
                if snapshot is None:
                    raise _business_error("governance_dependency_unavailable")
                return snapshot
        raise _business_error("governance_dependency_unavailable")

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

    def _next_governance_gid(self) -> int:
        gid = self._next_governance_gid_value
        self._next_governance_gid_value += 1
        return gid

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
        entries_loader = getattr(self._store, "list_entries", None)
        if callable(entries_loader):
            try:
                return tuple(entries_loader())
            except Exception:
                return ()
        # Compatibility for legacy unit-test doubles.  Production stores are
        # required to implement GovernanceStore.list_entries and therefore do
        # not expose or depend on a private snapshot dictionary.
        snapshots = getattr(self._store, "_snapshots", None)
        if isinstance(snapshots, Mapping):
            return tuple(entry for snapshot in snapshots.values() for entry in getattr(snapshot, "entries", ()))
        return ()

    def _latest_snapshot(self) -> Any | None:
        if self._store is None:
            return None
        loader = getattr(self._store, "latest_snapshot", None)
        if callable(loader):
            try:
                return loader()
            except Exception:
                return None
        # Compatibility for legacy unit-test doubles; never used by the
        # Memory/SQL GovernanceStore implementations.
        snapshots = getattr(self._store, "_snapshots", None)
        return snapshots[max(snapshots)] if isinstance(snapshots, Mapping) and snapshots else None

    @staticmethod
    def _bounded_limit(value: Any) -> int:
        try:
            return min(max(1, int(value)), _MAX_SEARCH)
        except (TypeError, ValueError) as exc:
            raise _business_error("invalid_input") from exc

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _proposal_records(self) -> tuple[dict[str, Any], ...]:
        """Project the in-process or workflow-port proposal collection safely."""
        source = self._proposals
        list_method = getattr(source, "list", None)
        if callable(list_method):
            try:
                values = tuple(list_method())
            except Exception:
                values = ()
        else:
            values = tuple(getattr(source, "_proposals", {}).values()) if isinstance(getattr(source, "_proposals", None), Mapping) else ()
        records: list[dict[str, Any]] = []
        for proposal in values[:_MAX_SEARCH]:
            capability_id = str(getattr(proposal, "capability_id", ""))
            records.append({
                "proposal_gid": str(getattr(proposal, "proposal_gid", "")),
                "capability_id": capability_id,
                "capability_version_gid": str(getattr(proposal, "capability_version_gid", "")),
                "base_snapshot_gid": str(getattr(proposal, "base_snapshot_gid", "")),
                "previous_hash": str(getattr(proposal, "previous_hash", "")),
                "proposed_descriptor_hash": str(getattr(proposal, "proposed_descriptor_hash", "")),
                "evidence_hash": str(getattr(proposal, "evidence_hash", "")),
                "submitted_by_gid": str(getattr(proposal, "submitted_by_gid", "")),
                "status": str(getattr(proposal, "status", "detected")),
                "row_version": str(getattr(proposal, "row_version", "1")),
                "domain": capability_id.split(".", 1)[0] if "." in capability_id else "base",
                "reviews": tuple(self._review_record(review) for review in getattr(proposal, "reviews", ()))[:20],
            })
        return tuple(records)

    @staticmethod
    def _review_record(review: Any) -> dict[str, Any]:
        return {
            "review_gid": str(getattr(review, "review_gid", "")),
            "review_stage": str(getattr(review, "review_stage", "")),
            "decision": str(getattr(review, "decision", "")),
            "reviewer_gid": str(getattr(review, "reviewer_gid", "")),
        }

    def _load_findings(self, snapshot: Any, payload: Mapping[str, Any], context: object) -> tuple[Any, ...]:
        loader = getattr(self._store, "get_findings", None) if self._store is not None else None
        if callable(loader):
            try:
                return tuple(loader(int(getattr(snapshot, "snapshot_gid"))) or ())[:_MAX_SEARCH]
            except Exception:
                return ()
        if self._analysis_runner is None:
            return ()
        try:
            analysis = self._invoke_port(
                self._analysis_runner, snapshot=snapshot, payload=payload, context=context,
                kind="analysis", run_gid=str(getattr(snapshot, "snapshot_gid")),
                request=AnalysisRequest(),
            )
            return self._finding_records(snapshot, getattr(analysis, "findings", ()))
        except Exception:
            return ()

    def _audit_events(self) -> tuple[Any, ...]:
        sink = self._audit_sink
        if sink is None:
            return ()
        events = getattr(sink, "events", None)
        if events is not None:
            try:
                return tuple(events)[-500:]
            except Exception:
                return ()
        recent = getattr(sink, "recent", None)
        if callable(recent):
            try:
                return tuple(recent(500))
            except Exception:
                return ()
        return ()

    @staticmethod
    def _audit_record(event: Any) -> dict[str, Any]:
        if isinstance(event, Mapping):
            get = event.get
        else:
            get = lambda name, default=None: getattr(event, name, default)
        detail = get("detail", {})
        if not isinstance(detail, Mapping):
            detail = {}
        allowed_detail = {
            "status", "capability_id", "before_status", "after_status", "finding_gid",
            "conclusion", "blockers", "prompt_hash", "finding_count", "finding_types",
        }
        safe_detail: dict[str, Any] = {}
        for key, value in tuple(detail.items())[:50]:
            name = str(key)
            if name.lower() in {"token", "password", "secret", "credential", "authorization", "cookie"} or name not in allowed_detail:
                continue
            if name in {"blockers", "finding_types"}:
                if isinstance(value, (list, tuple)):
                    safe_detail[name] = [str(item)[:255] for item in value[:200]]
                continue
            if name == "finding_count":
                try:
                    safe_detail[name] = min(max(0, int(value)), 5000)
                except (TypeError, ValueError):
                    continue
            else:
                safe_detail[name] = str(value)[:512]

        def text_value(name: str, fallback: Any = None) -> str | None:
            value = get(name, fallback)
            if value is None:
                return None
            normalized = str(value).strip()
            return normalized or None

        capability_id = text_value("capability_id", detail.get("capability_id"))
        operation = text_value("operation", get("event_type"))
        return {
            "audit_event_gid": str(get("audit_event_gid", get("gid", "0"))),
            "operation": operation,
            "capability_id": capability_id,
            "event_type": text_value("event_type", operation),
            "actor_gid": text_value("actor_gid", get("user_gid")),
            "request_gid": text_value("request_gid", get("request_id")),
            "status": text_value("status", "recorded"),
            "occurred_at": text_value("occurred_at", get("created_at")),
            "detail": safe_detail,
        }

    def _finding_records(self, snapshot: Any, findings: Any) -> tuple[dict[str, Any], ...]:
        """Project deterministic candidates into read-only, UI-safe records."""
        entries = {
            (str(getattr(entry, "capability_id", "")), int(getattr(entry, "major_version", 0))): str(getattr(entry, "capability_version_gid", ""))
            for entry in getattr(snapshot, "entries", ())
        }
        domains = {
            (str(getattr(entry, "capability_id", "")), int(getattr(entry, "major_version", 0))): str(getattr(entry, "owner_domain", ""))
            for entry in getattr(snapshot, "entries", ())
        }
        records: list[dict[str, Any]] = []
        for candidate in tuple(findings or ())[:_MAX_SEARCH]:
            code = str(getattr(candidate, "code", ""))
            fingerprint = str(getattr(candidate, "fingerprint", ""))
            if not code or not fingerprint:
                continue
            finding_gid = self._finding_gids.get(fingerprint)
            if finding_gid is None:
                finding_gid = self._next_governance_gid()
                self._finding_gids[fingerprint] = finding_gid
            subjects = tuple(getattr(candidate, "subjects", ()))
            subject_gids = tuple(
                entries[key] for subject in subjects
                if (key := (str(getattr(subject, "capability_id", "")), int(getattr(subject, "major_version", 0)))) in entries
            )
            finding_domains = tuple(sorted({domains[key] for subject in subjects if (key := (str(getattr(subject, "capability_id", "")), int(getattr(subject, "major_version", 0)))) in domains and domains[key]}))
            records.append({
                "finding_gid": str(finding_gid), "code": code,
                "severity": str(getattr(candidate, "severity", "warning")), "status": "open",
                "fingerprint": fingerprint,
                "remediation_boundary": str(getattr(candidate, "remediation_boundary", "")),
                "subject_version_gids": subject_gids,
                "domains": finding_domains,
                "evidence": tuple(str(value) for value in getattr(candidate, "evidence_keys", ())[:200]),
            })
        return tuple(records)

    def _audit(self, *, operation: str, request_id: str, context: object, detail: Mapping[str, Any]) -> None:
        if self._audit_sink is None:
            return
        self._audit_sink.append(
            operation=operation,
            entity_gid=None,
            actor_gid=_context_user(context),
            request_gid=request_id,
            detail=self._audit_detail(operation, detail),
            idempotency_key=f"{operation}:{request_id}",
        )

    @staticmethod
    def _can_read_repair_prompt(context: object) -> bool:
        principal = str(getattr(context, "user_gid", "") or getattr(context, "actor_gid", "")).strip()
        permissions = getattr(context, "governance_permissions", ())
        if not principal or _PROMPT_READ_PERMISSION not in {str(item) for item in permissions}:
            return False
        delegation = getattr(context, "delegation", None)
        if delegation is None:
            return True
        scopes = delegation.get("capability_scopes", ()) if isinstance(delegation, Mapping) else getattr(delegation, "capability_scopes", ())
        return _PROMPT_READ_PERMISSION in {str(item) for item in scopes}

    @staticmethod
    def _audit_detail(operation: str, detail: Mapping[str, Any]) -> dict[str, Any]:
        """Audit only fixed metadata; discard summary/payload fields even if supplied."""
        if operation == "prompt_generation":
            prompt_hash = str(detail.get("prompt_hash", ""))
            return {"prompt_hash": prompt_hash} if prompt_hash.startswith("sha256:") and len(prompt_hash) == 71 else {}
        if operation == "agent_invocation":
            allowed = {"duplicate", "semantic_overlap", "conflict", "gap", "non_atomic_facade", "lifecycle_pair_gap"}
            finding_types = tuple(str(value) for value in detail.get("finding_types", ()) if str(value) in allowed)
            return {
                "status": "candidate" if detail.get("status") == "candidate" else "invalid",
                "finding_count": min(max(0, int(detail.get("finding_count", 0))), 5000),
                "finding_types": finding_types,
            }
        return {}

    @staticmethod
    def _idempotency(payload: Mapping[str, Any]) -> str:
        value = str(payload.get("idempotency_key", "")).strip()
        if not value:
            raise _business_error("idempotency_conflict")
        return value

    def _require_workflow_persistence(self) -> None:
        if self._workflow_persistence_required:
            raise _business_error("governance_persistence_unavailable")

    @staticmethod
    def _completed(capability_id: str, **data: Any) -> dict[str, Any]:
        return {"capability_id": capability_id, "status": "completed", **data}

    @staticmethod
    def _accepted(capability_id: str, **data: Any) -> dict[str, Any]:
        return {"capability_id": capability_id, "status": "accepted", **data}


__all__ = ["CapabilityGovernanceService", "GovernedRun"]
