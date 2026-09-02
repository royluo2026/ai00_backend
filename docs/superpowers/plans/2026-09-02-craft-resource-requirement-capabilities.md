# Craft Resource Requirement Capability Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver independently governed socket, tool, fixture, and equipment requirements whose nonempty Gateway contracts, TC matching, review workflow, legacy reconciliation, and BOP import path work against real test data.

**Architecture:** Keep the existing nine atomic `craft.resource_requirement.*@1` identities because they have not been approved or released. Repair their authoritative schemas and descriptors at the Craft Provider boundary, add `socket_need` as the fourth TC/BOP resource node, reuse the existing lineage staging panel for human decisions, and fix the independent BOP import-preview clock defect before running a real import transaction.

**Tech Stack:** Python, FastAPI, PyMySQL, MySQL/OceanBase SQL, Capability V2.5 Registry/Gateway, browser JavaScript, pytest, Node tests.

**Spec:** `docs/superpowers/specs/2026-09-02-craft-resource-requirement-capabilities-design.md`

## Global Constraints

- Work only in the existing backend and frontend verification worktrees; preserve unrelated dirty changes.
- Do not mutate production databases or deploy production services.
- `socket` is an independent requirement identity represented by `socket_need` and `resource_socket`.
- Public Capability input/output objects are closed; unknown engineering attributes fail explicitly rather than disappearing.
- All writes continue through the Gateway and Craft-owned Provider transaction boundary.
- Use tests with nonempty attributes, aliases, staging rows, and imported entries; empty HTTP 200 responses are insufficient.
- Keep `machine_passed`, `human_approved`, and `runtime_verified` independent.

---

### Task 1: Reproduce and repair the published Gateway contracts

**Files:**
- Modify: `plugins/craft/tests/test_resource_requirement_provider.py`
- Modify: `backend/tests/test_capability_catalog_release.py`
- Modify: `plugins/craft/craft_backend/capabilities/resource_requirements.py`
- Modify: `plugins/craft/craft_backend/capabilities/provider.py`

**Interfaces:**
- Consumes: `descriptor_for(spec) -> CapabilityDescriptorV2` and `validate_payload(schema, value)`.
- Produces: closed `RESOURCE_ATTRIBUTES`, `RESOURCE_ALIAS_ROW`, and `RESOURCE_STAGING_ROW` schemas; required staging `version_gid`; per-Capability errors and invariants.

- [ ] **Step 1: Write failing tests for real nonempty payloads**

  Add tests that construct the released descriptors and validate these literal values: a tool with `attributes={"gun_model":"G-01"}`, a resource row with alias `{"gid":"a-1","alias_value":"枪一"}`, and a staging row containing `gid`, `version_gid`, `entry_gid`, `resource_type`, `raw_name`, `raw_payload`, `match_status`, `candidate_resource_gids`, `resolved_resource_gid`, `review_note`, `resource_version`, and timestamps. Assert staging search rejects a missing `version_gid`.

- [ ] **Step 2: Run the focused tests and verify RED**

  Run: `python -m pytest plugins/craft/tests/test_resource_requirement_provider.py backend/tests/test_capability_catalog_release.py -q --tb=short`

  Expected: failures reporting unknown fields inside `attributes`, aliases, or staging items, and missing required `version_gid` not rejected.

- [ ] **Step 3: Implement the minimum closed schemas**

  Replace open objects with explicit properties. Support the existing legacy fields: tool fields `gun_model`, `matou_part_no`, `importance`, `gun_type`, `wireless`, `output_square`, `torque_min`, `torque_recommended`, `cad_model_no`, `socket_model`, `fastener_type`, `fastener_params`, `extension_model`, `socket_cad_no`, `extension_cad_no`, `category`, `legacy_spec`; socket fields `socket_model`, `socket_cad_no`, `fastener_type`, `fastener_params`; fixture/equipment fields `category`, `legacy_spec`. Define explicit alias and staging rows. Mark `version_gid` required.

- [ ] **Step 4: Declare exact governance metadata**

  Give create/update/retire/alias/staging actions their actual `BusinessInvariantContract` tuples and only their reachable `DomainErrorContract` entries. Add a create selector on `resource_type`. Remove generic no-invariant and no-consumer claims where a real rule or consumer exists.

