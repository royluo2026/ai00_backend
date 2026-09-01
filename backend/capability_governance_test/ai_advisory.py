"""Bounded candidate-only advisory adapter over the governed Agent domain."""
from __future__ import annotations

from collections.abc import Mapping
import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
import time
from typing import Any, Literal

from pydantic import Field, ValidationError

from backend.capability_v2.contracts import CapabilityStatus, ConsumerIdentity, CorrelationRef, FrozenModel
from backend.capability_v2.domain_client import DomainCapabilityClient, DomainInvocation
from backend.domain_ports.capability_governance_ai import GovernanceAdvisorPort

from .business_models import CapabilityRelationCandidate
from .redaction import sanitize_candidate_package


_MAX_INPUT_BYTES = 64 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024
_MAX_TIMEOUT_SECONDS = 30
_MAX_OPERATION_POLLS = 4
_DECIMAL_GID = re.compile(r"^[0-9]{1,19}$")
_EVIDENCE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}$")
_MAX_EVIDENCE_KEYS = 20


class AdvisoryContractError(ValueError):
    """Raised when a model-advisory input or output crosses its fixed contract."""


class AdvisoryFinding(FrozenModel):
    finding_type: Literal[
        "duplicate", "semantic_overlap", "conflict", "gap", "non_atomic_facade", "lifecycle_pair_gap",
    ]
    subject_version_gids: tuple[str, ...] = ()
    capability_keys: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)
    evidence_keys: tuple[str, ...]
    recommendation: str = Field(min_length=1, max_length=4000)
    status: Literal["candidate"] = "candidate"
    authority: Literal["advisory"] = "advisory"
    severity: Literal["info", "review"] = "review"

    @classmethod
    def _validate_gids(cls, value: Any) -> Any:
        if not isinstance(value, (tuple, list)) or not value or any(
            not isinstance(item, str) or _DECIMAL_GID.fullmatch(item) is None
            for item in value
        ):
            raise AdvisoryContractError("candidate_only: subject_version_gids must be decimal strings")
        return value

    @classmethod
    def _validate_evidence_keys(cls, value: Any) -> Any:
        if not isinstance(value, (tuple, list)) or len(value) > _MAX_EVIDENCE_KEYS or any(
            not isinstance(item, str) or _EVIDENCE_KEY.fullmatch(item) is None
            for item in value
        ):
            raise AdvisoryContractError("candidate_only: evidence_keys must be bounded identifiers")
        return value

    def __init__(self, **data: Any) -> None:
        gids = data.get("subject_version_gids", ())
        capability_keys = data.get("capability_keys", ())
        if gids:
            data["subject_version_gids"] = self._validate_gids(gids)
        elif not isinstance(capability_keys, (tuple, list)) or not capability_keys or any(
            not isinstance(key, str) or not key.strip() for key in capability_keys
        ):
            raise AdvisoryContractError("candidate_only: subject_version_gids must be decimal strings")
        data["capability_keys"] = tuple(capability_keys)
        data["evidence_keys"] = self._validate_evidence_keys(data.get("evidence_keys"))
        super().__init__(**data)


class AdvisoryResult(FrozenModel):
    findings: tuple[AdvisoryFinding, ...] = ()
    status: Literal["candidate", "unavailable"] = "candidate"
    reason_code: Literal["timeout", "failed", "invalid_output", "dependency_unavailable"] | None = None

    def __init__(self, **data: Any) -> None:
        if data.get("status", "candidate") == "unavailable":
            if data.get("findings", ()):
                raise AdvisoryContractError("unavailable_advisory_must_be_empty")
            if data.get("reason_code") is None:
                raise AdvisoryContractError("unavailable_advisory_requires_reason")
        elif data.get("reason_code") is not None:
            raise AdvisoryContractError("candidate_advisory_has_reason")
        super().__init__(**data)


def advisory_result(**values: Any) -> dict[str, Any]:
    """Small fixture-safe constructor; validation remains at the boundary."""
    return {"findings": values.pop("findings", ()), "status": values.pop("status", "candidate"), **values}


