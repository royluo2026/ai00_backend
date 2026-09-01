"""Bounded service boundary for the test-only governance capability extension."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import inspect
from typing import Any
import re

from backend.capabilities.models_next import CapabilityBusinessError
from backend.capability_v2.contracts import ConsumerIdentity, ConsumerType
from backend.domain_ports.capability_governance_ai import GovernanceAdvisorPort

from .ai_advisory import AdvisoryContractError, AdvisoryResult
from .analysis import AnalysisRequest, run_deterministic_analysis
from .business_relations import analyze_relationships
from .prompting import PromptAuthorizationError, RedactedPrompt, _render_repair_prompt
from .redaction import redact
from .release_gate import ReleaseCandidate, ReleaseGate, ReleaseGateError
from .workflow import ProposalService, ReviewerContext, WaiverService, WorkflowError


_MAX_SEARCH = 200
_MAX_HEALTH_FINDINGS = 5000
_MAX_GRAPH_DEPTH = 4
_MAX_GRAPH_NODES = 500
_PROMPT_READ_PERMISSION = "base.capability_repair_prompt.read"
_DEFAULT_PORT = object()
_MAX_OFFSET = 100000


# Finding codes are the machine-stable NOK categories.  Keep their explanations
# in the governance service so every consumer (UI, agent and audit export) sees
# the same fail-closed rationale without parsing implementation details.
_FINDING_REASON_TEXT = {
    "provider_missing": "目录声明了该 Capability，但没有找到对应的 Provider 注册或实现证据。",
    "gap": "该 Capability 没有可验证的实现绑定，无法证明它可以执行。",
    "exposure_without_capability": "发现公开入口，但没有找到它通过已声明 Capability 或 Gateway 暴露的证据。",
    "provider_without_descriptor": "发现 Provider 实现，但没有找到对应的 Catalog 描述。",
    "required_test_missing": "没有找到覆盖该 Capability 的测试用例证据。",
    "repository_table_migration_mismatch": "Repository 写入的表没有找到对应迁移声明。",
    "transaction_participant_missing": "强写 Capability 没有找到事务参与者证据。",
    "permission_policy_mismatch": "Provider 的权限策略与 Catalog 声明不一致。",
    "confirmation_policy_mismatch": "Provider 的确认策略与 Catalog 声明不一致。",
    "catalog_schema_drift": "Provider 的输入、输出或错误 Schema 与 Catalog 不一致。",
    "lifecycle_incompatibility": "Provider 生命周期状态与 Catalog 不兼容。",
    "duplicate": "跨域 Capability 的合约与业务效果完全重叠，疑似重复。",
    "semantic_overlap": "跨域 Capability 的业务效果存在重叠，需要确认边界。",
    "cross_domain_conflict": "跨域 Capability 的策略或合约存在冲突。",
    "lifecycle_pair_gap": "没有找到与该 Capability 配套的生命周期操作。",
    "non_atomic_facade": "聚合 Facade 组合多个 Provider，但没有找到事务性证据。",
    "stale_evidence": "当前证据与最新代码、Catalog 或 Snapshot 不一致。",
}


def _finding_reason(code: str) -> str:
    return _FINDING_REASON_TEXT.get(code, f"规则 {code} 判定该治理对象缺少满足发布要求的证据。")[:255]


def _capability_refs(subjects: Any) -> tuple[str, ...]:
    """Return stable capability/version references for an actionable root cause."""
    refs: set[str] = set()
    for subject in tuple(subjects or ()):
        if isinstance(subject, Mapping):
            capability_id = subject.get("capability_id") or subject.get("capabilityId")
            major = subject.get("major_version", subject.get("majorVersion", 0))
        else:
            capability_id = getattr(subject, "capability_id", "")
            major = getattr(subject, "major_version", 0)
        capability_id = str(capability_id or "").strip()
        if not capability_id:
            continue
        try:
            major_value = int(major or 0)
        except (TypeError, ValueError):
            major_value = 0
        refs.add(f"{capability_id}@{major_value}" if major_value else capability_id)
    return tuple(sorted(refs))


def _root_cause_fields(
    code: str, *, subjects: Any = (), evidence: Any = (), record: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Build an actionable key: NOK category + concrete Capability target(s)."""
    record = record or {}
    known_key = str(record.get("root_cause_key", "") or "").strip()
    if known_key:
        known_label = str(record.get("root_cause_label", "") or "").strip()
        return known_key, known_label[:512] if known_label else f"{_finding_reason(code)} · {known_key.split(':', 1)[-1]}"
    refs = _capability_refs(subjects)
    if not refs:
        refs = tuple(str(item).strip() for item in record.get("capability_refs", ()) if str(item).strip())
    if not refs:
        summary = str(record.get("subject_summary", record.get("subjectSummary", "")))
        refs = tuple(f"{match[0]}@{match[1]}" for match in re.findall(r"Capability：([^@、]+)@(\d+)", summary))
    if refs:
        target = "|".join(refs[:20])
        return f"{code}:{target}", f"{_finding_reason(code)} · {target}"
    evidence_values = tuple(str(item).strip() for item in evidence or () if str(item).strip())
    fallback = evidence_values[0][:160] if evidence_values else "unresolved"
    return f"{code}:unresolved:{fallback}", f"{_finding_reason(code)} · 未解析 Capability（{fallback}）"


