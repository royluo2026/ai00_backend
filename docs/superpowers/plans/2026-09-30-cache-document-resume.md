# Fixed Cache Document Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore control mapping and native visibility of previously loaded frozen-cache nodes when the user switches away from an environment and back in the same page session, without another model open.

**Architecture:** A new backend completion contract verifies fresh signed existing-document identity against the original frozen package, binding and source association, then atomically renews the current-runtime association and signs a Main-owned grant. Electron attaches the already-open document under that grant. The page retains only a bounded-by-loaded-scope, nonpersistent structural candidate; after matching refreshed authoritative state, it performs read-only batched visibility calibration.

**Tech Stack:** Python/Pydantic/SQLite-backed simulation tests; Electron Main/preload and browser JavaScript; Node's built-in test runner.

**Spec:** `docs/superpowers/specs/2026-09-30-cache-document-resume-design.md` in the backend worktree. Frontend edits go to sibling `orchestration-merge-frontend-20260905`; backend edits go to `orchestration-merge-backend-20260905`.

## Global Constraints

- Scope: same page session, switch away and back; Connector restart, performance, first-document count and two physical clients remain separate verification items.
- Keep the 10-document limit and existing tenant/user/device/runtime, single-environment single-document/root, authorization and unknown-effect fences.
- Resume never calls `cache_source.open.request`, downloads JT, creates an open plan, inserts instances, changes coordinates or writes visibility. Never replace a scoped open with an unscoped document open.
- Shared cache remains fixed TC metadata/file references/assembly evidence. Candidate mapping and visibility stay client-local; no JT paths, credentials, persisted runtime mapping or old visibility values.
- The signed identity must be current for the exact native session; old runtime generation, changed package/batch, version, device, binding or source association fails closed. Only the current Main-generated nonce receives a grant.
- Existing online resume and frozen-cache open-completion semantics remain unchanged. Do not edit `dist`/`dist-production`, unrelated dirty files or the existing checkpoint commits; do not commit or push without a fresh explicit request.

## Review Focus

- Reload/new page has no candidate: keep all cached nodes unknown and do not invoke resume (Task 4 test).
- Same native session but changed batch or package revision: do not merge old mappings or issue control (Tasks 1 and 3 tests).
- An `outcome_unknown` slot or an interrupted cache open: quarantine its candidate and never retry/open automatically (Tasks 2 and 3 tests).
- A loaded node near the end of a 16k-node tree must be read despite the existing 2000-node calibration cap; an unloaded sibling remains unknown (Task 4 test).
- A late identity, grant or visibility result after selection/tree change cannot attach controls or update checkboxes (Tasks 2 and 4 tests).

---

### Task 1: Transactional frozen-cache resume and grant

