# Live-document synchronization implementation evidence

This is an implementation checkpoint, not a release or completion declaration.

## 1. Change classification

Simulation-owned internal implementation plus a planned new create-from-live-document business effect. Repeated insertion semantics differ from the path-deduplicating legacy operation; do not silently change `vismockup.model.insert@1`.

## 2. Authoritative context inspected

- Simulation workspace/model-document/AH Providers, repository, migrations 0011/0018, Connector contracts/adapter, and actual AppHost plan journal.
- `PlanExecutionWorker` journals/rejects plan replay by signed PlanId. StepId alone is not a cross-plan idempotency key.
- `0011_simulation_workspaces.sql` declares `uq_sim_vm_document_source(workspace_gid,source_identity_hash)`. The legacy source row cannot also represent every repeated insertion. Do not simply remove this index without reviewing existing consumers.
- Installed `Vis3D.dll`, `DMUtils.dll`, `VisAutomation.tlb`; live process 297616 / UI thread 137448 inspected read-only.

## 3. Reuse and ownership

Reuse Simulation workspace/AH ownership and the existing plan journal. Add explicit insertion-instance identity rather than duplicate caches or filesystem-path deduplication. No new production Capability, arbitrary native command exposure, or database write was performed in this checkpoint.

## 4. Implemented boundary

- `domain/live_hierarchy_sync.py`: validated, same-session, complete-observation three-way merge; references require source + insertion-instance + occurrence. Partial observations cannot become deletion baselines.
- `domain/live_document_import.py`: immutable model observation projection; preserves first-seen time and insertion identity; retains unobserved models; ambiguous disappeared/reappeared keys fail closed. AH links resolve to specific observed insertions; unresolved links are retained and prevent completion.
- Frontend `packages/sim-plugin/electron/document_session_coordinator.js`: adopted-document selection requires re-read binding; slow creation does not block selecting another document or steal selection later. Adapter injection is required; no UI action/IPC registration has been wired yet.

## 5. Verification evidence

Backend command:

```text
py -m pytest plugins/simulation/tests/test_live_document_import.py plugins/simulation/tests/test_live_hierarchy_sync.py plugins/simulation/tests/test_alternate_hierarchy_capabilities.py plugins/simulation/tests/test_environment_materialization.py plugins/simulation/tests/test_environment_document_capabilities.py plugins/simulation/tests/test_environment_document_repository.py -q -p no:cacheprovider --tb=short --durations=3
```

Result: 68 passed in 4.63 s. One root with 100,000 siblings: 1.14 s for the Python test, including setup/verification. 10,000 AH reuse one inventory index (0.11 s). Not a native synchronization SLA.

Frontend command:

```text
node --test --experimental-test-isolation=none packages/sim-plugin/electron/document_session_coordinator.test.js
```

Result: 14 passed, including create-from-document intent coordination, document-session pinning, and late-failure isolation. Unit adapters simulate the persistence/native boundary; these are not end-to-end tests.

### Read-only native findings

`IVis3DDocAutomation` IID `4C5B1E7B-279D-11D1-AD40-0060B01AEE42` is available on the native owning document. `IVisDispDoc` IID `8998EB81-80A4-416E-8460-3FBB746FBD30` is not available on that same object (E_NOINTERFACE); these are different interfaces, not evidence that the document is unavailable.

- Dispatch 12 / `CountFullName2`: source count including the primary source.
- Dispatch 13 / `FullName2(index)`: source strings, index 0 is the primary `FullName` (confirmed by disassembly).
- First document: six sources, two URI-shaped sources and four absolute local-file paths; six canonical top-level roots with keys 6, 1398, 1938, 2241, 2746, 2947.
- Second document: one URI-shaped source; one top-level root key 3.
- `IProductStructure.GetPrototype` and `IProductProtoNode.GetData` succeeded for these roots. Direct pointer equality did not correlate them with the imported-source record fields. Do not fabricate the remaining source-to-root mapping or assume list order is a contract.
- No pair of exactly equal printable root names was observed in this sample; repeated-identical-source mapping is not runtime-verified.

Probe source/log: `E:/Projects/ai00_v3/.runtime/vis_probe/read_model_roots.cpp`, `model-roots-read.log`. Research-only injected DLLs remain loaded in VisMockup until process exit; no original product/AH structure was changed and no geometry-load method was called. Do not ship the hardcoded addresses or record offsets.

## 2026-09-14 evening correction: create from current document is not live-ready

The test client process started at 18:50, before the real page adapter/bootstrap was written at 20:22–20:23. The screenshot's exact “当前连接尚未提供实时文档绑定” message is the controller's no-adapter branch; it is not an adoption result. The page now wires the adapter and switch selector in source, but the running Electron process has not loaded the new native selector binary. Frontend focused checks: 30 passed; native isolated MDI selector harness passed. No live create or switch was claimed.

The test Catalog was regenerated to an isolated candidate `rel_2292f6badeb76bab36b3f89e275ad947` (774 descriptors); exact check and `start_test_app.ps1 -ValidateOnly` pass. The shared `test_` simulation ledger matched 0001–0024 checksums, and only migration 0025 was applied; readback found both new `test_` tables and ledger 0025. This is test schema readiness, not Capability approval or runtime success. Backend focused tests: 55 passed with the existing Windows pytest temp-directory ACL workaround.

