from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import MappingProxyType, SimpleNamespace

import pytest

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext
from backend.capabilities.validation_next import validate_payload
from backend.capability_governance_test.business_audit import (
    AuditCapability,
    AuditEvidence,
    AuditRelation,
    UnboundPublicEntry,
    audit,
)
from backend.capability_governance_test.contracts import OUTPUT_SCHEMAS
from backend.capability_governance_test.provider import _safe_response, register_governance_capabilities
from backend.capability_governance_test.service import CapabilityGovernanceService, GovernedRun
from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    TenantIdentity,
)


SOURCE_REVISION = "a" * 40
WEB_REVISION = "b" * 40
DEFINITION_HASH = "sha256:" + "c" * 64


def _context(*, super_admin: bool = False) -> CapabilityContext:
    identity = ConsumerIdentity(
        actor=ActorIdentity(
            user_id="42", authentication_method="test",
            authenticated_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        ),
        tenant=TenantIdentity(
            tenant_id="tenant", membership="member",
            active_roles=("super_admin",) if super_admin else (),
        ),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
        delegation=None,
    )
    return CapabilityContext(user_gid="42", effective_identity=identity)


def _report(*, snapshot_gid: str = "100", source_revision: str = SOURCE_REVISION):
    capabilities = tuple(
        AuditCapability(
            capability_id=f"craft.review.item_{index:03d}", major_version=1,
            domain="craft", maturity="L1", semantic_class="write",
        )
        for index in range(495)
    )
    findings = tuple(
        AuditEvidence(
            reason_code="business_rules_missing", capability_id=item.capability_id,
            major_version=1, domain="craft", layer="C",
            evidence_ref=f"catalog:{index}", remediation_family="declare_business_rule",
        )
        for index, item in enumerate(capabilities)
    )
    relations = tuple(
        AuditRelation(
            candidate_hash=f"relation-{index:03d}", relation_type="overlap",
            source="deterministic" if index % 2 == 0 else "advisory",
            capability_keys=(capabilities[index].capability_key,),
            evidence={"reason": f"evidence-{index}", "token": "must-not-cross"},
            status="pending_review",
        )
        for index in range(205)
    )
    unbound = tuple(
        UnboundPublicEntry(
            "Provider", f"provider:craft:{index:03d}", "craft",
            f"plugins/craft/provider_{index:03d}.py", f"Provider{index:03d}", source_line=index + 1,
        )
        for index in range(205)
    )
    return audit(
        findings, capabilities=capabilities, snapshot_gid=snapshot_gid,
        source_revisions={"backend": source_revision, "web": WEB_REVISION, "source": source_revision},
        relations=relations, unbound_entries=unbound,
    )


class _RunStore:
    def __init__(self) -> None:
        self.snapshot = SimpleNamespace(
            snapshot_gid=100,
            document=SimpleNamespace(
                code_revision=SOURCE_REVISION,
                product_release_id="catalog-r9",
                snapshot_hash="sha256:" + "d" * 64,
                capabilities=(), nodes=(), bindings=(), relations=(),
            ),
            entries=(),
        )
        self.runs: dict[str, GovernedRun] = {}

    def get_snapshot(self, snapshot_gid: int):
        return self.snapshot if snapshot_gid == 100 else None

    def save_governed_run(self, run: GovernedRun) -> None:
        self.runs[run.run_gid] = run

    def get_governed_run(self, run_gid: str):
        return self.runs.get(str(run_gid))


def _run_report(store: _RunStore, report=None) -> tuple[CapabilityGovernanceService, str]:
    service = CapabilityGovernanceService(store, analysis_runner=lambda snapshot, request: report or _report())
    accepted = service.base_capability_analysis_run(
        {"target_gid": "100", "idempotency_key": "task9-analysis"}, _context(),
    )
    return service, accepted["run_gid"]


def test_analysis_get_keeps_the_legacy_run_envelope_when_no_audit_result_exists():
    run = GovernedRun("9", "100", "analysis", "42", "legacy", status="completed")

    response = _safe_response("base.capability_analysis.get", {
        "status": "completed", "run": run,
    })

    assert response == {
        "capability_id": "base.capability_analysis.get", "status": "completed",
        "run": {"run_gid": "9", "snapshot_gid": "100", "kind": "analysis", "status": "completed"},
    }


def test_business_audit_result_is_immutable_redacted_and_survives_supported_store_restart():
    store = _RunStore()
    service, run_gid = _run_report(store)
    in_memory = service.base_capability_analysis_get({"target_gid": run_gid}, _context())["run"]

    assert isinstance(in_memory.result, MappingProxyType)
    assert in_memory.result["business_audit"]["snapshot_gid"] == "100"
    assert in_memory.result["business_audit"]["catalog_binding"] == {
        "catalog_release_id": "catalog-r9", "snapshot_hash": "sha256:" + "d" * 64,
    }
    with pytest.raises(TypeError):
        in_memory.result["business_audit"]["finding_count"] = 0

    restarted = CapabilityGovernanceService(store, analysis_runner=None, worker=None)
    loaded = restarted.base_capability_analysis_get({"target_gid": run_gid}, _context())
    projected = _safe_response("base.capability_analysis.get", loaded)
    validate_payload(OUTPUT_SCHEMAS["base.capability_analysis.get"], projected, label="output")
    encoded = repr(projected)
    assert "must-not-cross" not in encoded
    assert projected["run"]["result"]["business_audit"]["source_revisions"]["web"] == WEB_REVISION


