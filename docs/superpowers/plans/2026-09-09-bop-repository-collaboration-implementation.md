# BOP Repository Collaboration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one Craft-owned BOP Repository per authoritative project, with team and managed personal spaces, immutable versions, governed Fork/Diff/VPPS/proposal workflows, private Simulation import, and the desktop workbench integration.

**Architecture:** Craft owns Repository identity, logical BOP node/binding identities, space heads, immutable versions, Fork, VPPS and proposals. Simulation owns unlimited private environments and signs immutable version export references for Craft imports. All new Capability definitions remain candidate/experimental and outside the product release until the later trusted approval; the desktop consumes them only in an isolated development catalog.

**Tech Stack:** Python 3.12, FastAPI Capability V2 providers, PyMySQL/OceanBase-compatible SQL, pytest, Electron renderer JavaScript, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-09-simulation-environment-collaboration-versioning-design.md` and `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md`

## Global Constraints

- Windows x64 is the only desktop target; the backend remains deployable in the cloud.
- Use snowflake `next_gid()` for persisted GIDs; do not introduce UUID identity.
- Project identity and authorization come from Project Management; Knowledge UI only supplies the project selection surface.
- One active Repository per project, one team space per Repository, and one managed personal space per user per Repository; private Simulation environments remain unlimited.
- Do not modify executed migrations, especially Simulation `0011_simulation_workspaces.sql`; add Craft `0010` and Simulation `0012` or later.
- Do not cross domain tables directly. Craft consumes Simulation, Project, Knowledge, Digital Model and Artifact data through governed Capability/Gateway contracts.
- New or changed Capabilities remain `machine_passed=unverified`, `human_approved=unverified`, `runtime_verified=unverified`, `advisory=true` until real evidence changes each state.
- Renderer actions that the user explicitly initiated use `confirmation=none`; authorization and invariants remain server-side.
- Every write uses trusted InvocationContext identity, expected version/CAS, stable operation GID, idempotency key and audit evidence.
- Large trees and Diffs use bounded pagination, `max_depth`, `max_nodes` and stable ordering.

---

### Task 1: Authoritative Capability Inventory and Change Record

**Files:**
- Create: `docs/governance/changes/2026-09-09-bop-repository-collaboration.md`
- Modify: `backend/governance/domain_table_ownership.json`
- Test: `backend/tests/test_bop_repository_governance_inventory.py`

**Interfaces:**
- Consumes: current Craft/Simulation Capability registries, provider registrations, migration inventory and Catalog release projections.
- Produces: an advisory inventory with exact reuse decisions, candidate IDs, owner paths, affected consumers and independent governance states.

- [ ] **Step 1: Write the failing inventory test**

```python
def test_change_record_lists_every_candidate_without_claiming_approval():
    text = CHANGE_RECORD.read_text(encoding="utf-8")
    assert "craft.bop.repository.create@1" in text
    assert "simulation.environment.workspace_version.export_for_import@1" in text
    assert "human_approved: unverified" in text
    assert "runtime_verified: unverified" in text
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest backend/tests/test_bop_repository_governance_inventory.py -q`

Expected: FAIL because the change record does not exist.

- [ ] **Step 3: Inspect and record authoritative context**

Run read-only searches over `plugins/craft/craft_backend/capabilities`, `plugins/simulation/simulation_backend/capabilities`, `backend/governance`, current migrations, API consumers and frontend invocations. Record each candidate using the governance proposal template, and classify legacy `craft.bop.fork.change.apply@1` as non-reusable for Repository semantics because it lacks target project uniqueness, Preview/Apply portability, workflow and immutable space versions.

- [ ] **Step 4: Add Craft ownership declarations**

Add every `workmanship_craft_bop_*` table from Task 2 to `domain_table_ownership.json` with domain `craft`; do not add Simulation tables to Craft.

- [ ] **Step 5: Run the inventory and ownership tests**

Run: `python -m pytest backend/tests/test_bop_repository_governance_inventory.py backend/tests/test_domain_table_ownership.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/governance/changes/2026-09-09-bop-repository-collaboration.md backend/governance/domain_table_ownership.json backend/tests/test_bop_repository_governance_inventory.py
git commit -m "docs(governance): inventory bop repository capabilities"
```

### Task 2: Craft Repository and Space Persistence Foundation

**Files:**
- Create: `backend/db/migrations/domains/craft/0010_bop_repositories.sql`
- Create: `backend/tests/test_bop_repository_migration.py`
- Modify: `backend/governance/domain_table_inventory.json`

**Interfaces:**
- Consumes: snowflake decimal GIDs and existing Craft migration runner.
- Produces: Repository, space, head, immutable space version, logical node/binding, revision, membership, idempotency and audit tables.

- [ ] **Step 1: Write failing schema assertions**

```python
def test_repository_schema_has_space_scoped_revision_membership():
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in REQUIRED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in sql
    assert "UNIQUE KEY `uq_craft_bop_project_slot` (`tenant_gid`,`project_gid`,`active_slot`)" in sql
    assert "`space_gid` CHAR(36) NOT NULL" in sql
    assert "`is_tombstone` TINYINT(1) NOT NULL DEFAULT 0" in sql
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest backend/tests/test_bop_repository_migration.py -q`

Expected: FAIL because migration `0010` does not exist.

- [ ] **Step 3: Implement OceanBase-compatible additive DDL**

Create the tables named in spec section 12. Use generated active-slot keys for nullable tombstone uniqueness, non-null `parent_scope_gid` for VPPS ordering, unique `(space_head_gid,member_kind,logical_gid)`, and append-only version memberships. Put `frozen_version_gid` on spaces and `baseline_version_gid` on repositories.

- [ ] **Step 4: Verify schema and ownership**

Run: `python -m pytest backend/tests/test_bop_repository_migration.py backend/tests/test_domain_migration_runner.py backend/tests/test_domain_table_ownership.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/migrations/domains/craft/0010_bop_repositories.sql backend/tests/test_bop_repository_migration.py backend/governance/domain_table_inventory.json
git commit -m "feat(craft): add bop repository persistence"
```

### Task 3: Repository Data Port and Identity Rules

**Files:**
- Create: `plugins/craft/craft_backend/data/bop_repository.py`
- Create: `plugins/craft/tests/test_bop_repository_data.py`

**Interfaces:**
- Produces: `BopRepositoryStore.create_repository(...)`, `get_repository(...)`, `search_repositories(...)`, `save_space_version(...)`, `freeze_team_space(...)`, and `set_baseline(...)`.
- Returns: dictionaries with decimal string GIDs, `row_version`, immutable manifest hash and audit operation GID.

- [ ] **Step 1: Write failing behavior tests**

```python
def test_create_repository_is_idempotent_and_enforces_project_slot(store):
    first = store.create_repository(project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="r-1")
    assert store.create_repository(project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="r-1") == first
    with pytest.raises(BopRepositoryError, match="target_repository_exists"):
        store.create_repository(project_gid="10", tenant_gid="20", actor_gid="30", idempotency_key="r-2")
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest plugins/craft/tests/test_bop_repository_data.py -q`

Expected: FAIL because the store is absent.

- [ ] **Step 3: Implement minimal transaction methods**

Use `plugins.craft.craft_backend.data.connection.get_craft_conn`, `next_gid()`, row locks and payload hashes. Persist logical node identity separately from revision membership. Reject baseline versions whose resolved space is not the same Repository team space.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest plugins/craft/tests/test_bop_repository_data.py -q`

