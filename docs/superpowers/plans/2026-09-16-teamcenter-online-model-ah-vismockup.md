# Teamcenter Online Model and AH VisMockup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a Simulation environment read and cache a Teamcenter online occurrence tree, open the same online source in VisMockup through official VVI/runner, and incrementally project the environment's BOP-derived alternate hierarchies into that same VisMockup document.

**Architecture:** The App-owned local runtime holds Teamcenter credentials and SOA/FMS sessions, exposes only closed read/launch operations, and returns bounded observation pages. The Simulation backend persists immutable source/observation/AH facts; the web UI uses cached observations immediately. VisMockup opens the official online CPS first, then a version-pinned native AH bridge maps stable occurrences to session-only CPS keys and applies idempotent AH diffs without changing CPS.

**Tech Stack:** Python/FastAPI capability runtime, MySQL test schema, .NET 8 App-owned ConnectorHost, Teamcenter 14.2 Java SOA runtime, Electron 41/Node.js, SQLite local cache, vanilla JavaScript UI.

**Spec:** `docs/superpowers/specs/2026-09-15-teamcenter-product-structure-vismockup-bridge-design.md`

## 2026-09-16 execution checkpoint

Implemented and machine-tested in the `test` worktrees: exact Item/revision search, current-user-only local login IPC, bounded read-only Teamcenter observation, local SQLite pages, append-only Simulation snapshots, cached model-tree rendering, online-source binding, official `createLaunchInfo`/VVI/`runner.exe` launch, and exact `__PLM_INST_UID`-first runtime node mapping. The page projection also carries relative/absolute transforms, bbox, torque, torque importance, weight, ownership, component type, revision, and JT Dataset/ImanFile references.

The planned AH writer is deliberately not advertised in the test Catalog. The native inventory reader remains available, but mutation stays fail-closed until a live test proves stable occurrence-to-CPS mapping, idempotent copied-link insertion, and unchanged CPS parent/name. This checkpoint prevents an unimplemented contract from appearing as an available Capability.

Remaining release gates: apply migration `0026` with the dedicated test DDL identity, run a credentialed Tool2025/W10 end-to-end observation and official launch against the packaged ConnectorHost, then implement and live-verify Task 8 before enabling bidirectional AH writes. These gates cannot be converted into AI self-approval.

## Global Constraints

- All business capabilities remain owned by `simulation`; no new domain is created.
- Teamcenter product data is strictly read-only: no generic invoke, reflection passthrough, `setProperties`, `saveBOMWindows`, structure mutation, upload, or write ticket.
- Passwords, cookies, SOA/FMS tokens, SessionID, CredToken, and VVI bodies remain local and never enter capability payloads, databases, logs, command lines, or renderer persistence.
- An online CPS is opened only through Teamcenter `createLaunchInfo` plus official `runner.exe`; cached nodes and PLMXML never reconstruct an online CPS.
- An AH is projected into the same attested VisMockup `document_session` as its CPS; products are copied as links and original CPS parentage is unchanged.
- Runtime numeric node keys are session-only. Persist stable Teamcenter occurrence identity, AI00 insertion identity, hashes, timestamps, and source selectors instead.
- Same-name sources and repeated occurrences are never merged.
- Structure/AH operations are bounded, paginated, idempotent, cancel-aware, and do not block the renderer or VisMockup UI thread.
- Existing PLMXML/JT import remains explicit and source-typed; it cannot silently become an online source.
- `machine_passed`, `human_approved`, and `runtime_verified` are reported independently.

---

### Task 1: Close the Teamcenter and VisMockup operation contracts

**Files:**
- Create: `docs/contracts/teamcenter.product_structure.observe@1.json`
- Create: `docs/contracts/teamcenter.product_structure.page.read@1.json`
- Create: `docs/contracts/teamcenter.visualization.launch@1.json`
- Create: `docs/contracts/vismockup.alternate_hierarchy.apply@1.json`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Test: `backend/tests/test_connector_runtime_control_plane.py`