**Files:**
- Create: `backend/contracts/viewer_cache_resume_v1.py`
- Modify: `plugins/simulation/simulation_backend/application/cache_open_evidence.py`, `plugins/simulation/simulation_backend/data/viewer_interaction_repository.py`, `plugins/simulation/simulation_backend/data/workspace_repository.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/live_documents.py`, `plugins/simulation/simulation_backend/application/viewer_interaction.py`, `plugins/simulation/simulation_backend/capabilities/provider.py`, `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Test: `plugins/simulation/tests/test_cache_document_resume.py`

**Interfaces:**
- Consumes: `SimulationConnectorRepository.verified_existing_document_identity_evidence(cursor, operation_id, actor_id, tenant_id, now)`, `ViewerInteractionRepository.record_source_association(...)`, `authorize_interaction(..., transaction=cursor, issuer=...)`, the existing immutable completion and grant models.
- Produces: `CacheResumeRequest` (closed Pydantic model: `workspace_gid`, `document_gid`, `identity_operation_id`, `expected_document_session`, `expected_workspace_row_version`, `idempotency_key`, `session_nonce`); `CacheResumeResult(binding: OpenBinding, grant: SignedGrant)`; `WorkspaceRepository.resume_cache_live_document(*, tenant_gid, actor_gid, workspace_gid, document_gid, identity_operation_id, expected_document_session, expected_workspace_row_version, idempotency_key, session_nonce, now, complete_binding)`; `LiveDocumentProvider.resume_cache(payload, context)`; `simulation.environment.cache_source.live_document.resume@1`.

- [ ] **Step 1: Write the failing backend cases in `test_cache_document_resume.py`.** Reuse the signed-grant/cache-completion fixtures and fresh current-runtime identity pattern from `test_live_document_resume.py`. Name and assert: `test_resume_cache_replays_one_signed_grant_without_open` (both document roles, `verify_signature(public)`, `grant.session_nonce == request.session_nonce`, exact replay, unchanged workspace revision/document/open-plan counts); `test_resume_cache_rejects_changed_pins` (parameterized batch/package/content/association/device/session/runtime instance/runtime generation/workspace version/owner mutations, no additional association or grant); `test_resume_cache_nonce_conflict` (`idempotency_conflict`); `test_resume_cache_rolls_back_signer_and_proof_failures` (no association/grant committed); `test_resume_cache_rejects_stale_identity` (no grant).

- [ ] **Step 2: Run red tests.** Run `python -m pytest plugins/simulation/tests/test_cache_document_resume.py -q`. Expected: missing contract/capability/repository entry, not a fixture or import failure unrelated to the feature.

- [ ] **Step 3: Implement the contract and shared cache revision check.** `CacheResumeRequest` uses `OpenCompletionRequest`'s field bounds and nonce pattern; `CacheResumeResult` reuses `OpenBinding` and `SignedGrant`. Extract the existing frozen envelope/package/content validation from `ViewerInteractionRepository.authorize_scope` into `validated_cache_package_revision(document) -> str` in `cache_open_evidence.py`, then call it from both paths; leave legacy cache and online behavior intact.

- [ ] **Step 4: Implement `WorkspaceRepository.resume_cache_live_document`.** Under workspace lock, check the exact owned `teamcenter_cache_snapshot` primary/inserted document, one `bound` binding, one active association with matching device/session/source revision, package pin and workspace version; verify fresh signed identity in the same transaction. Renew only the runtime association, return `OpenBinding` with unchanged row/cache revision, invoke `complete_binding` before idempotency finish, and hash `session_nonce` into the request. Never consult the old open receipt or change document/workspace revisions.

- [ ] **Step 5: Register and sign the new capability.** `LiveDocumentProvider.resume_cache(payload, context)` validates `CacheResumeRequest` and uses the repository callback to call `authorize_interaction` with issuer `('simulation.environment.cache_source.live_document.resume', 1)`, returning `CacheResumeResult`. Add exactly this issuer, Capability descriptor/policies/resource reference and runtime allowlist entry without changing online resume.

- [ ] **Step 6: Run green and nearby regressions.** Run `python -m pytest plugins/simulation/tests/test_cache_document_resume.py plugins/simulation/tests/test_cache_open_completion.py plugins/simulation/tests/test_live_document_resume.py plugins/simulation/tests/test_viewer_open_completion.py -q`. Expected: all selected tests pass; report unrelated failures separately.

### Task 2: Main-owned resume of an already-open cached document

**Files:**
- Modify: `packages/core/electron/viewer_interaction_client.js`, `packages/core/electron/capability_client.js`, `packages/core/electron/preload.js`
- Test: `packages/core/electron/viewer_interaction_client.test.js`

**Interfaces:**
- Consumes: Task 1 `resume@1` returning `{binding,grant}`; existing `readExistingIdentity`, `prepare`, `installPreparedGrant`, `attachVerified`, `ViewerRuntimeSlots`.
- Produces: `ViewerInteractionClient.resumeFromCache(event, input)` where closed `input` is `workspace_gid`, `document_gid`, `identity_operation_id`, `expected_document_session`, `expected_workspace_row_version`, `idempotency_key`; IPC/preload/iframe relay method `resumeFromCache`; result `{interaction_id,workspace_row_version,document_gid,document_session,visibility_context}`.

- [ ] **Step 1: Write failing Main tests.** Name and assert: `cache resume attaches without source open` (one `resume@1`, grant install, two `prepare_document`, attach, zero source/open-plan/activate calls); `cache resume rejects forged scope and grant` (extra fields, wrong nonce/session/version/source all rejected before attach); `cache resume preserves unknown quarantine` (unknown owner/slot rejected, no new grant); `cache resume rejects changed target and late navigation` (wrong target in either prepare or owner epoch change leaves no active control).

- [ ] **Step 2: Run red tests.** Run `node --test packages/core/electron/viewer_interaction_client.test.js`. Expected: `resumeFromCache` missing and/or new assertions fail.

- [ ] **Step 3: Implement `ViewerInteractionClient.resumeFromCache(event,input)`.** Validate closed input and owner epoch before and after awaits; reject unknown owner/slot *before* replacing the previous session. Generate nonce in Main; invoke only Task 1's resume capability using the request key plus nonce; validate binding/grant against input and nonce, install/renew through existing grant code, run `attachVerified` (including its second `prepare`), then store the cache slot and return a fresh `visibility_context`. Do not accept renderer-supplied grant/runtime identity or bypass canceled-open fencing.

- [ ] **Step 4: Expose the closed resume method.** Add `resumeFromCache` to `capability_client.js` completion-style envelope, Main IPC/relay allowlists and preload, with no other method exposed.

- [ ] **Step 5: Run green and bridge regressions.** Run `node --test packages/core/electron/viewer_interaction_client.test.js`. Expected: new and existing Main tests pass.

### Task 3: Keep only successful loaded-scope structure in page memory

**Files:**
- Modify: `packages/sim-plugin/web/cad_sim/cache_snapshot_viewer.js`, `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Test: `packages/sim-plugin/web/cad_sim/cache_snapshot_viewer.test.js`, `packages/sim-plugin/web/cad_sim/cache_snapshot_ui.test.js`

