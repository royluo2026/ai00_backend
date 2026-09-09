# Digital Simulation Environment Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private, versioned AI00 simulation workspace that projects immutable Teamcenter/PLMXML references, controls VisMockup through governed Connector v2 plans, creates one reverse-order image per process, and selectively publishes approved changes into a Craft BOP draft.

**Architecture:** The cloud Simulation domain owns workspaces, VM document/session/snapshot facts, occurrence identity, poses, bindings, frozen manifests, comparisons, capture orchestration, and publish mappings. Craft, Knowledge, Digital Model, and Base Platform remain authoritative for their own data. Every local VisMockup effect follows Renderer → Gateway → Simulation Provider → signed execution-plan.v2 → ConnectorHost journal/Adapter → COM → signed Outcome v2.

**Tech Stack:** Python/FastAPI domain plugins, MySQL versioned migrations, .NET 8 Windows x64 ConnectorHost and COM Adapter, Electron/Vite/vanilla JavaScript UI, pytest, xUnit, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md`

## Global Constraints

- Work only on frontend/backend `test` worktrees; do not merge or publish.
- New Capability candidates remain experimental/advisory. Do not request human approval or mark `human_approved`, `machine_passed`, or `runtime_verified` true.
- G0–G6 in the spec are mandatory checkpoints; a failed Gate blocks dependent work.
- Windows x64 only; cloud backend remains remote; no local business server.
- Persistent GIDs come from `backend.platform_sdk.ids.next_gid()` and travel to JavaScript as decimal strings.
- Teamcenter/model links are immutable; AI00 stores references, projections, bindings, versions, and poses.
- No Renderer/IPC/named-pipe/loopback VisMockup business bypass.
- All production changes follow test-first red/green/refactor.

---

### Task 1: G0/G1 authoritative baseline and gap record

**Files:**
- Create: `docs/governance/simulation-environment-redesign-baseline.md`
- Create: `backend/tests/test_simulation_environment_redesign_governance.py`
- Modify only if the test proves a gap: `plugins/simulation/manifest.json`

**Interfaces:**
- Consumes: current Catalog, Registry descriptors, Provider registrations, consumer manifests, Connector v2 contracts.
- Produces: immutable inventory of reused/candidate capabilities, lifecycle states, owners, and Gate results.

- [x] Write a failing governance test asserting no candidate shadows an existing stable business effect, all local operations route through plan v2, and deprecated/experimental capabilities are not release targets.
- [x] Run `python -m pytest backend/tests/test_simulation_environment_redesign_governance.py -q` and record the expected failure.
- [x] Write the baseline record from current sources; make only minimal descriptor/manifest corrections required by the test, leaving candidates experimental.
- [x] Run the focused test plus `backend/tests/test_simulation_domain_boundary.py` and Connector v2 contract tests.
- [x] Mark G0/G1 passed only for local development evidence; keep approval/runtime states unverified.

### Task 2: Safe PLMXML streaming parser and bounded projection

**Files:**
- Create: `plugins/simulation/simulation_backend/domain/plmxml_projection.py`
- Create: `plugins/simulation/tests/test_plmxml_projection.py`
- Create: `plugins/simulation/tests/fixtures/plmxml/` bounded fixtures

**Interfaces:**
- Produces: `parse_plmxml(stream, limits, algorithm_version) -> PlmxmlProjection` with document facts, ProductInstance/Occurrence/ProductRevisionView joins, raw/normalized transforms, and structured errors.

- [x] Write failing tests for BOM line `W01-89184128/00;1`, `catiaOccurrenceName`, revision, parent path, transform normalization, duplicate instances, broken refs, DTD/entity/XInclude rejection, depth/count/string/reference/time limits, and zero external I/O.
- [x] Run the focused tests and verify RED.
- [x] Implement a streaming parser with DTD/entity/XInclude disabled and opaque Representation locations.
- [x] Run focused tests and a read-only parse of the 21MB reference sample; record counts, duration, peak memory, and limit decisions without storing the source path in normal logs.
- [x] Update the spec with measured limits and mark G2 only from real evidence.

### Task 3: VM document/session/snapshot persistence and identity diff

**Files:**
- Create: `backend/db/migrations/domains/simulation/0011_simulation_workspaces.sql`
- Create: `plugins/simulation/simulation_backend/domain/vm_identity.py`
- Create: `plugins/simulation/simulation_backend/data/vm_snapshot_repository.py`
- Create: `plugins/simulation/tests/test_vm_identity.py`
- Create: `backend/tests/test_simulation_workspace_sql.py`

**Interfaces:**
- Produces snowflake-GID document/session/snapshot/occurrence/observation/pose records and versioned `diff_snapshots()`.

- [x] Write RED tests for exact identity, moved part, repeated resource instances, same live occurrence movement, delete/reload predecessor, upgrade predecessor, ambiguity, tenant isolation, sequence/CAS, and soft deletion.
- [x] Add migration with GID, tenant/owner, FKs, unique keys, row_version, status/removed_at, algorithm versions, ArtifactRef/hash, and current-head constraints.
- [x] Implement repository and identity/diff service minimally.
- [x] Run migration/compiler, provider, boundary, and identity tests.

### Task 4: Private workspace, atomic structure/binding operations, and freeze saga

**Files:**
- Create: `plugins/simulation/simulation_backend/domain/workspace.py`
- Create: `plugins/simulation/simulation_backend/data/workspace_repository.py`
- Create: `plugins/simulation/simulation_backend/capabilities/workspaces.py`
- Create: `plugins/simulation/tests/test_workspace_capabilities.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/__init__.py`
- Modify: `plugins/simulation/manifest.json`

**Interfaces:**
- Produces separate experimental create/search/get/metadata/archive, structure-node create/move/remove/reorder, binding create/update/remove, version freeze/get/search, compare start/get, and migration-accept capabilities.

- [ ] Write one failing contract/provider test per atomic effect, including owner-only selectors, CAS, idempotency, load uniqueness, soft deletion, paging, and stable errors.
- [x] Implement private workspace/revision logic and local patches that preserve UI view state.
- [x] Implement freeze as Base Platform Artifact finalize + Simulation DB saga with orphan/unavailable reconciliation.
- [ ] Register candidates as experimental only and regenerate only affected capability documents.
- [ ] Run focused, mandatory acceptance, catalog lineage, and migration tests; mark G5/G6 only from evidence.

### Task 5: Knowledge reverse model lookup and Craft Load projection

**Files:**
- Create: `plugins/knowledge/knowledge_backend/capabilities/resource_model_reverse_lookup.py`
- Create: `plugins/knowledge/tests/test_resource_model_reverse_lookup.py`
- Create or modify after schema verification: `plugins/craft/craft_backend/capabilities/bop_structure.py`
- Modify: `backend/tests/test_craft_simulation_contract.py`

**Interfaces:**
- Produces exact batch `model_numbers -> resolved/not_found/ambiguous` resource candidates and Craft-owned normalized `is_load_part` output.

- [x] Inspect running/test BOP ontology data to identify the authoritative Load property code, type, precedence, null and version semantics; stop dependent work if unverified.
- [x] Write RED tests for tool/fixture/equipment/socket lookup, exact-only auto match, ambiguous/not-found, batch limits, tenant context, and sensitive-field trimming.
- [x] Implement Knowledge-owned reverse lookup without Simulation table access.
- [x] Write RED Craft contract tests for process/operation Load projection and implement the minimal owner-side projection.
- [ ] Register candidates experimental, run owner/boundary/consumer tests, and record G4/G5 state without approval.

### Task 6: Connector document discovery, ExportEx, instance tracking, and scene journal

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupConnection.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/SceneRecoveryJournal.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/VisMockupDocumentDiscoveryTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/VisMockupExportPlmxmlTests.cs`
- Create: `local-runtime/tests/Ai00.Connector.Tests/SceneRecoveryJournalTests.cs`