def validate_advisory(
    value: Any,
    *,
    allowed_gids: tuple[str, ...] = (),
    allowed_keys: tuple[str, ...] = (),
    allowed_evidence_keys: tuple[str, ...] = (),
) -> AdvisoryResult:
    """Validate exactly the candidate contract; advice can never become a decision."""
    try:
        if isinstance(value, AdvisoryResult):
            result = value
        elif isinstance(value, Mapping):
            result = AdvisoryResult.model_validate(value)
        else:
            raise AdvisoryContractError("candidate_only: advisory result must be a mapping")
    except AdvisoryContractError:
        raise
    except ValidationError as exc:
        raise AdvisoryContractError(f"candidate_only: {exc.errors()[0]['msg']}") from exc
    if result.status == "unavailable":
        return result
    if any(finding.status != "candidate" for finding in result.findings):
        raise AdvisoryContractError("candidate_only: confirmed findings are forbidden")
    for finding in result.findings:
        # Candidate binding is fail-closed: an empty allow-list does not mean
        # "all subjects".  A model may only refer to the exact members sent.
        if not finding.subject_version_gids or not set(finding.subject_version_gids).issubset(allowed_gids):
            raise AdvisoryContractError("candidate_only: subject outside candidate")
        if not set(finding.capability_keys).issubset(allowed_keys):
            raise AdvisoryContractError("candidate_only: capability outside candidate")
        if not set(finding.evidence_keys).issubset(allowed_evidence_keys):
            raise AdvisoryContractError("candidate_only: evidence outside candidate")
    return result


def explain_relation(
    candidate: CapabilityRelationCandidate, evidence: Mapping[str, Any],
) -> AdvisoryFinding:
    """Attach a non-authoritative explanation without changing hard evidence."""
    if candidate.source != "deterministic":
        raise AdvisoryContractError("relation_explanation_requires_deterministic_candidate")
    if not isinstance(evidence, Mapping):
        raise AdvisoryContractError("invalid_relation_evidence")
    finding_type = {
        "duplicate": "duplicate",
        "coverage": "semantic_overlap",
        "conflict": "conflict",
        "boundary_overlap": "semantic_overlap",
    }[candidate.relation_type]
    evidence_keys = tuple(sorted({
        *(str(key) for key in candidate.evidence if _EVIDENCE_KEY.fullmatch(str(key))),
        *(str(key) for key in evidence if _EVIDENCE_KEY.fullmatch(str(key))),
    }))[:_MAX_EVIDENCE_KEYS]
    return AdvisoryFinding(
        finding_type=finding_type,
        capability_keys=candidate.capability_keys,
        confidence=0.0,
        evidence_keys=evidence_keys,
        recommendation=str(evidence.get("recommendation") or "Review the cited deterministic relation evidence; this advisory cannot change its type or gate severity."),
    )


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AdvisoryContractError("invalid_advisory_json") from exc