**Interfaces:**
- Consumes: existing `mergeLoadedBranches(previous, opened)`, `product_tree` and successful `_ensureCacheSnapshotViewer` result.
- Produces: `AI00CacheSnapshotViewer.captureResumeCandidate({workspace_gid,document_gid,cache_binding,product_tree}, viewer)` with only `workspace_gid`, `document_gid`, pinned `cache_binding`, `package_hash`, `document_session`, identity, merged `node_map`, `excluded`, `root_node_key`, and sanitized loaded `product_tree` (`nodes`, `pages`, structural tree metadata; omit `visible`, `visibility_state`, `control_key`, native visibility, local JT paths and credentials). In `cad_sim.js` a page-lifetime `Map` keyed by workspace/document retains this candidate; `_cacheSnapshotResumeCandidate(workspaceGid, documentGid)` returns it only while not quarantined, and `_forgetCacheSnapshotResumeCandidate(...)` removes it.

- [ ] **Step 1: Write failing candidate tests.** Name and assert: `merge only the same package and native session` (two scoped assembly loads merge keys/pages, changed hash/session/batch does not); `candidate contains only loaded structure` (no `native_visibility`, old node visibility, `tc_open_payload`, JT path or credential, no serializable document/structure-cache runtime field); `candidate dies on unknown outcome or page exit` (no candidate after interrupted open, unknown effect or new page context).

- [ ] **Step 2: Run red tests.** Run `node --test packages/sim-plugin/web/cad_sim/cache_snapshot_viewer.test.js packages/sim-plugin/web/cad_sim/cache_snapshot_ui.test.js`. Expected: missing candidate access or changed assertions fail.

- [ ] **Step 3: Implement candidate capture and lifecycle.** Guard `mergeLoadedBranches` by `package_hash` as well as session/batch. Copy only the structural fields after a successful *scoped* bind (never during admission/unknown effect), strip native visibility, keep the snapshot outside document JSON/localStorage, and retain it when `_invalidateCacheSnapshotVisibility` removes `_cacheViewer`. Clear it on pagehide/auth loss, model removal, conflict or unknown effect; do not clear it merely because the user selected another environment. Leave visible UI state unknown on switch-away.

- [ ] **Step 4: Run green candidate tests.** Run the Step 2 command again. Expected: all selected tests pass.

### Task 4: Restore matching mapping and calibrate loaded nodes read-only

**Files:**
- Modify: `packages/sim-plugin/web/cad_sim/viewer_interaction.js`, `packages/sim-plugin/web/cad_sim/live_document_bootstrap.js`, `packages/sim-plugin/web/cad_sim/live_document_adoption.js`, `packages/sim-plugin/web/cad_sim/cad_sim.js`, `packages/sim-plugin/web/cad_sim/debug.js`
- Test: `packages/sim-plugin/web/cad_sim/live_document_bootstrap.test.js`, `packages/sim-plugin/web/cad_sim/live_document_adoption.test.js`, `packages/sim-plugin/web/cad_sim/cache_snapshot_ui.test.js`, `packages/sim-plugin/web/cad_sim/viewer_interaction.test.js`

**Interfaces:**
- Consumes: Task 2 bridge `resumeFromCache(input)`; Task 3 candidate getter/forgetter; existing `sourceDescriptor(document,node)`, `readVisibility({source_nodes})`, `cacheIncompleteAncestors(viewer)` and `_refreshModelDocuments`.
- Produces: page interaction `local.resumeFromCache(input) -> {workspace_row_version,document_gid,document_session,visibility_context}` and adoption `calibrateLoadedCache({workspaceGid,document,viewer,isCurrent}) -> {calibrated,unknown_count}`. This method never calls `ensureCachedReady`, `executeCachedIntent` or an open method.

