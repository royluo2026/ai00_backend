# VisMockup Stage A Cache Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AI00 acquire the complete lightweight VisMockup 14.2 product structure reliably, publish only complete atomic local cache generations, and keep interactive control responsive and correctly mapped to the current COM session.

**Architecture:** Reuse the governed `simulation.document_snapshot.request@2` two-phase workflow and the Connector operation `vismockup.document.snapshot@1`. Correct the native PLMXML export first, normalize both standard and VisMockup current-state PLMXML into one projection, then fingerprint and atomically publish that projection to the existing Connector SQLite cache. Treat the UI depth selector as display-only; persistent occurrence identity uses PLM metadata while transient NodeKey mapping remains session-scoped.

**Tech Stack:** .NET 8/C#, VisMockup 14.2 COM Automation, Python 3 streaming Expat parser, SQLite, vanilla JavaScript/Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-10-simulation-three-layer-cache-version-diff-design.md`

## Global Constraints

- This is an implementation fix to the existing Simulation-owned snapshot capability; do not add or bypass a public REST route, permission, confirmation, audit, or database write contract.
- Export the full lightweight product structure with `ExportEx` SaveType `2`; never use SaveType `0` and never copy JT payloads.
- Snapshot acquisition is independent of the UI display depth. Display depth may hide nodes but cannot truncate export, normalization, fingerprinting, or cache coverage.
- A malformed, incomplete, timed-out, or identity-ambiguous refresh cannot replace the last complete cache generation.
- PDM occurrence UID is the preferred persistent occurrence identity. COM NodeKey is valid only within the exact active process/document session.
- Control operations remain uncached and higher priority than automatic structure acquisition.
- Preserve unrelated dirty-worktree changes and stage only files changed by this plan.

---

### Task 1: Correct native PLMXML export and restore user options

**Files:**

- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/FakeVisMockupCom.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/VisMockupExportPlmxmlTests.cs`

**Interfaces:**

- Consumes: `IVisMockupApplication.ActiveDocument` and `IVisMockupDocument.ExportPlmxml(path, hierarchyIndex)`.
- Produces: the same public Connector interface, implemented with SaveType `2` and a scoped save-options restore in `finally`.

- [ ] Add a failing test with a recording export settings object. Assert that export observes `AskEveryTime=0`, `CopyParts=0`, `RetainReferences=1`, `ForceRetainRefs=1`, `SaveLateLoadedProperties=0`, `SaveExtendedInPLMXML=0`, `SaveInsertedAssemblies=0`, and SaveType `2`, then assert every original value is restored.
- [ ] Run `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --filter VisMockupExportPlmxmlTests -m:1` and confirm the new assertion fails because the implementation currently sends SaveType `0` and has no option scope.
- [ ] Pass `PLMXMLSaveOptions` from the active VisAutomation application into `DynamicDocument`; snapshot the seven values, set the bounded values, call DISPID 13 with `(2, path, "", hierarchyIndex)`, and restore all seven values in `finally`.
- [ ] Re-run the focused test and confirm all export tests pass.

### Task 2: Normalize VisMockup 14.2 current-state PLMXML

**Files:**

- Add: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupPlmxmlProjectionReader.cs`
- Add: `local-runtime/tests/Ai00.Connector.Tests/VisMockupPlmxmlProjectionReaderTests.cs`
- Modify: `plugins/simulation/simulation_backend/domain/plmxml_projection.py`
- Modify: `plugins/simulation/tests/test_plmxml_projection.py`

**Interfaces:**

- Consumes: current-state `Occurrence/ApplicationRef/UserValue` records with `PS_API-doc/JT_PROP_NAME`, `PS_API-doc/NGID`, `__PLM_OCC_PDM_UID`, `__PLM_ABSOCC_UID`, and `catiaOccurrenceName`.
- Produces: the existing server `PlmxmlProjection` plus the equivalent Connector-local `VisMockupPlmxmlProjection`; extend existing records only with optional identity fields so standard documents remain source-compatible. The small .NET reader is required because the local SQLite and COM control map cannot send a 37 MB transient source to Python before displaying cached structure.

