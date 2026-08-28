from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.capability_v2.contracts import (
    ActorIdentity, CapabilityStatus, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    CorrelationRef, TenantIdentity,
)
from backend.capability_v2.domain_client import DomainCapabilityClient
from plugins.integration.integration_backend.application.sync import ImportDispatcher, SyncService


def identity(owner: str, team: str) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(user_id=owner, authentication_method="persisted-integration-operation", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id=team, membership="persisted-operation"),
        consumer=ConsumerDescriptor(type=ConsumerType.WORKER, consumer_id="domain.integration.import-worker"),
    )


class Client(DomainCapabilityClient):
    def __init__(self, statuses=(CapabilityStatus.COMPLETED,)):
        self.calls = []
        self.statuses = list(statuses)

    async def invoke(self, invocation, principal, correlation, deadline=None):
        self.calls.append((invocation, principal))
        status = self.statuses.pop(0)
        return SimpleNamespace(ok=status is CapabilityStatus.COMPLETED, status=status, data={"version": 1}, error=None)


class RunRepository:
    def __init__(self, runs):
        self.runs = runs

    def claim_next_import_run(self, worker):
        for run in self.runs:
            if run["status"] in {"accepted", "reconcile_pending"}:
                run.update(status="claimed", claim_token=f"{worker}:{run['run_id']}")
                return dict(run)
        return None

    def get_mapping(self, data):
        return {"gid": data["gid"], "datasource_gid": f"ds-{data['owner_gid']}", "status": "active",
                "target_domain": "knowledge", "field_mappings": []}

    def get_connector(self, data):
        return {"gid": data["gid"]}

    def mark_target_invocation(self, **data):
        run = next(row for row in self.runs if row["run_id"] == data["run_id"])
        run.update(target_invocation=data["target_invocation"], target_dispatched_at=datetime.now(UTC),
                   target_idempotency_key=data["target_idempotency_key"])
        return {"target_dispatched_at": run["target_dispatched_at"], "target_idempotency_key": run["target_idempotency_key"]}

    def transition_import_run(self, **data):
        run = next(row for row in self.runs if row["run_id"] == data["run_id"])
        run["status"] = data["status"]
        return {"run_id": run["run_id"], "status": run["status"]}

    def record_import_uncertainty(self, **data):
        run = next(row for row in self.runs if row["run_id"] == data["run_id"])
        run["status"] = "reconcile_pending"
        run["attempt_count"] = int(run.get("attempt_count", 0)) + 1
        return {"run_id": run["run_id"], "status": run["status"], "attempt_count": run["attempt_count"]}


class Runtime:
    async def preview(self, *_args, **_kwargs):
        return {"rows": []}


class Catalog:
    def require_stable(self, *_args):
        return None


def run(owner, team, suffix):
    return {"run_id": f"run-{suffix}", "mapping_gid": f"mapping-{suffix}", "owner_gid": owner,
            "team_gid": team, "status": "accepted", "target_invocation": {
                "capability_id": "knowledge.reference_dataset.publish", "major_version": 1,
                "minimum_catalog_release": "rel_floor", "payload": {"dataset_gid": f"dataset-{suffix}"},
            }}


def test_multi_tenant_concurrent_dispatch_uses_each_persisted_principal_and_rejects_static_mismatch():
    runs, client = [run("actor-a", "team-a", "a"), run("actor-b", "team-b", "b")], Client((CapabilityStatus.COMPLETED,) * 2)
    repository = RunRepository(runs)
    dispatcher = ImportDispatcher(repository, Runtime(), SyncService(client, Catalog()),
                                  lambda item: identity(item["owner_gid"], item["team_gid"]))

    async def execute():
        return await asyncio.gather(*(
            dispatcher.dispatch_next(worker_id=f"worker-{i}", correlation=CorrelationRef(request_id=f"request-{i}"))
            for i in range(2)
        ))

    asyncio.run(execute())
    assert {(call[1].actor.user_id, call[1].tenant.tenant_id) for call in client.calls} == {
        ("actor-a", "team-a"), ("actor-b", "team-b")
    }

    bad_run, bad_client = run("actor-b", "team-b", "bad"), Client()
    bad = ImportDispatcher(RunRepository([bad_run]), Runtime(), SyncService(bad_client, Catalog()),
                           lambda _item: identity("actor-a", "team-a"))
    result = asyncio.run(bad.dispatch_next(worker_id="worker-a", correlation=CorrelationRef(request_id="request-bad")))
    assert result["status"] == "failed" and bad_client.calls == []


def test_outcome_unknown_reclaims_exact_invocation_and_idempotency_without_reextracting():
    item = run("actor-a", "team-a", "unknown")
    repository, runtime = RunRepository([item]), Runtime()
    client = Client((CapabilityStatus.OUTCOME_UNKNOWN, CapabilityStatus.COMPLETED))
    dispatcher = ImportDispatcher(repository, runtime, SyncService(client, Catalog()),
                                  lambda row: identity(row["owner_gid"], row["team_gid"]))

    first = asyncio.run(dispatcher.dispatch_next(worker_id="worker", correlation=CorrelationRef(request_id="request-1")))
    second = asyncio.run(dispatcher.dispatch_next(worker_id="worker", correlation=CorrelationRef(request_id="request-2")))

    assert first["status"] == "reconcile_pending" and second["status"] == "succeeded"
    assert client.calls[0][0].idempotency_key == client.calls[1][0].idempotency_key
    assert client.calls[0][0].payload == client.calls[1][0].payload
