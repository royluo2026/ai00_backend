# Simulation Model Documents and Alternate Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an AI00 simulation environment a durable, multi-document workspace whose editable alternate hierarchies can be materialized as VisMockup-compatible PLMXML, opened or inserted into VisMockup, read back, and verified without losing AI00-only analysis state.

**Architecture:** The Simulation database is the authoritative live draft and version store. Original PLMXML/JT files remain immutable Artifacts, while a deterministic codec projects the database model to a single top-level runtime PLMXML package. AI00 opens the first document and inserts later documents through governed Connector operations. A separate verification workflow reads the actual VisMockup document back and compares document, hierarchy, occurrence, and sampled scene state before marking a version runtime verified. Craft continues to own BOP; BOP Fork is a retryable cross-domain saga that creates a Simulation alternate-hierarchy skeleton without direct cross-domain table access.

**Tech Stack:** Python 3.11, FastAPI/Pydantic, MySQL/OceanBase-compatible SQL, Capability V2 Catalog/Providers, .NET 8 Connector, Win32 COM/IDispatch, Electron/Vite, browser-native JavaScript, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-10-simulation-model-documents-alternate-hierarchy-design.md`

## Global Constraints

- Preserve existing unrelated dirty changes. Before implementation, inventory and isolate overlapping edits in `VisMockupAdapter.cs`, `workspaces.py`, `workspace_repository.py`, `cad_sim.js`, `cad_sim.css`, and `index.html`; never reset or overwrite them.
- Resolve the two existing `0016_simulation_*.sql` migrations before adding this feature migration. The accepted baseline must contain unique, monotonically increasing migration numbers. This plan uses `0017` only after that prerequisite is true.
- Use snowflake GIDs through the repository's existing `next_gid()` path for all database identities. Do not introduce UUID primary keys.
- The database is authoritative for mutable environment drafts. PLMXML is an import/export/runtime artifact, not the live write store.
- Preserve original uploaded bytes as immutable Artifacts. Byte-for-byte export is promised only when returning an unedited original Artifact; edited environments promise semantic round-trip equivalence.
- Never persist local filesystem paths as portable business identity. Persist Artifact refs, hashes, portability class, display names, and source metadata. Device-bound paths remain Connector-local.
- Do not directly read or write Craft tables from Simulation. Cross-domain references are immutable GIDs/hashes resolved through governed Capabilities.
- Every local side effect uses a prepare/dispatch/outcome or equivalent idempotent two-phase workflow. Unknown outcomes remain reconcilable and are never silently retried.
- Parser limits remain fail-closed: bounded file size, node count, depth, text length, URI schemes, and external reference count; DTD/entity expansion stays disabled.
- Environment verification is a state machine (`draft`, `materializing`, `runtime_verified`, `runtime_drifted`, `unmaterializable`, `outcome_unknown`), not a boolean inferred from HTTP success. Materialization runs separately expose `prepared`, `dispatched`, `opened`, `read_back`, `verified`, and `failed` progress.
- Unit tests must use small committed fixtures. The 21 MB and 37 MB W10 files under `D:\Temp\vis\plmxml` are opt-in local integration inputs and must not be committed.
- Keep the implementation minimal: extend existing workspace, cache, Artifact, plan, and Connector abstractions; do not add another orchestration framework, XML library, or database.

---

### Task 0: Establish a safe implementation baseline

**Files:**
- Inspect: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Inspect: `plugins/simulation/simulation_backend/capabilities/workspaces.py`
- Inspect: `plugins/simulation/simulation_backend/data/workspace_repository.py`
- Inspect: `backend/db/migrations/domains/simulation/0016_simulation_cache_snapshots_and_diffs.sql`
- Inspect: `backend/db/migrations/domains/simulation/0016_simulation_workspace_fork_visibility.sql`
- Inspect in frontend worktree: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Inspect in frontend worktree: `packages/sim-plugin/web/cad_sim/cad_sim.css`
- Inspect in frontend worktree: `packages/sim-plugin/web/cad_sim/index.html`

**Interfaces:** No production interface changes. Produce a clean dependency baseline or an explicit patch inventory before feature edits.

- [ ] Record backend and frontend worktree status and overlapping diffs.

```powershell
Set-Location E:\Projects\ai00_v3\.worktrees\orchestration-merge-backend-20260905
git status --short
git diff -- local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs plugins/simulation/simulation_backend/capabilities/workspaces.py plugins/simulation/simulation_backend/data/workspace_repository.py backend/db/migrations/domains/simulation
Set-Location E:\Projects\ai00_v3\.worktrees\orchestration-merge-frontend-20260905
git status --short
git diff -- packages/sim-plugin/web/cad_sim/cad_sim.js packages/sim-plugin/web/cad_sim/cad_sim.css packages/sim-plugin/web/cad_sim/index.html
```

- [ ] Resolve migration numbering without changing deployed semantics: retain the already-applied `0016_simulation_cache_snapshots_and_diffs.sql`; rename the not-yet-baselined fork-visibility migration to the next free number if its deployment ledger confirms it has not run. If either file has run, add a new forward-only reconciliation migration instead of renaming history.
- [ ] Create isolated backend and frontend feature worktrees from the exact accepted local `test` commits, then reapply only the overlapping dependency commits required by this feature.
- [ ] Re-run the targeted existing baseline tests before new code.

```powershell
Set-Location E:\Projects\ai00_v3\.worktrees\orchestration-merge-backend-20260905
python -m pytest plugins/simulation/tests/test_plmxml_projection.py plugins/simulation/tests/test_workspace_capabilities.py -q
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "FullyQualifiedName~VisMockupDocumentLifecycleTests|FullyQualifiedName~VisMockupExportPlmxmlTests"
Set-Location E:\Projects\ai00_v3\.worktrees\orchestration-merge-frontend-20260905
node packages/sim-plugin/web/cad_sim/plmxml_tree_import.test.js
node packages/sim-plugin/web/cad_sim/environment_workspace.test.js
```

- [ ] Commit only the migration-numbering reconciliation if one was required.

```powershell
git add backend/db/migrations/domains/simulation
git commit -m "chore: disambiguate simulation migration sequence"
```

---

### Task 1: Prove and govern VisMockup document insertion

**Files:**
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs`
- Modify: `local-runtime/src/Ai00.Connector.Adapters.VisMockup/VisMockupAdapter.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/FakeVisMockupCom.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/VisMockupDocumentLifecycleTests.cs`
- Modify: `local-runtime/tests/Ai00.Connector.Tests/vismockup.adapter.json`
- Create: `local-runtime/tests/pilot/probe-vismockup-insert-document.ps1`