- [ ] Add a minimal hand-authored current-state fixture with one root and two nested occurrences. Assert three projected nodes, correct parent closure, full path, PDM UID, absolute UID, clone-stable chain, item/revision extraction, and deterministic order.
- [ ] Run `python -m pytest plugins/simulation/tests/test_plmxml_projection.py -q` and confirm failure because the existing parser projects only the single ProductInstance referenced by `instanceRefs`.
- [ ] Extend the streaming parser to capture occurrence-level ApplicationRefs and UserValues, decode the full path and NGID chain, build a prefix trie, reject duplicate preferred identities or missing parents, and emit the normalized projection without reading external files.
- [ ] Implement the same bounded normalization in the Connector with `System.Xml.XmlReader`; share fixture values and canonical field semantics, not language-specific source code.
- [ ] Re-run the focused parser tests and also parse `D:\Temp\vis\ai00-current-w10-structure-only.plmxml`; assert more than 14,000 normalized occurrences, no unresolved parents, and no security/limit failure.

### Task 3: Publish deterministic atomic SQLite generations

**Files:**

- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupTreeCache.cs`
- Add: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupTreeFingerprint.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/VisMockupSnapshotTests.cs`

**Interfaces:**

- Consumes: one complete normalized structure and stable occurrence metadata.
- Produces: `document_identity_hash`, `revision_fingerprint`, `subtree_hash`, `snapshot_hash`, and an atomically switched complete cache generation.

- [ ] Add failing tests for identical reopen cache hit, one-node revision change, aborted refresh preserving the prior generation, and a truncated source never becoming current.
- [ ] Run the focused `VisMockupSnapshotTests` and confirm the new generation assertions fail.
- [ ] Compute canonical SHA-256 fingerprints bottom-up and write generation metadata plus nodes in one SQLite transaction; update the document head only as the final statement before commit.
- [ ] Re-run the focused tests and confirm all pass, including the pre-existing partial-depth rejection test.

### Task 4: Make depth display-only and resolve NodeKeys lazily per session

**Files:**

- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/VisMockupSnapshotTests.cs`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/cad_sim_vm_tree.test.js`

**Interfaces:**

- Consumes: complete cached occurrences plus the active process/document/root session identity.
- Produces: filtered UI display without a new backend acquisition and a lazy `stable_occurrence_key → NodeKey` control map invalidated on session change.

- [ ] Add failing Connector and UI tests proving that changing display depth causes no snapshot/export request and that the first node control resolves only its ancestor path while a repeated control reuses the mapping.
- [ ] Run the focused .NET and Node tests and confirm failure on current max-depth acquisition behavior.
- [ ] Remove display depth from acquisition/cache identity, filter the already-loaded tree in the browser, and add the bounded session map used only by node visibility/selection operations.
- [ ] Re-run the focused .NET and Node tests and confirm all pass.

### Task 5: Serialize acquisition behind interactive controls and verify runtime

**Files:**

- Modify: `local-runtime/src/Ai00.Connector.AppHost/PlanExecutionWorker.cs`
- Modify: `local-runtime/src/Ai00.Connector.AppHost/RuntimeSessionWorker.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/AppHostLifecycleTests.cs`
- Modify: `backend/tests/test_connector_runtime_control_plane.py`

**Interfaces:**

- Consumes: existing Connector work queue and document snapshot plan execution.
- Produces: high-priority interactive control queue, one low-priority exclusive export after ten idle seconds, and explicit `verifying/degraded` state.

- [ ] Add failing tests proving control runs before queued automatic export, duplicate export coalescing, export timeout preserves last-good cache, and no automatic retry loop starts.
- [ ] Run the focused Connector host and Python control-plane tests and confirm the scheduler assertions fail.
- [ ] Add the smallest priority gate around the existing workers: controls update last-interaction time; automatic export starts only after ten idle seconds; one export is in flight; timeout marks exporter degraded without killing VisMockup.
- [ ] Re-run focused tests, then run the full Connector test project and Simulation snapshot tests.
- [ ] In a user-approved local session, export W10, verify no JT geometry count increase, reopen the same model and verify cache-first display, change display depth without export, and verify full show/hide plus highlight remain responsive.

## Governance and acceptance record

- Capability: `simulation.document_snapshot.request@2` (existing experimental two-phase entrypoint) and its existing `action.get`, `dispatch`, and `get` companions.
- Connector operation: `vismockup.document.snapshot@1`.
- Owner: Simulation domain; Connector local runtime is the approved execution boundary.
- Classification: implementation fix; no published input/output, permission, confirmation, idempotency, audit, or business-effect change.
- Database impact: no production MySQL/OceanBase migration in Stage A; SQLite cache schema is local and rebuildable.
- `machine_passed`, `human_approved`, and `runtime_verified` remain separate and are reported only from current evidence.
