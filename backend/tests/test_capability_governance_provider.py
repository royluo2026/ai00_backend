from types import SimpleNamespace

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capabilities.validation_next import validate_payload
from backend.capability_governance_test.contracts import OUTPUT_SCHEMAS
from backend.capability_governance_test.provider import register_governance_capabilities
from backend.capability_governance_test.release_gate import ReleaseGate
from backend.capability_governance_test.service import CapabilityGovernanceService
from backend.scripts.build_capability_governance_catalog import current_release


def _context() -> CapabilityContext:
    return CapabilityContext(user_gid="42", source="web", request_id="request_1")


def _snapshot() -> SimpleNamespace:
    entries = tuple(
        SimpleNamespace(capability_id=f"base.example.{index}", capability_version_gid=index)
        for index in range(250)
    )
    return SimpleNamespace(
        snapshot_gid=100,
        entries=entries,
        document=SimpleNamespace(nodes=(), relations=(), bindings=(), capabilities=()),
    )


class _Store:
    def __init__(self):
        self._snapshots = {100: _snapshot()}

    def get_snapshot(self, snapshot_gid: int):
        return self._snapshots.get(snapshot_gid)


def test_search_caps_collection_to_200_items():
    service = CapabilityGovernanceService(_Store())

    result = service.base_capability_registry_search({"query": "example", "limit": 500}, _context())

    assert result["status"] == "completed"
    assert result["limit"] == 200
    assert len(result["items"]) == 200
    assert len(result["items"]) == 200


def test_graph_requires_explicit_bounded_depth_and_nodes():
    service = CapabilityGovernanceService(_Store())

    with pytest.raises(CapabilityBusinessError, match="invalid_input"):
        service.base_capability_graph_get({"target_gid": "100"}, _context())


def test_analysis_run_pins_the_snapshot_before_queueing_work():
    service = CapabilityGovernanceService(_Store())

    result = service.base_capability_analysis_run(
        {"target_gid": "100", "idempotency_key": "analysis-1"}, _context()
    )

    assert result["status"] == "accepted"
    assert result["snapshot_gid"] == "100"


def test_provider_uses_service_handlers_instead_of_placeholder_results():
    class Registry:
        def __init__(self):
            self.items = {}

        def register(self, spec, handler, *, descriptor=None):
            self.items[spec.id] = (spec, handler, descriptor)

    registry = Registry()
    register_governance_capabilities(registry, CapabilityGovernanceService(_Store()))

    result = registry.items["base.capability_registry.search"][1]({"query": "example"}, _context())

    assert result["capability_id"] == "base.capability_registry.search"
    assert result["status"] == "completed"
    assert result["items"][0] == {
        "capability_id": "base.example.0", "capability_version_gid": "0",
    }
    assert len(result["items"]) == 200


def test_provider_drops_undeclared_service_response_fields():
    class Service:
        def base_capability_registry_search(self, payload, context):
            return {
                "capability_id": "base.capability_registry.search",
                "status": "completed",
                "items": (SimpleNamespace(capability_id="base.safe", capability_version_gid=17),),
                "secret": "must-not-cross-transport",
            }

    class Registry:
        def register(self, spec, handler, *, descriptor=None):
            if spec.id == "base.capability_registry.search":
                self.handler = handler

    registry = Registry()
    register_governance_capabilities(registry, Service())

    assert registry.handler({"query": "safe"}, _context()) == {
        "capability_id": "base.capability_registry.search",
        "status": "completed",
        "items": [{"capability_id": "base.safe", "capability_version_gid": "17"}],
    }