Expected: PASS, including idempotency conflict, CAS failure, cross-space baseline rejection and space tombstone isolation.

- [ ] **Step 5: Commit**

```bash
git add plugins/craft/craft_backend/data/bop_repository.py plugins/craft/tests/test_bop_repository_data.py
git commit -m "feat(craft): persist repository and space identities"
```

### Task 4: Repository Foundation Capability Candidates

**Files:**
- Create: `plugins/craft/craft_backend/capabilities/bop_repositories.py`
- Modify: `plugins/craft/craft_backend/capabilities/__init__.py`
- Modify: `plugins/craft/craft_backend/capabilities/provider.py`
- Test: `plugins/craft/tests/test_bop_repository_capabilities.py`

**Interfaces:**
- Produces candidate handlers for `repository.search/get/create`, `space.search/get`, `space_version.search/get/save/freeze`, `repository_baseline.set`, archive/restore/delete and managed personal delete.
- Consumes the Task 3 store and trusted `CapabilityContext`.

- [ ] **Step 1: Write failing closed-contract tests**

```python
def test_repository_candidates_are_closed_and_not_stable():
    items = candidate_specs(StubStore())
    assert {s.id for s, _ in items} >= {"craft.bop.repository.create", "craft.bop.space_version.freeze"}
    assert all(s.input_schema["additionalProperties"] is False for s, _ in items)
    assert all(descriptor_for(s).lifecycle_status.value == "experimental" for s, _ in items)
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest plugins/craft/tests/test_bop_repository_capabilities.py -q`

