# Simulation Connector Runtime Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first real web-to-VisMockup simulation environment and reverse-capture path without changing the generic Capability governance framework.

**Architecture:** Keep business orchestration in `simulation`, adapt existing Craft/Knowledge/Device capabilities through typed owner-domain ports, and keep COM execution in the bound-user SessionHost. Use short per-operation capture plans, verified ArtifactRefs, durable outcome projection, and a Connector heartbeat loop independent of plan execution.

**Tech Stack:** Python 3/FastAPI/Pydantic/MySQL, .NET 8 Worker Service/Windows named pipes/COM/WiX 5, browser JavaScript.

**Spec:** `docs/superpowers/specs/2026-09-03-simulation-connector-runtime-closure-design.md`

## Global Constraints

- Do not modify generic Registry, Catalog generation, governance scanner, approval, or Release Gate behavior.
- Reuse `craft.bop.execution_structure.get@1`, `craft.process_screenshot.attach@1`, and `knowledge.resource_model_mapping.resolve@1`.
- Browser code must not call localhost for the governed workflow.
- Local paths and secrets must never cross the Connector outcome boundary.
- `machine_passed`, `human_approved`, and `runtime_verified` remain independent.
- Preserve unrelated working-tree changes and stage only files owned by this plan.

---

### Task 1: Bind real owner-domain ports into Simulation

**Files:**
- Create: `plugins/craft/craft_backend/public_ports/simulation_execution.py`
- Create: `plugins/knowledge/knowledge_backend/public_ports/resource_model_mapping.py`
- Create: `plugins/device/device_backend/public_ports/simulation_connector.py`
- Create: `plugins/simulation/simulation_backend/application/runtime_ports.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/__init__.py`
- Test: `backend/tests/test_simulation_runtime_port_bindings.py`

**Interfaces:**
- Produce typed implementations of `CraftExecutionPlanPort`, `ResourceModelMappingPort`, `ActiveDocumentSnapshotPort`, Connector plan queue, and Craft screenshot command port.
- Owner adapters call existing public Capability/provider surfaces and preserve `CapabilityContext`; Simulation does not import owner repositories or tables.
- Production `register_capabilities()` constructs real providers; `_Unavailable*Port` remains test/fail-closed fallback only.

- [ ] Write a production-registration test proving compose/capture handlers are not backed by `_Unavailable*Port`.
- [ ] Run the test and confirm it fails because default providers are unavailable placeholders.
- [ ] Implement the smallest owner-domain adapters and Simulation composition root.
- [ ] Run the focused tests and existing domain-boundary tests.
- [ ] Commit only Task 1 files.

### Task 2: Persist and consume the current VisMockup document snapshot

**Files:**
- Modify: `plugins/simulation/simulation_backend/application/capture_worker.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/environment_composition.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `plugins/simulation/simulation_backend/data/environment_repository.py`
- Modify: `plugins/simulation/simulation_backend/domain/environment_manifest.py`
- Modify: `plugins/simulation/simulation_backend/routers/environments.py`
- Modify: relevant Simulation migration under `backend/db/migrations/domains/simulation/`
- Test: `backend/tests/test_simulation_document_snapshot_workflow.py`
- Test: `backend/tests/test_simulation_environment_composition_capabilities.py`

**Interfaces:**
- Produce an asynchronous request/status flow backed by a Connector plan containing `vismockup.document.snapshot@1`.
- Persist immutable snapshot identity, hash, document identity, node ordering, and product references.
- Compose consumes a confirmed snapshot reference, not an invented synchronous local read.

- [ ] Write failing tests for request idempotency, pending/completed state, document change, product binding, and unauthorized visibility.
- [ ] Run them and confirm the missing workflow/binding failures.
- [ ] Implement snapshot persistence and workflow using existing Connector Plan operations; add a new Capability only if reuse cannot express the independently observable business effect.
- [ ] Add/adjust migration and governance metadata only for Simulation-owned facts.
- [ ] Run focused, migration, contract, and boundary tests.
- [ ] Commit only Task 2 files.

### Task 3: Project signed Connector outcomes into Simulation and Craft

**Files:**
- Modify: `plugins/device/device_backend/capabilities/connector_runtime.py`
- Modify: `plugins/simulation/simulation_backend/application/capture_worker.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/capture_runs.py`
- Modify: `plugins/simulation/simulation_backend/data/environment_repository.py`
- Test: `backend/tests/test_connector_simulation_outcome_projection.py`
- Test: `backend/tests/test_simulation_capture_workflow.py`

**Interfaces:**
- Device completion emits a narrow trusted completion callback/port after signature and lease validation.
- Simulation maps plan/step IDs to snapshot, materialization, or capture runs; duplicate identical outcomes are no-ops and conflicting outcomes fail.
- Confirmed image ArtifactRefs advance Capture Run and call `craft.process_screenshot.attach@1` exactly once.

- [ ] Write failing tests for completed, failed, outcome-unknown, duplicate, conflict, and restart replay cases.
- [ ] Verify the tests fail because completion currently only stores JSON in the Device table.
- [ ] Implement durable projection and idempotent Craft attachment.
- [ ] Run focused tests and cross-domain ownership checks.
- [ ] Commit only Task 3 files.

### Task 4: Make Connector heartbeat independent and accurate

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Service/ConnectorHealthReporter.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/RuntimeWorker.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/Program.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/SessionHostSupervisor.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/ConnectorHeartbeatTests.cs`