def _record_value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _business_contract_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _business_contract_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_business_contract_value(item) for item in value]
    values = getattr(value, "__dict__", None)
    if isinstance(values, Mapping):
        return {
            str(key): _business_contract_value(item)
            for key, item in values.items() if not str(key).startswith("_")
        }
    return value


def _root_cause_capability_refs(record: Any, root_key: str = "") -> tuple[str, ...]:
    refs = _capability_refs(_record_value(record, "subjects", ()))
    if not refs:
        refs = tuple(str(value).strip() for value in (_record_value(record, "capability_refs", ()) or ()) if str(value).strip())
    if not refs:
        summary = str(_record_value(record, "subject_summary", _record_value(record, "subjectSummary", "")) or "")
        refs = tuple(f"{match[0]}@{match[1]}" for match in re.findall(r"Capability：([^@、]+)@(\d+)", summary))
    if not refs and ":" in root_key:
        candidate = root_key.split(":", 1)[1]
        if not candidate.startswith("unresolved:"):
            refs = tuple(part for part in candidate.split("|") if part)
    return tuple(dict.fromkeys(refs))[:20]


def _finding_subject_summary(
    snapshot: Any, subjects: tuple[Any, ...], evidence_keys: tuple[Any, ...] = (),
) -> str:
    """Resolve a compact, human-readable subject without exposing raw internals."""
    document = getattr(snapshot, "document", snapshot)
    nodes = {
        str(getattr(node, "canonical_key", "")): node
        for node in getattr(document, "nodes", ())
        if getattr(node, "canonical_key", None)
    }
    labels = {
        "rest_route": "REST 路由", "gateway": "Gateway", "mount_binding": "Mount",
        "agent_tool": "Agent Tool", "mcp_tool": "MCP Tool", "legacy_api": "旧 API",
    }
    parts: list[str] = []
    for subject in subjects[:20]:
        capability_id = str(getattr(subject, "capability_id", "")).strip()
        if capability_id:
            major = int(getattr(subject, "major_version", 0) or 0)
            parts.append(f"Capability：{capability_id}@{major}")
            continue
        evidence_key = str(getattr(subject, "evidence_key", "")).strip()
        node = nodes.get(evidence_key)
        if node is not None:
            node_type = str(getattr(node, "node_type", "入口"))
            label = labels.get(node_type, node_type or "入口")
            symbol = str(getattr(node, "source_symbol", "") or getattr(node, "source_path", "") or evidence_key)
            parts.append(f"{label}：{symbol}")
        elif evidence_key:
            parts.append(evidence_key)
    for value in evidence_keys[:20]:
        evidence_key = str(value).strip()
        node = nodes.get(evidence_key)
        if node is None:
            continue
        node_type = str(getattr(node, "node_type", "入口"))
        label = labels.get(node_type, node_type or "入口")
        symbol = str(getattr(node, "source_symbol", "") or getattr(node, "source_path", "") or evidence_key)
        parts.append(f"{label}：{symbol}")
    return "、".join(dict.fromkeys(parts))[:255] or "未解析主体"


def _enrich_finding_record(snapshot: Any, item: Any) -> dict[str, Any]:
    """Backfill explanations for findings loaded from a persisted store."""
    if isinstance(item, Mapping):
        record = dict(item)
    else:
        record = dict(getattr(item, "__dict__", {}))
        if not record:
            for field in (
                "finding_gid", "code", "finding_type", "severity", "status", "fingerprint",
                "remediation_boundary", "subject_version_gids", "domains", "evidence",
                "reason_code", "reason", "subject_summary",
                "root_cause_key", "root_cause_label", "root_cause_count", "capability_refs",
                "subjects", "evidence_keys",
            ):
                if hasattr(item, field):
                    record[field] = getattr(item, field)
    code = str(record.get("code") or record.get("finding_type") or record.get("findingType") or "finding")
    if not str(record.get("reason_code", "")).strip():
        record["reason_code"] = code
    if not str(record.get("reason", "")).strip():
        record["reason"] = _finding_reason(str(record["reason_code"]))
    subjects = tuple(record.get("subjects", ()) or ())
    evidence = tuple(record.get("evidence", record.get("evidence_keys", ())) or ())
    if subjects and not record.get("capability_refs"):
        record["capability_refs"] = _capability_refs(subjects)
    if subjects and not record.get("domains"):
        domain_by_capability = {
            (str(getattr(entry, "capability_id", "")), int(getattr(entry, "major_version", 0) or 0)): str(getattr(entry, "owner_domain", ""))
            for entry in getattr(getattr(snapshot, "document", snapshot), "entries", ())
        }
        # Some stores expose entries on the snapshot itself; use that shape too.
        domain_by_capability.update({
            (str(getattr(entry, "capability_id", "")), int(getattr(entry, "major_version", 0) or 0)): str(getattr(entry, "owner_domain", ""))
            for entry in getattr(snapshot, "entries", ())
        })
        record["domains"] = tuple(sorted({
            domain_by_capability.get((str(getattr(subject, "capability_id", "")), int(getattr(subject, "major_version", 0) or 0)), "")
            for subject in subjects
            if domain_by_capability.get((str(getattr(subject, "capability_id", "")), int(getattr(subject, "major_version", 0) or 0)), "")
        }))
    if not str(record.get("subject_summary", record.get("subjectSummary", ""))).strip():
        record["subject_summary"] = _finding_subject_summary(snapshot, subjects, evidence)
    key, label = _root_cause_fields(str(record["reason_code"]), subjects=subjects, evidence=evidence, record=record)
    record["root_cause_key"] = str(record.get("root_cause_key") or key)
    record["root_cause_label"] = str(record.get("root_cause_label") or label)[:512]
    return record


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