Expected: FAIL because candidate specs are absent.

- [ ] **Step 3: Implement providers and descriptors**

Use one method per business effect, stable error mapping, resource selectors, bounded search and `confirmation=none` for explicit desktop writes. Register as experimental candidates; do not add them to a stable product release or claim approval.

- [ ] **Step 4: Run GREEN and registration boundaries**

Run: `python -m pytest plugins/craft/tests/test_bop_repository_capabilities.py backend/tests/test_capability_provider_loading.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/craft/craft_backend/capabilities/bop_repositories.py plugins/craft/craft_backend/capabilities/__init__.py plugins/craft/craft_backend/capabilities/provider.py plugins/craft/tests/test_bop_repository_capabilities.py
git commit -m "feat(craft): expose repository foundation candidates"
```

### Task 5: Immutable Private Simulation Version Export

**Files:**
- Create: `backend/db/migrations/domains/simulation/0012_simulation_contexts.sql`
- Modify: `plugins/simulation/simulation_backend/data/workspace_repository.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/workspaces.py`
- Test: `plugins/simulation/tests/test_workspace_version_export.py`
- Test: `backend/tests/test_simulation_context_migration.py`

**Interfaces:**
- Produces: `workspace_version.get` and `workspace_version.export_for_import` candidate handlers.
- Export token claims: caller actor, tenant, target personal/repository, consumer ID/major, source workspace/version, content hash and expiry.

- [ ] **Step 1: Write failing immutable-export tests**

```python
def test_export_ref_is_bound_to_caller_target_consumer_and_hash(provider):
    out = provider.export_for_import(PAYLOAD, context("30", "20")).data
    claims = verify_export_ref(out["export_ref"])
    assert claims["actor_gid"] == "30"
    assert claims["target_personal_space_gid"] == "501"
    assert claims["consumer"] == "craft.bop.managed_personal_space.import.preview@1"
    assert claims["content_hash"] == out["content_hash"]
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest plugins/simulation/tests/test_workspace_version_export.py backend/tests/test_simulation_context_migration.py -q`

Expected: FAIL because export and migration are absent.

- [ ] **Step 3: Implement signed scoped exports**