**Interfaces:**

```csharp
public interface IVisMockupDocument
{
    string InsertDocument(string path);
    IReadOnlyList<string> InsertedDocumentPaths { get; }
}
```

Adapter operation:

```json
{
  "operation_id": "vismockup.model.insert@1",
  "input": {"local_artifact_path": "C:\\staged\\resource.jt"},
  "output": {"document_id": "active-doc-1", "inserted_path": "C:\\staged\\resource.jt", "inserted_count": 1}
}
```

- [ ] Add failing fake-COM tests proving insertion targets the active document, preserves the existing document, returns the inserted path/count, rejects disallowed extensions, and is idempotent for the same staged path within one plan.
- [ ] Add a source-contract test proving the dynamic COM implementation invokes `IVisDispDoc.InsertDocument` with DISPID `1`, and reads `NumInsertedDocuments`/`InsertedDocumentPath(index)` using the TLB-confirmed DISPIDs `8` and `12`.
- [ ] Run the focused tests and confirm they fail for the missing operation.

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter FullyQualifiedName~VisMockupDocumentLifecycleTests
```

- [ ] Implement `DynamicDocument.InsertDocument` and inserted-document inspection through the existing `VisMockupDispatch` helper. Do not use `ActiveView.AddModel`, which has different VisMockup semantics.
- [ ] Add `vismockup.model.insert@1` to `VisMockupAdapter.Manifest` and `ExecuteAsync`; reuse `AllowedPathPolicy`, STA dispatch, connection fencing, and postcondition checks.
- [ ] Update the fake and checked-in adapter manifest.
- [ ] Run focused and complete Connector tests.

```powershell
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "FullyQualifiedName~VisMockupDocumentLifecycleTests|FullyQualifiedName~AdapterManifestTests|FullyQualifiedName~PlanRecoveryTests"
```

- [ ] With a disposable VisMockup session, run the pilot script against one small PLMXML as the primary document and one JT/PLMXML as the inserted document. Record product version, active document identity, inserted count/path, and whether the inserted occurrence is addressable. If the real COM call fails, stop this task and retain the failing HRESULT as evidence; do not substitute `AddModel`.
- [ ] Commit the Connector slice.

```powershell
git add local-runtime/src/Ai00.Connector.Adapters.VisMockup local-runtime/tests/Ai00.Connector.Tests local-runtime/tests/pilot/probe-vismockup-insert-document.ps1
git commit -m "feat(connector): add governed VisMockup document insertion"
```

---

### Task 2: Build the semantic PLMXML environment codec

**Files:**
- Create: `plugins/simulation/simulation_backend/domain/plmxml_environment_codec.py`
- Modify: `plugins/simulation/simulation_backend/domain/plmxml_projection.py`
- Modify: `plugins/simulation/simulation_backend/domain/environment_manifest.py`
- Create: `plugins/simulation/tests/fixtures/plmxml/environment_with_alt_hierarchy.plmxml`
- Create: `plugins/simulation/tests/fixtures/plmxml/environment_with_external_document.plmxml`
- Create: `plugins/simulation/tests/test_plmxml_environment_codec.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class EnvironmentModelDocument:
    document_gid: str
    role: Literal["primary", "inserted"]
    media_type: Literal["application/plmxml+xml", "model/vnd.jt"]
    artifact_ref: dict[str, str] | None
    source_identity_hash: str
    content_sha256: str
    portability: Literal["portable", "device_bound"]

@dataclass(frozen=True)
class AlternateHierarchyProjection:
    hierarchy_gid: str
    name: str
    root_placement_gid: str | None
    placements: Sequence["EnvironmentPlacementProjection"]

def import_environment_plmxml(stream: BinaryIO, *, limits: PlmxmlLimits,
                              algorithm_version: str) -> EnvironmentImportProjection:
    raise NotImplementedError