**Interfaces:**
- Produces operation IDs `teamcenter.product_structure.observe@1`, `teamcenter.product_structure.page.read@1`, `teamcenter.visualization.launch@1`, and `vismockup.alternate_hierarchy.apply@1` with generated SHA-256 contract hashes.
- Produces request capabilities `simulation.teamcenter.product_structure.observe.request@1`, `simulation.teamcenter.product_structure.page.read.request@1`, `simulation.teamcenter.visualization.launch.request@1`, and `simulation.vismockup.alternate_hierarchy.apply.request@1`.

- [ ] **Step 1: Write failing registration tests** asserting exact operation IDs/hashes, closed schemas, `simulation.use`, read/write classifications, confirmation policy, and no generic Teamcenter operation.
- [ ] **Step 2: Run** `python -m pytest backend/tests/test_connector_runtime_control_plane.py -q` and confirm the four capabilities are absent.
- [ ] **Step 3: Add closed JSON schemas.** The observe input is `{source_selector,max_nodes,max_depth,property_projection}`; page input is `{observation_id,cursor,page_size}`; launch input is `{source_selector,expected_visdoc_uid}`; AH apply input is `{document_session,hierarchy_gid,base_hash,desired_hash,cursor,max_operations}`. Set `page_size <= 1000`, `max_nodes <= 250000`, `max_depth <= 128`, and `max_operations <= 256`.
- [ ] **Step 4: Register the request capabilities** through the existing signed App runtime plan builder. Treat observe/page as reads from Teamcenter/runtime, launch/AH apply as runtime writes, and add readback for launch/AH outcome-unknown paths.
- [ ] **Step 5: Run the registration test** and commit only the contract/registration files.

### Task 2: Persist immutable online sources and product-structure observations

**Files:**
- Create: `backend/db/migrations/domains/simulation/0026_teamcenter_online_structure_observations.sql`
- Create: `plugins/simulation/simulation_backend/domain/product_structure_observation.py`
- Modify: `plugins/simulation/simulation_backend/data/workspace_repository.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/workspaces.py`
- Test: `plugins/simulation/tests/test_product_structure_observation_repository.py`
- Test: `backend/tests/test_schema_migration_static.py`

**Interfaces:**
- Produces `register_online_source(workspace_gid, selector, expected_workspace_version, actor_gid, tenant_gid, idempotency_key)`.
- Produces `begin_observation(...)`, `append_observation_page(...)`, `publish_observation(...)`, and `get_observation_page(...)`.

- [ ] **Step 1: Write repository tests** for selector identity, repeated same-name sources, immutable observation manifests, duplicate occurrences, chunk replay, hash mismatch, partial observation, and publish-after-all-pages.
- [ ] **Step 2: Run the new tests** and confirm missing repository methods/migration failures.
- [ ] **Step 3: Add tables** for online sources, observation manifests, immutable chunks, workspace/source binding, and insertion instances. Unique keys use tenant/workspace/source identity and observation/page identity, never display name.
- [ ] **Step 4: Implement canonical models.** `OccurrenceRecord` requires occurrence ID, parent ID, depth, order, Item/Revision identities, transform/bbox typed values, property provenance, and zero-or-more geometry references. Validation rejects cycles, duplicate occurrence IDs, out-of-range depth/count, and incomplete references.
- [ ] **Step 5: Implement transactional append/publish.** Page replays with the same hash return the saved result; different bodies conflict. Publishing verifies all page hashes and counts, then advances workspace revision once.
- [ ] **Step 6: Run repository and migration tests** and commit.