def test_provider_preserves_the_declared_bounded_response_envelope():
    """Removing an envelope field below would discard a service result."""
    from backend.capabilities.registry_next import CapabilityRegistry

    class Service:
        def base_capability_registry_search(self, payload, context):
            return {
                "capability_id": "base.capability_registry.search",
                "status": "completed",
                "data": {"summary": "one matching capability"},
                "items": ({"capability_id": "base.safe", "capability_version_gid": 17},),
                "nodes": ({"canonical_key": "base.safe"},),
                "findings": ({"code": "governance_check"},),
                "snapshot_gid": 11,
                "run_gid": 12,
                "proposal_gid": 13,
                "waiver_gid": 14,
                "release_report_gid": 15,
                "secret": "must-not-cross-transport",
            }

    registry = CapabilityRegistry()
    register_governance_capabilities(registry, Service())

    result = __import__("asyncio").run(registry.invoke(
        "base.capability_registry.search",
        {"query": "safe"},
        CapabilityContext(user_gid="42", permissions=("system.capability.read",)),
    ))

    assert result.data == {
        "capability_id": "base.capability_registry.search",
        "status": "completed",
        "data": {"summary": "one matching capability"},
        "items": [{"capability_id": "base.safe", "capability_version_gid": "17"}],
        "nodes": [{"canonical_key": "base.safe"}],
        "findings": [{"code": "governance_check"}],
        "snapshot_gid": "11",
        "run_gid": "12",
        "proposal_gid": "13",
        "waiver_gid": "14",
        "release_report_gid": "15",
    }


def test_provider_projects_workflow_mutation_and_release_records():
    """Dropping a workflow-record branch would hide its outcome from callers."""
    class Registry:
        def __init__(self):
            self.handlers = {}

        def register(self, spec, handler, *, descriptor=None):
            self.handlers[spec.id] = handler

    registry = Registry()
    service = CapabilityGovernanceService(release_gate=ReleaseGate(
        next_gid=iter(range(1, 20)).__next__, signer=lambda value: "signature",
    ))
    register_governance_capabilities(registry, service)

    proposal = registry.handlers["base.capability_proposal.submit"]({
        "capability_id": "base.capability_registry.search", "capability_version_gid": "17",
        "base_snapshot_gid": "31", "previous_hash": "sha256:old",
        "proposed_descriptor_hash": "sha256:new", "evidence_hash": "sha256:evidence",
        "idempotency_key": "proposal-projection",
    }, _context())
    waiver = registry.handlers["base.capability_waiver.grant"]({
        "finding_gid": "23", "capability_version_gid": "17", "scope": "repository",
        "reason": "temporary exception", "code_hash": "sha256:code",
        "catalog_hash": "sha256:catalog", "evidence_hash": "sha256:evidence",
        "starts_at": "2026-01-01T00:00:00Z", "expires_at": "2099-01-01T00:00:00Z",
        "idempotency_key": "waiver-projection",
    }, _context())
    release = registry.handlers["base.capability_release_gate.evaluate"]({
        "code_revision": "rev-a", "product_catalog_release_id": "catalog-a",
        "snapshot_gid": "31", "test_run_gid": "41", "test_status": "unavailable",
        "approvals_complete": True, "data_complete": True, "evidence_hash": "sha256:evidence",
        "idempotency_key": "release-projection",
    }, _context())

    validate_payload(OUTPUT_SCHEMAS["base.capability_proposal.submit"], proposal, label="output")
    validate_payload(OUTPUT_SCHEMAS["base.capability_waiver.grant"], waiver, label="output")
    validate_payload(OUTPUT_SCHEMAS["base.capability_release_gate.evaluate"], release, label="output")

    assert proposal == {
        "capability_id": "base.capability_proposal.submit", "status": "accepted",
        "proposal": {"proposal_gid": "1", "status": "submitted", "row_version": "3"},
    }
    assert waiver == {
        "capability_id": "base.capability_waiver.grant", "status": "accepted",
        "waiver": {"waiver_gid": "2", "status": "active", "row_version": "1"},
    }
    assert release == {
        "capability_id": "base.capability_release_gate.evaluate", "status": "completed",
        "release": {
            "report_gid": "1", "conclusion": "fail",
            "blockers": [
                "governance_dependency_unavailable", "required_test_unavailable", "stale_evidence",
            ],
        },
    }


