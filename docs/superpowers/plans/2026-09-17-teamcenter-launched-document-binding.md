# Teamcenter Launched Document Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind a newly launched Teamcenter online source to its existing Simulation environment using trusted launch and document-identity evidence, then immediately embed that exact VisMockup document in AI00.

**Architecture:** Add one simulation-owned atomic Capability that verifies two persisted Connector outcomes and commits a first live-session binding without changing the Teamcenter model source. Update the existing web launch flow to wait for a new attested document session, invoke that Capability, and attach the native viewport only after the committed binding matches the selected environment and document.

**Tech Stack:** Python 3.12, FastAPI Capability V2 Provider contracts, PyMySQL/SQLite repository tests, vanilla browser JavaScript, Electron native-view IPC, Node test runner with JSDOM.

**Spec:** `docs/superpowers/specs/2026-09-17-teamcenter-launched-document-binding-design.md`

## Global Constraints

- Never bind by title, display name, item name, or guessed window identity.
- Never overwrite `teamcenter_online` source kind, selector, `source_identity_hash`, or `content_sha256`.
- Do not rebuild or automatically reread the product tree or alternate hierarchies.
- Do not change `simulation.environment.live_document.rebind@1` semantics.
- Reuse existing Connector plans, live-document binding table, workspace transaction, and native-view controller; add no database table or external dependency.
- A failed bind must not repeat the Teamcenter launch.
- All Connector evidence remains owner-, tenant-, device-, protocol-, status-, and freshness-scoped.

---

### Task 1: Verify Teamcenter launch evidence

**Files:**
- Create: `plugins/simulation/simulation_backend/application/teamcenter_launch_evidence.py`
- Modify: `plugins/simulation/simulation_backend/data/connector_repository.py`
- Test: `plugins/simulation/tests/test_teamcenter_launch_evidence.py`

**Interfaces:**
- Consumes: persisted `workmanship_sim_connector_runtime_plans` rows for protocol `ai00.connector.execution-plan.v2`.
- Produces: `SimulationConnectorRepository.verified_teamcenter_launch(operation_id, *, actor_id, tenant_id, now) -> dict` with `connector_device_id`, `source_identity_hash`, and `launch_id`.

- [ ] **Step 1: Write the failing evidence tests**

Create literal successful plan/outcome rows for exactly one `teamcenter.visualization.launch@1` step. Assert the verifier returns:

```python
assert verified == {
    "connector_device_id": "device-A",
    "source_identity_hash": "sha256:" + "a" * 64,
    "launch_id": "tclaunch:" + "b" * 64,
}
```

Add parametrized rejection cases for wrong operation, non-succeeded plan/step, missing result fields, other actor/tenant, other active runtime device, and evidence older than the existing evidence freshness window.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m pytest plugins/simulation/tests/test_teamcenter_launch_evidence.py -q
```

Expected: FAIL because `verified_teamcenter_launch` and its verifier do not exist.

- [ ] **Step 3: Implement the minimal pure verifier and repository adapter**

In `teamcenter_launch_evidence.py`, validate the closed shape and canonical operation:

```python
def verify_teamcenter_launch_evidence(row, runtime, *, actor_id: str, tenant_id: str, now: datetime) -> dict:
    # Require owner, tenant, active runtime device, v2 protocol, succeeded plan,
    # one succeeded teamcenter.visualization.launch@1 step, and fresh timestamps.
    return {
        "connector_device_id": str(row["device_id"]),
        "source_identity_hash": result["source_identity_hash"],
        "launch_id": result["launch_id"],
    }