- [ ] **Step 1: Write failing page tests.** Name and assert: `switch back resumes and reads loaded cache only` (A→B→A, matching authoritative pins, new identity passed to Main, non-enumerable `_cacheViewer`, only ≤128-node `readVisibility` batches and no open/download/write); `calibrates loaded tail of 16k tree` (mapped node beyond index 15000 read, unloaded sibling unknown, mixed/failed/excluded keep no old boolean); `missing or mismatched candidate is display only` (new page, batch/package/session/version or mapping conflict: no resume, all unknown); `late results cannot restore controls` (selection/tree/pagehide/auth/unknown effect at each await: no stale checkbox/grant); `resume diagnostics are redacted` (separate window/control stages; no nonce, credential or JT path).

- [ ] **Step 2: Run red tests.** Run `node --test packages/sim-plugin/web/cad_sim/live_document_bootstrap.test.js packages/sim-plugin/web/cad_sim/live_document_adoption.test.js packages/sim-plugin/web/cad_sim/cache_snapshot_ui.test.js packages/sim-plugin/web/cad_sim/viewer_interaction.test.js`. Expected: resume/calibration assertions fail before implementation.

- [ ] **Step 3: Add page-level `resumeFromCache`.** Add the method to `frameAPI`, `createViewerInteraction` and the preview/open interlock; use the same `onReady` and generation fences as `openFromCache`, with no call to an open method.

- [ ] **Step 4: Add the read-only `calibrateLoadedCache`.** Traverse *all* candidate mapped loaded keys (no 2000 cap), call only `readVisibility` in batches of 128, check selection epoch, object/tree identity, visibility context and a consistent native `structure_epoch` after each await, and apply values to current nodes only after the full safe read. Preserve mixed/unknown and excluded states.

- [ ] **Step 5: Wire the verified switch-back path.** After the successful managed-window identity branch, fetch current workspace/document, await the matching refreshed tree and compare workspace/document/binding/package/session with the candidate. Call Main with the fresh identity plan ID and current row version; attach sanitized mapping only after it succeeds, then run Step 4 and refresh checkboxes. On mismatch, timeout, authorization failure, unknown effect or late result, close the local grant, forget/quarantine the candidate, invalidate controls and leave the original native window visible; never call `_ensureCacheSnapshotViewer` or automatically retry. Emit separate redacted window-restored/control-calibrated diagnostics.

- [ ] **Step 6: Run green and adjacent tests.** Run the Step 2 command plus `node --test packages/sim-plugin/web/cad_sim/cache_snapshot_viewer.test.js packages/core/electron/viewer_interaction_client.test.js`. Expected: all selected tests pass; note any pre-existing failures separately.

### Task 5: End-to-end regression and evidence boundary

**Files:**
- Modify only if a tested assertion reveals a missing integration wire in the files owned by Tasks 1–4.
- Test: selected Python and Node suites above; `docs/verification/2026-09-30-tc-local-open-execution.md` only when new *actual* runtime evidence exists.

**Interfaces:**
- Consumes: Tasks 1–4 as one integrated feature; no new product interface.
- Produces: an exact verification report distinguishing automated tests from native single-machine and two-client observations.

- [ ] **Step 1: Run both selected suites from the correct worktrees.** Backend: `python -m pytest plugins/simulation/tests/test_cache_document_resume.py plugins/simulation/tests/test_cache_open_completion.py plugins/simulation/tests/test_live_document_resume.py plugins/simulation/tests/test_viewer_open_completion.py -q`. Frontend: `node --test packages/core/electron/viewer_interaction_client.test.js packages/sim-plugin/web/cad_sim/cache_snapshot_viewer.test.js packages/sim-plugin/web/cad_sim/cache_snapshot_ui.test.js packages/sim-plugin/web/cad_sim/live_document_bootstrap.test.js packages/sim-plugin/web/cad_sim/live_document_adoption.test.js packages/sim-plugin/web/cad_sim/viewer_interaction.test.js`. Expected: pass without changing the known unrelated checkpoint failures.

- [ ] **Step 2: Inspect diffs and boundary assertions.** `git diff --check` in each worktree; verify no `dist` paths, no unrelated dirty file, no new cache-open/JT-download/visibility-write calls from resume, and unchanged online resume. Report exact counts, failures and skipped checks.

- [ ] **Step 3: If a live backend, login and VisMockup/Connector are available, perform the single-machine A→B→A observation.** Compare before/after native session, document/root/instance count, loaded instance matrices and actual visibility; verify zero new opens, downloads and writes. Record this only if witnessed. Otherwise explicitly mark runtime behavior, Connector restart and dual-physical-client verification `unverified`; leave the handoff's performance and first-document-count issues open. No deployment, commit or push in this task.