def bounded_candidate_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a package to its declared advisory surface before redaction and transport."""
    if not isinstance(package, Mapping):
        raise AdvisoryContractError("invalid_candidate_package")
    return sanitize_candidate_package(package)


class GovernedAgentAdvisor(GovernanceAdvisorPort):
    """Calls only ``DomainCapabilityClient``; no model HTTP client is present here."""

    def __init__(
        self,
        client: DomainCapabilityClient,
        *,
        max_input_bytes: int = _MAX_INPUT_BYTES,
        max_output_bytes: int = _MAX_OUTPUT_BYTES,
        timeout_seconds: int = _MAX_TIMEOUT_SECONDS,
    ) -> None:
        if not 1 <= max_input_bytes <= _MAX_INPUT_BYTES:
            raise AdvisoryContractError("invalid_input_byte_limit")
        if not 1 <= max_output_bytes <= _MAX_OUTPUT_BYTES:
            raise AdvisoryContractError("invalid_output_byte_limit")
        if not 1 <= timeout_seconds <= _MAX_TIMEOUT_SECONDS:
            raise AdvisoryContractError("invalid_advisory_deadline")
        self._client = client
        self._max_input_bytes = max_input_bytes
        self._max_output_bytes = max_output_bytes
        self._timeout_seconds = timeout_seconds
        self._inflight_task: asyncio.Task[Any] | None = None

    async def review(
        self,
        package: Mapping[str, Any],
        *,
        identity: ConsumerIdentity,
        request_id: str,
    ) -> AdvisoryResult:
        if len(_json_bytes(package)) > self._max_input_bytes:
            raise AdvisoryContractError("input_bytes_exceeded")
        candidate_package = bounded_candidate_package(package)
        request_hash = hashlib.sha256(_json_bytes(candidate_package)).hexdigest()
        payload = {
            "resource_gid": "capability-governance-advisory",
            "status": "requested",
            "content": {"kind": "capability_governance_advisory", "package": candidate_package},
        }
        if len(_json_bytes(payload)) > self._max_input_bytes:
            raise AdvisoryContractError("input_bytes_exceeded")
        deadline = datetime.now(UTC) + timedelta(seconds=self._timeout_seconds)
        deadline_monotonic = time.monotonic() + self._timeout_seconds
        try:
            result = await self._invoke_before_deadline(
                DomainInvocation("agent.interaction.request", 1, payload,
                                 idempotency_key=f"capability-advisory:{request_hash}"),
                identity, request_id, deadline, deadline_monotonic,
            )
        except TimeoutError as exc:
            raise AdvisoryContractError("agent_advisory_timeout") from exc
        result = await self._completed_result(
            result, identity=identity, request_id=request_id, deadline=deadline,
            deadline_monotonic=deadline_monotonic,
        )
        if len(_json_bytes(result.data)) > self._max_output_bytes:
            raise AdvisoryContractError("output_bytes_exceeded")
        data = result.data
        if isinstance(data, Mapping) and isinstance(data.get("content"), Mapping):
            data = data["content"]
        allowlist = candidate_package.get("advisory_output_allowlist", {})
        return validate_advisory(
            data,
            allowed_gids=tuple(allowlist.get("subject_version_gids", ())) if isinstance(allowlist, Mapping) else (),
            allowed_keys=tuple(allowlist.get("capability_keys", ())) if isinstance(allowlist, Mapping) else (),
            allowed_evidence_keys=tuple(allowlist.get("evidence_keys", ())) if isinstance(allowlist, Mapping) else (),
        )

    async def _invoke_before_deadline(
        self, invocation: DomainInvocation, identity: ConsumerIdentity, request_id: str,
        deadline: datetime, deadline_monotonic: float,
    ) -> Any:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            raise AdvisoryContractError("agent_advisory_timeout")
        # Do not use wait_for here: it waits for a coroutine that swallows
        # CancelledError.  One detached task is permitted, then the advisor is
        # fail-fast until it completes, bounding both latency and task count.
        if self._inflight_task is not None and not self._inflight_task.done():
            raise AdvisoryContractError("agent_advisory_timeout")
        task = asyncio.create_task(
            self._client.invoke(invocation, identity, CorrelationRef(request_id=request_id), deadline=deadline),
        )
        self._inflight_task = task
        task.add_done_callback(self._reap_detached_task)
        done, _ = await asyncio.wait((task,), timeout=remaining)
        if not done:
            raise AdvisoryContractError("agent_advisory_timeout")
        if self._inflight_task is task:
            self._inflight_task = None
        return task.result()

    def _reap_detached_task(self, task: asyncio.Task[Any]) -> None:
        """Consume late completion so detached failures never hit loop warnings."""
        try:
            task.exception()
        except asyncio.CancelledError:
            pass
        if self._inflight_task is task:
            self._inflight_task = None

    async def _completed_result(
        self,
        result: Any,
        *,
        identity: ConsumerIdentity,
        request_id: str,
        deadline: datetime,
        deadline_monotonic: float,
    ) -> Any:
        if result.ok and result.status is CapabilityStatus.COMPLETED:
            return result
        if result.status is not CapabilityStatus.ACCEPTED or not result.ok or result.operation_ref is None:
            raise AdvisoryContractError("agent_advisory_failed")
        operation_id = result.operation_ref.operation_id
        for _ in range(_MAX_OPERATION_POLLS):
            if time.monotonic() >= deadline_monotonic:
                raise AdvisoryContractError("agent_advisory_timeout")
            payload = {"resource_gid": operation_id}
            if len(_json_bytes(payload)) > self._max_input_bytes:
                raise AdvisoryContractError("input_bytes_exceeded")
            result = await self._invoke_before_deadline(
                DomainInvocation("agent.run.read", 1, payload), identity, request_id,
                deadline, deadline_monotonic,
            )
            if result.ok and result.status is CapabilityStatus.COMPLETED:
                return result
            if not result.ok or result.status in {CapabilityStatus.FAILED, CapabilityStatus.REJECTED}:
                raise AdvisoryContractError("agent_advisory_failed")
        raise AdvisoryContractError("agent_advisory_timeout")


__all__ = [
    "AdvisoryContractError", "AdvisoryFinding", "AdvisoryResult", "GovernedAgentAdvisor",
    "advisory_result", "bounded_candidate_package", "explain_relation", "validate_advisory",
]
