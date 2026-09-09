# Org Management Manual Trees Implementation Plan (test baseline)

> Gate: start business implementation only after the designated review task passes this revision. Use backend `test@3affc4e7c` and web `test@f2818cca` feature worktrees; do not merge without an explicit request.

**Goal:** Deliver super-admin-maintained organization and project responsibility trees, multiple project managers, multiple leaders per manual line, selected BOP-line mapping, real scoped BOP edit rights, later editing, and a one-project responsibility matrix.

**Architecture:** Base owns organizations, active principals, multi-manager assignments and source-scoped grants. Project Management owns revisioned manual-line configuration plus a durable projection Saga. Craft owns active-line discovery and BOP write authorization. Web consumers invoke exact atomic Capabilities only.

**Global constraints:** TDD; no direct cross-domain SQL; no `replace_section_leads`; no name matching; bounded reads; writes use exact Gateway confirmation and idempotency; Project worker never persists/replays confirmation tokens; no success UI until the line projection operation is completed.

## Task 0 — Freeze contracts and consumer inventory

Files:

- Modify `plugins/project_management/project_management_backend/application/service.py`
- Modify `plugins/project_management/project_management_backend/capabilities/reviewed.py`
- Modify `plugins/project_management/project_management_backend/capabilities/provider.py`
- Modify `backend/base/desktop_actions.py`, `backend/base/official_provider.py`
- Modify `plugins/craft/craft_backend/capabilities/__init__.py`, `plugins/craft/craft_backend/capabilities/provider.py`
- Add `backend/tests/test_org_management_capability_contracts.py`
- Modify `plugins/project_management/tests/test_project_capabilities.py`
- Modify `plugins/craft/tests/test_bop_domain_sharing.py`

Steps:

1. RED tests assert every ID/version/schema/error/exposure from spec §6, including closed arrays (`maxItems=50`), cursor/page size, `max_depth=32`, `max_nodes=5000`, expected revision and idempotency.
2. RED tests assert Project writes are `confirmation='user'`; downstream Base projection is `confirmation='none'`, web/agent exposure false and restricted to Project worker identity.
3. RED tests freeze the breaking-major/deprecation set for Base team writes, old line assignment and affected Craft BOP writes.
4. Record all consumer hits with `rg -n "base\.team\.|project\.member\.change\.apply|craft\.bop\..*change"` across backend and web worktrees; the minimum known list is the one in spec §6.
5. Run `python -m pytest backend/tests/test_org_management_capability_contracts.py plugins/project_management/tests/test_project_capabilities.py plugins/craft/tests/test_bop_domain_sharing.py -q`; retain RED evidence.

## Task 1 — Base active-principal and multi-manager authority

Files:

- Add `backend/base/project_responsibility.py`
- Add `backend/base/active_principal.py`
- Modify `backend/base/official_provider.py`
- Add `backend/db/migrations/202609090001_base_project_responsibility.sql`
- Modify `backend/governance/domain_table_ownership.json`, `backend/governance/table_inventory.json`
- Add `backend/tests/test_base_project_manager_repository.py`
- Add `backend/tests/test_base_project_responsibility_capabilities.py`
- Modify `backend/tests/test_bop_line_permissions.py`

Steps:

1. RED repository tests: unmanaged project returns legacy single manager; first replace sets managed and full zero-to-50 set; later clear stays managed; `(tenant,project,user,role)` unique; concurrent expected revision conflict; same-key replay and changed-payload conflict.
2. RED capability tests: `base.identity.active_principal.get@1` returns only GID/name/avatar/active; inactive/missing has stable error. `base.project_manager.read@1` is bounded; `replace@1` is super-only, user-confirmed, expected-revision and idempotent.
3. Implement Base transaction and migration without changing the old single-manager unique index. Access projection checks the new manager table when managed and otherwise falls back to legacy.
4. Give each managed manager project-scoped BOP edit via an exact Base-owned effective row; replacement removes only rows stored as created by the new manager authority.
5. Run `python -m pytest backend/tests/test_base_project_manager_repository.py backend/tests/test_base_project_responsibility_capabilities.py backend/tests/test_bop_line_permissions.py backend/tests/test_domain_table_ownership.py -q`; commit.

## Task 2 — Project manual-line codec, CAS and durable operation

Files:

- Modify `plugins/project_management/project_management_backend/domain/models.py`
- Modify `plugins/project_management/project_management_backend/application/service.py`
- Modify `plugins/project_management/project_management_backend/infrastructure/repository.py`
- Add `backend/db/migrations/202609090002_project_org_management_operations.sql`
- Modify `backend/governance/domain_table_ownership.json`, `backend/governance/table_inventory.json`
- Add `plugins/project_management/tests/test_org_management_repository.py`
- Add `plugins/project_management/tests/test_org_management_application.py`

Steps:

1. RED codec tests: revision-0 default; stable line GID; unique trimmed names/BOP GIDs; `leader_user_gids` deduped and capped at 50; null-vs-omitted patch; unrelated meta keys preserved.
2. RED real repository tests: two writers CAS; POST replay returns same GID; changed payload conflicts; outbox failure rolls back config/operation/audit; opaque GID keyset pages do not duplicate.
3. Implement one transaction using `SELECT ... FOR UPDATE`: compare expected revision, merge only `meta.org_management`, insert operation/audit/outbox and commit. Status is pending/completed/retryable/terminal.
4. Implement responsibility tree/matrix/operation reads. Compose manager data through Base capability client; ordinary project members never enter matrix.
5. Run `python -m pytest plugins/project_management/tests/test_org_management_repository.py plugins/project_management/tests/test_org_management_application.py backend/tests/test_domain_table_ownership.py -q`; commit.

## Task 3 — Craft active-line reads and real scoped authorization

Files:

- Add `plugins/craft/craft_backend/capabilities/bop_active_line.py`
- Modify `plugins/craft/craft_backend/capabilities/__init__.py`, `plugins/craft/craft_backend/capabilities/provider.py`
- Modify `plugins/craft/craft_backend/routers/_bop/_helpers.py`
- Modify `plugins/craft/craft_backend/capabilities/bop_entry_change.py`, `bop_entry_link_change.py`, `bop_staging_lifecycle_change.py`
- Modify `plugins/craft/craft_backend/routers/_bop/entries.py`, `plugins/craft/craft_backend/routers/_bop/staging.py`
- Add `plugins/craft/tests/test_bop_active_line_capabilities.py`
- Modify `plugins/craft/tests/test_bop_domain_sharing.py`, `backend/tests/test_bop_line_permissions.py`

Steps:

1. RED active-line search/validate tests: exact `status='active'`, project ownership, nondeleted `line_process`, deterministic GID keyset, path, max depth/nodes and `graph_limit_exceeded`.
2. RED role matrix: super admin edits all; each managed project manager edits its project; each section leader edits only mapped line descendants; member/team admin/unscoped project admin are read-only; inactive-version writes fail.
3. Implement Craft-owned query and exact capabilities. Remove broad role bypass from `_check_line_editable`; preserve copy-only exception without allowing original BOP mutation.
4. Publish `craft.bop.entry.change.apply@2`, `craft.bop.entry_link.change.apply@2`, and `craft.bop.staging.lifecycle.change.apply@2` plus their entry/staging compatibility bindings; old major remains deprecated until Task 8.
5. Run `python -m pytest plugins/craft/tests/test_bop_active_line_capabilities.py plugins/craft/tests/test_bop_domain_sharing.py backend/tests/test_bop_line_permissions.py -q`; commit.

## Task 4 — Base source-scoped multi-leader grant projection

Files:

- Extend `backend/base/project_responsibility.py`, `backend/base/official_provider.py`
- Add `backend/db/migrations/202609090003_base_line_responsibility_projection.sql`
- Modify governance ownership/inventory JSON
- Add `backend/tests/test_base_line_projection_repository.py`
- Add `backend/tests/test_base_line_projection_gateway.py`

Steps:

1. RED schema/repository tests for source, target, source-target, operation/idempotency unique keys and monotonic source revision.
2. RED behavior: zero-to-50 desired leaders; two sources share target; last source removal; baseline grant survives; projection-created exact GID is removed; unrelated grants survive; concurrent apply/remove serializes.
3. Implement one Base transaction. Never delete by line GID; target deletion is exact effective row GID and only after reference count zero.
4. Register `base.project_responsibility.projection.apply/get@1`. Build identity with `IdentityBroker.for_worker(service_principal, tenant_id, worker_id='project-org-projection')`; reject Web, Agent, user principal, other worker IDs and tenant mismatch.
5. Assert outbox evidence has parent capability/version GID, actor, tenant, operation, payload hash and audit ref but no token/secret.
6. Run `python -m pytest backend/tests/test_base_line_projection_repository.py backend/tests/test_base_line_projection_gateway.py backend/tests/test_consumer_identity_broker.py backend/tests/test_bop_line_permissions.py -q`; commit.