### Task 3: Productize the local Teamcenter read-only worker

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Adapters.Teamcenter/Ai00.Connector.Adapters.Teamcenter.csproj`
- Create: `local-runtime/src/Ai00.Connector.Adapters.Teamcenter/TeamcenterReadOnlyAdapter.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.Teamcenter/TeamcenterWorkerProcess.cs`
- Create: `local-runtime/src/Ai00.Connector.Adapters.Teamcenter/java/Ai00TeamcenterWorker.java`
- Create: `local-runtime/src/Ai00.Connector.Adapters.Teamcenter/java/com/teamcenter/services/rac/visualization/_2013_05/DataManagement.java`
- Modify: `local-runtime/Ai00.LocalRuntime.sln`
- Modify: `local-runtime/src/Ai00.Connector.AppHost/Ai00.Connector.AppHost.csproj`
- Modify: `local-runtime/src/Ai00.Connector.AppHost/Program.cs`
- Test: `local-runtime/tests/Ai00.Connector.Tests/TeamcenterReadOnlyAdapterTests.cs`

**Interfaces:**
- Produces a persistent local worker protocol over inherited stdin/stdout: `login`, `status`, `search`, `observe`, `page`, `launch`, `logout`.
- The C# adapter exposes only the four operation contracts from Task 1; credentials enter through a local authenticated App IPC command and are never members of an execution plan.

- [ ] **Step 1: Write recording-transport tests** proving the allowlist contains login/logout, load/query, temporary BOMWindow create/expand/close, properties, GRM, read tickets, `createLaunchInfo`, and no persistent Teamcenter write.
- [ ] **Step 2: Write process-security tests** proving credentials are sent only via inherited stdin, are absent from arguments/environment/log output, response size is bounded, malformed lines terminate the worker, and logout/process exit zeroes the credential holder.
- [ ] **Step 3: Run the tests** and confirm missing adapter/worker failures.
- [ ] **Step 4: Implement the Java 11 worker** by extracting the verified probe logic. Use strong typed SOA services, the lightweight Visualization compatibility DTO, initialized `Map<String,String>`, and no `sun.misc.Unsafe`. Compile with `--release 11`.
- [ ] **Step 5: Implement observation paging** into a restricted local SQLite/file cache. Expansion and property fetch use batches; geometry records contain Dataset/ImanFile identities but do not obtain tickets or download JT during observation.
- [ ] **Step 6: Implement official launch** using `createLaunchInfo`; keep VVI only in memory/ACL-restricted random temp file, encode its path as UTF-16BE for `runner.exe`, wait for attested `visDocUid`, then delete the file.
- [ ] **Step 7: Add the C# supervisor** with one worker per local user/session, bounded line protocol, cancellation, timeout, restart on protocol failure, and stable sanitized errors.
- [ ] **Step 8: Run unit tests and a test-host smoke test** with the small Tool2025 object; commit without generated credentials, VVI, logs, or cache files.

### Task 4: Orchestrate observation pages into the Simulation snapshot

**Files:**
- Create: `plugins/simulation/simulation_backend/capabilities/product_structures.py`
- Create: `plugins/simulation/simulation_backend/application/product_structure_workflow.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_runtime.py`
- Test: `plugins/simulation/tests/test_product_structure_capabilities.py`
- Test: `plugins/simulation/tests/test_product_structure_workflow.py`

**Interfaces:**
- Produces `simulation.environment.online_source.bind@1`, `simulation.product_structure.snapshot.get@1`, and an internal workflow consuming the local observe/page operations.

- [ ] **Step 1: Write failing capability tests** for ownership, exact selector, idempotency, version conflict, bounded pagination, partial failure retaining prior snapshot, and source-name collisions.
- [ ] **Step 2: Run tests** and confirm absent workflow/capabilities.
- [ ] **Step 3: Implement source binding and snapshot reads** with closed schemas and resource scope `simulation-workspace`.
- [ ] **Step 4: Implement the workflow**: queue observe, persist manifest, pull bounded pages, append idempotently, publish only complete/declared-partial results, and expose progress without blocking the HTTP request.
- [ ] **Step 5: Run tests** and commit.

### Task 5: Add local Teamcenter login/source UI and cached model tree

**Files (frontend `test` worktree):**
- Create: `packages/sim-plugin/web/cad_sim/teamcenter_source.js`
- Create: `packages/sim-plugin/web/cad_sim/teamcenter_source.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/index.html`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.css`
- Modify: `packages/core/electron/preload.js`
- Modify: `packages/sim-plugin/electron/handlers.js`
- Modify: `packages/sim-plugin/manifest.json`