An independent read-only COM test proved a deeper connector blocker. Two original `VisView_NG` processes were running; `VFFrame.Application` Dispatch started a third empty COM server, reporting its own PID and zero documents instead of the user's embedded document. The exact newly launched empty PID 263184 was stopped after verification; original PIDs 124004 and 297616 remained untouched. Earlier research in `D:/Temp/vis/vismockup-plmxml-integration.md` already documented this per-instance COM behavior and ROT absence. Current `vismockup.document.identity.read@1` requires a unique process and reads the active document via that COM path, so reloading the client alone cannot make current-document adoption succeed. The in-process research probe in `D:/Temp/vis/vismockup-live-alternate-hierarchy-crud.md` did access the user's existing document, but its memory-layout addresses and injection lifecycle are explicitly research-only. A governed, process-bound native identity/read path is still required.

Current status: `machine_passed` for the full feature is unverified; `human_approved` is unverified; `runtime_verified` is false. The UI's separate model/AH “not started” statuses are accurate: creation binding does not yet ingest those structures.

## 6. Governance status (historical checkpoint; superseded where noted above)

- Relevant unit checks: passed. Global `machine_passed`: not established.
- `human_approved`: no exact-version/definition-hash decision verified for new effects.
- `runtime_verified`: no end-to-end create/bind/ingest evidence. The read-only probes above are narrow experimental evidence only.
- Read-only local test DB inspection found `test_workmanship_base_capability_snapshots` absent. This does not prove the independent test-governance service lacks its own data. The documented local independent service health endpoint on port 8094 was unreachable.
- Existing offline governance scan returned `blocked / pinned_product_descriptor_count_mismatch`: script expects 545 stable entries while the current Catalog has 546 (769 total). No pinned count, approval, or gate was changed to bypass this result.
- Existing scan report: `.runtime/live-sync-governance-scan.json`. Its zero scan totals are early-abort defaults, not an empty Catalog.

## 7. Remaining work and risks

Durable atomic create-and-bind, instance storage separate from source rows, bounded staging/ingestion, governed contract/version migration, trustworthy native source/instance mapping, and actual UI/IPC integration remain incomplete. No clickable create-from-document feature has been delivered yet. Resolve test governance configuration with the platform owner rather than creating governance tables in the product test database blindly.

Self-review identified and fixed per-AH inventory-index reconstruction: `HierarchyReferenceProjector` builds the lookup once per fixed inventory revision. A 10,000-AH test verifies one inventory traversal. Batch integration must reuse this projector; this is not a native performance claim.

## Test-governance repair follow-up

Latest correction from the user: the intended isolation is a shared database
with `test_` tables, not a separate database. Read-only preflight against
`.runtime/local-app-test.env` verifies OceanBase compatibility and finds the
test Catalog release table present, but all 28 governance tables and its ledger
absent. The earlier separate-database assumption is superseded.

Fixed the migration command to support exact `TABLE_PREFIX=test_`, including
backfill dependencies, metadata parameter names, ledger, and lock; checksums
remain bound to immutable source migrations. All 14 migration tests pass,
including a recording-connection execution of all nine migrations proving no
unprefixed table SQL/probes are emitted (simulated boundary, not live DDL).
Update: all nine governance migrations have now been applied to the verified
shared database's `test_` namespace, and immediate replay applied zero. The
separate `.runtime/local-app-migration.env` was rejected because it targets a
different local database. SHOW GRANTS confirmed the actual shared-test account
already has CREATE/ALTER; it was explicitly used without changing any privilege.
Execution used a workstation mutex for the single local migration runner because
this OceanBase lacks GET_LOCK. The five empty binary-hash tables were rebuilt,
retaining empty backups; the empty snapshot hash column was recreated NOT NULL.
See governance operations for exact recovery limits. Candidate fingerprint,
human approval and end-to-end feature verification remain unresolved.

User explicitly included shared-platform test configuration repairs; production and approval bypass remain excluded. Classification: implementation/configuration fix, platform governance owner; simulation is the affected consumer. No Capability identity, business definition, API, permission, transaction, or database schema changes in this repair.

Authoritative comparison: Catalog commit `46209c0dd` adds stable `craft.resource_requirement.get@1` relative to the previous scanner baseline `56af45fcd`. Current committed candidate `ee3f0a2ef` contains 769 total / 546 stable descriptors. Corrected scanner pin 545 to 546 and stale test assertions 730/544 to 769/546. These are inventory assertions, not human approval. Targeted Catalog pin and craft resource-requirement provider tests: 23 passed. The initial full Catalog suite had 32 passed, 4 failed, 1 setup error (temporary-directory access); Provider artifact mismatch remains a real failure, not waived.

The subsequent offline scan advances past the count gate and blocks at `capability_registry_load_error`. Registry loading identifies `provider_artifact_mismatch: simulation`; current uncommitted simulation domain files change its artifact fingerprint. Rebuild and review the candidate only after implementation settles; do not disable fingerprint verification.

Read-only service inspection: `AI00Backend-CapabilityV2` is stopped. Its launcher uses the older `capability-v2-implementation` worktree at `655418f80` and `.env.v2.runtime`, copies a shared database URL into domain database settings, and has no dedicated governance DDL configuration in the inspected files. The local app test config uses `test_` but likewise has no dedicated governance DDL URL. No service was started, database migrated, credentials logged, or old environment silently repurposed. Dedicated test-governance runtime/DDL configuration remains unverified and is required before live repair. Machine status remains blocked; human approval and end-to-end runtime verification remain unverified.