def _definition_hash(payload: Mapping[str, Any], field: str = "definition_hash") -> str:
    value = payload.get(field)
    if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise _business_error("review_subject_hash_invalid")
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
            business_review_sink=self._save_business_review,
            business_review_store=store,
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
        # SqlGovernanceStore is itself the minimal durable workflow boundary:
        # ProposalService uses its CAS/read methods directly.  Requiring a
        # wrapper port here made the default SQL bootstrap reject operations
        # even though the durable implementation was already present.
        self._workflow_port = workflow_port or (store if getattr(store, "persistent", False) else None)
        self._workflow_persistence_required = bool(getattr(store, "persistent", False)) and self._workflow_port is None
        if self._workflow_port is not None:
            # A persistent adapter may expose the durable state machines
            # directly.  Keeping this as a narrow port avoids coupling the
            # service to a particular SQL driver or schema implementation.
            self._proposals = getattr(self._workflow_port, "proposal_service", self._proposals)
            self._waivers = getattr(self._workflow_port, "waiver_service", self._waivers)
        self._release_gate = release_gate or ReleaseGate(
            next_gid=self._next_governance_gid, audit_sink=audit_sink,
        )
        if self._workflow_port is not None:
            self._release_gate = getattr(self._workflow_port, "release_gate", self._release_gate)

    def bind_registry_snapshot(self, snapshot: Any) -> None:
        """Bind the registry used by the scanner to the serving registry."""
        if self._scanner is None:
            return
        binder = getattr(self._scanner, "bind_registry_snapshot", None)
        if not callable(binder):
            raise RuntimeError("governance_scanner_registry_binding_unavailable")
        binder(snapshot)

    def base_capability_registry_search(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        limit = self._bounded_limit(payload.get("limit", _MAX_SEARCH))
        offset = self._bounded_offset(payload.get("offset", 0))
        query = str(payload.get("query", "")).strip().lower()
        domain = str(payload.get("domain", "")).strip().lower()
        entries = sorted(self._entries(), key=lambda item: str(getattr(item, "capability_id", "")))
        matches = [
            item for item in entries
            if (not query or query in " ".join(
                str(getattr(item, field, "")) for field in ("capability_id", "capability_version_gid", "business_effect", "owner_domain")
            ).lower())
            and (not domain or domain == str(getattr(item, "owner_domain", getattr(item, "domain", ""))).lower())
        ]
        extension_matches = [
            item for item in matches
            if str(getattr(item, "capability_id", "")).lower().startswith("base.capability_")
        ]
        latest = self._latest_snapshot()
        scanned = {
            (str(getattr(item, "capability_id", "")), int(getattr(item, "major_version", 0) or 0)): item
            for item in getattr(getattr(latest, "document", None), "capabilities", ())
        }
        projected: list[Any] = []
        for item in matches[offset:offset + limit]:
            evidence = scanned.get((
                str(getattr(item, "capability_id", "")), int(getattr(item, "major_version", 0) or 0),
            ))
            if evidence is None:
                projected.append(item)
                continue
            record = dict(item) if isinstance(item, Mapping) else dict(getattr(item, "__dict__", {}))
            record["contract"] = {
                "business_rules": _business_contract_value(getattr(evidence, "business_rules", ())),
                "fingerprint": _business_contract_value(getattr(evidence, "fingerprint", None)),
                "business_layer_evidence": _business_contract_value(getattr(evidence, "business_layer_evidence", {})),
                "business_maturity": _business_contract_value(getattr(evidence, "business_maturity", None)),
            }
            projected.append(record)
        return self._completed(
            "base.capability_registry.search", limit=limit, offset=offset, items=tuple(projected),
            total=len(matches),
            product_capability_total=len(matches) - len(extension_matches),
            governance_extension_capability_total=len(extension_matches),
        )

    def base_capability_governance_snapshot_summary_get(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        """Return a bounded, agent-friendly summary of one verified snapshot.

        The summary groups evidence rows by the actionable root-cause key
        (reason category + concrete Capability) so an agent can triage with one
        read call and then drill into the existing registry/finding APIs.
        """
        snapshot_payload = {"target_gid": payload.get("snapshot_gid")} if payload.get("snapshot_gid") is not None else {}
        snapshot = self._snapshot(snapshot_payload) if snapshot_payload else self._latest_snapshot()
        if snapshot is None:
            raise _business_error("governance_dependency_unavailable")
        limit = self._bounded_limit(payload.get("limit", 50))
        offset = self._bounded_offset(payload.get("offset", 0))
        raw_domains = payload.get("domains", ())
        raw_severities = payload.get("severity", ())
        if isinstance(raw_domains, (str, bytes, Mapping)) or isinstance(raw_severities, (str, bytes, Mapping)):
            raise _business_error("invalid_input")
        domains = {str(value).strip().lower() for value in tuple(raw_domains or ()) if str(value).strip()}
        severities = {str(value).strip().lower() for value in tuple(raw_severities or ()) if str(value).strip()}
        query = str(payload.get("query", "")).strip().lower()
        findings = self._load_findings(snapshot, payload, context, limit=_MAX_HEALTH_FINDINGS)

        def values(item: Any, field: str) -> Any:
            return _record_value(item, field, ())

        filtered: list[Any] = []
        for item in findings:
            item_domains = {str(value).lower() for value in (values(item, "domains") or ())}
            severity = str(values(item, "severity") or "warning").lower()
            code = str(values(item, "reason_code") or values(item, "code") or "finding")
            root_key, root_label = _root_cause_fields(code, evidence=values(item, "evidence"), record=item)
            searchable = " ".join((root_key, root_label, str(values(item, "reason") or ""), str(values(item, "subject_summary") or ""))).lower()
            if domains and not domains.intersection(item_domains):
                continue
            if severities and severity not in severities:
                continue
            if query and query not in searchable:
                continue
            filtered.append(item)

        severity_rank = {"blocking": 4, "critical": 3, "error": 2, "warning": 1, "info": 0}
        groups: dict[str, dict[str, Any]] = {}
        domain_finding_counts: dict[str, int] = {}
        for item in filtered:
            code = str(values(item, "reason_code") or values(item, "code") or "finding")
            evidence = tuple(str(value) for value in (values(item, "evidence") or ()) if str(value).strip())
            root_key, root_label = _root_cause_fields(code, evidence=evidence, record=item)
            severity = str(values(item, "severity") or "warning")
            item_domains = tuple(sorted({str(value) for value in (values(item, "domains") or ()) if str(value).strip()}))
            group = groups.setdefault(root_key, {
                "root_cause_key": root_key, "reason_code": code,
                "root_cause_label": str(values(item, "root_cause_label") or root_label)[:512],
                "capabilities": set(_root_cause_capability_refs(item, root_key)),
                "domains": set(item_domains), "finding_count": 0,
                "severity": severity, "evidence_refs": set(),
            })
            group["finding_count"] += 1
            group["capabilities"].update(_root_cause_capability_refs(item, root_key))
            group["domains"].update(item_domains)
            group["evidence_refs"].update(evidence[:20])
            if severity_rank.get(severity.lower(), 0) > severity_rank.get(str(group["severity"]).lower(), 0):
                group["severity"] = severity
            for domain in item_domains:
                domain_finding_counts[domain] = domain_finding_counts.get(domain, 0) + 1

        entries = tuple(getattr(snapshot, "entries", ()))
        capability_total = sum(
            1 for entry in entries
            if not domains or str(getattr(entry, "owner_domain", getattr(entry, "domain", ""))).lower() in domains
        )
        ordered_groups = sorted(
            groups.values(),
            key=lambda item: (-severity_rank.get(str(item["severity"]).lower(), 0), str(item["root_cause_key"])),
        )
        root_causes = tuple({
            **group,
            "capabilities": tuple(sorted(group["capabilities"]))[:20],
            "domains": tuple(sorted(group["domains"]))[:11],
            "evidence_refs": tuple(sorted(group["evidence_refs"]))[:20],
        } for group in ordered_groups)
        domain_capability_counts: dict[str, int] = {}
        for entry in entries:
            domain = str(getattr(entry, "owner_domain", getattr(entry, "domain", ""))).strip()
            if domain and (not domains or domain.lower() in domains):
                domain_capability_counts[domain] = domain_capability_counts.get(domain, 0) + 1
        domain_summaries = tuple({
            "domain": domain,
            "finding_count": domain_finding_counts.get(domain, 0),
            "capability_count": count,
        } for domain, count in sorted(domain_capability_counts.items()))
        page = root_causes[offset:offset + limit]
        document = getattr(snapshot, "document", snapshot)
        result: dict[str, Any] = {
            "snapshot_gid": str(getattr(snapshot, "snapshot_gid")),
            "capability_total": capability_total,
            "finding_total": len(filtered),
            "root_cause_total": len(root_causes),
            "blocking_total": sum(1 for item in filtered if str(values(item, "severity") or "").lower() == "blocking"),
            "critical_total": sum(1 for item in filtered if str(values(item, "severity") or "").lower() == "critical"),
            "limit": limit, "offset": offset,
            "next_offset": offset + limit if offset + limit < len(root_causes) else None,
            "root_causes": page,
            "domain_summaries": domain_summaries,
        }
        catalog_release = str(getattr(document, "product_release_id", "")).strip()
        snapshot_hash = str(getattr(document, "snapshot_hash", "")).strip()
        if catalog_release:
            result["catalog_release"] = catalog_release
        if snapshot_hash:
            result["snapshot_hash"] = snapshot_hash
        return self._completed("base.capability_governance.snapshot.summary.get", **result)

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
        proposals = self._proposal_records(context=context)
        def matches(item: Mapping[str, Any]) -> bool:
            if domain and domain not in str(item.get("domain", "")).lower():
                return False
            if stage and stage != str(item.get("status", "")).lower():
                return False
            if query and query not in " ".join(str(item.get(field, "")) for field in ("proposal_gid", "capability_id", "status", "domain")).lower():
                return False
            return True
        cursor = str(payload.get("cursor", "")).strip()
        try:
            after_gid = int(cursor) if cursor else 0
        except ValueError as exc:
            raise _business_error("invalid_input") from exc
        selected = tuple(item for item in proposals if matches(item) and int(item["proposal_gid"] or 0) > after_gid)
        page = selected[:limit + 1]
        items = page[:limit]
        return self._completed(
            "base.capability_proposal.search", items=items,
            data={"available": self._workflow_port is not None or not self._workflow_persistence_required,
                  "checked_at": self._now_iso(),
                  "next_cursor": str(items[-1]["proposal_gid"]) if len(page) > len(items) else None},
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
        findings = self._load_findings(snapshot, payload, context, limit=_MAX_HEALTH_FINDINGS)
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
            elif any(severity.lower() in {"blocking", "critical"} for severity in severities):
                status, reason = "blocked", "blocking_findings"
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
        try:
            relation_offset = self._bounded_offset(payload.get("relation_offset", 0))
            relation_limit = self._bounded_limit(payload.get("relation_limit", _MAX_SEARCH))
        except CapabilityBusinessError:
            raise
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
        loader = getattr(self._store, "list_relation_candidates", None) if self._store is not None else None
        if callable(loader):
            candidates = tuple(sorted(
                loader(int(getattr(snapshot, "snapshot_gid"))),
                key=lambda item: (str(getattr(item, "candidate_hash", "")), int(getattr(item, "relation_candidate_gid", 0))),
            ))
            result.update(
                relation_candidates=candidates[relation_offset:relation_offset + relation_limit],
                relation_total=len(candidates), relation_offset=relation_offset, relation_limit=relation_limit,
            )
        else:
            result.update(relation_candidates=(), relation_total=0, relation_offset=relation_offset, relation_limit=relation_limit)
        return result

    def base_capability_finding_search(self, payload: Mapping[str, Any], context: object) -> dict[str, Any]:
        limit = self._bounded_limit(payload.get("limit", _MAX_SEARCH))
        offset = self._bounded_offset(payload.get("offset", 0))
        snapshot = None
        if payload.get("target_gid") is not None:
            snapshot = self._snapshot(payload)
        elif self._store is not None:
            snapshot = self._latest_snapshot()
        findings: tuple[Any, ...] = ()
        if snapshot is not None:
            findings = self._load_findings(
                snapshot, payload, context, limit=_MAX_HEALTH_FINDINGS,
            )
            if not findings and self._analysis_runner is None and self._store is None:
                raise _business_error("governance_dependency_unavailable")
        query = str(payload.get("query", "")).strip().lower()
        domain = str(payload.get("domain", "")).strip().lower()
        severity = str(payload.get("severity", "")).strip().lower()
        status = str(payload.get("status", "")).strip().lower()
        reason_code = str(payload.get("reason_code", "")).strip().lower()
        if query:
            def field(item: Any, name: str) -> Any:
                if isinstance(item, Mapping):
                    return item.get(name, "")
                return getattr(item, name, "")
            findings = tuple(item for item in findings if query in " ".join(
                str(field(item, name)) for name in ("code", "fingerprint", "reason", "root_cause_key", "root_cause_label", "subject_summary")
            ).lower())
        def field(item: Any, name: str) -> Any:
            if isinstance(item, Mapping):
                return item.get(name, "")
            return getattr(item, name, "")
        if domain:
            findings = tuple(item for item in findings if domain in {str(value).lower() for value in (field(item, "domains") or ())})
        if severity:
            findings = tuple(item for item in findings if str(field(item, "severity")).lower() == severity)
        if status:
            findings = tuple(item for item in findings if str(field(item, "status")).lower() == status)
        if reason_code:
            findings = tuple(item for item in findings if str(field(item, "reason_code") or field(item, "code")).lower() == reason_code)
        root_counts: dict[str, int] = {}
        for item in findings:
            record = item if isinstance(item, Mapping) else getattr(item, "__dict__", {})
            code = str(field(item, "reason_code") or field(item, "code") or "finding")
            root_key, root_label = _root_cause_fields(code, evidence=field(item, "evidence"), record=record)
            if isinstance(item, dict):
                item.setdefault("root_cause_key", root_key)
                item.setdefault("root_cause_label", root_label)
            root_counts[root_key] = root_counts.get(root_key, 0) + 1
        projected: list[Any] = []
        for item in findings:
            record = item if isinstance(item, Mapping) else getattr(item, "__dict__", {})
            code = str(field(item, "reason_code") or field(item, "code") or "finding")
            root_key, root_label = _root_cause_fields(code, evidence=field(item, "evidence"), record=record)
            if isinstance(item, dict):
                item["root_cause_key"] = root_key
                item["root_cause_label"] = root_label
                item["root_cause_count"] = root_counts[root_key]
            else:
                projected.append(dict(record, root_cause_key=root_key, root_cause_label=root_label, root_cause_count=root_counts[root_key]))
                continue
            projected.append(item)
        return self._completed(
            "base.capability_finding.search", findings=tuple(projected[offset:offset + limit]),
            total=len(projected), offset=offset, root_cause_total=len(root_counts),
        )

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
            self._persist_relation_candidates(snapshot, document)
        except CapabilityBusinessError:
            raise
        except Exception as exc:
            raise _business_error("governance_dependency_unavailable") from exc
        return self._completed(
            "base.capability_scan.run",
            snapshot_gid=str(getattr(snapshot, "snapshot_gid")),
            scan_run_gid=str(getattr(snapshot, "scan_run_gid", "")),
            scan_status=str(getattr(document, "scan_status", "completed")),
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
                definition_hash = payload.get("definition_hash")
                review_kind = "standard"
                proposed_descriptor_hash = _required_text(payload, "proposed_descriptor_hash")
                if definition_hash is not None:
                    definition_hash = _definition_hash(payload)
                    if proposed_descriptor_hash != definition_hash:
                        raise _business_error("review_subject_hash_mismatch")
                    review_kind = "business_definition"
                proposal = self._proposals.detect(
                    capability_id=_required_text(payload, "capability_id"),
                    capability_version_gid=_payload_gid(payload, "capability_version_gid"),
                    base_snapshot_gid=_payload_gid(payload, "base_snapshot_gid"),
                    previous_hash=_required_text(payload, "previous_hash"),
                    proposed_descriptor_hash=proposed_descriptor_hash,
                    evidence_hash=_required_text(payload, "evidence_hash"),
                    submitted_by_gid=_mutation_actor(context),
                    idempotency_key=f"proposal-detect:{key}",
                    review_kind=review_kind,
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
        try:
            proposal_gid = _payload_gid(payload, "proposal_gid", "target_gid")
            subject = self._proposals.get(proposal_gid)
            if getattr(subject, "review_kind", "standard") == "business_definition":
                reviewer = self._business_reviewer_context(context)
                if "super_admin" not in reviewer.roles:
                    raise WorkflowError("reviewer_not_authorized")
                definition_hash = _definition_hash(payload)
                proposal = self._proposals.decide_business_definition(
                    proposal_gid,
                    reviewer_context=reviewer,
                    definition_hash=definition_hash,
                    current_definition_hash=self._current_business_definition_hash(subject),
                    decision=_required_text(payload, "decision"),
                    decision_reason=_required_text(payload, "decision_reason"),
                    expected_row_version=_row_version(payload),
                    idempotency_key=f"business-review:{key}",
                )
            else:
                if payload.get("definition_hash") is not None or payload.get("decision_reason") is not None:
                    raise _business_error("review_subject_type_invalid")
                reviewer = ReviewerContext(
                    gid=_mutation_actor(context),
                    roles=_context_values(context, "active_roles", "governance_roles"),
                    permissions=_context_values(context, "permissions", "governance_permissions"),
                    owned_domains=_context_values(context, "owned_domains", "governance_owned_domains"),
                )
                proposal = self._proposals.decide(
                    proposal_gid,
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
                static_gate_status=evidence["static_gate_status"],
                static_gate_hash=evidence["static_gate_hash"],
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
            "static_gate_status": None,
            "static_gate_hash": "",
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
            "static_gate_status", "static_gate_hash",
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
            static_gate_status = str(evidence["static_gate_status"]).strip() or None
            static_gate_hash = str(evidence["static_gate_hash"]).strip()
            if not isinstance(stale_evidence, bool) or not isinstance(approvals_complete, bool) or not isinstance(data_complete, bool):
                return fallback
            if not evidence_hash or not static_gate_hash:
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
            "static_gate_status": static_gate_status,
            "static_gate_hash": static_gate_hash,
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
        unavailable = False
        try:
            result = await self._advisor.review(package, identity=identity, request_id=request_id)
            unavailable = result.status == "unavailable"
        except Exception as exc:
            # Advice is optional.  It must never suppress deterministic scan
            # evidence or turn an AI transport failure into a service failure.
            reason = "timeout" if isinstance(exc, TimeoutError) or (
                isinstance(exc, AdvisoryContractError) and str(exc) == "agent_advisory_timeout"
            ) else "failed"
            result = AdvisoryResult(status="unavailable", reason_code=reason)
            unavailable = True
        self._audit(
            operation="agent_invocation", request_id=request_id, context=context,
            detail={
                "status": result.status,
                "reason_code": result.reason_code,
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

    def _persist_relation_candidates(self, snapshot: Any, document: Any) -> tuple[Any, ...]:
        """Persist only reproducible candidates; advisory failures never affect them."""
        if self._store is None:
            return ()
        candidates = analyze_relationships(
            getattr(document, "capabilities", ()), snapshot_gid=int(getattr(snapshot, "snapshot_gid")),
        )
        save = getattr(self._store, "save_relation_candidates", None)
        if callable(save):
            save(candidates)
        loader = getattr(self._store, "list_relation_candidates", None)
        if callable(loader):
            return tuple(loader(int(getattr(snapshot, "snapshot_gid"))))
        return candidates

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
    def _bounded_offset(value: Any) -> int:
        try:
            return min(max(0, int(value)), _MAX_OFFSET)
        except (TypeError, ValueError) as exc:
            raise _business_error("invalid_input") from exc

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _proposal_records(self, *, context: object | None = None) -> tuple[dict[str, Any], ...]:
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
        may_read_business_evidence = context is not None and "super_admin" in self._business_reviewer_context(context).roles
        for proposal in sorted(values, key=lambda item: int(getattr(item, "proposal_gid", 0))):
            capability_id = str(getattr(proposal, "capability_id", ""))
            business = getattr(proposal, "review_kind", "standard") == "business_definition"
            records.append({
                "proposal_gid": str(getattr(proposal, "proposal_gid", "")),
                "capability_id": capability_id,
                "capability_version_gid": str(getattr(proposal, "capability_version_gid", "")),
                "base_snapshot_gid": str(getattr(proposal, "base_snapshot_gid", "")),
                "previous_hash": str(getattr(proposal, "previous_hash", "")),
                "proposed_descriptor_hash": str(getattr(proposal, "proposed_descriptor_hash", "")),
                "proposed_descriptor_hash_label": "business_definition_hash" if business else "descriptor_hash",
                "business_definition_hash": str(getattr(proposal, "proposed_descriptor_hash", "")) if business else None,
                "review_type": "business_definition" if business else "standard",
                "evidence_hash": str(getattr(proposal, "evidence_hash", "")),
                "submitted_by_gid": str(getattr(proposal, "submitted_by_gid", "")),
                "status": str(getattr(proposal, "status", "detected")),
                "row_version": str(getattr(proposal, "row_version", "1")),
                "domain": capability_id.split(".", 1)[0] if "." in capability_id else "base",
                "reviews": tuple(self._review_record(review) for review in getattr(proposal, "reviews", ()))[:20] if may_read_business_evidence or not business else (),
                "review_evidence": self._proposal_business_evidence(proposal) if business and may_read_business_evidence else {},
            })
        return tuple(records)

    @staticmethod
    def _review_record(review: Any) -> dict[str, Any]:
        return {
            "review_gid": str(getattr(review, "review_gid", "")),
            "review_stage": str(getattr(review, "review_stage", "")),
            "decision": str(getattr(review, "decision", "")),
            "reviewer_gid": str(getattr(review, "reviewer_gid", "")),
            "decision_reason": str(getattr(review, "decision_reason", ""))[:2000],
            "review_type": str(getattr(review, "review_type", "standard")),
        }

    def _save_business_review(self, review: Any) -> None:
        saver = getattr(self._store, "save_business_review", None) if self._store is not None else None
        if not callable(saver):
            raise RuntimeError("business_review_persistence_unavailable")
        saver(review)

    @staticmethod
    def _business_reviewer_context(context: object) -> ReviewerContext:
        """Trust only the server-created effective identity, never context/payload claims."""
        identity = getattr(context, "effective_identity", None)
        if not isinstance(identity, ConsumerIdentity):
            return ReviewerContext(gid=_mutation_actor(context), roles=(), permissions=(), owned_domains=())
        actor = getattr(identity, "actor", None)
        tenant = getattr(identity, "tenant", None)
        consumer = getattr(identity, "consumer", None)
        user_id = getattr(actor, "user_id", None)
        consumer_type = getattr(consumer, "type", None)
        roles = getattr(tenant, "active_roles", ()) if (
            identity is not None and user_id and getattr(identity, "delegation", None) is None
            and consumer_type is ConsumerType.WEB
        ) else ()
        return ReviewerContext(
            gid=str(user_id or _mutation_actor(context)), roles=tuple(str(role) for role in roles),
            permissions=(), owned_domains=(),
        )

    def _current_business_definition_hash(self, proposal: Any) -> str:
        pinned = self._snapshot_by_gid(int(getattr(proposal, "base_snapshot_gid", 0) or 0))
        current = self._latest_snapshot()
        pinned_hash = self._snapshot_definition_hash(pinned, proposal)
        current_hash = self._snapshot_definition_hash(current, proposal)
        if pinned_hash != current_hash:
            raise WorkflowError("review_subject_hash_mismatch")
        return current_hash

    def _snapshot_by_gid(self, snapshot_gid: int) -> Any:
        getter = getattr(self._store, "get_snapshot", None) if self._store is not None else None
        snapshot = getter(snapshot_gid) if callable(getter) else None
        if snapshot is None:
            raise WorkflowError("review_subject_hash_mismatch")
        return snapshot

    @staticmethod
    def _snapshot_definition_hash(snapshot: Any, proposal: Any) -> str:
        document = getattr(snapshot, "document", None)
        version_entry = next((
            entry for entry in getattr(snapshot, "entries", ())
            if int(getattr(entry, "capability_version_gid", 0) or 0)
            == int(getattr(proposal, "capability_version_gid", 0) or 0)
            and str(getattr(entry, "capability_id", "")) == str(getattr(proposal, "capability_id", ""))
        ), None)
        if version_entry is None:
            raise WorkflowError("review_subject_hash_mismatch")
        for capability in getattr(document, "capabilities", ()):
            if (
                str(getattr(capability, "capability_id", "")) == str(getattr(proposal, "capability_id", ""))
                and int(getattr(capability, "major_version", 0) or 0) == int(getattr(version_entry, "major_version", 0) or 0)
            ):
                descriptor = getattr(capability, "descriptor", {})
                value = descriptor.get("business_definition_hash") if isinstance(descriptor, Mapping) else None
                if isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value):
                    return value
        raise WorkflowError("review_subject_hash_mismatch")

    def _proposal_business_evidence(self, proposal: Any) -> dict[str, Any]:
        try:
            snapshot = self._snapshot_by_gid(int(getattr(proposal, "base_snapshot_gid", 0) or 0))
        except WorkflowError:
            return {}
        document = getattr(snapshot, "document", None)
        version_entry = next((
            entry for entry in getattr(snapshot, "entries", ())
            if int(getattr(entry, "capability_version_gid", 0) or 0)
            == int(getattr(proposal, "capability_version_gid", 0) or 0)
            and str(getattr(entry, "capability_id", "")) == str(getattr(proposal, "capability_id", ""))
        ), None)
        if version_entry is None:
            return {}
        for capability in getattr(document, "capabilities", ()):
            if (
                str(getattr(capability, "capability_id", "")) == str(getattr(proposal, "capability_id", ""))
                and int(getattr(capability, "major_version", 0) or 0) == int(getattr(version_entry, "major_version", 0) or 0)
            ):
                relation_loader = getattr(self._store, "list_relation_candidates", None) if self._store is not None else None
                relations = tuple(relation_loader(int(getattr(snapshot, "snapshot_gid"))) if callable(relation_loader) else ())
                capability_key = f"{capability.capability_id}@{capability.major_version}"
                def project(source: str) -> list[dict[str, Any]]:
                    return [
                        {
                            "candidate_hash": str(getattr(item, "candidate_hash", "")),
                            "relation_type": str(getattr(item, "relation_type", "")),
                            "capability_keys": list(getattr(item, "capability_keys", ()))[:20],
                            "evidence": _business_contract_value(redact(getattr(item, "evidence", {}))),
                        }
                        for item in relations if (
                            str(getattr(item, "source", "")) == source
                            and capability_key in tuple(getattr(item, "capability_keys", ()))
                        )
                    ][:20]
                return {
                    "business_effect": str(getattr(capability, "business_effect", ""))[:4000],
                    "business_rules": _business_contract_value(getattr(capability, "business_rules", ())),
                    "business_maturity": _business_contract_value(getattr(capability, "business_maturity", None)),
                    "definition_hash": str(getattr(proposal, "proposed_descriptor_hash", "")),
                    "deterministic_relation_candidates": project("deterministic"),
                    "ai_advisory_relation_candidates": project("advisory"),
                }
        return {}

    def _load_findings(
        self, snapshot: Any, payload: Mapping[str, Any], context: object, *, limit: int = _MAX_SEARCH,
    ) -> tuple[Any, ...]:
        loader = getattr(self._store, "get_findings", None) if self._store is not None else None
        persisted: tuple[Any, ...] = ()
        if callable(loader):
            try:
                persisted = tuple(
                    _enrich_finding_record(snapshot, item)
                    for item in tuple(loader(int(getattr(snapshot, "snapshot_gid"))) or ())[:limit]
                )
            except Exception:
                persisted = ()
        if self._analysis_runner is None:
            return persisted
        try:
            analysis = self._invoke_port(
                self._analysis_runner, snapshot=snapshot, payload=payload, context=context,
                kind="analysis", run_gid=str(getattr(snapshot, "snapshot_gid")),
                request=AnalysisRequest(),
            )
            analysed = self._finding_records(snapshot, getattr(analysis, "findings", ()), limit=limit)
            combined = (*persisted, *analysed)
            unique: dict[str, Any] = {}
            for index, item in enumerate(combined):
                fingerprint = str(_record_value(item, "fingerprint", "")) or f"record:{index}"
                unique.setdefault(fingerprint, item)
            return tuple(unique.values())[:limit]
        except Exception:
            return persisted

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

    def _finding_records(
        self, snapshot: Any, findings: Any, *, limit: int = _MAX_SEARCH,
    ) -> tuple[dict[str, Any], ...]:
        """Project deterministic candidates into read-only, UI-safe records."""
        entries = {
            (str(getattr(entry, "capability_id", "")), int(getattr(entry, "major_version", 0))): str(getattr(entry, "capability_version_gid", ""))
            for entry in getattr(snapshot, "entries", ())
        }
        domains = {
            (str(getattr(entry, "capability_id", "")), int(getattr(entry, "major_version", 0))): str(getattr(entry, "owner_domain", ""))
            for entry in getattr(snapshot, "entries", ())
        }
        node_domains = {
            str(getattr(node, "canonical_key", "")): str(getattr(node, "owner_domain", ""))
            for node in getattr(getattr(snapshot, "document", snapshot), "nodes", ())
            if getattr(node, "canonical_key", None)
        }
        records: list[dict[str, Any]] = []
        for candidate in tuple(findings or ())[:limit]:
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
            finding_domain_values = {
                domains[key]
                for subject in subjects
                if (key := (str(getattr(subject, "capability_id", "")), int(getattr(subject, "major_version", 0)))) in domains
                and domains[key]
            }
            finding_domain_values.update(
                node_domains[str(getattr(subject, "evidence_key", ""))]
                for subject in subjects
                if str(getattr(subject, "evidence_key", "")) in node_domains
                and node_domains[str(getattr(subject, "evidence_key", ""))]
            )
            finding_domain_values.update(
                node_domains[str(value)] for value in getattr(candidate, "evidence_keys", ())
                if str(value) in node_domains and node_domains[str(value)]
            )
            finding_domains = tuple(sorted(finding_domain_values))
            reason_code = code
            root_key, root_label = _root_cause_fields(
                reason_code, subjects=subjects, evidence=getattr(candidate, "evidence_keys", ()),
            )
            records.append({
                "finding_gid": str(finding_gid), "code": code,
                "severity": str(getattr(candidate, "severity", "warning")), "status": "open",
                "fingerprint": fingerprint,
                "remediation_boundary": str(getattr(candidate, "remediation_boundary", "")),
                "subject_version_gids": subject_gids,
                "domains": finding_domains,
                "evidence": tuple(str(value) for value in getattr(candidate, "evidence_keys", ())[:200]),
                "reason_code": reason_code,
                "reason": _finding_reason(reason_code),
                "root_cause_key": root_key,
                "root_cause_label": root_label,
                "subject_summary": _finding_subject_summary(
                    snapshot, subjects, tuple(getattr(candidate, "evidence_keys", ())),
                ),
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
            status = "unavailable" if detail.get("status") in {"advisory_unavailable", "unavailable"} else (
                "candidate" if detail.get("status") == "candidate" else "invalid"
            )
            reason = str(detail.get("reason_code", ""))
            return {
                "status": status,
                "reason_code": reason if status == "unavailable" and reason in {
                    "timeout", "failed", "invalid_output", "dependency_unavailable",
                } else None,
                "finding_count": 0 if status == "unavailable" else min(max(0, int(detail.get("finding_count", 0))), 5000),
                "finding_types": () if status == "unavailable" else finding_types,
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
