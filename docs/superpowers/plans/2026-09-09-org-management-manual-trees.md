# Org Management Manual Trees Implementation Plan (test baseline)

> Gate: this plan may start only after the designated review task approves the revised spec and plan, and the user accepts any materially changed scope. Implement in the two existing feature worktrees based on `test`.

**Goal:** Deliver super-admin-maintained organization and project responsibility trees, explicit BOP-line mapping, source-safe BOP edit projection, later editing, and one-project responsibility matrix.

**Architecture:** Project Management owns revisioned responsibility configuration plus a durable projection operation/outbox. Craft supplies governed active-BOP line search/validation. Base applies idempotent source-scoped responsibility projections and preserves unrelated legacy grants. The web uses only exact atomic Capabilities and reports success only after projection completion.

**Constraints:** TDD for each task; no new npm dependency; no direct cross-domain SQL; no `replace_section_leads`; no name matching; every write requires envelope/body idempotency and capability confirmation; keep deterministic stable errors.

## Task 0 — Freeze contracts and RED governance tests

Files:

- Modify `plugins/project_management/project_management_backend/application/service.py`
- Modify `plugins/project_management/project_management_backend/capabilities/reviewed.py`
- Modify `plugins/project_management/project_management_backend/capabilities/provider.py`
- Modify Base/Craft capability registration files identified by focused `rg`
- Add/modify capability, Catalog, Descriptor and compatibility tests in each owner domain

Steps:

1. Add failing tests asserting every exact ID/version/schema/error/confirmation/idempotency/concurrency policy from spec §6.
2. Assert Project atomics have closed argument/output schemas; writes require `system.user.manage`, `confirmation='user'`, required idempotency and `expected_revision`.
3. Assert Craft search is cursor-bounded and active-only; Base projection is not web-callable and accepts only Project provider identity/evidence.
4. Add failing retirement tests for Base team v1 writes and old Project line-assignment atomic/REST after known consumers migrate.
5. Run focused tests and record RED causes before implementation.

## Task 1 — Project responsibility codec, repository CAS, operation/outbox

Files:

- Modify `plugins/project_management/project_management_backend/domain/models.py`
- Modify `plugins/project_management/project_management_backend/application/service.py`
- Modify `plugins/project_management/project_management_backend/infrastructure/repository.py`
- Add one `backend/db/migrations/20260909xxxx_project_org_management_operations.sql`
- Update `backend/governance/domain_table_ownership.json` and `backend/governance/table_inventory.json`
- Add Project repository/application/migration tests

Steps:

1. RED: codec defaults, stable line GID, trimmed unique names, unique non-null BOP GID, null-vs-omitted patch, unrelated meta preservation.
2. RED: real repository CAS with two writers; stale `expected_revision`; same-key replay; changed-payload conflict; outbox insert failure rolls back meta and operation.
3. Implement closed schema v1 and repository transaction: `SELECT ... FOR UPDATE`, compare revision, merge only `meta.org_management`, insert operation/audit/outbox, commit once.
4. Implement bounded tree/matrix/operation reads with opaque cursor and `page_size 1..100`. Matrix includes only configured/legacy manager and managed-line leaders.
5. GREEN focused repository/application/migration tests; commit this slice.

## Task 2 — Craft-owned active BOP line capabilities

Files:

- Add/modify Craft application/repository/capability Provider files under `plugins/craft/craft_backend`
- Modify Craft Catalog/Descriptor tests and BOP repository tests

Steps:

1. RED: search returns only entries whose version is exactly `status='active'`, project matches, entry is not deleted and `node_type='line_process'`; cursor and page size bounded; path deterministic.
2. RED: validate distinguishes inactive, wrong project, wrong node type and missing entry with stable codes.
3. Implement repository query in Craft only; register `craft.bop.active_line.search@1` and `.validate@1` through Provider/Descriptor/Catalog.
4. Add Project domain-client contract test proving envelope identity, cursor, no direct Craft SQL and governed error mapping.
5. GREEN focused Craft + boundary tests; commit.

## Task 3 — Base source-scoped responsibility projection

Files:

- Add one Base migration for source ledger and effective projection metadata
- Add Base repository/application/capability files in the existing Base pattern
- Update governance table ownership/inventory
- Add real repository, concurrency, capability and permission tests

Steps:

1. RED: applying manager/line source creates expected effective row; replay is no-op; stale revision cannot regress; changed payload conflicts.
2. RED: two source GIDs for same target retain access until last source is removed.
3. RED: pre-existing member/grant is recorded as baseline and survives final source removal; a row created by projection is deleted only by exact stored GID; unrelated line/user grants always survive.
4. RED: concurrent apply/remove serializes; transaction failure leaves ledger and effective row consistent.
5. Implement `base.project_responsibility.projection.apply@1` and get capability with trusted Project consumer policy, exact source/operation/revision contracts and stable outcomes.
6. Confirm BOP permission check observes the effective `section_lead` grant. Remove this feature's dependency on destructive `replace_section_leads` without deleting unrelated legacy SDK users.
7. GREEN Base repository/capability/permission/governance tests; commit.

## Task 4 — Project orchestration and reconciliation

Files:

- Modify Project application/provider/repository from Task 1
- Add Project domain clients for Craft validation and Base projection using existing governed gateway patterns
- Add a bounded worker/reconciliation entry using the repository's outbox conventions
- Add orchestration and gateway integration tests