```

In `connector_repository.py`, load the owner-scoped plan row exactly as `verified_document_identity` does, call the pure verifier, and map failures to `launch_evidence_stale` or `launch_evidence_unavailable`.

- [ ] **Step 4: Run evidence and existing identity tests GREEN**

```powershell
python -m pytest plugins/simulation/tests/test_teamcenter_launch_evidence.py plugins/simulation/tests/test_live_document_identity_evidence.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add plugins/simulation/simulation_backend/application/teamcenter_launch_evidence.py plugins/simulation/simulation_backend/data/connector_repository.py plugins/simulation/tests/test_teamcenter_launch_evidence.py
git commit -m "feat(simulation): verify Teamcenter launch evidence"
```

### Task 2: Atomically bind an opened online source

**Files:**
- Modify: `plugins/simulation/simulation_backend/data/workspace_repository.py`
- Test: `plugins/simulation/tests/test_live_document_binding_repository.py`

**Interfaces:**
- Consumes: trusted `connector_device_id`, `document_session`, and `source_identity_hash` from Task 1 and existing identity verification.
- Produces: `WorkspaceRepository.bind_online_live_document(*, workspace_gid, document_gid, tenant_gid, actor_gid, connector_device_id, document_session, source_identity_hash, expected_workspace_row_version, idempotency_key) -> dict`.

- [ ] **Step 1: Extend the SQLite fixture and write failing repository tests**

Insert one workspace and one `teamcenter_online` primary document with literal `content_sha256 = "a" * 64`, `source_identity_hash = "instance-hash"`, and no connector device. Assert a successful bind returns `state == "bound"`, creates one live binding, advances the workspace once, and changes only `connector_device_id` on the model document.

Snapshot protected fields before and after:

```python
assert after == (
    "teamcenter_online", "instance-hash", "a" * 64,
    original_artifact_ref_json, "device-A",
)
```

Add rejection tests for source mismatch, wrong owner/tenant/workspace/document, stale row version, existing different environment binding, and an existing different active session. Assert every rejected case leaves bindings and workspace version unchanged. Assert replay with the same idempotency key returns the exact first result.

- [ ] **Step 2: Run the focused repository tests and verify RED**

```powershell
python -m pytest plugins/simulation/tests/test_live_document_binding_repository.py -q
```

Expected: FAIL because `bind_online_live_document` does not exist.

- [ ] **Step 3: Implement the single repository transaction**

Use the existing `_live_document_identity`, `_idempotency_begin`, `_idempotency_finish`, and `_advance_workspace_revision` helpers. Lock and verify the workspace and target document, compare `content_sha256` to the trusted launch hash without its `sha256:` prefix, reject conflicting active bindings, insert one `bound` binding, update only the target document `connector_device_id` and `row_version`, then advance the workspace revision.

Return this closed shape:

```python
{
    "workspace_gid": workspace_gid,
    "document_gid": document_gid,
    "state": "bound",
    "connector_device_id": connector_device_id,
    "document_session": document_session,
    "workspace_row_version": next_version,
    "cache_revision_hash": cache_hash,
}
```

- [ ] **Step 4: Run repository tests GREEN**

```powershell
python -m pytest plugins/simulation/tests/test_live_document_binding_repository.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add plugins/simulation/simulation_backend/data/workspace_repository.py plugins/simulation/tests/test_live_document_binding_repository.py
git commit -m "feat(simulation): bind online source to live document"
```

### Task 3: Register the atomic Capability

**Files:**
- Modify: `plugins/simulation/simulation_backend/capabilities/live_documents.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Test: `plugins/simulation/tests/test_live_document_capabilities.py`
- Generated: `backend/capability_v2/official_domains.json`
- Generated: `docs/capabilities/simulation/simulation.environment.online_source.live_document.bind@1.md`
- Generated: `docs/capabilities/catalog.v2.json`
- Generated: `docs/capabilities/.generated-manifest.json`
- Generated: `docs/governance/capability-catalog-release.json`
- Generated: `docs/governance/capability-catalog-lineage.json`

**Interfaces:**
- Consumes: `verified_teamcenter_launch`, `verified_document_identity`, and `bind_online_live_document` from Tasks 1–2.
- Produces: `simulation.environment.online_source.live_document.bind@1`, write risk, confirmation `user`, idempotent, permission `simulation.use`, web exposure only.

- [ ] **Step 1: Write failing Provider tests**

