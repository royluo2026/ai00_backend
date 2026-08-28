# Base Structural Owner Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all 11 unresolved Base Web root-cause groups with closed, domain-owned services shared by REST compatibility and Capability Gateway adapters.

**Architecture:** Four public Base boundaries own saved views, self annotations, identity projection, and signed plugin installation lifecycle. Adapters translate only; repositories own persistence; closed contracts reject arbitrary nested JSON, and every write is actor-bound, idempotent, revision-aware, recoverable, and audited.

**Tech Stack:** Python 3.12, FastAPI, Pydantic/dataclasses, MySQL-compatible repositories, Capability V2 registry/providers, vanilla JavaScript Capability Gateway client, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-structural-owner-services-design.md`

## Global Constraints

- Do not add operations exclusions, BFF classifications, generic JSON schemas, direct-SQL providers, private-router imports, auto-confirmation, or cross-domain database access.
- REST handlers and Capability providers must delegate to the same public Base service method.
- Unknown input/output fields fail closed; destructive verbs produce recoverable tombstones, never permanent purge.
- Every write binds actor and tenant, checks expected revision where applicable, consumes an idempotency key, and writes durable audit evidence in the aggregate transaction.
- Frontend calls use exact stable `Capability@1` targets and explicit confirmation for writes.
- Preserve unrelated user changes in both worktrees.
- Backend worktree: `E:/Projects/ai00_v3/.worktrees/capability-v2-implementation`.
- Frontend worktree: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance`.

---

### Task 1: Saved-view aggregate service

**Files:**
- Create: `backend/base/saved_views.py`
- Modify: `backend/routers/views.py`
- Modify: `backend/base/web_atomic.py`
- Modify: `backend/capability_v2/atomic_web_contracts.py`
- Modify: `backend/scripts/build_base_structural_web_remediation.py`
- Test: `backend/tests/test_base_saved_view_service.py`
- Test: `backend/tests/test_base_structural_web_capabilities.py`

**Interfaces:**
- Consumes: `backend.db.connection.get_conn`, the existing actor identity supplied by both adapters, and the existing saved-view table.
- Produces: `SavedViewService.search(actor, query)`, `create(actor, command)`, `update(actor, view_gid, command)`, `copy(actor, view_gid, command)`, and `delete(actor, view_gid, command)` returning closed dictionaries; Capability targets `base.saved_view.search@1`, `create@1`, `update@1`, `copy@1`, and `delete@1`.

- [ ] **Step 1: Write failing service and contract tests**

Add tests that construct a fake transaction repository and require the following commands to reject unknown keys:

```python
VALID_CONFIG = {
    "field_gids": ["field_1"],
    "sort": [{"field_gid": "field_1", "direction": "asc"}],
    "filters": [{"field_gid": "field_1", "operator": "eq", "value": "open"}],
    "page_size": 50,
    "presentation": "table",
}

CREATE = {"name": "Open", "config": VALID_CONFIG, "share_scope": "private", "idempotency_key": "idem-1"}
UPDATE = {"expected_revision": 1, "name": "Open items", "config": VALID_CONFIG, "idempotency_key": "idem-2"}
COPY = {"name": "Copy", "idempotency_key": "idem-3"}
DELETE = {"expected_revision": 2, "idempotency_key": "idem-4"}
```

Assert owner/team/share visibility; copy resets grants and changes owner; duplicate idempotency returns the first result; stale revisions fail with `revision_conflict`; delete sets a tombstone and restore metadata; unknown config keys, operators, directions, presentation values, or page sizes outside `1..200` fail with `invalid_input`.

- [ ] **Step 2: Run tests and verify the red state**

Run: `python -m pytest backend/tests/test_base_saved_view_service.py backend/tests/test_base_structural_web_capabilities.py -q`

Expected: failure because `backend.base.saved_views.SavedViewService` and the five atomic registrations do not exist.

- [ ] **Step 3: Implement the minimal aggregate boundary**