Steps:

1. RED: manager/line create/update/delete verifies super admin, exact confirmation, expected revision and idempotency; invalid user/BOP fails before config commit.
2. RED: successful config commit + Base success marks operation completed; Base temporary failure leaves pending, never returns false success; retry with same operation converges once.
3. RED: terminal validation errors are stable; status read exposes pending/completed/failed without sensitive payload.
4. Implement exact Project read/change atomic capabilities from spec, using Craft validate before commit and Base apply after commit. Store projection command in outbox; retries use operation GID as stable key.
5. Implement reconciliation claim/lease/backoff so concurrent workers do not double-apply; completed operations are immutable.
6. GREEN application, real repository, gateway confirmation/idempotency, failure/retry and Catalog tests; commit.

## Task 5 — Organization invariants and breaking v2 migration

Files:

- Modify `backend/base/desktop_actions.py` and existing Base team application/router as needed
- Modify Base Provider/Descriptor/Catalog/deprecation manifests
- Add organization repository/role/concurrency/compatibility tests

Steps:

1. RED role matrix: team admin/member cannot create/update/archive/add/remove; super admin can.
2. RED invariants: missing/deleted parent, self parent, archive with child/member, duplicate archive, moving existing member, audit and concurrent mutation.
3. Publish `base.team.*@2` write capabilities with super-admin Provider checks, confirmation and required idempotency. Keep read capability behavior bounded.
4. Bind REST compatibility to Gateway v2; do not invoke router functions directly as an alternate authority path.
5. Delay v1 retirement switch until Task 7 migrates all known web consumers; add explicit deprecation metadata now.
6. GREEN Base tests; commit.

## Task 6 — Organization tree web UI

Files:

- Modify `workmanship-web/web/org_mgmt/org_mgmt.html`
- Modify `workmanship-web/web/org_mgmt/org_mgmt.js`
- Modify `workmanship-web/web/org_mgmt/org_mgmt.css`
- Add/modify `workmanship-web/web/tests/org_mgmt.test.js`

Steps:

1. RED jsdom tests using the real page: one combined tree, no sync controls/calls, parent hierarchy, orphan/cycle fallback, visible edit buttons.
2. RED writes: exact Base v2 atomics; same payload/key through confirmation challenge and retry; node busy; failure preserves rendered data.
3. Implement root/child create, rename/archive, Feishu-search add member and remove member. No reparent UI.
4. Handle `organization_not_empty`, `version_conflict`, `confirmation_required` and provider failure with actionable messages.
5. GREEN focused jsdom tests and web lint/build subset; commit in web worktree.

## Task 7 — Project tree, BOP picker, responsibility matrix web UI

Files: same org management HTML/JS/CSS/test files.

Steps:

1. RED: cursor pages merge into one `project → manager → lines` tree; later-edit buttons remain for every role/mapping; ordinary members absent from matrix.
2. RED: BOP picker lazy-loads Craft-backed Project read projection, shows full paths, submits GID only, shows stale mapping without guessing.
3. RED: write client sends exact Project atomic ID, body/envelope idempotency equality, expected revision and confirmation token; pending operation displays syncing and polls with bounded backoff; only completed toasts success.
4. Implement selected-project responsibility matrix and remove global cross-project matrix as the main view.
5. Migrate/remove every known old `/line-assignment` write consumer and old Base team v1 write consumer; keep project detail read-only matrix/navigation.
6. GREEN jsdom tests and `npm run build:web`; commit.

## Task 8 — Retire old writes and verify release gates

Files:

- Finalize Base/Project deprecation manifests and REST compatibility adapters
- Modify only defects exposed by verification

Steps:

1. Enable retirement tests: old Base team v1 writes and old Project line-assignment write return `capability_retired`; reads remain compatible.
2. Run focused backend suites for Project, Craft, Base, BOP permission, migration ownership, Provider/Descriptor/Catalog/Gateway/REST compatibility.
3. Run complete relevant plugin/backend tests, then full backend suite if practical; report exact passed/failed/skipped.
4. In web worktree rerun baseline/focused `npm test` and `npm run build:web`; report exact output. The local sibling-backend test fixture must resolve to the test-based backend worktree, not deploy.
5. Run `git diff --check`, inspect both worktree statuses and review only feature commits.
6. Request code review, fix validated findings with TDD, rerun affected and full gates.
7. Report `machine_passed`, `human_approved`, `runtime_verified`, feature-flag/rollback state separately. Do not merge to `test` or `deploy` without an explicit user request.

## Acceptance checklist

- [ ] Both trees show all existing records expected by their bounded read contracts.
- [ ] Only super admin can mutate organization/responsibility data through any known binding.
- [ ] Feishu is searched only when adding organization people; no automatic tree/member sync.
- [ ] Manual line maps by selected active BOP entry GID; stale mapping remains editable.
- [ ] Correct leader receives BOP edit; replacement/removal revokes only this source's need.
- [ ] Baseline/unrelated grants and concurrent source references survive.
- [ ] Every write supports later edit, expected revision, idempotent replay and confirmation.
- [ ] UI success means config and Base projection are completed.
- [ ] Single-project responsibility matrix remains available and excludes ordinary members.
- [ ] Capability/Catalog/Provider/Descriptor, migration ownership and compatibility gates pass.