def export_environment_plmxml(model: EnvironmentRuntimeModel) -> EnvironmentExportResult:
    raise NotImplementedError
```

- [ ] Write failing tests for: populated `ProductView usage="variant"`; multiple alternate hierarchies; external PLMXML references; local JT references; stable occurrence identity; empty hierarchy represented in the database model even when absent from PLMXML; unknown XML extension preservation via the original Artifact; deterministic semantic output for identical input.
- [ ] Write security-limit tests for DTD/entity input, unsupported URI schemes, path traversal, excessive external references, excessive hierarchy depth, and excessive nodes.
- [ ] Run the new tests and confirm the codec is absent.

```powershell
python -m pytest plugins/simulation/tests/test_plmxml_environment_codec.py -q
```

- [ ] Implement the codec by extending the existing streaming parser. Normalize namespaces and relationship IDs only inside the semantic projection; never load the full production XML into an unbounded DOM.
- [ ] Export one top-level runtime PLMXML whose document references and alternate hierarchy placements resolve deterministically. Keep AI00-only notes, tasks, issues, and report bodies out of the PLMXML payload.
- [ ] Emit an export report containing `semantic_hash`, document count, hierarchy count, placement count, unresolved refs, omitted AI00-only records, and original-artifact passthrough eligibility.
- [ ] Add opt-in local integration assertions for the two files in `D:\Temp\vis\plmxml`; skip when absent. Assert the newer file imports at least one populated alternate hierarchy and both files stay within limits.
- [ ] Run codec and legacy projection tests.

```powershell
python -m pytest plugins/simulation/tests/test_plmxml_projection.py plugins/simulation/tests/test_plmxml_environment_codec.py -q
```

- [ ] Commit the codec slice.

```powershell
git add plugins/simulation/simulation_backend/domain/plmxml_environment_codec.py plugins/simulation/simulation_backend/domain/plmxml_projection.py plugins/simulation/simulation_backend/domain/environment_manifest.py plugins/simulation/tests/fixtures/plmxml/environment_with_alt_hierarchy.plmxml plugins/simulation/tests/fixtures/plmxml/environment_with_external_document.plmxml plugins/simulation/tests/test_plmxml_environment_codec.py
git commit -m "feat(simulation): add semantic PLMXML environment codec"
```

---

### Task 3: Persist model documents, alternate hierarchies, placements, and verification state

**Files:**
- Create: `backend/db/migrations/domains/simulation/0017_simulation_environment_documents_and_hierarchies.sql`
- Modify: `plugins/simulation/simulation_backend/data/workspace_repository.py`
- Create: `plugins/simulation/tests/test_environment_document_repository.py`
- Create: `plugins/simulation/tests/test_environment_hierarchy_repository.py`
- Modify: `plugins/simulation/tests/test_workspace_cache_revision.py`

**Schema:**

```sql
ALTER TABLE workmanship_sim_vm_documents
  ADD COLUMN document_role VARCHAR(16) NOT NULL DEFAULT 'inserted',
  ADD COLUMN primary_slot TINYINT UNSIGNED NULL,
  ADD COLUMN display_name VARCHAR(255) NOT NULL DEFAULT '',
  ADD COLUMN media_type VARCHAR(96) NOT NULL DEFAULT 'application/plmxml+xml',
  ADD COLUMN artifact_gid BIGINT UNSIGNED NULL,
  ADD COLUMN content_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT '',
  ADD COLUMN portability VARCHAR(16) NOT NULL DEFAULT 'portable',
  ADD COLUMN sort_order INT UNSIGNED NOT NULL DEFAULT 0,
  ADD UNIQUE KEY uq_sim_vm_document_primary (workspace_gid, primary_slot);

ALTER TABLE workmanship_sim_workspace_nodes
  ADD COLUMN hierarchy_gid BIGINT UNSIGNED NULL,
  ADD KEY idx_sim_workspace_node_hierarchy (workspace_gid, hierarchy_gid, parent_gid, removed_at);