**Interfaces:**
- Produces UI states `signed_out|signing_in|ready|expired|unavailable` and exact source selection.
- Consumes Task 4 snapshot pages and the App-local session IPC from Task 3.

- [ ] **Step 1: Write controller tests** for password non-persistence, login state, exact Item/revision selection, cached-first tree, manual refresh, duplicate occurrences, session expiry, and switching A-B-A.
- [ ] **Step 2: Run tests** and confirm missing controller/UI.
- [ ] **Step 3: Add a lightweight login/source modal** in the model-file toolbar. Password uses a password input, is never serialized, and is cleared immediately after local IPC completion.
- [ ] **Step 4: Render snapshot pages through the existing virtual/cached tree path.** Cache labels show captured time/configuration and “未自动重读”; right-click owns refresh.
- [ ] **Step 5: Copy source files to `dist-production` through the existing web build**, run focused UI tests and `npm run build:web:test-governance`, then commit.

### Task 6: Bind official online launch to environment/document switching

**Files:**
- Modify: `packages/sim-plugin/electron/document_session_coordinator.js`
- Modify: `packages/sim-plugin/electron/vismockup_controller.js`
- Create: `packages/sim-plugin/web/cad_sim/online_document_projection.js`
- Create: `packages/sim-plugin/web/cad_sim/online_document_projection.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/live_document_switcher.js`

**Interfaces:**
- Produces `openOnlineSource(environment, sourceSelector)` returning `{documentId,documentSession,visDocUid,insertionInstanceId}`.
- Consumes Task 3 launch and existing native document identity/list/select functions.

- [ ] **Step 1: Write failing tests** for already-open exact-source reuse, no name-based reuse, launch timeout, delayed runner success, generation supersession, process/document restart, and hide-on-leave Simulation.
- [ ] **Step 2: Run tests** and confirm missing online projection.
- [ ] **Step 3: Implement launch coordination**: resolve environment source, reuse only exact `visDocUid`, otherwise request official launch, poll 90–180 seconds, attest the new document, bind it, then attach the 3D child window.
- [ ] **Step 4: Make environment/document switching last-intent-wins** and ensure process/session changes invalidate runtime mapping before controls re-enable.
- [ ] **Step 5: Run focused Electron/UI tests and commit.**

### Task 7: Establish stable occurrence mapping

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/OnlineOccurrenceMapper.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Create: `plugins/simulation/simulation_backend/domain/occurrence_mapping.py`
- Test: `local-runtime/tests/Ai00.Connector.Tests/OnlineOccurrenceMapperTests.cs`
- Test: `plugins/simulation/tests/test_occurrence_mapping.py`

**Interfaces:**
- Produces mapping states `complete|partial|ambiguous|stale` keyed by snapshot occurrence, document session, insertion instance, and runtime CPS key.

- [ ] **Step 1: Write tests** with repeated ItemRevision occurrences, same names, different parent paths/transforms, a restarted document, and deliberately ambiguous evidence.
- [ ] **Step 2: Run tests** and confirm missing mapper.
- [ ] **Step 3: Implement deterministic matching** using exact Teamcenter occurrence/absolute occurrence UID first, then verified parent-chain/product-revision/path evidence; names are display-only hints.
- [ ] **Step 4: Refuse controls for partial/ambiguous/stale entries** and return actionable error state rather than a disabled cursor without explanation.
- [ ] **Step 5: Run tests and commit.**

### Task 8: Incrementally project AI00 AH into the same VisMockup document