Only saved immutable versions can be exported. Store token digest, scope and expiry in Simulation; return an opaque reference rather than the private manifest. Reject drifting head, wrong owner, wrong target, consumer mismatch and expiry.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest plugins/simulation/tests/test_workspace_version_export.py backend/tests/test_simulation_context_migration.py plugins/simulation/tests/test_workspace_capabilities.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/migrations/domains/simulation/0012_simulation_contexts.sql plugins/simulation/simulation_backend/data/workspace_repository.py plugins/simulation/simulation_backend/capabilities/workspaces.py plugins/simulation/tests/test_workspace_version_export.py backend/tests/test_simulation_context_migration.py
git commit -m "feat(simulation): export immutable private versions"
```

### Task 6: Two-Stage Fork and Managed Personal Workflow

**Files:**
- Create: `plugins/craft/craft_backend/data/bop_fork.py`
- Create: `plugins/craft/craft_backend/capabilities/bop_repository_fork.py`
- Test: `plugins/craft/tests/test_bop_repository_fork.py`

**Interfaces:**
- Produces repository and personal `fork.preview/apply`, `fork_run.get` and `fork_workflow.get`.
- Preview output fixes `preview_gid`, `workflow_gid`, input/plan hash, expiry, owner verdicts and allowed decisions.

- [ ] **Step 1: Write failing Preview/Apply tests**

```python
def test_apply_rejects_renderer_verdict_and_expired_preview(provider):
    preview = provider.preview(SOURCE, context()).data
    with pytest.raises(CapabilityBusinessError, match="fork_plan_changed"):
        provider.apply({**APPLY, "preview_gid": preview["preview_gid"], "owner_verdict": "copy"}, context())
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest plugins/craft/tests/test_bop_repository_fork.py -q`

Expected: FAIL because Fork providers are absent.

- [ ] **Step 3: Implement Preview/Apply and workflow recovery**

Provider creates a workflow when personal Preview omits it; supplied workflow must resolve to the fixed personal child. Apply revalidates authorization, owner verdicts, plan hash, expiry and target slot before creating the Repository. Use stable child idempotency keys so personal retry never repeats team Fork.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest plugins/craft/tests/test_bop_repository_fork.py -q`

Expected: PASS for all five depths, cross-project GID derivation, partial workflow recovery and target collision.

- [ ] **Step 5: Commit**

```bash
git add plugins/craft/craft_backend/data/bop_fork.py plugins/craft/craft_backend/capabilities/bop_repository_fork.py plugins/craft/tests/test_bop_repository_fork.py
git commit -m "feat(craft): add governed repository fork workflow"
```

### Task 7: Ordered VPPS Groups and Versioned Adjustments

**Files:**
- Create: `plugins/craft/craft_backend/data/bop_vpps_groups.py`
- Create: `plugins/craft/craft_backend/capabilities/bop_vpps_groups.py`
- Test: `plugins/craft/tests/test_bop_vpps_groups.py`

**Interfaces:**
- Produces ordered reference/generated_initial/adjustment versions and current-pointer CAS.
- Uses `(group_version_gid,parent_scope_gid,order_key)` uniqueness and `(target_group_gid,reference_version_gid,matcher_policy_hash)` operation identity.

- [ ] **Step 1: Write failing group invariants**

```python
def test_root_members_use_non_null_scope_and_repeat_vpps(store):
    version = store.create_adjustment(group_gid="10", members=MEMBERS_WITH_DUPLICATE_VPPS, expected_current=None)
    assert all(member["parent_scope_gid"] for member in version["members"])
    assert [m["vpps_gid"] for m in version["members"]].count("900") == 2
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest plugins/craft/tests/test_bop_vpps_groups.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement immutable groups and candidate capabilities**

Preserve reference versions, append generated/adjustment versions, inherit hierarchy/order during matching, and require project manager acceptance before team current advances.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest plugins/craft/tests/test_bop_vpps_groups.py -q`

Expected: PASS, including duplicate VPPS members, concurrent CAS, stable rebalance hash and cross-target generation isolation.

- [ ] **Step 5: Commit**

```bash
git add plugins/craft/craft_backend/data/bop_vpps_groups.py plugins/craft/craft_backend/capabilities/bop_vpps_groups.py plugins/craft/tests/test_bop_vpps_groups.py
git commit -m "feat(craft): version ordered vpps groups"
```

### Task 8: Diff, Private Import and Change Proposals

**Files:**
- Create: `plugins/craft/craft_backend/data/bop_collaboration.py`
- Create: `plugins/craft/craft_backend/capabilities/bop_collaboration.py`
- Test: `plugins/craft/tests/test_bop_collaboration.py`

**Interfaces:**
- Produces repository Diff, personal sync Preview/Apply, private import Preview/Apply and proposal create/submit/review/apply/cancel/withdraw/supersede.
- Consumes Simulation opaque export verification through a Gateway port, never a Simulation table.

- [ ] **Step 1: Write failing trust and state-machine tests**