Implement focused dataclasses or closed parsers with these exact callable signatures: `search(*, actor: dict, query: dict) -> dict`, `create(*, actor: dict, command: dict) -> dict`, `update(*, actor: dict, view_gid: str, command: dict) -> dict`, `copy(*, actor: dict, view_gid: str, command: dict) -> dict`, and `delete(*, actor: dict, view_gid: str, command: dict) -> dict`.

Use a single transaction per write to lock the aggregate, check authorization/revision/idempotency, mutate, and append the audit record. Keep SQL in the repository/service boundary; Capability handlers and the router only adapt inputs and errors. Register closed Capability schemas and strong/single-transaction metadata for writes.

- [ ] **Step 4: Make both adapters use the owner service**

Replace route-owned saved-view mutation/query logic with calls to the service. Add Capability handlers over those same methods. Update the Base remediation builder so the five exact normalized routes resolve only after the shared-boundary evidence and closed-contract tests exist.

- [ ] **Step 5: Run focused and governance tests**

Run: `python -m pytest backend/tests/test_base_saved_view_service.py backend/tests/test_base_structural_web_capabilities.py backend/tests/test_base_structural_remediation_manifest.py backend/tests/test_atomic_web_capability_contracts.py -q`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/base/saved_views.py backend/routers/views.py backend/base/web_atomic.py backend/capability_v2/atomic_web_contracts.py backend/scripts/build_base_structural_web_remediation.py backend/tests/test_base_saved_view_service.py backend/tests/test_base_structural_web_capabilities.py
git commit -m "feat: govern Base saved view lifecycle"
```

### Task 2: Self-annotation and identity projection services

**Files:**
- Create: `backend/base/self_annotations.py`
- Create: `backend/base/identity_profile.py`
- Modify: `backend/routers/self_annotations.py`
- Modify: `backend/routers/users.py`
- Modify: `backend/base/web_atomic.py`
- Modify: `backend/capability_v2/atomic_web_contracts.py`
- Modify: `backend/scripts/build_base_structural_web_remediation.py`
- Test: `backend/tests/test_base_self_annotation_service.py`
- Test: `backend/tests/test_base_identity_profile_service.py`

**Interfaces:**
- Consumes: Base attachment-reference validator port, current actor/session identity, and existing annotation/identity persistence.
- Produces: `SelfAnnotationService.get/search/apply_change`; `IdentityProfileService.get_current`; targets `base.self_annotation.record.get@1`, `search@1`, `change.apply@1`, and `base.identity.session.profile.get@1`.

- [ ] **Step 1: Write failing closed-projection tests**

Use the exact allowed attachment shape:

```python
ATTACHMENT = {
    "attachment_gid": "att_1",
    "media_type": "image/png",
    "display_name": "photo.png",
    "size": 42,
    "checksum": "sha256:" + "a" * 64,
}
CHANGE = {
    "item_gid": "item_1",
    "expected_revision": 1,
    "status": "open",
    "schedule": "2026-08-28",
    "note": "note",
    "attachments": [ATTACHMENT],
    "idempotency_key": "idem-ann-1",
}
```

Assert self-only reads/writes, bounded search (`limit <= 200`), attachment visibility validation, revision conflict, idempotent replay, tombstone on an explicit empty/deleted change, and rejection of unknown attachment/command keys. Assert the identity result contains only `actor_gid`, `display_name`, `tenant_gid`, `team_gids`, `locale`, `timezone`, and `permission_ids`; seed forbidden credential/token/recovery fields and prove they do not appear.

- [ ] **Step 2: Verify tests fail before implementation**

Run: `python -m pytest backend/tests/test_base_self_annotation_service.py backend/tests/test_base_identity_profile_service.py -q`

Expected: import/registration failures for the two new services.

- [ ] **Step 3: Implement services and shared adapters**

Implement `SelfAnnotationService.get(*, actor: dict, item_gid: str) -> dict`, `search(*, actor: dict, query: dict) -> dict`, and `apply_change(*, actor: dict, command: dict) -> dict`, plus `IdentityProfileService.get_current(*, actor: dict) -> dict`.

All annotation writes use one lock/revision/idempotency/audit transaction. Routers and Gateway handlers delegate to the services. Contracts set `additionalProperties: false` at every object level and never accept binary/credential data.

- [ ] **Step 4: Run focused and structural evidence tests**

Run: `python -m pytest backend/tests/test_base_self_annotation_service.py backend/tests/test_base_identity_profile_service.py backend/tests/test_base_structural_web_capabilities.py backend/tests/test_base_structural_remediation_manifest.py backend/tests/test_atomic_web_gateway_policy.py -q`

Expected: all pass and four exact route groups become capability-bindable.

- [ ] **Step 5: Commit**

```bash
git add backend/base/self_annotations.py backend/base/identity_profile.py backend/routers/self_annotations.py backend/routers/users.py backend/base/web_atomic.py backend/capability_v2/atomic_web_contracts.py backend/scripts/build_base_structural_web_remediation.py backend/tests/test_base_self_annotation_service.py backend/tests/test_base_identity_profile_service.py
git commit -m "feat: govern Base annotations and identity profile"
```

### Task 3: Signed plugin install and recoverable uninstall

**Files:**
- Modify: `backend/plugin_platform/service.py`
- Modify: `backend/plugin_platform/lifecycle.py`
- Modify: `backend/plugin_platform/compatibility.py`
- Modify: `backend/routers/plugins.py`
- Modify: `backend/base/web_atomic.py`
- Modify: `backend/capability_v2/atomic_web_contracts.py`
- Modify: `backend/scripts/build_base_structural_web_remediation.py`
- Test: `backend/tests/test_plugin_platform_service.py`
- Test: `backend/tests/test_base_plugin_lifecycle_capabilities.py`

**Interfaces:**
- Consumes: signed marketplace release registry, installation store, actor tenant context, and explicit confirmation metadata.
- Produces: `PluginPlatformService.request_install(actor, command)` and `transition_uninstall(actor, command)`; targets `base.plugin.installation.request.create@1` and `base.plugin.installation.transition.uninstall@1`.

- [ ] **Step 1: Add failing lifecycle/security tests**

Use closed commands:

```python
INSTALL = {
    "plugin_id": "plugin.example",
    "release_version": "1.2.3",
    "release_sha256": "sha256:" + "b" * 64,
    "requested_grants": ["project.read"],
    "idempotency_key": "idem-plugin-1",
}
UNINSTALL = {
    "plugin_id": "plugin.example",
    "expected_revision": 3,
    "retain_tenant_data": True,
    "idempotency_key": "idem-plugin-2",
}
```

Prove arbitrary URLs and unknown grants are rejected; release signature/hash/dependency failures make no installation change; install is tenant-bound and idempotent; uninstall atomically disables mounts, revokes grants, marks the installation uninstalled, preserves plugin data, and audits; stale revision and cross-tenant access fail; replay returns the original outcome.

- [ ] **Step 2: Verify the red state**

Run: `python -m pytest backend/tests/test_plugin_platform_service.py backend/tests/test_base_plugin_lifecycle_capabilities.py -q`

Expected: the public methods and Capability registrations are absent or the new security assertions fail.

- [ ] **Step 3: Implement the two transitions**

Add the two public service methods and keep release verification before the installation transaction. Inside uninstall's one transaction, lock installation/release/data-policy state, enforce tenant/revision/idempotency, revoke effective grants, disable mounts, retain tenant data, write audit, and return the new revision. Route and Gateway adapters call these exact methods; write Capabilities require user confirmation.

- [ ] **Step 4: Run plugin and governance tests**

Run: `python -m pytest backend/tests/test_plugin_platform_service.py backend/tests/test_base_plugin_lifecycle_capabilities.py backend/tests/test_plugin_marketplace_capabilities.py backend/tests/test_base_structural_remediation_manifest.py -q`

Expected: all pass and the obsolete arbitrary-URL path is not accepted by either adapter.

- [ ] **Step 5: Commit**

```bash
git add backend/plugin_platform/service.py backend/plugin_platform/lifecycle.py backend/plugin_platform/compatibility.py backend/routers/plugins.py backend/base/web_atomic.py backend/capability_v2/atomic_web_contracts.py backend/scripts/build_base_structural_web_remediation.py backend/tests/test_plugin_platform_service.py backend/tests/test_base_plugin_lifecycle_capabilities.py
git commit -m "feat: govern signed plugin installation lifecycle"
```

### Task 4: Base frontend migration and canonical closure

**Files:**
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/components/view_manager.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/components/self_annotation_panel.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/knowledge_hub/knowledge_hub.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/admin/task_planning.html`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/web/core/web_compat.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance/packages/craft-plugin/web/lineage_view/lineage.js`
- Modify: `docs/governance/base-structural-web-remediation.json`
- Modify: `docs/governance/web-api-route-inventory.json`
- Test: `backend/tests/test_base_structural_remediation_manifest.py`
- Test: `backend/tests/test_web_api_route_inventory.py`

**Interfaces:**
- Consumes: the 11 stable Base `@1` targets created in Tasks 1-3 and the existing frontend Capability Gateway client/confirmation helper.
- Produces: zero unresolved Base groups/occurrences in a fresh canonical scan without new BFF or operations exclusions.

- [ ] **Step 1: Add/adjust failing inventory expectations**

Make the Base structural manifest test require every Base group to carry `implementation_status=implemented`, exact provider/owner-service evidence, frontend callsite evidence, closed-contract evidence, and a stable target. Make the canonical inventory test assert no unresolved occurrence with `owner_domain == "base"` and no `/api/views`, `/api/self_ann`, session-profile, plugin-install, or plugin-uninstall REST call remains in governed frontend sources.

- [ ] **Step 2: Verify the old frontend fails the new expectations**

Run the manifest and Web inventory tests against frontend commit `6dd62900c9a82173adcbbe277bb38846ab556031` and record the 11 expected failing groups.

- [ ] **Step 3: Migrate callsites as a single frontend batch**

Use the existing client to invoke exact `Capability@1` targets. Supply revisions and idempotency keys on writes; require the existing confirmation flow before invoke/confirm; map returned closed projections to the current UI without a REST fallback. Plugin install UI selects a signed release and explicit grants, never a URL. Preserve the Project branch of mixed list handling.

- [ ] **Step 4: Regenerate evidence from source**

Run the checked-in Base remediation builder and canonical Web inventory builder with the backend and frontend worktree roots. Do not hand-edit generated hashes/counts. Verify the new frontend full SHA and source hashes are stored.

- [ ] **Step 5: Run Base batch acceptance**

Run:

```text
python -m pytest backend/tests/test_base_saved_view_service.py backend/tests/test_base_self_annotation_service.py backend/tests/test_base_identity_profile_service.py backend/tests/test_base_plugin_lifecycle_capabilities.py backend/tests/test_base_structural_remediation_manifest.py backend/tests/test_web_api_route_inventory.py -q
python backend/scripts/check_structural_remediation_plan.py
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict
```

Expected: all commands pass; Base unresolved groups/occurrences are zero; overall unresolved counts fall from 37/45 to 26/29 without count-hiding dispositions.

- [ ] **Step 6: Commit backend evidence and frontend migration separately**

```bash
git add docs/governance/base-structural-web-remediation.json docs/governance/web-api-route-inventory.json backend/tests/test_base_structural_remediation_manifest.py backend/tests/test_web_api_route_inventory.py
git commit -m "docs: close Base structural Web governance"

git -C E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance add web/components/view_manager.js web/components/self_annotation_panel.js web/knowledge_hub/knowledge_hub.js web/admin/task_planning.html web/core/web_compat.js packages/craft-plugin/web/lineage_view/lineage.js
git -C E:/Projects/ai00_v3/.worktrees/workmanship-web-capability-governance commit -m "feat: route Base flows through capability gateway"
```