- [ ] **Step 5: Run the focused tests and verify GREEN**

  Run the Step 2 command. Expected: all selected tests pass with no skips introduced by this task.

### Task 2: Make socket an independent legacy and TC resource

**Files:**
- Modify: `plugins/craft/tests/test_resource_requirement_provider.py`
- Modify: `backend/tests/test_domain_migration_runner.py`
- Create: `backend/db/migrations/domains/craft/0006_socket_resource_requirements.sql`
- Modify: `plugins/craft/craft_backend/capabilities/resource_requirements.py`
- Modify: `plugins/craft/craft_backend/routers/_bop/_constants.py`
- Modify: `plugins/craft/craft_backend/routers/_bop/entries.py`

**Interfaces:**
- Consumes: legacy `workmanship_tpl_vpps_tools.socket_model/socket_cad_no` and TC entry `node_type`.
- Produces: independent `socket` standards, `socket_need` matching, and `resource_socket` BOP links.

- [ ] **Step 1: Write failing socket identity tests**

  Assert `TC_RESOURCE_NODES["socket_need"] == ("socket", "resource_socket")`; exact and alias matching query the socket type; repeated legacy rows with the same preferred socket code describe one resulting socket standard; a socket cannot satisfy a `tool_need` link.

- [ ] **Step 2: Run the socket tests and verify RED**

  Run: `python -m pytest plugins/craft/tests/test_resource_requirement_provider.py backend/tests/test_domain_migration_runner.py backend/tests/test_resource_requirement_boundary.py -q --tb=short`

  Expected: `socket_need` is missing and migration reconciliation has no independent socket projection.

- [ ] **Step 3: Add the minimum mapping and resumable backfill**

  Add `socket_need` to the shared TC resource map. Keep applied migration `0004` unchanged. Add migration `0006` with a grouped insert selecting nonblank legacy socket values, using trimmed `socket_model` as code and `socket_cad_no` as fallback, retaining socket CAD and fastener fields, and using `ON DUPLICATE KEY UPDATE resource_version=resource_version` for reruns. Do not delete or rewrite legacy tool rows.

- [ ] **Step 4: Run the socket tests and verify GREEN**

  Run the Step 2 command. Expected: all selected tests pass.

### Task 3: Complete the TC review consumer and resource boundary

