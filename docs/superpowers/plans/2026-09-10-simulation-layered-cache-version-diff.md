# Simulation Layered Cache and Version Diff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Make VisMockup structure reopening fast and correct across restarts and model revisions, add a separately invalidated simulation-workspace/binding cache, and provide governed manual snapshots plus optional version-difference reports without caching or delaying COM control commands.

**Architecture:** Keep the three caches independent: Connector SQLite owns only the raw VM tree projection; browser IndexedDB owns only user-scoped workspace projections and binding projections; MySQL remains authoritative for workspace state, VM snapshots, checkpoints, and diff reports. Validate every cached generation with stable identity plus revision/subtree fingerprints, validate browser projections with a short-lived server lease and `cache_revision_hash`, and route every server write/read through Capability Gateway providers.

**Tech Stack:** .NET/C# Connector, SQLite, Python 3/FastAPI provider layer, MySQL/OceanBase-compatible SQL, vanilla JavaScript, IndexedDB, Node test runner, pytest.

**Spec:** `docs/superpowers/specs/2026-09-10-simulation-three-layer-cache-version-diff-design.md`

## Global Constraints

- Do not add a BOP process-diagram cache in this implementation; that is a later project.
- Do not cache, batch, or replay VisMockup visibility, selection, highlight, open, or close commands. Only tree reads may use the Connector cache.
- Server-persisted entities use `backend.platform_sdk.ids.next_gid()`; Connector SQLite uses local integer row IDs and stores server GIDs only after the server assigns them.
- Cache hits must never be based only on a path, transient COM document ID, workspace `version_gid`, or tenant ID.
- Any uncertain VM revision signal must return `uncertain` and trigger a bounded refresh; it must never silently reuse a stale generation.
- Browser cache keys must include `auth_subject_gid` and `workspace_gid`. Expired leases must not render protected cached data.
- All workspace mutations must advance both `row_version` and `cache_revision_hash` in the same transaction.
- Preserve the existing two-phase governed Connector workflow for document acquisition. A manual checkpoint may reference only a completed snapshot request whose exact snapshot hash is re-read by the Provider.
- Use generation-level atomic replacement. A failed refresh must leave the preceding complete generation readable.
- Do not store JT, PLMXML, screenshots, or other model blobs in SQLite or IndexedDB.
- Work in the existing dirty worktrees without staging or reverting unrelated user changes. Commit only files named by the current task.

---

### Task 1: Define deterministic VM document, node, and subtree fingerprints

**Files:**

- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/DocumentSnapshotReader.cs`
- Add: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupTreeFingerprint.cs`
- Add: `local-runtime/tests/Ai00.Connector.Tests/VisMockupTreeFingerprintTests.cs`

**Step 1: Write the failing tests**

Cover stable document identity, deterministic canonicalization, bottom-up subtree hashing, child reorder detection, representation revision changes, and insufficient-evidence handling.

```csharp
[Fact]
public void SameSourceAndTreeProduceTheSameHashesAcrossSessions()
{
    var left = Fixture(sessionId: "session-a", source: @"C:\models\W10.vfz");
    var right = Fixture(sessionId: "session-b", source: @"c:\models\W10.vfz");

    Assert.Equal(Fingerprint.DocumentIdentity(left), Fingerprint.DocumentIdentity(right));
    Assert.Equal(Fingerprint.SubtreeHash(left.Root), Fingerprint.SubtreeHash(right.Root));
}

[Fact]
public void ChangedChildRevisionChangesOnlyItsAncestorChain()
{
    var before = Fixture();
    var after = before.WithNodeRevision("part-2", "B");

    var changes = Fingerprint.Compare(before, after);

    Assert.Contains("part-2", changes.ChangedNodeKeys);
    Assert.Contains("root", changes.ChangedNodeKeys);
    Assert.DoesNotContain("part-1", changes.ChangedNodeKeys);
}

[Fact]
public void MissingRevisionEvidenceIsUncertainNotFresh()
{
    var manifest = Fingerprint.Manifest(FixtureWithoutRevisionOrFileMetadata());
    Assert.Equal(CacheFreshness.Uncertain, manifest.Freshness);
}
```

**Step 2: Run the focused tests and confirm RED**

Run:

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --filter VisMockupTreeFingerprintTests -m:1
```

Expected: compilation fails because `VisMockupTreeFingerprint` and its manifest types do not exist.

**Step 3: Implement canonical fingerprint types**

Add immutable types with these exact responsibilities:

```csharp
internal enum CacheFreshness { Fresh, Changed, Uncertain }

internal sealed record VmTreeNodeFingerprint(
    string ExternalNodeKey,
    string RevisionFingerprint,
    string SubtreeHash);

internal sealed record VmTreeManifest(
    string DocumentIdentityHash,
    string RootNodeKey,
    string RootSubtreeHash,
    CacheFreshness Freshness,
    IReadOnlyList<VmTreeNodeFingerprint> Nodes);
