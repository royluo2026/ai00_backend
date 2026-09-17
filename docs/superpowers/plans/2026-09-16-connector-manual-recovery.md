# Connector Manual Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Give the authenticated device owner an actionable, audited recovery path for uncertain VisMockup document-open operations without replaying them.

**Architecture:** Simulation-owned Gateway capabilities list unresolved operations and record a human disposition. Keep the signed runtime outcome immutable; cancel further processing of that exact plan and append a separate human-review audit. The Connector consumes the existing authoritative closed-plan recovery response and acknowledges the old journal entry. UI uses existing document association after an executed disposition; it never represents an association as successful before the existing binding flow succeeds.

**Tech Stack:** Python Capability Gateway and MySQL test tables, .NET Connector journal, JavaScript simulation UI.

**Spec:** User-approved design in this task: status-adjacent handling button; identify the failed operation; choices not executed / executed and associate / defer; preserve audit; no automatic retry.

## Global Constraints
- Use the current env with `TABLE_PREFIX=test_`; production is out of scope.
- No direct editing of live plan state or local journal during diagnosis/deployment.
- No Teamcenter product writes, VisMockup reload, or model/document deletion.
- Do not turn a human assertion into a signed runtime-success outcome.
- New capabilities are web-human-only, owner/tenant-scoped, with user confirmation, exact outcome-hash/generation preconditions, and idempotency for disposition.
- Only uncertain document-open/insert operations are eligible initially; other operations remain explicitly unsupported.
- A cancelled reviewed plan is never re-enqueued. A separate explicit user action is required for any new operation.

## Task 1: Governed recovery contracts and persistence
Files: `plugins/simulation/simulation_backend/capabilities/connector_contracts.py`, `connector_runtime.py`, `provider.py`; `data/connector_repository.py`; `backend/tests/test_simulation_connector_runtime_v2_sql.py`.

Interfaces: `simulation.connector.recovery.search@1` returns up to 20 owner-scoped unresolved plans with plan ID, device/generation, outcome hash, operation and safe error. `simulation.connector.recovery.resolve@1` takes that exact identity, decision (`not_executed` or `executed`), and required reason; returns audit reference and `retry_started:false`.

- [ ] Test on existing real-SQL fixture: list scoping; owner refusal; stale generation/hash; ineligible operation; resolving does not modify signed outcome; repeated exact decision replays; conflicting decision refuses.
- [ ] Implement device-first locks, then exact plan lock. Store decision in existing runtime audit, preserving original signed outcome/hash. Mark only that plan cancelled with a human-review reconciliation marker. Do not clear other pending plans or create new plans.
- [ ] Register closed schemas, web-only exposure, resource scopes, business effect/invariants and confirmation; regenerate and check Catalog/Provider metadata.

## Task 2: Connector recovery acknowledgement
Files: `local-runtime/src/Ai00.Connector.AppHost/RuntimeSessionWorker.cs`, `PlanExecutionWorker.cs`; corresponding outcome-recovery tests.

- [ ] Verify closed-plan recovery response is accepted only through authenticated server transport and exact plan identity.
- [ ] Test acknowledgement skips the old journal entry after restart, preserves its signed outcome, does not execute the operation again, and leaves unrelated uncertain plans blocked.
- [ ] Prefer existing obsolete-recovery handling; change it only if the tests show a real gap. Do not forge successful probe evidence.

## Task 3: Visible user handling entry
Files: frontend `packages/sim-plugin/web/cad_sim/connector_recovery.js` and tests, `cad_sim.js`, `index.html`, styles only as needed.

- [ ] Test with DOM: entry available even while Connector is not ready; loading/empty/failure states; operation identity and safe error shown; confirmation required; prevent double submit.
- [ ] Add `处理未完成操作` by the connection state. Fetch unresolved server state through Gateway, not desktop-only IPC.
- [ ] Not executed records the human decision. Executed records the decision then opens the existing document chooser; association remains a separate verified flow. Defer changes nothing.
- [ ] On success refresh connection status; never call online launch/insert automatically. If more unresolved plans exist, keep the entry and explain remaining blockers.

## Task 4: Verification and controlled deployment
- [ ] Run contract/SQL authorization and idempotency tests, .NET recovery tests, full CAD UI tests, and test-governance build.
- [ ] Check current test Catalog and Provider artifact binding; keep `machine_passed`, `human_approved`, and `runtime_verified` separate. Do not manufacture approval for new capability hashes.
- [ ] Restart only the test App/Connector if required, preserving VisMockup. User performs the real manual decision in UI. Read back audit, closed-plan acknowledgement, and ready state before claiming runtime completion.

## Governance record
Classification: new, Simulation-owned recovery read and human disposition capabilities. Provider: simulation.provider. Consumer: official.sim web UI only. Existing owned runtime plans/audit tables; no new domain or migration planned. Current runtime evidence: old launch failed with missing Java class, server/local recovery is manual-review-required; no manual disposition has been executed. New capability GIDs, exact hashes, release approval and runtime end-to-end verification remain unverified until generated/tested through the repository workflow.
