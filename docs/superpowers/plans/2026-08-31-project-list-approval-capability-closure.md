# Project/List and Approval Capability Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three remaining Project-facing REST occurrences with exact owner Capabilities and an atomic approval-rejection notification outcome.

**Architecture:** The shipped Web compatibility client performs finite pre-Gateway dispatch to existing Craft/Project atomic capabilities. Project Management adds one exact rejection capability whose business mutation and notification outbox event commit together.

**Tech Stack:** Python 3.12, pytest, MySQL/OceanBase SQL, JavaScript, Node.js, Vite, Capability Gateway V2.

**Spec:** `docs/superpowers/specs/2026-08-31-project-list-approval-capability-closure-design.md`

## Global Constraints

- No `/api/lists` or approval-reject REST fallback remains in committed Web source or `dist-production`.
- BOP version behavior remains Craft-owned; ordinary list behavior remains Project-owned.
- Every write requires confirmation, canonical idempotency, actor/team authorization, and optimistic revision where the resource is revisioned.
- Notification delivery uses a transactional outbox; transport availability cannot repeat or roll back the approval transition.
- This plan reduces the canonical remainder from 14 groups / 17 occurrences to 11 groups / 14 occurrences.

---

### Task 1: Finite list capability dispatch

**Files:**
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/core/existing_capability_client.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/dist-production/web/core/existing_capability_client.js`
- Create: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/scripts/test_project_list_capability_dispatch.js`
- Test: `backend/tests/test_special_web_residuals.py`

**Interfaces:**
- Consumes: `craft.bop.version.list@1`, `craft.bop.version.archive@1`, `project.list.read.atomic.lists_search@1`, and `project.list.change.apply.atomic.lists_delete@1`.
- Produces: `resolveListCapability({operation, itemType}) -> {capabilityId, write}` with no REST default.

- [ ] **Step 1: Add failing real-client dispatch tests**

```javascript
assert.deepEqual(resolveListCapability({ operation: 'search', itemType: 'bop_version' }), {
  capabilityId: 'craft.bop.version.list', write: false,
});
assert.deepEqual(resolveListCapability({ operation: 'delete', itemType: 'task' }), {
  capabilityId: 'project.list.change.apply.atomic.lists_delete', write: true,
});
assert.throws(() => resolveListCapability({ operation: 'search', itemType: 'unknown' }), /capability_not_bound/);
```

- [ ] **Step 2: Run the tests red**

Run: `node scripts/test_project_list_capability_dispatch.js`

Expected: FAIL because the current client still selects `/api/lists` branches.

- [ ] **Step 3: Implement the finite dispatcher and exact payload adapters**

```javascript
const LIST_CAPABILITIES = Object.freeze({
  bop_version: Object.freeze({ search: 'craft.bop.version.list', delete: 'craft.bop.version.archive' }),
  project: Object.freeze({ search: 'project.list.read.atomic.lists_search', delete: 'project.list.change.apply.atomic.lists_delete' }),
});
```

Map known Project item types to `project`; require `expectedRevision`, confirmation, and a stable idempotency key for delete; throw before network access for unknown types.

- [ ] **Step 4: Verify behavior and build**

Run: `node scripts/test_project_list_capability_dispatch.js`

Run: `npm run build:web`

Expected: PASS; source/dist contain no `GET:/api/lists` or `DELETE:/api/lists/{dynamic}` fallback.

- [ ] **Step 5: Commit frontend**

Commit: `feat: govern shared list dispatch`

### Task 2: Atomic Project approval rejection

**Files:**
- Modify: `plugins/project_management/project_management_backend/application/service.py`
- Modify: `plugins/project_management/project_management_backend/infrastructure/repository.py`
- Modify: `plugins/project_management/project_management_backend/capabilities/reviewed.py`
- Modify: `plugins/project_management/project_management_backend/capabilities/provider.py`
- Create: `backend/db/migrations/domains/project_management/0002_approval_notification_outbox.sql`
- Create: `plugins/project_management/tests/test_project_approval_reject_capability.py`

**Interfaces:**
- Consumes: existing approval-order repository and domain outbox conventions.
- Produces: `project.approval.order.reject@1` with input `{order_gid, comment, expected_revision}` and output `{order_gid, status, revision, notification_event_gid}`.