def test_health_counts_blocking_exposure_findings_by_node_domain() -> None:
    """Health must surface a route-only blocking finding as blocked for its domain."""
    from backend.capability_governance_test.rules import FindingCandidate, FindingSubject

    entry = SimpleNamespace(
        capability_id="craft.example.read", major_version=1,
        capability_version_gid=101, owner_domain="craft",
    )
    route = SimpleNamespace(
        canonical_key="rest_route:craft:plugins/craft/routes.py:read_factory",
        owner_domain="craft", node_type="rest_route",
    )
    snapshot = SimpleNamespace(
        snapshot_gid=100, entries=(entry,),
        document=SimpleNamespace(nodes=(route,), relations=(), bindings=(), capabilities=()),
    )

    class Store:
        def get_snapshot(self, snapshot_gid: int):
            return snapshot if snapshot_gid == 100 else None

        def latest_snapshot(self):
            return snapshot

    finding = FindingCandidate(
        "exposure_without_capability", "blocking",
        subjects=(FindingSubject("", 0, "exposure", route.canonical_key),),
        evidence_keys=(route.canonical_key,),
    )
    service = CapabilityGovernanceService(
        Store(), analysis_runner=lambda snapshot, request: SimpleNamespace(findings=(finding,)),
    )

    result = service.base_capability_health_get({"domains": ["craft"]}, _context())

    assert result["items"] == ({
        "domain": "craft", "status": "blocked", "snapshot_gid": "100",
        "checked_at": result["items"][0]["checked_at"], "entry_count": 1,
        "finding_count": 1, "severities": ["blocking"], "reason": "blocking_findings",
    },)


def test_finding_records_explain_nok_reason_and_subject() -> None:
    """Finding rows must explain the stable NOK category and concrete subject."""
    from backend.capability_governance_test.rules import FindingCandidate, FindingSubject

    route = SimpleNamespace(
        canonical_key="rest_route:craft:plugins/craft/routes.py:read_factory",
        owner_domain="craft", node_type="rest_route", source_symbol="read_factory",
    )
    snapshot = SimpleNamespace(
        snapshot_gid=100, entries=(),
        document=SimpleNamespace(nodes=(route,), relations=(), bindings=(), capabilities=()),
    )

    class Store:
        def get_snapshot(self, snapshot_gid: int):
            return snapshot if snapshot_gid == 100 else None

        def latest_snapshot(self):
            return snapshot

    finding = FindingCandidate(
        "exposure_without_capability", "blocking",
        subjects=(FindingSubject("", 0, "exposure", route.canonical_key),),
        evidence_keys=(route.canonical_key,),
    )
    service = CapabilityGovernanceService(
        Store(), analysis_runner=lambda snapshot, request: SimpleNamespace(findings=(finding,)),
    )

    result = service.base_capability_finding_search({"target_gid": "100"}, _context())

    assert result["findings"][0]["reason_code"] == "exposure_without_capability"
    assert "公开入口" in result["findings"][0]["reason"]
    assert result["findings"][0]["subject_summary"] == "REST 路由：read_factory"


def test_finding_transport_preserves_explanation_fields() -> None:
    """The closed provider response must not strip finding explanations."""
    from backend.capabilities.registry_next import CapabilityRegistry

    class Service:
        def base_capability_finding_search(self, payload, context):
            return {
                "capability_id": "base.capability_finding.search", "status": "completed",
                "findings": ({
                    "finding_gid": 17, "code": "gap", "severity": "blocking", "status": "open",
                    "fingerprint": "sha256:finding", "remediation_boundary": "catalog",
                    "subject_version_gids": (), "domains": ("craft",), "evidence": ("evidence",),
                    "reason_code": "gap", "reason": "缺少实现证据。", "subject_summary": "Capability：craft.example@1",
                },),
            }

    registry = CapabilityRegistry()
    register_governance_capabilities(registry, Service())
    import asyncio
    result = asyncio.run(registry.invoke(
        "base.capability_finding.search", {},
        CapabilityContext(user_gid="42", permissions=("system.capability.read",)),
    ))

    finding = result.data["findings"][0]
    assert finding["reason_code"] == "gap"
    assert finding["reason"] == "缺少实现证据。"
    assert finding["subject_summary"] == "Capability：craft.example@1"


def test_persisted_finding_backfills_explanation_fields() -> None:
    """Older stored findings remain understandable after the schema extension."""
    snapshot = SimpleNamespace(
        snapshot_gid=100, entries=(),
        document=SimpleNamespace(nodes=(), relations=(), bindings=(), capabilities=()),
    )

    class Store:
        def get_snapshot(self, snapshot_gid: int):
            return snapshot if snapshot_gid == 100 else None

        def latest_snapshot(self):
            return snapshot

        def get_findings(self, snapshot_gid: int):
            return ({"finding_gid": "17", "code": "gap", "severity": "blocking", "evidence": ()},)

    result = CapabilityGovernanceService(Store()).base_capability_finding_search(
        {"target_gid": "100"}, _context()
    )

    assert result["findings"][0]["reason_code"] == "gap"
    assert "没有可验证的实现绑定" in result["findings"][0]["reason"]
    assert result["findings"][0]["subject_summary"] == "未解析主体"