```

Implement:

- normalized `SourceIdentity + RootNodeKey` document SHA-256;
- node revision evidence priority: PLMXML/Teamcenter revision, representation location metadata, then local JT length plus UTC mtime;
- canonical attribute serialization with ordinal key ordering;
- bottom-up `subtree_hash = SHA256(node_identity + revision_fingerprint + ordered child subtree hashes)`;
- no use of transient document/session IDs in cross-restart identity;
- explicit `Uncertain` when no trustworthy revision source exists.

**Step 4: Run the focused tests and confirm GREEN**

Run the command from Step 2.

Expected: all `VisMockupTreeFingerprintTests` pass.

**Step 5: Commit**

```powershell
git add local-runtime/src/Ai00.Connector.Adapters.VisMockup/DocumentSnapshotReader.cs local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupTreeFingerprint.cs local-runtime/tests/Ai00.Connector.Tests/VisMockupTreeFingerprintTests.cs
git commit -m "feat(connector): fingerprint vismockup tree revisions"
```

---

### Task 2: Upgrade Connector SQLite to atomic versioned generations

**Files:**

- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupTreeCache.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/VisMockupSnapshotTests.cs`

**Step 1: Write failing migration, hit, miss, and rollback tests**

```csharp
[Fact]
public void CacheHitRequiresMatchingDocumentAndRootSubtreeHashes() { /* arrange v2 generation; assert hit */ }

[Fact]
public void ChangedRevisionCreatesNewGenerationWithoutDeletingLastGoodGeneration() { /* assert two generations */ }

[Fact]
public void FailedRefreshLeavesThePreviousCompleteGenerationReadable() { /* abort writer; assert old tree */ }

[Fact]
public void LegacySchemaIsMigratedWithoutTreatingRowsAsVerifiedFresh() { /* assert Uncertain */ }
```

**Step 2: Run the focused tests and confirm RED**

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --filter VisMockupSnapshotTests -m:1
```

Expected: new generation and manifest assertions fail.

**Step 3: Implement the v2 SQLite schema and one-transaction publish**

Retain the existing cache database location, set `PRAGMA journal_mode=WAL`, and migrate to:

```sql
CREATE TABLE vm_cache_documents (
  local_id INTEGER PRIMARY KEY,
  document_identity_hash TEXT NOT NULL UNIQUE,
  source_identity TEXT NOT NULL,
  root_node_key TEXT NOT NULL,
  current_generation INTEGER,
  last_accessed_utc TEXT NOT NULL
);

CREATE TABLE vm_cache_generations (
  document_local_id INTEGER NOT NULL,
  generation INTEGER NOT NULL,
  root_subtree_hash TEXT NOT NULL,
  freshness TEXT NOT NULL,
  max_depth INTEGER NOT NULL,
  completed_utc TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  PRIMARY KEY (document_local_id, generation)
);

CREATE TABLE vm_cache_nodes (
  document_local_id INTEGER NOT NULL,
  generation INTEGER NOT NULL,
  external_node_key TEXT NOT NULL,
  parent_external_node_key TEXT,
  child_order INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  revision_fingerprint TEXT NOT NULL,
  subtree_hash TEXT NOT NULL,
  PRIMARY KEY (document_local_id, generation, external_node_key)
);
```

Write nodes and generation metadata first; switch `current_generation` only at transaction commit. A legacy cache row may seed display only after a live manifest check; otherwise refresh.

**Step 4: Integrate cache validation into `TreeAsync`**

`TreeAsync(maxDepth)` must:

1. read a lightweight live manifest;
2. return the current generation only when identity, depth coverage, and root subtree hash agree;
3. refresh only changed/uncertain branches when node manifests are available, otherwise perform one bounded full tree read;
4. persist a new complete generation;
5. return a response containing `cache_status`, `document_identity_hash`, `root_subtree_hash`, and nodes.

Do not touch control-command dispatch paths.

**Step 5: Run tests and commit**

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --filter VisMockupSnapshotTests -m:1
git add local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupTreeCache.cs local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs local-runtime/tests/Ai00.Connector.Tests/VisMockupSnapshotTests.cs
git commit -m "feat(connector): version vismockup tree cache generations"
```

Expected: focused tests pass and visibility/highlight tests remain unchanged.

---

### Task 3: Bound and clean the Connector cache

**Files:**

- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupTreeCache.cs`
- Add: `local-runtime/tests/Ai00.Connector.Tests/VisMockupTreeCacheRetentionTests.cs`

**Step 1: Write failing capacity tests**

Test the 2 GiB hard limit through an injected size policy rather than allocating gigabytes:

```csharp
[Fact]
public void CleanupRemovesOldGenerationsThenClosedLruDocumentsToSixtyPercent() { /* assert order */ }

[Fact]
public void CurrentDocumentAndUnpublishedGenerationAreNeverEvicted() { /* assert protected */ }