CREATE TABLE workmanship_sim_workspace_hierarchies (
  gid BIGINT UNSIGNED NOT NULL,
  workspace_gid BIGINT UNSIGNED NOT NULL,
  tenant_gid BIGINT UNSIGNED NOT NULL,
  owner_gid BIGINT UNSIGNED NOT NULL,
  name VARCHAR(255) NOT NULL,
  source_bop_repository_gid BIGINT UNSIGNED NULL,
  source_bop_version_gid BIGINT UNSIGNED NULL,
  source_bop_fork_run_gid BIGINT UNSIGNED NULL,
  source_bop_content_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  projection_identity VARCHAR(191) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  sort_order INT UNSIGNED NOT NULL DEFAULT 0,
  row_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  removed_at DATETIME(6) NULL,
  PRIMARY KEY (gid),
  KEY idx_sim_alt_hierarchy_workspace (tenant_gid, workspace_gid, removed_at, sort_order),
  CONSTRAINT fk_sim_alt_hierarchy_workspace FOREIGN KEY (workspace_gid)
    REFERENCES workmanship_sim_workspaces (gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE workmanship_sim_workspace_placements (
  gid BIGINT UNSIGNED NOT NULL,
  hierarchy_gid BIGINT UNSIGNED NOT NULL,
  workspace_gid BIGINT UNSIGNED NOT NULL,
  tenant_gid BIGINT UNSIGNED NOT NULL,
  owner_gid BIGINT UNSIGNED NOT NULL,
  target_node_gid BIGINT UNSIGNED NOT NULL,
  parent_placement_gid BIGINT UNSIGNED NULL,
  source_kind VARCHAR(32) NOT NULL,
  source_ref_json JSON NOT NULL,
  transform_json JSON NOT NULL,
  display_name VARCHAR(255) NOT NULL,
  sort_order INT UNSIGNED NOT NULL DEFAULT 0,
  row_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  removed_at DATETIME(6) NULL,
  PRIMARY KEY (gid),
  KEY idx_sim_placement_hierarchy (tenant_gid, hierarchy_gid, removed_at, sort_order),
  KEY idx_sim_placement_workspace (tenant_gid, workspace_gid, removed_at),
  CONSTRAINT fk_sim_placement_hierarchy FOREIGN KEY (hierarchy_gid)
    REFERENCES workmanship_sim_workspace_hierarchies (gid),
  CONSTRAINT fk_sim_placement_workspace FOREIGN KEY (workspace_gid)
    REFERENCES workmanship_sim_workspaces (gid),
  CONSTRAINT fk_sim_placement_target_node FOREIGN KEY (target_node_gid)
    REFERENCES workmanship_sim_workspace_nodes (gid),
  CONSTRAINT fk_sim_placement_parent FOREIGN KEY (parent_placement_gid)
    REFERENCES workmanship_sim_workspace_placements (gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE workmanship_sim_vm_session_documents (
  gid BIGINT UNSIGNED NOT NULL,
  session_gid BIGINT UNSIGNED NOT NULL,
  document_gid BIGINT UNSIGNED NOT NULL,
  tenant_gid BIGINT UNSIGNED NOT NULL,
  owner_gid BIGINT UNSIGNED NOT NULL,
  document_role VARCHAR(16) NOT NULL,
  inserted_index INT UNSIGNED NULL,
  actual_identity_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  actual_content_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  sync_state VARCHAR(32) NOT NULL,
  row_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (gid),
  UNIQUE KEY uq_sim_session_document (session_gid, document_gid),
  UNIQUE KEY uq_sim_session_inserted_index (session_gid, inserted_index),
  CONSTRAINT fk_sim_session_document_session FOREIGN KEY (session_gid)
    REFERENCES workmanship_sim_vm_sessions (gid),
  CONSTRAINT fk_sim_session_document_document FOREIGN KEY (document_gid)
    REFERENCES workmanship_sim_vm_documents (gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE workmanship_sim_materialization_verifications (
  gid BIGINT UNSIGNED NOT NULL,
  workspace_gid BIGINT UNSIGNED NOT NULL,
  version_gid BIGINT UNSIGNED NOT NULL,
  tenant_gid BIGINT UNSIGNED NOT NULL,
  actor_gid BIGINT UNSIGNED NOT NULL,
  state VARCHAR(24) NOT NULL,
  manifest_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  runtime_package_artifact_gid BIGINT UNSIGNED NULL,
  connector_device_gid BIGINT UNSIGNED NULL,
  report_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (gid),
  UNIQUE KEY uq_sim_verification_version_manifest (tenant_gid, version_gid, manifest_hash),
  KEY idx_sim_verification_workspace (tenant_gid, workspace_gid, state, updated_at),
  CONSTRAINT fk_sim_verification_workspace FOREIGN KEY (workspace_gid)
    REFERENCES workmanship_sim_workspaces (gid),
  CONSTRAINT fk_sim_verification_version FOREIGN KEY (version_gid)
    REFERENCES workmanship_sim_workspace_versions (gid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Set `primary_slot=1` only for the active primary document and `NULL` for every inserted document, so MySQL/OceanBase enforces at most one primary without blocking multiple inserted rows. Repository creation must require one primary before materialization. Add the hierarchy foreign key on `workmanship_sim_workspace_nodes.hierarchy_gid` only after backfilling existing active nodes into a deterministic default hierarchy; then make it non-null in a later forward migration if the deployed data proves safe.

The full migration must use existing table prefix/collation conventions, BIGINT snowflake GIDs, tenant/workspace indexes, soft-delete columns where existing workspace records use them, and foreign keys only within the Simulation domain.

**Repository interfaces:**

```python
def add_model_document(*, workspace_gid: str, expected_workspace_version: int,
                       document: EnvironmentModelDocument, actor_gid: str,
                       tenant_gid: str) -> dict[str, Any]:
    raise NotImplementedError
def create_alternate_hierarchy(*, workspace_gid: str, name: str,
                               source_bop_version_gid: str | None,
                               expected_workspace_version: int, actor_gid: str,
                               tenant_gid: str) -> dict[str, Any]:
    raise NotImplementedError
def add_placement(*, hierarchy_gid: str, parent_placement_gid: str | None,
                  source_kind: str, source_ref: dict[str, str],
                  transform: list[float], expected_hierarchy_version: int,
                  actor_gid: str, tenant_gid: str) -> dict[str, Any]:
    raise NotImplementedError
def save_materialization_verification(*, workspace_gid: str, version_gid: str,
                                      state: str, manifest_hash: str,
                                      report: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError
```

- [ ] Write migration/repository tests for multiple documents, exactly one primary document, empty alternate hierarchies, placement ordering, same source placed more than once, soft removal, tenant/user visibility, stale row-version conflict, and rollback on partial failure.
- [ ] Verify tests fail before the migration/repository methods exist.
- [ ] Implement migration and repository methods using existing transaction helpers and `next_gid()`.
- [ ] Extend workspace revision hashing so document/hierarchy/placement changes invalidate the environment revision and materialization, while pure UI expansion state does not.
- [ ] Run repository and workspace tests.

```powershell
python -m pytest plugins/simulation/tests/test_environment_document_repository.py plugins/simulation/tests/test_environment_hierarchy_repository.py plugins/simulation/tests/test_workspace_cache_revision.py -q
```

- [ ] Commit the persistence slice.

```powershell
git add backend/db/migrations/domains/simulation/0017_simulation_environment_documents_and_hierarchies.sql plugins/simulation/simulation_backend/data/workspace_repository.py plugins/simulation/tests/test_environment_document_repository.py plugins/simulation/tests/test_environment_hierarchy_repository.py plugins/simulation/tests/test_workspace_cache_revision.py
git commit -m "feat(simulation): persist environment documents and hierarchies"
```

---

### Task 4: Publish atomic Simulation Capabilities

**Files:**
- Create: `plugins/simulation/simulation_backend/capabilities/environment_documents.py`
- Create: `plugins/simulation/simulation_backend/capabilities/alternate_hierarchies.py`
- Create: `plugins/simulation/simulation_backend/capabilities/plmxml_environments.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/__init__.py`
- Create: `plugins/simulation/tests/test_environment_document_capabilities.py`
- Create: `plugins/simulation/tests/test_alternate_hierarchy_capabilities.py`
- Create: `plugins/simulation/tests/test_plmxml_environment_capabilities.py`

**Capability set:**

```text
simulation.environment.model_document.search@1
simulation.environment.model_document.add@1
simulation.environment.model_document.remove@1
simulation.environment.alternate_hierarchy.search@1
simulation.environment.alternate_hierarchy.get@1
simulation.environment.alternate_hierarchy.create@1
simulation.environment.alternate_hierarchy.update@1
simulation.environment.alternate_hierarchy.archive@1
simulation.environment.placement.create@1
simulation.environment.placement.move@1
simulation.environment.placement.remove@1
simulation.environment.bop_fork_workflow.get@1
simulation.plmxml.environment.import@1
simulation.plmxml.environment.export@1
simulation.vismockup.model.insert.request@1
```

- [ ] Add failing provider tests for exact input/output schemas, resource selectors, authorization, confirmation on destructive removal, idempotency, optimistic concurrency, portability validation, Artifact media/hash verification, and domain error codes.
- [ ] Assert import and export are separate atomic Capabilities under one Simulation-owned Provider, not one mode-switched endpoint.
- [ ] Implement Pydantic schemas and thin handlers that call the codec/repository; handlers must not contain direct XML or SQL logic.
- [ ] Import must create/update a draft through one transaction and return projection/report refs. Export must return an immutable Artifact ref and semantic report, not inline multi-megabyte XML.
- [ ] Register descriptors, business definitions, invariants, side-effect level, automation level, lifecycle, evidence, and audit metadata in `provider.py`.
- [ ] Run focused provider tests.

```powershell
python -m pytest plugins/simulation/tests/test_environment_document_capabilities.py plugins/simulation/tests/test_alternate_hierarchy_capabilities.py plugins/simulation/tests/test_plmxml_environment_capabilities.py plugins/simulation/tests/test_domain_completion.py -q
```

- [ ] Commit the Capability slice without generated Catalog files yet.

```powershell
git add plugins/simulation/simulation_backend/capabilities/environment_documents.py plugins/simulation/simulation_backend/capabilities/alternate_hierarchies.py plugins/simulation/simulation_backend/capabilities/plmxml_environments.py plugins/simulation/simulation_backend/capabilities/contracts.py plugins/simulation/simulation_backend/capabilities/provider.py plugins/simulation/simulation_backend/capabilities/__init__.py plugins/simulation/tests/test_environment_document_capabilities.py plugins/simulation/tests/test_alternate_hierarchy_capabilities.py plugins/simulation/tests/test_plmxml_environment_capabilities.py
git commit -m "feat(simulation): expose environment document and hierarchy capabilities"
```

---

### Task 5: Turn BOP Fork into a recoverable alternate-hierarchy bootstrap saga

**Files:**
- Modify: `plugins/simulation/simulation_backend/capabilities/workspaces.py`
- Modify: `plugins/simulation/simulation_backend/data/workspace_repository.py`
- Modify: `plugins/simulation/tests/test_workspace_capabilities.py`
- Modify: `plugins/simulation/tests/test_workspace_freeze_saga.py`
- Modify as needed, without reading Simulation tables: `plugins/craft/craft_backend/capabilities/bop_repository_fork.py`
- Modify: `plugins/craft/tests/test_bop_repository_fork.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class BopForkReference:
    source_repository_gid: str
    source_version_gid: str
    source_content_hash: str
    fork_operation_gid: str

def bootstrap_from_bop_fork(*, workspace_gid: str, fork_ref: BopForkReference,
                            hierarchy_name: str, idempotency_key: str,
                            expected_workspace_version: int,
                            context: CapabilityContext) -> CapabilityOutput:
    raise NotImplementedError
```

- [ ] Add tests proving Craft Fork completes once, returns immutable source refs, and can be retried independently from Simulation hierarchy creation.
- [ ] Add tests proving a retry after Simulation failure does not create a second Craft fork or a second hierarchy, and a different payload with the same idempotency key conflicts.
- [ ] Build the alternate-hierarchy skeleton from the governed Craft BOP snapshot projection. Store Craft node GIDs as external refs only; do not query Craft tables.
- [ ] Mark the workspace `bootstrap_pending` until both steps complete; expose a repair action for a completed Craft fork with missing Simulation hierarchy.
- [ ] Run Craft and Simulation saga tests.

```powershell
python -m pytest plugins/craft/tests/test_bop_repository_fork.py plugins/simulation/tests/test_workspace_capabilities.py plugins/simulation/tests/test_workspace_freeze_saga.py -q
```

- [ ] Commit the cross-domain workflow slice.

```powershell
git add plugins/simulation/simulation_backend/capabilities/workspaces.py plugins/simulation/simulation_backend/data/workspace_repository.py plugins/simulation/tests/test_workspace_capabilities.py plugins/simulation/tests/test_workspace_freeze_saga.py plugins/craft/craft_backend/capabilities/bop_repository_fork.py plugins/craft/tests/test_bop_repository_fork.py
git commit -m "feat(simulation): bootstrap alternate hierarchy from BOP fork"
```

---

### Task 6: Materialize one runtime package and verify mutual recognition

**Files:**
- Create: `plugins/simulation/simulation_backend/application/environment_materialization.py`
- Create: `plugins/simulation/simulation_backend/application/environment_verification.py`
- Modify: `plugins/simulation/simulation_backend/application/connector_plans.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/environment_composition.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/connector_contracts.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/provider.py`
- Create: `plugins/simulation/tests/test_environment_materialization.py`
- Create: `plugins/simulation/tests/test_environment_verification.py`
- Modify: `plugins/simulation/tests/test_workspace_freeze_saga.py`

**Interfaces:**

```python
def build_runtime_package(workspace_version: dict[str, Any]) -> RuntimePackage:
    """Return top-level PLMXML Artifact, dependency Artifacts, manifest and semantic hash."""
    raise NotImplementedError

def compare_runtime_readback(expected: RuntimeManifest,
                             actual: ConnectorDocumentSnapshot,
                             sampled_scene: list[SceneProbe]) -> VerificationReport:
    raise NotImplementedError
```

Verified runtime-package replay order:

```text
artifact.stage(top-level PLMXML and every dependency)
-> verify every staged hash and package-relative reference
-> vismockup.model.open@1(top-level PLMXML only)
vismockup.tree.read@1 -> sampled visibility/selection probes -> outcome apply
```

- [ ] Write failing tests for deterministic package generation, exactly one top-level PLMXML, dependency ordering, portable vs device-bound preflight, stale source hash, missing dependency, plan idempotency, unknown local outcome, and compensation boundaries.
- [ ] Write verification tests for exact document set, hierarchy names, occurrence identity, placement count, expected source hashes, and sampled show/hide/select behavior. A failed sample must produce `failed`; a lost Connector response after possible side effect must produce `outcome_unknown`.
- [ ] Implement package construction using the codec and Artifact service. The root PLMXML references dependencies by package-relative controlled names.
- [ ] Extend frozen-version composition plans to stage the complete package, verify every hash, open only the top-level PLMXML, and then execute readback/probe steps. Do not reinsert dependencies already referenced by that top-level document, and do not dispatch from the prepare Capability.
- [ ] Persist every state transition and immutable report through the repository added in Task 3.
- [ ] Freeze/publish must reject drafts that are not `verified`, except for an explicit policy-approved device-bound mode that records the device and content hashes.
- [ ] Run materialization, Connector plan, freeze, and verification tests.

```powershell
python -m pytest plugins/simulation/tests/test_environment_materialization.py plugins/simulation/tests/test_environment_verification.py plugins/simulation/tests/test_workspace_freeze_saga.py plugins/simulation/tests/test_workspace_version_export.py -q
```

- [ ] Commit the runtime round-trip slice.

```powershell
git add plugins/simulation/simulation_backend/application/environment_materialization.py plugins/simulation/simulation_backend/application/environment_verification.py plugins/simulation/simulation_backend/application/connector_plans.py plugins/simulation/simulation_backend/capabilities/environment_composition.py plugins/simulation/simulation_backend/capabilities/connector_contracts.py plugins/simulation/simulation_backend/capabilities/provider.py plugins/simulation/tests/test_environment_materialization.py plugins/simulation/tests/test_environment_verification.py plugins/simulation/tests/test_workspace_freeze_saga.py
git commit -m "feat(simulation): materialize and verify VisMockup runtime packages"
```

---

### Task 7: Replace the single-file VM tree with a multi-document source collection

**Files in frontend worktree:**
- Modify: `packages/sim-plugin/web/cad_sim/index.html`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.css`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify: `packages/sim-plugin/web/cad_sim/plmxml_tree_import.js`
- Create: `packages/sim-plugin/web/cad_sim/model_document_collection.js`
- Create: `packages/sim-plugin/web/cad_sim/model_document_collection.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/plmxml_tree_import.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim_vm_tree.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/environment_workspace.js`
- Modify: `packages/sim-plugin/web/cad_sim/environment_workspace.test.js`

**UI state:**

```js
{
  documents: [{ documentGid, role, displayName, mediaType, portability, syncState }],
  selectedDocumentGid: null,
  hierarchies: [{ hierarchyGid, name, placementCount, expanded }],
  runtimeState: "draft",
  verificationSummary: null
}
```

- [ ] Add failing UI tests for adding several PLMXML/JT documents, exactly one primary badge, document-local tree identity, empty alternate hierarchy visibility, deterministic ordering, removal confirmation, and collapsed large document groups.
- [ ] Add failing interaction tests for dragging a VM occurrence or resource onto a BOP-derived alternate-hierarchy node. Assert the command creates a placement ref and does not duplicate source bytes or mutate the source tree.
- [ ] Add progress-state tests for `staging`, `opening`, `inserting`, `reading back`, `verified`, `failed`, and `outcome unknown`, plus environment-state tests for `draft`, `materializing`, `runtime_verified`, `runtime_drifted`, and `unmaterializable`; never collapse these to `provider_failed` without the domain code/report link.
- [ ] Implement the collection model and render it inside the existing Product/Resource panel. Accept `.plmxml`, `.xml`, and `.jt`; use governed Artifact/local-file selection paths already exposed by the app.
- [ ] Replace the old single `_openPlmxmlTree` state mutation with Capability-backed add/search/remove operations. Keep the lightweight browser parser only for pre-upload preview; the server projection is authoritative after import.
- [ ] Render alternate hierarchies as editable workspace trees and source documents as read-only trees. Preserve current panel typography/folding conventions.
- [ ] Run focused UI tests.

```powershell
node packages/sim-plugin/web/cad_sim/model_document_collection.test.js
node packages/sim-plugin/web/cad_sim/plmxml_tree_import.test.js
node packages/sim-plugin/web/cad_sim/cad_sim_vm_tree.test.js
node packages/sim-plugin/web/cad_sim/environment_workspace.test.js
```

- [ ] Commit the frontend slice.

```powershell
git add packages/sim-plugin/web/cad_sim/index.html packages/sim-plugin/web/cad_sim/cad_sim.css packages/sim-plugin/web/cad_sim/cad_sim.js packages/sim-plugin/web/cad_sim/plmxml_tree_import.js packages/sim-plugin/web/cad_sim/model_document_collection.js packages/sim-plugin/web/cad_sim/model_document_collection.test.js packages/sim-plugin/web/cad_sim/plmxml_tree_import.test.js packages/sim-plugin/web/cad_sim/cad_sim_vm_tree.test.js packages/sim-plugin/web/cad_sim/environment_workspace.js packages/sim-plugin/web/cad_sim/environment_workspace.test.js
git commit -m "feat(simulation-ui): support multi-document environment composition"
```

---

### Task 8: Wire real VisMockup synchronization into the UI workflow

**Files in frontend worktree:**
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.js`
- Modify: `packages/sim-plugin/web/cad_sim/capture_workflow.js`
- Modify: `packages/sim-plugin/web/cad_sim/capture_workflow.test.js`
- Modify: `packages/sim-plugin/web/cad_sim/connector_onboarding.js`
- Modify: `packages/sim-plugin/web/cad_sim/connector_onboarding.test.js`
- Modify: `packages/sim-plugin/electron/handlers.js`
- Modify only if the existing handler boundary requires it: `packages/sim-plugin/electron/vismockup_controller.js`
- Modify: `scripts/test_simulation_p0_boundary.js`

**Interfaces:** The browser invokes only business Capabilities. Electron transports governed local-file tokens and Connector status; it does not call COM directly.

- [ ] Add failing tests proving live draft synchronization opens the first document and inserts each subsequent document, while frozen-version replay opens only its generated top-level PLMXML. Reordered UI items must not silently mutate an already verified runtime, and reconnect must reconcile actual inserted documents before retry.
- [ ] Add tests proving a local JT selection becomes a short-lived local file token, not a raw browser path in Capability payload or persisted workspace state.
- [ ] Wire add-document completion to materialization prepare, user-confirmed dispatch, status polling/push, and readback verification. Show progress in the stable status bar without layout jumps or repeated modal prompts.
- [ ] Keep the existing direct scene controls on the Connector fast path; environment persistence and verification must not add an HTTP round trip to every show/hide/highlight command.
- [ ] Run Simulation UI boundary and Electron boundary tests.

```powershell
npm run test:simulation-p0-boundary
npm run test:electron-security
node packages/sim-plugin/web/cad_sim/capture_workflow.test.js
node packages/sim-plugin/web/cad_sim/connector_onboarding.test.js
```

- [ ] Commit the synchronization slice.

```powershell
git add packages/sim-plugin/web/cad_sim/cad_sim.js packages/sim-plugin/web/cad_sim/capture_workflow.js packages/sim-plugin/web/cad_sim/capture_workflow.test.js packages/sim-plugin/web/cad_sim/connector_onboarding.js packages/sim-plugin/web/cad_sim/connector_onboarding.test.js packages/sim-plugin/electron/handlers.js packages/sim-plugin/electron/vismockup_controller.js scripts/test_simulation_p0_boundary.js
git commit -m "feat(simulation-ui): synchronize environment documents with VisMockup"
```

---

### Task 9: Regenerate governance artifacts and run acceptance

**Files:**
- Modify generated: `backend/capability_v2/official_domains.json`
- Modify generated: `docs/governance/capability-catalog-release.json`
- Modify generated: `docs/governance/capability-catalog-lineage.json`
- Modify generated: `docs/capabilities/`
- Create: `docs/governance/changes/2026-09-10-simulation-environment-round-trip.md`
- Create: `docs/governance/reports/2026-09-10-simulation-environment-round-trip-readiness.md`

- [ ] Write the governance change proposal from the accepted spec: business purpose, atomicity, owner, consumers, schemas, authorization, confirmation, idempotency, consistency, transaction boundary, errors, evidence, lifecycle, rollout, rollback, and human approval state.
- [ ] Freeze Provider artifacts, build Catalog/lineage, and generate docs.

```powershell
Set-Location E:\Projects\ai00_v3\.worktrees\orchestration-merge-backend-20260905
python backend/scripts/freeze_official_domains.py
python backend/scripts/build_capability_catalog.py --write
python backend/scripts/generate_capability_docs.py --write
```

- [ ] Verify generated artifacts are deterministic and governance checks pass.

```powershell
python backend/scripts/freeze_official_domains.py --check
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/audit_capability_business_rules.py
python backend/scripts/run_capability_governance_scan.py
```

- [ ] Run the targeted backend and Connector suite; do not claim full-system regression from this subset.

```powershell
python -m pytest plugins/simulation/tests plugins/craft/tests/test_bop_repository_fork.py -q
dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter "FullyQualifiedName~VisMockup|FullyQualifiedName~PlanRecoveryTests|FullyQualifiedName~AdapterManifestTests"
```

- [ ] Run the frontend Simulation suite and production build.

```powershell
Set-Location E:\Projects\ai00_v3\.worktrees\orchestration-merge-frontend-20260905
npm run test:simulation-p0-boundary
npm run test:electron-security
npm run build:web
```

- [ ] Run one real end-to-end pilot with VisMockup: import the newer W10 PLMXML, add one JT or second PLMXML, create a BOP-derived alternate hierarchy, place one product and one resource, materialize, open/insert, read back, show/hide/select samples, close/reopen, and verify the same semantic manifest. Save timing and verification evidence without committing proprietary model files.
- [ ] Confirm failure recovery by interrupting one insert dispatch and reconciling to either `verified`, `failed`, or `outcome_unknown`; no duplicate insert is allowed.
- [ ] Record exact test commands/results, Catalog release/hash, Connector/VisMockup versions, device-bound limitations, and remaining human approval in the readiness report.
- [ ] Commit generated governance artifacts and evidence separately.

```powershell
git add backend/capability_v2/official_domains.json docs/governance/capability-catalog-release.json docs/governance/capability-catalog-lineage.json docs/capabilities docs/governance/changes/2026-09-10-simulation-environment-round-trip.md docs/governance/reports/2026-09-10-simulation-environment-round-trip-readiness.md
git commit -m "docs(governance): publish simulation round-trip capability evidence"
```

---

## Final Review Checklist

- [ ] Compare every delivered behavior against the accepted spec section by section; list any intentional deferral explicitly in the readiness report.
- [ ] Search changed files for `TODO`, `TBD`, `FIXME`, sentinel hashes, fake success states, raw local paths, UUID primary keys, direct Craft-table SQL from Simulation, and UI calls that bypass Capability V2.
- [ ] Confirm empty alternate hierarchies survive database save/load even though VisMockup may omit them from exported PLMXML.
- [ ] Confirm one environment can hold multiple source documents while every runtime package has exactly one top-level PLMXML entry document.
- [ ] Confirm original Artifact passthrough and edited semantic export are distinct, visible outcomes.
- [ ] Confirm `device_bound` and `portable` sources produce different, policy-correct share/freeze behavior.
- [ ] Confirm direct VisMockup show/hide/highlight latency remains on the local Connector path and is not serialized through environment persistence.
- [ ] Confirm real COM insertion used `InsertDocument` and the active document's inserted-document list matched readback; do not approve based only on fake tests.
- [ ] Confirm Catalog descriptors, runtime Provider binding, generated docs, consumer calls, database migrations, and tests all refer to the same Capability IDs and versions.
- [ ] Run `git diff --check` in both worktrees and inspect the exact staged diff before each final commit.
- [ ] Request code review before merging backend and frontend feature branches into local `test`; merge only after overlapping dirty work is reconciled and targeted acceptance is green.