def test_business_audit_review_queue_pages_495_without_omission_or_duplication():
    service, run_gid = _run_report(_RunStore())
    rows = []
    cursor = None
    while True:
        payload = {"target_gid": run_gid, "collection": "review_queue", "limit": 200}
        if cursor is not None:
            payload["cursor"] = cursor
        run = service.base_capability_analysis_get(payload, _context())["run"]
        page = run.result["business_audit"]
        assert len(page["review_queue"]) <= 200
        rows.extend(item["capability_key"] for item in page["review_queue"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert len(rows) == 495
    assert len(set(rows)) == 495
    assert rows == sorted(rows)


def test_registered_provider_returns_the_enriched_frontend_analysis_fixture_shape():
    class Registry:
        def __init__(self):
            self.handlers = {}

        def register(self, spec, handler, *, descriptor=None):
            self.handlers[spec.id] = handler

    service, run_gid = _run_report(_RunStore())
    registry = Registry()
    register_governance_capabilities(registry, service)

    response = registry.handlers["base.capability_analysis.get"](
        {"target_gid": run_gid, "collection": "review_queue", "limit": 200}, _context(),
    )

    validate_payload(OUTPUT_SCHEMAS["base.capability_analysis.get"], response, label="output")
    assert response["capability_id"] == "base.capability_analysis.get"
    assert response["status"] == "completed"
    assert response["run"]["snapshot_gid"] == "100"
    report = response["run"]["result"]["business_audit"]
    assert report["finding_count"] == 495
    assert report["root_cause_group_count"] == 495
    assert len(report["review_queue"]) == 200
    assert report["next_cursor"] == "review_queue:200"


@pytest.mark.parametrize(
    ("collection", "expected_total"),
    (("root_causes", 495), ("unbound_entries", 205), ("relations", 205)),
)
def test_business_audit_large_collections_have_collection_scoped_stable_cursors(collection, expected_total):
    service, run_gid = _run_report(_RunStore())
    first = service.base_capability_analysis_get(
        {"target_gid": run_gid, "collection": collection, "limit": 200}, _context(),
    )["run"].result["business_audit"]

    assert len(first[collection]) == 200
    assert first["next_cursor"] == f"{collection}:200"
    seen = list(first[collection])
    cursor = first["next_cursor"]
    while cursor is not None:
        page = service.base_capability_analysis_get(
            {"target_gid": run_gid, "collection": collection, "cursor": cursor, "limit": 200},
            _context(),
        )["run"].result["business_audit"]
        seen.extend(page[collection])
        cursor = page["next_cursor"]
    assert len(seen) == expected_total
    with pytest.raises(CapabilityBusinessError, match="invalid_input"):
        service.base_capability_analysis_get(
            {"target_gid": run_gid, "collection": "review_queue", "cursor": first["next_cursor"]}, _context(),
        )


@pytest.mark.parametrize(
    "runner_result",
    (
        {"secret": "must-not-cross"},
        {"business_audit": _report(), "extra": "must-not-cross"},
        _report(snapshot_gid="101"),
        _report(source_revision="e" * 40),
    ),
)
def test_analysis_result_rejects_arbitrary_or_stale_runner_output(runner_result):
    store = _RunStore()
    service = CapabilityGovernanceService(store, analysis_runner=lambda snapshot, request: runner_result)

    with pytest.raises(CapabilityBusinessError, match="governance_result_invalid"):
        service.base_capability_analysis_run(
            {"target_gid": "100", "idempotency_key": "bad-analysis"}, _context(),
        )


@pytest.mark.parametrize(
    "report",
    (
        replace(_report(), machine_passed="yes"),
        replace(_report(), finding_count=494),
        replace(
            _report(),
            relations=(replace(_report().relations[0], source="untrusted"),) + _report().relations[1:],
        ),
        replace(
            _report(),
            relations=(replace(_report().relations[0], evidence={"score": float("inf")}),) + _report().relations[1:],
        ),
    ),
)
def test_analysis_result_rejects_invalid_types_counts_and_relation_enums(report):
    store = _RunStore()
    service = CapabilityGovernanceService(store, analysis_runner=lambda snapshot, request: report)

    with pytest.raises(CapabilityBusinessError, match="governance_result_invalid"):
        service.base_capability_analysis_run(
            {"target_gid": "100", "idempotency_key": "malformed-analysis"}, _context(),
        )


def test_provider_rejects_extra_keys_in_a_business_audit_result_instead_of_dropping_them():
    service, run_gid = _run_report(_RunStore())
    run = service.base_capability_analysis_get({"target_gid": run_gid}, _context())["run"]
    audit_page = dict(run.result["business_audit"])
    audit_page["secret"] = "must-not-cross"
    injected = GovernedRun(
        run.run_gid, run.snapshot_gid, run.kind, run.requested_by, run.idempotency_key,
        status=run.status, result={"business_audit": audit_page},
    )

    with pytest.raises(CapabilityBusinessError, match="provider_invalid_response"):
        _safe_response("base.capability_analysis.get", {"status": "completed", "run": injected})


class _ProposalStore:
    persistent = False

    def __init__(self) -> None:
        descriptor = {
            "business_definition_hash": DEFINITION_HASH,
            "business_effect": "Operators receive one exact governed result.",
            "business_acceptance_criteria": ("The result is schema-valid.",),
            "use_when": "A governed result is required.",
            "do_not_use_when": "The requested major is not one.",
        }
        self.subject = SimpleNamespace(
            capability_id="craft.factory.create", major_version=1, owner_domain="craft",
            descriptor=descriptor, business_effect=descriptor["business_effect"],
            business_rules=({
                "rule_id": "factory.name.unique", "version": 1,
                "statement": "Factory names are unique.", "applies_when": "creating a factory",
                "enforcement_ref": "factory.provider:create", "error_code": "factory_name_conflict",
                "test_refs": ("tests/test_factory.py::test_duplicate",),
            },),
            business_maturity=SimpleNamespace(level="L3", reason_codes=("runtime_pending",)),
        )
        self.snapshot = SimpleNamespace(
            snapshot_gid=31,
            document=SimpleNamespace(
                code_revision=SOURCE_REVISION, product_release_id="catalog-r9",
                capabilities=(self.subject, SimpleNamespace(
                    capability_id=self.subject.capability_id, major_version=2, owner_domain="secret",
                    descriptor={"business_definition_hash": "sha256:" + "f" * 64},
                    business_effect="Wrong-major secret.", business_rules=(), business_maturity=None,
                )),
            ),
            entries=(SimpleNamespace(
                capability_id=self.subject.capability_id, capability_version_gid=17,
                major_version=1, owner_domain="craft",
            ),),
        )
        self.relations = (
            SimpleNamespace(
                candidate_hash="kept", relation_type="overlap", source="deterministic",
                capability_keys=("craft.factory.create@1", "factory.structure.create@1"),
                evidence={"reason": "shared scope", "token": "must-not-cross"}, status="pending_review",
            ),
            SimpleNamespace(
                candidate_hash="hidden", relation_type="overlap", source="deterministic",
                capability_keys=("craft.factory.create@2",), evidence={"secret": "wrong major"},
                status="pending_review",
            ),
        )

    def get_snapshot(self, snapshot_gid):
        return self.snapshot if int(snapshot_gid) == 31 else None

    def latest_snapshot(self):
        return self.snapshot

    def list_relation_candidates(self, snapshot_gid):
        return self.relations if int(snapshot_gid) == 31 else ()

    def save_business_review(self, review):
        return None


def _proposal_service(store: _ProposalStore):
    service = CapabilityGovernanceService(store)
    service.base_capability_proposal_submit({
        "capability_id": "craft.factory.create", "capability_version_gid": "17",
        "base_snapshot_gid": "31", "previous_hash": "sha256:" + "0" * 64,
        "proposed_descriptor_hash": DEFINITION_HASH, "definition_hash": DEFINITION_HASH,
        "evidence_hash": "sha256:" + "1" * 64, "idempotency_key": "task9-proposal",
    }, _context())
    return service


def test_proposal_detail_projects_exact_version_business_contract_and_closed_redacted_evidence():
    service = _proposal_service(_ProposalStore())
    result = service.base_capability_proposal_search({"limit": 1}, _context(super_admin=True))
    projected = _safe_response("base.capability_proposal.search", result)
    validate_payload(OUTPUT_SCHEMAS["base.capability_proposal.search"], projected, label="output")
    proposal = projected["items"][0]
    evidence = proposal["review_evidence"]

    assert evidence["capability_key"] == "craft.factory.create@1"
    assert evidence["major_version"] == 1
    assert evidence["capability_version_gid"] == "17"
    assert evidence["definition_hash"] == DEFINITION_HASH
    assert evidence["business_acceptance_criteria"] == ["The result is schema-valid."]
    assert evidence["accepted_examples"] == ["A governed result is required."]
    assert evidence["rejected_examples"] == ["The requested major is not one."]
    assert evidence["owner_domains"] == ["craft"]
    assert evidence["business_rules"][0]["test_refs"] == ["tests/test_factory.py::test_duplicate"]
    assert [item["candidate_hash"] for item in evidence["deterministic_relation_candidates"]] == ["kept"]
    assert "hidden" not in repr(evidence)
    assert "must-not-cross" not in repr(evidence)


def test_proposal_detail_fails_closed_when_proposal_hash_no_longer_matches_pinned_contract():
    store = _ProposalStore()
    service = _proposal_service(store)
    store.subject.descriptor["business_definition_hash"] = "sha256:" + "9" * 64

    result = service.base_capability_proposal_search({"limit": 1}, _context(super_admin=True))

    assert result["items"][0]["review_evidence"] == {}