**Files:**
- Modify: `backend/tests/test_resource_requirement_boundary.py`
- Modify: `plugins/craft/craft_backend/routers/resource_requirements.py`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-v25-verify/packages/craft-plugin/web/lineage_view/staging_panel.js`
- Modify: `E:/Projects/ai00_v3/.worktrees/workmanship-web-v25-verify/packages/craft-plugin/web/lineage_view/index.html`
- Create: `E:/Projects/ai00_v3/.worktrees/workmanship-web-v25-verify/packages/craft-plugin/web/lineage_view/resource_staging_review.test.js`
- Modify: `plugins/craft/craft_backend/capabilities/contracts.py`

**Interfaces:**
- Consumes: required BOP `version_gid`, staging search/resolve/ignore REST adapters, active same-type resource search.
- Produces: an authorized resource-match subsection in the existing BOP staging panel and verified Web consumer refs for all three staging capabilities.

- [ ] **Step 1: Write failing route and browser tests**

  Assert the REST search route requires `version_gid`; the panel requests `/api/craft/tc-resource-staging?version_gid=<current>`; resolve sends `resource_gid` and `expected_staging_version`; ignore sends `expected_staging_version`; candidates are filtered by `resource_type`.

- [ ] **Step 2: Run focused tests and verify RED**

  Run backend boundary pytest and `node packages/craft-plugin/web/lineage_view/resource_staging_review.test.js` from the frontend worktree.

  Expected: optional route parameter and missing panel workflow failures.

- [ ] **Step 3: Reuse the existing staging panel**

  Add one compact resource-review section to `StagingPanel`; do not create a second page or duplicate matching rules. Require `version_gid` in FastAPI. Register the actual staging search/resolve/ignore Web consumer references in the authoritative Craft contract projection.

- [ ] **Step 4: Run focused tests and verify GREEN**

  Repeat Step 2. Expected: backend and Node tests pass.

### Task 4: Fix BOP import-preview time and prove transactional import

**Files:**
- Modify: `backend/tests/test_craft_write_capabilities.py`
- Modify: `plugins/craft/tests/test_resource_requirement_provider.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_writes.py`
- Modify only if the failing integration test proves necessary: `plugins/craft/craft_backend/capabilities/bop_entry_bulk_change.py`
- Modify only if the failing integration test proves necessary: `plugins/craft/craft_backend/routers/_bop/entries.py`

**Interfaces:**
- Consumes: UTC-aware preview timestamps, MySQL/OceanBase `UTC_TIMESTAMP(6)`, and `craft.bop.entry.bulk.change.apply(operation="import_tc")`.
- Produces: readable fresh previews, rejected expired previews, nonzero imported entries, and rollback on import failure.

- [ ] **Step 1: Write failing clock tests**

  Freeze a UTC-aware timestamp and assert `_db_datetime` persists a value comparable to `UTC_TIMESTAMP(6)`. Exercise repository lookup SQL and assert it uses `UTC_TIMESTAMP(6)`. Cover a fresh preview as readable and an expired preview as unavailable.

- [ ] **Step 2: Verify the clock tests fail for the observed +08 mismatch**

  Run: `python -m pytest backend/tests/test_craft_write_capabilities.py -q --tb=short`

- [ ] **Step 3: Make database comparison consistently UTC**

  Keep aware values normalized to naive UTC for storage and replace database expiry comparisons with `UTC_TIMESTAMP(6)`. Apply the same clock basis to change previews and import previews where applicable.

- [ ] **Step 4: Write a failing real import transaction test**

  Invoke the actual bulk-change Provider with literal TC rows including `line_process`, `socket_need`, `tool_need`, `fixture_need`, and `equipment_need`. Assert nonzero BOP entries and the matching resource links are committed. Inject a database failure mid-import and assert no partial entries, links, or staging decisions remain.

- [ ] **Step 5: Implement only the Provider/transaction changes demanded by RED**

  Preserve the public Capability identity and schema. Do not patch the frontend lifecycle flow in this task.

- [ ] **Step 6: Run Task 4 tests and verify GREEN**

  Run the selected BOP write, bulk-change, and resource tests. Expected: fresh/expired preview and commit/rollback scenarios pass.

### Task 5: Regenerate authoritative artifacts and run complete verification

**Files:**
- Regenerate: `docs/capabilities/catalog.v2.json`
- Regenerate: `docs/capabilities/craft/craft.resource_requirement.*@1.md`
- Regenerate: schema ownership/build artifacts and Web distribution artifacts using repository scripts.

**Interfaces:**
- Consumes: Tasks 1–4 source contracts and tests.
- Produces: current Catalog release, documentation, schema inventory, build output, governance scan, and bounded runtime evidence.

- [ ] **Step 1: Run focused backend and frontend suites**

  Run all resource requirement, BOP import, migration, Catalog, schema, boundary, and new browser tests. Record exact pass/fail/skip totals.

- [ ] **Step 2: Regenerate and check Catalog, docs, schema, and Web**

  Run `build_capability_catalog.py`, `generate_capability_docs.py`, schema compiler/checks, frontend build/tests, and official-domain hash checks using the repository's existing commands.

- [ ] **Step 3: Run the strict offline governance scan**

  Record Catalog release ID, capability totals, stable totals, Snapshot/hash, Finding outcome, and any skipped evidence. Do not convert machine pass into human approval.

- [ ] **Step 4: Run nonempty local runtime verification**

  Against the test database only, create controlled socket/tool/fixture/equipment rows with attributes and aliases, create one resource staging row, exercise search/resolve or ignore, and invoke a bounded real TC import. Clean up only records created under the test run's unique identity.

- [ ] **Step 5: Report governance state**

  Report `machine_passed`, `human_approved`, and `runtime_verified` independently, including current revisions, commands, raw outcomes, unavailable checks, and the fact that AI remains advisory.