[Fact]
public void OversizedProtectedContentDisablesNewWritesWithoutBreakingReads() { /* assert read succeeds */ }
```

**Step 2: Implement and verify retention**

Add a `VisMockupTreeCachePolicy` with default hard limit 2 GiB, cleanup trigger 80%, target 60%, and injectable file-size reader for tests. Cleanup order is old generations, then LRU closed documents. Run incremental vacuum after deletions; never persist source model blobs.

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj -c Release --filter VisMockupTreeCacheRetentionTests -m:1
```

Expected: all retention tests pass.

**Step 3: Commit**

```powershell
git add local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupTreeCache.cs local-runtime/tests/Ai00.Connector.Tests/VisMockupTreeCacheRetentionTests.cs
git commit -m "feat(connector): bound vismockup cache growth"
```

---

### Task 4: Add authoritative workspace cache revisions

**Files:**

- Add: `backend/db/migrations/domains/simulation/0016_simulation_cache_snapshots_and_diffs.sql`
- Modify: `plugins/simulation/simulation_backend/data/workspace_repository.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/workspaces.py`
- Modify: `plugins/simulation/tests/test_workspace_capabilities.py`
- Add: `plugins/simulation/tests/test_workspace_cache_revision.py`

**Step 1: Write failing repository contract tests**

```python
def test_every_workspace_mutation_advances_cache_revision_in_same_transaction():
    before = repository.get(WORKSPACE_GID, tenant_gid=TEAM_GID, owner_gid=USER_GID)
    result = repository.mutate(
        workspace_gid=WORKSPACE_GID,
        tenant_gid=TEAM_GID,
        owner_gid=USER_GID,
        expected_row_version=before["row_version"],
        idempotency_key="create-node-1",
        operation="create_node",
        values={"parent_gid": None, "node_type": "line", "name": "Line 1"},
    )
    after = repository.get(WORKSPACE_GID, tenant_gid=TEAM_GID, owner_gid=USER_GID)
    assert after["cache_revision_hash"] != before["cache_revision_hash"]
    assert result["cache_revision_hash"] == after["cache_revision_hash"]
```

Also add `test_failed_mutation_advances_neither_version_nor_cache_hash` and `test_canonical_patch_produces_deterministic_hash` with complete fake-connection assertions against the emitted SQL parameters and committed transaction state.

**Step 2: Add schema and hash helper**

In migration `0016`, add non-null `cache_revision_hash VARCHAR(71)` to `workmanship_sim_workspaces`, backfill `sha256:` plus 64 lowercase hex characters from canonical current state, and add checkpoint/diff tables described in Tasks 9 and 10 so the domain receives one forward migration.

Add a pure helper:

```python
def next_cache_revision_hash(previous: str, patch: Mapping[str, Any], next_row_version: int) -> str:
    canonical = json.dumps(patch, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(f"{previous}|{canonical}|{next_row_version}".encode()).hexdigest()
```

Use it in create, update, delete, node create/move/remove, binding create/remove, fork apply, and freeze transactions. Include `cache_revision_hash` in workspace summaries, full reads, and mutation outputs.

Migration rollback acceptance is additive and non-destructive: the previous application build must continue to read/write the workspace table while ignoring the new column and new tables. Rollback means deploying the prior application build and leaving additive data in place; do not drop checkpoint/report tables during emergency rollback.

**Step 3: Run tests and commit**

```powershell
python -m pytest plugins/simulation/tests/test_workspace_cache_revision.py plugins/simulation/tests/test_workspace_capabilities.py -q
git add backend/db/migrations/domains/simulation/0016_simulation_cache_snapshots_and_diffs.sql plugins/simulation/simulation_backend/data/workspace_repository.py plugins/simulation/simulation_backend/capabilities/workspaces.py plugins/simulation/tests/test_workspace_cache_revision.py plugins/simulation/tests/test_workspace_capabilities.py
git commit -m "feat(simulation): version workspace cache projections"
```

Expected: focused tests pass; every returned hash matches `^sha256:[0-9a-f]{64}$`.

---

### Task 5: Add a governed short-lived workspace cache lease

**Files:**

- Add: `plugins/simulation/simulation_backend/domain/cache_lease.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/workspaces.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/contracts.py`
- Add: `plugins/simulation/tests/test_workspace_cache_lease.py`
- Add descriptors and catalog entries under the repository's existing Simulation capability descriptor/catalog directories found by `rg -l 'simulation.environment.workspace.get'`.

**Step 1: Perform registry reuse scan**

```powershell
rg -n "cache_lease|projection_lease|workspace\.cache" backend plugins docs
```

Expected: no semantically equivalent stable Capability. If one exists, reuse it and record the mapping in the commit message rather than adding a duplicate.

**Step 2: Write failing capability tests**

Cover read authorization, subject scoping, 60–300 second TTL, signed payload tamper rejection, permission-version changes, and removed workspaces.

```python
def test_cache_lease_is_bound_to_actor_workspace_and_revision():
    result = provider.cache_lease_get({"workspace_gid": WORKSPACE_GID}, context)
    assert result["auth_subject_gid"] == context.user_gid
    assert result["cache_revision_hash"].startswith("sha256:")
    assert 0 < result["expires_in_seconds"] <= 300
```