**Interfaces:**
- `ConnectorHealthReporter` sends Connector-specific health on its own timed loop.
- Health reports bound user/session, SessionHost readiness, system awake state, protocol version, actual Adapter manifest and actual product version.
- Long plan execution cannot pause heartbeat.

- [ ] Write failing tests with a blocked executor and advancing fake clock.
- [ ] Confirm no Connector heartbeat is sent by current code.
- [ ] Implement the independent reporter using existing `BackgroundService` and `ConnectorGatewayClient`.
- [ ] Run Connector heartbeat and server compatibility tests.
- [ ] Commit only Task 4 files.

### Task 5: Integrate verified input and output Artifact transfer

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Service/HttpArtifactTransport.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/ArtifactTransfer.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/PlanSessionHostClient.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/ConnectorGatewayClient.cs`
- Modify: `local-runtime/src/Ai00.Connector.Service/Program.cs`
- Modify: `local-runtime/src/Ai00.Connector.Contracts/ExecutionPlan.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/PlanArtifactPipelineTests.cs`
- Test: `backend/tests/test_connector_execution_plan_v1.py`

**Interfaces:**
- Before SessionHost execution, download every authorized input ArtifactRef, verify size/hash, and inject `local_artifact_path` only into a local execution copy.
- Upload `LocalCaptureArtifact`, reconcile ambiguous uploads, and replace it with server ArtifactRef before signing outcome.
- Reject any outcome containing a local path.

- [ ] Write failing tests for integrity mismatch, URL authorization, local-only payload injection, upload reconciliation, and path leakage.
- [ ] Confirm `ArtifactTransfer` is currently unregistered and unused.
- [ ] Implement HTTP transport and Plan executor integration without adding a new dependency.
- [ ] Run .NET and Python contract tests.
- [ ] Commit only Task 5 files.

### Task 6: Bound plan duration and enforce step timeout

**Files:**
- Modify: `plugins/simulation/simulation_backend/application/connector_plans.py`
- Modify: `plugins/simulation/simulation_backend/application/capture_worker.py`
- Modify: `local-runtime/src/Ai00.Connector.SessionHost/AdapterDispatcher.cs`
- Test: `backend/tests/test_simulation_capture_workflow.py`
- Test: `local-runtime/tests/Ai00.Connector.Tests/PlanRecoveryTests.cs`

**Interfaces:**
- Capture queues one operation's apply/verify/capture chain per Plan in descending process order.
- The next Plan is queued only after confirmed completion and attachment of the prior operation.
- SessionHost enforces each step's `timeout_seconds`; timeout becomes `outcome_unknown` and is never auto-replayed.

- [ ] Write failing ordering, lease-window, timeout, and recovery tests.
- [ ] Confirm the current multi-operation 15-minute Plan and unenforced step timeout fail those expectations.
- [ ] Implement short-plan progression and timeout enforcement.
- [ ] Run workflow and recovery tests.
- [ ] Commit only Task 6 files.

### Task 7: Align VisMockup contracts with the real product

**Files:**
- Modify: `plugins/simulation/simulation_backend/domain/environment_manifest.py`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/DocumentSnapshotReader.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/VisMockupCaptureTests.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/VisMockupSnapshotTests.cs`
- Test: `backend/tests/test_simulation_environment_manifest.py`