```python
def test_partially_applied_is_not_terminal_and_accepted_cannot_withdraw(service):
    proposal = service.apply_component(ACCEPTED_PROPOSAL, component_gid="c1")
    assert proposal["apply_status"] == "partially_applied"
    assert proposal["is_terminal"] is False
    with pytest.raises(ProposalError, match="proposal_not_withdrawable"):
        service.withdraw(proposal["proposal_gid"])
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest plugins/craft/tests/test_bop_collaboration.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement server-resolved three-way inputs**

Resolve Base/Ours/Theirs from the personal space record, build explicit dependency components, apply one component per Craft transaction and preserve outcomes. Verify every private export claim against caller, tenant, target, consumer, hash and expiry before Preview and again before Apply.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest plugins/craft/tests/test_bop_collaboration.py -q`

Expected: PASS for legal state pairs, terminal predicate, component atomicity, stale team head and export replay rejection.

- [ ] **Step 5: Commit**

```bash
git add plugins/craft/craft_backend/data/bop_collaboration.py plugins/craft/craft_backend/capabilities/bop_collaboration.py plugins/craft/tests/test_bop_collaboration.py
git commit -m "feat(craft): add bop diff import and proposals"
```

### Task 9: Maintenance Fence and Legacy Backfill

**Files:**
- Create: `backend/db/migrations/domains/craft/0011_bop_repository_backfill_control.sql`
- Create: `scripts/migrate_bop_repositories.py`
- Create: `backend/tests/test_bop_repository_backfill.py`

**Interfaces:**
- Produces preliminary snapshot, atomic fence activation token, lease drain, final high-water, delta replay, reconciliation report and cutover readiness result.

- [ ] **Step 1: Write failing race tests**

```python
def test_writes_between_preliminary_watermark_and_fence_are_replayed(harness):
    preliminary = harness.preliminary()
    outcome = harness.legacy_write_after(preliminary)
    harness.activate_fence_and_drain()
    result = harness.backfill()
    assert outcome.operation_gid in result.migrated_operation_gids
    assert result.lost_write_count == 0
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest backend/tests/test_bop_repository_backfill.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement resumable backfill and dry-run default**

The script defaults to report-only. Mutation mode requires an explicit environment switch, installs the guard, atomically records fence activation, drains old leases, records final high-water, replays `(preliminary, final]`, and emits count/hash/quarantine evidence. It never enables the production cutover or approval itself.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest backend/tests/test_bop_repository_backfill.py backend/tests/test_domain_migration_runner.py -q`

Expected: PASS for both race injections, retries, interruption recovery and zero lost writes.

- [ ] **Step 5: Commit**

```bash
git add backend/db/migrations/domains/craft/0011_bop_repository_backfill_control.sql scripts/migrate_bop_repositories.py backend/tests/test_bop_repository_backfill.py
git commit -m "feat(craft): add fenced bop repository backfill"
```

### Task 10: Incremental VM Snapshot, Binding Migration and Reverse Capture

**Files:**
- Modify: `plugins/simulation/simulation_backend/domain/plmxml_projection.py`
- Modify: `plugins/simulation/simulation_backend/data/vm_snapshot_repository.py`
- Modify: `plugins/simulation/simulation_backend/application/document_snapshots.py`
- Modify: `plugins/simulation/simulation_backend/domain/process_capture_plan.py`
- Test: `plugins/simulation/tests/test_plmxml_projection.py`
- Test: `plugins/simulation/tests/test_vm_snapshot_repository.py`
- Test: `backend/tests/test_simulation_process_capture_plan.py`

**Interfaces:**
- Produces immutable, incrementally updated VM snapshots keyed by document/window and observed-at sequence.
- Identity consumes BOM line number/revision, `catiaOccurrenceName`, parent occurrence path and normalized transform; bindings retain Teamcenter/Digital Model references without changing them.

- [ ] **Step 1: Write failing identity and capture tests**

