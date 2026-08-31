from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.authorization import AuthorizationGrants
from backend.capability_v2.catalog import CatalogResolver, build_release
from backend.capability_v2.catalog_store import InMemoryCatalogStore
from backend.capability_v2.contracts import (
    ActorIdentity,
    CapabilityStatus,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.capability_v2.operations import InMemoryOperationStore, OperationService
from backend.capability_v2.outcomes import InMemoryOutcomeStore
from backend.capability_v2.policies import LegacyServerGatewayPolicy
from backend.capability_v2.reliability import (
    ApprovalService,
    InMemoryApprovalStore,
    InMemoryRateLimiter,
    ReliabilityCoordinator,
)
from backend.tests.test_craft_rule_definition_change_capability import (
    MemoryRuleDefinitionRepository,
)
from plugins.craft.craft_backend.capabilities import register_capabilities


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_FIXTURE = ROOT / "backend/tests/fixtures/craft_rule_reference_projection.json"
EVALUATE_CAPABILITY_ID = "craft.rule.entry.evaluate"
CHANGE_CAPABILITY_ID = "craft.rule.definition.change.apply"


def test_registered_craft_rule_gateway_lifecycle_is_exact_and_idempotent(monkeypatch):
    from plugins.craft.craft_backend.capabilities import rule_engine, rule_library

    reference = json.loads(REFERENCE_FIXTURE.read_text(encoding="utf-8"))
    revision = reference["rule_reference"]["rule_revision"]
    projected = rule_library._row({
        "gid": reference["rule_gid"],
        "rule_definition": {"_revision": revision},
    })
    assert {key: projected[key] for key in reference} == reference

    repository = MemoryRuleDefinitionRepository(rule={
        "gid": reference["rule_gid"],
        "owner_user_gid": "owner-1",
        "team_gid": "team-a",
        "revision": revision,
        "name": "Original",
        "description": "old",
        "severity": "warning",
        "enabled": True,
        "expression": "quantity > 0",
        "message": "old message",
        "scope": "team",
        "tags": ["old"],
        "priority": 1,
        "category": "process",
    })
    monkeypatch.setattr(rule_library, "rule_definition_repository", repository)

    def load_visible_rule(rule_gid, user_gid, team_gid):
        rule = repository.rules[rule_gid]
        if rule["owner_user_gid"] != user_gid or rule["team_gid"] != team_gid:
            raise LookupError("rule not found")
        return {
            **rule,
            "share_scope": "team",
            "rule_definition": {"_revision": rule["revision"]},
        }

    monkeypatch.setattr(rule_engine, "load_visible_rule", load_visible_rule)
    monkeypatch.setattr(
        rule_engine,
        "_run_isolated_check",
        lambda *_args: rule_engine.RuleResult.PASS.value,
    )

    registry = CapabilityRegistry()
    register_capabilities(registry)
    release = build_release([
        item.descriptor for item in registry.snapshot() if item.descriptor is not None
    ])
    catalog = InMemoryCatalogStore()
    catalog.publish(release)
    policy = LegacyServerGatewayPolicy(
        user_loader=lambda user_gid: {"gid": user_gid, "is_active": True},
        grants_resolver=lambda identity, _user: AuthorizationGrants(
            permissions=("craft.read", "craft.rule.write"),
            capability_scopes=("*",),
            resource_scopes=("*",),
            data_scopes=("*",),
            policy_version="craft-rule-gateway-test",
            tenant_id=identity.tenant.tenant_id,
        ),
        approval_service=ApprovalService(InMemoryApprovalStore()),
    )
    gateway = CapabilityGatewayService(
        CatalogResolver(catalog, registry),
        policy,
        reliability=ReliabilityCoordinator(
            InMemoryOutcomeStore(), InMemoryRateLimiter(limit=100),
        ),
        operations=OperationService(InMemoryOperationStore()),
    ).bind_release(release.release_id)
    identity = ConsumerIdentity(
        actor=ActorIdentity(
            user_id="owner-1",
            authentication_method="session",
            authenticated_at=datetime.now(UTC),
        ),
        tenant=TenantIdentity(tenant_id="team-a", membership="member"),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )

    def envelope(
        capability_id,
        payload,
        *,
        key=None,
        confirmation=None,
        expected_version=None,
        major_version=1,
        request_id="craft-rule-request",
    ):
        return InvocationEnvelope(
            capability_id=capability_id,
            major_version=major_version,
            catalog_release=release.release_id,
            payload=payload,
            identity=identity,
            idempotency_key=key,
            expected_resource_version=expected_version,
            approval_reference=confirmation,
            request_id=request_id,
            trace_id="craft-rule-trace",
        )

    rule_reference = projected["rule_reference"]
    evaluation_payload = {
        **rule_reference,
        "entry": {"quantity": 2},
    }
    evaluation = asyncio.run(gateway.invoke(envelope(
        EVALUATE_CAPABILITY_ID,
        evaluation_payload,
    )))
    assert evaluation.ok is True and evaluation.status is CapabilityStatus.COMPLETED
    assert evaluation.data == {
        "passed": True,
        "rule_revision": revision,
        "diagnostics": [],
    }

    change_payload = {
        "rule_gid": rule_reference["rule_gid"],
        "expected_revision": rule_reference["rule_revision"],
        "changes": {"name": "Stable"},
    }
    pending = envelope(
        CHANGE_CAPABILITY_ID,
        change_payload,
        key="craft-rule-change-1",
        expected_version=str(revision),
    )
    initial = asyncio.run(gateway.invoke(pending))
    issued = asyncio.run(gateway.request_approval(pending))
    confirmed = asyncio.run(gateway.invoke(pending.model_copy(update={
        "approval_reference": issued.token,
    })))
    replay = asyncio.run(gateway.invoke(pending.model_copy(update={
        "request_id": "craft-rule-replay",
    })))

    assert initial.error.code == "confirmation_required"
    assert issued.challenge.capability_id == CHANGE_CAPABILITY_ID
    assert issued.challenge.major_version == 1
    assert confirmed.ok is True and confirmed.status is CapabilityStatus.COMPLETED
    assert confirmed.data["rule_gid"] == reference["rule_gid"]
    assert confirmed.data["revision"] == revision + 1
    assert confirmed.data["name"] == "Stable"
    assert replay.data == confirmed.data
    assert repository.rules[reference["rule_gid"]]["revision"] == revision + 1
    assert repository.commits == 1
    assert len(repository.operations) == 1
    assert len(repository.audits) == 1
    assert len(repository.results) == 1

    stale_pending = envelope(
        CHANGE_CAPABILITY_ID,
        change_payload,
        key="craft-rule-change-stale",
        expected_version=str(revision),
        request_id="craft-rule-stale",
    )
    stale_approval = asyncio.run(gateway.request_approval(stale_pending))
    stale = asyncio.run(gateway.invoke(stale_pending.model_copy(update={
        "approval_reference": stale_approval.token,
    })))
    assert stale.error.code == "revision_conflict"
    assert repository.commits == 1
    assert len(repository.operations) == 1
    assert len(repository.audits) == 1

    open_payload = asyncio.run(gateway.invoke(envelope(
        EVALUATE_CAPABILITY_ID,
        {**evaluation_payload, "source": "quantity > 0"},
        request_id="craft-rule-open-payload",
    )))
    open_change_payload = asyncio.run(gateway.invoke(envelope(
        CHANGE_CAPABILITY_ID,
        {**change_payload, "compiled": "forged"},
        key="craft-rule-open-change-payload",
        expected_version=str(revision),
        request_id="craft-rule-open-change-payload",
    )))
    wrong_expected_version = asyncio.run(gateway.invoke(envelope(
        CHANGE_CAPABILITY_ID,
        change_payload,
        key="craft-rule-wrong-version",
        expected_version="999",
        request_id="craft-rule-wrong-version",
    )))
    wrong_major = asyncio.run(gateway.invoke(envelope(
        EVALUATE_CAPABILITY_ID,
        evaluation_payload,
        major_version=2,
        request_id="craft-rule-wrong-major",
    )))

    assert open_payload.error.code == "invalid_input"
    assert open_change_payload.error.code == "invalid_input"
    assert wrong_expected_version.error.code == "expected_resource_version_mismatch"
    assert wrong_major.error.code == "catalog_resolution_failed"
    assert repository.commits == 1
    assert len(repository.operations) == 1
    assert len(repository.audits) == 1