**Interfaces:**
- Plan compatibility accepts advertised VisMockup 14.x and rejects other major versions.
- Snapshot JSON contains stable snake_case product references required by composition.
- First release supports exactly PNG 1920×1080 with current background, or returns a stable unsupported-profile error.
- Visibility verification uses actual visibility state.

- [ ] Write failing cross-language compatibility and serialization tests.
- [ ] Confirm the current `>=1,<2` requirement rejects Adapter `14.0.0` and capture profile is a no-op.
- [ ] Implement the minimum verified VisMockup 14 behavior; do not claim JPEG/transparent/arbitrary-size support.
- [ ] Run Adapter and Simulation manifest tests.
- [ ] Commit only Task 7 files.

### Task 8: Produce an installable single-user Connector

**Files:**
- Modify: `local-runtime/appsettings.example.json`
- Modify: `local-runtime/installer/Product.wxs`
- Modify: `local-runtime/installer/Ai00.Connector.wixproj`
- Modify: `local-runtime/src/Ai00.Connector.Service/Program.cs`
- Add the smallest required installer custom action/helper only if WiX native elements cannot activate and bind the device safely.
- Test: `local-runtime/tests/Ai00.Connector.Tests/InstallerContractTests.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/SessionOwnershipTests.cs`

**Interfaces:**
- MSI installs complete publish outputs, Windows Service, bound-user SessionHost startup, config, and restricted ProgramData directories.
- Named pipe ACL permits only service SID and bound user SID.
- Enrollment activation persists DPAPI credentials; operation signing keys are provisioned without being written to sample JSON.

- [ ] Write failing tests for complete payload, config section, startup registration, ACL identities, and activation artifacts.
- [ ] Confirm the current MSI installs only three EXEs, writes only a registry marker, and cannot cross `CurrentUserOnly`.
- [ ] Implement the smallest native WiX/Windows solution.
- [ ] Build MSI and run installer contract tests.
- [ ] Commit only Task 8 files.

### Task 9: Make the governed Web flow cloud-only

**Files:**
- Modify: `dist/packages/sim-plugin/web/cad_sim/capture_workflow.js`
- Modify: `dist/packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify: `dist/packages/sim-plugin/web/cad_sim/index.html` only if controls change.
- Test: `dist/packages/sim-plugin/web/cad_sim/capture_workflow.test.js`

**Interfaces:**
- The governed flow requests snapshot, composes/preflights, starts capture, and polls authoritative status through `_cloudFetch`.
- It defaults to the one healthy bound device but keeps identity visible.
- No governed-flow call reaches `_bridge` or `127.0.0.1`.

- [ ] Write failing browser-library tests for snapshot pending/completion and absence of localhost calls.
- [ ] Implement the minimal state-machine/UI changes.
- [ ] Run Node tests and syntax checks.
- [ ] Commit only Task 9 files.

### Task 10: Verification and governance handoff

**Files:**
- Modify generated governance artifacts only through repository generators and only when Simulation-owned descriptors changed.
- Create/update runtime pilot evidence under the repository's existing governed evidence location only after a real run.

- [ ] Run focused Python tests for Simulation, Device, Craft, and Knowledge.
- [ ] Run `.NET 8` Release build and tests after restoring the missing `Microsoft.CodeCoverage` package.
- [ ] Run Web Node tests and production build.
- [ ] Run Catalog/docs/acceptance generators in `--check` mode, domain dependency audit, and strict offline acceptance.
- [ ] Build MSI.
- [ ] Run the VisMockup pilot on the installed workstation; separately record unlocked, locked, network-loss, Service-restart, and SessionHost-restart outcomes.
- [ ] Report exact passed/failed/skipped/unavailable results and independent governance states.
- [ ] Send commit range, Capability identities, ownership impact, raw commands, and unresolved risks to `codex://threads/01a0183f-f392-7d73-a4e6-d5822122fe5d` for review.