```python
def test_part_pose_change_is_observation_not_new_instance(projector):
    first = projector.project(PART_AT_HOME)
    moved = projector.project(PART_MOVED_BY_SIMULATION, previous=first)
    assert moved.instances[0].gid == first.instances[0].gid
    assert moved.instances[0].movement_state == "moved"

def test_reverse_capture_hides_future_parts_and_accumulates_completed_parts():
    plan = build_process_capture_plan(PROCESS_WITH_THREE_ORDERED_LOADS)
    assert plan.steps[0].visible_occurrences == ("part-1", "part-2", "part-3")
    assert plan.steps[-1].visible_occurrences == ("part-1",)
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest plugins/simulation/tests/test_plmxml_projection.py plugins/simulation/tests/test_vm_snapshot_repository.py backend/tests/test_simulation_process_capture_plan.py -q`

Expected: FAIL on instance classification or reverse visibility semantics.

- [ ] **Step 3: Implement incremental document/window snapshots**

Compare each new PLMXML export to the latest immutable snapshot for the same VisMockup document/window. Reuse a part instance only when BOM identity plus reference pose matches, record later pose as movement, and allocate distinct instance GIDs for repeated tools/equipment/fixtures/sockets even when model numbers match. Preserve source links and BOM revision fields verbatim as refs.

- [ ] **Step 4: Implement one-image-per-process capture plans**

Traverse selected BOP process/operation order in reverse. At each step hide parts loaded by later steps, retain all earlier accumulated parts, apply temporary color/visibility through the existing Connector plan, capture one image for the process, then restore the saved scene.

- [ ] **Step 5: Run GREEN**

Run: `python -m pytest plugins/simulation/tests/test_plmxml_projection.py plugins/simulation/tests/test_vm_snapshot_repository.py backend/tests/test_simulation_document_snapshot_workflow.py backend/tests/test_simulation_process_capture_plan.py backend/tests/test_simulation_capture_workflow.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add plugins/simulation/simulation_backend/domain/plmxml_projection.py plugins/simulation/simulation_backend/data/vm_snapshot_repository.py plugins/simulation/simulation_backend/application/document_snapshots.py plugins/simulation/simulation_backend/domain/process_capture_plan.py plugins/simulation/tests/test_plmxml_projection.py plugins/simulation/tests/test_vm_snapshot_repository.py backend/tests/test_simulation_process_capture_plan.py
git commit -m "feat(simulation): version vm snapshots and reverse capture"
```

### Task 11: Desktop Repository and Simulation Workspace UI

**Files (frontend worktree):**
- Modify: `packages/sim-plugin/web/cad_sim/index.html`
- Modify: `packages/sim-plugin/web/cad_sim/cad_sim.css`
- Modify: `packages/sim-plugin/web/cad_sim/environment_records.js`
- Modify: `packages/sim-plugin/web/cad_sim/environment_store.js`
- Modify: `packages/sim-plugin/web/cad_sim/environment_workspace.js`
- Test: `packages/sim-plugin/web/cad_sim/environment_store.test.js`
- Test: `packages/sim-plugin/web/cad_sim/environment_workspace.test.js`

**Interfaces:**
- Consumes development-catalog Craft Repository/space/Fork/Diff/proposal candidates and existing Simulation private workspace candidates through `business_facade`.
- Produces project/space selector, current environment tree, VM tree and reserved right pane with grouped state, Fork and Diff actions.

- [ ] **Step 1: Write failing UI state tests**

```javascript
test('groups team personal and unlimited private environments without losing selection', async () => {
  const state = await store.load();
  assert.deepEqual(state.groups.map(g => g.kind), ['team', 'managed_personal', 'private']);
  store.applyServerUpdate(nextPayload);
  assert.equal(store.viewpoint.selectedNodeGid, selectedNodeGid);
});
```

- [ ] **Step 2: Run RED**

Run: `node --test packages/sim-plugin/web/cad_sim/environment_store.test.js packages/sim-plugin/web/cad_sim/environment_workspace.test.js`

Expected: FAIL.

- [ ] **Step 3: Implement the four-column state and dialogs**