def test_health_count_is_not_limited_to_the_finding_center_page_size() -> None:
    """Health totals must include all bounded findings, not only the first 200 rows."""
    from backend.capability_governance_test.rules import FindingCandidate, FindingSubject

    entry = SimpleNamespace(
        capability_id="craft.example.read", major_version=1,
        capability_version_gid=101, owner_domain="craft",
    )
    route = SimpleNamespace(
        canonical_key="rest_route:craft:plugins/craft/routes.py:read_factory",
        owner_domain="craft", node_type="rest_route",
    )
    snapshot = SimpleNamespace(
        snapshot_gid=100, entries=(entry,),
        document=SimpleNamespace(nodes=(route,), relations=(), bindings=(), capabilities=()),
    )

    class Store:
        def get_snapshot(self, snapshot_gid: int):
            return snapshot if snapshot_gid == 100 else None

        def latest_snapshot(self):
            return snapshot

    subject = FindingSubject("", 0, "exposure", route.canonical_key)
    findings = tuple(FindingCandidate(
        "exposure_without_capability", "blocking", subjects=(subject,), evidence_keys=(f"{route.canonical_key}:{index}",)
    ) for index in range(201))
    service = CapabilityGovernanceService(
        Store(), analysis_runner=lambda snapshot, request: SimpleNamespace(findings=findings),
    )

    result = service.base_capability_health_get({"domains": ["craft"]}, _context())

    assert result["items"][0]["finding_count"] == 201


def test_health_transport_accepts_bounded_counts_above_finding_page_size() -> None:
    """The closed Gateway schema must allow health totals larger than one page."""
    import asyncio
    from backend.capability_governance_test.rules import FindingCandidate, FindingSubject
    from backend.capabilities.registry_next import CapabilityRegistry

    entry = SimpleNamespace(
        capability_id="craft.example.read", major_version=1,
        capability_version_gid=101, owner_domain="craft",
    )
    route = SimpleNamespace(
        canonical_key="rest_route:craft:plugins/craft/routes.py:read_factory",
        owner_domain="craft", node_type="rest_route",
    )
    snapshot = SimpleNamespace(
        snapshot_gid=100, entries=(entry,),
        document=SimpleNamespace(nodes=(route,), relations=(), bindings=(), capabilities=()),
    )

    class Store:
        def get_snapshot(self, snapshot_gid: int):
            return snapshot if snapshot_gid == 100 else None

        def latest_snapshot(self):
            return snapshot

    subject = FindingSubject("", 0, "exposure", route.canonical_key)
    findings = tuple(FindingCandidate(
        "exposure_without_capability", "blocking", subjects=(subject,), evidence_keys=(f"{route.canonical_key}:{index}",)
    ) for index in range(201))
    registry = CapabilityRegistry()
    register_governance_capabilities(registry, CapabilityGovernanceService(
        Store(), analysis_runner=lambda snapshot, request: SimpleNamespace(findings=findings),
    ))

    result = asyncio.run(registry.invoke(
        "base.capability_health.get", {"domains": ["craft"]},
        CapabilityContext(user_gid="42", permissions=("system.capability.read",)),
    ))

    assert result.data["items"][0]["finding_count"] == 201


def test_closed_provider_schema_admits_graph_bounds_required_by_service():
    from backend.capabilities.registry_next import CapabilityRegistry

    registry = CapabilityRegistry()
    register_governance_capabilities(registry, CapabilityGovernanceService(_Store()))

    result = __import__("asyncio").run(registry.invoke(
        "base.capability_graph.get",
        {"target_gid": "100", "max_depth": 4, "max_nodes": 500},
        CapabilityContext(user_gid="42", permissions=("system.capability.read",)),
    ))

    assert result.data == {
        "capability_id": "base.capability_graph.get", "status": "completed",
        "snapshot_gid": "100", "snapshot": {"snapshot_gid": "100"},
        "max_depth": 4, "max_nodes": 500, "nodes": [],
    }