**Step 3: Implement candidate Capability**

Register `simulation.environment.workspace.cache_lease.get@1` as a read Capability. Return:

```json
{
  "auth_subject_gid": "123",
  "workspace_gid": "456",
  "permission_version": 7,
  "row_version": 12,
  "cache_revision_hash": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "expires_at": "2026-09-10T10:00:00Z",
  "expires_in_seconds": 300,
  "read_lease": "signed-opaque-value"
}
```

Use the existing application signing/verification facility; do not introduce a new crypto package. Add `_RESOURCES` mapping to `simulation-workspace`. Provider must re-check current read permission before issuance.

**Step 4: Verify and commit**

```powershell
python -m pytest plugins/simulation/tests/test_workspace_cache_lease.py plugins/simulation/tests/test_workspace_capabilities.py -q
git add plugins/simulation/simulation_backend/domain/cache_lease.py plugins/simulation/simulation_backend/capabilities/workspaces.py plugins/simulation/simulation_backend/capabilities/provider.py plugins/simulation/simulation_backend/capabilities/contracts.py plugins/simulation/tests/test_workspace_cache_lease.py
python backend/scripts/build_capability_catalog.py --write
python backend/scripts/generate_capability_docs.py --write
git add docs/governance/capability-catalog-release.json docs/governance/capability-catalog-lineage.json docs/capabilities
git commit -m "feat(simulation): issue workspace cache read leases"
```

Expected: capability schema, authorization, descriptor, and provider tests pass.

---

### Task 6: Add the browser IndexedDB cache adapter

**Files:**

- Add in frontend worktree: `packages/sim-plugin/web/cad_sim/simulation_cache.js`
- Add in frontend worktree: `packages/sim-plugin/web/cad_sim/simulation_cache.test.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/index.html`

**Step 1: Write failing adapter tests**

Use an injected minimal IndexedDB-compatible backend in Node tests; production uses native IndexedDB. Test subject/workspace scoping, atomic generation publish, lease expiry, quota cleanup, and whole-generation eviction.

```javascript
test('never returns a workspace projection for another auth subject', async () => {
  await cache.putWorkspace({ authSubjectGid: '1', workspaceGid: '9', generation: projection });
  assert.equal(await cache.getWorkspace({ authSubjectGid: '2', workspaceGid: '9' }), null);
});

test('expired lease hides cached protected data', async () => { /* advance clock; assert null */ });
test('failed generation write preserves previous generation', async () => { /* reject transaction */ });
```

**Step 2: Implement `ai00-simulation-cache-v1`**

Expose:

```javascript
createSimulationCache({ indexedDB, clock, estimateStorage })
  .getWorkspace({ authSubjectGid, workspaceGid, lease })
  .putWorkspace({ authSubjectGid, workspaceGid, rowVersion, cacheRevisionHash, lease, workspace })
  .getBindings({ authSubjectGid, workspaceGid, workspaceNodeVersions, vmDocumentHash })
  .putBindings({ authSubjectGid, workspaceGid, generation, bindings })
  .putSnapshotSummary({ authSubjectGid, workspaceGid, snapshot })
  .putDiffSummary({ authSubjectGid, workspaceGid, report })
  .clearLocal({ authSubjectGid })
  .compact()
```

Store heads separately from immutable generation rows. Limit to the smaller of 200 MiB or 20% of reported browser quota. Evict complete old generations, never individual nodes from a live generation.

**Step 3: Verify and commit in frontend worktree**

```powershell
node --test packages/sim-plugin/web/cad_sim/simulation_cache.test.js
git add packages/sim-plugin/web/cad_sim/simulation_cache.js packages/sim-plugin/web/cad_sim/simulation_cache.test.js packages/sim-plugin/web/cad_sim/index.html
git commit -m "feat(simulation): cache workspace projections in indexeddb"
```

Expected: all cache adapter tests pass.

---

### Task 7: Integrate cached-first workspace display without weakening authorization

**Files:**

- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/environment_store.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/environment_workspace.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/environment_store.test.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/environment_workspace.test.js`

**Step 1: Write failing behavior tests**

```javascript
test('openWorkspace renders valid cached projection before full get', async () => { /* assert event order */ });
test('matching row version and cache hash skips full workspace get', async () => { /* assert invocations */ });
test('changed cache hash fetches authoritative workspace and replaces generation', async () => { /* assert */ });
test('expired lease shows skeleton and never cached nodes', async () => { /* assert */ });
test('cache failure degrades to ordinary gateway read', async () => { /* assert */ });
```

**Step 2: Inject cache and authenticated subject**

Change the constructor to:

```javascript
createEnvironmentStore({ invoke, cache = null, getAuthSubjectGid = () => null })
```

`openWorkspace` sequence:

1. call `simulation.environment.workspace.cache_lease.get@1`;
2. display a matching cached generation if the signed lease is unexpired;
3. if cached `row_version` and `cache_revision_hash` match the lease, finish without full `workspace.get`;
4. otherwise call `simulation.environment.workspace.get@1`, display it, and atomically publish the new generation;
5. on lease denial/expiry, clear that subject/workspace head and show the existing loading skeleton.

Local cache errors must be logged and ignored; they must not become a `provider_failed` UI state.

**Step 3: Verify and commit**

```powershell
node --test packages/sim-plugin/web/cad_sim/environment_store.test.js packages/sim-plugin/web/cad_sim/environment_workspace.test.js packages/sim-plugin/web/cad_sim/simulation_cache.test.js
git add packages/sim-plugin/web/cad_sim/environment_store.js packages/sim-plugin/web/cad_sim/environment_workspace.js packages/sim-plugin/web/cad_sim/environment_store.test.js packages/sim-plugin/web/cad_sim/environment_workspace.test.js
git commit -m "feat(simulation): validate cached workspaces with leases"
```

Expected: cached-first behavior passes without exposing stale/unauthorized nodes.

---

### Task 8: Cache bindings with node-level invalidation

**Files:**

- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/simulation_cache.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/environment_store.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/simulation_cache.test.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/bop_vm_binding_draft.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/bop_vm_binding_draft.test.js`

**Step 1: Write failing invalidation tests**

Test these exact cases:

- unrelated workspace mutation keeps a binding fresh;
- target workspace node `row_version` change stales only bindings for that node;
- VM node revision fingerprint change stales only bindings to that occurrence;
- changed VM document identity stales all bindings for that document;
- ambiguous identity is shown as review-required and never auto-applied.

**Step 2: Persist binding projections**

Each browser binding cache record contains:

```javascript
{
  bindingGid, workspaceGid, workspaceNodeGid, workspaceNodeRowVersion,
  vmDocumentIdentityHash, vmSnapshotGid, vmOccurrenceGid, vmNodeFingerprint,
  role, source, confidence, reviewState, cacheState
}
```

Do not use whole-workspace `row_version` as the sole invalidator. Server binding records remain authoritative; this task changes only projection reuse and UI status.

**Step 3: Verify and commit**

```powershell
node --test packages/sim-plugin/web/cad_sim/simulation_cache.test.js packages/sim-plugin/web/cad_sim/bop_vm_binding_draft.test.js packages/sim-plugin/web/cad_sim/environment_store.test.js
git add packages/sim-plugin/web/cad_sim/simulation_cache.js packages/sim-plugin/web/cad_sim/environment_store.js packages/sim-plugin/web/cad_sim/simulation_cache.test.js packages/sim-plugin/web/cad_sim/bop_vm_binding_draft.js packages/sim-plugin/web/cad_sim/bop_vm_binding_draft.test.js
git commit -m "feat(simulation): invalidate vm bindings at node scope"
```

---

### Task 9: Persist governed manual VM checkpoints

**Files:**

- Complete schema in: `backend/db/migrations/domains/simulation/0016_simulation_cache_snapshots_and_diffs.sql`
- Add: `plugins/simulation/simulation_backend/data/vm_checkpoint_repository.py`
- Add: `plugins/simulation/simulation_backend/capabilities/vm_checkpoints.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/__init__.py`
- Add: `plugins/simulation/tests/test_vm_checkpoint_capabilities.py`
- Add descriptors/catalog entries discovered by the Task 5 registry scan.

**Step 1: Write failing authorization and provenance tests**

Cover personal creation by a reader with a bound Connector, shared baseline creation only by workspace owner/project manager/super-admin, snapshot request ownership, completed status, exact hash re-read, idempotency, archive-only deletion, and tenant/owner isolation.

**Step 2: Add checkpoint persistence**

Add `workmanship_sim_vm_checkpoints` with:

```sql
gid BIGINT UNSIGNED PRIMARY KEY,
snapshot_gid BIGINT UNSIGNED NOT NULL,
workspace_gid BIGINT UNSIGNED NOT NULL,
created_by BIGINT UNSIGNED NOT NULL,
scope VARCHAR(32) NOT NULL,
name VARCHAR(255) NOT NULL,
note TEXT NULL,
row_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
archived_at DATETIME(6) NULL
```

Use `next_gid()`. Add a deterministic uniqueness/idempotency constraint compatible with OceanBase; do not hard-delete checkpoint rows.

**Step 3: Register capabilities after reuse scan**

- `simulation.vm_checkpoint.create@1`
- `simulation.vm_checkpoint.search@1`
- `simulation.vm_checkpoint.archive@1`

`create` accepts `snapshot_request_id`, exact `snapshot_hash`, `workspace_gid`, `scope`, `name`, optional `note`, and `idempotency_key`. Provider re-reads `simulation.document_snapshot.get@1` persistence, reuses/persists the immutable VM snapshot through `VmSnapshotRepository`, then creates the checkpoint in one service transaction boundary.

**Step 4: Verify and commit**