**Files:**
- Create: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/AlternateHierarchyProjector.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Modify: `local-runtime/native/VisMockupHierarchyBridge/bridge.cpp`
- Create: `local-runtime/tests/Ai00.Connector.Tests/AlternateHierarchyProjectorTests.cs`
- Modify: `plugins/simulation/simulation_backend/application/connector_workflow_v2.py`
- Test: `plugins/simulation/tests/test_alternate_hierarchy_projection_workflow.py`

**Interfaces:**
- Consumes desired AI00 AH pages and Task 7 CPS mappings.
- Produces cursor-based diffs and readback `{applied,skipped,conflicts,next_cursor,result_hash}`.

- [ ] **Step 1: Write fake-native tests** for create/reuse/rename root, duplicate product links with distinct insertion IDs, unchanged retry, missing mapping, stale document session, no CPS mutation, and a 10,000-node chunk schedule.
- [ ] **Step 2: Run tests** and confirm missing projector.
- [ ] **Step 3: Implement only the live-verified native set**: enumerate/create/add/remove whole AI00-owned AH, rename root, and add CPS product reference. Version/hash whitelist the bridge and execute on the VisMockup UI thread.
- [ ] **Step 4: Feature-gate unverified virtual child create/move/delete.** If the desired BOP needs one of them, return `native_ah_operation_unverified` and preserve AI00 facts instead of issuing an unsafe call.
- [ ] **Step 5: Apply bounded idempotent chunks** with base/desired hashes, operation cursor, fencing, readback, and outcome-unknown reconciliation. Never move/delete CPS keys.
- [ ] **Step 6: Run local runtime and backend workflow tests; then perform a live test only against an AI00-owned test AH and verify original CPS parent/name unchanged. Commit.**

### Task 9: Governance, end-to-end verification, and test release

**Files:**
- Modify generated Catalog/Descriptor/provider/exposure/consumer artifacts through repository scripts.
- Create: `docs/acceptance/teamcenter-online-model-ah-test-snapshot.json`
- Create: `docs/runbooks/teamcenter-online-model-ah.md`

**Interfaces:**
- Produces immutable machine evidence and a human-reviewable test candidate; it does not self-approve.

- [ ] **Step 1: Run capability/catalog generators and checks**; inspect Registry bindings, exposure, consumers, dependencies, migrations, permissions, and generated diffs.
- [ ] **Step 2: Run backend, local runtime, Electron security, simulation UI, and build tests.** Record pass/fail/skip separately.
- [ ] **Step 3: Run Tool2025 end to end**: login, read complete tree, official online launch, bind document, map sampled occurrences, create an AI00-owned AH, add a copied product link, and read back CPS parent unchanged.
- [ ] **Step 4: Run W10 performance** without “show all geometry”: cold observation, hot cache, manual refresh, VVI open, mapping, and chunked AH projection. Record counts/calls/timing/memory and explain direct-vs-PLMXML differences.
- [ ] **Step 5: Scan logs/cache/database** for passwords, VVI bodies, SessionID and CredToken; any hit fails release.
- [ ] **Step 6: Build frontend/backend App test artifacts and update the local Gitea/GitHub `test` branches only after clean readback.** Report `machine_passed`, `human_approved`, and `runtime_verified` independently; do not mark approval from AI output.

## Plan self-review

- Spec coverage: source identity, authentication, read-only structure/JT metadata, immutable cache/history, official online launch, switching, mapping, BOP/AH projection, large trees, errors, migration, and governance each map to a task.
- Placeholder scan: no implementation step delegates unspecified error handling or tests; live-unverified AH operations are explicitly gated rather than deferred invisibly.
- Type consistency: `source_selector`, `observation_id`, `document_session`, `visDocUid`, `insertionInstanceId`, `occurrence_id`, `hierarchy_gid`, cursors, hashes, and mapping states use the same names across tasks.
- Scope control: Task 3–5 form the first usable slice (direct cached tree); Task 6 adds online opening; Task 7–8 add safe mapping/AH projection. Each can be reviewed independently.
- Governance: local authentication is not exposed publicly; business snapshot/binding/projection effects remain governed Simulation capabilities. No old approval is reused for new contracts.
