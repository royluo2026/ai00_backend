# Connector Push Wake-up and VM Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wake AI00 Connector immediately for queued work and load the VM structure tree through governed document snapshots.

**Architecture:** A Simulation-owned WebSocket sends wake-only events while existing HTTP lease/signature/outcome paths remain authoritative. The web page uses the existing document snapshot Capability workflow and converts its flat bounded snapshot into the current tree UI model.

**Tech Stack:** FastAPI WebSocket, .NET 8 `ClientWebSocket`, Python/pytest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-07-connector-push-and-vm-tree-design.md`

## Global Constraints

- Do not restore browser access to a workstation loopback service.
- Do not put plans, tokens, or business payloads on the wake socket.
- Preserve signed plan leasing, idempotency, bounded snapshot limits, and exact Capability provenance.
- Keep two-second polling only as failure recovery.

---

### Task 1: Backend Connector wake broker and WebSocket

**Files:**
- Create: `plugins/simulation/simulation_backend/application/connector_wakeup.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Modify: `backend/routers/simulation_connector.py`
- Test: `backend/tests/test_connector_runtime_control_plane.py`

**Interfaces:**
- Produces: `connector_wake_broker.subscribe(connector_id)` and `notify(connector_id)`.
- Produces: authenticated `/api/v1/simulation/connectors/plans/wake` WebSocket.

- [ ] Write tests showing queue insertion notifies only the target Connector and subscriptions receive bounded wake signals.
- [ ] Run the targeted pytest tests and confirm the new assertions fail because the broker/notifier does not exist.
- [ ] Implement the thread-safe in-process wake broker, queue notification, authenticated WebSocket, and keepalive.
- [ ] Run the targeted pytest tests and confirm they pass.

### Task 2: Connector push client and immediate queue draining

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Service/ConnectorPlanWakeClient.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/PlanWorker.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/Program.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/PlanRecoveryTests.cs`

**Interfaces:**
- Produces: `IConnectorPlanWakeSignal.WaitAsync(TimeSpan, CancellationToken)`.
- Changes: `PlanWorker.StartOnceAsync` returns `true` when it handled work.

- [ ] Write tests proving handled work returns `true`, an empty lease returns `false`, and queued plans are requested again without a fixed sleep.
- [ ] Run the targeted .NET tests and confirm failure against the old `Task` API.
- [ ] Implement the persistent authenticated WebSocket client and wake-or-fallback worker loop.
- [ ] Run the Connector test project and confirm all tests pass.

### Task 3: Governed VM snapshot consumer

**Files:**
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Create: `packages/sim-plugin/web/cad_sim/cad_sim_vm_tree.test.js`

**Interfaces:**
- Consumes: `simulation.document_snapshot.request@2`, `action.get@1`, `dispatch@1`, and `get@1`.
- Produces: `_snapshotToVisTree(snapshot)` for the existing renderer.

- [ ] Write a Node test proving the tree loader has no `_bridge('vis_mockup', 'get_vis_tree')` call and a flat snapshot renders in parent/child order.
- [ ] Run the test and confirm it fails against the legacy Bridge loader.
- [ ] Implement prepare, exact-plan confirmation, dispatch, result polling, and flat-to-tree conversion.
- [ ] Run the Node test and syntax check and confirm both pass.

### Task 4: Integration verification and deployment

**Files:**
- Rebuild/deploy the existing Connector installation; no new source file.

- [ ] Run backend control-plane tests, Connector tests, frontend tests, Catalog check, and Capability docs check.
- [ ] Rebuild and deploy Connector, restart its tray/session host, and verify presence.
- [ ] Use the browser to load the VM tree and execute full-hide/full-show.
- [ ] Measure queue-created-to-step-start latency and report raw evidence separately from approval status.