- [ ] **Step 1: Add failing transaction and replay tests**

```python
def test_reject_commits_order_operation_audit_and_outbox_once(application):
    first = application.reject_order(command, context)
    second = application.reject_order(command, context)
    assert second == first
    assert repository.count_notifications(first["notification_event_gid"]) == 1
```

Also test revision conflict, changed-payload idempotency conflict, cross-team not-found, and rollback when outbox insert fails.

- [ ] **Step 2: Run the focused test red**

Run: `python -m pytest plugins/project_management/tests/test_project_approval_reject_capability.py -q`

Expected: FAIL because no exact capability/outbox transaction exists.

- [ ] **Step 3: Implement the smallest owner transaction**

```python
def reject_order(*, command: RejectOrder, context: CapabilityContext) -> dict[str, object]:
    with repository.transaction() as tx:
        order = tx.require_order(command.order_gid, context.user_gid, context.team_gid)
        order.reject(comment=command.comment, expected_revision=command.expected_revision)
        event_gid = tx.enqueue_notification(order.rejection_notification())
        return tx.complete_idempotent(command, order.project(event_gid))
```

Register the exact closed contract and write policy; do not modify Craft approval adapters.

- [ ] **Step 4: Run Project tests and migration gates**

Run: `python -m pytest plugins/project_management/tests/test_project_approval_reject_capability.py plugins/project_management/tests/test_project_application.py -q`

Run: `python -m pytest backend/tests/test_domain_migrations.py -q`

Expected: PASS with one outbox event per committed rejection.

- [ ] **Step 5: Commit backend**

Commit: `feat: add governed approval rejection`

### Task 3: Migrate approval Web call through the real Gateway

**Files:**
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/packages/craft-plugin/web/approval/approval.js`
- Modify: matching `dist-production` output.
- Create: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/scripts/test_project_approval_reject_capability.js`
- Test: `backend/tests/test_web_compatibility_confirmation.py`

**Interfaces:**
- Consumes: `project.approval.order.reject@1` from Task 2.
- Produces: terminal/reconcilable rejection UI with no legacy notification side effect in Craft Web code.

- [ ] **Step 1: Add failing client/Gateway tests**

Assert missing confirmation, idempotency, and expected revision are rejected; success returns rejected status and one notification event identity; replay makes one provider call.

- [ ] **Step 2: Run tests red**

Run: `node scripts/test_project_approval_reject_capability.js`

Expected: FAIL on the existing REST request.

- [ ] **Step 3: Replace the request**

```javascript
await capabilityClient.invoke('project.approval.order.reject', {
  order_gid: gid,
  comment,
  expected_revision: revision,
}, { write: true, confirmed: true, idempotencyKey });
```

Remove the Web-side notification publication because the owner transaction now owns it.

- [ ] **Step 4: Verify and commit**

Run the Node test, syntax check, and `npm run build:web`.

Commit: `feat: migrate approval rejection to capability`

### Task 4: Freeze Project/List closure evidence

**Files:**
- Modify: `backend/scripts/build_craft_agent_project_structural_web_remediation.py`
- Modify: `backend/tests/test_craft_agent_project_structural_remediation_manifest.py`
- Regenerate: route ledger, atomic contracts, remediation manifest/plan, provider trust, Catalog, docs, and acceptance manifest.
- Create: `.superpowers/sdd/2026-08-31-project-list-approval-capability-closure/final-report.md`

**Interfaces:**
- Consumes: committed backend/frontend heads from Tasks 1-3.
- Produces: immutable evidence with Project/List 3/3 resolved and canonical remainder 11/14.

- [ ] **Step 1: Add failing source-derived closure assertions**

Assert exact frontend commit/blob identities, no three route literals, exact provider/contract/outbox anchors, and arithmetic `14/17 - 3/3 = 11/14`.

- [ ] **Step 2: Regenerate in dependency order**

Freeze frontend first, then rebuild route inventory, ledger, atomic contracts, remediation manifest, structural plan, provider trust, Catalog, docs, and acceptance manifest.

- [ ] **Step 3: Run final gates**

Run focused Project/Web tests, all generator `--check` commands, domain dependency/migration checks, and `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict`.

- [ ] **Step 4: Commit evidence and request whole-plan review**

Commit: `docs: close Project list and approval governance`