**Interfaces:**
- Produces allowlisted `document.discover`, `document.export_plmxml`, stable occurrence tracking, scene backup/restore, and post-condition probes used only inside signed plan v2.

- [ ] Write RED xUnit tests for process-running versus automation-connected state, multiple windows, exact document selection, no ambiguous auto-attach, ExportEx artifact limits, session continuity, and wrong-document rejection.
- [x] Run a bounded G3 feasibility spike for a Teamcenter-launched window. Existing evidence says `GetActiveObject` is unavailable and `Dispatch` creates a new instance; accept only an official attachment mechanism or a governed in-process Adapter, and record failure honestly if neither works.
- [ ] Write RED tests for DPAPI journal binding to user/device/plan/document/generation, quotas, retention, terminal cleanup, and uncertain-outcome retention.
- [ ] Implement minimal Adapter operations and journal; never expose a local business IPC method.
- [ ] Run focused xUnit tests serially with bounded workers, then perform the real Windows/VisMockup G3 matrix and record actual failures separately.

### Task 7: Four-column simulation workspace UI and governed synchronization

**Files:**
- Create: `packages/sim-plugin/web/cad_sim/environment_store.js`
- Create: `packages/sim-plugin/web/cad_sim/environment_tree.js`
- Create: `packages/sim-plugin/web/cad_sim/environment_records.js`
- Create: `packages/sim-plugin/web/cad_sim/model_binding_panel.js`
- Modify: `packages/sim-plugin/web/cad_sim/index.html`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.css`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Create: `packages/sim-plugin/web/cad_sim/environment_workspace.test.js`

**Interfaces:**
- Consumes only governed capabilities and platform-only file dialog APIs; produces four-column UI, optimistic local patches, explicit sync/freeze, drag/drop binding, inline ambiguity, and bidirectional highlight.

- [ ] Write RED DOM tests for first-load tabs/status, environment selection, view preservation, atomic autosave/CAS conflict, no duplicate confirmation popup, drag/drop classification, exact/fuzzy behavior, and lazy tree paging.
- [ ] Implement the smallest state/store/components and remove obsolete scattered command UI.
- [ ] Route all VM actions through Gateway capabilities and plan v2; add a static boundary test rejecting direct bridge/IPC business calls.
- [ ] Build production assets, run Node tests, and compare packaged UI screenshots.

### Task 8: Process-level reverse capture with Load semantics and recovery

**Files:**
- Create: `plugins/simulation/simulation_backend/domain/process_capture_plan.py`
- Modify: `plugins/simulation/simulation_backend/application/capture_worker.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/capture_runs.py`
- Create: `backend/tests/test_simulation_process_capture_plan.py`
- Modify: `packages/sim-plugin/web/cad_sim/capture_workflow.js`
- Modify: `packages/sim-plugin/web/cad_sim/capture_workflow.test.js`

**Interfaces:**
- Produces deterministic one-image-per-process plans bound to frozen environment/snapshot/BOP/profile/algorithm hashes.

- [x] Write RED tests for cumulative forward load state, reverse hiding only past Load, later tightening highlights, initial-loaded parts, per-process operation aggregation, and deterministic hashes.
- [ ] Write failure tests for post-condition, capture, upload, Craft attach, cancel, crash, restore, duplicate dispatch, and outcome reconciliation.
- [ ] Implement the planner and resumable worker; keep changed semantics on an experimental new major.
- [ ] Run backend, Connector, frontend and real VisMockup smoke matrices without marking runtime verified.

### Task 9: Selective BOP publication and version migration

**Files:**
- Create: `plugins/simulation/simulation_backend/application/publish_plans.py`
- Create: `plugins/simulation/simulation_backend/data/publish_repository.py`
- Create: `plugins/simulation/simulation_backend/capabilities/publish_plans.py`
- Create: `backend/tests/test_simulation_bop_publish.py`
- Modify only if Craft gap is proven: `plugins/craft/craft_backend/capabilities/bop_writes.py`

**Interfaces:**
- Produces publish-plan create/action.get/dispatch, parent closure, Craft opaque client_ref correlation, conflict handling, and Simulation-owned publish maps.

- [ ] Write RED tests for partial selection, parent closure, unrelated rebase, same-node conflict, preview staleness, confirmation receipt, Craft CAS, idempotency, opaque client refs, outbox recovery, and uncertain outcome.
- [ ] Implement Simulation orchestration through Gateway; Craft returns only Craft GIDs and opaque correlation refs.
- [x] Persist publish maps in Simulation after confirmed Craft outcome; never cross-write tables.
- [ ] Run owner, consumer, boundary, acceptance and end-to-end tests; leave all approval/release status unverified.

### Task 10: Final integrated verification and release-ready evidence draft

**Files:**
- Create: `docs/governance/simulation-environment-redesign-verification.md`
- Modify: `scripts/test_simulation_p0_boundary.js`

**Interfaces:**
- Produces evidence report only; no approvals or release promotion.

- [ ] Run backend focused/full tests, migration checks, capability catalog/doc checks, .NET tests with bounded parallelism, frontend Node tests, and production build.
- [ ] Run manual Windows x64 scenarios for Teamcenter/open PLMXML, multiple VM windows, incremental sync, repeated resource instances, moved part, reverse capture, crash recovery, and selective publish.
- [x] Record passed/failed/skipped/unverified results, commits, hashes, environment and Gate status exactly.
- [x] Keep `human_approved=false/unverified`, `runtime_verified=unverified` until the later unified approval and controlled runtime process.
