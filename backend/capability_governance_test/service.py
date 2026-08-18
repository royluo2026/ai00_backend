"""Bounded service boundary for the test-only governance capability extension."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
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
        analysis_runner: Callable[..., Any] = run_deterministic_analysis,
        advisor: GovernanceAdvisorPort | None = None,
        audit_sink: Any | None = None,
        proposal_service: ProposalService | None = None,
        waiver_service: WaiverService | None = None,
        release_gate: ReleaseGate | None = None,
        release_evidence_port: Any | None = None,
    ) -> None:
        self._store = store
        self._scanner = scanner
        self._analysis_runner = analysis_runner
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
        self._release_gate = release_gate or ReleaseGate(
            next_gid=self._next_governance_gid, audit_sink=audit_sink,
        )

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
                analysis = self._analysis_runner(getattr(snapshot, "document"), AnalysisRequest())
                findings = self._finding_records(snapshot, getattr(analysis, "findings", ()))
        query = str(payload.get("query", "")).strip().lower()
        if query:
            findings = tuple(item for item in findings if query in str(
                getattr(item, "code", item.get("code", "") if isinstance(item, Mapping) else "")
            ).lower() or query in str(
                getattr(item, "fingerprint", item.get("fingerprint", "") if isinstance(item, Mapping) else "")
            ).lower())
        return self._completed("base.capability_finding.search", findings=tuple(findings[:limit]))

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
        return self._analysis_runner(getattr(snapshot, "document"), AnalysisRequest())

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
        snapshots = getattr(self._store, "_snapshots", {})
        if isinstance(snapshots, Mapping):
            return tuple(entry for snapshot in snapshots.values() for entry in getattr(snapshot, "entries", ()))
        snapshot = getattr(self._store, "latest_snapshot", lambda: None)()
        return tuple(getattr(snapshot, "entries", ())) if snapshot is not None else ()

    def _latest_snapshot(self) -> Any | None:
        if self._store is None:
            return None
        snapshots = getattr(self._store, "_snapshots", {})
        if isinstance(snapshots, Mapping) and snapshots:
            return snapshots[max(snapshots)]
        loader = getattr(self._store, "latest_snapshot", None)
        return loader() if callable(loader) else None

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

    @staticmethod
    def _completed(capability_id: str, **data: Any) -> dict[str, Any]:
        return {"capability_id": capability_id, "status": "completed", **data}

    @staticmethod
    def _accepted(capability_id: str, **data: Any) -> dict[str, Any]:
        return {"capability_id": capability_id, "status": "accepted", **data}


__all__ = ["CapabilityGovernanceService", "GovernedRun"]