```powershell
python -m pytest plugins/simulation/tests/test_vm_checkpoint_capabilities.py plugins/simulation/tests/test_vm_snapshot_repository.py -q
python backend/scripts/build_capability_catalog.py --write
python backend/scripts/generate_capability_docs.py --write
git add backend/db/migrations/domains/simulation/0016_simulation_cache_snapshots_and_diffs.sql plugins/simulation/simulation_backend/data/vm_checkpoint_repository.py plugins/simulation/simulation_backend/capabilities/vm_checkpoints.py plugins/simulation/simulation_backend/capabilities/provider.py plugins/simulation/simulation_backend/capabilities/contracts.py plugins/simulation/simulation_backend/capabilities/__init__.py plugins/simulation/tests/test_vm_checkpoint_capabilities.py
git add docs/governance/capability-catalog-release.json docs/governance/capability-catalog-lineage.json docs/capabilities
git commit -m "feat(simulation): persist governed vm checkpoints"
```

---

### Task 10: Generate immutable node-level VM difference reports

**Files:**

- Modify: `plugins/simulation/simulation_backend/domain/vm_identity.py`
- Add: `plugins/simulation/simulation_backend/domain/vm_diff.py`
- Add: `plugins/simulation/simulation_backend/data/vm_diff_repository.py`
- Add: `plugins/simulation/simulation_backend/capabilities/vm_diffs.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/__init__.py`
- Add: `plugins/simulation/tests/test_vm_diff.py`
- Add: `plugins/simulation/tests/test_vm_diff_capabilities.py`
- Complete schema in: `backend/db/migrations/domains/simulation/0016_simulation_cache_snapshots_and_diffs.sql`

**Step 1: Write failing diff classification tests**

Create explicit fixtures for `added`, `removed`, `revision_upgraded`, `representation_replaced`, `geometry_content_changed`, `moved`, `reordered`, `renamed`, `attributes_changed`, and `ambiguous_identity`. Assert deterministic output order and identity ambiguity rather than guessing.

**Step 2: Implement pure comparison**

Expose:

```python
def compare_vm_snapshots(
    before: Iterable[VmObservation],
    after: Iterable[VmObservation],
    *,
    algorithm_version: str,
) -> VmDiff:
    return VmDiffBuilder(algorithm_version).compare(before, after)
```

Use occurrence lineage first, then stable external node identity and fingerprints. A node can emit multiple atomic diff items when different business properties changed. Include before/after parent, order, revision, representation, geometry hash, attributes, and affected binding GIDs where available.

**Step 3: Persist reports and items**

Add:

- `workmanship_sim_vm_diff_reports` keyed by snowflake GID, with unique `(before_snapshot_gid, after_snapshot_gid, algorithm_version)`;
- `workmanship_sim_vm_diff_items` keyed by snowflake GID with report GID, change type, occurrence references, severity, payload JSON, and stable sequence.

Generation is idempotent. Reports are immutable except archival/compaction metadata.

**Step 4: Register governed capabilities**

- `simulation.vm_diff_report.generate@1`
- `simulation.vm_diff_report.get@1`
- `simulation.vm_diff_item.search@1`

`generate` is idempotent write without external side effect; `get` and `search` are reads. Scope all resources to visible workspace/checkpoints and add `_RESOURCES` mappings.

**Step 5: Verify and commit**

```powershell
python -m pytest plugins/simulation/tests/test_vm_identity.py plugins/simulation/tests/test_vm_diff.py plugins/simulation/tests/test_vm_diff_capabilities.py -q
python backend/scripts/build_capability_catalog.py --write
python backend/scripts/generate_capability_docs.py --write
git add plugins/simulation/simulation_backend/domain/vm_identity.py plugins/simulation/simulation_backend/domain/vm_diff.py plugins/simulation/simulation_backend/data/vm_diff_repository.py plugins/simulation/simulation_backend/capabilities/vm_diffs.py plugins/simulation/simulation_backend/capabilities/provider.py plugins/simulation/simulation_backend/capabilities/contracts.py plugins/simulation/simulation_backend/capabilities/__init__.py plugins/simulation/tests/test_vm_diff.py plugins/simulation/tests/test_vm_diff_capabilities.py backend/db/migrations/domains/simulation/0016_simulation_cache_snapshots_and_diffs.sql
git add docs/governance/capability-catalog-release.json docs/governance/capability-catalog-lineage.json docs/capabilities
git commit -m "feat(simulation): report vm snapshot differences"
```

---

### Task 11: Add snapshot and comparison controls to the Simulation UI

**Files:**

- Add in frontend worktree: `packages/sim-plugin/web/cad_sim/vm_versioning.js`
- Add in frontend worktree: `packages/sim-plugin/web/cad_sim/vm_versioning.test.js`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/index.html`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/cad_sim.css`
- Modify in frontend worktree: `packages/sim-plugin/web/cad_sim/cad_sim.js`

**Step 1: Write failing UI-state tests**

Test:

- toolbar contains `创建快照`, `立即对比`, and `自动版本对比` switch;
- automatic preference is stored per authenticated user and workspace;
- switch off still performs freshness validation but creates no visible report;
- `立即对比` runs once and does not enable automatic mode;
- report pages at 200 items;
- status is conveyed by text/icon as well as color;
- report selection navigates and expands the changed tree node;
- failures are non-blocking and leave live COM controls usable.

**Step 2: Implement a small versioning controller**

Expose:

```javascript
createVmVersioningController({ invoke, cache, getAuthSubjectGid, clock })
  .createCheckpoint({ workspaceGid, scope, name, note })
  .compareNow({ beforeCheckpointGid, afterCheckpointGid })
  .setAutomaticComparison({ workspaceGid, enabled })
  .onFreshSnapshot(snapshotSummary)
  .loadReport(reportGid, cursor)
```

Reuse `capture_workflow.js` for snapshot request/action/dispatch/get. Do not duplicate confirmation logic. Auto mode may generate a report only after a fresh completed snapshot exists; it must not make Connector control operations wait.

**Step 3: Implement report panel**

Display summary counts, changed-node list, binding-impact groups, and before/after properties. Add JSON export and flat CSV export from already loaded report pages. Keep the report panel lazy-loaded and collapsible.

**Step 4: Verify and commit**

```powershell
node --test packages/sim-plugin/web/cad_sim/vm_versioning.test.js packages/sim-plugin/web/cad_sim/capture_workflow.test.js packages/sim-plugin/web/cad_sim/cad_sim_vm_tree.test.js packages/sim-plugin/web/cad_sim/cad_sim_visibility.test.js
git add packages/sim-plugin/web/cad_sim/vm_versioning.js packages/sim-plugin/web/cad_sim/vm_versioning.test.js packages/sim-plugin/web/cad_sim/index.html packages/sim-plugin/web/cad_sim/cad_sim.css packages/sim-plugin/web/cad_sim/cad_sim.js
git commit -m "feat(simulation): add vm snapshots and version comparisons"
```

---

### Task 12: Add server retention without deleting governed evidence

**Files:**

- Add: `plugins/simulation/simulation_backend/application/vm_retention.py`
- Modify: `plugins/simulation/simulation_backend/data/vm_snapshot_repository.py`
- Modify: `plugins/simulation/simulation_backend/data/vm_diff_repository.py`
- Add: `plugins/simulation/tests/test_vm_retention.py`

**Step 1: Write failing retention tests**

Assert:

- identical technical snapshots deduplicate by `(document_gid, snapshot_hash, algorithm_version)`;
- at most 20 unreferenced automatic snapshots per document and 30 days are retained;
- at most 100 automatic reports and 90 days are retained;
- old automatic reports compact to summary before unreferenced automatic snapshots are removed;
- manual personal checkpoints, shared baselines, audit evidence, release evidence, and referenced snapshots are never deleted;
- local browser clear never calls server retention APIs.

**Step 2: Implement bounded cleanup**

Create one idempotent application service callable after successful technical snapshot/report creation. Use small batches and explicit protected-reference joins. If a protected-only set exceeds limits, record metrics and stop deleting rather than violating evidence retention.

**Step 3: Verify and commit**

```powershell
python -m pytest plugins/simulation/tests/test_vm_retention.py plugins/simulation/tests/test_vm_snapshot_repository.py plugins/simulation/tests/test_vm_diff_capabilities.py -q
git add plugins/simulation/simulation_backend/application/vm_retention.py plugins/simulation/simulation_backend/data/vm_snapshot_repository.py plugins/simulation/simulation_backend/data/vm_diff_repository.py plugins/simulation/tests/test_vm_retention.py
git commit -m "feat(simulation): retain bounded vm cache evidence"
```

---

### Task 13: Complete governance artifacts and end-to-end verification

**Files:**

- Modify generated governance artifacts: `docs/governance/capability-catalog-release.json`, `docs/governance/capability-catalog-lineage.json`, `docs/capabilities/**`, and `docs/governance/capability-coverage-review/simulation.json`.
- Modify governed database artifacts: `backend/governance/table_inventory.json`, `backend/governance/domain_table_inventory.json`, `backend/governance/domain_table_ownership.json`, and `backend/governance/schema/{expected-schema.json,schema-source-map.json,schema-build-summary.json}`.
- Add: `plugins/simulation/tests/test_vm_cache_integration.py`
- Add in frontend worktree: `packages/sim-plugin/web/cad_sim/vm_cache_integration.test.js`
- Modify: `docs/superpowers/specs/2026-09-10-simulation-three-layer-cache-version-diff-design.md` only if implementation has an approved, evidence-backed deviation.

**Step 1: Run governance reuse and coverage checks**

```powershell
rg -n "simulation\.vm_checkpoint|simulation\.vm_diff|simulation\.environment\.workspace\.cache_lease" backend plugins docs
rg -n "workmanship_sim_vm_checkpoints|workmanship_sim_vm_diff_reports|workmanship_sim_vm_diff_items|cache_revision_hash" backend plugins docs
```