def test_service_proposal_submit_uses_the_workflow_and_review_fails_before_approval():
    service = CapabilityGovernanceService()
    submitted = service.base_capability_proposal_submit({
        "capability_id": "base.capability_registry.search", "capability_version_gid": "17",
        "base_snapshot_gid": "31", "previous_hash": "sha256:old",
        "proposed_descriptor_hash": "sha256:new", "evidence_hash": "sha256:evidence",
        "idempotency_key": "proposal-1",
    }, _context())

    assert submitted["proposal"].status == "submitted"
    with pytest.raises(CapabilityBusinessError, match="invalid_transition"):
        service.base_capability_review_decide({
            "proposal_gid": str(submitted["proposal"].proposal_gid), "stage": "base_owner",
            "decision": "approved", "row_version": str(submitted["proposal"].row_version),
            "idempotency_key": "review-1",
        }, _context())


def test_service_release_handler_uses_fail_closed_release_gate():
    service = CapabilityGovernanceService(release_gate=ReleaseGate(
        next_gid=iter(range(1, 20)).__next__, signer=lambda value: "signature",
    ))

    result = service.base_capability_release_gate_evaluate({
        "code_revision": "rev-a", "product_catalog_release_id": "catalog-a",
        "snapshot_gid": "101", "test_run_gid": "201", "test_status": "unavailable",
        "approvals_complete": True, "data_complete": True, "idempotency_key": "gate-1",
    }, _context())

    assert result["release"].conclusion == "fail"
    assert "required_test_unavailable" in result["release"].blockers


def test_unconfigured_provider_fails_closed_instead_of_returning_empty_results():
    from backend.capabilities.registry_next import CapabilityRegistry

    registry = CapabilityRegistry()
    register_governance_capabilities(registry)

    with pytest.raises(CapabilityBusinessError, match="provider_unavailable"):
        registry.get("base.capability_registry.search").handler({"query": "example"}, _context())


def test_governance_read_capabilities_expose_proposals_health_and_audit():
    from backend.capability_governance_test.audit import AuditSink

    class ProposalStore:
        def __init__(self):
            self._snapshots = {100: _snapshot()}
            self.persistent = False

        def get_snapshot(self, snapshot_gid: int):
            return self._snapshots.get(snapshot_gid)

        def latest_snapshot(self):
            return self._snapshots[100]

        def list_entries(self):
            return self._snapshots[100].entries

    audit = AuditSink(next_gid=iter(range(1000, 1100)).__next__)
    service = CapabilityGovernanceService(ProposalStore(), audit_sink=audit)
    service._audit(operation="governance_scan", request_id="req-1", context=_context(), detail={})
    audit.append(
        operation="proposal",
        entity_gid=100,
        actor_gid="42",
        request_gid="req-2",
        detail={"status": "draft", "capability_id": "base.example.read", "blockers": ["missing_test"]},
        idempotency_key="proposal:req-2",
    )
    registry = __import__("backend.capabilities.registry_next", fromlist=["CapabilityRegistry"]).CapabilityRegistry()
    register_governance_capabilities(registry, service)

    proposal = registry.get("base.capability_proposal.search").handler({"limit": 10}, _context())
    health = registry.get("base.capability_health.get").handler({"domains": ["craft"]}, _context())
    audit_result = registry.get("base.capability_audit.search").handler({"limit": 10}, _context())

    assert proposal["capability_id"] == "base.capability_proposal.search"
    assert proposal["status"] == "completed"
    assert proposal["data"]["available"] is True
    assert health["items"][0]["domain"] == "craft"
    assert health["items"][0]["status"] in {"healthy", "attention", "blocked", "unverified"}
    assert audit_result["items"][0]["operation"] == "proposal"
    descriptors = {item.id: item for item in current_release().descriptors}
    for capability_id, result in (
        ("base.capability_proposal.search", proposal),
        ("base.capability_health.get", health),
        ("base.capability_audit.search", audit_result),
    ):
        validate_payload(dict(descriptors[capability_id].output_schema), result, label=f"{capability_id}.output")