Render project/space records in the first column, current BOP/Simulation tree in the second, VisMockup structure in the third and the reserved pane in the fourth. Selecting either tree invokes governed VisMockup highlight. Dragging a VM part/tool/equipment/fixture/socket to a BOP station/process/operation writes only a binding to the immutable source link. Persist selection/scroll/zoom before mutations and restore after targeted state patches. Never full-reload after add, delete, move, save, Fork or proposal action.

- [ ] **Step 4: Run GREEN and layout smoke**

Run: `node --test packages/sim-plugin/web/cad_sim/*.test.js && node scripts/test_simulation_workspace_layout.js`

Expected: PASS.

- [ ] **Step 5: Commit in frontend repository**

```bash
git add packages/sim-plugin/web/cad_sim
git commit -m "feat(simulation): add bop repository collaboration workspace"
```

### Task 12: Agent Repository Assistant

**Files:**
- Create: `plugins/agent/agent_backend/orchestration/bop_repository_assistant.py`
- Modify: `plugins/agent/agent_backend/orchestration/provider.py`
- Test: `plugins/agent/tests/test_bop_repository_assistant.py`

**Interfaces:**
- Produces Task Tool `task.bop_repository_assistant` with fixed `craft_repository` and `simulation_private_environment` profiles.
- Consumes only exact candidate Capability ID/major from an explicitly pinned development Catalog and owner delegation.

- [ ] **Step 1: Write failing routing tests**

```python
def test_team_profile_never_advances_current_or_accepts_proposal(tool):
    with pytest.raises(TaskToolError, match="operation_not_allowed"):
        tool.run({"profile": "craft_repository", "task_kind": "proposal_accept", **CONTEXT})
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest plugins/agent/tests/test_bop_repository_assistant.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement fixed profile routing**

Validate delegation scope, Catalog release, expiry and allowed Capability IDs. Return bounded outcome references and summaries; do not return full PLMXML/BOP trees or embed business rules in the Tool.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest plugins/agent/tests/test_bop_repository_assistant.py backend/tests/test_agent_tool_catalog_boundary.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/agent/agent_backend/orchestration/bop_repository_assistant.py plugins/agent/agent_backend/orchestration/provider.py plugins/agent/tests/test_bop_repository_assistant.py
git commit -m "feat(agent): orchestrate bop repository workflows"
```

### Task 13: Integrated Verification and Release-Readiness Report

**Files:**
- Create: `docs/governance/reports/2026-09-09-bop-repository-collaboration-readiness.md`
- Modify: `docs/superpowers/plans/2026-09-09-bop-repository-collaboration-implementation.md`

**Interfaces:**
- Consumes all backend/frontend commits and real test output.
- Produces a report with exact passed/failed/skipped checks and separate machine/human/runtime states; it does not approve or publish the release.

- [ ] **Step 1: Run backend focused suites**

Run: `python -m pytest backend/tests/test_bop_repository_*.py plugins/craft/tests/test_bop_repository_*.py plugins/craft/tests/test_bop_vpps_groups.py plugins/craft/tests/test_bop_collaboration.py plugins/simulation/tests/test_workspace_version_export.py plugins/agent/tests/test_bop_repository_assistant.py -q`

- [ ] **Step 2: Run governance boundaries**

Run: `python -m pytest backend/tests/test_domain_table_ownership.py backend/tests/test_domain_migration_runner.py backend/tests/test_capability_provider_loading.py backend/tests/test_capability_v2_completion.py -q`

- [ ] **Step 3: Run frontend suites and build**

Run in frontend worktree: `node --test packages/sim-plugin/web/cad_sim/*.test.js && npm run build:test`

- [ ] **Step 4: Record evidence honestly**

Write commands, raw outcomes, revision hashes and unavailable identifiers. Keep `human_approved` and `runtime_verified` unverified until trusted workflows provide them; do not add candidates to a stable release.

- [ ] **Step 5: Commit**

```bash
git add docs/governance/reports/2026-09-09-bop-repository-collaboration-readiness.md docs/superpowers/plans/2026-09-09-bop-repository-collaboration-implementation.md
git commit -m "docs(governance): report bop collaboration readiness"
```

