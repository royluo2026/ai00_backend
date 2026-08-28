# Base Final Blocker Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five load-bearing Base blockers left by the first plan's single final-fix/re-review cycle without widening Capability scope.

**Architecture:** Preserve already-applied migration bytes and add forward-only repair migrations; align the saved-view public contract to the approved 1..200 bound and eliminate hidden local fallback behavior; produce deployable evidence exclusively from immutable tracked frontend commit contents. Each task adds a mutation-resistant regression test before implementation.

**Tech Stack:** Python 3.12, MySQL/OceanBase migrations, Capability V2 builders, vanilla JavaScript/Electron, Node.js, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-structural-owner-services-design.md`

## Global Constraints

- Binding findings: `.superpowers/sdd/2026-08-28-base-structural-owner-services/final-fix-rereview.md`.
- Do not modify or renumber historical migration bytes already present at backend commit `242f329f`.
- Do not derive evidence from untracked files or a dirty frontend worktree and label it with `git rev-parse HEAD`.
- Do not restore silent localStorage success paths, arbitrary URL plugin installation, destructive Electron uninstall, BFF, or operations exclusions.
- Preserve Base 16/16 groups and 33/33 occurrences; canonical non-Base remaining stays source-derived rather than forced to 26/29.
- Backend worktree: `E:/Projects/ai00_v3/.worktrees/capability-v2-implementation`.
- Frontend worktree: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance`.

---

### Task 1: Forward-only migration checksum and tenant repair

**Files:**
- Restore: `backend/db/migrations/202608280004_base_plugin_lifecycle_idempotency_scope.sql` to its exact `242f329f` bytes
- Create: `backend/db/migrations/202608280006_base_historical_tenant_repair.sql`
- Modify: `backend/tests/test_versioned_migrations.py`
- Modify: `backend/tests/test_base_structural_owner_hardening_migration.py`

**Interfaces:**
- Consumes: migration runner checksum ledger, `workmanship_auth_users.team_id`, saved-view/annotation aggregate tenant values.
- Produces: an upgrade path from both pre-0004 and already-applied-0004 databases without checksum mismatch; historical replay/audit rows inherit aggregate/user team tenant when determinable and become explicit unreachable legacy rows otherwise.

- [ ] **Step 1: Add failing upgrade-chain tests**

Create fixtures for: database with the original `242f329f` checksum for 0004; database before 0004; team-owned saved-view and annotation aggregates with historical replay/audit rows; user-without-team rows. Assert the runner accepts the unchanged 0004 checksum and applies 0005/0006 once; team rows receive `team_id`; user-only rows receive `user:<actor_gid>`; ambiguous rows receive a reserved `legacy-unresolved:<row-id>` scope that cannot match a live request.

- [ ] **Step 2: Run red tests**

Run: `python -m pytest -q -p no:cacheprovider backend/tests/test_versioned_migrations.py backend/tests/test_base_structural_owner_hardening_migration.py`

Expected: failure because 0004 differs from the recorded historical bytes and 0005 assigns `user:<actor>` without aggregate/team reconciliation.

- [ ] **Step 3: Restore history and add forward repair**

Restore 0004 exactly from `242f329f`. Keep 0005 immutable at its current committed bytes; put all corrections in 0006. Use joins from replay/audit rows to saved-view/annotation aggregates and `workmanship_auth_users` to derive the trusted tenant. Use metadata-preflighted, replay-safe DDL/DML and an explicit migration marker so repeated execution is a no-op.

- [ ] **Step 4: Run migration and ownership gates**

Run the two focused modules, the full migration/ownership suite named in the predecessor report, and `git diff --check`.

Expected: all pass; a mutation to 0004 bytes or a `CONCAT('user:', actor_gid)`-only backfill makes a regression test fail.

- [ ] **Step 5: Commit**

```bash
git add backend/db/migrations/202608280004_base_plugin_lifecycle_idempotency_scope.sql backend/db/migrations/202608280006_base_historical_tenant_repair.sql backend/tests/test_versioned_migrations.py backend/tests/test_base_structural_owner_hardening_migration.py
git commit -m "fix: preserve Base migration upgrade chain"
```

### Task 2: Exact saved-view bound and fail-visible storage behavior