Add a fake Connector that returns distinct trusted launch and identity values. Invoke the wished-for handler with:

```python
payload = {
    "workspace_gid": "100",
    "document_gid": "101",
    "launch_operation_id": "launch-op",
    "identity_operation_id": "identity-op",
    "expected_workspace_row_version": 1,
    "idempotency_key": "bind-op",
}
```

Assert the repository receives only server-derived device/session/source values. Add a device-mismatch test that raises `connector_device_mismatch` before any repository call. Assert the registered descriptor is simulation-owned, web-only, write, user-confirmed, and idempotent.

- [ ] **Step 2: Run Provider tests and verify RED**

```powershell
python -m pytest plugins/simulation/tests/test_live_document_capabilities.py -q
```

Expected: FAIL because the input/output contracts and handler are absent.

- [ ] **Step 3: Implement the closed contracts and handler**

Add `ONLINE_BIND_INPUT` and `ONLINE_BIND_OUTPUT` with `additionalProperties: false`. Implement `LiveDocumentProvider.bind_online_source` to validate web ownership, verify both operations at the same clock instant, require equal connector devices, and call the repository method. Register the capability without changing `rebind@1`.

- [ ] **Step 4: Run Provider and control-plane tests GREEN**

```powershell
python -m pytest plugins/simulation/tests/test_live_document_capabilities.py backend/tests/test_connector_runtime_control_plane.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 5: Regenerate and check governed artifacts**

Run the guarded official-domain freeze using the current HEAD and current manifest digest, then:

```powershell
python backend/scripts/build_capability_catalog.py --write
python backend/scripts/generate_capability_docs.py --write
python backend/scripts/freeze_official_domains.py --check
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
```

Expected: one new simulation descriptor, no missing Provider binding, all checks PASS.

- [ ] **Step 6: Commit Task 3**

Stage only the capability implementation, tests, official-domain manifest, generated capability page, and regenerated catalog/governance artifacts. Commit:

```powershell
git commit -m "feat(simulation): register trusted online document binding"
```

### Task 4: Bind and embed after the web launch

**Files:**
- Modify: `packages/sim-plugin/web/cad_sim/teamcenter_online_source.js`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Test: `packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js`
- Test: `packages/sim-plugin/web/cad_sim/cad_sim_native_view.test.js`

**Interfaces:**
- Consumes: launch outcome operation ID, current workspace/document state, identity-read outcome, and Task 3 Capability.
- Produces: `_bindAndEmbedOpenedTeamcenterDocument({workspace, document, launchOutcome, isCurrent}) -> Promise<object>` and user-visible recovery status on failure.

- [ ] **Step 1: Write failing browser behavior tests**

Cover these literal event sequences:

1. `launch.request` completes; identity reads initially return the old session, then a new session; the bind Capability receives the launch operation ID and the successful new identity operation ID; native attach occurs only after binding succeeds.
2. Workspace selection changes while waiting; no bind or attach occurs.
3. Bind fails; launch is called once, native attach is not called, and UI contains `文档已打开，绑定未完成`.
4. `insert` still calls only `visualization.insert.request` and never calls the new bind Capability.

The expected successful order is:

```javascript
assert.deepEqual(events, ['launch', 'identity-old', 'identity-new', 'bind', 'attach']);
```

- [ ] **Step 2: Run browser tests and verify RED**

```powershell
node --test packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js packages/sim-plugin/web/cad_sim/cad_sim_native_view.test.js
```

Expected: FAIL because the launch flow still schedules `_tryAutoConnect` and never invokes the bind Capability.

- [ ] **Step 3: Return the launch outcome and implement bounded waiting**

Change `openOnline`/`_openTeamcenterOnlineDocument` to preserve the Connector command outcome. Capture the selected workspace/document object and initial document session before launch when available. Poll identity with a fixed deadline and stop only when a valid session differs from the initial session; every loop must re-check that the same workspace and document remain selected.

Do not match names. Use the outcome operation IDs as the only evidence references.

- [ ] **Step 4: Invoke the bind Capability and attach after commit**

Call:

```javascript
await _invokeCapability('simulation.environment.online_source.live_document.bind', {
  workspace_gid: String(workspace.workspace_gid),
  document_gid: String(document.document_gid),
  launch_operation_id: launchOutcome.plan_id,
  identity_operation_id: identityOutcome.plan_id,
  expected_workspace_row_version: workspace.row_version,
  idempotency_key: bindKey,
}, {confirmation:true, idempotency:true, idempotencyKey:bindKey});
```

Update in-memory workspace concurrency tokens only if the original selection and row version are still current. Mark live-document context available, then call `_attachNativeViewport()` and require an `attached` state. Replace the old `setTimeout(() => _tryAutoConnect(), 1500)` path for `new` mode only.

On timeout or bind failure, show `文档已打开，绑定未完成：<code>；请重试绑定，不要重复打开文档` and retain enough in-memory evidence for the same action to retry binding without relaunch. Do not enable model-node runtime controls before binding succeeds.

- [ ] **Step 5: Run browser tests GREEN and build the App**

```powershell
node --test packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js packages/sim-plugin/web/cad_sim/cad_sim_native_view.test.js packages/sim-plugin/web/cad_sim/live_document_switcher.test.js packages/sim-plugin/web/cad_sim/live_document_adapter.test.js
npm run build:web
```

Expected: all selected tests PASS and the production web build completes.

- [ ] **Step 6: Commit Task 4**

```powershell
git add packages/sim-plugin/web/cad_sim/teamcenter_online_source.js packages/sim-plugin/web/cad_sim/cad_sim.js packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js packages/sim-plugin/web/cad_sim/cad_sim_native_view.test.js dist-production/packages/sim-plugin/web/cad_sim
git commit -m "feat(simulation): embed newly launched Teamcenter document"
```

### Task 5: Integrated verification and test runtime rollout

**Files:**
- Verify only unless a failing test identifies a root-cause defect.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: machine test evidence and controlled test-runtime evidence; no claim of human governance approval.

- [ ] **Step 1: Run the focused cross-layer suite**

```powershell
python -m pytest plugins/simulation/tests/test_teamcenter_launch_evidence.py plugins/simulation/tests/test_live_document_binding_repository.py plugins/simulation/tests/test_live_document_capabilities.py backend/tests/test_connector_reconciliation_v2.py backend/tests/test_connector_runtime_control_plane.py -q
node --test packages/sim-plugin/web/cad_sim/teamcenter_lazy_tree.test.js packages/sim-plugin/web/cad_sim/cad_sim_native_view.test.js packages/sim-plugin/web/cad_sim/live_document_switcher.test.js packages/sim-plugin/web/cad_sim/live_document_adapter.test.js
```

Expected: all selected tests PASS; report skips separately.

- [ ] **Step 2: Re-run governance checks**

```powershell
python backend/scripts/freeze_official_domains.py --check
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
```

Expected: all checks PASS against the same Catalog release.

- [ ] **Step 3: Restart test backend and AI00 App from built artifacts**

Restart only the test backend and test App; do not close VisMockup. Verify port 8080, Connector heartbeat, and that the App is serving the rebuilt `dist-production` assets.

- [ ] **Step 4: Perform the controlled smoke test**

From a selected environment containing a `teamcenter_online` model, execute “新文档打开” once. Query the production database's `test_` tables read-only and verify:

- launch plan succeeded;
- identity-read plan succeeded for a different document session;
- one online-source live bind audit/outcome succeeded;
- one active live binding points to the selected workspace and new session;
- the model document remains `teamcenter_online` and retains its source/content hashes;
- native status is `attached` and node visibility control targets the new document session.

- [ ] **Step 5: Report governance states honestly**

Report:

- `machine_passed`: true only if tests and deterministic governance checks pass;
- `human_approved`: unchanged/not granted by this implementation;
- `runtime_verified`: true only after the controlled smoke evidence above;
- unresolved errors, skipped database variants, or manual confirmation needs as separate risks.