## Task 5 — Project orchestration, validation and stale reconciliation

Files:

- Modify Project application/repository/capability files from Task 2
- Add `plugins/project_management/project_management_backend/infrastructure/org_management_clients.py`
- Add `plugins/project_management/project_management_backend/infrastructure/org_management_worker.py`
- Modify `plugins/project_management/project_management_backend/capabilities/__init__.py`
- Add `plugins/project_management/tests/test_org_management_orchestration.py`
- Add `plugins/project_management/tests/test_org_management_gateway.py`

Steps:

1. RED writes validate every leader using `base.identity.active_principal.get@1` and every mapping using `craft.bop.active_line.validate@1` before config commit; direct Base/Craft SQL scan remains empty.
2. RED confirmation/idempotency/CAS tests for line create/update/delete/retry; exact payload and envelope key must match.
3. RED Saga tests: Base sync success completes; temporary failure remains pending and never reports success; leased worker retries same operation once; terminal failure visible; completed immutable.
4. Worker uses service principal + `for_worker`, never `_invoke_from_confirmed_parent` and never persists confirmation token. Base apply has no interactive confirmation because the user-confirmed Project parent owns the full business effect.
5. Stale scan is explicit worker/retry activity, never a read side effect: Craft validate inactive -> remove source projection but retain stale config; remap restores active projection.
6. Run `python -m pytest plugins/project_management/tests/test_org_management_orchestration.py plugins/project_management/tests/test_org_management_gateway.py plugins/project_management/tests/test_project_capabilities.py -q`; commit.

## Task 6 — Organization v2 invariants and compatibility

Files:

- Modify `backend/base/desktop_actions.py`, `backend/base/official_provider.py`, `backend/routers/teams.py`
- Modify `backend/base/web_atomic.py`, `backend/capability_v2/atomic_web_contracts.py`
- Regenerate `docs/governance/atomic-web-capability-contracts.json` with `backend/scripts/build_atomic_web_contracts.py`
- Add `backend/tests/test_team_admin_mutations.py`
- Modify `backend/tests/test_team_member_visibility.py`, `backend/tests/test_web_compatibility_adapters.py`

Steps:

1. RED role/invariant tests: only super admin writes; missing/deleted parent/self rejected; no reparent; archive with child/member rejected; move member audited atomically; replay/concurrency deterministic.
2. Publish `base.team.create/update/archive/member.add/member.remove@2` with user confirmation and required idempotency. REST compatibility binds Gateway v2, never direct authority logic.
3. Mark v1 deprecated but do not retire until every Task 7 consumer migrates.
4. Run `python backend/scripts/build_atomic_web_contracts.py --write`, then `python -m pytest backend/tests/test_team_admin_mutations.py backend/tests/test_team_member_visibility.py backend/tests/test_web_compatibility_adapters.py backend/tests/test_atomic_web_capability_contracts.py -q`; commit.

## Task 7 — Web UI and all consumer migration

Files:

- Modify `workmanship-web/web/org_mgmt/org_mgmt.html`, `org_mgmt.js`, `org_mgmt.css`
- Add `workmanship-web/web/tests/org_mgmt.test.js`
- Modify `workmanship-web/web/team_space/team_space.js`
- Add `workmanship-web/web/tests/team_space_permissions.test.js` and register it in `workmanship-web/web/tests/run_tests.js`
- Modify `workmanship-web/packages/craft-plugin/web/project/project.js`
- Modify `workmanship-web/packages/core/manifest.json`, `packages/craft-plugin/manifest.json`, `packages/sim-plugin/manifest.json`
- Modify `workmanship-web/scripts/build_desktop_round5_contracts.js` and generated `web/core/business_facade.js` through the repository generator

Steps:

1. RED jsdom: one organization tree; no sync; orphan/cycle fallback; visible edit buttons; Feishu search only for organization add-person.
2. RED project UI: GID-keyset pages merge into `project → manager group (0..50) → unique manual lines`; each line shows 0..50 leaders; matrix excludes ordinary members; BOP picker shows full path/stale state.
3. RED write flow: exact capability/major, expected revision, same body/envelope idempotency, confirmation challenge/retry, per-node busy, no optimistic update, pending polling and completed-only success.
4. Implement organization UI. Migrate `org_mgmt.js` to Base v2. In `team_space.js`, non-super users get read-only UI with “请联系超管”; super users use v2.
5. Implement Base manager multi-select and Project manual-line leader multi-select. BOP selection submits GID only; all edit/change/clear buttons remain.
6. Remove/redirect old project line-assignment writes in Craft project page; migrate affected Craft write majors and all manifest/facade/route consumer references.
7. Run `node web/tests/org_mgmt.test.js`, `node --test web/tests/team_space_permissions.test.js`, `node web/tests/run_tests.js`, `node scripts/test_existing_capability_migrations.js`, `node scripts/test_atomic_web_migrations.js`, `npm run build:web`; commit web changes.

## Task 8 — Generate governance artifacts, retire old writes, verify

Files:

- Modify generated backend Catalog/docs/route evidence only through the named scripts
- Finalize Base/Project/Craft deprecation manifests and compatibility adapters
- Modify only defects exposed by verification

Steps:

1. From backend worktree run:

   ```powershell
   python backend/scripts/build_capability_catalog.py --write
   python backend/scripts/build_atomic_web_contracts.py --check
   python backend/scripts/generate_capability_docs.py --write
   python backend/scripts/check_capability_v2_catalog_audit.py --fail-on-open-arguments --fail-on-default-all-exposure
   python backend/scripts/check_domain_change_governance.py --check --frontend-root E:\Projects\ai00_v3\workmanship-web\.worktrees\org-management-manual-trees
   python backend/scripts/check_web_capability_routes.py --web-root E:\Projects\ai00_v3\workmanship-web\.worktrees\org-management-manual-trees --write --fail-on-unresolved
   python backend/scripts/build_capability_catalog.py --check
   python backend/scripts/generate_capability_docs.py --check
   ```

2. Run `python backend/scripts/check_capability_v2_release_gate.py --web-root E:\Projects\ai00_v3\workmanship-web\.worktrees\org-management-manual-trees`; if trusted business approval is absent, report that gate separately—do not fabricate approval.
3. After route/consumer evidence proves zero old writes, switch v1/old Craft/line-assignment writes to `capability_retired`; assert reads remain compatible and all old write bindings return the stable error.
4. Run focused suites from Tasks 0–7, then `python -m pytest plugins/project_management/tests plugins/craft/tests backend/tests -q`; report exact counts.
5. From web worktree run `npm test` and `npm run build:web`. The sibling backend fixture must point to this test-based backend worktree.
6. Run `git diff --check 3affc4e7c..HEAD` in backend and `git diff --check f2818cca..HEAD` in web, inspect both `git status --short`, and request code review.
7. Fix only validated findings with RED/GREEN tests and rerun affected/full gates. Report `machine_passed`, `human_approved`, `runtime_verified` and advisory status independently.

## Acceptance checklist

- [ ] Existing organizations and projects render in bounded trees; no automatic organization/member/BOP-line import.
- [ ] Project manager group and every line support multiple people plus later add/remove/replace/clear.
- [ ] Only super admin mutates organization/responsibility configuration through every known binding.
- [ ] Ordinary members/team admins cannot edit all BOP; managers edit their project; line leaders edit mapped line scope only.
- [ ] Active BOP node GID, never name, controls mapping; stale mappings retain config but lose obsolete effective access through reconciliation.
- [ ] Shared/baseline/unrelated grants survive source removal; exact projection rows converge idempotently.
- [ ] Worker identity is service-only and no confirmation token is stored/replayed.
- [ ] Project config CAS/outbox and Base projection completion govern UI success.
- [ ] Team space/manifests/facade/project page and generated route/consumer evidence are migrated before retirement.
- [ ] Single-project responsibility matrix remains and excludes ordinary members.
- [ ] Catalog/Descriptor/Provider/Gateway, migration ownership, REST compatibility, jsdom, backend and build gates pass or are reported precisely.
