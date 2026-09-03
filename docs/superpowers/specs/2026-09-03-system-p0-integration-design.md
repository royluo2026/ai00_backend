# System P0 Integration Design

## Goal

Prepare the reviewed Agent and Simulation domains for functional testing on the local `test` branches, add one repeatable cross-domain P0 integration suite, and keep incomplete Orchestration and governance-release work outside the integration boundary.

## Authoritative baselines

- Backend: `E:/Projects/ai00_v3/.worktrees/capability-v2-implementation`, branch `test`, starting at `6144cc14`.
- Frontend: `E:/Projects/ai00/workmanship-web`, branch `test`, starting at `7613b66`.
- Backend `test` already contains the reviewed Agent and Simulation commits. They must not be re-merged or cherry-picked.
- `E:/Projects/ai00_v3/workmanship-web/.worktrees/test` is not an integration target because it is an older independent checkout with an unfinished merge.

## Integration boundary

The integrated backend keeps the reviewed Agent stream, transaction, durable-outbox, reconciliation, migration, Simulation Connector ownership, pairing, plan-worker, projection-outbox, and migration changes already present in `test`.

The frontend receives only the final reviewed Simulation UI delta needed to align the authoritative source tree with the packaged backend web assets: governed capture and pairing surfaces, and fail-closed removal of production localhost Bridge entry points. Existing Agent UI changes already present in frontend `test` remain untouched.

The following remain isolated:

- Ontology work.
- Orchestration Capability Gate 0 and its backend/frontend feature branches.
- Orchestration migrations currently numbered `0005/0006`; these conflict with the released Agent outbox migrations and require a later replay as `0007/0008`.
- Catalog, provider freeze, generated Capability docs, acceptance manifests, signed reports, Snapshots, and approval evidence.

No worktree or branch containing uncommitted files is force-removed.

## Two-layer verification

### Layer 1: deterministic P0 integration

Add `backend/tests/integration/test_agent_simulation_runtime_recovery.py` and reuse production composition rather than creating another mock Gateway.

The suite contains two live-database scenarios guarded by the existing integration environment controls:

1. Start `backend.main.app` through `TestClient` lifespan, seed a committed Agent outbox item and a Base `outcome_unknown` record, then verify the registered `agent.capability-outbox` lifecycle reconciles the Base outcome exactly once and marks the Agent row delivered.
2. Compose the production `ConnectorProjectionWorker` with `GovernedSimulationRuntimeClient(get_default_gateway())`, verify a committed Simulation projection intent reaches its target exactly once, and verify failure followed by retry/stale reclaim does not duplicate the result.

The normal offline gate also runs the already committed focused tests for:

- Agent stream close/deadline/lease cleanup and outbox migration upgrade.
- Simulation outcome/outbox atomicity, stale reclaim, pairing approval CAS, worker registration, and migration upgrade.
- Domain dependency and migration discovery checks.
- Frontend Agent capability flow and Simulation capture boundary tests.
- .NET Connector tests from a fresh source build.

Live tests are reported as `skipped` when their required test database URLs are absent; skipped is never reported as runtime verification.

### Layer 2: live functional smoke

After deterministic verification:

1. Start backend, frontend, Agent outbox lifecycle, and the independent Simulation projection worker.
2. Verify Agent settings load and test-connection response, open the assistant UI, and exercise normal stream, cancellation, timeout, one successful write, and one failed write rollback without sending a real external message.
3. Complete Connector browser pairing, start Connector and SessionHost, start VisMockup, and execute the governed capture flow from the production UI.
4. Inspect browser network requests and assert the governed capture path uses only Capability Gateway calls and produces no localhost Bridge request.
5. Record environment failures separately from code failures.

## P0 decision rule

A failure is P0 only when it prevents the reviewed Agent or Simulation functional flow from running, can write incorrect/duplicate data, breaks authentication or identity binding, leaks a runtime resource indefinitely, or makes an existing database unable to upgrade.

Incomplete Orchestration Gate 0, stale release evidence, missing human approval, and unavailable external runtime configuration do not fail the functional P0 code gate. They remain separately reported as `unverified` or environment blockers.

## Governance status

This integration is an implementation-fix verification. AI conclusions are advisory. `machine_passed`, `human_approved`, and `runtime_verified` are reported independently; no Catalog release, approval, or signed evidence is created by this work.