**Files:**
- Modify: `backend/base/saved_views.py`
- Modify: `backend/capability_v2/atomic_web_contracts.py`
- Modify: `backend/tests/test_base_saved_view_service.py`
- Modify: `backend/tests/test_base_structural_web_capabilities.py`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/components/view_manager.js`
- Modify: frontend saved-view migration/behavior tests

**Interfaces:**
- Consumes: approved conjunction-only saved-view grammar and Capability Gateway client.
- Produces: `page_size` and search `limit` constrained to `1..200` in service, JSON Schema, REST, Gateway, and UI; `_lsKey()` cannot provide a silent persistence fallback.

- [ ] **Step 1: Add failing boundary and fallback tests**

Assert 200 succeeds and 201 fails for config `page_size` and search `limit` through service and Capability schema. In frontend tests, remove/disable Gateway and assert create/update/copy/delete reject visibly without writing or deleting any localStorage view; assert `_lsKey()` is absent or used only for explicitly named non-persistent UI preferences, never saved-view records.

- [ ] **Step 2: Run red tests**

Run focused Python modules and the frontend saved-view behavior/migration tests.

Expected: backend accepts 201..500 and source still contains the historical `_lsKey()` storage implementation.

- [ ] **Step 3: Implement the exact bound and remove dormant fallback**

Change every saved-view page/search maximum and default to 200. Remove the saved-view localStorage key, read/write/delete helpers, and dormant branches; keep UI state in memory only until a governed response succeeds. Errors remain visible to the caller.

- [ ] **Step 4: Run focused backend/frontend and syntax checks**

Run the red commands again plus `node --check web/components/view_manager.js` and the official frontend build.

Expected: all pass and a source scan finds no saved-view `_lsKey()` or local persistence fallback.

- [ ] **Step 5: Commit frontend and backend separately**

```bash
git add backend/base/saved_views.py backend/capability_v2/atomic_web_contracts.py backend/tests/test_base_saved_view_service.py backend/tests/test_base_structural_web_capabilities.py
git commit -m "fix: enforce bounded saved view contract"

git -C E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance add web/components/view_manager.js
git -C E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance commit -m "fix: remove saved view local fallback"
```

### Task 3: Immutable deployable evidence and closure verification

**Files:**
- Modify: deployable-surface scanner and its tests in the exact paths introduced by `a7bf669f`
- Modify: Base/Web evidence builders that consume frontend revision and source roots
- Regenerate: checked-in deployable, Base remediation, route inventory, ledger, structural plan, Catalog/docs, and acceptance artifacts
- Test: `backend/tests/test_base_structural_remediation_manifest.py`
- Test: `backend/tests/test_capability_v2_route_inventory.py`

**Interfaces:**
- Consumes: a clean frontend commit and `git ls-tree`/`git show` immutable file bytes for `web`, `packages/core/electron`, and `dist-production`.
- Produces: evidence whose file list, hashes, content hash, and frontend revision all derive from the same immutable commit; dirty/untracked deployable files make generation fail rather than enter evidence.

- [ ] **Step 1: Add failing immutable-source tests**

Create a temporary git fixture with tracked deployable files plus an untracked generated file. Assert scanning `HEAD` reads only `HEAD` blobs and produces the same result with or without the untracked file. Assert worktree mode refuses dirty tracked deployable roots. Assert the real report file count equals the count obtained from the pinned commit using the same extension/root rules.

- [ ] **Step 2: Run red evidence tests**

Run the deployable scanner tests and Base/route source-derived evidence tests.

Expected: failure because the current scanner walks disk bytes and labels them with HEAD.

- [ ] **Step 3: Implement commit-bound scanning**

Read the immutable tree via git object commands or an equivalent repository abstraction. Store scan mode `commit`, full frontend SHA, exact roots/extensions/exclusions, tracked blob IDs/content hashes, file count, finding identities, and report content hash. Never mix `Path.rglob()` worktree bytes with a commit revision.

- [ ] **Step 4: Commit frontend build, then regenerate all evidence**

Run the official frontend build, add intended production artifacts, commit them, and verify tracked status is clean. Regenerate evidence against that exact frontend commit, then freeze providers and regenerate Catalog/docs/acceptance in dependency order.

- [ ] **Step 5: Run final verification**

Run:

```text
python -m pytest -q -p no:cacheprovider backend/tests/test_base_saved_view_service.py backend/tests/test_base_self_annotation_service.py backend/tests/test_base_identity_profile_service.py backend/tests/test_plugin_platform_service.py backend/tests/test_base_structural_remediation_manifest.py backend/tests/test_capability_v2_route_inventory.py backend/tests/test_structural_remediation_plan.py
python backend/scripts/freeze_official_domains.py --check
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/check_structural_remediation_plan.py --check
python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict
```

Expected: all pass; Base 16/16 and 33/33; no Base unresolved/count hiding; canonical remaining and disposition counts equal a fresh immutable frontend scan; historical plan remains 37/45; strict acceptance has zero failed/skipped.

- [ ] **Step 6: Commit generated evidence and report**

Commit only builder/test/generated evidence changes. Record exact backend/frontend commits, immutable file count, Catalog release, acceptance report, commands, and outputs in the task report.