Verify every new public route/provider/consumer is bound to one stable candidate Capability, every table is in global inventory/schema projection, descriptions state actor/outcome/resource boundaries, and no direct database or direct loopback HTTP bypass was introduced.

**Step 2: Add two-layer integration tests**

Backend integration test must prove:

1. first tree read creates a generation;
2. reopen same unchanged project hits cache;
3. one node revision changes and only its ancestor chain refreshes;
4. manual checkpoint persists from an exact completed snapshot request;
5. one-shot comparison returns deterministic node-level changes;
6. workspace node mutation invalidates only its affected binding projection;
7. expired permission lease prevents cached display.

Frontend integration test must prove cached-first render, authoritative refresh, switch behavior, one-shot report, and non-interference with visibility/highlight commands.

**Step 3: Run proportional test suites**

Backend worktree:

```powershell
dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release -m:1
python -m pytest plugins/simulation/tests -q
```

Frontend worktree:

```powershell
$simulationTestFiles = Get-ChildItem packages/sim-plugin/web/cad_sim -Filter "*.test.js" | ForEach-Object FullName
node --test $simulationTestFiles
```

Then run the repository's existing Catalog, descriptor, schema/table-inventory, capability-document, and release-gate commands discovered from the current audit scripts. Do not substitute a hand-written partial scanner.

The concrete generation/check commands are:

```powershell
python backend/scripts/build_capability_catalog.py --write
python backend/scripts/generate_capability_docs.py --write
python backend/scripts/build_single_database_schema.py --write
python backend/scripts/build_capability_coverage_review.py --write
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_single_database_schema.py --check
$simulationWebRoot = Resolve-Path ..\orchestration-merge-frontend-20260905\web
python backend/scripts/check_capability_v2_release_gate.py --web-root $simulationWebRoot
```

Expected:

- Connector suite passes;
- Simulation backend suite passes;
- Simulation frontend suite passes;
- no new blocker/critical Finding for the added capabilities, consumers, or tables;
- static release gate passes;
- no visibility/highlight/open/close latency regression;
- cache performance evidence records local SQLite P95 below 100 ms and cached IndexedDB display below 300 ms on the test fixture.

**Step 4: Perform one real-runtime acceptance session**

With the user-approved local Connector and a non-production test database:

1. open a VisMockup project and load the VM tree;
2. close/reopen VisMockup and confirm same-project cache hit;
3. update one test model revision and confirm bounded invalidation plus visible change report;
4. create a personal manual snapshot;
5. turn automatic comparison off and confirm no automatic report appears;
6. click `立即对比` and confirm exactly one report appears without changing the switch;
7. confirm full show/hide and highlight remain responsive;
8. record Capability Gateway receipts, snapshot/report GIDs, timings, and screenshots as verification evidence.

Do not claim `runtime_verified` without this session. Do not claim `human_approved`; leave that for the super-admin governance workflow.

**Step 5: Commit integration evidence**

```powershell
git add plugins/simulation/tests/test_vm_cache_integration.py
git add docs/governance/capability-catalog-release.json docs/governance/capability-catalog-lineage.json docs/capabilities docs/governance/capability-coverage-review/simulation.json backend/governance/table_inventory.json backend/governance/domain_table_inventory.json backend/governance/domain_table_ownership.json backend/governance/schema
git commit -m "test(simulation): verify layered vm cache governance"
```

In the frontend worktree:

```powershell
git add packages/sim-plugin/web/cad_sim/vm_cache_integration.test.js
git commit -m "test(simulation): verify cached vm workflows"
```

---

## Spec-to-Task Traceability

| Specification concern | Implemented and verified by |
|---|---|
| Cross-restart VM cache correctness | Tasks 1–2, 13 |
| Node-level revision/fingerprint comparison | Tasks 1–2, 10, 13 |
| Connector cache size and eviction | Task 3 |
| Independent workspace projection cache | Tasks 4–7 |
| Short-lived authorization lease | Tasks 5–7, 13 |
| Independent binding cache and selective invalidation | Task 8 |
| Manual personal/shared checkpoints | Tasks 9, 11, 13 |
| Optional automatic and one-shot comparison | Tasks 10–11, 13 |
| Immutable version-difference reports and exports | Tasks 10–11 |
| Server snapshot/report retention | Task 12 |
| Snowflake GIDs for authoritative records | Tasks 4, 9–10 |
| Capability Gateway/Catalog governance | Tasks 5, 9–10, 13 |
| COM control latency isolation | Global constraints, Tasks 2, 11, 13 |
| BOP cache explicitly deferred | Global constraints |

## Final Acceptance Boundary

Implementation is complete only when all automated checks in Task 13 pass and the real-runtime acceptance session demonstrates both correctness and latency. Cache speed alone is not acceptance: stale model reuse, unauthorized cached display, guessed ambiguous identity, orphaned evidence, or any regression in direct VisMockup controls is a release blocker.
